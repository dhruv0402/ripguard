"""
RipGuard Optical Filters & Environmental Guards:
1. Sun Glint & Specular Reflection Masking:
   Detects high-luminance, low-saturation solar flares on the water surface and
   suppresses spurious optical flow noise. Flags when motorized Circular Polarizing (CPL)
   filter actuation is recommended.
2. Twilight / Low-Light Adaptive Denoising:
   Estimates high-gain sensor noise at dusk/dawn and applies edge-preserving filtering
   before Farnebäck optical flow calculation.
"""

from typing import Tuple, Dict, Any
import cv2
import numpy as np


class SunGlintFilter:
    """
    Identifies specular sun reflection / glint flares on ocean surface
    and suppresses corrupted optical flow vectors.
    """

    def __init__(
        self,
        luminance_threshold: int = 238,
        saturation_max: int = 40,
        glint_area_warning_pct: float = 12.0,
    ):
        self.lum_thresh = luminance_threshold
        self.sat_max = saturation_max
        self.glint_warning_pct = glint_area_warning_pct

    def compute_glint_mask(self, bgr_frame: np.ndarray) -> np.ndarray:
        """
        Generates a uint8 binary mask [0, 255] where 255 indicates solar specular glint.
        Uses HSV color space where glint presents as extreme brightness (V) + washed-out saturation (S).
        """
        hsv = cv2.cvtColor(bgr_frame, cv2.COLOR_BGR2HSV)
        sat = hsv[:, :, 1]
        val = hsv[:, :, 2]

        glint_binary = ((val >= self.lum_thresh) & (sat <= self.sat_max)).astype(np.uint8) * 255

        # Morphological dilation to encompass boundary shimmer halos
        kernel = cv2.getStructuringElement(cv2.MORPH_ELLIPSE, (5, 5))
        dilated = cv2.dilate(glint_binary, kernel, iterations=1)
        return dilated

    def suppress_flow_in_glint(
        self,
        flow: np.ndarray,
        glint_mask: np.ndarray,
        dampening_factor: float = 0.05,
    ) -> np.ndarray:
        """
        Dampens spurious optical flow velocities inside detected sun glare zones.
        flow: float32 array of shape (H, W, 2).
        """
        cleaned_flow = flow.copy()
        mask_bool = glint_mask > 0
        cleaned_flow[mask_bool] *= dampening_factor
        return cleaned_flow

    def analyze_glint_severity(self, bgr_frame: np.ndarray) -> Dict[str, Any]:
        """Calculates solar glare coverage percentage and alerts when CPL filter is required."""
        glint_mask = self.compute_glint_mask(bgr_frame)
        total_pixels = glint_mask.shape[0] * glint_mask.shape[1]
        glint_pixels = int(np.count_nonzero(glint_mask))
        glint_pct = round((glint_pixels / total_pixels) * 100.0, 2)

        requires_cpl = glint_pct >= self.glint_warning_pct

        return {
            "glint_coverage_pct": glint_pct,
            "requires_cpl_polarizer": requires_cpl,
            "status": "SEVERE_SPECULAR_GLARE" if requires_cpl else "NOMINAL_LIGHTING",
            "recommended_action": (
                "ENGAGE_MOTORIZED_CPL_FILTER" if requires_cpl else "CPL_PASSIVE"
            ),
        }


class TwilightAdaptivePreprocessor:
    """
    Analyzes ambient illumination and sensor noise at dusk/dawn (high swimmer risk hours).
    Applies edge-preserving denoising to prevent high ISO grain from triggering false optical flow.
    """

    TWILIGHT_LUM_THRESHOLD = 50.0  # Mean grayscale intensity below which twilight is active
    NOISE_VARIANCE_THRESHOLD = 180.0

    def __init__(self, twilight_threshold: float = TWILIGHT_LUM_THRESHOLD):
        self.twilight_thresh = twilight_threshold

    def analyze_scene_lighting(self, bgr_frame: np.ndarray) -> Dict[str, Any]:
        """Estimates mean scene illumination and high-frequency sensor noise."""
        gray = cv2.cvtColor(bgr_frame, cv2.COLOR_BGR2GRAY)
        mean_lum = float(np.mean(gray))

        # Estimate sensor grain noise using high-pass Laplacian variance
        laplacian = cv2.Laplacian(gray, cv2.CV_64F)
        noise_var = float(laplacian.var())

        is_twilight = mean_lum < self.twilight_thresh
        is_high_noise = noise_var > self.NOISE_VARIANCE_THRESHOLD

        if mean_lum < 20.0:
            sensor_mode = "NIGHT_IR_REQUIRED"
        elif is_twilight:
            sensor_mode = "TWILIGHT_DENOISING_ACTIVE"
        else:
            sensor_mode = "DAYLIGHT_STANDARD"

        return {
            "mean_luminance": round(mean_lum, 2),
            "noise_variance": round(noise_var, 2),
            "is_twilight": is_twilight,
            "is_high_noise": is_high_noise,
            "sensor_mode": sensor_mode,
        }

    def preprocess_for_optical_flow(
        self,
        curr_gray: np.ndarray,
        lighting_info: Dict[str, Any],
    ) -> np.ndarray:
        """
        If twilight / high sensor noise is detected, applies fast bilateral filtering
        to preserve wave edge sharpness while suppressing high-gain ISO noise grain.
        """
        if lighting_info["is_twilight"] or lighting_info["is_high_noise"]:
            # Bilateral filter preserves sharp rip channel boundaries while smoothing high-frequency noise
            denoised = cv2.bilateralFilter(curr_gray, d=5, sigmaColor=35, sigmaSpace=35)
            return denoised
        return curr_gray
