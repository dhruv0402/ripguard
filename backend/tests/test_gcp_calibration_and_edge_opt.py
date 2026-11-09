import pytest
import numpy as np
from httpx import AsyncClient
from ml.inference.homography import BeachCameraCalibrator, GCPPoint
from ml.inference.edge_optimizer import EdgeOptimizer
from app.api import stream as stream_api


def test_4gcp_planar_homography_and_extrinsics_calibration():
    """
    Validates that 4 ground control points (GCPs) surveyed with RTK GPS:
      1. Correctly solve the 3x3 planar homography matrix H.
      2. Yield sub-meter reprojection RMSE.
      3. Accurately calibrate mounting height (h) and tilt angle (theta).
    """
    calibrator = BeachCameraCalibrator(
        camera_lat=15.5492,
        camera_lon=73.7535,
        mounting_height_m=12.0,
        tilt_angle_deg=16.5,
        azimuth_deg=270.0,
        focal_length_px=850.0,
    )

    # 4 Surveyed beach GCPs: (pixel_x, pixel_y) -> (alongshore X, offshore Y)
    gcps = [
        {"label": "GCP-1_Near_Left", "pixel_x": 480, "pixel_y": 900, "rtk_lat": 15.5492, "rtk_lon": 73.7533, "metric_x": -20.0, "metric_y": 15.0},
        {"label": "GCP-2_Near_Right", "pixel_x": 1440, "pixel_y": 900, "rtk_lat": 15.5492, "rtk_lon": 73.7533, "metric_x": 20.0, "metric_y": 15.0},
        {"label": "GCP-3_Far_Right", "pixel_x": 1200, "pixel_y": 650, "rtk_lat": 15.5492, "rtk_lon": 73.7529, "metric_x": 18.0, "metric_y": 45.0},
        {"label": "GCP-4_Far_Left", "pixel_x": 720, "pixel_y": 650, "rtk_lat": 15.5492, "rtk_lon": 73.7529, "metric_x": -18.0, "metric_y": 45.0},
    ]

    result = calibrator.calibrate_with_gcps(gcps)

    assert result["status"] == "calibrated"
    assert result["gcp_count"] == 4
    assert result["reprojection_rmse_m"] <= 0.5  # Sub-meter accuracy
    assert result["certified_for_field_trials"] is True
    assert calibrator.calibrated_from_gcps is True
    assert calibrator.homography_matrix is not None
    assert calibrator.homography_matrix.shape == (3, 3)

    # Validate physical extrinsics were optimized
    assert 2.0 <= calibrator.height <= 50.0
    assert 3.0 <= calibrator.tilt_deg <= 85.0

    # Project mid-point on the beach
    pt = calibrator.pixel_to_metric_distance(norm_x=960 / 1920, norm_y=775 / 1080)
    assert pt["method"] == "planar_homography_4gcp"
    assert abs(pt["lateral_offset_m"]) < 2.0  # Center of alongshore baseline
    assert 20.0 <= pt["offshore_distance_m"] <= 35.0

    # Test serialization & deserialization
    cal_dict = calibrator.to_dict()
    restored = BeachCameraCalibrator.from_dict(cal_dict)
    assert restored.calibrated_from_gcps is True
    assert restored.reprojection_rmse_m == calibrator.reprojection_rmse_m
    np.testing.assert_allclose(restored.homography_matrix, calibrator.homography_matrix, rtol=1e-5)


def test_4gcp_calibration_insufficient_points_rejection():
    """Confirms error when fewer than 4 GCP points are provided."""
    calibrator = BeachCameraCalibrator()
    insufficient_gcps = [
        {"pixel_x": 100, "pixel_y": 200, "rtk_lat": 15.5, "rtk_lon": 73.7},
        {"pixel_x": 300, "pixel_y": 400, "rtk_lat": 15.5, "rtk_lon": 73.7},
    ]
    with pytest.raises(ValueError, match="At least 4 Ground Control Points"):
        calibrator.calibrate_with_gcps(insufficient_gcps)


def test_edge_optimizer_missing_checkpoint_is_not_certified(tmp_path):
    optimizer = EdgeOptimizer(onnx_path=str(tmp_path / "missing.onnx"))
    for result in (optimizer.compile_onnx_to_tensorrt(), optimizer.benchmark_edge_throughput()):
        assert result["status"] == "UNAVAILABLE"
        assert result["power_consumption_w"] is None
        assert result["sub_20w_certified"] is False
        assert result["field_trial_ready"] is False


