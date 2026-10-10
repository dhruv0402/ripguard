"""
PyTorch Dataset for RipVIS. Expects frames + mask images already extracted
(see ml/README.md — if RipVIS ships as raw video + annotations rather than
pre-extracted frame/mask pairs, write a prepare_dataset.py that does that
extraction first; this class assumes it's already done).
"""

import os
import cv2
import numpy as np
import torch
from torch.utils.data import Dataset


class RipVISDataset(Dataset):
    def __init__(self, root_dir: str, split: str, transform=None):
        """
        root_dir: path to ml/data/ripvis
        split: "train" | "val" | "test"
        """
        self.video_dir = os.path.join(root_dir, split, "videos")
        self.mask_dir = os.path.join(root_dir, split, "masks")
        self.transform = transform

        if not os.path.isdir(self.video_dir):
            raise FileNotFoundError(
                f"Expected frame images under {self.video_dir} — see ml/README.md for the "
                f"expected dataset layout. If RipVIS ships as raw video, extract frames first."
            )

        self.filenames = sorted(
            f for f in os.listdir(self.video_dir) if f.lower().endswith((".jpg", ".png"))
        )

    def __len__(self):
        return len(self.filenames)

    def __getitem__(self, idx):
        fname = self.filenames[idx]
        image_path = os.path.join(self.video_dir, fname)
        mask_path = os.path.join(self.mask_dir, fname)

        image = cv2.cvtColor(cv2.imread(image_path), cv2.COLOR_BGR2RGB)
        mask = cv2.imread(mask_path, cv2.IMREAD_GRAYSCALE)
        if mask is None:
            raise FileNotFoundError(f"No matching mask found for {fname} at {mask_path}")

        mask = (mask > 127).astype(np.float32)  # binarize: rip current region vs not

        if self.transform:
            augmented = self.transform(image=image, mask=mask)
            image, mask = augmented["image"], augmented["mask"]

        image = torch.from_numpy(image.transpose(2, 0, 1)).float() / 255.0
        mask = torch.from_numpy(mask).float()

        return image, mask.unsqueeze(0) if mask.dim() == 2 else mask
