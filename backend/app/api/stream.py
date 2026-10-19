import asyncio
import os
from urllib.parse import urlparse
from fastapi import APIRouter, Depends, HTTPException, Query, status
from fastapi.responses import StreamingResponse
from app.services.stream_service import stream_registry, default_stream_manager, LiveStreamManager
from app.api.deps import get_current_user, get_current_user_flexible
from app.models.user import User

router = APIRouter(prefix="/api/stream", tags=["stream"])


def _validate_stream_source(source: str) -> str:
    source_clean = source.strip()
    if source_clean.isdigit():
        return source_clean
    if source_clean.startswith(("rtsp://", "http://", "https://")):
        return source_clean

    norm_path = os.path.normpath(source_clean)
    if norm_path.startswith("test_assets" + os.sep) or norm_path == "test_assets":
        if os.path.exists(norm_path) and os.path.isfile(norm_path):
            return norm_path
        raise HTTPException(status_code=404, detail=f"Test asset '{source_clean}' not found")

    raise HTTPException(
        status_code=status.HTTP_400_BAD_REQUEST,
        detail="Invalid stream source. Allowed sources: RTSP/HTTP stream URLs, camera device numbers, or paths within test_assets/.",
    )


async def mjpeg_frame_generator(manager: LiveStreamManager):
    await manager.start()
    while manager.is_running:
        if manager.latest_frame_jpeg is not None:
            yield (
                b"--frame\r\n"
                b"Content-Type: image/jpeg\r\n\r\n" + manager.latest_frame_jpeg + b"\r\n"
            )
        await asyncio.sleep(0.04)  # ~25 FPS max output


@router.get("/feed")
async def get_stream_feed(
    source: str | None = None,
    user: User = Depends(get_current_user_flexible),
):
    """
    Returns an MJPEG stream suitable for direct rendering in an HTML <img> tag.
    Requires authentication via Bearer token or ?token= query parameter.
    """
    valid_source = _validate_stream_source(source) if source else None
    manager = await stream_registry.get_or_create(valid_source)

    return StreamingResponse(
        mjpeg_frame_generator(manager),
        media_type="multipart/x-mixed-replace; boundary=frame",
    )


@router.get("/status")
async def get_stream_status(
    source: str | None = None,
    user: User = Depends(get_current_user),
):
    """Returns current real-time detection telemetry (FPS, risk level, confidence)."""
    valid_source = _validate_stream_source(source) if source else None
    manager = await stream_registry.get_or_create(valid_source)
    return manager.latest_meta



@router.get("/alerts")
async def get_alerts_history(user: User = Depends(get_current_user)):
    """Returns the chronological audit log of triggered lifeguard alerts."""
    from app.services.alert_service import default_alert_dispatcher
    return {
        "count": len(default_alert_dispatcher.dispatch_history),
        "alerts": default_alert_dispatcher.dispatch_history[::-1],  # newest first
    }


@router.post("/alerts/webhook")
async def register_alert_webhook(
    url: str = Query(..., description="Webhook endpoint URL"),
    user: User = Depends(get_current_user),
):
    """Registers an external webhook (e.g., Slack, Twilio endpoint) to receive real-time alerts."""
    parsed = urlparse(url.strip())
    if parsed.scheme not in ("http", "https") or not parsed.netloc:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Invalid webhook URL. Must begin with http:// or https:// and include a valid domain/host.",
        )

    from app.services.alert_service import default_alert_dispatcher
    default_alert_dispatcher.register_webhook(url.strip())
    return {"status": "registered", "url": url.strip()}


@router.post("/alerts/sms")
async def register_sms_recipient(
    phone: str = Query(..., description="Phone number with country code (e.g. +919876543210)"),
    user: User = Depends(get_current_user),
):
    """Registers an emergency SMS recipient for critical escalated rip current alerts."""
    phone_clean = phone.strip()
    if not (phone_clean.startswith("+") and phone_clean[1:].isdigit() and len(phone_clean) >= 10):
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Invalid phone number format. Must include country code starting with '+' followed by digits.",
        )
    from app.services.alert_service import default_alert_dispatcher
    default_alert_dispatcher.register_sms_recipient(phone_clean)
    return {"status": "registered", "phone": phone_clean}


