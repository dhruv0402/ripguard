import os
from fastapi import FastAPI, Depends, Response, status
from fastapi.middleware.cors import CORSMiddleware
from contextlib import asynccontextmanager
from sqlalchemy import text
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.config import get_settings
from app.core.database import init_db, get_db
from app.services.task_queue import default_job_queue
from app.api import auth, sessions, benchmark, stream

settings = get_settings()


@asynccontextmanager
async def lifespan(app: FastAPI):
    await init_db()
    await default_job_queue.start()
    yield
    await default_job_queue.stop()


app = FastAPI(title=settings.app_name, lifespan=lifespan)


app.add_middleware(
    CORSMiddleware,
    allow_origins=settings.cors_origins,
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

app.include_router(auth.router)
app.include_router(sessions.router)
app.include_router(benchmark.router)
app.include_router(stream.router)


@app.get("/health")
async def health(response: Response, db: AsyncSession = Depends(get_db)):
    model_exists = os.path.exists(settings.model_checkpoint_path) or os.path.exists(
        "ml/checkpoints/ripguard_unet_best.pt"
    )
    health_status = {
        "status": "healthy",
        "database": "healthy",
        "model_checkpoint": "loaded" if model_exists else "missing",
        "job_queue": {
            "is_running": default_job_queue.is_running,
            "depth": default_job_queue.queue_depth,
        },
    }

    try:
        await db.execute(text("SELECT 1"))
    except Exception as e:
        health_status["database"] = f"unhealthy: {e}"
        health_status["status"] = "degraded"
        response.status_code = status.HTTP_503_SERVICE_UNAVAILABLE

    if health_status["model_checkpoint"] == "missing":
        health_status["status"] = "degraded"

    return health_status

