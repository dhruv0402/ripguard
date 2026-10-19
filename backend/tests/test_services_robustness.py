import asyncio
import uuid
import pytest
from app.services.task_queue import InferenceJobQueue
from app.core.rate_limiter import SlidingWindowRateLimiter
from app.services.stream_service import MultiStreamRegistry


@pytest.mark.asyncio
async def test_inference_job_queue_concurrency():
    queue = InferenceJobQueue(max_concurrent_workers=2)
    await queue.start()

    executed_jobs = []
    active_worker_counts = []

    async def mock_task(job_id: str, duration: float):
        active_worker_counts.append(queue.active_jobs_count)
        await asyncio.sleep(duration)
        executed_jobs.append(job_id)

    id1 = uuid.uuid4()
    id2 = uuid.uuid4()
    id3 = uuid.uuid4()

    await queue.enqueue(id1, mock_task, "job-1", 0.05)
    await queue.enqueue(id2, mock_task, "job-2", 0.05)
    await queue.enqueue(id3, mock_task, "job-3", 0.05)

    # Let jobs process
    await asyncio.sleep(0.2)
    await queue.stop()

    assert len(executed_jobs) == 3
    # At no point should active workers exceed max_concurrent_workers (2)
    for count in active_worker_counts:
        assert count <= 2


@pytest.mark.asyncio
async def test_sliding_window_rate_limiter():
    limiter = SlidingWindowRateLimiter(max_requests=3, window_seconds=1.0)
    client_ip = "192.168.1.100"

    # First 3 requests must pass
    assert limiter.is_allowed(client_ip) is True
    assert limiter.is_allowed(client_ip) is True
    assert limiter.is_allowed(client_ip) is True

    # 4th request must be rejected
    assert limiter.is_allowed(client_ip) is False

    # Wait for window to expire
    await asyncio.sleep(1.05)
    assert limiter.is_allowed(client_ip) is True


@pytest.mark.asyncio
async def test_multi_stream_registry():
    registry = MultiStreamRegistry()

    stream1 = registry.register_stream("cam-north")
    stream2 = registry.register_stream("cam-south")

    assert stream1.stream_source == "cam-north"
    assert stream2.stream_source == "cam-south"


    active = registry.list_active_streams()
    assert "cam-north" in active
    assert "cam-south" in active

    registry.deregister_stream("cam-north")
    assert registry.get_stream("cam-north") is None
    assert registry.get_stream("cam-south") is not None
