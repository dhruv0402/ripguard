"""
Baseline training loop for RipGuard's segmentation model.

Run:
    python training/train.py --config training/config.yaml

This is a starting point, not a finished, tuned pipeline — the honest next
steps (see ml/README.md) are trying encoder variants, adding temporal
context across frames, and tuning augmentation, then recording each
attempt's effect on the benchmark numbers via evaluate.py.
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
    """
    Focal Tversky Loss specifically designed for small-target segmentation
    with severe class imbalance (rip currents occupy <10% of coastal frames).
    
    alpha: Weight for False Positives (penalizes whitewater false alarms).
    beta: Weight for False Negatives (penalizes missing active rip current channels).
    gamma: Focal exponent (focuses gradient updates on hard, ambiguous surf boundaries).
    """

    def __init__(self, alpha: float = 0.3, beta: float = 0.7, gamma: float = 1.33, smooth: float = 1.0):
        super().__init__()
        self.alpha = alpha
        self.beta = beta
        self.gamma = gamma
        self.smooth = smooth

    def forward(self, pred, target):
        pred_sigmoid = torch.sigmoid(pred)
        
        # Flatten tensors
        p = pred_sigmoid.view(-1)
        t = target.view(-1)

        # True Positives, False Positives, False Negatives
        tp = (p * t).sum()
        fp = ((1 - t) * p).sum()
        fn = (t * (1 - p)).sum()

        tversky = (tp + self.smooth) / (tp + self.alpha * fp + self.beta * fn + self.smooth)
        focal_tversky = torch.pow((1.0 - tversky), self.gamma)
        return focal_tversky


def train(config_path: str):
    with open(config_path) as f:
        cfg = yaml.safe_load(f)

    if torch.cuda.is_available():
        device = torch.device("cuda")
    elif torch.backends.mps.is_available():
        device = torch.device("mps")
    else:
        device = torch.device("cpu")
    print(f"Training on {device}")

    import albumentations as A

    train_transform = A.Compose([
        A.HorizontalFlip(p=0.5),
        A.RandomBrightnessContrast(p=0.3),
        A.ShiftScaleRotate(shift_limit=0.05, scale_limit=0.05, rotate_limit=10, p=0.3, border_mode=cv2.BORDER_CONSTANT),
    ])

    train_ds = RipVISDataset(cfg["data"]["root_dir"], split="train", transform=train_transform)
    val_ds = RipVISDataset(cfg["data"]["root_dir"], split="val")

    train_loader = DataLoader(train_ds, batch_size=cfg["training"]["batch_size"], shuffle=True, num_workers=2)
    val_loader = DataLoader(val_ds, batch_size=cfg["training"]["batch_size"], shuffle=False, num_workers=2)

    model = smp.create_model(
        arch=cfg["model"]["architecture"],
        encoder_name=cfg["model"]["encoder"],
        encoder_weights=cfg["model"]["encoder_weights"],
        in_channels=3,
        classes=1,
    ).to(device)

    criterion = FocalTverskyLoss(alpha=0.3, beta=0.7, gamma=1.33)
    optimizer = torch.optim.AdamW(model.parameters(), lr=cfg["training"]["learning_rate"], weight_decay=1e-4)
    scheduler = torch.optim.lr_scheduler.CosineAnnealingLR(optimizer, T_max=cfg["training"]["epochs"], eta_min=1e-6)

    os.makedirs(cfg["output"]["checkpoint_dir"], exist_ok=True)
    checkpoint_path = os.path.join(cfg["output"]["checkpoint_dir"], cfg["output"]["checkpoint_name"])

    best_val_loss = float("inf")
    patience_counter = 0

    for epoch in range(cfg["training"]["epochs"]):
        model.train()
        train_loss = 0.0
        for images, masks in tqdm(train_loader, desc=f"Epoch {epoch+1} [train]"):
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
            for images, masks in tqdm(val_loader, desc=f"Epoch {epoch+1} [val]"):
                images, masks = images.to(device), masks.to(device)
                preds = model(images)
                val_loss += criterion(preds, masks).item()

        avg_train_loss = train_loss / max(len(train_loader), 1)
        avg_val_loss = val_loss / max(len(val_loader), 1)
        scheduler.step()
        print(f"Epoch {epoch+1}: train_loss={avg_train_loss:.4f} val_loss={avg_val_loss:.4f} lr={scheduler.get_last_lr()[0]:.6f}")

        if avg_val_loss < best_val_loss:
            best_val_loss = avg_val_loss
            patience_counter = 0
            torch.save(model.state_dict(), checkpoint_path)
            print(f"  -> saved new best checkpoint to {checkpoint_path}")
        else:
            patience_counter += 1
            if patience_counter >= cfg["training"]["early_stopping_patience"]:
                print("Early stopping triggered.")
                break


if __name__ == "__main__":
    parser = argparse.ArgumentParser()
    parser.add_argument("--config", type=str, required=True)
    args = parser.parse_args()
    train(args.config)
