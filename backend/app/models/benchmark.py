import uuid
from datetime import datetime, timezone
from sqlalchemy import String, DateTime, Float, Text
from sqlalchemy.orm import Mapped, mapped_column
from sqlalchemy.dialects.postgresql import UUID

from app.core.database import Base


class BenchmarkRun(Base):
    """
    Records of model evaluation runs against the RipVIS test set.
    This is the auditable record behind the project's "here's how well the
    model actually performs" claim — never overwritten, always appended to,
    so the history of model improvement attempts is visible.
    """

    __tablename__ = "benchmark_runs"

    id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    model_version: Mapped[str] = mapped_column(String(100), nullable=False)
    dataset_split: Mapped[str] = mapped_column(String(100), nullable=False, default="ripvis_test")

    iou: Mapped[float] = mapped_column(Float, nullable=False)
    dice_f1: Mapped[float] = mapped_column(Float, nullable=False)
    precision: Mapped[float] = mapped_column(Float, nullable=False)
    recall: Mapped[float] = mapped_column(Float, nullable=False)

    notes: Mapped[str | None] = mapped_column(Text, nullable=True)
    run_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=lambda: datetime.now(timezone.utc))
