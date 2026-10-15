"""
Large-scale RipVIS dataset expansion script.
Downloads and extracts frames + rasterized binary masks across all available videos
in RipVIS, including positive coastal rip currents and negative control sequences.
"""

import json
import os
import cv2
import numpy as np
from huggingface_hub import hf_hub_download
from tqdm import tqdm

REPO_ID = "Irikos/RipVIS"

def expand_dataset(max_frames_per_video=35):
    print("Loading official COCO annotations from Hugging Face...")
    train_ann_path = hf_hub_download(repo_id=REPO_ID, repo_type="dataset", filename="train/coco_annotations/train.json")
    val_ann_path = hf_hub_download(repo_id=REPO_ID, repo_type="dataset", filename="val/coco_annotations/val.json")

    with open(train_ann_path) as f:
        train_coco = json.load(f)
    with open(val_ann_path) as f:
        val_coco = json.load(f)

    # All train videos
    all_train_vids = sorted(list(set(img["file_name"].split("_")[0] for img in train_coco["images"])))
    all_val_test_vids = sorted(list(set(img["file_name"].split("_")[0] for img in val_coco["images"])))
    
    # Split val and test evenly across the 36 non-training videos
    val_vids = all_val_test_vids[:18]
    test_vids = all_val_test_vids[18:]

    splits = {
        "train": (all_train_vids, train_coco, "train/videos"),
        "val": (val_vids, val_coco, "val/videos"),
        "test": (test_vids, val_coco, "val/videos")
    }

    base_dir = "ml/data/ripvis"

    for split_name, (vids, coco_data, remote_prefix) in splits.items():
        print(f"\n=== Ingesting Split: {split_name} ({len(vids)} videos) ===")
        split_vid_dir = os.path.join(base_dir, split_name, "videos")
        split_mask_dir = os.path.join(base_dir, split_name, "masks")
        os.makedirs(split_vid_dir, exist_ok=True)
        os.makedirs(split_mask_dir, exist_ok=True)

        existing_frames = set(os.listdir(split_vid_dir))
        existing_vids = set(f.split("_")[0] for f in existing_frames)
        print(f"Already have {len(existing_vids)} videos ({len(existing_frames)} frames) in {split_name}.")

        # Index annotations
        ann_by_image = {}
        for ann in coco_data.get("annotations", []):
            ann_by_image.setdefault(ann["image_id"], []).append(ann)

        images_by_video = {}
        for img in coco_data.get("images", []):
            vname = img["file_name"].split("_")[0]
            if vname in vids:
                images_by_video.setdefault(vname, []).append(img)

        # Process videos
        new_extracted = 0
        for vname in vids:
            # Check if video already has extracted frames
            existing_for_this = [f for f in existing_frames if f.startswith(f"{vname}_")]
            if len(existing_for_this) >= 15:
                # Already populated
                continue

            imgs = images_by_video.get(vname, [])
            if not imgs:
                continue

            imgs.sort(key=lambda x: int(x["file_name"].split("_")[1].split(".")[0]))
            if len(imgs) > max_frames_per_video:
                step = len(imgs) / max_frames_per_video
                imgs = [imgs[int(i * step)] for i in range(max_frames_per_video)]

            remote_video_file = f"{remote_prefix}/{vname}.mp4"
            try:
                local_path = hf_hub_download(repo_id=REPO_ID, repo_type="dataset", filename=remote_video_file)
            except Exception as e:
                print(f"Skipping {vname}: {e}")
                continue

            cap = cv2.VideoCapture(local_path)
            if not cap.isOpened():
                continue

            for img_info in imgs:
                frame_fname = img_info["file_name"]
                out_img_path = os.path.join(split_vid_dir, frame_fname)
                out_mask_path = os.path.join(split_mask_dir, frame_fname)

                if os.path.exists(out_img_path) and os.path.exists(out_mask_path):
                    continue

                frame_idx = int(frame_fname.split("_")[1].split(".")[0])
                cap.set(cv2.CAP_PROP_POS_FRAMES, frame_idx)
                ret, frame = cap.read()
                if not ret or frame is None:
                    continue

                anns = ann_by_image.get(img_info["id"], [])
                mask = np.zeros((img_info["height"], img_info["width"]), dtype=np.uint8)
                for ann in anns:
                    for poly in ann.get("segmentation", []):
                        pts = np.array(poly, dtype=np.int32).reshape(-1, 2)
                        cv2.fillPoly(mask, [pts], 255)

                frame_resized = cv2.resize(frame, (512, 512))
                mask_resized = cv2.resize(mask, (512, 512), interpolation=cv2.INTER_NEAREST)

                cv2.imwrite(out_img_path, frame_resized)
                cv2.imwrite(out_mask_path, mask_resized)
                new_extracted += 1

            cap.release()
            print(f"Extracted {len(imgs)} frames from {vname} (Total new: {new_extracted})")

        print(f"Split {split_name} complete: {new_extracted} new frames added.")

if __name__ == "__main__":
    expand_dataset(max_frames_per_video=35)