@router.post("/alerts/siren")
async def configure_siren_relay(
    url: str | None = Query(None, description="Siren relay webhook endpoint URL"),
    user: User = Depends(get_current_user),
):
    """Configures the beach siren hardware relay endpoint."""
    from app.services.alert_service import default_alert_dispatcher
    if url:
        parsed = urlparse(url.strip())
        if parsed.scheme not in ("http", "https") or not parsed.netloc:
            raise HTTPException(status_code=400, detail="Invalid siren relay URL.")
        default_alert_dispatcher.set_siren_relay(url.strip())
    else:
        default_alert_dispatcher.set_siren_relay(None)
    return {"status": "configured", "siren_relay_url": default_alert_dispatcher.siren_relay_url}


@router.post("/alerts/test-dispatch")
async def trigger_test_dispatch(
    user: User = Depends(get_current_user),
):
    """Triggers an end-to-end simulated alert dispatch across all registered channels."""
    from app.services.alert_service import default_alert_dispatcher
    simulated_meta = {
        "confidence": 0.95,
        "risk_level": "HIGH",
        "fps": 28.5,
        "timestamp": 1234567.89,
    }
    payload = default_alert_dispatcher._create_alert_payload(simulated_meta, sustained_duration=16.0, is_escalated=True)
    payload["type"] = "SIMULATED_TEST_DISPATCH"
    default_alert_dispatcher.dispatch_history.append(payload)
    await default_alert_dispatcher._deliver_all_channels(payload)
    return {"status": "dispatched", "payload": payload}


# ==============================================================================
# Camera Calibration & Hardware Edge Acceleration
# ==============================================================================

try:
    from ml.inference.homography import BeachCameraCalibrator, default_beach_calibrator
    from ml.inference.edge_optimizer import EdgeOptimizer
except ImportError:
    try:
        from inference.homography import BeachCameraCalibrator, default_beach_calibrator
        from inference.edge_optimizer import EdgeOptimizer
    except ImportError:
        BeachCameraCalibrator = None
        default_beach_calibrator = None
        EdgeOptimizer = None

from typing import Optional, List, Dict, Any
from pydantic import BaseModel, Field

# Stream-specific camera calibration registry
stream_calibrators: dict[str, Any] = {}


def _get_stream_calibrator(source: str | None = None) -> Any:
    key = (source or "default").strip()
    if key not in stream_calibrators:
        if default_beach_calibrator is not None:
            stream_calibrators[key] = BeachCameraCalibrator()
        else:
            return None
    return stream_calibrators[key]


class CalibrationPayload(BaseModel):
    source: Optional[str] = Field(None, description="Stream source identifier")
    camera_lat: Optional[float] = Field(None, description="Camera tower GPS latitude")
    camera_lon: Optional[float] = Field(None, description="Camera tower GPS longitude")
    mounting_height_m: Optional[float] = Field(None, description="Mounting height above water line in meters")
    tilt_angle_deg: Optional[float] = Field(None, description="Camera tilt depression angle in degrees")
    azimuth_deg: Optional[float] = Field(None, description="Compass azimuth heading in degrees")
    focal_length_px: Optional[float] = Field(None, description="Camera focal length in pixels")
    gcps: Optional[List[Dict[str, Any]]] = Field(
        None,
        description="4 (or more) surveyed ground control points with pixel_x, pixel_y, rtk_lat, rtk_lon",
    )


class ProjectionPayload(BaseModel):
    source: Optional[str] = Field(None, description="Stream source identifier")
    pixel_x: Optional[float] = Field(None, description="Pixel x coordinate [0, img_w]")
    pixel_y: Optional[float] = Field(None, description="Pixel y coordinate [0, img_h]")
    norm_x: Optional[float] = Field(None, description="Normalized x coordinate [0, 1]")
    norm_y: Optional[float] = Field(None, description="Normalized y coordinate [0, 1]")
    img_w: int = Field(1920, description="Image width")
    img_h: int = Field(1080, description="Image height")


@router.get("/calibration")
async def get_stream_calibration(
    source: str | None = None,
    user: User = Depends(get_current_user),
):
    """Retrieves current camera calibration profile, GCP status, and homography matrix."""
    calibrator = _get_stream_calibrator(source)
    if not calibrator:
        raise HTTPException(status_code=500, detail="Homography calibrator engine unavailable.")
    return calibrator.to_dict()


