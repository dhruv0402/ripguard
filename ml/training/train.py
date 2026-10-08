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
import yaml
import torch
import torch.nn as nn
from torch.utils.data import DataLoader
import segmentation_models_pytorch as smp
from tqdm import tqdm

from dataset import RipVISDataset


class DiceBCELoss(nn.Module):
    """Standard combined loss for segmentation with class imbalance —
    rip current regions are typically a small fraction of each frame,
    so BCE alone tends to collapse toward predicting "nothing" everywhere."""

    def __init__(self, bce_weight: float = 0.5):
        super().__init__()
        self.bce = nn.BCEWithLogitsLoss()
        self.bce_weight = bce_weight

    def forward(self, pred, target):
        bce_loss = self.bce(pred, target)

        pred_sigmoid = torch.sigmoid(pred)
        smooth = 1.0
        intersection = (pred_sigmoid * target).sum()
        dice_loss = 1 - (2.0 * intersection + smooth) / (pred_sigmoid.sum() + target.sum() + smooth)

        return self.bce_weight * bce_loss + (1 - self.bce_weight) * dice_loss


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

    train_ds = RipVISDataset(cfg["data"]["root_dir"], split="train")
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

    criterion = DiceBCELoss()
    optimizer = torch.optim.AdamW(model.parameters(), lr=cfg["training"]["learning_rate"])

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
        print(f"Epoch {epoch+1}: train_loss={avg_train_loss:.4f} val_loss={avg_val_loss:.4f}")

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
