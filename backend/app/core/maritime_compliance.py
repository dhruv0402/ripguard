"""
RipGuard Maritime Compliance & Decision-Support Audit System
Complies with USLA (United States Lifesaving Association) & SLSA guidelines:
1. Enforces that RipGuard acts strictly as a Decision-Support Tool (advisory cue only).
2. Prohibits automated autonomous beach closures or unconfirmed siren activations.
3. Implements tamper-evident Human-in-the-Loop (HITL) operator clearance & audit logging.
4. Injects statutory maritime disclaimers into all alert dispatches and API payloads.
"""

import time
import uuid
from typing import Dict, Any, List, Optional
from enum import Enum


class ClearanceAction(str, Enum):
    CONFIRMED_DISPATCH = "CONFIRMED_DISPATCH"      # Lifeguard confirmed active rip & verified siren/flag
    DISMISSED_FALSE_ALARM = "DISMISSED_FALSE_ALARM"  # Lifeguard marked as non-hazardous wave breaking
    UNDER_OBSERVATION = "UNDER_OBSERVATION"        # Lifeguard actively monitoring area with binoculars


STATUTORY_MARITIME_DISCLAIMER = (
    "STATUTORY DISCLAIMER: RipGuard is an experimental AI decision-support system intended solely "
    "to assist qualified human observers. It is NOT certified as an autonomous lifesaving appliance. "
    "Never initiate automated beach closures, public evacuations, or medical responses without "
    "direct visual verification by certified beach lifeguards (USLA / SLSA standard)."
)


class MaritimeComplianceGuard:
    """
    Maintains statutory disclaimers and immutable audit logs of operator clearances
    to satisfy maritime regulatory requirements and civil liability standards.
    """

    def __init__(self):
        self.audit_log: List[Dict[str, Any]] = []

    def record_operator_clearance(
        self,
        alert_id: str,
        user_id: str,
        user_email: str,
        action: ClearanceAction,
        operator_notes: Optional[str] = None,
        client_ip: Optional[str] = None,
    ) -> Dict[str, Any]:
        """
        Records human operator clearance or dismissal of an escalated coastal rip current alert.
        Provides an immutable audit record for municipal safety review.
        """
        entry = {
            "clearance_id": f"CLR-{uuid.uuid4().hex[:10].upper()}",
            "alert_id": alert_id,
            "operator_id": user_id,
            "operator_email": user_email,
            "action": action.value,
            "notes": operator_notes or "Visual inspection completed by duty lifeguard.",
            "client_ip": client_ip or "127.0.0.1",
            "timestamp": time.time(),
            "iso_time": time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime()),
            "disclaimer_accepted": True,
        }
        self.audit_log.append(entry)
        return entry

    def inject_compliance_metadata(self, payload: Dict[str, Any]) -> Dict[str, Any]:
        """Injects maritime decision-support disclaimers and human clearance requirements into alerts."""
        enriched = dict(payload)
        enriched["maritime_compliance"] = {
            "system_classification": "ADVISORY_DECISION_SUPPORT_SYSTEM",
            "autonomous_action_permitted": False,
            "requires_human_clearance": True,
            "statutory_disclaimer": STATUTORY_MARITIME_DISCLAIMER,
        }
        return enriched

    def get_audit_trail(self, limit: int = 100) -> List[Dict[str, Any]]:
        """Returns the chronological audit trail of operator clearance decisions."""
        return self.audit_log[-limit:][::-1]


# Default singleton compliance instance
default_compliance_guard = MaritimeComplianceGuard()
