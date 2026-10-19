"""
RipGuard Planar Homography & Camera Frustum Calibration Engine:
Converts 2D video pixel detections (u, v) into real physical metric distances
(meters offshore, meters alongshore) and geographic GPS coordinates (latitude, longitude).
Calculates real physical seaward drift velocity (m/s) from optical displacement.
"""

import math
from typing import Tuple, Dict, Any, Optional
import numpy as np


class BeachCameraCalibrator:
    def __init__(
        self,
        camera_lat: float = 15.5492,
        camera_lon: float = 73.7535,
        mounting_height_m: float = 12.0,
        tilt_angle_deg: float = 16.5,
        azimuth_deg: float = 270.0,  # 270 deg = West (seaward facing)
        focal_length_px: float = 850.0,
    ):
        self.camera_lat = camera_lat
        self.camera_lon = camera_lon
        self.height = max(1.0, mounting_height_m)
        self.tilt_rad = math.radians(tilt_angle_deg)
        self.azimuth_rad = math.radians(azimuth_deg)
        self.focal_px = focal_length_px

    def pixel_to_metric_distance(
        self,
        norm_x: float,
        norm_y: float,
        img_w: int = 1920,
        img_h: int = 1080,
    ) -> Dict[str, float]:
        """
        Maps normalized bounding box centroid (norm_x in [0,1], norm_y in [0,1])
        to metric coordinates relative to the camera tower base:
          - offshore_distance_m: seaward perpendicular distance from beach baseline.
          - lateral_offset_m: alongshore distance (positive = north/right, negative = south/left).
          - direct_range_m: Euclidean 3D distance from tower.
        """
        # Pixel coordinates centered at optical principal point
        px_x = (norm_x - 0.5) * img_w
        px_y = (norm_y - 0.5) * img_h

        # Optical depression angle calculation
        # norm_y near 1.0 (bottom of screen) is close to shore; norm_y near 0.0 (top) is far offshore
        d_theta = math.atan2(px_y, self.focal_px)
        total_depression = self.tilt_rad + d_theta

        # Avoid singularity near or above horizon
        total_depression = max(math.radians(2.0), min(math.radians(88.0), total_depression))

        # Ground range (meters offshore)
        ground_range = self.height / math.tan(total_depression)

        # Azimuthal angle deflection
        d_phi = math.atan2(px_x, self.focal_px)
        lateral_offset = ground_range * math.tan(d_phi)

        direct_range = math.sqrt(ground_range**2 + lateral_offset**2 + self.height**2)

        return {
            "offshore_distance_m": round(ground_range, 1),
            "lateral_offset_m": round(lateral_offset, 1),
            "direct_range_m": round(direct_range, 1),
        }

    def metric_to_gps(
        self,
        offshore_distance_m: float,
        lateral_offset_m: float,
    ) -> Tuple[float, float]:
        """
        Transforms local metric coordinates (offshore, lateral) into GPS latitude & longitude.
        Assumes spherical Earth approximation (WGS84 local meter scaling).
        """
        # Seaward component vector
        dx_seaward = offshore_distance_m * math.sin(self.azimuth_rad)
        dy_seaward = offshore_distance_m * math.cos(self.azimuth_rad)

        # Perpendicular alongshore component vector (azimuth + 90 deg)
        alongshore_azimuth = self.azimuth_rad + math.pi / 2.0
        dx_lateral = lateral_offset_m * math.sin(alongshore_azimuth)
        dy_lateral = lateral_offset_m * math.cos(alongshore_azimuth)

        total_dx = dx_seaward + dx_lateral  # East-West displacement (meters)
        total_dy = dy_seaward + dy_lateral  # North-South displacement (meters)

        # 1 deg latitude ≈ 111,320 meters
        delta_lat = total_dy / 111320.0
        # 1 deg longitude ≈ 111,320 * cos(lat) meters
        delta_lon = total_dx / (111320.0 * math.cos(math.radians(self.camera_lat)))

        target_lat = round(self.camera_lat + delta_lat, 6)
        target_lon = round(self.camera_lon + delta_lon, 6)
        return target_lat, target_lon

    def calculate_physical_drift_speed(
        self,
        pixel_velocity_y_per_sec: float,
        norm_y: float,
        img_h: int = 1080,
    ) -> float:
        """
        Converts pixel vertical displacement per second into real physical drift velocity (m/s).
        Accounts for perspective projection scale elongation at increasing offshore distances.
        """
        metric_current = self.pixel_to_metric_distance(0.5, norm_y, img_h=img_h)
        norm_y_next = max(0.01, norm_y - abs(pixel_velocity_y_per_sec) / img_h)
        metric_next = self.pixel_to_metric_distance(0.5, norm_y_next, img_h=img_h)

        delta_m = abs(metric_next["offshore_distance_m"] - metric_current["offshore_distance_m"])
        return round(min(3.5, max(0.2, delta_m)), 2)


# Default calibrator instance for coastal surveillance
default_beach_calibrator = BeachCameraCalibrator()