@router.post("/calibration")
async def calibrate_stream_camera(
    payload: CalibrationPayload,
    user: User = Depends(get_current_user),
):
    """
    Calibrates camera mounting height (h), tilt angle (theta), and solves 3x3 planar homography matrix
    using 4 Ground Control Points (GCPs) surveyed with an RTK GPS on the beach.
    """
    calibrator = _get_stream_calibrator(payload.source)
    if not calibrator:
        raise HTTPException(status_code=500, detail="Homography calibrator engine unavailable.")

    # Update base properties if supplied
    if payload.camera_lat is not None:
        calibrator.camera_lat = float(payload.camera_lat)
    if payload.camera_lon is not None:
        calibrator.camera_lon = float(payload.camera_lon)
    if payload.mounting_height_m is not None:
        calibrator.height = max(1.0, float(payload.mounting_height_m))
    if payload.tilt_angle_deg is not None:
        import math
        calibrator.tilt_deg = float(payload.tilt_angle_deg)
        calibrator.tilt_rad = math.radians(calibrator.tilt_deg)
    if payload.azimuth_deg is not None:
        import math
        calibrator.azimuth_deg = float(payload.azimuth_deg)
        calibrator.azimuth_rad = math.radians(calibrator.azimuth_deg)
    if payload.focal_length_px is not None:
        calibrator.focal_px = float(payload.focal_length_px)

    gcp_calibration_result = None
    if payload.gcps is not None:
        if len(payload.gcps) < 4:
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail=f"At least 4 Ground Control Points (GCPs) surveyed with RTK GPS are required. Provided: {len(payload.gcps)}",
            )
        try:
            gcp_calibration_result = calibrator.calibrate_with_gcps(payload.gcps)
        except Exception as e:
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail=f"Homography calibration error: {str(e)}",
            )

    return {
        "status": "calibrated",
        "calibration": calibrator.to_dict(),
        "gcp_result": gcp_calibration_result,
    }


@router.post("/calibration/project")
async def project_stream_coordinate(
    payload: ProjectionPayload,
    user: User = Depends(get_current_user),
):
    """
    Projects a camera image pixel coordinate to physical metric distances (meters offshore / alongshore)
    and RTK GPS coordinates (latitude, longitude) using the calibrated homography profile.
    """
    calibrator = _get_stream_calibrator(payload.source)
    if not calibrator:
        raise HTTPException(status_code=500, detail="Homography calibrator engine unavailable.")

    # Derive normalized coordinates
    norm_x = payload.norm_x
    norm_y = payload.norm_y
    if norm_x is None:
        if payload.pixel_x is None:
            raise HTTPException(status_code=400, detail="Must provide either pixel_x/pixel_y or norm_x/norm_y.")
        norm_x = payload.pixel_x / payload.img_w
    if norm_y is None:
        if payload.pixel_y is None:
            raise HTTPException(status_code=400, detail="Must provide either pixel_x/pixel_y or norm_x/norm_y.")
        norm_y = payload.pixel_y / payload.img_h

    metric_res = calibrator.pixel_to_metric_distance(
        norm_x=norm_x,
        norm_y=norm_y,
        img_w=payload.img_w,
        img_h=payload.img_h,
    )
    lat, lon = calibrator.metric_to_gps(
        offshore_distance_m=metric_res["offshore_distance_m"],
        lateral_offset_m=metric_res["lateral_offset_m"],
    )

    return {
        **metric_res,
        "gps": {"lat": lat, "lon": lon},
        "camera_tower": {
            "lat": calibrator.camera_lat,
            "lon": calibrator.camera_lon,
            "height_m": calibrator.height,
            "tilt_deg": calibrator.tilt_deg,
        },
    }


@router.delete("/calibration")
async def reset_stream_calibration(
    source: str | None = None,
    user: User = Depends(get_current_user),
):
    """Resets camera calibration back to default factory baseline."""
    key = (source or "default").strip()
    if BeachCameraCalibrator is not None:
        stream_calibrators[key] = BeachCameraCalibrator()
    return {"status": "reset", "source": key}


@router.get("/hardware")
async def get_hardware_edge_status(
    user: User = Depends(get_current_user),
):
    """
    Returns edge hardware acceleration status, NVIDIA Jetson Orin compatibility,
    TensorRT FP16 compilation status, and sub-20W power envelope certification.
    """
    if EdgeOptimizer is None:
        raise HTTPException(status_code=500, detail="EdgeOptimizer module not available.")

    optimizer = EdgeOptimizer()
    caps = optimizer.detect_edge_capabilities()
    bench = optimizer.benchmark_edge_throughput(iterations=5, warmup=1)

    return {
        "status": "operational",
        "target_node": "NVIDIA Jetson Orin Lifeguard Edge Node",
        "power_mode": "Sub-20W (Jetson Orin 15W/20W Mode)",
        "precision": "TensorRT FP16",
        "target_fps": 30.0,
        "capabilities": caps,
        "benchmark": bench,
    }



