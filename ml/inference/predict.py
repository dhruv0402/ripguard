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


def _load_model(checkpoint_path: str, device: torch.device):
    state_dict = torch.load(checkpoint_path, map_location=device)
    # Check if checkpoint expects 5 input channels (motion model) or 3 channels (appearance)
    first_weight = state_dict.get("encoder.conv1.weight", None)
    in_channels = first_weight.shape[1] if first_weight is not None else 3

    model = smp.create_model(arch="Unet", encoder_name="resnet34", encoder_weights=None, in_channels=in_channels, classes=1)
    model.load_state_dict(state_dict)
    model.to(device).eval()
    return model, in_channels


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
    if torch.cuda.is_available():
        device = torch.device("cuda")
    elif torch.backends.mps.is_available():
        device = torch.device("mps")
    else:
        device = torch.device("cpu")
    model, in_channels = _load_model(checkpoint_path, device)

    cap = cv2.VideoCapture(video_path)
    fps = cap.get(cv2.CAP_PROP_FPS) or 25.0
    width = int(cap.get(cv2.CAP_PROP_FRAME_WIDTH))
    height = int(cap.get(cv2.CAP_PROP_FRAME_HEIGHT))

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
                pred = torch.sigmoid(model(input_tensor))[0, 0].cpu().numpy()
                confidence = float(pred.max())

                risk_timeline.append({"t": round(timestamp_sec, 2), "confidence": round(confidence, 4)})

                if confidence >= confidence_threshold_for_detection:
                    region = _mask_to_region(pred, threshold=confidence_threshold_for_detection)
                    raw_detections.append({"t": timestamp_sec, "confidence": confidence, "region": region})

                # Overlay: resize mask back to frame size, tint flagged regions
                mask_resized = cv2.resize(pred, (width, height))
                overlay = frame.copy()
                overlay[mask_resized > confidence_threshold_for_detection] = [0, 0, 255]  # red tint, BGR
                frame = cv2.addWeighted(overlay, 0.4, frame, 0.6, 0)

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
