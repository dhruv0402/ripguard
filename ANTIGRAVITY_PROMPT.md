# Antigravity Agent Brief — RipGuard

Copy everything below this line into Antigravity as your task brief.

---

## Who you are working for and why this project exists

You're continuing work on **RipGuard**, a rip current detection and beach-safety decision-support system. This is a student's resume/portfolio project, built by a final-year CS (AI) undergraduate targeting AI engineering roles. The project's entire point is **honest, demonstrable technical depth** — not a flashy demo that hides weak results. Keep this in mind in every decision you make: favor working, tested, honestly-reported code over impressive-looking but unverified code.

## The problem this project tackles

Rip currents are a leading cause of drowning deaths at beaches worldwide, including on Indian coastlines (Goa, Kerala, Tamil Nadu). Detecting them from video is a **genuinely unsolved computer vision problem** — it's the subject of a live NTIRE 2026 CVPR workshop challenge, meaning current state-of-the-art models still perform imperfectly on it. This project is not claiming to solve rip current detection. It is building a working, transparently-evaluated attempt against the public **RipVIS** dataset (CVPR 2025, ~184 videos / ~212,000 frames with rip current segmentation masks), with an honest benchmark-tracking system so model performance over iterations is auditable, not just asserted.

**Do not inflate claims anywhere in code comments, docstrings, UI copy, or commit messages.** If the model's IoU is 0.45, that's what gets reported — framed as "here's where this open problem currently stands with this approach," not hidden or rounded up.

## What already exists in this repo (read before writing anything)

