import pytest
import numpy as np
from httpx import AsyncClient
from ml.inference.tide_compensator import TidalCompensator
from ml.inference.optical_filters import SunGlintFilter, TwilightAdaptivePreprocessor
from ml.inference.thermal_governor import JetsonThermalGovernor, ThermalState
from ml.inference.homography import BeachCameraCalibrator
from app.core.maritime_compliance import (
    MaritimeComplianceGuard,
    ClearanceAction,
    STATUTORY_MARITIME_DISCLAIMER,
)


def test_tidal_compensator_modulation():
    """Validates harmonic tidal height calculation and dynamic camera elevation adjustment."""
    compensator = TidalCompensator(base_mounting_height_m=12.0, tidal_range_m=2.0)

    # 1. Test harmonic computation at peak high tide vs low tide
    # At t=0, cos(0) = 1 -> peak tide = +1.0m
    tide_high = compensator.compute_harmonic_tide_height(epoch_time=0.0)
    assert abs(tide_high - 1.0) < 0.05

    # At t = 12.42h / 2 = 6.21h, cos(pi) = -1 -> low tide = -1.0m
    tide_low = compensator.compute_harmonic_tide_height(epoch_time=6.2103 * 3600.0)
    assert abs(tide_low - (-1.0)) < 0.05

    # 2. Test effective camera height
    eff_high = compensator.get_effective_camera_height(epoch_time=0.0)
    assert eff_high["effective_camera_height_m"] == 11.0  # 12m - 1m = 11m

    eff_low = compensator.get_effective_camera_height(epoch_time=6.2103 * 3600.0)
    assert eff_low["effective_camera_height_m"] == 13.0  # 12m - (-1m) = 13m

    # 3. Test manual override
    compensator.set_manual_override(1.8)
    manual_eff = compensator.get_effective_camera_height()
    assert manual_eff["effective_camera_height_m"] == 10.2
    assert manual_eff["tide_source"] == "manual_override"

    # 4. Verify effect on BeachCameraCalibrator
    calibrator = BeachCameraCalibrator(mounting_height_m=12.0, tilt_angle_deg=18.0)
    dist_base = calibrator.pixel_to_metric_distance(0.5, 0.6)["offshore_distance_m"]

    # When high tide raises water level by +2.0m, effective height drops to 10.0m
    calibrator.set_active_tide_delta(2.0)
    assert calibrator.effective_height == 10.0
    dist_tide = calibrator.pixel_to_metric_distance(0.5, 0.6)["offshore_distance_m"]
    assert dist_tide < dist_base  # Shorter vertical baseline yields adjusted offshore projection


def test_optical_glint_and_twilight_filters():
    """Validates sun glint specular flare detection and twilight adaptive preprocessing."""
    glint_filter = SunGlintFilter(luminance_threshold=235, saturation_max=40)

    # 1. Create synthetic frame with central specular sun flare
    bgr_frame = np.full((100, 100, 3), 120, dtype=np.uint8)  # Ocean water baseline
    bgr_frame[40:60, 40:60] = [250, 250, 250]  # Specular white sun glint flare

    glint_mask = glint_filter.compute_glint_mask(bgr_frame)
    assert np.count_nonzero(glint_mask) > 0

    # 2. Test optical flow suppression in glint region
    dummy_flow = np.ones((100, 100, 2), dtype=np.float32) * 10.0
    dampened_flow = glint_filter.suppress_flow_in_glint(dummy_flow, glint_mask, dampening_factor=0.0)
    assert np.all(dampened_flow[45:55, 45:55] == 0.0)
    assert np.all(dampened_flow[10:20, 10:20] == 10.0)

    # 3. Test Twilight Adaptive Preprocessor
    twilight_prep = TwilightAdaptivePreprocessor()
    bright_frame = np.full((100, 100, 3), 180, dtype=np.uint8)
    day_analysis = twilight_prep.analyze_scene_lighting(bright_frame)
    assert day_analysis["is_twilight"] is False
    assert day_analysis["sensor_mode"] == "DAYLIGHT_STANDARD"

    dark_frame = np.full((100, 100, 3), 35, dtype=np.uint8)
    dusk_analysis = twilight_prep.analyze_scene_lighting(dark_frame)
    assert dusk_analysis["is_twilight"] is True
    assert dusk_analysis["sensor_mode"] == "TWILIGHT_DENOISING_ACTIVE"


