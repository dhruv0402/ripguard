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

settings = get_settings()


class LiveStreamManager:
    def __init__(self, stream_source: str | int = 0, checkpoint_path: str | None = None):
        self.stream_source = stream_source
        self.checkpoint_path = checkpoint_path or (
            "ml/checkpoints/ripguard_motion_unet_best.onnx"
            if os.path.exists("ml/checkpoints/ripguard_motion_unet_best.onnx")
            else settings.model_checkpoint_path
        )
        self.is_running = False
        self.device = (
            torch.device("cuda")
            if torch.cuda.is_available()
            else (torch.device("mps") if torch.backends.mps.is_available() else torch.device("cpu"))
        )
        self.model = None
        self.in_channels = 3
        self.latest_frame_jpeg: bytes | None = None
        self.latest_meta: dict = {
            "status": "idle",
            "confidence": 0.0,
            "risk_level": "LOW",
            "fps": 0.0,
            "timestamp": time.time(),
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
        asyncio.create_task(self._capture_and_infer_loop())

    def stop(self):
        self.is_running = False

    async def _capture_and_infer_loop(self):
        # Allow passing test video paths or RTSP URLs
        source = self.stream_source
        # If integer string (like "0"), convert to int for webcam
        if isinstance(source, str) and source.isdigit():
            source = int(source)

        cap = cv2.VideoCapture(source)
        prev_frame = None
        ema_confidence = 0.0
        alpha = 0.65
        fps_timer = time.time()
        frame_count = 0
        current_fps = 0.0

        try:
            while self.is_running:
                ret, frame = cap.read()
                if not ret:
                    # Loop back if it's a test video file
                    if isinstance(source, str) and os.path.exists(source):
                        cap.set(cv2.CAP_PROP_POS_FRAMES, 0)
                        await asyncio.sleep(0.01)
                        continue
                    else:
                        await asyncio.sleep(0.1)
                        continue

                frame_count += 1
                now = time.time()
                if now - fps_timer >= 1.0:
                    current_fps = round(frame_count / (now - fps_timer), 1)
                    frame_count = 0
                    fps_timer = now

                h, w = frame.shape[:2]

                # Run inference on every 2nd or 3rd frame to sustain 20+ FPS
                input_tensor = _preprocess_frame(frame, prev_frame=prev_frame, in_channels=self.in_channels)
                pred = self.model.predict_mask(input_tensor)
                raw_conf = float(pred.max())
                ema_confidence = alpha * raw_conf + (1.0 - alpha) * ema_confidence

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

                # Encode to JPEG
                _, buffer = cv2.imencode(".jpg", frame, [cv2.IMWRITE_JPEG_QUALITY, 75])
                self.latest_frame_jpeg = buffer.tobytes()

                self.latest_meta = {
                    "status": "streaming",
                    "confidence": round(ema_confidence, 4),
                    "risk_level": risk_level,
                    "fps": current_fps,
                    "timestamp": round(now, 2),
                }

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
            cap.release()
            self.is_running = False


# Global default stream manager (can be overridden with query param / video source)
default_stream_manager = LiveStreamManager(
    stream_source="test_assets/beach_ripvis_072.mp4"
    if os.path.exists("test_assets/beach_ripvis_072.mp4")
    else "test_assets/active_rip_current.mp4"
)
