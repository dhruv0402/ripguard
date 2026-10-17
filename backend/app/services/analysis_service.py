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
# These are intentionally simple and documented here so they're easy to
# revisit once real model performance numbers are in — don't treat these
# as tuned/validated values yet.
HIGH_RISK_CONFIDENCE_THRESHOLD = 0.7
MEDIUM_RISK_CONFIDENCE_THRESHOLD = 0.4


def _derive_risk_level(max_confidence: float) -> RiskLevel:
    if max_confidence >= HIGH_RISK_CONFIDENCE_THRESHOLD:
        return RiskLevel.HIGH
    if max_confidence >= MEDIUM_RISK_CONFIDENCE_THRESHOLD:
        return RiskLevel.MEDIUM
    return RiskLevel.LOW


async def process_video(session_id: uuid.UUID, session_maker=None) -> None:
    sm = session_maker or db_module.AsyncSessionLocal
    async with sm() as db:
        result = await db.get(AnalysisSession, session_id)
        session = result
        if session is None:
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
            )
            # inference_result expected shape (see ml/inference/predict.py):
            # {
            #   "annotated_video_path": str,
            #   "risk_timeline": [{"t": float, "confidence": float}, ...],
            #   "detections": [{"start": float, "end": float, "confidence": float, "region": dict}, ...]
            # }

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

        await db.commit()
