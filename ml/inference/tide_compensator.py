"""
RipGuard Tidal Stage Modulation Engine
Compensates for tidal height oscillations (Mean High Water / Mean Low Water)
that alter the vertical baseline height (h) between the beach camera tower
and the sea water surface in real-time.

Mathematical Foundation:
  True camera elevation above water surface:
      h_eff(t) = h_tower - Delta_Z_tide(t)

  Where Delta_Z_tide(t) is derived from:
    1. NOAA CO-OPS REST API or coastal tide station telemetry.
    2. Local harmonic tidal synthesis fallback:
       Delta_Z_tide(t) = (H_range / 2) * cos(2 * pi * (t - t_high) / T_semi_diurnal)
       with T_semi_diurnal = 12.42 hours (M2 principal lunar tide).
"""

import math
import time
from dataclasses import dataclass
from typing import Dict, Any, Optional
import httpx


@dataclass
class TideMeasurement:
    timestamp: float
    water_level_m: float  # water level relative to Mean Sea Level (MSL) or datum
    station_id: str
    datum: str
    source: str  # "noaa_api", "harmonic_model", or "manual_override"


class TidalCompensator:
    """
    Dynamically modulates camera mounting height h_eff(t) based on active tide height.
    Prevents 10-25% distance calculation distortion caused by rising or receding tides.
    """

    M2_PERIOD_HOURS = 12.4206  # Principal lunar semidiurnal tide constituent
    DEFAULT_TIDAL_RANGE_M = 2.2  # Standard spring tidal range in meters

    def __init__(
        self,
        base_mounting_height_m: float = 12.0,
        station_id: Optional[str] = "9410230",  # Example NOAA station
        datum: str = "MLLW",  # Mean Lower Low Water
        tidal_range_m: float = DEFAULT_TIDAL_RANGE_M,
    ):
        self.base_mounting_height = max(1.0, float(base_mounting_height_m))
        self.station_id = station_id
        self.datum = datum
        self.tidal_range_m = float(tidal_range_m)
        self.manual_override_m: Optional[float] = None
        self._cached_tide: Optional[TideMeasurement] = None
        self._last_fetch_time: float = 0.0

    def compute_harmonic_tide_height(self, epoch_time: Optional[float] = None) -> float:
        """
        Synthesizes harmonic water level when offline or station API is unreachable.
        Uses M2 lunar semidiurnal cycle:
          z(t) = (tidal_range / 2) * cos(2 * pi * (t / 12.42h))
        """
        t = epoch_time if epoch_time is not None else time.time()
        hours = t / 3600.0
        amplitude = self.tidal_range_m / 2.0
        # Phase oscillation
        phase = (2.0 * math.pi * hours) / self.M2_PERIOD_HOURS
        z_tide = amplitude * math.cos(phase)
        return round(z_tide, 3)

    async def fetch_noaa_tide(self, epoch_time: Optional[float] = None) -> Optional[float]:
        """
        Queries NOAA CO-OPS REST API for real-time verified water level.
        Falls back smoothly if offline or unavailable.
        """
        if not self.station_id:
            return None

        # Return cached measurement if fresh (< 10 minutes old)
        now = time.time()
        if self._cached_tide and (now - self._last_fetch_time) < 600:
            return self._cached_tide.water_level_m

        try:
            url = (
                "https://api.tidesandcurrents.noaa.gov/api/prod/datagetter"
                f"?date=latest&station={self.station_id}&product=water_level"
                f"&datum={self.datum}&time_zone=gmt&units=metric&application=ripguard&format=json"
            )
            async with httpx.AsyncClient(timeout=3.0) as client:
                res = await client.get(url)
                if res.status_code == 200:
                    data = res.json()
                    if "data" in data and len(data["data"]) > 0:
                        val = float(data["data"][0]["v"])
                        self._cached_tide = TideMeasurement(
                            timestamp=now,
                            water_level_m=val,
                            station_id=self.station_id,
                            datum=self.datum,
                            source="noaa_api",
                        )
                        self._last_fetch_time = now
                        return val
        except Exception:
            pass  # Fallback to harmonic model

        return None

    def get_current_tide(self, epoch_time: Optional[float] = None) -> TideMeasurement:
        """
        Returns active tide measurement using priority:
          1. Manual override (if set by beach operator).
          2. Cached NOAA API measurement (if available).
          3. Real-time harmonic tide synthesis.
        """
        t = epoch_time if epoch_time is not None else time.time()

        if self.manual_override_m is not None:
            return TideMeasurement(
                timestamp=t,
                water_level_m=round(self.manual_override_m, 3),
                station_id="manual",
                datum=self.datum,
                source="manual_override",
            )

        if self._cached_tide and (t - self._last_fetch_time) < 600:
            return self._cached_tide

        # Compute harmonic tide
        harmonic_z = self.compute_harmonic_tide_height(t)
        return TideMeasurement(
            timestamp=t,
            water_level_m=harmonic_z,
            station_id=self.station_id or "harmonic_synth",
            datum=self.datum,
            source="harmonic_model",
        )

    def get_effective_camera_height(self, epoch_time: Optional[float] = None) -> Dict[str, Any]:
        """
        Calculates real dynamic camera mounting height above instantaneous sea surface:
          h_eff = base_height - water_level_offset
        """
        tide = self.get_current_tide(epoch_time)
        h_eff = max(1.0, self.base_mounting_height - tide.water_level_m)

        return {
            "base_tower_height_m": self.base_mounting_height,
            "effective_camera_height_m": round(h_eff, 2),
            "water_level_delta_m": tide.water_level_m,
            "tide_source": tide.source,
            "datum": tide.datum,
            "timestamp": tide.timestamp,
        }

    def set_manual_override(self, water_level_m: Optional[float]):
        """Allows beach lifeguards to manually set active water level from visual tide poles."""
        self.manual_override_m = float(water_level_m) if water_level_m is not None else None
