from pydantic import BaseModel, ConfigDict
from typing import Any
import uuid
from datetime import datetime

from app.models.session import SessionStatus, RiskLevel, FeedbackType


class DetectionOut(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: uuid.UUID
    start_timestamp_sec: float
    end_timestamp_sec: float
    confidence: float
    bounding_region: Any = None


class FeedbackCreate(BaseModel):
    detection_id: uuid.UUID | None = None
    feedback_type: FeedbackType
    confidence_rating: int | None = None  # 1 to 5 scale
    operator_notes: str | None = None
    corrected_region: Any = None


class FeedbackOut(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: uuid.UUID
    session_id: uuid.UUID
    detection_id: uuid.UUID | None = None
    user_id: uuid.UUID
    feedback_type: FeedbackType
    confidence_rating: int | None = None
    operator_notes: str | None = None
    corrected_region: Any = None
    created_at: datetime


class HardExampleItem(BaseModel):
    feedback_id: uuid.UUID
    session_id: uuid.UUID
    detection_id: uuid.UUID | None
    feedback_type: FeedbackType
    video_filename: str
    timestamp_sec: float
    bounding_region: Any = None
    operator_notes: str | None = None


class ActiveLearningManifestOut(BaseModel):
    total_hard_negatives: int
    total_confirmed_positives: int
    generated_at: datetime
    hard_examples: list[HardExampleItem]


class SessionOut(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: uuid.UUID
    filename: str
    location_label: str | None = None
    status: SessionStatus
    overall_risk_level: RiskLevel | None = None
    error_message: str | None = None
    created_at: datetime


class SessionDetailOut(SessionOut):
    risk_timeline: Any = None
    detections: list[DetectionOut] = []
    annotated_video_path: str | None = None
    feedback: list[FeedbackOut] = []


class BenchmarkRunOut(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    model_version: str
    dataset_split: str
    iou: float
    dice_f1: float
    precision: float
    recall: float
    notes: str | None = None
    run_at: datetime


