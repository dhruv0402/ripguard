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
            self.model = smp.create_model(
                arch="Unet",
                encoder_name="resnet34",
                encoder_weights=None,
                in_channels=self.in_channels,
                classes=1
            )
            self.model.load_state_dict(state_dict)
            self.model.to(device).eval()
            self.ort_session = None

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
    """Collapses a predicted mask into a normalized bounding region for the
    `detections` table — a lightweight summary, not the full mask (the full
    annotated video carries the actual pixel-level overlay)."""
    binary = (mask > threshold).astype(np.uint8)
    ys, xs = np.where(binary > 0)
    if len(xs) == 0:
        return None
    h, w = mask.shape
    return {
        "x": float(xs.min() / w),
        "y": float(ys.min() / h),
        "w": float((xs.max() - xs.min()) / w),
        "h": float((ys.max() - ys.min()) / h),
    }


def _is_coastal_environment(first_few_frames: list[np.ndarray]) -> tuple[bool, str]:
    """
    Validates whether incoming video frames exhibit coastal characteristics
    (water, foam, sand, sky color distribution and ocean surface dynamics).
    Prevents out-of-distribution (OOD) false alarms on irrelevant indoor/street footage.
    """
    if not first_few_frames:
        return False, "Unable to read video frames"

    water_sand_foam_ratios = []
    for frame in first_few_frames:
        hsv = cv2.cvtColor(frame, cv2.COLOR_BGR2HSV)
        h, s, v = hsv[:, :, 0], hsv[:, :, 1], hsv[:, :, 2]

        # 1. Water spectrum: blue/cyan/green hues (H between 35 and 130)
        water_mask = (h >= 35) & (h <= 130) & (s >= 20) & (v >= 20)
        # 2. Whitewater foam / Breaking surf: high brightness, low saturation
        foam_mask = (v >= 200) & (s <= 60)
        # 3. Sand / beach tones: yellow-orange hues (H between 15 and 35) with moderate saturation
        sand_mask = (h >= 12) & (h <= 35) & (s >= 30) & (v >= 60)

        coastal_ratio = np.mean(water_mask | foam_mask | sand_mask)
        water_sand_foam_ratios.append(coastal_ratio)

    avg_coastal_ratio = float(np.mean(water_sand_foam_ratios))

    # Coastal surf environments typically contain >= 20% water, sand, or foam
    if avg_coastal_ratio < 0.18:
        return False, f"Non-coastal environment detected (coastal texture ratio: {avg_coastal_ratio:.1%}). Please upload coastal beach or surf surveillance footage."

    return True, "Coastal environment verified"


