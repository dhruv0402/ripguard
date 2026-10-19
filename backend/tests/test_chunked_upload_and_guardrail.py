import pytest
import io
import numpy as np
from httpx import AsyncClient
from ml.inference.predict import _is_coastal_environment


@pytest.mark.asyncio
async def test_chunked_upload_file_handling(client: AsyncClient):
    await client.post(
        "/api/auth/signup",
        json={"email": "uploader@beach.gov", "password": "password123"},
    )
    res_login = await client.post(
        "/api/auth/login",
        data={"username": "uploader@beach.gov", "password": "password123"},
    )
    token = res_login.json()["access_token"]
    headers = {"Authorization": f"Bearer {token}"}

    # Upload video in 1MB chunked stream
    fake_video = b"\x00\x00\x00\x18ftypmp42" + (b"A" * 1024 * 100)  # 100KB payload
    files = {"file": ("chunk_test.mp4", io.BytesIO(fake_video), "video/mp4")}

    res = await client.post("/api/sessions", headers=headers, files=files)
    assert res.status_code == 201
    assert res.json()["filename"] == "chunk_test.mp4"
    assert res.json()["status"] == "pending"


def test_coastal_guardrail_rejection():
    # 1. Zero motion / static frames (like an indoor room or slide)
    static_frames = [np.ones((256, 256, 3), dtype=np.uint8) * 100 for _ in range(10)]
    is_coastal, reason = _is_coastal_environment(static_frames)
    assert not is_coastal
    assert "Static or non-fluid video" in reason

    # 2. Insufficient frames
    is_coastal, reason = _is_coastal_environment(static_frames[:2])
    assert not is_coastal
    assert "Insufficient video frames" in reason

    # 3. Dynamic ocean water frames with real motion and blue/cyan/foam colors
    ocean_frames = []
    for i in range(10):
        # Base ocean blue in BGR: Blue=200, Green=140, Red=40
        f = np.zeros((256, 256, 3), dtype=np.uint8)
        f[:, :, 0] = 200 + (i * 3)  # B
        f[:, :, 1] = 140 + (i * 2)  # G
        f[:, :, 2] = 40              # R
        ocean_frames.append(f)

    is_coastal, reason = _is_coastal_environment(ocean_frames)
    assert is_coastal
    assert reason == "Coastal environment verified"
