"""
Inference Job Queue & Worker Pool:
Decouples heavy ML video inference from FastAPI HTTP request threads.
Uses a bounded asynchronous queue with a dedicated worker pool to prevent host
GPU/CPU starvation and out-of-memory crashes under concurrent load.
"""

import asyncio
import logging
import uuid
from typing import Callable, Coroutine, Any
from enum import Enum

logger = logging.getLogger(__name__)


class JobStatus(str, Enum):
    QUEUED = "queued"
    PROCESSING = "processing"
    COMPLETED = "completed"
    FAILED = "failed"


class InferenceJobQueue:
    def __init__(self, max_concurrent_workers: int = 2):
        self.max_workers = max_concurrent_workers
        self.queue: asyncio.Queue = asyncio.Queue()
        self.active_workers: list[asyncio.Task] = []
        self.job_registry: dict[str, dict[str, Any]] = {}
        self.is_running: bool = False

    async def start(self):
        """Starts worker tasks in the background."""
        if self.is_running:
            return
        self.is_running = True
        for i in range(self.max_workers):
            task = asyncio.create_task(self._worker_loop(worker_id=i + 1))
            self.active_workers.append(task)
        logger.info("InferenceJobQueue initialized with %d workers", self.max_workers)

    async def stop(self):
        """Gracefully drains and cancels active workers."""
        self.is_running = False
        for task in self.active_workers:
            task.cancel()
        self.active_workers.clear()

    async def enqueue(
        self,
        job_id: uuid.UUID | str,
        handler: Callable[..., Coroutine[Any, Any, None]],
        *args,
        **kwargs,
    ) -> str:
        """Enqueues an inference task and returns the job ID."""
        jid = str(job_id)
        self.job_registry[jid] = {
            "status": JobStatus.QUEUED,
            "error": None,
            "queue_position": self.queue.qsize() + 1,
        }
        await self.queue.put((jid, handler, args, kwargs))
        logger.info("Job %s enqueued. Current queue depth: %d", jid, self.queue.qsize())
        return jid

    def get_job_status(self, job_id: uuid.UUID | str) -> dict[str, Any] | None:
        return self.job_registry.get(str(job_id))

    @property
    def queue_depth(self) -> int:
        return self.queue.qsize()

    @property
    def active_jobs_count(self) -> int:
        return sum(
            1 for j in self.job_registry.values()
            if j.get("status") == JobStatus.PROCESSING
        )


    async def _worker_loop(self, worker_id: int):
        while self.is_running:
            try:
                jid, handler, args, kwargs = await self.queue.get()
                if jid in self.job_registry:
                    self.job_registry[jid]["status"] = JobStatus.PROCESSING

                logger.info("Worker #%d started processing job %s", worker_id, jid)
                try:
                    await handler(*args, **kwargs)
                    if jid in self.job_registry:
                        self.job_registry[jid]["status"] = JobStatus.COMPLETED
                    logger.info("Worker #%d finished job %s successfully", worker_id, jid)
                except Exception as exc:
                    logger.exception("Worker #%d encountered error on job %s: %s", worker_id, jid, exc)
                    if jid in self.job_registry:
                        self.job_registry[jid]["status"] = JobStatus.FAILED
                        self.job_registry[jid]["error"] = str(exc)
                finally:
                    self.queue.task_done()
            except asyncio.CancelledError:
                break
            except Exception as e:
                logger.error("Worker #%d loop exception: %s", worker_id, e)
                await asyncio.sleep(0.5)


default_job_queue = InferenceJobQueue(max_concurrent_workers=2)