@pytest.mark.asyncio
async def test_stream_calibration_and_hardware_endpoints(client: AsyncClient, monkeypatch, tmp_path):
    """
    E2E integration test for /api/stream/calibration, /api/stream/calibration/project,
    and /api/stream/hardware endpoints.
    """
    # 0. Sign up and authenticate operator
    await client.post(
        "/api/auth/signup",
        json={"email": "cal_op@beach.gov", "password": "password123"},
    )
    res_login = await client.post(
        "/api/auth/login",
        data={"username": "cal_op@beach.gov", "password": "password123"},
    )
    token = res_login.json()["access_token"]
    headers = {"Authorization": f"Bearer {token}"}

    # 1. GET initial calibration
    res_get = await client.get("/api/stream/calibration?source=tower-1", headers=headers)
    assert res_get.status_code == 200
    data = res_get.json()
    assert "mounting_height_m" in data
    assert "tilt_angle_deg" in data

    # 2. POST 4-GCP calibration
    gcps = [
        {"label": "GCP-1", "pixel_x": 480, "pixel_y": 900, "rtk_lat": 15.5492, "rtk_lon": 73.7533, "metric_x": -20.0, "metric_y": 15.0},
        {"label": "GCP-2", "pixel_x": 1440, "pixel_y": 900, "rtk_lat": 15.5492, "rtk_lon": 73.7533, "metric_x": 20.0, "metric_y": 15.0},
        {"label": "GCP-3", "pixel_x": 1200, "pixel_y": 650, "rtk_lat": 15.5492, "rtk_lon": 73.7529, "metric_x": 18.0, "metric_y": 45.0},
        {"label": "GCP-4", "pixel_x": 720, "pixel_y": 650, "rtk_lat": 15.5492, "rtk_lon": 73.7529, "metric_x": -18.0, "metric_y": 45.0},
    ]
    payload = {
        "source": "tower-1",
        "camera_lat": 15.5492,
        "camera_lon": 73.7535,
        "mounting_height_m": 12.0,
        "tilt_angle_deg": 16.5,
        "gcps": gcps,
    }

    res_cal = await client.post("/api/stream/calibration", json=payload, headers=headers)
    assert res_cal.status_code == 200
    cal_data = res_cal.json()
    assert cal_data["status"] == "calibrated"
    assert cal_data["calibration"]["calibrated_from_gcps"] is True
    assert cal_data["calibration"]["reprojection_rmse_m"] is not None

    # 3. Test projection endpoint
    res_proj = await client.post(
        "/api/stream/calibration/project",
        json={"source": "tower-1", "pixel_x": 960, "pixel_y": 775, "img_w": 1920, "img_h": 1080},
        headers=headers,
    )
    assert res_proj.status_code == 200
    proj_data = res_proj.json()
    assert proj_data["method"] == "planar_homography_4gcp"
    assert "offshore_distance_m" in proj_data
    assert "gps" in proj_data
    assert "lat" in proj_data["gps"]
    assert "lon" in proj_data["gps"]

    # 4. Test insufficient GCP rejection (3 points)
    res_fail = await client.post(
        "/api/stream/calibration",
        json={"source": "tower-1", "gcps": gcps[:3]},
        headers=headers,
    )
    assert res_fail.status_code == 400
    assert "At least 4 Ground Control Points" in res_fail.json()["detail"]

    # 5. Missing weights are visible, not a successful hardware certification.
    monkeypatch.setattr(stream_api, "EdgeOptimizer", lambda: EdgeOptimizer(
        onnx_path=str(tmp_path / "missing.onnx")
    ))
    res_hw = await client.get("/api/stream/hardware", headers=headers)
    assert res_hw.status_code == 200
    hw_data = res_hw.json()
    assert hw_data["status"] == "unavailable"
    assert "Jetson Orin" in hw_data["target_node"]
    assert hw_data["precision"] is None
    assert hw_data["target_precision"] == "TensorRT FP16"
    assert hw_data["target_fps"] == 30.0
    assert hw_data["power_mode"] is None
    assert hw_data["target_power_budget_w"] == 20.0
    assert hw_data["benchmark"]["field_trial_ready"] is False

    # 6. DELETE calibration reset
    res_del = await client.delete("/api/stream/calibration?source=tower-1", headers=headers)
    assert res_del.status_code == 200
    assert res_del.json()["status"] == "reset"
