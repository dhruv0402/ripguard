# Validation scope

## Reproducible software checks

From the repository root, in a Python 3.12 environment:

```bash
pip install -r backend/requirements.txt -r ml/requirements.txt
PYTHONPATH=backend:. DATABASE_URL="sqlite+aiosqlite:///backend/ripguard.db" python -m pytest backend/tests ml/tests
cd frontend
npm ci
npm test
npm run build
```

These checks exercise API contracts, missing/corrupt model behavior, ML utilities,
and a tiny generated ONNX fixture. They do not download trained weights, establish
segmentation accuracy, or certify a safety deployment. A synthetic model fixture
is a software test input, not a RipVIS benchmark.

The existing `ml/active_learning/retrain_daemon.py` is a simulation: it produces
synthetic metrics and text placeholder checkpoint files, rather than training
and evaluating a network. Its tests exercise that workflow only. They do not
establish real model promotion, accuracy gains, or production readiness. This
limitation is separate from the measured host inference benchmark described below.

## Real inference prerequisites

Supply a trusted, architecture-compatible checkpoint and set
`MODEL_CHECKPOINT_PATH` before running the API. The live service prefers
`ml/checkpoints/ripguard_motion_unet_best.onnx` when present; otherwise it uses
the configured checkpoint. The default configured PyTorch file is
`ml/checkpoints/ripguard_v4_deeplab_best.pt`. Neither file is distributed here.
There is no verified release download or checksum in this repository, so do not
substitute an arbitrary model and describe its scores as the reported results.

Missing/corrupt models must produce degraded status and unknown risk, never a
low-risk observation. The live feed returns HTTP 503 while unavailable. Restart
or poll again after configuring a usable checkpoint.

## Hardware evidence

`python -m ml.inference.edge_optimizer --onnx /path/to/model.onnx` attempts real
TensorRT compilation when the compiler is available and separately measures ONNX
Runtime inference on the current host. It does not benchmark the serialized
TensorRT engine, measure board power, or prove end-to-end camera throughput.
Unavailable/failed operations are reported explicitly. CPU or CUDA results must
not be relabeled as Jetson TensorRT FP16 measurements.

Field claims require recorded device/software versions, model hash, actual
execution configuration, representative video input, warmup/iteration counts,
latency distribution, sustained throughput, and independently measured power.
Safety/field readiness requires validation beyond any throughput result.

## Next model evaluation

Use one frozen, video- and beach-disjoint holdout for all compared checkpoints.
Record the checkpoint SHA-256, data/example IDs, split hash, preprocessing,
thresholds, and software revision alongside each result. Report per-video
segmentation scores, false alarms per video-hour, missed annotated events, and
event detection latency. Quantify uncertainty by resampling independent videos,
not correlated frames. Include negative videos and out-of-distribution beaches.

The historical table in `RESULTS.md` is not a reproduced v4 evaluation. Do not
claim an accuracy improvement until those inputs and results are available.
