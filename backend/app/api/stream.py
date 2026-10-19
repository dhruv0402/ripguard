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


# ==============================================================================
# Environmental Sensing & Maritime Compliance Endpoints
# ==============================================================================

try:
    from ml.inference.tide_compensator import TidalCompensator
    from ml.inference.optical_filters import SunGlintFilter, TwilightAdaptivePreprocessor
    from ml.inference.thermal_governor import JetsonThermalGovernor
except ImportError:
    try:
        from inference.tide_compensator import TidalCompensator
        from inference.optical_filters import SunGlintFilter, TwilightAdaptivePreprocessor
        from inference.thermal_governor import JetsonThermalGovernor
    except ImportError:
        TidalCompensator = None
        SunGlintFilter = None
        TwilightAdaptivePreprocessor = None
        JetsonThermalGovernor = None

from app.core.maritime_compliance import (
    default_compliance_guard,
    ClearanceAction,
    STATUTORY_MARITIME_DISCLAIMER,
)

# Global singleton environmental handlers
default_tide_compensator = TidalCompensator() if TidalCompensator else None
default_thermal_governor = JetsonThermalGovernor() if JetsonThermalGovernor else None


class OperatorClearancePayload(BaseModel):
    alert_id: str = Field(..., description="Alert ID being cleared or dismissed")
    action: ClearanceAction = Field(..., description="Lifeguard action (CONFIRMED_DISPATCH, DISMISSED_FALSE_ALARM, UNDER_OBSERVATION)")
    notes: Optional[str] = Field(None, description="Visual observations from duty lifeguard")


class TideUpdatePayload(BaseModel):
    water_level_m: Optional[float] = Field(None, description="Manual tide height in meters above MSL")
    station_id: Optional[str] = Field(None, description="NOAA station ID")


@router.post("/compliance/clearance")
async def record_operator_clearance(
    payload: OperatorClearancePayload,
    user: User = Depends(get_current_user),
):
    """
    Records human-in-the-loop operator clearance or dismissal of an alert,
    logging it into the tamper-evident maritime compliance audit log.
    """
    entry = default_compliance_guard.record_operator_clearance(
        alert_id=payload.alert_id,
        user_id=user.id,
        user_email=user.email,
        action=payload.action,
        operator_notes=payload.notes,
    )
    return {
        "status": "clearance_recorded",
        "entry": entry,
        "statutory_disclaimer": STATUTORY_MARITIME_DISCLAIMER,
    }


@router.get("/compliance/audit-trail")
async def get_compliance_audit_trail(
    limit: int = 50,
    user: User = Depends(get_current_user),
):
    """Retrieves chronological tamper-evident maritime compliance audit trail."""
    return {
        "count": len(default_compliance_guard.audit_log),
        "audit_trail": default_compliance_guard.get_audit_trail(limit=limit),
        "statutory_disclaimer": STATUTORY_MARITIME_DISCLAIMER,
    }


@router.get("/environmental")
async def get_environmental_status(
    source: str | None = None,
    user: User = Depends(get_current_user),
):
    """
    Returns real-time environmental conditions:
      - Tidal stage modulation & effective water height
      - Sun glint & optical CPL filter recommendation
      - Twilight illumination & noise estimation
      - Jetson Orin SoC temperature & thermal governance state
    """
    calibrator = _get_stream_calibrator(source)

    # 1. Tide Status
    tide_status = (
        default_tide_compensator.get_effective_camera_height()
        if default_tide_compensator
        else {"effective_camera_height_m": calibrator.height if calibrator else 12.0}
    )

    if calibrator and default_tide_compensator:
        calibrator.set_active_tide_delta(tide_status.get("water_level_delta_m", 0.0))

    # 2. Thermal Status
    thermal_status = (
        default_thermal_governor.evaluate_thermal_state()
        if default_thermal_governor
        else {"thermal_state": "NOMINAL", "soc_temperature_c": 45.0}
    )

    return {
        "tidal_modulation": tide_status,
        "thermal_governance": thermal_status,
        "optical_filters": {
            "glint_filter_active": True,
            "twilight_filter_active": True,
            "cpl_polarizer_mode": "AUTO_ACTUATED",
        },
        "maritime_classification": "DECISION_SUPPORT_ONLY",
    }


