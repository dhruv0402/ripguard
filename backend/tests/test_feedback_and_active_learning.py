import pytest
import numpy as np
from httpx import AsyncClient
from app.main import app
from ml.active_learning.harvester import EntropyUncertaintyScorer, ActiveLearningHarvester


@pytest.mark.asyncio
async def test_entropy_uncertainty_scorer():
    # Certain map (all 0 or 1) -> ~0 entropy
    certain_map = np.zeros((10, 10), dtype=np.float32)
    assert EntropyUncertaintyScorer.compute_frame_uncertainty(certain_map) == 0.0

    # Uncertain map (all 0.5) -> high entropy (close to 1.0)
    uncertain_map = np.full((10, 10), 0.5, dtype=np.float32)
    entropy = EntropyUncertaintyScorer.compute_frame_uncertainty(uncertain_map)
    assert entropy > 0.95


@pytest.mark.asyncio
async def test_operator_feedback_and_active_learning(client: AsyncClient):
    # Signup and login to get auth token
    await client.post(
        "/api/auth/signup",
        json={"email": "lifeguard_lead@beach.gov", "password": "securepassword123"},
    )
    login_res = await client.post(
        "/api/auth/login",
        data={"username": "lifeguard_lead@beach.gov", "password": "securepassword123"},
    )
    assert login_res.status_code == 200

    token = login_res.json()["access_token"]
    token_headers = {"Authorization": f"Bearer {token}"}

    import io
    fake_video_content = b"\x00\x00\x00\x18ftypmp42\x00\x00\x00\x00mp42mp41"
    files = {"file": ("beach_rip_014.mp4", io.BytesIO(fake_video_content), "video/mp4")}
    data = {"location_label": "RipVIS Sector 14"}

    # Create a test session
    upload_resp = await client.post(
        "/api/sessions",
        headers=token_headers,
        files=files,
        data=data,
    )
    assert upload_resp.status_code == 201
    session_id = upload_resp.json()["id"]


    # Submit feedback: Confirmed True Positive
    fb_resp1 = await client.post(
        f"/api/sessions/{session_id}/feedback",
        headers=token_headers,
        json={
            "feedback_type": "confirmed_true_positive",
            "confidence_rating": 5,
            "operator_notes": "Lifeguard verified: strong seaward rip channel observed.",
        },
    )
    assert fb_resp1.status_code == 201
    fb1_data = fb_resp1.json()
    assert fb1_data["feedback_type"] == "confirmed_true_positive"
    assert fb1_data["confidence_rating"] == 5

    # Submit feedback: False Positive (Boat wake)
    fb_resp2 = await client.post(
        f"/api/sessions/{session_id}/feedback",
        headers=token_headers,
        json={
            "feedback_type": "false_positive_wake",
            "confidence_rating": 4,
            "operator_notes": "Jet ski wake churn mistaken for rip current channel.",
            "corrected_region": {"x": 0.2, "y": 0.4, "w": 0.1, "h": 0.2},
        },
    )
    assert fb_resp2.status_code == 201
    fb2_data = fb_resp2.json()
    assert fb2_data["feedback_type"] == "false_positive_wake"

    # List feedback for session
    list_fb = await client.get(
        f"/api/sessions/{session_id}/feedback",
        headers=token_headers,
    )
    assert list_fb.status_code == 200
    feedbacks = list_fb.json()
    assert len(feedbacks) == 2

    # Check get_session includes feedback
    sess_resp = await client.get(
        f"/api/sessions/{session_id}",
        headers=token_headers,
    )
    assert sess_resp.status_code == 200
    session_data = sess_resp.json()
    assert len(session_data["feedback"]) == 2

    # Export active learning manifest
    manifest_resp = await client.get(
        f"/api/sessions/{session_id}/active-learning-manifest",
        headers=token_headers,
    )
    assert manifest_resp.status_code == 200
    manifest = manifest_resp.json()
    assert manifest["summary"]["total_hard_negatives"] == 1
    assert manifest["summary"]["total_confirmed_positives"] == 1
    assert manifest["summary"]["retraining_ready"] is True
    assert len(manifest["hard_negatives"]) == 1
    assert manifest["hard_negatives"][0]["feedback_type"] == "false_positive_wake"
