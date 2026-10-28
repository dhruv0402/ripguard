"""
Runs as a FastAPI BackgroundTask after a video upload. Calls into the ML
inference pipeline (ml/inference/), which is intentionally kept separate
from the web-framework code — the inference module should be runnable and
testable completely standalone, without FastAPI/SQLAlchemy in the loop.
"""

import asyncio
import sys
import os
import uuid

sys.path.append(os.path.join(os.path.dirname(__file__), "..", "..", "..", "ml"))
from inference.predict import run_inference_on_video  # noqa: E402

from app.core import database as db_module
from app.core.config import get_settings
from app.models.session import AnalysisSession, Detection, SessionStatus, RiskLevel

settings = get_settings()

# Confidence thresholds for deriving an overall risk level from the timeline.
HIGH_RISK_CONFIDENCE_THRESHOLD = 0.68
MEDIUM_RISK_CONFIDENCE_THRESHOLD = 0.35

# In-memory registry of active ingestion streams so the UI can display live
# frame-by-frame detection on top of the ingested video while it processes.
LIVE_SESSION_STREAMS: dict[str, dict] = {}


def _derive_risk_level(max_confidence: float) -> RiskLevel:
    if max_confidence >= HIGH_RISK_CONFIDENCE_THRESHOLD:
        return RiskLevel.HIGH
    if max_confidence >= MEDIUM_RISK_CONFIDENCE_THRESHOLD:
        return RiskLevel.MEDIUM
    return RiskLevel.LOW


async def process_video(session_id: uuid.UUID, session_maker=None) -> None:
    sm = session_maker or db_module.AsyncSessionLocal
    sid_str = str(session_id)
    LIVE_SESSION_STREAMS[sid_str] = {
        "is_active": True,
        "latest_jpeg": None,
        "telemetry": {
            "frame_idx": 0,
            "total_frames": 1,
            "progress_pct": 0.0,
            "confidence": 0.0,
            "t": 0.0,
            "region": None,
            "timeline_so_far": [],
        },
    }

    def _on_frame(jpg_bytes: bytes, meta: dict):
        if sid_str in LIVE_SESSION_STREAMS:
            LIVE_SESSION_STREAMS[sid_str]["latest_jpeg"] = jpg_bytes
            LIVE_SESSION_STREAMS[sid_str]["telemetry"] = meta

    async with sm() as db:
        result = await db.get(AnalysisSession, session_id)
        session = result
        if session is None:
            LIVE_SESSION_STREAMS.pop(sid_str, None)
            return

        session.status = SessionStatus.PROCESSING
        await db.commit()

        try:
            inference_result = await asyncio.to_thread(
                run_inference_on_video,
                session.storage_path,
                settings.model_checkpoint_path,
                settings.output_dir,
                settings.inference_frame_sample_rate,
                0.5,
                _on_frame,
            )

            session.annotated_video_path = inference_result["annotated_video_path"]
            session.risk_timeline = inference_result["risk_timeline"]

            confs = sorted(p["confidence"] for p in inference_result["risk_timeline"])
            if not confs:
                sustained_confidence = 0.0
            elif len(confs) < 5:
                sustained_confidence = confs[-1]
            else:
                idx_p90 = min(len(confs) - 1, int(0.90 * len(confs)))
                sustained_confidence = confs[idx_p90]
            session.overall_risk_level = _derive_risk_level(sustained_confidence)

            for det in inference_result["detections"]:
                db.add(
                    Detection(
                        session_id=session.id,
                        start_timestamp_sec=det["start"],
                        end_timestamp_sec=det["end"],
                        confidence=det["confidence"],
                        bounding_region=det.get("region"),
                    )
                )

            session.status = SessionStatus.DONE
            session.error_message = None

        except Exception as e:  # noqa: BLE001 — any inference failure marks the job failed, doesn't crash the worker
            session.status = SessionStatus.FAILED
            session.error_message = str(e)
            session.overall_risk_level = None
            session.risk_timeline = None

        finally:
            if sid_str in LIVE_SESSION_STREAMS:
                LIVE_SESSION_STREAMS[sid_str]["is_active"] = False

        await db.commit()
