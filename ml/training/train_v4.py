"""
RipGuard v4 Training Script.
Architecture: DeepLabV3+ with ResNet-50 / ResNet-34 encoder.
Loss: Focal Tversky Loss (alpha=0.3, beta=0.7, gamma=1.33)
Data: Ingests all expanded positive and negative control beach frames.
"""

import argparse
import os
import cv2
import yaml
import torch
import torch.nn as nn
from torch.utils.data import DataLoader
import segmentation_models_pytorch as smp
from tqdm import tqdm

from dataset import RipVISDataset


class FocalTverskyLoss(nn.Module):
    def __init__(self, alpha: float = 0.3, beta: float = 0.7, gamma: float = 1.33, smooth: float = 1.0):
        super().__init__()
        self.alpha = alpha
        self.beta = beta
        self.gamma = gamma
        self.smooth = smooth

    def forward(self, pred, target):
        p = torch.sigmoid(pred).view(-1)
        t = target.view(-1)

        tp = (p * t).sum()
        fp = ((1 - t) * p).sum()
        fn = (t * (1 - p)).sum()

        tversky = (tp + self.smooth) / (tp + self.alpha * fp + self.beta * fn + self.smooth)
        return torch.pow((1.0 - tversky), self.gamma)


def train_v4(epochs=20, batch_size=8, lr=1e-4, arch="DeepLabV3Plus", encoder="resnet34"):
    device = torch.device("mps" if torch.backends.mps.is_available() else "cpu")
    print(f"--- Launching RipGuard v4 [{arch} + {encoder}] on {device} ---")

    import albumentations as A
    train_transform = A.Compose([
        A.HorizontalFlip(p=0.5),
        A.RandomBrightnessContrast(p=0.4),
        A.ShiftScaleRotate(shift_limit=0.08, scale_limit=0.08, rotate_limit=15, p=0.4, border_mode=cv2.BORDER_CONSTANT),
        A.GaussianBlur(blur_limit=(3, 5), p=0.2),
    ])

    root_dir = "ml/data/ripvis"
    train_ds = RipVISDataset(root_dir, split="train", transform=train_transform)
    val_ds = RipVISDataset(root_dir, split="val")

    print(f"Loaded {len(train_ds)} training pairs, {len(val_ds)} validation pairs.")

    train_loader = DataLoader(train_ds, batch_size=batch_size, shuffle=True, num_workers=2)
    val_loader = DataLoader(val_ds, batch_size=batch_size, shuffle=False, num_workers=2)

    try:
        model = smp.create_model(
            arch=arch,
            encoder_name=encoder,
            encoder_weights="imagenet",
            in_channels=3,
            classes=1
        ).to(device)
    except Exception as e:
        print(f"Fallback to Unet resnet34 due to: {e}")
        model = smp.create_model(
            arch="Unet",
            encoder_name="resnet34",
            encoder_weights="imagenet",
            in_channels=3,
            classes=1
        ).to(device)

    criterion = FocalTverskyLoss(alpha=0.3, beta=0.7, gamma=1.33)
    optimizer = torch.optim.AdamW(model.parameters(), lr=lr, weight_decay=1e-4)
    scheduler = torch.optim.lr_scheduler.CosineAnnealingLR(optimizer, T_max=epochs, eta_min=1e-6)

    os.makedirs("ml/checkpoints", exist_ok=True)
    out_checkpoint = "ml/checkpoints/ripguard_v4_deeplab_best.pt"

    best_val_loss = float("inf")
    patience = 7
    patience_counter = 0

    for epoch in range(epochs):
        model.train()
        train_loss = 0.0
        for images, masks in train_loader:
            images, masks = images.to(device), masks.to(device)
            optimizer.zero_grad()
            preds = model(images)
            loss = criterion(preds, masks)
            loss.backward()
            optimizer.step()
            train_loss += loss.item()

        model.eval()
        val_loss = 0.0
        with torch.no_grad():
            for images, masks in val_loader:
                images, masks = images.to(device), masks.to(device)
                preds = model(images)
                val_loss += criterion(preds, masks).item()

        avg_train = train_loss / max(len(train_loader), 1)
        avg_val = val_loss / max(len(val_loader), 1)
        scheduler.step()

        print(f"Epoch [{epoch+1}/{epochs}] | Train Loss: {avg_train:.4f} | Val Loss: {avg_val:.4f} | LR: {scheduler.get_last_lr()[0]:.6f}")

        if avg_val < best_val_loss:
            best_val_loss = avg_val
            patience_counter = 0
            torch.save(model.state_dict(), out_checkpoint)
            print(f"  -> Saved top checkpoint to {out_checkpoint} (Val Loss: {best_val_loss:.4f})")
        else:
            patience_counter += 1
            if patience_counter >= patience:
                print(f"Early stopping at epoch {epoch+1}")
                break

    print(f"v4 training completed. Best checkpoint saved to {out_checkpoint}")


if __name__ == "__main__":
    train_v4()
