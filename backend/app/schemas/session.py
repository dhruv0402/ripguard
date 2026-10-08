from pydantic import BaseModel
from typing import Any
import uuid
from datetime import datetime

from app.models.session import SessionStatus, RiskLevel


class DetectionOut(BaseModel):
    id: uuid.UUID
    start_timestamp_sec: float
    end_timestamp_sec: float
    confidence: float
    bounding_region: Any = None

    class Config:
        from_attributes = True


class SessionOut(BaseModel):
    id: uuid.UUID
    filename: str
    location_label: str | None = None
    status: SessionStatus
    overall_risk_level: RiskLevel | None = None
    error_message: str | None = None
    created_at: datetime

    class Config:
        from_attributes = True


class SessionDetailOut(SessionOut):
    risk_timeline: Any = None
    detections: list[DetectionOut] = []
    annotated_video_path: str | None = None


class BenchmarkRunOut(BaseModel):
    model_version: str
    dataset_split: str
    iou: float
    dice_f1: float
    precision: float
    recall: float
    notes: str | None = None
    run_at: datetime

    class Config:
        from_attributes = True
