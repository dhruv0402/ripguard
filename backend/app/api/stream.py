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


