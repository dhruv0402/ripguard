import os
import uuid
from fastapi import APIRouter, Depends, UploadFile, File, Form, HTTPException, BackgroundTasks
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy import select
from sqlalchemy.orm import selectinload

from app.core.database import get_db
from app.core.config import get_settings
from app.core.rate_limiter import rate_limit_upload
from app.api.deps import get_current_user, get_current_user_flexible
from app.models.user import User
from app.models.session import AnalysisSession, SessionStatus, Detection, DetectionFeedback
from app.schemas.session import (
    SessionOut,
    SessionDetailOut,
    FeedbackCreate,
    FeedbackOut,
    ActiveLearningManifestOut,
)
from app.services.analysis_service import process_video
from app.services.task_queue import default_job_queue
from ml.active_learning.harvester import ActiveLearningHarvester

router = APIRouter(prefix="/api/sessions", tags=["sessions"])
settings = get_settings()


ALLOWED_CONTENT_TYPES = {"video/mp4", "video/quicktime", "video/x-msvideo"}


@router.post("", response_model=SessionOut, status_code=201)
async def upload_video(
    background_tasks: BackgroundTasks,
    file: UploadFile = File(...),
    location_label: str | None = Form(None),
    user: User = Depends(get_current_user),
    _rate_check: None = Depends(rate_limit_upload),
    db: AsyncSession = Depends(get_db),
):

    if file.content_type not in ALLOWED_CONTENT_TYPES:
        raise HTTPException(status_code=400, detail=f"Unsupported file type: {file.content_type}")

    os.makedirs(settings.upload_dir, exist_ok=True)
    session_id = uuid.uuid4()
    extension = os.path.splitext(file.filename or "")[1] or ".mp4"
    storage_path = os.path.join(settings.upload_dir, f"{session_id}{extension}")

    max_bytes = settings.max_upload_size_mb * 1024 * 1024
    bytes_written = 0

    try:
        with open(storage_path, "wb") as f:
            while chunk := await file.read(1024 * 1024):  # 1MB chunks to prevent RAM exhaustion
                bytes_written += len(chunk)
                if bytes_written > max_bytes:
                    raise HTTPException(
                        status_code=400,
                        detail=f"File exceeds {settings.max_upload_size_mb}MB limit",
                    )
                f.write(chunk)
    except HTTPException:
        if os.path.exists(storage_path):
            os.remove(storage_path)
        raise
    except Exception as e:
        if os.path.exists(storage_path):
            os.remove(storage_path)
        raise HTTPException(status_code=500, detail=f"Failed to save upload: {e}")

    session = AnalysisSession(
        id=session_id,
        owner_id=user.id,
        filename=file.filename or "upload",
        location_label=location_label,
        storage_path=storage_path,
        status=SessionStatus.PENDING,
    )
    db.add(session)
    await db.commit()
    if default_job_queue.is_running:
        await default_job_queue.enqueue(session.id, process_video, session.id)
    else:
        background_tasks.add_task(process_video, session.id)

    return session




TEST_ASSETS_CATALOG = [
    {
        "filename": "active_rip_current.mp4",
        "title": "Active Rip Current Channel (Tower Cam)",
        "category": "Strong Rip Current (High Risk)",
        "location": "South Goa Lifeguard Tower 2",
    },
    {
        "filename": "drone_rip_channel_001.mp4",
        "title": "Aerial Drone Rip Current Neck & Plume (RipVIS-001)",
        "category": "Strong Rip Current (High Risk)",
        "location": "RipVIS Aerial Survey Sector A",
    },
    {
        "filename": "coastal_surf_rip_014.mp4",
        "title": "Breaking Sandbar Feeder Current (RipVIS-014)",
        "category": "Strong Rip Current (High Risk)",
        "location": "RipVIS Coastal Cam 14",
    },
    {
        "filename": "beach_break_rip_024.mp4",
        "title": "Cross-Shore Surf Break Rip Channel (RipVIS-024)",
        "category": "Moderate / Strong Rip Current",
        "location": "RipVIS Surf Break Sector 24",
    },
    {
        "filename": "offshore_plume_rip_053.mp4",
        "title": "Offshore Sediment Rip Plume (RipVIS-053)",
        "category": "Moderate Rip Current (Caution)",
        "location": "RipVIS Headland Cam 53",
    },
    {
        "filename": "beach_ripvis_072.mp4",
        "title": "Moderate Offshore Feeder Channel (RipVIS-072)",
        "category": "Moderate Rip Current (Caution)",
        "location": "Calangute North Cam",
    },
    {
        "filename": "calm_beach_no_rip.mp4",
        "title": "Calm Beach Shoreline Wash (Negative Control)",
        "category": "Safe / Calm Water (Low Risk)",
        "location": "Baga South Safe Zone",
    },
    {
        "filename": "safe_shoreline_waves_nr004.mp4",
        "title": "Uniform Planar Breaking Waves (RipVIS-NR-004)",
        "category": "Safe / Calm Water (Low Risk)",
        "location": "RipVIS Safe Control Beach #4",
    },
    {
        "filename": "calm_coastal_surf_nr019.mp4",
        "title": "Gentle Coastal Swell — No Rip Channel (RipVIS-NR-019)",
        "category": "Safe / Calm Water (Low Risk)",
        "location": "RipVIS Safe Control Beach #19",
    },
    {
        "filename": "non_coastal_ood_test.mp4",
        "title": "Non-Beach / Indoor Feed (OOD Guardrail Test)",
        "category": "Out-of-Distribution Rejection Test",
        "location": "Indoor Control Room Feed",
    },
]


