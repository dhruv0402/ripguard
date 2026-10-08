"""
Evaluates a trained checkpoint against a RipVIS split and prints
IoU / Dice-F1 / precision / recall — the numbers that go into
benchmark_runs via log_benchmark_run.py.

Run:
    python training/evaluate.py --checkpoint checkpoints/ripguard_unet_best.pt --split test
"""

import argparse
import torch
from torch.utils.data import DataLoader
import segmentation_models_pytorch as smp
from sklearn.metrics import precision_score, recall_score, f1_score

from dataset import RipVISDataset


def compute_iou(pred_mask, true_mask, threshold=0.5, eps=1e-7):
    pred_binary = (pred_mask > threshold).float()
    intersection = (pred_binary * true_mask).sum()
    union = pred_binary.sum() + true_mask.sum() - intersection
    return (intersection + eps) / (union + eps)


def evaluate(checkpoint_path: str, split: str, root_dir: str = "ml/data/ripvis"):
    if torch.cuda.is_available():
        device = torch.device("cuda")
    elif torch.backends.mps.is_available():
        device = torch.device("mps")
    else:
        device = torch.device("cpu")

    dataset = RipVISDataset(root_dir, split=split)
    loader = DataLoader(dataset, batch_size=8, shuffle=False, num_workers=2)

    model = smp.create_model(arch="Unet", encoder_name="resnet34", encoder_weights=None, in_channels=3, classes=1)
    model.load_state_dict(torch.load(checkpoint_path, map_location=device))
    model.to(device).eval()

    ious, all_preds, all_targets = [], [], []

    with torch.no_grad():
        for images, masks in loader:
            images, masks = images.to(device), masks.to(device)
            preds = torch.sigmoid(model(images))

            for p, m in zip(preds, masks):
                ious.append(compute_iou(p, m).item())

            all_preds.extend((preds > 0.5).cpu().numpy().flatten().tolist())
            all_targets.extend(masks.cpu().numpy().flatten().tolist())

    mean_iou = sum(ious) / len(ious) if ious else 0.0
    precision = precision_score(all_targets, all_preds, zero_division=0)
    recall = recall_score(all_targets, all_preds, zero_division=0)
    f1 = f1_score(all_targets, all_preds, zero_division=0)

    print(f"\n--- Results on '{split}' split ---")
    print(f"Mean IoU:   {mean_iou:.4f}")
    print(f"Precision:  {precision:.4f}")
    print(f"Recall:     {recall:.4f}")
    print(f"Dice/F1:    {f1:.4f}")

    return {"iou": mean_iou, "precision": precision, "recall": recall, "dice_f1": f1}


if __name__ == "__main__":
    parser = argparse.ArgumentParser()
    parser.add_argument("--checkpoint", type=str, required=True)
    parser.add_argument("--split", type=str, default="test")
    args = parser.parse_args()
    evaluate(args.checkpoint, args.split)
