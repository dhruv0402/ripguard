"""
Direct DB logging script for benchmark runs.
Inserts an evaluation record into the `benchmark_runs` table.
"""

import argparse
import asyncio
import uuid
from datetime import datetime, timezone

from sqlalchemy.ext.asyncio import create_async_engine, AsyncSession, async_sessionmaker
from sqlalchemy.dialects.postgresql import UUID
from sqlalchemy import String, DateTime, Float, Text
from sqlalchemy.orm import DeclarativeBase, Mapped, mapped_column


class Base(DeclarativeBase):
    pass


class BenchmarkRun(Base):
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


async def log_run(
    db_url: str,
    model_version: str,
    dataset_split: str,
    iou: float,
    dice_f1: float,
    precision: float,
    recall: float,
    notes: str | None = None,
):
    engine = create_async_engine(db_url)
    async_session = async_sessionmaker(engine, expire_on_commit=False, class_=AsyncSession)

    async with engine.begin() as conn:
        await conn.run_sync(Base.metadata.create_all)

    async with async_session() as session:
        run_record = BenchmarkRun(
            model_version=model_version,
            dataset_split=dataset_split,
            iou=iou,
            dice_f1=dice_f1,
            precision=precision,
            recall=recall,
            notes=notes,
        )
        session.add(run_record)
        await session.commit()
        print(f"Logged benchmark run {run_record.id} for {model_version} on {dataset_split}:")
        print(f"  IoU: {iou:.4f} | F1: {dice_f1:.4f} | Precision: {precision:.4f} | Recall: {recall:.4f}")

    await engine.dispose()


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description="Log benchmark evaluation metrics to the database")
    parser.add_argument("--db-url", type=str, default="sqlite+aiosqlite:///backend/ripguard.db")
    parser.add_argument("--model-version", type=str, default="unet_resnet34_epoch8")
    parser.add_argument("--dataset-split", type=str, default="ripvis_test")
    parser.add_argument("--iou", type=float, required=True)
    parser.add_argument("--dice-f1", type=float, required=True)
    parser.add_argument("--precision", type=float, required=True)
    parser.add_argument("--recall", type=float, required=True)
    parser.add_argument("--notes", type=str, default=None)

    args = parser.parse_args()

    asyncio.run(
        log_run(
            db_url=args.db_url,
            model_version=args.model_version,
            dataset_split=args.dataset_split,
            iou=args.iou,
            dice_f1=args.dice_f1,
            precision=args.precision,
            recall=args.recall,
            notes=args.notes,
        )
    )
