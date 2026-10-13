"""
Lifeguard Alert Dispatcher:
Monitors live stream telemetry and triggers webhooks or emergency dispatch notifications
when sustained HIGH-risk rip current activity exceeds a configurable duration threshold
(e.g., >= 5 consecutive seconds with confidence >= 0.70).
"""

import asyncio
import logging
import time
from typing import Any
import httpx

logger = logging.getLogger(__name__)


class AlertDispatcher:
    def __init__(self, sustained_seconds_threshold: float = 4.0, cooldown_seconds: float = 30.0):
        self.sustained_seconds_threshold = sustained_seconds_threshold
        self.cooldown_seconds = cooldown_seconds
        
        self.high_risk_start_time: float | None = None
        self.last_dispatched_time: float = 0.0
        self.webhook_urls: list[str] = []
        self.dispatch_history: list[dict[str, Any]] = []

    def register_webhook(self, url: str) -> None:
        if url not in self.webhook_urls:
            self.webhook_urls.append(url)

    def process_telemetry(self, meta: dict[str, Any]) -> dict[str, Any] | None:
        """
        Evaluates real-time telemetry. Returns alert payload if a dispatch occurs, else None.
        """
        now = time.time()
        confidence = meta.get("confidence", 0.0)
        risk_level = meta.get("risk_level", "LOW")

        # Check if currently in high risk state
        if risk_level == "HIGH" or confidence >= 0.70:
            if self.high_risk_start_time is None:
                self.high_risk_start_time = now
            
            sustained_duration = now - self.high_risk_start_time

            # Check if duration threshold met and cooldown period has expired
            if sustained_duration >= self.sustained_seconds_threshold:
                if now - self.last_dispatched_time >= self.cooldown_seconds:
                    alert_payload = self._create_alert_payload(meta, sustained_duration)
                    self.last_dispatched_time = now
                    self.dispatch_history.append(alert_payload)
                    # Trigger async delivery
                    asyncio.create_task(self._deliver_webhooks(alert_payload))
                    return alert_payload
        else:
            # Reset sustained counter when conditions drop back down
            self.high_risk_start_time = None

        return None

    def _create_alert_payload(self, meta: dict[str, Any], sustained_duration: float) -> dict[str, Any]:
        return {
            "id": f"alert_{int(time.time())}",
            "type": "SUSTAINED_RIP_CURRENT_DETECTED",
            "priority": "CRITICAL",
            "confidence": meta.get("confidence", 0.0),
            "sustained_duration_sec": round(sustained_duration, 1),
            "timestamp": time.strftime("%Y-%m-%d %H:%M:%S UTC", time.gmtime()),
            "message": (
                f"CRITICAL: Active rip current corridor detected with "
                f"{round(meta.get('confidence', 0.0) * 100, 1)}% confidence sustained for "
                f"{round(sustained_duration, 1)}s. Lifeguard inspection recommended immediately."
            ),
        }

    async def _deliver_webhooks(self, payload: dict[str, Any]) -> None:
        if not self.webhook_urls:
            logger.info("Lifeguard Alert Triggered (No external webhooks configured): %s", payload["message"])
            return

        async with httpx.AsyncClient(timeout=5.0) as client:
            for url in self.webhook_urls:
                try:
                    await client.post(url, json=payload)
                    logger.info("Successfully dispatched alert to %s", url)
                except Exception as e:
                    logger.warning("Failed to dispatch alert to %s: %s", url, e)


# Global singleton dispatcher instance
default_alert_dispatcher = AlertDispatcher()
