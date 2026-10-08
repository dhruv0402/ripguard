import os
import uuid
from fastapi import APIRouter, Depends, UploadFile, File, Form, HTTPException, BackgroundTasks
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy import select
from sqlalchemy.orm import selectinload

from app.core.database import get_db
from app.core.config import get_settings
from app.api.deps import get_current_user
from app.models.user import User
from app.models.session import AnalysisSession, SessionStatus
from app.schemas.session import SessionOut, SessionDetailOut
from app.services.analysis_service import process_video

router = APIRouter(prefix="/api/sessions", tags=["sessions"])
settings = get_settings()

ALLOWED_CONTENT_TYPES = {"video/mp4", "video/quicktime", "video/x-msvideo"}


@router.post("", response_model=SessionOut, status_code=201)
async def upload_video(
    background_tasks: BackgroundTasks,
    file: UploadFile = File(...),
    location_label: str | None = Form(None),
    user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    if file.content_type not in ALLOWED_CONTENT_TYPES:
        raise HTTPException(status_code=400, detail=f"Unsupported file type: {file.content_type}")

    contents = await file.read()
    max_bytes = settings.max_upload_size_mb * 1024 * 1024
    if len(contents) > max_bytes:
        raise HTTPException(status_code=400, detail=f"File exceeds {settings.max_upload_size_mb}MB limit")

    os.makedirs(settings.upload_dir, exist_ok=True)
    session_id = uuid.uuid4()
    extension = os.path.splitext(file.filename or "")[1] or ".mp4"
    storage_path = os.path.join(settings.upload_dir, f"{session_id}{extension}")

    with open(storage_path, "wb") as f:
        f.write(contents)

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
    await db.refresh(session)

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
        .options(selectinload(AnalysisSession.detections))
        .where(AnalysisSession.id == session_id, AnalysisSession.owner_id == user.id)
    )
    session = result.scalar_one_or_none()
    if session is None:
        raise HTTPException(status_code=404, detail="Session not found")
    return session


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
    user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    result = await db.execute(
        select(AnalysisSession)
        .where(AnalysisSession.id == session_id, AnalysisSession.owner_id == user.id)
    )
    session = result.scalar_one_or_none()
    if session is None:
        raise HTTPException(status_code=404, detail="Session not found")
    if not session.annotated_video_path or not os.path.exists(session.annotated_video_path):
        raise HTTPException(status_code=404, detail="Annotated video not available yet")

    from fastapi.responses import FileResponse
    return FileResponse(session.annotated_video_path, media_type="video/mp4")