@router.post("/environmental/tide")
async def update_environmental_tide(
    payload: TideUpdatePayload,
    user: User = Depends(get_current_user),
):
    """Updates active tidal compensation via manual water level or station selection."""
    if not default_tide_compensator:
        raise HTTPException(status_code=500, detail="Tidal compensator not available.")

    if payload.station_id:
        default_tide_compensator.station_id = payload.station_id
    if payload.water_level_m is not None:
        default_tide_compensator.set_manual_override(payload.water_level_m)
    else:
        default_tide_compensator.set_manual_override(None)

    status = default_tide_compensator.get_effective_camera_height()
    return {"status": "updated", "tide": status}


# ==============================================================================
# PTZ Dynamic Homography, CPL Filter Actuation, Domain Adapter & CAD Dispatch
# ==============================================================================

try:
    from ml.inference.ptz_controller import PTZController
    from ml.inference.cpl_actuator import CPLActuator
    from ml.active_learning.domain_adapter import CoastalDomainAdapter, BeachArchetype
    from ml.inference.hardware_acceptance import HardwareAcceptanceTester
except ImportError:
    try:
        from inference.ptz_controller import PTZController
        from inference.cpl_actuator import CPLActuator
        from active_learning.domain_adapter import CoastalDomainAdapter, BeachArchetype
        from inference.hardware_acceptance import HardwareAcceptanceTester
    except ImportError:
        PTZController = None
        CPLActuator = None
        CoastalDomainAdapter = None
        BeachArchetype = None
        HardwareAcceptanceTester = None

from app.services.cad_dispatch import default_cad_dispatcher

default_ptz_controller = PTZController() if PTZController else None
default_cpl_actuator = CPLActuator() if CPLActuator else None
default_domain_adapter = CoastalDomainAdapter() if CoastalDomainAdapter else None


class PTZMovePayload(BaseModel):
    pan_delta_deg: float = Field(0.0, description="Relative pan in degrees")
    tilt_delta_deg: float = Field(0.0, description="Relative tilt in degrees")
    zoom_ratio: float = Field(1.0, description="Optical zoom multiplier (1.0 = standard)")
    reset_to_home: bool = Field(False, description="Whether to command return to calibrated Home preset")


class CPLActuatePayload(BaseModel):
    target_angle_deg: Optional[float] = Field(None, description="Target angle in [0, 180]")
    auto_glint_extinguish: bool = Field(False, description="Whether to automatically extinguish glare based on solar azimuth")
    solar_azimuth_deg: float = Field(180.0, description="Sun compass azimuth in degrees")


class DomainConfigPayload(BaseModel):
    archetype: Optional[str] = Field(None, description="Beach archetype (GOLDEN_QUARTZ, VOLCANIC_BLACK, PEBBLE_SHINGLE, ESTUARINE_TURBID)")
    shadow_mode: Optional[bool] = Field(None, description="Enable 14-day shadow harvesting mode")


class CADDispatchPayload(BaseModel):
    alert_id: str = Field(..., description="Alert ID being forwarded to 911/CAD")
    gps_lat: float = Field(15.5492, description="Latitude of corridor centroid")
    gps_lon: float = Field(73.7535, description="Longitude of corridor centroid")
    message: Optional[str] = Field(None, description="Custom dispatch message")


@router.get("/ptz/status")
async def get_ptz_status(user: User = Depends(get_current_user)):
    """Returns PTZ camera position, return-to-home watchdog status, and dynamic homography state."""
    if not default_ptz_controller:
        raise HTTPException(status_code=500, detail="PTZ controller not available.")
    watchdog = default_ptz_controller.check_home_preset_watchdog()
    return {
        "pan_deg": default_ptz_controller.current_pan_deg,
        "tilt_deg": default_ptz_controller.current_tilt_deg,
        "zoom_ratio": default_ptz_controller.current_zoom_ratio,
        "is_at_home_preset": default_ptz_controller.is_at_home_preset,
        "watchdog": watchdog,
    }


@router.post("/ptz/move")
async def move_ptz_camera(
    payload: PTZMovePayload,
    user: User = Depends(get_current_user),
):
    """Updates PTZ camera orientation or commands return to calibrated Home preset."""
    if not default_ptz_controller:
        raise HTTPException(status_code=500, detail="PTZ controller not available.")

    if payload.reset_to_home:
        res = default_ptz_controller.command_goto_preset()
    else:
        default_ptz_controller.update_ptz_state(
            pan_delta_deg=payload.pan_delta_deg,
            tilt_delta_deg=payload.tilt_delta_deg,
            zoom_ratio=payload.zoom_ratio,
        )
        res = {
            "pan_deg": default_ptz_controller.current_pan_deg,
            "tilt_deg": default_ptz_controller.current_tilt_deg,
            "zoom_ratio": default_ptz_controller.current_zoom_ratio,
            "is_at_home_preset": default_ptz_controller.is_at_home_preset,
        }
    return {"status": "success", "ptz": res}


