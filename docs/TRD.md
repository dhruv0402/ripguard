# TRD — RipGuard: Technical Requirements Document

## 1. System Architecture Overview

```
┌─────────────┐      ┌──────────────────┐      ┌─────────────────────┐
│  Frontend    │ <--> │   FastAPI Backend │ <--> │   PostgreSQL         │
│  (React/     │ REST │   (async)         │ ORM  │   (sessions, alerts, │
│   Next.js)   │      │                   │      │    benchmark runs)   │
└─────────────┘      └─────────┬─────────┘      └─────────────────────┘
                                │
                                │ background task
                                ▼
                     ┌─────────────────────┐
                     │   ML Inference        │
                     │   Service              │
                     │   (segmentation model) │
                     └─────────────────────┘
                                │
                                ▼
                     ┌─────────────────────┐
                     │  Video storage         │
                     │  (local disk / S3)     │
                     └─────────────────────┘
```

Same architectural pattern as a standard upload → background-process → poll-for-result flow: the backend accepts a video upload, returns immediately with a `pending` status, and processes the video asynchronously so the HTTP request isn't blocked for the (potentially multi-minute) duration of video inference.

## 2. Tech Stack

| Layer | Choice | Why |
|---|---|---|
| Backend API | FastAPI (async) | Async request handling, auto-generated OpenAPI docs, Pydantic validation |
| Database | PostgreSQL + SQLAlchemy (async, asyncpg) | Relational data (sessions, detections, alerts) with clear foreign-key relationships |
| Auth | JWT (python-jose) + passlib/bcrypt | Standard stateless auth for a small team/operator tool |
| ML framework | PyTorch | Standard for segmentation model training/inference |
| Segmentation architecture | U-Net or DeepLabV3+ (via `segmentation-models-pytorch`) fine-tuned on RipVIS | Well-understood, well-documented segmentation architectures; appropriate starting point for a problem this hard rather than inventing a novel architecture from scratch |
| Video I/O | OpenCV | Frame extraction, annotation overlay, video re-encoding |
| Frontend | React (or Next.js) | Dashboard, video upload, detection timeline visualization |
| Containerization | Docker + docker-compose | backend, db, frontend as services |
| Dataset | RipVIS (CVPR 2025) | Public dataset built specifically for rip current video segmentation — 184 videos, ~212,000 frames |

## 3. ML Pipeline Design

### 3.1 Data
- Source: RipVIS public dataset (videos + frame-level segmentation masks for rip current regions).
- Split: use the dataset's provided train/val/test split if available; otherwise an 70/15/15 split, stratified by video (not by frame, to avoid leakage between train/test on frames from the same video).
- Augmentation: horizontal flip, brightness/contrast jitter (water/lighting conditions vary a lot), random crop — avoid augmentations that would distort water-texture cues the model needs (e.g. no heavy blur).

### 3.2 Model
- Baseline: U-Net or DeepLabV3+ with a pretrained encoder (e.g. ResNet34/ResNet50 ImageNet weights) via `segmentation-models-pytorch`.
- Output: per-frame binary segmentation mask (rip current region vs. not).
- Loss: combination of Dice loss + BCE (standard for segmentation with class imbalance — rip current regions are a small fraction of most frames).
- Optional v2 improvement: incorporate temporal context (e.g. feeding a short frame window instead of single frames) since rip currents are partly characterized by motion patterns over time, not just static texture — this is a legitimate place to try to improve on naive single-frame baselines.

### 3.3 Evaluation
- Metrics: IoU, Dice/F1, precision, recall — computed per-frame and aggregated per-video.
- Report honestly against the RipVIS benchmark/leaderboard context if available, so the result is comparable to other attempts at this problem.

### 3.4 Inference service
- Takes a video file, runs the model frame-by-frame (or on sampled frames at a reasonable FPS to keep inference time reasonable), produces:
  - An annotated output video with mask overlays
  - A frame-level confidence/risk timeline (JSON) for the dashboard

## 4. API Design (high level)

```
POST   /api/auth/signup
POST   /api/auth/login

POST   /api/sessions              # upload a video, returns session id, status=pending
GET    /api/sessions/{id}         # poll status; once done, returns risk summary + detection timeline
GET    /api/sessions              # list past analysis sessions
GET    /api/sessions/{id}/video   # fetch the annotated output video

GET    /api/benchmark             # model's measured performance against RipVIS test set
```

## 5. Non-Functional Requirements

- **Latency:** inference doesn't need to be real-time for v1 (video upload + async processing is fine); target reasonable turnaround (a few minutes for a short clip) rather than live-stream speed.
- **Transparency:** every API response carrying a detection must include the model's confidence score — never present a binary yes/no without it.
- **Reproducibility:** training pipeline and evaluation script must be runnable end-to-end from the repo, so the benchmark numbers are independently verifiable.

## 6. Deployment (scope for this project)

- Local development via `docker-compose up` (backend + db + frontend).
- Model weights stored separately from the repo (too large for git) — documented download/training instructions instead.
- No production cloud deployment required for the resume-project scope, but the structure should not block it later (standard Dockerized services deploy to Render/Railway/Fly.io without major rework).
