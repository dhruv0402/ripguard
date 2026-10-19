"""
Matches docs/SCHEMA.md. The risk_timeline is a JSON column directly on
AnalysisSession (per the design note in SCHEMA.md) rather than a normalized
table, since it's always read/written as a whole unit per session.
"""

import uuid
import enum
from datetime import datetime, timezone
from sqlalchemy import String, DateTime, ForeignKey, Enum, Float, Text, JSON, Integer
from sqlalchemy.orm import Mapped, mapped_column, relationship
from sqlalchemy.dialects.postgresql import UUID

from app.core.database import Base


class SessionStatus(str, enum.Enum):
    PENDING = "pending"
    PROCESSING = "processing"
    DONE = "done"
    FAILED = "failed"


class RiskLevel(str, enum.Enum):
    LOW = "low"
    MEDIUM = "medium"
    HIGH = "high"


class FeedbackType(str, enum.Enum):
    CONFIRMED_TRUE_POSITIVE = "confirmed_true_positive"
    FALSE_POSITIVE_WAKE = "false_positive_wake"
    FALSE_POSITIVE_SANDBAR = "false_positive_sandbar"
    FALSE_POSITIVE_WAVE_BREAK = "false_positive_wave_break"
    FALSE_POSITIVE_OTHER = "false_positive_other"
    MISSED_DETECTION = "missed_detection"


class AnalysisSession(Base):
    __tablename__ = "analysis_sessions"

    id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    owner_id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), ForeignKey("users.id"), nullable=False)

    filename: Mapped[str] = mapped_column(String(255), nullable=False)
    location_label: Mapped[str | None] = mapped_column(String(255), nullable=True)
    storage_path: Mapped[str] = mapped_column(String(512), nullable=False)
    annotated_video_path: Mapped[str | None] = mapped_column(String(512), nullable=True)

    status: Mapped[SessionStatus] = mapped_column(Enum(SessionStatus), default=SessionStatus.PENDING)
    error_message: Mapped[str | None] = mapped_column(Text, nullable=True)
    overall_risk_level: Mapped[RiskLevel | None] = mapped_column(Enum(RiskLevel), nullable=True)

    # Per-sampled-frame confidence timeline, e.g. [{"t": 0.0, "confidence": 0.12}, ...]
    risk_timeline: Mapped[list | None] = mapped_column(JSON, nullable=True)

    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=lambda: datetime.now(timezone.utc))

    owner: Mapped["User"] = relationship(back_populates="sessions")
    detections: Mapped[list["Detection"]] = relationship(back_populates="session", cascade="all, delete-orphan")
    feedback: Mapped[list["DetectionFeedback"]] = relationship(back_populates="session", cascade="all, delete-orphan")


class Detection(Base):
    __tablename__ = "detections"

    id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    session_id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), ForeignKey("analysis_sessions.id"), nullable=False)

    start_timestamp_sec: Mapped[float] = mapped_column(Float, nullable=False)
    end_timestamp_sec: Mapped[float] = mapped_column(Float, nullable=False)
    confidence: Mapped[float] = mapped_column(Float, nullable=False)

    # Normalized region descriptor, e.g. {"x": 0.3, "y": 0.5, "w": 0.2, "h": 0.15}
    bounding_region: Mapped[dict | None] = mapped_column(JSON, nullable=True)

    session: Mapped["AnalysisSession"] = relationship(back_populates="detections")
    feedback: Mapped[list["DetectionFeedback"]] = relationship(back_populates="detection", cascade="all, delete-orphan")


class DetectionFeedback(Base):
    __tablename__ = "detection_feedback"

    id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    session_id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), ForeignKey("analysis_sessions.id"), nullable=False)
    detection_id: Mapped[uuid.UUID | None] = mapped_column(UUID(as_uuid=True), ForeignKey("detections.id"), nullable=True)
    user_id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), ForeignKey("users.id"), nullable=False)

    feedback_type: Mapped[FeedbackType] = mapped_column(Enum(FeedbackType), nullable=False)
    confidence_rating: Mapped[int | None] = mapped_column(Integer, nullable=True)  # 1 to 5 scale
    operator_notes: Mapped[str | None] = mapped_column(Text, nullable=True)
    corrected_region: Mapped[dict | None] = mapped_column(JSON, nullable=True)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=lambda: datetime.now(timezone.utc))

    session: Mapped["AnalysisSession"] = relationship(back_populates="feedback")
    detection: Mapped["Detection | None"] = relationship(back_populates="feedback")
    user: Mapped["User"] = relationship()