def test_jetson_thermal_governor_state_machine():
    """Validates multi-tier Jetson Orin thermal governance and dynamic frame rate throttling."""
    governor = JetsonThermalGovernor()

    # NOMINAL State (< 65°C)
    governor.set_simulation_temperature(55.0)
    res_nom = governor.evaluate_thermal_state()
    assert res_nom["thermal_state"] == ThermalState.NOMINAL.value
    assert res_nom["frame_skip_factor"] == 1
    assert res_nom["target_fps"] == 30.0

    # ELEVATED State (65°C - 75°C)
    governor.set_simulation_temperature(70.0)
    res_elev = governor.evaluate_thermal_state()
    assert res_elev["thermal_state"] == ThermalState.ELEVATED.value
    assert res_elev["frame_skip_factor"] == 1

    # THROTTLED State (75°C - 82°C) -> 2x Frame Skip (15 FPS)
    governor.set_simulation_temperature(78.0)
    res_throt = governor.evaluate_thermal_state()
    assert res_throt["thermal_state"] == ThermalState.THROTTLED.value
    assert res_throt["frame_skip_factor"] == 2
    assert res_throt["target_fps"] == 15.0

    # CRITICAL State (>= 82°C) -> Emergency 4x Frame Skip (7.5 FPS)
    governor.set_simulation_temperature(83.5)
    res_crit = governor.evaluate_thermal_state()
    assert res_crit["thermal_state"] == ThermalState.CRITICAL.value
    assert res_crit["frame_skip_factor"] == 4
    assert res_crit["target_fps"] == 7.5
    assert res_crit["hardware_shutdown_margin_c"] < 3.0


def test_maritime_compliance_guard():
    """Validates Human-in-the-Loop clearance, tamper-evident audit trail, and statutory disclaimers."""
    guard = MaritimeComplianceGuard()

    # 1. Statutory disclaimer injection
    raw_alert = {"id": "alert_test", "risk": "HIGH"}
    enriched = guard.inject_compliance_metadata(raw_alert)
    assert "maritime_compliance" in enriched
    assert enriched["maritime_compliance"]["requires_human_clearance"] is True
    assert STATUTORY_MARITIME_DISCLAIMER in enriched["maritime_compliance"]["statutory_disclaimer"]

    # 2. Operator clearance recording
    entry = guard.record_operator_clearance(
        alert_id="alert_test",
        user_id="user_guard_123",
        user_email="lifeguard@beach.gov",
        action=ClearanceAction.CONFIRMED_DISPATCH,
        operator_notes="Visual confirmation: swimmers trapped in north groin rip neck. Dispatched IRB.",
    )
    assert entry["action"] == "CONFIRMED_DISPATCH"
    assert entry["alert_id"] == "alert_test"
    assert len(guard.audit_log) == 1

    # 3. Audit trail retrieval
    trail = guard.get_audit_trail()
    assert len(trail) == 1
    assert trail[0]["operator_email"] == "lifeguard@beach.gov"


@pytest.mark.asyncio
async def test_environmental_and_compliance_endpoints(client: AsyncClient):
    """E2E API test for environmental conditions and maritime compliance endpoints."""
    # 0. Auth setup
    await client.post(
        "/api/auth/signup",
        json={"email": "maritime_officer@beach.gov", "password": "password123"},
    )
    res_login = await client.post(
        "/api/auth/login",
        data={"username": "maritime_officer@beach.gov", "password": "password123"},
    )
    token = res_login.json()["access_token"]
    headers = {"Authorization": f"Bearer {token}"}

    # 1. GET environmental status
    res_env = await client.get("/api/stream/environmental", headers=headers)
    assert res_env.status_code == 200
    env_data = res_env.json()
    assert "tidal_modulation" in env_data
    assert "thermal_governance" in env_data
    assert "optical_filters" in env_data

    # 2. POST update tide
    res_tide = await client.post(
        "/api/stream/environmental/tide",
        json={"water_level_m": 1.4, "station_id": "9410230"},
        headers=headers,
    )
    assert res_tide.status_code == 200
    assert res_tide.json()["status"] == "updated"
    assert res_tide.json()["tide"]["water_level_delta_m"] == 1.4

    # 3. POST operator clearance
    clearance_payload = {
        "alert_id": "alert_9999",
        "action": "CONFIRMED_DISPATCH",
        "notes": "Verified by tower 4 lifeguard.",
    }
    res_clr = await client.post(
        "/api/stream/compliance/clearance",
        json=clearance_payload,
        headers=headers,
    )
    assert res_clr.status_code == 200
    assert res_clr.json()["status"] == "clearance_recorded"
    assert res_clr.json()["entry"]["action"] == "CONFIRMED_DISPATCH"

    # 4. GET audit trail
    res_audit = await client.get("/api/stream/compliance/audit-trail", headers=headers)
    assert res_audit.status_code == 200
    audit_data = res_audit.json()
    assert audit_data["count"] >= 1
    assert "STATUTORY DISCLAIMER" in audit_data["statutory_disclaimer"]
