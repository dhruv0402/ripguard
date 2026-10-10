"""
RipVIS Optical Flow Dataset Loader & Motion-Aware Tensor Builder.

Extracts dense optical flow (Farnebäck motion vectors) between adjacent
coastal video frames to construct a 5-channel spatio-temporal tensor:
[R, G, B, vx, vy].

Why:
Rip currents are defined by water velocity over time (seaward discharge through
breaking waves). Static 2D CNNs cannot infer velocity and easily confuse wave
foam/whitewater with rip currents. Adding optical flow gives the network explicit
directional motion cues.
"""

import os
import cv2
import numpy as np
import torch
from torch.utils.data import Dataset


def compute_farneback_flow(prev_gray: np.ndarray, curr_gray: np.ndarray) -> np.ndarray:
    """Computes dense optical flow (Farnebäck) between two grayscale frames.
    Returns:
        flow: (H, W, 2) array with (dx, dy) velocities in pixels.
    """
    flow = cv2.calcOpticalFlowFarneback(
        prev_gray,
        curr_gray,
        None,
        pyr_scale=0.5,
        levels=3,
        winsize=15,
        iterations=3,
        poly_n=5,
        poly_sigma=1.2,
        flags=0,
    )
    # Clip extreme noise artifacts (e.g. spray/camera shake) and scale to [-1, 1] range
    flow = np.clip(flow, -20.0, 20.0) / 20.0
    return flow.astype(np.float32)


class RipVISMotionDataset(Dataset):
    """
    Loads coastal frames, groups frames by video, computes dense optical flow
    with the preceding frame in the sequence, and outputs a 5-channel tensor
    (RGB + vx + vy) paired with the ground truth segmentation mask.
    """

    def __init__(self, root_dir: str, split: str, transform=None):
        self.video_dir = os.path.join(root_dir, split, "videos")
        self.mask_dir = os.path.join(root_dir, split, "masks")
        self.transform = transform

        if not os.path.isdir(self.video_dir):
            raise FileNotFoundError(f"Missing videos dir: {self.video_dir}")

        all_files = sorted(f for f in os.listdir(self.video_dir) if f.lower().endswith((".jpg", ".png")))

        # Group filenames by video prefix
        self.video_groups = {}
        for f in all_files:
            vname = f.split("_")[0]
            self.video_groups.setdefault(vname, []).append(f)

        for vname in self.video_groups:
            self.video_groups[vname].sort(key=lambda x: int(x.split("_")[1].split(".")[0]))

        # Flatten list with predecessor reference
        self.samples = []
        for vname, fnames in self.video_groups.items():
            for idx, curr_f in enumerate(fnames):
                prev_f = fnames[idx - 1] if idx > 0 else curr_f
                self.samples.append((curr_f, prev_f))

    def __len__(self):
        return len(self.samples)

    def __getitem__(self, idx):
        curr_fname, prev_fname = self.samples[idx]

        curr_img_path = os.path.join(self.video_dir, curr_fname)
        prev_img_path = os.path.join(self.video_dir, prev_fname)
        mask_path = os.path.join(self.mask_dir, curr_fname)

        curr_bgr = cv2.imread(curr_img_path)
        prev_bgr = cv2.imread(prev_img_path)
        mask = cv2.imread(mask_path, cv2.IMREAD_GRAYSCALE)

        if mask is None:
            raise FileNotFoundError(f"Missing mask for {curr_fname}")

        curr_rgb = cv2.cvtColor(curr_bgr, cv2.COLOR_BGR2RGB)
        curr_gray = cv2.cvtColor(curr_bgr, cv2.COLOR_BGR2GRAY)
        prev_gray = cv2.cvtColor(prev_bgr, cv2.COLOR_BGR2GRAY)

        # Compute optical flow (dx, dy)
        flow = compute_farneback_flow(prev_gray, curr_gray)  # (H, W, 2)

        mask = (mask > 127).astype(np.float32)

        # Stack into 5-channel array: R, G, B, flow_x, flow_y
        rgb_norm = curr_rgb.astype(np.float32) / 255.0
        combined = np.concatenate([rgb_norm, flow], axis=-1)  # (H, W, 5)

        if self.transform:
            augmented = self.transform(image=combined, mask=mask)
            combined = augmented["image"]
            mask = augmented["mask"]

        # Convert to PyTorch tensors (C, H, W)
        tensor = torch.from_numpy(combined.transpose(2, 0, 1)).float()
        mask_tensor = torch.from_numpy(mask).float()

        return tensor, mask_tensor.unsqueeze(0) if mask_tensor.dim() == 2 else mask_tensor
