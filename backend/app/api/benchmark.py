from fastapi import APIRouter, Depends
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy import select

from app.core.database import get_db
from app.models.benchmark import BenchmarkRun
from app.schemas.session import BenchmarkRunOut

router = APIRouter(prefix="/api/benchmark", tags=["benchmark"])


@router.get("", response_model=list[BenchmarkRunOut])
async def list_benchmark_runs(db: AsyncSession = Depends(get_db)):
    """
    Public (no auth required) — this is the honest, auditable record of
    model performance against the RipVIS test set. Intentionally visible
    without login since it's the evidence behind the project's claims.
    """
    result = await db.execute(select(BenchmarkRun).order_by(BenchmarkRun.run_at.desc()))
    return result.scalars().all()
