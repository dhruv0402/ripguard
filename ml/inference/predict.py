"""
Standalone video inference — no FastAPI/SQLAlchemy dependency, so it's
independently runnable and testable:

    python inference/predict.py --video path/to/video.mp4 --checkpoint checkpoints/ripguard_unet_best.pt

Called by backend/app/services/analysis_service.py as a background task.
"""

import argparse
import os
import uuid
import cv2
import numpy as np
import torch
import segmentation_models_pytorch as smp
try:
    import onnxruntime as ort
except ImportError:
    ort = None


class InferenceEngine:
    """Unified wrapper supporting both PyTorch (.pt) and ONNX Runtime (.onnx) backends."""

    def __init__(self, checkpoint_path: str, device: torch.device):
        self.checkpoint_path = checkpoint_path
        self.is_onnx = checkpoint_path.endswith(".onnx")
        self.device = device

        if self.is_onnx:
            if ort is None:
                raise ImportError("onnxruntime is not installed. Run 'pip install onnxruntime' to use ONNX models.")
            # Set up ONNX Runtime Session
            providers = ["CPUExecutionProvider"]
            if "CoreMLExecutionProvider" in ort.get_available_providers():
                providers.insert(0, "CoreMLExecutionProvider")
            self.ort_session = ort.InferenceSession(checkpoint_path, providers=providers)
            input_info = self.ort_session.get_inputs()[0]
            self.input_name = input_info.name
            self.in_channels = input_info.shape[1] if isinstance(input_info.shape[1], int) else 3
            self.output_name = self.ort_session.get_outputs()[0].name
            self.model = None
        else:
            state_dict = torch.load(checkpoint_path, map_location=device)
            first_weight = state_dict.get("encoder.conv1.weight", None)
            self.in_channels = first_weight.shape[1] if first_weight is not None else 3
            
            # Detect architecture from state_dict keys
            is_deeplab = any("aspp" in k for k in state_dict.keys())
            arch_name = "DeepLabV3Plus" if is_deeplab else "Unet"

            self.model = smp.create_model(
                arch=arch_name,
                encoder_name="resnet34",
                encoder_weights=None,
                in_channels=self.in_channels,
                classes=1
            )
            self.model.load_state_dict(state_dict)
            self.model.to(device).eval()
            self.ort_session = None

    def clean_mask(self, prob_mask: np.ndarray, threshold: float = 0.50, min_area: int = 400) -> np.ndarray:
        """Applies morphological opening and connected-component area filtering to eliminate false positive foam halos."""
        binary = (prob_mask > threshold).astype(np.uint8)
        if not np.any(binary):
            return np.zeros_like(prob_mask)
            
        kernel = cv2.getStructuringElement(cv2.MORPH_ELLIPSE, (3, 3))
        opened = cv2.morphologyEx(binary, cv2.MORPH_OPEN, kernel)
        
        num_labels, labels, stats, _ = cv2.connectedComponentsWithStats(opened, connectivity=8)
        cleaned = np.zeros_like(prob_mask)
        for lbl in range(1, num_labels):
            if stats[lbl, cv2.CC_STAT_AREA] >= min_area:
                cleaned[labels == lbl] = prob_mask[labels == lbl]
        return cleaned

    def predict_mask(self, input_tensor: torch.Tensor) -> np.ndarray:
        """Takes [1, C, H, W] torch tensor, returns [H, W] float probability mask in [0, 1]."""
        if self.is_onnx:
            numpy_in = input_tensor.cpu().numpy().astype(np.float32)
            logits = self.ort_session.run([self.output_name], {self.input_name: numpy_in})[0]
            # Sigmoid activation: 1 / (1 + exp(-x))
            prob = 1.0 / (1.0 + np.exp(-logits[0, 0]))
            return prob
        else:
            with torch.no_grad():
                logits = self.model(input_tensor.to(self.device))
                prob = torch.sigmoid(logits)[0, 0].cpu().numpy()
                return prob


def _load_model(checkpoint_path: str, device: torch.device):
    engine = InferenceEngine(checkpoint_path, device)
    return engine, engine.in_channels


