import asyncio
from fastapi import APIRouter, WebSocket, WebSocketDisconnect, Query
from fastapi.responses import StreamingResponse
from app.services.stream_service import default_stream_manager, LiveStreamManager

router = APIRouter(prefix="/api/stream", tags=["stream"])


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
async def get_stream_feed(source: str | None = None):
    """
    Returns an MJPEG stream suitable for direct rendering in an HTML <img> tag.
    Optional ?source= parameter accepts RTSP URL or local video filepath.
    """
    manager = default_stream_manager
    if source and source != manager.stream_source:
        manager.stream_source = source
    await manager.start()

    return StreamingResponse(
        mjpeg_frame_generator(manager),
        media_type="multipart/x-mixed-replace; boundary=frame",
    )


@router.get("/status")
async def get_stream_status():
    """Returns current real-time detection telemetry (FPS, risk level, confidence)."""
    return default_stream_manager.latest_meta


@router.get("/alerts")
async def get_alerts_history():
    """Returns the chronological audit log of triggered lifeguard alerts."""
    from app.services.alert_service import default_alert_dispatcher
    return {
        "count": len(default_alert_dispatcher.dispatch_history),
        "alerts": default_alert_dispatcher.dispatch_history[::-1],  # newest first
    }


@router.post("/alerts/webhook")
async def register_alert_webhook(url: str = Query(..., description="Webhook endpoint URL")):
    """Registers an external webhook (e.g., Slack, Twilio endpoint) to receive real-time alerts."""
    from app.services.alert_service import default_alert_dispatcher
    default_alert_dispatcher.register_webhook(url)
    return {"status": "registered", "url": url}
