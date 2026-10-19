import pytest
import asyncio
from httpx import AsyncClient
from app.services.stream_service import LiveStreamManager, StreamStatus
from ml.active_learning.retrain_daemon import ContinuousRetrainingDaemon
from ml.inference.homography import BeachCameraCalibrator
from app.services.alert_service import AlertDispatcher
from app.services.task_queue import create_job_queue, BaseInferenceQueue


@pytest.mark.asyncio
async def test_camera_homography_calibrator():
    calibrator = BeachCameraCalibrator(
        camera_lat=15.5492,
        camera_lon=73.7535,
        mounting_height_m=12.0,
        tilt_angle_deg=18.0,
        azimuth_deg=270.0,  # Facing West
        focal_length_px=800.0,
    )

    # Centroid at center-bottom of screen (close to shore)
    close_shore = calibrator.pixel_to_metric_distance(norm_x=0.5, norm_y=0.9)
    assert close_shore["offshore_distance_m"] > 0
    assert close_shore["offshore_distance_m"] < 50.0  # Under 50m offshore

    # Centroid at upper-middle of screen (far offshore)
    far_offshore = calibrator.pixel_to_metric_distance(norm_x=0.5, norm_y=0.3)
    assert far_offshore["offshore_distance_m"] > close_shore["offshore_distance_m"]

    # Test GPS transformation
    lat, lon = calibrator.metric_to_gps(
        offshore_distance_m=close_shore["offshore_distance_m"],
        lateral_offset_m=close_shore["lateral_offset_m"],
    )
    assert isinstance(lat, float)
    assert isinstance(lon, float)
    # Since camera is facing 270 deg (West), offshore distance moves longitude westward (< 73.7535)
    assert lon <= 73.7535

    # Test physical drift velocity calculation (px/s -> m/s)
    speed_ms = calibrator.calculate_physical_drift_speed(pixel_velocity_y_per_sec=15.0, norm_y=0.6)
    assert 0.2 <= speed_ms <= 3.5


@pytest.mark.asyncio
async def test_continuous_retraining_daemon():
    daemon = ContinuousRetrainingDaemon(batch_threshold=3, checkpoint_dir="ml/checkpoints")

    # 1. Below threshold: should not trigger
    sparse_feedback = [
        {"id": "fb-1", "feedback_type": "false_positive_wake"},
    ]
    res1 = await daemon.check_and_retrain(sparse_feedback, force=False)
    assert res1["triggered"] is False
    assert res1["pending_count"] == 1

    # 2. At or above threshold: triggers fine-tuning
    full_feedback = [
        {"id": "fb-1", "feedback_type": "false_positive_wake"},
        {"id": "fb-2", "feedback_type": "false_positive_sandbar"},
        {"id": "fb-3", "feedback_type": "confirmed_true_positive"},
    ]
    res2 = await daemon.check_and_retrain(full_feedback, force=False)
    assert res2["triggered"] is True
    assert res2["status"] == "SUCCESS"
    assert "metrics" in res2
    assert res2["metrics"]["hard_negatives_harvested"] == 2
    assert res2["metrics"]["confirmed_positives_harvested"] == 1
    assert res2["metrics"]["val_iou"] > 0.3211

    # Check status method
    status_data = daemon.get_status()
    assert status_data["total_retrains_completed"] >= 1
    assert status_data["status"] == "SUCCESS"


@pytest.mark.asyncio
async def test_lifeguard_alert_dispatcher_escalation():
    dispatcher = AlertDispatcher(
        sustained_seconds_threshold=1.0,
        critical_escalation_seconds=3.0,
        cooldown_seconds=0.1,
    )
    dispatcher.register_sms_recipient("+919876543210")
    dispatcher.set_siren_relay("http://mock-siren.local/relay")

    meta_high = {"confidence": 0.88, "risk_level": "HIGH"}

    # Time 0: First high risk observation (starts timer)
    alert1 = dispatcher.process_telemetry(meta_high)
    assert alert1 is None  # Below 1.0s threshold

    # Wait 1.1s: crosses sustained threshold
    await asyncio.sleep(1.1)
    alert2 = dispatcher.process_telemetry(meta_high)
    assert alert2 is not None
    assert alert2["priority"] == "CRITICAL"
    assert alert2["is_escalated"] is False
    assert "sms" in alert2["channels_notified"]

    # Wait another 2.1s (total > 3.0s): crosses critical escalation threshold
    await asyncio.sleep(2.1)
    alert3 = dispatcher.process_telemetry(meta_high)
    assert alert3 is not None
    assert alert3["is_escalated"] is True
    assert alert3["priority"] == "ESCALATED_LIFE_SAFETY"


@pytest.mark.asyncio
async def test_stream_watchdog_state_machine():
    # Test on valid asset
    manager = LiveStreamManager(stream_source="test_assets/beach_ripvis_072.mp4")
    assert manager.stream_status == StreamStatus.INITIALIZING
    await manager.start()
    assert manager.is_running is True

    # Allow loop to start
    await asyncio.sleep(0.1)
    assert manager.stream_status in (StreamStatus.INITIALIZING, StreamStatus.STREAMING)

    manager.stop()
    assert manager.stream_status == StreamStatus.OFFLINE
    assert manager.is_running is False


@pytest.mark.asyncio
async def test_pluggable_task_queue():
    local_q = create_job_queue(max_workers=3)
    assert isinstance(local_q, BaseInferenceQueue)
    assert local_q.queue_depth == 0

    distributed_q = create_job_queue(max_workers=2, redis_url="redis://localhost:6379/0")
    assert isinstance(distributed_q, BaseInferenceQueue)
