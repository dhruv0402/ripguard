import pytest
import io
import uuid
from httpx import AsyncClient

from app.models.benchmark import BenchmarkRun
from tests.conftest import TestSessionLocal


@pytest.mark.asyncio
async def test_benchmark_endpoint_public(client: AsyncClient):
    # Insert a benchmark run in the database
    async with TestSessionLocal() as session:
        run_record = BenchmarkRun(
            id=uuid.uuid4(),
            model_version="ripguard_unet_v1",
            dataset_split="ripvis_test",
            iou=0.3211,
            dice_f1=0.4973,
            precision=0.4554,
            recall=0.5478,
            notes="Baseline evaluation",
        )
        session.add(run_record)
        await session.commit()

    # Public GET /api/benchmark without auth token
    response = await client.get("/api/benchmark")
    assert response.status_code == 200
    data = response.json()
    assert len(data) >= 1
    assert data[0]["model_version"] == "ripguard_unet_v1"
    assert data[0]["iou"] == 0.3211
    assert data[0]["dice_f1"] == 0.4973


@pytest.mark.asyncio
async def test_session_endpoints(client: AsyncClient):
    # Signup and login
    signup_res = await client.post(
        "/api/auth/signup",
        json={"email": "operator@beachsafe.gov", "password": "securepassword123"},
    )
    assert signup_res.status_code == 201

    login_res = await client.post(
        "/api/auth/login",
        data={"username": "operator@beachsafe.gov", "password": "securepassword123"},
    )
    assert login_res.status_code == 200
    token = login_res.json()["access_token"]
    headers = {"Authorization": f"Bearer {token}"}

    # Upload video
    fake_video_content = b"\x00\x00\x00\x18ftypmp42\x00\x00\x00\x00mp42mp41"
    files = {"file": ("test_beach.mp4", io.BytesIO(fake_video_content), "video/mp4")}
    data = {"location_label": "Calangute Beach, Goa"}

    upload_res = await client.post("/api/sessions", headers=headers, files=files, data=data)
    assert upload_res.status_code == 201
    session_data = upload_res.json()
    assert session_data["filename"] == "test_beach.mp4"
    assert session_data["location_label"] == "Calangute Beach, Goa"
    assert session_data["status"] == "pending"
    session_id = session_data["id"]

    # List sessions
    list_res = await client.get("/api/sessions", headers=headers)
    assert list_res.status_code == 200
    sessions_list = list_res.json()
    assert len(sessions_list) == 1
    assert sessions_list[0]["id"] == session_id

    # Get session detail
    detail_res = await client.get(f"/api/sessions/{session_id}", headers=headers)
    assert detail_res.status_code == 200
    detail_data = detail_res.json()
    assert detail_data["id"] == session_id
    assert "detections" in detail_data


@pytest.mark.asyncio
async def test_health_endpoint(client: AsyncClient):
    res = await client.get("/health")
    assert res.status_code == 200
    data = res.json()
    assert data["database"] == "healthy"
    assert "model_checkpoint" in data

