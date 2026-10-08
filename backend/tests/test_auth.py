import pytest


@pytest.mark.asyncio
async def test_signup_and_login(client):
    signup = await client.post("/api/auth/signup", json={"email": "a@test.com", "password": "pass12345"})
    assert signup.status_code == 201

    login = await client.post("/api/auth/login", data={"username": "a@test.com", "password": "pass12345"})
    assert login.status_code == 200
    assert "access_token" in login.json()


@pytest.mark.asyncio
async def test_sessions_require_auth(client):
    response = await client.get("/api/sessions")
    assert response.status_code == 401


@pytest.mark.asyncio
async def test_benchmark_endpoint_is_public(client):
    response = await client.get("/api/benchmark")
    assert response.status_code == 200
    assert response.json() == []
