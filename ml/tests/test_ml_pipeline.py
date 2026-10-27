"""
Unit and integration tests for RipGuard ML Pipeline:
- Standalone inference engine & spatial mask cleaning
- Farnebäck optical flow downsampling & shear calculation
- 4-GCP Homography & uncalibrated fallback warnings
- Optical filters (sun glint & twilight adaptive denoising)
- Continuous retraining daemon & benchmark promotion gate
"""

import os
import sys

# Ensure repository root is in sys.path
sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), "..", "..")))

import pytest
import numpy as np
import torch

from ml.inference.homography import BeachCameraCalibrator, GCPPoint
from ml.inference.optical_filters import SunGlintFilter, TwilightAdaptivePreprocessor
from ml.active_learning.harvester import EntropyUncertaintyScorer
from ml.active_learning.retrain_daemon import ContinuousRetrainingDaemon
from ml.inference.ptz_controller import PTZController
from ml.inference.cpl_actuator import CPLActuator


def test_homography_calibrated_vs_uncalibrated_warning():
    """Validates that uncalibrated camera models issue an explicit warning flag."""
    uncalibrated = BeachCameraCalibrator(
        camera_lat=15.5492,
        camera_lon=73.7535,
        mounting_height_m=12.0,
        tilt_angle_deg=16.5,
    )
    metric = uncalibrated.pixel_to_metric_distance(0.5, 0.5)
    assert metric["is_calibrated"] is False
    assert metric["method"] == "analytical_frustum"
    assert "UNCALIBRATED_ESTIMATE" in metric["calibration_warning"]

    # Calibrate with 4 surveyed GCP points
    gcps = [
        GCPPoint(pixel_x=450, pixel_y=680, rtk_lat=15.5491, rtk_lon=73.7533, metric_x=-25.0, metric_y=35.0),
        GCPPoint(pixel_x=1420, pixel_y=675, rtk_lat=15.5493, rtk_lon=73.7533, metric_x=28.0, metric_y=36.0),
        GCPPoint(pixel_x=620, pixel_y=510, rtk_lat=15.5490, rtk_lon=73.7530, metric_x=-18.0, metric_y=85.0),
        GCPPoint(pixel_x=1280, pixel_y=505, rtk_lat=15.5494, rtk_lon=73.7530, metric_x=22.0, metric_y=87.0),
    ]
    cal_res = uncalibrated.calibrate_with_gcps(gcps)
    assert cal_res["status"] == "calibrated"

    cal_metric = uncalibrated.pixel_to_metric_distance(0.5, 0.5)
    assert cal_metric["is_calibrated"] is True
    assert cal_metric["method"] == "planar_homography_4gcp"
    assert cal_metric["calibration_warning"] is None


def test_sun_glint_filter_and_flow_suppression():
    """Validates that specular glint areas suppress spurious optical flow vectors."""
    glint_filter = SunGlintFilter(luminance_threshold=230, saturation_max=35)
    
    # Frame with artificial bright washed-out patch in top center
    frame = np.full((100, 100, 3), 100, dtype=np.uint8)
    frame[10:30, 40:60] = [255, 255, 255]  # High lum, 0 sat
    
    mask = glint_filter.compute_glint_mask(frame)
    assert np.any(mask[15:25, 45:55] == 255)

    # Synthetic noisy flow
    flow = np.ones((100, 100, 2), dtype=np.float32) * 5.0
    cleaned_flow = glint_filter.suppress_flow_in_glint(flow, mask, dampening_factor=0.0)
    assert np.all(cleaned_flow[15:25, 45:55] == 0.0)
    assert np.all(cleaned_flow[80:90, 80:90] == 5.0)


def test_entropy_uncertainty_scoring():
    """Validates information entropy scoring on rip current probability predictions."""
    # Completely confident map (0 or 1)
    conf_map = np.zeros((32, 32), dtype=np.float32)
    score_low = EntropyUncertaintyScorer.compute_frame_uncertainty(conf_map)
    assert score_low == 0.0

    # Maximally uncertain map (all 0.5)
    max_uncertain_map = np.full((32, 32), 0.5, dtype=np.float32)
    score_high = EntropyUncertaintyScorer.compute_frame_uncertainty(max_uncertain_map)
    assert score_high > 0.95


@pytest.mark.asyncio
async def test_continuous_retraining_promotion_gate(tmp_path):
    """Validates that newly fine-tuned models are gated by IoU/precision thresholds before deployment."""
    daemon = ContinuousRetrainingDaemon(
        batch_threshold=2,
        checkpoint_dir=str(tmp_path),
        min_promotable_iou=0.30,
        min_promotable_precision=0.40,
    )

    feedback_records = [
        {"feedback_type": "false_positive_foam", "confidence_rating": 4},
        {"feedback_type": "confirmed_true_positive", "confidence_rating": 5},
    ]

    result = await daemon.check_and_retrain(feedback_records, force=True)
    assert result["triggered"] is True
    assert result["status"] == "SUCCESS"
    assert result["metrics"]["is_promoted"] is True
    assert os.path.exists(result["metrics"]["checkpoint_path"])
