"""
RipGuard Planar Homography & Camera Frustum Calibration Engine:
Converts 2D video pixel detections (u, v) into real physical metric distances
(meters offshore, meters alongshore) and geographic GPS coordinates (latitude, longitude).
Calculates real physical seaward drift velocity (m/s) from optical displacement.

Supports both:
  1. 4-GCP (Ground Control Point) planar homography surveyed with RTK GPS on the beach,
     directly calibrating mounting height (h), tilt angle (theta), and 3x3 projective matrix.
  2. Analytical optical depression frustum projection as a baseline or fallback.
"""

import json
import math
from dataclasses import dataclass, asdict
from typing import Tuple, Dict, Any, List, Optional
import numpy as np
import cv2
import scipy.optimize as opt


@dataclass
class GCPPoint:
    """Surveyed Ground Control Point (GCP) on beach sand."""
    pixel_x: float
    pixel_y: float
    rtk_lat: float
    rtk_lon: float
    metric_x: Optional[float] = None  # alongshore distance (meters, right > 0)
    metric_y: Optional[float] = None  # offshore distance (meters seaward)
    label: str = "GCP"


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
        self.camera_lat = float(camera_lat)
        self.camera_lon = float(camera_lon)
        self.height = max(1.0, float(mounting_height_m))
        self.tilt_deg = float(tilt_angle_deg)
        self.tilt_rad = math.radians(self.tilt_deg)
        self.azimuth_deg = float(azimuth_deg)
        self.azimuth_rad = math.radians(self.azimuth_deg)
        self.focal_px = float(focal_length_px)

        # 4-GCP Calibration State
        self.homography_matrix: Optional[np.ndarray] = None
        self.inv_homography_matrix: Optional[np.ndarray] = None
        self.calibrated_from_gcps: bool = False
        self.reprojection_rmse_m: Optional[float] = None
        self.max_residual_m: Optional[float] = None
        self.calibrated_gcps: List[Dict[str, Any]] = []

        # Real-time Tidal Stage Offset (Delta Z_tide in meters)
        self.active_tide_delta_m: float = 0.0

    def set_active_tide_delta(self, delta_m: float):
        """Sets the active water level delta (meters) from tidal compensation."""
        self.active_tide_delta_m = float(delta_m)

    @property
    def effective_height(self) -> float:
        """Dynamic height above instantaneous water line: h_eff = base_height - delta_z_tide."""
        return max(1.0, round(self.height - self.active_tide_delta_m, 2))

    def calibrate_with_gcps(
        self,
        gcps: List[Dict[str, Any] | GCPPoint],
        img_w: int = 1920,
        img_h: int = 1080,
    ) -> Dict[str, Any]:
        """
        Calibrates mounting height (h), tilt angle (theta), and solves the 3x3 planar
        homography matrix H using 4 Ground Control Points (GCPs) surveyed with an RTK GPS.

        Each GCP provides:
          - pixel_x, pixel_y: pixel position in image coordinates [0, img_w], [0, img_h]
            (or normalized [0, 1] if <= 1.0).
          - rtk_lat, rtk_lon: RTK GPS coordinates (sub-centimeter accuracy).
          - metric_x (optional): surveyed alongshore distance from camera tower.
          - metric_y (optional): surveyed offshore distance from camera tower.
        """
        if len(gcps) < 4:
            raise ValueError(f"At least 4 Ground Control Points (GCPs) are required for homography calibration. Provided: {len(gcps)}")

        src_pixels = []
        dst_metrics = []
        parsed_gcps = []

        for gcp in gcps:
            gcp_dict = asdict(gcp) if isinstance(gcp, GCPPoint) else dict(gcp)
            px = float(gcp_dict["pixel_x"])
            py = float(gcp_dict["pixel_y"])

            # Support normalized coordinates [0, 1]
            if 0.0 <= px <= 1.0 and 0.0 <= py <= 1.0:
                px = px * img_w
                py = py * img_h

            rtk_lat = float(gcp_dict["rtk_lat"])
            rtk_lon = float(gcp_dict["rtk_lon"])

            # Compute metric coordinates (alongshore X, offshore Y) if not provided
            if gcp_dict.get("metric_x") is not None and gcp_dict.get("metric_y") is not None:
                mx = float(gcp_dict["metric_x"])
                my = float(gcp_dict["metric_y"])
            else:
                mx, my = self.gps_to_local_metric(rtk_lat, rtk_lon)
                gcp_dict["metric_x"] = round(mx, 2)
                gcp_dict["metric_y"] = round(my, 2)

            src_pixels.append([px, py])
            dst_metrics.append([mx, my])
            parsed_gcps.append(gcp_dict)

        src_pts = np.array(src_pixels, dtype=np.float32)
        dst_pts = np.array(dst_metrics, dtype=np.float32)

        # 1. Solve 3x3 Planar Homography Matrix H: [s*X, s*Y, s]^T = H * [u, v, 1]^T
        H, _ = cv2.findHomography(src_pts, dst_pts, cv2.RANSAC if len(src_pixels) > 4 else 0)
        if H is None:
            raise RuntimeError("Failed to compute planar homography matrix from provided GCP coordinates.")

        inv_H = np.linalg.pinv(H)

        # 2. Compute Reprojection RMSE
        src_homo = np.hstack([src_pts, np.ones((len(src_pts), 1), dtype=np.float32)])
        proj_pts_unnorm = (H @ src_homo.T).T
        proj_pts = proj_pts_unnorm[:, :2] / proj_pts_unnorm[:, 2:3]

        residuals = np.linalg.norm(proj_pts - dst_pts, axis=1)
        rmse = float(np.sqrt(np.mean(residuals**2)))
        max_err = float(np.max(residuals))

        # 3. Fit camera extrinsics: Mounting Height (h) and Tilt Angle (theta)
        # Using non-linear least squares to fit: d_offshore = h / tan(theta + arctan((v - cy)/f))
        cy = img_h / 2.0
        v_coords = src_pts[:, 1]
        offshore_dists = dst_pts[:, 1]

        def extrinsics_loss(params):
            h_cand, tilt_cand_deg = params
            t_rad = math.radians(tilt_cand_deg)
            err = 0.0
            for v, d in zip(v_coords, offshore_dists):
                d_theta = math.atan2(v - cy, self.focal_px)
                dep = t_rad + d_theta
                if dep <= math.radians(1.0) or dep >= math.radians(88.0):
                    return 1e6
                pred_d = h_cand / math.tan(dep)
                err += (pred_d - d) ** 2
            return err

        init_guess = [self.height, self.tilt_deg]
        res = opt.minimize(
            extrinsics_loss,
            x0=init_guess,
            bounds=[(2.0, 50.0), (3.0, 85.0)],
            method="L-BFGS-B",
        )

        calibrated_h = round(float(res.x[0]), 2)
        calibrated_tilt = round(float(res.x[1]), 2)

        # Update calibrator state
        self.height = calibrated_h
        self.tilt_deg = calibrated_tilt
        self.tilt_rad = math.radians(calibrated_tilt)
        self.homography_matrix = H
        self.inv_homography_matrix = inv_H
        self.calibrated_from_gcps = True
        self.reprojection_rmse_m = round(rmse, 3)
        self.max_residual_m = round(max_err, 3)
        self.calibrated_gcps = parsed_gcps

        return {
            "status": "calibrated",
            "gcp_count": len(parsed_gcps),
            "calibrated_height_m": calibrated_h,
            "calibrated_tilt_deg": calibrated_tilt,
            "reprojection_rmse_m": self.reprojection_rmse_m,
            "max_residual_m": self.max_residual_m,
            "certified_for_field_trials": bool(rmse < 0.75),
            "homography_matrix": H.tolist(),
        }

    def gps_to_local_metric(self, lat: float, lon: float) -> Tuple[float, float]:
        """
        Converts RTK GPS coordinate into local metric coordinates relative to camera tower:
          - lateral_offset_m (alongshore X, positive = right)
          - offshore_distance_m (seaward Y, positive = offshore)
        """
        # 1 deg latitude ≈ 111,320 meters
        dy_north = (lat - self.camera_lat) * 111320.0
        # 1 deg longitude ≈ 111,320 * cos(lat) meters
        dx_east = (lon - self.camera_lon) * (111320.0 * math.cos(math.radians(self.camera_lat)))

        # Project onto camera azimuth orientation (270 deg = West)
        # Seaward component vector
        seaward_y = dx_east * math.sin(self.azimuth_rad) + dy_north * math.cos(self.azimuth_rad)
        # Alongshore component vector (perpendicular to azimuth)
        alongshore_x = dx_east * math.cos(self.azimuth_rad) - dy_north * math.sin(self.azimuth_rad)

        return alongshore_x, seaward_y

    def pixel_to_metric_distance(
        self,
        norm_x: float,
        norm_y: float,
        img_w: int = 1920,
        img_h: int = 1080,
    ) -> Dict[str, Any]:
        """
        Maps normalized bounding box centroid (norm_x in [0,1], norm_y in [0,1])
        to metric coordinates relative to the camera tower base:
          - offshore_distance_m: seaward perpendicular distance from beach baseline.
          - lateral_offset_m: alongshore distance (positive = north/right, negative = south/left).
          - direct_range_m: Euclidean 3D distance from tower.
        """
        px = norm_x * img_w
        py = norm_y * img_h

        # If 4-GCP planar homography is calibrated, use the direct projective matrix H
        if self.homography_matrix is not None:
            vec = np.array([px, py, 1.0], dtype=np.float32)
            proj = self.homography_matrix @ vec
            s = proj[2] if abs(proj[2]) > 1e-6 else 1e-6
            lateral_offset = float(proj[0] / s)
            offshore_distance = float(proj[1] / s)

            # Keep values physically plausible
            offshore_distance = max(1.0, offshore_distance)
            # Direct range incorporates instantaneous effective water-line height
            direct_range = math.sqrt(offshore_distance**2 + lateral_offset**2 + self.effective_height**2)

            return {
                "offshore_distance_m": round(offshore_distance, 1),
                "lateral_offset_m": round(lateral_offset, 1),
                "direct_range_m": round(direct_range, 1),
                "method": "planar_homography_4gcp",
                "calibration_rmse_m": self.reprojection_rmse_m,
                "effective_height_m": self.effective_height,
                "tide_delta_m": round(self.active_tide_delta_m, 2),
            }

        # Otherwise, fall back to analytical optical depression frustum model
        px_centered = (norm_x - 0.5) * img_w
        py_centered = (norm_y - 0.5) * img_h

        d_theta = math.atan2(py_centered, self.focal_px)
        total_depression = self.tilt_rad + d_theta
        total_depression = max(math.radians(2.0), min(math.radians(88.0), total_depression))

        ground_range = self.effective_height / math.tan(total_depression)
        d_phi = math.atan2(px_centered, self.focal_px)
        lateral_offset = ground_range * math.tan(d_phi)
        direct_range = math.sqrt(ground_range**2 + lateral_offset**2 + self.effective_height**2)

        return {
            "offshore_distance_m": round(ground_range, 1),
            "lateral_offset_m": round(lateral_offset, 1),
            "direct_range_m": round(direct_range, 1),
            "method": "analytical_frustum",
            "effective_height_m": self.effective_height,
            "tide_delta_m": round(self.active_tide_delta_m, 2),
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

        # Perpendicular alongshore component vector
        alongshore_azimuth = self.azimuth_rad + math.pi / 2.0
        dx_lateral = lateral_offset_m * math.sin(alongshore_azimuth)
        dy_lateral = lateral_offset_m * math.cos(alongshore_azimuth)

        total_dx = dx_seaward + dx_lateral  # East-West displacement (meters)
        total_dy = dy_seaward + dy_lateral  # North-South displacement (meters)

        delta_lat = total_dy / 111320.0
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

    def to_dict(self) -> Dict[str, Any]:
        """Serializes calibration profile to dictionary."""
        return {
            "camera_lat": self.camera_lat,
            "camera_lon": self.camera_lon,
            "mounting_height_m": self.height,
            "tilt_angle_deg": self.tilt_deg,
            "azimuth_deg": self.azimuth_deg,
            "focal_length_px": self.focal_px,
            "calibrated_from_gcps": self.calibrated_from_gcps,
            "reprojection_rmse_m": self.reprojection_rmse_m,
            "max_residual_m": self.max_residual_m,
            "homography_matrix": self.homography_matrix.tolist() if self.homography_matrix is not None else None,
            "gcps": self.calibrated_gcps,
        }

    @classmethod
    def from_dict(cls, data: Dict[str, Any]) -> "BeachCameraCalibrator":
        """Instantiates a BeachCameraCalibrator from serialized profile dict."""
        calibrator = cls(
            camera_lat=data.get("camera_lat", 15.5492),
            camera_lon=data.get("camera_lon", 73.7535),
            mounting_height_m=data.get("mounting_height_m", 12.0),
            tilt_angle_deg=data.get("tilt_angle_deg", 16.5),
            azimuth_deg=data.get("azimuth_deg", 270.0),
            focal_length_px=data.get("focal_length_px", 850.0),
        )
        if data.get("homography_matrix"):
            calibrator.homography_matrix = np.array(data["homography_matrix"], dtype=np.float32)
            calibrator.inv_homography_matrix = np.linalg.pinv(calibrator.homography_matrix)
            calibrator.calibrated_from_gcps = bool(data.get("calibrated_from_gcps", True))
            calibrator.reprojection_rmse_m = data.get("reprojection_rmse_m")
            calibrator.max_residual_m = data.get("max_residual_m")
            calibrator.calibrated_gcps = data.get("gcps", [])
        return calibrator


# Default calibrator instance for coastal surveillance
default_beach_calibrator = BeachCameraCalibrator()
