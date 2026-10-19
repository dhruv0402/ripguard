"""
Stream ingestion service:
Handles live coastal camera feeds (RTSP streams, HTTP video feeds, local webcams, or looped drone test clips).
Runs frame sampling, runs ONNX / PyTorch inference, overlays real-time rip current segmentation masks,
and provides an async generator yielding JPEG frames for multipart MJPEG streaming + WebSocket alert broadcast.
"""

import asyncio
import base64
import os
import sys
import time
import cv2
import numpy as np
import torch

sys.path.append(os.path.join(os.path.dirname(__file__), "..", "..", "ml"))
from inference.predict import _load_model, _preprocess_frame, _mask_to_region  # noqa: E402
from app.core.config import get_settings  # noqa: E402
from app.services.alert_service import default_alert_dispatcher  # noqa: E402

settings = get_settings()


from enum import Enum


class StreamStatus(str, Enum):
    INITIALIZING = "initializing"
    STREAMING = "streaming"
    RECONNECTING = "reconnecting"
    DEGRADED = "degraded"
    OFFLINE = "offline"


class LiveStreamManager:
    def __init__(self, stream_source: str | int = 0, checkpoint_path: str | None = None):
        self.stream_source = stream_source
        self.checkpoint_path = checkpoint_path or (
            "ml/checkpoints/ripguard_motion_unet_best.onnx"
            if os.path.exists("ml/checkpoints/ripguard_motion_unet_best.onnx")
            else settings.model_checkpoint_path
        )
        self.is_running = False
        self.stream_status = StreamStatus.INITIALIZING
        self.reconnect_count = 0
        self.device = (
            torch.device("cuda")
            if torch.cuda.is_available()
            else (torch.device("mps") if torch.backends.mps.is_available() else torch.device("cpu"))
        )
        self.model = None
        self.in_channels = 3
        self.latest_frame_jpeg: bytes | None = None
        self.latest_meta: dict = {
            "status": StreamStatus.INITIALIZING.value,
            "confidence": 0.0,
            "risk_level": "LOW",
            "fps": 0.0,
            "timestamp": time.time(),
            "reconnect_count": 0,
        }
        self.subscribers: set[asyncio.Queue] = set()

    def _init_model(self):
        if self.model is None:
            self.model, self.in_channels = _load_model(self.checkpoint_path, self.device)

    async def start(self):
        if self.is_running:
            return
        self._init_model()
        self.is_running = True
        self.stream_status = StreamStatus.INITIALIZING
        asyncio.create_task(self._capture_and_infer_loop())

    def stop(self):
        self.is_running = False
        self.stream_status = StreamStatus.OFFLINE


    async def _capture_and_infer_loop(self):
        source = self.stream_source
        if isinstance(source, str) and source.isdigit():
            source = int(source)

        cap = None
        backoff_seconds = 1.0
        max_backoff = 30.0

        prev_frame = None
        ema_confidence = 0.0
        alpha = 0.65
        fps_timer = time.time()
        frame_count = 0
        current_fps = 0.0

        try:
            while self.is_running:
                # Open or re-open capture if not open
                if cap is None or not cap.isOpened():
                    self.stream_status = StreamStatus.INITIALIZING if self.reconnect_count == 0 else StreamStatus.RECONNECTING
                    self.latest_meta["status"] = self.stream_status.value
                    cap = cv2.VideoCapture(source)
                    if not cap.isOpened():
                        self.reconnect_count += 1
                        self.latest_meta["reconnect_count"] = self.reconnect_count
                        await asyncio.sleep(min(backoff_seconds, max_backoff))
                        backoff_seconds = min(backoff_seconds * 1.5, max_backoff)
                        continue
                    else:
                        backoff_seconds = 1.0

                ret, frame = cap.read()
                if not ret:
                    # Loop back if it's a test video file
                    if isinstance(source, str) and os.path.exists(source):
                        cap.set(cv2.CAP_PROP_POS_FRAMES, 0)
                        await asyncio.sleep(0.01)
                        continue
                    else:
                        self.reconnect_count += 1
                        self.stream_status = StreamStatus.RECONNECTING
                        self.latest_meta["status"] = StreamStatus.RECONNECTING.value
                        self.latest_meta["reconnect_count"] = self.reconnect_count
                        if cap is not None:
                            cap.release()
                            cap = None
                        await asyncio.sleep(min(backoff_seconds, max_backoff))
                        backoff_seconds = min(backoff_seconds * 1.5, max_backoff)
                        continue

                backoff_seconds = 1.0
                self.stream_status = StreamStatus.STREAMING

                frame_count += 1
                now = time.time()
                if now - fps_timer >= 1.0:
                    current_fps = round(frame_count / (now - fps_timer), 1)
                    frame_count = 0
                    fps_timer = now

                h, w = frame.shape[:2]

                # Run heavy ONNX/PyTorch inference every 3rd frame to keep stream playback buttery smooth (30 FPS)
                if frame_count % 3 == 0 or 'last_pred' not in locals():
                    input_tensor = _preprocess_frame(frame, prev_frame=prev_frame, in_channels=self.in_channels)
                    last_pred = self.model.predict_mask(input_tensor)
                    raw_conf = float(last_pred.max())
                    ema_confidence = alpha * raw_conf + (1.0 - alpha) * ema_confidence

                pred = last_pred

                # Overlay segmentation mask in red if rip current detected
                if ema_confidence >= 0.40:
                    mask_resized = cv2.resize(pred, (w, h))
                    overlay = frame.copy()
                    overlay[mask_resized > 0.40] = [0, 0, 255]  # Red overlay (BGR)
                    frame = cv2.addWeighted(overlay, 0.4, frame, 0.6, 0)

                # Determine risk level
                risk_level = "LOW"
                if ema_confidence >= 0.70:
                    risk_level = "HIGH"
                elif ema_confidence >= 0.40:
                    risk_level = "MEDIUM"

                # Encode to JPEG with optimal performance quality (65)
                _, buffer = cv2.imencode(".jpg", frame, [cv2.IMWRITE_JPEG_QUALITY, 65])
                self.latest_frame_jpeg = buffer.tobytes()

                self.latest_meta = {
                    "status": self.stream_status.value,
                    "confidence": round(ema_confidence, 4),
                    "risk_level": risk_level,
                    "fps": current_fps,
                    "timestamp": round(now, 2),
                    "reconnect_count": self.reconnect_count,
                }

                # Evaluate for sustained high-risk alert dispatch
                dispatched_alert = default_alert_dispatcher.process_telemetry(self.latest_meta)
                if dispatched_alert:
                    self.latest_meta["latest_alert"] = dispatched_alert

                # Broadcast metadata to subscribers
                dead_subs = set()
                for q in self.subscribers:
                    try:
                        q.put_nowait(self.latest_meta)
                    except asyncio.QueueFull:
                        pass
                    except Exception:
                        dead_subs.add(q)
                self.subscribers.difference_update(dead_subs)

                prev_frame = frame.copy()
                # Yield control to event loop
                await asyncio.sleep(0.02)

        finally:
            if cap is not None:
                cap.release()
            self.stream_status = StreamStatus.OFFLINE
            self.is_running = False



