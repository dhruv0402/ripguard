import pytest
import xml.etree.ElementTree as ET
import numpy as np
from httpx import AsyncClient

from ml.inference.ptz_controller import PTZController
from ml.inference.cpl_actuator import CPLActuator
from ml.active_learning.domain_adapter import CoastalDomainAdapter, BeachArchetype
from backend.app.services.cad_dispatch import CADDispatcher
from ml.inference.hardware_acceptance import HardwareAcceptanceTester


def test_ptz_controller_dynamic_homography_and_watchdog():
    """Validates dynamic 3D homography rotation and automated return-to-home preset watchdog."""
    H_base = np.array([
        [-0.069, 0.0, 66.6],
        [0.0, 0.066, -85.0],
        [0.0, -0.0029, 1.0],
    ], dtype=np.float32)

    controller = PTZController(
        base_homography_matrix=H_base,
        focal_length_px=850.0,
        home_timeout_sec=5.0,
    )

    # 1. At home preset, dynamic H matches base H
    H_active = controller.compute_dynamic_homography()
    np.testing.assert_allclose(H_active, H_base, rtol=1e-5)
    assert controller.is_at_home_preset is True

    # 2. Pan 15 deg and Zoom 1.5x
    controller.update_ptz_state(pan_delta_deg=15.0, tilt_delta_deg=3.0, zoom_ratio=1.5)
    assert controller.is_at_home_preset is False
    H_moved = controller.compute_dynamic_homography()
    assert H_moved.shape == (3, 3)
    # Confirm homography was modified by the 3D rotation and zoom
    assert not np.allclose(H_moved, H_base)

    # 3. Test watchdog before timeout
    status_early = controller.check_home_preset_watchdog()
    assert status_early["action_taken"] == "NONE"

    # Simulate operator inactivity exceeding 5.0 seconds
    controller.last_operator_action_time -= 6.0
    status_watchdog = controller.check_home_preset_watchdog()
    assert status_watchdog["action_taken"] == "AUTONOMOUS_RETURN_TO_HOME"
    assert controller.is_at_home_preset is True
    assert controller.current_pan_deg == 0.0


def test_cpl_actuator_glint_extinction():
    """Validates Brewster polarizing angle calculation and motorized CPL rotation."""
    actuator = CPLActuator(camera_azimuth_deg=270.0)  # Camera facing West

    # Sun at South-West (azimuth = 225 deg)
    opt_angle = actuator.compute_optimal_cpl_angle(solar_azimuth_deg=225.0)
    assert 0.0 <= opt_angle <= 180.0

    # Test auto glint actuation
    res = actuator.auto_adjust_for_glint(requires_cpl=True, solar_azimuth_deg=225.0)
    assert res["action"] == "ENGAGED_SPECULAR_EXTINCTION"
    assert actuator.is_polarizer_engaged is True

    # Return to neutral when glare cleared
    res_neutral = actuator.auto_adjust_for_glint(requires_cpl=False)
    assert res_neutral["action"] == "RETURN_TO_NEUTRAL"
    assert actuator.current_filter_angle_deg == 0.0


def test_coastal_domain_adapter_archetypes():
    """Validates classification of volcanic black sand and CLAHE contrast enhancement."""
    adapter = CoastalDomainAdapter(shadow_mode_enabled=True)

    # 1. Synthetic Volcanic Black Sand frame (dark overall luminance)
    black_sand_frame = np.full((100, 100, 3), 40, dtype=np.uint8)
    profile = adapter.classify_beach_archetype(black_sand_frame)
    assert profile["archetype"] == BeachArchetype.VOLCANIC_BLACK.value
    assert profile["adapted_confidence_threshold"] == 0.45

    # 2. Frame adaptation via CLAHE
    enhanced = adapter.adapt_frame(black_sand_frame)
    assert enhanced.shape == black_sand_frame.shape

    # 3. Shadow mode evaluation
    harvested = adapter.evaluate_shadow_mode_sample(confidence=0.55, frame_rgb=black_sand_frame)
    assert harvested is True
    assert adapter.harvested_shadow_samples == 1

    # Confident sample (> 0.65) is not flagged as ambiguous shadow candidate
    assert adapter.evaluate_shadow_mode_sample(confidence=0.88, frame_rgb=black_sand_frame) is False


