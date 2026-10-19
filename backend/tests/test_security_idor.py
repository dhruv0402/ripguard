import pytest
import io
import os
import uuid
from httpx import AsyncClient

from app.models.session import AnalysisSession, SessionStatus
from tests.conftest import TestSessionLocal


@pytest.mark.asyncio
async def test_session_video_idor_protection(client: AsyncClient):
    # 1. Create User A
    res_a = await client.post(
        "/api/auth/signup",
        json={"email": "usera@beach.gov", "password": "password123"},
    )
    assert res_a.status_code == 201
    user_a_id = uuid.UUID(res_a.json()["id"])

    res_login_a = await client.post(
        "/api/auth/login",
        data={"username": "usera@beach.gov", "password": "password123"},
    )
    token_a = res_login_a.json()["access_token"]
    headers_a = {"Authorization": f"Bearer {token_a}"}

    # 2. Create User B
    res_b = await client.post(
        "/api/auth/signup",
        json={"email": "userb@beach.gov", "password": "password123"},
    )
    assert res_b.status_code == 201

    res_login_b = await client.post(
        "/api/auth/login",
        data={"username": "userb@beach.gov", "password": "password123"},
    )
    token_b = res_login_b.json()["access_token"]
    headers_b = {"Authorization": f"Bearer {token_b}"}

    # 3. Create a dummy session owned by User A with a real dummy file
    session_id = uuid.uuid4()
    dummy_video_path = f"storage/uploads/test_{session_id}.mp4"
    os.makedirs("storage/uploads", exist_ok=True)
    with open(dummy_video_path, "wb") as f:
        f.write(b"fake video data")

    try:
        async with TestSessionLocal() as db:
            session = AnalysisSession(
                id=session_id,
                owner_id=user_a_id,
                filename="beach_patrol.mp4",
                storage_path=dummy_video_path,
                annotated_video_path=dummy_video_path,
                status=SessionStatus.DONE,
            )
            db.add(session)
            await db.commit()

        # 4. Unauthenticated access must be rejected with 401
        unauth_res = await client.get(f"/api/sessions/{session_id}/video")
        assert unauth_res.status_code == 401

        # 5. User B accessing User A's session must be rejected with 404 (IDOR blocked)
        idor_res = await client.get(f"/api/sessions/{session_id}/video", headers=headers_b)
        assert idor_res.status_code == 404

        # 6. User B query token attempt with User B token must also be rejected
        idor_query_res = await client.get(f"/api/sessions/{session_id}/video?token={token_b}")
        assert idor_query_res.status_code == 404

        # 7. User A accessing their own video with header must succeed
        owner_res = await client.get(f"/api/sessions/{session_id}/video", headers=headers_a)
        assert owner_res.status_code == 200
        assert owner_res.content == b"fake video data"

        # 8. User A accessing their own video with query token (?token=...) must succeed
        owner_query_res = await client.get(f"/api/sessions/{session_id}/video?token={token_a}")
        assert owner_query_res.status_code == 200
        assert owner_query_res.content == b"fake video data"

        # 9. Verify telemetry and live feed IDOR protection
        unauth_telem = await client.get(f"/api/sessions/{session_id}/live-telemetry")
        assert unauth_telem.status_code == 401

        idor_telem = await client.get(f"/api/sessions/{session_id}/live-telemetry", headers=headers_b)
        assert idor_telem.status_code == 404

        owner_telem = await client.get(f"/api/sessions/{session_id}/live-telemetry", headers=headers_a)
        assert owner_telem.status_code == 200

    finally:
        if os.path.exists(dummy_video_path):
            os.remove(dummy_video_path)
