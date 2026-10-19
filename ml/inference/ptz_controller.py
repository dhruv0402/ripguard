"""
RipGuard PTZ Camera Controller & Dynamic Homography Engine
Manages Pan-Tilt-Zoom (PTZ) cameras deployed on beach lifeguard towers.

Key Capabilities:
  1. Automated Home-Preset Watchdog: If an operator manually pans/zooms to inspect
     swimmers, an inactivity timer automatically commands the camera to return
     to the calibrated "SURF_HOMOGRAPHY_HOME" preset after N seconds.
  2. Dynamic Homography Rotation & Focal Scaling:
     When the camera pans (Delta_psi), tilts (Delta_theta), or zooms (scale z),
     dynamically updates the planar homography matrix H in real time:
       H_active = H_home @ K_0 @ R^T(Delta_psi, Delta_theta) @ inv(K_z)
     ensuring distance and GPS mapping remain accurate while camera is actively moving.
  3. Protocol Support: ONVIF Profile S XML / Pelco-D serial / REST simulation.
"""

import math
import time
from typing import Dict, Any, Tuple, Optional
import numpy as np


class PTZController:
    """
    Controls beach PTZ camera presets, manages the automated return-to-home watchdog,
    and dynamically re-projects homography under pan, tilt, and zoom movements.
    """

    HOME_PRESET_NAME = "SURF_HOMOGRAPHY_HOME"

    def __init__(
        self,
        base_homography_matrix: Optional[np.ndarray] = None,
        focal_length_px: float = 850.0,
        img_w: int = 1920,
        img_h: int = 1080,
        home_timeout_sec: float = 60.0,
    ):
        self.H_home = (
            base_homography_matrix.copy()
            if base_homography_matrix is not None
            else np.eye(3, dtype=np.float32)
        )
        self.f0 = float(focal_length_px)
        self.img_w = img_w
        self.img_h = img_h
        self.home_timeout_sec = float(home_timeout_sec)

        # Active PTZ State (relative to calibrated home preset)
        self.current_pan_deg: float = 0.0
        self.current_tilt_deg: float = 0.0
        self.current_zoom_ratio: float = 1.0  # 1.0 = 1x optical zoom at calibration
        self.last_operator_action_time: float = time.time()
        self.is_at_home_preset: bool = True

    def set_base_homography(self, H: np.ndarray):
        """Sets the calibrated 4-GCP homography matrix measured at the Home preset."""
        self.H_home = H.copy()

    def update_ptz_state(
        self,
        pan_delta_deg: float,
        tilt_delta_deg: float,
        zoom_ratio: float = 1.0,
    ):
        """
        Updates relative PTZ state from camera encoder telemetry or operator joystick.
        Resets operator inactivity watchdog timer.
        """
        self.current_pan_deg = float(pan_delta_deg)
        self.current_tilt_deg = float(tilt_delta_deg)
        self.current_zoom_ratio = max(0.5, float(zoom_ratio))
        self.last_operator_action_time = time.time()
        self.is_at_home_preset = (
            abs(self.current_pan_deg) < 0.2
            and abs(self.current_tilt_deg) < 0.2
            and abs(self.current_zoom_ratio - 1.0) < 0.02
        )

    def check_home_preset_watchdog(self) -> Dict[str, Any]:
        """
        Evaluates operator inactivity. If camera has been left in a custom orientation
        longer than home_timeout_sec, commands automated return to calibrated Home preset.
        """
        now = time.time()
        elapsed_since_action = now - self.last_operator_action_time

        if not self.is_at_home_preset and elapsed_since_action >= self.home_timeout_sec:
            # Trigger automated return to home
            self.command_goto_preset(self.HOME_PRESET_NAME)
            return {
                "action_taken": "AUTONOMOUS_RETURN_TO_HOME",
                "reason": f"Operator inactive for {elapsed_since_action:.1f}s",
                "preset": self.HOME_PRESET_NAME,
                "is_at_home": True,
            }

        return {
            "action_taken": "NONE",
            "is_at_home": self.is_at_home_preset,
            "seconds_until_home_reset": max(0.0, round(self.home_timeout_sec - elapsed_since_action, 1)),
        }

    def command_goto_preset(self, preset_name: str = HOME_PRESET_NAME) -> Dict[str, Any]:
        """Commands PTZ hardware to slew directly to specified preset."""
        if preset_name == self.HOME_PRESET_NAME:
            self.current_pan_deg = 0.0
            self.current_tilt_deg = 0.0
            self.current_zoom_ratio = 1.0
            self.is_at_home_preset = True
            self.last_operator_action_time = time.time()

        return {
            "command": "GOTO_PRESET",
            "preset": preset_name,
            "pan_deg": self.current_pan_deg,
            "tilt_deg": self.current_tilt_deg,
            "zoom_ratio": self.current_zoom_ratio,
            "timestamp": time.time(),
        }

    def compute_dynamic_homography(self) -> np.ndarray:
        """
        Dynamically calculates the adjusted planar homography matrix H_active
        based on current pan, tilt, and zoom displacements from home:
          K_0: intrinsic matrix at calibration
          K_z: intrinsic matrix at current zoom
          R: 3D rotation matrix for (delta_pan, delta_tilt)
          H_active = H_home @ K_0 @ R^T @ inv(K_z)
        """
        if self.is_at_home_preset:
            return self.H_home.copy()

        cx = self.img_w / 2.0
        cy = self.img_h / 2.0
        f0 = self.f0
        fz = self.f0 * self.current_zoom_ratio

        # Intrinsic calibration matrix K_0
        K_0 = np.array([
            [f0, 0.0, cx],
            [0.0, f0, cy],
            [0.0, 0.0, 1.0],
        ], dtype=np.float32)

        # Current intrinsic matrix K_z
        K_z = np.array([
            [fz, 0.0, cx],
            [0.0, fz, cy],
            [0.0, 0.0, 1.0],
        ], dtype=np.float32)
        inv_K_z = np.linalg.inv(K_z)

        # 3D Rotation matrix R(pan, tilt)
        pan_rad = math.radians(self.current_pan_deg)
        tilt_rad = math.radians(self.current_tilt_deg)

        # R_y (pan around vertical axis)
        R_pan = np.array([
            [math.cos(pan_rad), 0.0, math.sin(pan_rad)],
            [0.0, 1.0, 0.0],
            [-math.sin(pan_rad), 0.0, math.cos(pan_rad)],
        ], dtype=np.float32)

        # R_x (tilt around horizontal axis)
        R_tilt = np.array([
            [1.0, 0.0, 0.0],
            [0.0, math.cos(tilt_rad), -math.sin(tilt_rad)],
            [0.0, math.sin(tilt_rad), math.cos(tilt_rad)],
        ], dtype=np.float32)

        R_total = R_tilt @ R_pan

        # H_active maps current moved pixels back to ground plane
        # [s*X, s*Y, s]^T = H_home * K_0 * R^T * inv(K_z) * [u_curr, v_curr, 1]^T
        H_dynamic = self.H_home @ K_0 @ R_total.T @ inv_K_z
        return H_dynamic.astype(np.float32)