def test_cad_dispatcher_cap_v12_xml_and_dispatch():
    """Validates OASIS Common Alerting Protocol (CAP v1.2) XML schema compliance."""
    dispatcher = CADDispatcher()

    alert_meta = {
        "id": "alert_888",
        "message": "Dangerous 2.4 m/s rip current corridor active near Tower 4.",
        "is_escalated": True,
        "confidence": 0.95,
    }

    cap_xml = dispatcher.generate_cap_v12_xml(
        alert_payload=alert_meta,
        gps_lat=15.5492,
        gps_lon=73.7535,
        radius_meters=60.0,
    )

    # Parse XML and verify OASIS CAP v1.2 tags
    root = ET.fromstring(cap_xml)
    assert "alert" in root.tag
    assert root.find("{urn:oasis:names:tc:emergency:cap:1.2}status").text == "Actual"
    assert root.find("{urn:oasis:names:tc:emergency:cap:1.2}msgType").text == "Alert"

    info = root.find("{urn:oasis:names:tc:emergency:cap:1.2}info")
    assert info.find("{urn:oasis:names:tc:emergency:cap:1.2}category").text == "Safety"
    assert info.find("{urn:oasis:names:tc:emergency:cap:1.2}urgency").text == "Immediate"
    assert info.find("{urn:oasis:names:tc:emergency:cap:1.2}severity").text == "Severe"

    area = info.find("{urn:oasis:names:tc:emergency:cap:1.2}area")
    assert "15.5492" in area.find("{urn:oasis:names:tc:emergency:cap:1.2}circle").text


def test_hardware_acceptance_tester_hat_certificate(tmp_path):
    """Validates automated pre-commissioning Hardware Acceptance Test (HAT) report generation."""
    report_file = str(tmp_path / "TEST_HAT_REPORT.json")
    tester = HardwareAcceptanceTester(output_report_path=report_file)

    cert = tester.generate_full_hat_certificate()
    assert cert["certification"] == "RIPGUARD_EDGE_COMMERCIAL_ACCEPTANCE"
    assert "HAT-ORIN-" in cert["certificate_id"]
    assert cert["hardware_audit"]["audit_passed"] is True
    assert cert["thermal_chamber_certification"]["thermal_throttling_certified"] is True
    assert cert["commercial_deployment_ready"] is True


@pytest.mark.asyncio
async def test_stream_gap_endpoints_e2e(client: AsyncClient):
    """E2E API test for PTZ, CPL, Domain Adapter, CAD dispatch, and HAT certification endpoints."""
    # 0. Auth
    await client.post(
        "/api/auth/signup",
        json={"email": "field_chief@beach.gov", "password": "password123"},
    )
    res_login = await client.post(
        "/api/auth/login",
        data={"username": "field_chief@beach.gov", "password": "password123"},
    )
    token = res_login.json()["access_token"]
    headers = {"Authorization": f"Bearer {token}"}

    # 1. PTZ Move & Status
    res_ptz_move = await client.post(
        "/api/stream/ptz/move",
        json={"pan_delta_deg": 12.0, "tilt_delta_deg": -2.0, "zoom_ratio": 1.2, "reset_to_home": False},
        headers=headers,
    )
    assert res_ptz_move.status_code == 200
    assert res_ptz_move.json()["ptz"]["pan_deg"] == 12.0

    res_ptz_status = await client.get("/api/stream/ptz/status", headers=headers)
    assert res_ptz_status.status_code == 200
    assert res_ptz_status.json()["is_at_home_preset"] is False

    # Reset PTZ to Home
    res_ptz_reset = await client.post(
        "/api/stream/ptz/move",
        json={"reset_to_home": True},
        headers=headers,
    )
    assert res_ptz_reset.status_code == 200

    # 2. CPL Actuator
    res_cpl = await client.post(
        "/api/stream/cpl/actuate",
        json={"auto_glint_extinguish": True, "solar_azimuth_deg": 210.0},
        headers=headers,
    )
    assert res_cpl.status_code == 200
    assert res_cpl.json()["status"] == "actuated"

    res_cpl_status = await client.get("/api/stream/cpl/status", headers=headers)
    assert res_cpl_status.status_code == 200
    assert res_cpl_status.json()["is_engaged"] is True

    # 3. Domain Adapter
    res_domain_cfg = await client.post(
        "/api/stream/domain/configure",
        json={"archetype": "VOLCANIC_BLACK", "shadow_mode": True},
        headers=headers,
    )
    assert res_domain_cfg.status_code == 200
    assert res_domain_cfg.json()["active_archetype"] == "VOLCANIC_BLACK"

    res_domain_status = await client.get("/api/stream/domain/status", headers=headers)
    assert res_domain_status.status_code == 200
    assert res_domain_status.json()["active_archetype"] == "VOLCANIC_BLACK"

    # 4. CAD Dispatch
    res_cad = await client.post(
        "/api/stream/cad/dispatch",
        json={"alert_id": "ALERT_SURF_101", "gps_lat": 15.5492, "gps_lon": 73.7535, "message": "Emergency dispatch"},
        headers=headers,
    )
    assert res_cad.status_code == 200
    assert "CAD-" in res_cad.json()["incident"]["cad_incident_id"]

    res_cad_hist = await client.get("/api/stream/cad/history", headers=headers)
    assert res_cad_hist.status_code == 200
    assert res_cad_hist.json()["count"] >= 1

    # 5. Hardware Acceptance Test Certification
    res_hat = await client.post("/api/stream/hardware/acceptance-test", headers=headers)
    assert res_hat.status_code == 200
    assert res_hat.json()["certificate"]["commercial_deployment_ready"] is True