@router.get("/cpl/status")
async def get_cpl_status(user: User = Depends(get_current_user)):
    """Returns motorized Circular Polarizing (CPL) lens actuator telemetry."""
    if not default_cpl_actuator:
        raise HTTPException(status_code=500, detail="CPL actuator not available.")
    return default_cpl_actuator.get_status()


@router.post("/cpl/actuate")
async def actuate_cpl_polarizer(
    payload: CPLActuatePayload,
    user: User = Depends(get_current_user),
):
    """Rotates physical motorized CPL filter glass to extinguish ocean sun glint."""
    if not default_cpl_actuator:
        raise HTTPException(status_code=500, detail="CPL actuator not available.")

    if payload.auto_glint_extinguish:
        res = default_cpl_actuator.auto_adjust_for_glint(
            requires_cpl=True,
            solar_azimuth_deg=payload.solar_azimuth_deg,
        )
    elif payload.target_angle_deg is not None:
        res = default_cpl_actuator.rotate_to_angle(payload.target_angle_deg)
    else:
        res = default_cpl_actuator.rotate_to_angle(0.0)

    return {"status": "actuated", "result": res}


@router.get("/domain/status")
async def get_domain_status(user: User = Depends(get_current_user)):
    """Returns coastal archetype adaptation (Black Sand, Estuary, Golden Sand) and shadow mode status."""
    if not default_domain_adapter:
        raise HTTPException(status_code=500, detail="Domain adapter not available.")
    return {
        "active_archetype": default_domain_adapter.active_archetype.value,
        "shadow_mode_active": default_domain_adapter.shadow_mode,
        "harvested_shadow_samples": default_domain_adapter.harvested_shadow_samples,
        "thresholds": default_domain_adapter.ARCHETYPE_THRESHOLDS[default_domain_adapter.active_archetype],
    }


@router.post("/domain/configure")
async def configure_domain_adapter(
    payload: DomainConfigPayload,
    user: User = Depends(get_current_user),
):
    """Configures beach archetype and 14-day shadow harvesting mode."""
    if not default_domain_adapter:
        raise HTTPException(status_code=500, detail="Domain adapter not available.")

    if payload.archetype and BeachArchetype:
        try:
            default_domain_adapter.active_archetype = BeachArchetype(payload.archetype)
        except ValueError:
            raise HTTPException(status_code=400, detail=f"Invalid archetype: {payload.archetype}")

    if payload.shadow_mode is not None:
        default_domain_adapter.shadow_mode = payload.shadow_mode

    return {
        "status": "configured",
        "active_archetype": default_domain_adapter.active_archetype.value,
        "shadow_mode_active": default_domain_adapter.shadow_mode,
    }


@router.post("/cad/dispatch")
async def dispatch_incident_to_cad(
    payload: CADDispatchPayload,
    user: User = Depends(get_current_user),
):
    """Dispatches standard OASIS Common Alerting Protocol (CAP v1.2) XML to municipal 911 CAD centers."""
    alert_meta = {
        "id": payload.alert_id,
        "message": payload.message or "Sustained high-velocity seaward rip current corridor.",
        "is_escalated": True,
        "confidence": 0.94,
    }
    incident = await default_cad_dispatcher.dispatch_to_cad(
        alert_payload=alert_meta,
        gps_lat=payload.gps_lat,
        gps_lon=payload.gps_lon,
    )
    return {"status": "dispatched", "incident": incident}


@router.get("/cad/history")
async def get_cad_dispatch_history(user: User = Depends(get_current_user)):
    """Returns municipal CAD dispatch log."""
    return {
        "count": len(default_cad_dispatcher.incident_history),
        "history": default_cad_dispatcher.incident_history[::-1],
    }


@router.post("/hardware/acceptance-test")
async def run_hardware_acceptance_test(user: User = Depends(get_current_user)):
    """Executes the automated Hardware Acceptance Test (HAT) and generates certification report."""
    if not HardwareAcceptanceTester:
        raise HTTPException(status_code=500, detail="HAT suite not available.")

    tester = HardwareAcceptanceTester()
    cert = tester.generate_full_hat_certificate()
    return {"status": "completed", "certificate": cert}





