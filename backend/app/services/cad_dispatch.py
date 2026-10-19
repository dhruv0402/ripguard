"""
RipGuard Computer-Aided Dispatch (CAD) Municipal Emergency Integration
Generates standard OASIS Common Alerting Protocol (CAP v1.2) XML alerts
and interfaces with municipal emergency dispatch systems
(Motorola Solutions PremierOne, Hexagon OnCall, Tyler CAD).

Standard: ITU-T X.1303 / OASIS CAP-V1.2
"""

import time
import uuid
import xml.etree.ElementTree as ET
from typing import Dict, Any, List, Optional
import httpx


class CADIncidentStatus:
    REPORTED = "REPORTED"
    DISPATCHED = "DISPATCHED"
    EN_ROUTE = "EN_ROUTE"
    ON_SCENE = "ON_SCENE"
    RESOLVED = "RESOLVED"


class CADDispatcher:
    """
    Formats coastal hazard events into OASIS CAP v1.2 XML and dispatches
    to municipal 911 / emergency communications centers.
    """

    def __init__(
        self,
        cad_endpoint_url: Optional[str] = None,
        agency_code: str = "RIPGUARD-BEACH-SAFETY",
    ):
        self.cad_url = cad_endpoint_url
        self.agency_code = agency_code
        self.incident_history: List[Dict[str, Any]] = []

    def generate_cap_v12_xml(
        self,
        alert_payload: Dict[str, Any],
        gps_lat: float = 15.5492,
        gps_lon: float = 73.7535,
        radius_meters: float = 50.0,
    ) -> str:
        """
        Constructs an OASIS Common Alerting Protocol (CAP) v1.2 compliant XML document.
        Standard specification required by FEMA IPAWS, CAD systems, and municipal 911 centers.
        """
        identifier = f"RIPGUARD-{uuid.uuid4().hex[:12].upper()}"
        iso_now = time.strftime("%Y-%m-%dT%H:%M:%S+00:00", time.gmtime())

        root = ET.Element("alert", xmlns="urn:oasis:names:tc:emergency:cap:1.2")
        ET.SubElement(root, "identifier").text = identifier
        ET.SubElement(root, "sender").text = f"{self.agency_code}@cad.safety.gov"
        ET.SubElement(root, "sent").text = iso_now
        ET.SubElement(root, "status").text = "Actual"
        ET.SubElement(root, "msgType").text = "Alert"
        ET.SubElement(root, "scope").text = "Public"

        info = ET.SubElement(root, "info")
        ET.SubElement(info, "category").text = "Safety"
        ET.SubElement(info, "event").text = "Active Coastal Rip Current Hazard"
        ET.SubElement(info, "urgency").text = "Immediate"
        ET.SubElement(info, "severity").text = "Severe" if alert_payload.get("is_escalated") else "Moderate"
        ET.SubElement(info, "certainty").text = "Observed"
        ET.SubElement(info, "eventCode").text = "RIP-CURRENT"
        ET.SubElement(info, "headline").text = f"Automated Lifeguard Alert: Sustained Rip Current at Tower Baseline"
        ET.SubElement(info, "description").text = alert_payload.get("message", "Active rip current corridor detected.")
        ET.SubElement(info, "instruction").text = "Dispatch beach rescue watercraft (IRB / Jet Ski). Direct bathers out of water."

        # Area geofencing
        area = ET.SubElement(info, "area")
        ET.SubElement(area, "areaDesc").text = f"Surf Zone adjacent to Tower ({gps_lat:.4f}, {gps_lon:.4f})"
        ET.SubElement(area, "circle").text = f"{gps_lat:.6f},{gps_lon:.6f} {radius_meters / 1000.0:.3f}"

        # Parameter tags for drift velocity and corridor
        p_corridor = ET.SubElement(info, "parameter")
        ET.SubElement(p_corridor, "valueName").text = "corridor_id"
        ET.SubElement(p_corridor, "value").text = str(alert_payload.get("id", "RC-01"))

        p_conf = ET.SubElement(info, "parameter")
        ET.SubElement(p_conf, "valueName").text = "detection_confidence"
        ET.SubElement(p_conf, "value").text = f"{alert_payload.get('confidence', 0.0):.2f}"

        return ET.tostring(root, encoding="utf-8", xml_declaration=True).decode("utf-8")

    async def dispatch_to_cad(
        self,
        alert_payload: Dict[str, Any],
        gps_lat: float = 15.5492,
        gps_lon: float = 73.7535,
    ) -> Dict[str, Any]:
        """
        Dispatches CAP v1.2 XML payload to municipal CAD endpoint.
        Logs incident in local audit database.
        """
        cap_xml = self.generate_cap_v12_xml(alert_payload, gps_lat, gps_lon)
        incident_id = f"CAD-{int(time.time())}-{uuid.uuid4().hex[:6].upper()}"

        status = CADIncidentStatus.REPORTED
        delivered = False

        if self.cad_url:
            try:
                async with httpx.AsyncClient(timeout=4.0) as client:
                    res = await client.post(
                        self.cad_url,
                        content=cap_xml,
                        headers={"Content-Type": "application/xml"},
                    )
                    delivered = res.status_code in (200, 201, 202)
                    status = CADIncidentStatus.DISPATCHED if delivered else CADIncidentStatus.REPORTED
            except Exception:
                delivered = False

        incident_record = {
            "cad_incident_id": incident_id,
            "status": status,
            "delivered_to_cad_endpoint": delivered,
            "cad_url": self.cad_url or "LOCAL_CAD_BUFFER",
            "cap_xml": cap_xml,
            "timestamp": time.time(),
        }
        self.incident_history.append(incident_record)
        return incident_record


default_cad_dispatcher = CADDispatcher()