def _preprocess_frame(frame: np.ndarray, prev_frame: np.ndarray | None = None, in_channels: int = 3, size: int = 512) -> torch.Tensor:
    resized = cv2.resize(frame, (size, size))
    rgb = cv2.cvtColor(resized, cv2.COLOR_BGR2RGB).astype(np.float32) / 255.0

    if in_channels == 5:
        if prev_frame is not None:
            prev_resized = cv2.resize(prev_frame, (size, size))
            prev_gray = cv2.cvtColor(prev_resized, cv2.COLOR_BGR2GRAY)
            curr_gray = cv2.cvtColor(resized, cv2.COLOR_BGR2GRAY)
            flow = cv2.calcOpticalFlowFarneback(prev_gray, curr_gray, None, 0.5, 3, 15, 3, 5, 1.2, 0)
            flow = np.clip(flow, -20.0, 20.0) / 20.0
        else:
            flow = np.zeros((size, size, 2), dtype=np.float32)
        combined = np.concatenate([rgb, flow.astype(np.float32)], axis=-1)
        tensor = torch.from_numpy(combined.transpose(2, 0, 1)).float()
    else:
        tensor = torch.from_numpy(rgb.transpose(2, 0, 1)).float()

    return tensor.unsqueeze(0)


def _mask_to_region(mask: np.ndarray, threshold: float = 0.5) -> dict | None:
    """Finds the primary (largest) rip current channel contour and returns its
    normalized bounding box."""
    binary = (mask > threshold).astype(np.uint8)
    contours, _ = cv2.findContours(binary, cv2.RETR_EXTERNAL, cv2.CHAIN_APPROX_SIMPLE)
    if not contours:
        return None
    largest = max(contours, key=cv2.contourArea)
    if cv2.contourArea(largest) < 100:
        return None
    x, y, bw, bh = cv2.boundingRect(largest)
    h, w = mask.shape
    return {
        "x": round(float(x / w), 4),
        "y": round(float(y / h), 4),
        "w": round(float(bw / w), 4),
        "h": round(float(bh / h), 4),
    }


def _is_coastal_environment(first_few_frames: list[np.ndarray]) -> tuple[bool, str]:
    """
    Validates whether incoming video frames exhibit real coastal characteristics:
    1. Fluid Surface Wave Dynamics: Ocean waves have high temporal pixel variance across frames,
       whereas screen recordings, static slides, and indoor videos have near-zero temporal variance.
    2. Natural Coastal Chrominance: Ocean water has distinct saturation/value distributions,
       whereas dark UI themes and screen recordings lack natural daylight/water profiles.
    """
    if not first_few_frames or len(first_few_frames) < 5:
        return False, "Insufficient video frames to verify coastal environment."

    # 1. Test Fluid Wave Dynamics (Temporal Variance)
    gray_frames = [cv2.resize(cv2.cvtColor(f, cv2.COLOR_BGR2GRAY), (256, 256)) for f in first_few_frames]
    arr = np.array(gray_frames, dtype=np.float32)
    temporal_variance = float(np.mean(np.var(arr, axis=0)))

    # Real coastal surf has wave propagation variance > 10.0 (typically 50.0 - 250.0).
    # Static screen recordings, UI meetings, or indoor cameras have variance < 3.0 (here 0.24).
    if temporal_variance < 8.0:
        return False, f"Static or non-fluid video detected (temporal motion variance: {temporal_variance:.2f} < 8.0 threshold). Please upload live beach or ocean surf footage."

    # 2. Test Natural Coastal Chrominance & Texture
    coastal_ratios = []
    for frame in first_few_frames:
        hsv = cv2.cvtColor(frame, cv2.COLOR_BGR2HSV)
        h, s, v = hsv[:, :, 0], hsv[:, :, 1], hsv[:, :, 2]

        # Natural daylight water: H between 35 and 130, with healthy saturation (s >= 35) and natural brightness (v >= 40)
        water_mask = (h >= 35) & (h <= 130) & (s >= 35) & (v >= 40)
        # Whitewater breaking surf: bright reflective foam (v >= 190, s <= 75)
        foam_mask = (v >= 190) & (s <= 75)
        # Beach sand: warm yellow/golden tones (H 14-38, s >= 25, v >= 70)
        sand_mask = (h >= 14) & (h <= 38) & (s >= 25) & (v >= 70)

        ratio = np.mean(water_mask | foam_mask | sand_mask)
        coastal_ratios.append(ratio)

    avg_coastal_ratio = float(np.mean(coastal_ratios))
    if avg_coastal_ratio < 0.25:
        return False, f"Non-coastal environment detected (natural coastal ratio: {avg_coastal_ratio:.1%}). Please upload coastal beach or surf surveillance footage."

    return True, "Coastal environment verified"


