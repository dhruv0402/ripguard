"""
RipVIS Dataset Downloader and Preparer.

This script:
1. Downloads annotations from Hugging Face (`Irikos/RipVIS` - CVPR 2025).
2. Downloads selected real videos for train, val, and test splits (following the official split partition).
3. Extracts frames corresponding to annotated timestamps.
4. Rasterizes the polygon annotations into binary segmentation masks matching the structure:
   ml/data/ripvis/{train, val, test}/{videos, masks}/
"""

import argparse
import json
import os
import sys
import cv2
import numpy as np
from huggingface_hub import hf_hub_download
from tqdm import tqdm

REPO_ID = "Irikos/RipVIS"

# Selected subset of videos to keep download and training fast while preserving real diversity
# Videos are selected strictly from their respective official splits.
DEFAULT_SPLIT_VIDEOS = {
    "train": [
        "RipVIS-123", "RipVIS-124", "RipVIS-065", "RipVIS-003", "RipVIS-075",
        "RipVIS-NR-012", "RipVIS-070", "RipVIS-011", "RipVIS-054", "RipVIS-082",
        "RipVIS-068", "RipVIS-122", "RipVIS-010", "RipVIS-092", "RipVIS-052",
        "RipVIS-049", "RipVIS-051", "RipVIS-050", "RipVIS-061", "RipVIS-071",
        "RipVIS-080", "RipVIS-116", "RipVIS-064", "RipVIS-094", "RipVIS-NR-003",
        "RipVIS-084", "RipVIS-NR-011", "RipVIS-NR-010"
    ],
    "val": [
        "RipVIS-072", "RipVIS-121", "RipVIS-067", "RipVIS-007", "RipVIS-059",
        "RipVIS-012", "RipVIS-137", "RipVIS-NR-019"
    ],
    "test": [
        "RipVIS-014", "RipVIS-053", "RipVIS-024", "RipVIS-NR-004", "RipVIS-015",
        "RipVIS-066"
    ]
}


def prepare_split(split_name: str, target_dir: str, video_names: list[str], max_frames_per_video: int = 40):
    print(f"\n================ Preparing Split: {split_name} ================")
    
    # Destination directories
    split_vid_dir = os.path.join(target_dir, split_name, "videos")
    split_mask_dir = os.path.join(target_dir, split_name, "masks")
    os.makedirs(split_vid_dir, exist_ok=True)
    os.makedirs(split_mask_dir, exist_ok=True)

    # Determine which annotation file to use
    if split_name == "train":
        ann_file = "train/coco_annotations/train.json"
        video_prefix = "train/videos"
    elif split_name in ("val", "test"):
        ann_file = "val/coco_annotations/val.json"
        video_prefix = "val/videos"
    else:
        raise ValueError(f"Unknown split: {split_name}")

    print(f"Downloading/loading annotations from {ann_file}...")
    local_ann_path = hf_hub_download(repo_id=REPO_ID, repo_type="dataset", filename=ann_file)
    with open(local_ann_path, "r") as f:
        coco_data = json.load(f)

    # Index annotations by image_id
    ann_by_image = {}
    for ann in coco_data.get("annotations", []):
        ann_by_image.setdefault(ann["image_id"], []).append(ann)

    # Index images by video name
    images_by_video = {}
    for img in coco_data.get("images", []):
        fname = img["file_name"]
        vname = fname.split("_")[0]
        if vname in video_names:
            images_by_video.setdefault(vname, []).append(img)

    total_extracted = 0

    for vname in video_names:
        imgs = images_by_video.get(vname, [])
        if not imgs:
            print(f"Warning: No annotations found for video {vname} in {ann_file}")
            continue

        # Sort images by frame index
        imgs.sort(key=lambda x: int(x["file_name"].split("_")[1].split(".")[0]))
        if len(imgs) > max_frames_per_video:
            # Subsample evenly to keep balance across videos
            step = len(imgs) / max_frames_per_video
            imgs = [imgs[int(i * step)] for i in range(max_frames_per_video)]

        print(f"Processing video {vname}: downloading video file and extracting {len(imgs)} frames...")
        remote_video_file = f"{video_prefix}/{vname}.mp4"
        try:
            local_video_path = hf_hub_download(repo_id=REPO_ID, repo_type="dataset", filename=remote_video_file)
        except Exception as e:
            print(f"Failed to download video {remote_video_file}: {e}")
            continue

        cap = cv2.VideoCapture(local_video_path)
        if not cap.isOpened():
            print(f"Failed to open video {local_video_path}")
            continue

        for img_info in tqdm(imgs, desc=f"Extracting {vname}"):
            frame_fname = img_info["file_name"]
            frame_idx = int(frame_fname.split("_")[1].split(".")[0])
            img_w = img_info["width"]
            img_h = img_info["height"]

            out_img_path = os.path.join(split_vid_dir, frame_fname)
            out_mask_path = os.path.join(split_mask_dir, frame_fname)

            # Seek and read frame
            cap.set(cv2.CAP_PROP_POS_FRAMES, frame_idx)
            ret, frame = cap.read()
            if not ret or frame is None:
                continue

            # Rasterize mask from polygons
            anns = ann_by_image.get(img_info["id"], [])
            mask = np.zeros((img_h, img_w), dtype=np.uint8)
            for ann in anns:
                for poly in ann.get("segmentation", []):
                    pts = np.array(poly, dtype=np.int32).reshape(-1, 2)
                    cv2.fillPoly(mask, [pts], 255)

            # Resize to 512x512 for consistent training & storage efficiency
            frame_resized = cv2.resize(frame, (512, 512))
            mask_resized = cv2.resize(mask, (512, 512), interpolation=cv2.INTER_NEAREST)

            cv2.imwrite(out_img_path, frame_resized)
            cv2.imwrite(out_mask_path, mask_resized)
            total_extracted += 1

        cap.release()

    print(f"Done split {split_name}: {total_extracted} frames saved to {split_vid_dir} and {split_mask_dir}")


def main():
    parser = argparse.ArgumentParser(description="Prepare RipVIS dataset from Hugging Face")
    parser.add_argument("--target_dir", type=str, default="ml/data/ripvis", help="Target dataset root directory")
    parser.add_argument("--max_frames", type=int, default=30, help="Max frames per video to extract")
    args = parser.parse_args()

    for split in ["train", "val", "test"]:
        prepare_split(
            split_name=split,
            target_dir=args.target_dir,
            video_names=DEFAULT_SPLIT_VIDEOS[split],
            max_frames_per_video=args.max_frames,
        )


if __name__ == "__main__":
    main()