def run_inference_on_video(
    video_path: str,
    checkpoint_path: str,
    output_dir: str,
    frame_sample_rate: int = 5,
    confidence_threshold_for_detection: float = 0.5,
) -> dict:
    """
    Returns:
        {
            "annotated_video_path": str,
            "risk_timeline": [{"t": float, "confidence": float}, ...],
            "detections": [{"start": float, "end": float, "confidence": float, "region": dict}, ...]
        }
    """
    cap = cv2.VideoCapture(video_path)
    fps = cap.get(cv2.CAP_PROP_FPS) or 25.0
    width = int(cap.get(cv2.CAP_PROP_FRAME_WIDTH))
    height = int(cap.get(cv2.CAP_PROP_FRAME_HEIGHT))

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

    with torch.no_grad():
        while True:
            ret, frame = cap.read()
            if not ret:
                break

            timestamp_sec = frame_idx / fps

            if frame_idx % frame_sample_rate == 0:
                input_tensor = _preprocess_frame(frame, prev_frame=prev_frame, in_channels=in_channels).to(device)
                pred = model.predict_mask(input_tensor)
                confidence = float(pred.max())

                risk_timeline.append({"t": round(timestamp_sec, 2), "confidence": round(confidence, 4)})

                if confidence >= confidence_threshold_for_detection:
                    region = _mask_to_region(pred, threshold=confidence_threshold_for_detection)
                    raw_detections.append({"t": timestamp_sec, "confidence": confidence, "region": region})

                # Calculate optical flow vectors for visual sea current motion tracking
                flow_vis = None
                if prev_frame is not None:
                    prev_gray = cv2.cvtColor(cv2.resize(prev_frame, (width, height)), cv2.COLOR_BGR2GRAY)
                    curr_gray = cv2.cvtColor(frame, cv2.COLOR_BGR2GRAY)
                    flow_vis = cv2.calcOpticalFlowFarneback(prev_gray, curr_gray, None, 0.5, 3, 15, 3, 5, 1.2, 0)

                # Overlay 1: Heatmap of rip current confidence (Red/Orange corridor)
                mask_resized = cv2.resize(pred, (width, height))
                overlay = frame.copy()
                
                # Highlight rip corridor with vivid red/crimson glow
                active_mask = mask_resized > confidence_threshold_for_detection
                overlay[active_mask] = [0, 0, 230]  # Red overlay
                frame = cv2.addWeighted(overlay, 0.45, frame, 0.55, 0)

                # Overlay 2: Contour boundary outline around active rip current corridor
                if np.any(active_mask):
                    contours, _ = cv2.findContours(active_mask.astype(np.uint8), cv2.RETR_EXTERNAL, cv2.CHAIN_APPROX_SIMPLE)
                    cv2.drawContours(frame, contours, -1, (0, 255, 255), 2)  # Bright yellow contour edge

                # Overlay 3: Real-time Sea Current Motion Vectors (Arrow grid showing ocean flow)
                if flow_vis is not None:
                    step = 32  # Grid spacing for vector arrows
                    for y in range(step // 2, height, step):
                        for x in range(step // 2, width, step):
                            fx, fy = flow_vis[y, x]
                            mag = np.hypot(fx, fy)
                            if mag > 1.2:  # Only draw vectors with noticeable motion
                                end_x = int(np.clip(x + fx * 2.5, 0, width - 1))
                                end_y = int(np.clip(y + fy * 2.5, 0, height - 1))
                                # In rip current regions, draw arrows in bright red/yellow; in surrounding water, draw in cyan
                                color = (0, 0, 255) if active_mask[y, x] else (255, 200, 0)
                                cv2.arrowedLine(frame, (x, y), (end_x, end_y), color, 1, tipLength=0.35)

                # Overlay 4: Top-left telemetry watermark on video
                cv2.putText(
                    frame,
                    f"RIPGUARD TRACKER | CONF: {confidence * 100:.1f}% | FLOW ACTIVE",
                    (20, 35),
                    cv2.FONT_HERSHEY_SIMPLEX,
                    0.6,
                    (0, 0, 0),
                    3,
                    cv2.LINE_AA,
                )
                cv2.putText(
                    frame,
                    f"RIPGUARD TRACKER | CONF: {confidence * 100:.1f}% | FLOW ACTIVE",
                    (20, 35),
                    cv2.FONT_HERSHEY_SIMPLEX,
                    0.6,
                    (0, 255, 255) if confidence >= 0.5 else (255, 255, 255),
                    1,
                    cv2.LINE_AA,
                )

            prev_frame = frame.copy()
            writer.write(frame)
            frame_idx += 1

    cap.release()
    writer.release()

    # Temporal Confidence Aggregation (TCA): Exponential moving average smoothing
    # across sampled confidence points to suppress single-frame whitewater transient spikes.
    smoothed_timeline = []
    alpha = 0.65  # Weight for current sample vs history
    ema = None
    for pt in risk_timeline:
        c = pt["confidence"]
        ema = c if ema is None else (alpha * c + (1.0 - alpha) * ema)
        smoothed_timeline.append({"t": pt["t"], "confidence": round(float(ema), 4)})

    # Filter raw detections with smoothed confidence thresholding to prevent spurious false alarms
    smoothed_detections = []
    for raw_det, smooth_pt in zip(raw_detections, smoothed_timeline):
        if smooth_pt["confidence"] >= confidence_threshold_for_detection:
            smoothed_detections.append({
                "t": raw_det["t"],
                "confidence": smooth_pt["confidence"],
                "region": raw_det["region"]
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