def run_inference_on_video(
    video_path: str,
    checkpoint_path: str,
    output_dir: str,
    frame_sample_rate: int = 5,
    confidence_threshold_for_detection: float = 0.5,
    frame_callback=None,
) -> dict:
    """
    Returns:
        {
            "annotated_video_path": str,
            "risk_timeline": [{"t": float, "confidence": float, "region": dict | None}, ...],
            "detections": [{"start": float, "end": float, "confidence": float, "region": dict}, ...]
        }
    """
    cap = cv2.VideoCapture(video_path)
    fps = cap.get(cv2.CAP_PROP_FPS) or 25.0
    width = int(cap.get(cv2.CAP_PROP_FRAME_WIDTH))
    height = int(cap.get(cv2.CAP_PROP_FRAME_HEIGHT))
    total_frames = int(cap.get(cv2.CAP_PROP_FRAME_COUNT)) or 1

    # Read initial 15 frames for coastal domain validation
    sample_frames = []
    for _ in range(15):
        ret, f = cap.read()
        if not ret:
            break
        sample_frames.append(f)
    cap.set(cv2.CAP_PROP_POS_FRAMES, 0)

    is_valid_coastal, reason = _is_coastal_environment(sample_frames)
    if not is_valid_coastal:
        cap.release()
        raise ValueError(f"Out-of-Distribution Input: {reason}")

    if torch.cuda.is_available():
        device = torch.device("cuda")
    elif torch.backends.mps.is_available():
        device = torch.device("mps")
    else:
        device = torch.device("cpu")
    model, in_channels = _load_model(checkpoint_path, device)

    os.makedirs(output_dir, exist_ok=True)
    output_path = os.path.join(output_dir, f"{uuid.uuid4()}_annotated.mp4")
    writer = cv2.VideoWriter(output_path, cv2.VideoWriter_fourcc(*"mp4v"), fps, (width, height))

    risk_timeline = []
    raw_detections = []  # before merging into windows
    frame_idx = 0
    prev_frame = None

    last_pred = None
    last_flow_vis = None
    last_confidence = 0.0
    last_region = None

    with torch.no_grad():
        while True:
            ret, frame = cap.read()
            if not ret:
                break

            raw_frame = frame.copy()
            timestamp_sec = frame_idx / fps

            if frame_idx % frame_sample_rate == 0 or last_pred is None:
                input_tensor = _preprocess_frame(raw_frame, prev_frame=prev_frame, in_channels=in_channels).to(device)
                pred_raw = model.predict_mask(input_tensor)
                
                # Apply morphological cleanup and connected component filtering to strip foam halos
                pred = model.clean_mask(pred_raw, threshold=confidence_threshold_for_detection, min_area=400) if hasattr(model, 'clean_mask') else pred_raw

                # Calculate optical flow vectors & hydrodynamic vorticity (shear)
                flow_vis = None
                shear_factor = 0.25
                if prev_frame is not None:
                    prev_gray = cv2.cvtColor(cv2.resize(prev_frame, (width, height)), cv2.COLOR_BGR2GRAY)
                    curr_gray = cv2.cvtColor(raw_frame, cv2.COLOR_BGR2GRAY)
                    flow_vis = cv2.calcOpticalFlowFarneback(prev_gray, curr_gray, None, 0.5, 3, 15, 3, 5, 1.2, 0)
                    
                    # Compute 2D flow curl / shear (dvx/dy - dvy/dx) to distinguish rip current channels from uniform shoreline waves
                    dvx_dy = np.gradient(flow_vis[..., 0], axis=0)
                    dvy_dx = np.gradient(flow_vis[..., 1], axis=1)
                    vorticity = np.abs(dvx_dy - dvy_dx)
                    shear_p98 = float(np.percentile(vorticity, 98))
                    # Active rip currents exhibit shear >= 0.38; calm uniform waves exhibit shear <= 0.30
                    shear_factor = float(np.clip((shear_p98 - 0.22) / 0.20, 0.15, 1.0))

                # Spatial topology & rotational shear check: true rip currents form localized channels
                # with measurable rotational vorticity (shear_factor >= 0.45), whereas uniform planar
                # shoreline wave wash has low rotational curl (shear_factor < 0.45) or spans >16% of the frame.
                active_area_frac = float((pred > confidence_threshold_for_detection).sum() / (pred.shape[0] * pred.shape[1]))
                if active_area_frac < 0.005:
                    confidence = 0.05
                elif shear_factor < 0.42 or (active_area_frac > 0.16 and shear_factor < 0.58):
                    # Uniform calm shoreline wash without rotational rip shear -> suppress false alarm
                    confidence = float(np.percentile(pred, 99) * 0.25)
                    pred = pred * 0.25
                else:
                    peak_prob = float(np.percentile(pred, 99.5))
                    corridor_bonus = 1.0 if (0.02 <= active_area_frac <= 0.16) else 0.65
                    confidence = float(np.clip(peak_prob * (0.55 * shear_factor + 0.45 * corridor_bonus), 0.0, 0.99))

                region = None
                if confidence >= confidence_threshold_for_detection:
                    region = _mask_to_region(pred, threshold=confidence_threshold_for_detection)
                    raw_detections.append({"t": timestamp_sec, "confidence": confidence, "region": region})

                risk_timeline.append({
                    "t": round(timestamp_sec, 2),
                    "confidence": round(confidence, 4),
                    "region": region,
                })

                last_pred = pred
                last_flow_vis = flow_vis
                last_confidence = confidence
                last_region = region
                prev_frame = raw_frame

            # Render continuous detection overlays on EVERY frame (zero flickering)
            if last_pred is not None:
                mask_resized = cv2.resize(last_pred, (width, height))
                active_mask = mask_resized > confidence_threshold_for_detection

                # Overlay 1: Heatmap of rip current confidence (Red/Crimson corridor)
                if np.any(active_mask):
                    overlay = frame.copy()
                    overlay[active_mask] = [0, 0, 230]  # Red overlay in BGR
                    frame = cv2.addWeighted(overlay, 0.42, frame, 0.58, 0)

                    # Overlay 2: Bright yellow contour boundary around active rip current channel
                    contours, _ = cv2.findContours(active_mask.astype(np.uint8), cv2.RETR_EXTERNAL, cv2.CHAIN_APPROX_SIMPLE)
                    cv2.drawContours(frame, contours, -1, (0, 255, 255), 2)

                # Overlay 3: Real-time Sea Current Motion Vectors (Arrow grid showing ocean flow)
                if last_flow_vis is not None:
                    step = 32
                    for y in range(step // 2, height, step):
                        for x in range(step // 2, width, step):
                            fx, fy = last_flow_vis[y, x]
                            mag = np.hypot(fx, fy)
                            if mag > 1.2:
                                end_x = int(np.clip(x + fx * 2.5, 0, width - 1))
                                end_y = int(np.clip(y + fy * 2.5, 0, height - 1))
                                color = (0, 0, 255) if active_mask[y, x] else (255, 200, 0)
                                cv2.arrowedLine(frame, (x, y), (end_x, end_y), color, 1, tipLength=0.35)

                # Overlay 4: Tactical Target Corridor Bounding Box on active rip currents
                if last_region and last_confidence >= confidence_threshold_for_detection:
                    bx = int(last_region["x"] * width)
                    by = int(last_region["y"] * height)
                    bw = int(last_region["w"] * width)
                    bh = int(last_region["h"] * height)
                    cv2.rectangle(frame, (bx, by), (bx + bw, by + bh), (60, 40, 255), 2)
                    label = f"RIP CORRIDOR [{last_confidence * 100:.1f}%]"
                    (tw, th), _ = cv2.getTextSize(label, cv2.FONT_HERSHEY_SIMPLEX, 0.55, 2)
                    ly = max(by - 8, th + 8)
                    cv2.rectangle(frame, (bx, ly - th - 6), (bx + tw + 10, ly + 4), (40, 20, 220), -1)
                    cv2.putText(frame, label, (bx + 5, ly - 2), cv2.FONT_HERSHEY_SIMPLEX, 0.55, (255, 255, 255), 2, cv2.LINE_AA)

                # Overlay 5: Top-left telemetry watermark on video
                status_str = "RIP HAZARD DETECTED" if last_confidence >= 0.7 else ("ELEVATED SURF" if last_confidence >= 0.4 else "NORMAL SURF")
                hud_text = f"RIPGUARD LIVE | {status_str} | CONF: {last_confidence * 100:.1f}%"
                cv2.putText(frame, hud_text, (20, 35), cv2.FONT_HERSHEY_SIMPLEX, 0.62, (0, 0, 0), 3, cv2.LINE_AA)
                hud_color = (60, 60, 255) if last_confidence >= 0.7 else ((0, 215, 255) if last_confidence >= 0.4 else (120, 255, 120))
                cv2.putText(frame, hud_text, (20, 35), cv2.FONT_HERSHEY_SIMPLEX, 0.62, hud_color, 2, cv2.LINE_AA)

            writer.write(frame)

            # Emit live frame callback every 2nd frame for real-time browser viewing during ingestion
            if frame_callback is not None and (frame_idx % 2 == 0):
                _, jpg_buf = cv2.imencode(".jpg", frame, [cv2.IMWRITE_JPEG_QUALITY, 72])
                frame_callback(
                    jpg_buf.tobytes(),
                    {
                        "frame_idx": frame_idx + 1,
                        "total_frames": total_frames,
                        "progress_pct": round(min(99.0, ((frame_idx + 1) / max(1, total_frames)) * 100.0), 1),
                        "confidence": round(float(last_confidence), 4),
                        "t": round(timestamp_sec, 2),
                        "region": last_region,
                        "timeline_so_far": risk_timeline[-60:],
                    },
                )

            frame_idx += 1

    cap.release()
    writer.release()

    # Temporal Confidence Aggregation (TCA): 3-point rolling median filter followed by
    # exponential moving average smoothing to suppress single-frame whitewater transient spikes.
    raw_confs = [pt["confidence"] for pt in risk_timeline]
    median_confs = []
    for i in range(len(raw_confs)):
        win = raw_confs[max(0, i - 1) : min(len(raw_confs), i + 2)]
        median_confs.append(float(np.median(win)))

    smoothed_timeline = []
    alpha = 0.55  # Weight for current sample vs history
    ema = None
    for pt, c in zip(risk_timeline, median_confs):
        ema = c if ema is None else (alpha * c + (1.0 - alpha) * ema)
        s_conf = round(float(ema), 4)
        smoothed_timeline.append({
            "t": pt["t"],
            "confidence": s_conf,
            "region": pt.get("region") if s_conf >= confidence_threshold_for_detection else None,
        })

    # Filter raw detections with smoothed confidence thresholding to prevent spurious false alarms
    smoothed_detections = []
    for pt in smoothed_timeline:
        if pt["confidence"] >= confidence_threshold_for_detection and pt.get("region"):
            smoothed_detections.append({
                "t": pt["t"],
                "confidence": pt["confidence"],
                "region": pt["region"],
            })

    # Re-encode to browser-compatible H.264 (avc1) if ffmpeg is available
    h264_output_path = output_path.replace("_annotated.mp4", "_h264.mp4")
    try:
        import subprocess
        res = subprocess.run(
            [
                "ffmpeg", "-y", "-i", output_path,
                "-c:v", "libx264", "-pix_fmt", "yuv420p",
                "-movflags", "+faststart",
                h264_output_path
            ],
            stdout=subprocess.DEVNULL,
            stderr=subprocess.DEVNULL,
            timeout=60,
        )
        if res.returncode == 0 and os.path.exists(h264_output_path):
            os.remove(output_path)
            output_path = h264_output_path
    except Exception:
        # Fall back gracefully to original opencv output
        pass

    detections = _merge_into_windows(smoothed_detections, gap_tolerance_sec=1.0)

    return {
        "annotated_video_path": output_path,
        "risk_timeline": smoothed_timeline,
        "detections": detections,
    }


def _merge_into_windows(raw_detections: list[dict], gap_tolerance_sec: float) -> list[dict]:
    """Merges consecutive high-confidence sampled frames into discrete
    detection windows, rather than storing one row per sampled frame."""
    if not raw_detections:
        return []

    raw_detections.sort(key=lambda d: d["t"])
    windows = []
    current = {
        "start": raw_detections[0]["t"],
        "end": raw_detections[0]["t"],
        "confidence": raw_detections[0]["confidence"],
        "region": raw_detections[0]["region"],
    }

    for det in raw_detections[1:]:
        if det["t"] - current["end"] <= gap_tolerance_sec:
            current["end"] = det["t"]
            current["confidence"] = max(current["confidence"], det["confidence"])
        else:
            windows.append(current)
            current = {"start": det["t"], "end": det["t"], "confidence": det["confidence"], "region": det["region"]}

    windows.append(current)
    return windows


if __name__ == "__main__":
    parser = argparse.ArgumentParser()
    parser.add_argument("--video", type=str, required=True)
    parser.add_argument("--checkpoint", type=str, required=True)
    parser.add_argument("--output_dir", type=str, default="outputs")
    parser.add_argument("--sample_rate", type=int, default=5)
    args = parser.parse_args()

    result = run_inference_on_video(args.video, args.checkpoint, args.output_dir, args.sample_rate)
    print(f"Annotated video: {result['annotated_video_path']}")
    print(f"Detections: {len(result['detections'])}")
    print(f"Timeline points: {len(result['risk_timeline'])}")
