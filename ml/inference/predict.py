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
    model = smp.create_model(arch="Unet", encoder_name="resnet34", encoder_weights=None, in_channels=3, classes=1)
    model.load_state_dict(torch.load(checkpoint_path, map_location=device))
    model.to(device).eval()
    return model


def _preprocess_frame(frame: np.ndarray, size: int = 512) -> torch.Tensor:
    resized = cv2.resize(frame, (size, size))
    rgb = cv2.cvtColor(resized, cv2.COLOR_BGR2RGB)
    tensor = torch.from_numpy(rgb.transpose(2, 0, 1)).float() / 255.0
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
    model = _load_model(checkpoint_path, device)

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

    with torch.no_grad():
        while True:
            ret, frame = cap.read()
            if not ret:
                break

            timestamp_sec = frame_idx / fps

            if frame_idx % frame_sample_rate == 0:
                input_tensor = _preprocess_frame(frame).to(device)
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

            writer.write(frame)
            frame_idx += 1

    cap.release()
    writer.release()

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

    detections = _merge_into_windows(raw_detections, gap_tolerance_sec=1.0)

    return {
        "annotated_video_path": output_path,
        "risk_timeline": risk_timeline,
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
