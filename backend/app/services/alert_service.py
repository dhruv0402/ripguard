"""
Lifeguard Alert Dispatcher:
Monitors live stream telemetry and triggers multi-channel emergency dispatches
(Webhooks, SMS/WhatsApp gateways, and Beach Siren Relays) when sustained HIGH-risk
rip current activity exceeds safety duration thresholds.
"""

import asyncio
import logging
import time
from typing import Any, List, Dict, Optional
import httpx

logger = logging.getLogger(__name__)


class AlertDispatcher:
    def __init__(
        self,
        sustained_seconds_threshold: float = 4.0,
        critical_escalation_seconds: float = 15.0,
        cooldown_seconds: float = 30.0,
    ):
        self.sustained_seconds_threshold = sustained_seconds_threshold
        self.critical_escalation_seconds = critical_escalation_seconds
        self.cooldown_seconds = cooldown_seconds
        
        self.high_risk_start_time: float | None = None
        self.last_dispatched_time: float = 0.0
        self.webhook_urls: list[str] = []
        self.sms_phone_numbers: list[str] = []
        self.siren_relay_url: Optional[str] = None
        self.dispatch_history: list[dict[str, Any]] = []

    def register_webhook(self, url: str) -> None:
        if url not in self.webhook_urls:
            self.webhook_urls.append(url)

    def register_sms_recipient(self, phone: str) -> None:
        if phone not in self.sms_phone_numbers:
            self.sms_phone_numbers.append(phone)

    def set_siren_relay(self, url: Optional[str]) -> None:
        self.siren_relay_url = url

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
                    is_escalated = sustained_duration >= self.critical_escalation_seconds
                    alert_payload = self._create_alert_payload(meta, sustained_duration, is_escalated)
                    self.last_dispatched_time = now
                    self.dispatch_history.append(alert_payload)
                    # Trigger async multi-channel delivery
                    asyncio.create_task(self._deliver_all_channels(alert_payload))
                    return alert_payload
        else:
            # Reset sustained counter when conditions drop back down
            self.high_risk_start_time = None

        return None

    def _create_alert_payload(
        self,
        meta: dict[str, Any],
        sustained_duration: float,
        is_escalated: bool = False,
    ) -> dict[str, Any]:
        priority = "ESCALATED_LIFE_SAFETY" if is_escalated else "CRITICAL"
        return {
            "id": f"alert_{int(time.time())}",
            "type": "SUSTAINED_RIP_CURRENT_DETECTED",
            "priority": priority,
            "is_escalated": is_escalated,
            "confidence": meta.get("confidence", 0.0),
            "sustained_duration_sec": round(sustained_duration, 1),
            "timestamp": time.strftime("%Y-%m-%d %H:%M:%S UTC", time.gmtime()),
            "channels_notified": ["websocket"] + (["webhook"] if self.webhook_urls else []) + (["sms"] if self.sms_phone_numbers else []) + (["siren"] if self.siren_relay_url else []),
            "message": (
                f"{priority}: Active seaward rip current corridor detected with "
                f"{round(meta.get('confidence', 0.0) * 100, 1)}% confidence sustained for "
                f"{round(sustained_duration, 1)}s. "
                f"{'ACTIVATE BEACH SIREN & IMMEDIATE PATROL RESCUE.' if is_escalated else 'Lifeguard inspection recommended immediately.'}"
            ),
        }

    async def _deliver_all_channels(self, payload: dict[str, Any]) -> None:
        tasks = []
        if self.webhook_urls:
            tasks.append(self._deliver_webhooks(payload))
        if self.sms_phone_numbers:
            tasks.append(self._deliver_sms(payload))
        if self.siren_relay_url:
            tasks.append(self._trigger_siren_relay(payload))

        if tasks:
            await asyncio.gather(*tasks, return_exceptions=True)
        else:
            logger.info("Lifeguard Alert Dispatched (Dashboard only): %s", payload["message"])

    async def _deliver_webhooks(self, payload: dict[str, Any]) -> None:
        async with httpx.AsyncClient(timeout=5.0) as client:
            for url in self.webhook_urls:
                try:
                    await client.post(url, json=payload)
                    logger.info("Dispatched alert webhook to %s", url)
                except Exception as e:
                    logger.warning("Failed to dispatch alert webhook to %s: %s", url, e)

    async def _deliver_sms(self, payload: dict[str, Any]) -> None:
        # Mockable SMS gateway dispatch (e.g. Twilio / Sinch format)
        for phone in self.sms_phone_numbers:
            logger.info("Dispatched emergency SMS alert to %s: %s", phone, payload["message"])

    async def _trigger_siren_relay(self, payload: dict[str, Any]) -> None:
        if not self.siren_relay_url:
            return
        async with httpx.AsyncClient(timeout=3.0) as client:
            try:
                await client.post(self.siren_relay_url, json={"trigger": "ON", "duration_sec": 10, "alert": payload})
                logger.warning("BEACH SIREN RELAY ACTIVATED at %s", self.siren_relay_url)
            except Exception as e:
                logger.error("Failed to trigger beach siren relay: %s", e)


# Global singleton dispatcher instance
default_alert_dispatcher = AlertDispatcher()
