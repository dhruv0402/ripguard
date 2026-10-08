# PRD — RipGuard: Rip Current Detection & Beach Safety Alert System

## 1. Problem Statement

Rip currents are one of the leading causes of drowning deaths at beaches worldwide. They're visually subtle — a trained lifeguard can miss one, and an untrained beachgoer almost certainly will. Detection today relies on human observation (lifeguards scanning water visually) or occasional physical surveys; there is no widely deployed automated visual detection system in use at most beaches, including in India (Goa, Kerala, Tamil Nadu coastlines all have documented rip current drowning incidents).

This is not a solved problem in computer vision. Rip current detection/segmentation is an active, unsolved research area — it's the subject of a live NTIRE 2026 CVPR workshop challenge, meaning current state-of-the-art models still perform imperfectly on it. RipGuard aims to build a working, honest, decision-support system against this open problem, clearly scoped as a research/prototype tool rather than a certified safety-of-life system.

## 2. Goals

- Build a system that ingests beach video (uploaded footage, or a live camera feed) and flags regions likely to contain a rip current.
- Give lifeguards / coastal safety staff a dashboard showing current risk level and flagged regions in near-real time.
- Log historical detections for a given camera/beach location so patterns (e.g. time of day, tide correlation) can be reviewed later.
- Be transparent about model confidence and limitations at every point in the UI — this is a decision-support aid, not an infallible alarm.

## 3. Non-Goals (v1)

- This is NOT a certified, liability-bearing safety system. It will not be marketed or positioned as a replacement for trained lifeguards.
- No real beach camera hardware deployment in v1 — the system is built and evaluated against the public RipVIS dataset and uploaded video files.
- No mobile app for beachgoers in v1 (future scope).
- No multi-camera sensor fusion in v1 (single video stream per analysis session).

## 4. Target Users

| Persona | Need |
|---|---|
| **Lifeguard / beach safety operator** | Wants a secondary pair of eyes on the water — an alert when the system flags a likely rip current, with enough visual context to verify it themselves. |
| **Coastal safety authority / municipal body** | Wants historical logs and analytics per beach/camera to understand risk patterns and justify safety resource allocation. |
| **Researcher / student (you)** | Wants a working benchmark pipeline evaluated against RipVIS, with clear, honest reporting of model accuracy — this is the resume/research-value audience. |

## 5. Core Features (v1 / MVP)

1. **Video upload & analysis** — upload a beach video; system runs the segmentation model frame-by-frame and returns an annotated output video + a frame-level risk timeline.
2. **Rip current segmentation overlay** — visual highlight (mask) on frames where the model detects a likely rip current region, with a confidence score.
3. **Risk dashboard** — per-session summary: overall risk level, timestamped list of high-confidence detections, confidence trend over the video.
4. **Detection history log** — all past analysis sessions stored and browsable, filterable by date/camera/risk level.
5. **Benchmark/eval view** — a dedicated page showing the model's measured performance (IoU, F1, precision/recall) against the RipVIS test set, displayed honestly as "current model performance," not hidden.
6. **Clear confidence/limitation messaging** — every detection view carries a visible reminder that this is a decision-support tool, not a certified alert system.

## 6. Future Scope (explicitly out of v1)

- Live camera feed ingestion (RTSP/webcam streaming) instead of only uploaded video
- SMS/push alerting to lifeguard staff
- Public-facing simplified "beach status" view
- Multi-beach/multi-camera fleet management
- Mobile app

## 7. Success Metrics

- **Model quality:** Segmentation IoU and F1 on the RipVIS held-out test set, reported transparently (even if not state-of-the-art — the honest number is the deliverable).
- **System functionality:** end-to-end flow works — upload video → get annotated output + risk dashboard — without manual intervention.
- **Resume/portfolio metric:** a working demo, a documented benchmark against a named public dataset/challenge, and a clear writeup of what was tried and what the actual limitations are.

## 8. Risks & Honest Constraints

- **This is a genuinely unsolved CV problem.** Expect imperfect accuracy. The deliverable is a transparent, well-evaluated attempt — not a claim of solving rip current detection.
- **False negatives carry real safety weight conceptually**, even though this is a prototype — the UI/copy must never imply more certainty than the model actually has.
- **No real deployment/field testing** is in scope for this version — all evaluation is against the RipVIS dataset and uploaded test videos, not live beach conditions.
