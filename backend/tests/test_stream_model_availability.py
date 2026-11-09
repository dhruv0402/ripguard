"""Missing checkpoints must never look like a low-risk live observation."""

import asyncio

import numpy as np
import pytest

from app.api import stream as stream_api
from app.services import stream_service
from app.services.stream_service import LiveStreamManager, MultiStreamRegistry, StreamStatus


@pytest.mark.asyncio
async def test_missing_checkpoint_reports_unknown_risk(tmp_path):
    manager = LiveStreamManager(checkpoint_path=str(tmp_path / "missing.pt"))

    await manager.start()

    assert not manager.is_running
    assert manager.stream_status == StreamStatus.DEGRADED
    assert manager.latest_meta["status"] == "degraded"
    assert manager.latest_meta["risk_level"] == "UNKNOWN"
    assert manager.latest_meta["confidence"] is None
    assert manager.latest_meta["error"] == "model_unavailable"
    assert manager.latest_frame_jpeg is None


@pytest.mark.asyncio
async def test_corrupt_checkpoint_reports_unknown_risk(tmp_path):
    checkpoint = tmp_path / "corrupt.pt"
    checkpoint.write_bytes(b"not a PyTorch model")
    manager = LiveStreamManager(checkpoint_path=str(checkpoint))
    await manager.start()

    assert manager.latest_meta["error"] == "model_unavailable"
    assert manager.latest_meta["risk_level"] == "UNKNOWN"
    assert not manager.is_running


@pytest.mark.asyncio
async def test_stream_can_recover_after_model_becomes_available(monkeypatch, tmp_path):
    manager = LiveStreamManager(checkpoint_path=str(tmp_path / "missing.pt"))
    await manager.start()

    class FakeModel:
        def predict_mask(self, _):
            return np.zeros((32, 32), dtype=np.float32)

    class FakeCapture:
        def __init__(self, _):
            self.released = False

        def isOpened(self):
            return not self.released

        def read(self):
            return True, np.zeros((32, 32, 3), dtype=np.uint8)

        def release(self):
            self.released = True

    monkeypatch.setattr(stream_service, "_load_model", lambda *_: (FakeModel(), 3))
    monkeypatch.setattr(stream_service.cv2, "VideoCapture", FakeCapture)
    await manager.start()
    try:
        async with asyncio.timeout(2):
            while manager.latest_frame_jpeg is None:
                await asyncio.sleep(0.01)
        assert manager.latest_meta["status"] == "streaming"
        assert "error" not in manager.latest_meta
        assert manager.latest_meta["risk_level"] == "LOW"
    finally:
        manager.stop()
        await asyncio.sleep(0.05)


@pytest.mark.asyncio
async def test_status_and_feed_handle_missing_model(client, monkeypatch, tmp_path):
    # Use a private registry so neither a trained checkpoint nor a camera is needed.
    registry = MultiStreamRegistry()
    registry.streams["0"] = LiveStreamManager(
        stream_source=0, checkpoint_path=str(tmp_path / "missing.pt")
    )
    monkeypatch.setattr(stream_api, "stream_registry", registry)
    await client.post("/api/auth/signup", json={"email": "missing@beach.gov", "password": "password123"})
    login = await client.post("/api/auth/login", data={"username": "missing@beach.gov", "password": "password123"})
    headers = {"Authorization": f"Bearer {login.json()['access_token']}"}

    status = await client.get("/api/stream/status?source=0", headers=headers)
    assert status.status_code == 200
    assert status.json()["status"] == "degraded"
    assert status.json()["risk_level"] == "UNKNOWN"
    assert status.json()["confidence"] is None

    feed = await client.get("/api/stream/feed?source=0", headers=headers)
    assert feed.status_code == 503
    assert feed.json()["detail"]["error"] == "model_unavailable"


@pytest.mark.asyncio
@pytest.mark.parametrize("failure", ["inference", "disconnect"])
async def test_runtime_failure_clears_stale_safe_observation(monkeypatch, failure):
    class Capture:
        reads = 0
        released = False

        def isOpened(self):
            return True

        def read(self):
            self.reads += 1
            if failure == "disconnect" and self.reads > 1:
                return False, None
            return True, np.zeros((8, 8, 3), dtype=np.uint8)

        def release(self):
            self.released = True

    class Model:
        predictions = 0

        def predict_mask(self, _):
            self.predictions += 1
            if self.predictions > 1:
                raise RuntimeError("Inference device disconnected")
            return np.zeros((8, 8), dtype=np.float32)

    capture = Capture()
    monkeypatch.setattr(stream_service.cv2, "VideoCapture", lambda _: capture)
    manager = LiveStreamManager(stream_source="test-camera")
    manager.model = Model()
    manager.is_running = True
    subscriber = asyncio.Queue(maxsize=1)
    manager.subscribers.add(subscriber)
    task = asyncio.create_task(manager._capture_and_infer_loop())
    try:
        async with asyncio.timeout(2):
            while manager.latest_frame_jpeg is None:
                await asyncio.sleep(0.001)
            assert manager.latest_meta["risk_level"] == "LOW"
            while manager.latest_meta["status"] == "streaming" and not task.done():
                await asyncio.sleep(0.001)
        assert manager.latest_meta["risk_level"] == "UNKNOWN"
        assert manager.latest_meta["confidence"] is None
        assert manager.latest_frame_jpeg is None
        assert subscriber.get_nowait()["risk_level"] == "UNKNOWN"
        if failure == "inference":
            await task
            assert manager.latest_meta["error"] == "inference_failed"
            assert manager.stream_status == StreamStatus.DEGRADED
            assert manager.model is None
        else:
            assert manager.latest_meta["status"] == "reconnecting"
    finally:
        manager.stop()
        task.cancel()
        await asyncio.gather(task, return_exceptions=True)
    assert capture.released


@pytest.mark.asyncio
async def test_reopened_capture_infers_new_frame_without_stale_mask(monkeypatch):
    captures = []

    class Capture:
        reads = 0

        def isOpened(self):
            # First device closes after one frame; replacement remains open.
            return self is not captures[0] or self.reads == 0

        def read(self):
            self.reads += 1
            return True, np.zeros((8, 8, 3), dtype=np.uint8)

        def release(self):
            pass

    def open_capture(_):
        capture = Capture()
        captures.append(capture)
        return capture

    class Model:
        predictions = 0

        def predict_mask(self, _):
            self.predictions += 1
            return np.full((8, 8), 0.0 if self.predictions == 1 else 1.0, dtype=np.float32)

    monkeypatch.setattr(stream_service.cv2, "VideoCapture", open_capture)
    # Alert delivery is unrelated to capture recovery and must not send messages.
    monkeypatch.setattr(stream_service.default_alert_dispatcher, "process_telemetry", lambda _: None)
    manager = LiveStreamManager(stream_source="test-camera")
    manager.model = Model()
    manager.is_running = True
    task = asyncio.create_task(manager._capture_and_infer_loop())
    try:
        async with asyncio.timeout(2):
            while len(captures) < 2:
                await asyncio.sleep(0.001)
        assert manager.latest_meta["risk_level"] == "MEDIUM"
        assert manager.latest_meta["confidence"] == 0.65
    finally:
        manager.stop()
        task.cancel()
        await asyncio.gather(task, return_exceptions=True)
