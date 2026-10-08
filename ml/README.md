# RipGuard ML Pipeline

## 1. Dataset — RipVIS

Download the RipVIS dataset (CVPR 2025) — videos + frame-level segmentation masks for rip current regions. Check the current release location/instructions via the paper's project page or the NTIRE 2026 challenge page (the exact download URL/host may change — search "RipVIS dataset" if the link below is stale).

Expected structure after download, place under `ml/data/ripvis/`:

```
ml/data/ripvis/
├── train/
│   ├── videos/
│   └── masks/
├── val/
│   ├── videos/
│   └── masks/
└── test/
    ├── videos/
    └── masks/
```

If the dataset ships as raw videos + a separate annotation format (not pre-split into per-frame mask images), the first real task is writing a `prepare_dataset.py` script that extracts frames and rasterizes the annotations into mask images matching the structure above. **This is expected, real work — not a placeholder to skip.**

## 2. Training

```bash
cd ml
pip install -r requirements.txt
python training/train.py --config training/config.yaml
```

Produces a checkpoint at `ml/checkpoints/ripguard_unet_best.pt` (path configurable).

## 3. Evaluation

```bash
python training/evaluate.py --checkpoint checkpoints/ripguard_unet_best.pt --split test
```

Writes a result row to the `benchmark_runs` table (via a small script that talks to the backend DB — see `training/log_benchmark_run.py`) so results are tracked over time, not just printed and forgotten.

## 4. Inference (used by the backend)

`inference/predict.py` exposes `run_inference_on_video(video_path, checkpoint_path, output_dir, frame_sample_rate)`, called by the backend's `analysis_service.py` as a background task. This module has no FastAPI/SQLAlchemy dependency — it should be runnable and testable completely standalone:

```bash
python inference/predict.py --video path/to/test_video.mp4 --checkpoint checkpoints/ripguard_unet_best.pt
```

## Honest expectations

This is a genuinely unsolved problem — current state-of-the-art approaches don't get near-perfect scores on this task. Don't treat a modest IoU/F1 as a failure of implementation; treat it as the honest, reportable result of working on an open research problem, and document what you tried (architecture choices, temporal context, augmentation) and what moved the number, even a little.