@router.get("/test-assets/list")
async def list_test_assets():
    """Lists available test videos in test_assets/ for quick UI testing."""
    available = []
    for item in TEST_ASSETS_CATALOG:
        path = os.path.join("test_assets", item["filename"])
        if os.path.exists(path):
            size_mb = round(os.path.getsize(path) / (1024 * 1024), 2)
            available.append({**item, "size_mb": size_mb})
    return available


@router.post("/test-assets/run", response_model=SessionOut, status_code=201)
async def run_test_asset(
    background_tasks: BackgroundTasks,
    filename: str = Form(...),
    location_label: str | None = Form(None),
    user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    """Creates and runs a live analysis session directly from a file in test_assets/."""
    import shutil
    safe_name = os.path.basename(filename)
    src_path = os.path.join("test_assets", safe_name)
    if not os.path.exists(src_path):
        raise HTTPException(status_code=404, detail=f"Test asset {safe_name} not found in test_assets/")

    os.makedirs(settings.upload_dir, exist_ok=True)
    session_id = uuid.uuid4()
    storage_path = os.path.join(settings.upload_dir, f"{session_id}.mp4")
    shutil.copyfile(src_path, storage_path)

    session = AnalysisSession(
        id=session_id,
        owner_id=user.id,
        filename=safe_name,
        location_label=location_label or "RipVIS Test Suite",
        storage_path=storage_path,
        status=SessionStatus.PENDING,
    )
    db.add(session)
    await db.commit()
    if default_job_queue.is_running:
        await default_job_queue.enqueue(session.id, process_video, session.id)
    else:
        background_tasks.add_task(process_video, session.id)
    return session



@router.get("/{session_id}", response_model=SessionDetailOut)
async def get_session(
    session_id: uuid.UUID,
    user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    result = await db.execute(
        select(AnalysisSession)
        .options(
            selectinload(AnalysisSession.detections),
            selectinload(AnalysisSession.feedback),
        )
        .where(AnalysisSession.id == session_id, AnalysisSession.owner_id == user.id)
    )
    session = result.scalar_one_or_none()
    if session is None:
        raise HTTPException(status_code=404, detail="Session not found")
    return session


@router.post("/{session_id}/feedback", response_model=FeedbackOut, status_code=201)
async def submit_session_feedback(
    session_id: uuid.UUID,
    payload: FeedbackCreate,
    user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    """
    Operator / Lifeguard feedback endpoint for Human-in-the-Loop Active Learning (RLHF).
    Allows marking true/false positives (wakes, sandbars) and missing detections.
    """
    sess_res = await db.execute(
        select(AnalysisSession).where(
            AnalysisSession.id == session_id,
            AnalysisSession.owner_id == user.id,
        )
    )
    session = sess_res.scalar_one_or_none()
    if session is None:
        raise HTTPException(status_code=404, detail="Session not found")

    if payload.detection_id is not None:
        det_res = await db.execute(
            select(Detection).where(
                Detection.id == payload.detection_id,
                Detection.session_id == session_id,
            )
        )
        detection = det_res.scalar_one_or_none()
        if detection is None:
            raise HTTPException(status_code=404, detail="Detection not found for this session")

    fb = DetectionFeedback(
        id=uuid.uuid4(),
        session_id=session_id,
        detection_id=payload.detection_id,
        user_id=user.id,
        feedback_type=payload.feedback_type,
        confidence_rating=payload.confidence_rating,
        operator_notes=payload.operator_notes,
        corrected_region=payload.corrected_region,
    )
    db.add(fb)
    await db.commit()
    await db.refresh(fb)
    return fb


@router.get("/{session_id}/feedback", response_model=list[FeedbackOut])
async def list_session_feedback(
    session_id: uuid.UUID,
    user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    sess_res = await db.execute(
        select(AnalysisSession).where(
            AnalysisSession.id == session_id,
            AnalysisSession.owner_id == user.id,
        )
    )
    session = sess_res.scalar_one_or_none()
    if session is None:
        raise HTTPException(status_code=404, detail="Session not found")

    res = await db.execute(
        select(DetectionFeedback)
        .where(DetectionFeedback.session_id == session_id)
        .order_by(DetectionFeedback.created_at.desc())
    )
    return res.scalars().all()


@router.get("/{session_id}/active-learning-manifest")
async def get_active_learning_manifest(
    session_id: uuid.UUID,
    user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    """
    Exports a curated active learning training manifest from operator feedback
    for continuous model improvement and hard-negative mining.
    """
    sess_res = await db.execute(
        select(AnalysisSession).where(
            AnalysisSession.id == session_id,
            AnalysisSession.owner_id == user.id,
        )
    )
    session = sess_res.scalar_one_or_none()
    if session is None:
        raise HTTPException(status_code=404, detail="Session not found")

    res = await db.execute(
        select(DetectionFeedback, Detection)
        .join(Detection, DetectionFeedback.detection_id == Detection.id, isouter=True)
        .where(DetectionFeedback.session_id == session_id)
    )
    rows = res.all()

    records = []
    for fb, det in rows:
        records.append({
            "id": fb.id,
            "session_id": fb.session_id,
            "detection_id": fb.detection_id,
            "video_filename": session.filename,
            "timestamp_sec": det.start_timestamp_sec if det else 0.0,
            "bounding_region": fb.corrected_region or (det.bounding_region if det else None),
            "operator_notes": fb.operator_notes,
            "confidence_rating": fb.confidence_rating,
            "feedback_type": fb.feedback_type.value if hasattr(fb.feedback_type, "value") else str(fb.feedback_type),
        })

    return ActiveLearningHarvester.compile_manifest(records)



@router.get("", response_model=list[SessionOut])
async def list_sessions(
    user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    result = await db.execute(
        select(AnalysisSession)
        .where(AnalysisSession.owner_id == user.id)
        .order_by(AnalysisSession.created_at.desc())
    )
    return result.scalars().all()


@router.get("/{session_id}/video")
async def get_session_video(
    session_id: uuid.UUID,
    user: User = Depends(get_current_user_flexible),
    db: AsyncSession = Depends(get_db),
):
    result = await db.execute(
        select(AnalysisSession).where(
            AnalysisSession.id == session_id,
            AnalysisSession.owner_id == user.id,
        )
    )
    session = result.scalar_one_or_none()
    if session is None:
        raise HTTPException(status_code=404, detail="Session not found")

    video_path = session.annotated_video_path or session.storage_path
    if not video_path or not os.path.exists(video_path):
        raise HTTPException(status_code=404, detail="Video not available yet")

    from fastapi.responses import FileResponse
    return FileResponse(video_path, media_type="video/mp4")


@router.get("/{session_id}/live-telemetry")
async def get_session_live_telemetry(
    session_id: uuid.UUID,
    user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    """Returns real-time frame-by-frame telemetry while an ingested video is being processed."""
    result = await db.execute(
        select(AnalysisSession).where(
            AnalysisSession.id == session_id,
            AnalysisSession.owner_id == user.id,
        )
    )
    session = result.scalar_one_or_none()
    if session is None:
        raise HTTPException(status_code=404, detail="Session not found")

    from app.services.analysis_service import LIVE_SESSION_STREAMS
    sid_str = str(session_id)
    state = LIVE_SESSION_STREAMS.get(sid_str)
    if not state:
        return {"is_active": False, "telemetry": None}
    return {
        "is_active": state.get("is_active", False),
        "telemetry": state.get("telemetry"),
    }


@router.get("/{session_id}/live-feed")
async def get_session_live_feed(
    session_id: uuid.UUID,
    user: User = Depends(get_current_user_flexible),
    db: AsyncSession = Depends(get_db),
):
    """Streams live annotated MJPEG frames of the ingested video as it is being analyzed."""
    result = await db.execute(
        select(AnalysisSession).where(
            AnalysisSession.id == session_id,
            AnalysisSession.owner_id == user.id,
        )
    )
    session = result.scalar_one_or_none()
    if session is None:
        raise HTTPException(status_code=404, detail="Session not found")

    import asyncio
    from fastapi.responses import StreamingResponse
    from app.services.analysis_service import LIVE_SESSION_STREAMS

    sid_str = str(session_id)

    async def frame_generator():
        last_sent = None
        for _ in range(1800):  # up to ~90s
            state = LIVE_SESSION_STREAMS.get(sid_str)
            if state and state.get("latest_jpeg") is not None:
                jpg = state["latest_jpeg"]
                if jpg is not last_sent:
                    last_sent = jpg
                    yield (
                        b"--frame\r\n"
                        b"Content-Type: image/jpeg\r\n\r\n" + jpg + b"\r\n"
                    )
            if state and not state.get("is_active", False):
                break
            await asyncio.sleep(0.05)

    return StreamingResponse(
        frame_generator(),
        media_type="multipart/x-mixed-replace; boundary=frame",
    )


