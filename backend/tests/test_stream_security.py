import pytest
from httpx import AsyncClient


@pytest.mark.asyncio
async def test_stream_unauthenticated_endpoints(client: AsyncClient):
    # All stream endpoints must reject unauthenticated requests with 401
    res_feed = await client.get("/api/stream/feed")
    assert res_feed.status_code == 401

    res_status = await client.get("/api/stream/status")
    assert res_status.status_code == 401

    res_alerts = await client.get("/api/stream/alerts")
    assert res_alerts.status_code == 401

    res_webhook = await client.post("/api/stream/alerts/webhook?url=https://example.com/hook")
    assert res_webhook.status_code == 401


@pytest.mark.asyncio
async def test_stream_authenticated_and_input_validation(client: AsyncClient):
    # 1. Login operator
    await client.post(
        "/api/auth/signup",
        json={"email": "stream_op@beach.gov", "password": "password123"},
    )
    res_login = await client.post(
        "/api/auth/login",
        data={"username": "stream_op@beach.gov", "password": "password123"},
    )
    token = res_login.json()["access_token"]
    headers = {"Authorization": f"Bearer {token}"}

    # 2. Status check with auth
    res_status = await client.get("/api/stream/status", headers=headers)
    assert res_status.status_code == 200
    assert "status" in res_status.json()

    # 3. Path traversal / SSRF rejection on feed
    res_traversal = await client.get("/api/stream/feed?source=../../etc/passwd", headers=headers)
    assert res_traversal.status_code == 400
    assert "Invalid stream source" in res_traversal.json()["detail"]

    # 4. Webhook URL validation
    res_bad_hook = await client.post("/api/stream/alerts/webhook?url=javascript:alert(1)", headers=headers)
    assert res_bad_hook.status_code == 400

    res_good_hook = await client.post("/api/stream/alerts/webhook?url=https://hooks.slack.com/services/XYZ", headers=headers)
    assert res_good_hook.status_code == 200
    assert res_good_hook.json()["status"] == "registered"

    # 5. Alerts history check
    res_alerts = await client.get("/api/stream/alerts", headers=headers)
    assert res_alerts.status_code == 200
    assert "alerts" in res_alerts.json()