class MultiStreamRegistry:
    """Thread-safe registry managing independent concurrent live camera/RTSP streams."""

    def __init__(self):
        self.streams: dict[str, LiveStreamManager] = {}
        self.lock = asyncio.Lock()

    def register_stream(self, stream_id: str, source: str | int | None = None) -> LiveStreamManager:
        src = source if source is not None else stream_id
        manager = LiveStreamManager(stream_source=src)
        self.streams[stream_id] = manager
        return manager

    def get_stream(self, stream_id: str) -> LiveStreamManager | None:
        return self.streams.get(stream_id)

    def deregister_stream(self, stream_id: str):
        manager = self.streams.pop(stream_id, None)
        if manager and manager.is_running:
            manager.stop()

    def list_active_streams(self) -> list[str]:
        return list(self.streams.keys())

    async def get_or_create(self, source: str | None = None) -> LiveStreamManager:
        src = source or (
            "test_assets/beach_ripvis_072.mp4"
            if os.path.exists("test_assets/beach_ripvis_072.mp4")
            else "test_assets/active_rip_current.mp4"
        )
        async with self.lock:
            if src not in self.streams:
                self.streams[src] = LiveStreamManager(stream_source=src)
            manager = self.streams[src]
            if not manager.is_running:
                await manager.start()
            return manager

    async def stop_all(self):
        async with self.lock:
            for manager in self.streams.values():
                manager.stop()
            self.streams.clear()



stream_registry = MultiStreamRegistry()

# Backwards-compatible default stream manager
default_stream_manager = LiveStreamManager(
    stream_source="test_assets/beach_ripvis_072.mp4"
    if os.path.exists("test_assets/beach_ripvis_072.mp4")
    else "test_assets/active_rip_current.mp4"
)