Read these four docs first, in order — they are the actual specification, not background color:
1. `docs/PRD.md` — product scope, target users, what's in v1 vs out of scope, success metrics
2. `docs/TRD.md` — architecture, tech stack decisions and why, ML pipeline design
3. `docs/APP_FLOW.md` — user journey, screens, a Mermaid sequence diagram of the upload → analyze → view flow
4. `docs/SCHEMA.md` — database schema / ERD, including a design note explaining why `risk_timeline` is a JSON column rather than a normalized table (read this reasoning — it's a deliberate tradeoff, not an oversight)

Then inspect the actual code:
- `backend/app/` — a working, tested FastAPI backend (auth with JWT, async SQLAlchemy models matching `docs/SCHEMA.md` exactly, video upload endpoint using `BackgroundTasks` for async processing, session polling endpoint, a public benchmark-results endpoint). **Tests exist in `backend/tests/` and currently pass** — run `pytest` before and after any change you make to confirm you haven't broken anything.
- `ml/` — a training/evaluation/inference pipeline skeleton for a U-Net-based segmentation model (via `segmentation-models-pytorch`), built against the expected RipVIS directory structure. **This has NOT been trained yet** — no dataset has been downloaded, no model checkpoint exists. The inference module (`ml/inference/predict.py`) is written and its core helper logic (window-merging, mask-to-region conversion) is unit-tested and passing, but it has never been run against a real trained checkpoint.
- `frontend/` — only empty folder scaffolding exists (`src/components`, `src/pages`). No frontend code has been written yet.

## Your task, in priority order

### Priority 1 — Get the ML pipeline actually working end to end
1. Find and download the RipVIS dataset (search for "RipVIS dataset CVPR 2025 rip current" — the exact hosting location may have changed; check the paper's project page or the NTIRE 2026 challenge page first).
2. Inspect its actual structure. It likely does NOT already match the `ml/data/ripvis/{split}/{videos,masks}/` layout assumed by `ml/training/dataset.py` — if so, write a `ml/prepare_dataset.py` script that extracts frames from the raw videos and rasterizes the provided annotations into mask images matching that layout. **This is real, necessary work — do not skip it or fake it with synthetic data.**
3. Run `ml/training/train.py` against the real data. Expect this to take real training time — don't short-circuit epochs just to get something to "complete."
4. Run `ml/training/evaluate.py` against the held-out test split. Record the actual IoU/F1/precision/recall numbers.
5. Write a small script (`ml/training/log_benchmark_run.py`, doesn't exist yet — create it) that inserts a row into the `benchmark_runs` table via a direct DB call, so results are tracked historically per the schema design.

### Priority 2 — Wire the backend to a real trained model
1. Confirm `backend/app/services/analysis_service.py` correctly calls `ml/inference/predict.py` with the trained checkpoint path.
2. Do an actual end-to-end test: sign up a user via the API, upload a real test video, poll until `status=done`, and confirm the annotated output video and risk timeline look sane (open the output video and actually look at it — don't just check that the file exists).
3. If the model's predictions are poor (very likely, given this is an open problem) — that's expected and fine. Document what you observe honestly in a new `docs/RESULTS.md` file: what the model gets right, what it misses, and why (e.g., does it confuse wave foam/whitewater with rip currents? Does it miss low-contrast rip currents in calm water?).

### Priority 3 — Build the frontend
Follow `docs/APP_FLOW.md` exactly for the five screens (Login, Dashboard/Session List, Upload, Session Detail, Benchmark). Specific things to get right:
- The **persistent disclaimer banner** on the Session Detail screen ("research prototype, not a certified safety system") is a product requirement from the PRD, not an afterthought — don't drop it.
- The risk timeline visualization should let a user click a point to jump the video to that timestamp (per `APP_FLOW.md` screen 4 spec).
- The Benchmark screen should pull real data from `GET /api/benchmark` and display it plainly — don't decorate it into looking more impressive than the numbers are.
- Use React or Next.js (TRD leaves this open) — pick Next.js if you want easy deployment to Vercel later, plain React + Vite if you want a simpler build.

### Priority 4 — Docker Compose end-to-end
`docker-compose.yml` already exists at the repo root with `db`, `backend`, `frontend` services wired together. The `frontend` service currently has no Dockerfile — write one once the frontend exists. Confirm `docker-compose up` brings up a working stack from a clean clone.

## Constraints and conventions to follow

- **Tech stack is fixed** per `docs/TRD.md` — FastAPI, async SQLAlchemy/PostgreSQL, PyTorch, React/Next.js. Don't substitute different frameworks without a strong reason, and if you do, update `docs/TRD.md` to reflect it and explain why.
- **Don't change the database schema casually.** `docs/SCHEMA.md` is the source of truth; if a real need arises to change it (e.g., you discover `risk_timeline` as JSON genuinely doesn't work), update the doc and explain the tradeoff you're making, matching the reasoning style already used there.
- **Every model/detection-related UI surface must show confidence, never a bare yes/no.** This is a hard requirement from the PRD, not a style preference.
- **Run `pytest` in `backend/` after any backend change.** The existing 3 tests must keep passing; add new tests for new endpoints/logic rather than leaving them uncovered.
- **Comment code to explain *why*, not just *what*** — especially in the ML pipeline, where design choices (loss function choice, confidence thresholds, frame sampling rate) should be explained so a human reviewer (a recruiter, an interviewer, the student themself six months from now) can follow the reasoning.
- **Never fabricate benchmark numbers, dataset statistics, or claim the model performs better than what you actually measured.** This is the single most important constraint in this entire brief. The whole value of this project rests on its numbers being real and reproducible.

## Definition of done for this engagement

You're done with a solid handoff when:
1. The RipVIS dataset is downloaded, prepared, and a model has been trained on it with real, recorded benchmark numbers.
2. The backend end-to-end flow (upload → async inference → poll → view results) works against a real video and a real trained checkpoint.
3. The frontend implements all five screens from `docs/APP_FLOW.md` and talks to the real backend.
4. `docker-compose up` brings the whole stack up from a clean clone.
5. `docs/RESULTS.md` exists with an honest writeup of what the model does well/poorly and why.
6. All backend tests pass, and new tests exist for any new backend functionality you added.

If you get stuck or blocked on something (e.g., the RipVIS dataset download location has changed, or training is computationally infeasible in your environment), stop and clearly report the blocker rather than silently working around it with fake/synthetic shortcuts that would misrepresent the project's real state.
