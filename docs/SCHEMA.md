# Database Schema — RipGuard

## Entity-Relationship Overview

```
users (1) ───< (many) analysis_sessions (1) ───< (many) detections
                              │
                              └─── (1) risk_summary (embedded/derived, not a separate table)

benchmark_runs  (standalone — records model evaluation runs against RipVIS test set)
```

## Tables

### `users`
| Column | Type | Notes |
|---|---|---|
| id | UUID, PK | |
| email | string, unique | |
| hashed_password | string | bcrypt |
| created_at | timestamp | |

### `analysis_sessions`
One row per uploaded video analysis.

| Column | Type | Notes |
|---|---|---|
| id | UUID, PK | |
| owner_id | UUID, FK -> users.id | |
| filename | string | original upload filename |
| location_label | string, nullable | free-text beach/camera name (v1, no real camera integration) |
| storage_path | string | path to original uploaded video |
| annotated_video_path | string, nullable | path to output video with overlays, set once processing completes |
| status | enum(pending, processing, done, failed) | |
| error_message | text, nullable | |
| overall_risk_level | enum(low, medium, high), nullable | derived once processing completes |
| created_at | timestamp | |

### `detections`
One row per detected high-confidence rip current window within a session (not one row per frame — frame-level data lives in the timeline JSON on the session, this table is for discrete flagged windows worth surfacing individually).

| Column | Type | Notes |
|---|---|---|
| id | UUID, PK | |
| session_id | UUID, FK -> analysis_sessions.id | |
| start_timestamp_sec | float | start of detection window in the video |
| end_timestamp_sec | float | end of detection window |
| confidence | float | model confidence for this window |
| bounding_region | JSON | approximate region descriptor (normalized coords) for quick reference without re-decoding the mask |

### `risk_timeline_points` (or stored as JSON column on `analysis_sessions` — see note)
Per-sampled-frame confidence score across the video, used to draw the timeline strip on the UI.

> **Design note:** for v1, store this as a JSON column (`risk_timeline: JSON`) directly on `analysis_sessions` rather than a separate table — it's always read/written as a whole unit per session, never queried frame-by-frame independently, so a normalized table adds complexity without benefit. Revisit only if per-frame querying becomes a real need.

### `benchmark_runs`
Records of model evaluation runs against the RipVIS test set — this is what powers the "Benchmark / Model Performance" screen, and is the auditable record behind the project's resume/research claims.

| Column | Type | Notes |
|---|---|---|
| id | UUID, PK | |
| model_version | string | e.g. git commit hash or model checkpoint name |
| dataset_split | string | e.g. "ripvis_test" |
| iou | float | |
| dice_f1 | float | |
| precision | float | |
| recall | float | |
| notes | text, nullable | free-text notes on the run (e.g. "added temporal context, +3% IoU") |
| run_at | timestamp | |
