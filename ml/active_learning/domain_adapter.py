"""
RipGuard Geographic & Environmental Domain Adapter
Solves visual domain shift across diverse coastal geographies:
  - Volcanic Black Sand (Hawaii, Iceland, Bali, New Zealand)
  - Pebble / Shingle beaches (UK, Mediterranean)
  - Estuarine / Turbid brown water coastlines
  - Standard Golden / Quartz Sand beaches

Provides:
  1. Automated beach archetype classification via color-space albedo & texture profiling.
  2. Domain-adapted CLAHE preprocessing in Lab color space to unmask rip sediment channels.
  3. Calibrated detection thresholds per coastal archetype.
  4. 14-day "Shadow Mode" harvesting for zero-false-alarm local commissioning.
"""

from enum import Enum
from typing import Dict, Any, Tuple
import cv2
import numpy as np


class BeachArchetype(str, Enum):
    GOLDEN_QUARTZ = "GOLDEN_QUARTZ"          # High-albedo tan/yellow sand (standard RipVIS)
    VOLCANIC_BLACK = "VOLCANIC_BLACK"        # Low-albedo basaltic sand (Hawaii, Iceland, Bali)
    PEBBLE_SHINGLE = "PEBBLE_SHINGLE"        # High-texture gray/brown gravel coastlines
    ESTUARINE_TURBID = "ESTUARINE_TURBID"    # Brown sediment-rich water, low clarity


class CoastalDomainAdapter:
    """
    Analyzes visual beach characteristics, normalizes domain-shifted imagery,
    and tunes inference thresholds to maintain precision across global beaches.
    """

    ARCHETYPE_THRESHOLDS = {
        BeachArchetype.GOLDEN_QUARTZ: {"confidence_thresh": 0.50, "clahe_clip": 2.0},
        BeachArchetype.VOLCANIC_BLACK: {"confidence_thresh": 0.45, "clahe_clip": 3.5},
        BeachArchetype.PEBBLE_SHINGLE: {"confidence_thresh": 0.52, "clahe_clip": 2.5},
        BeachArchetype.ESTUARINE_TURBID: {"confidence_thresh": 0.42, "clahe_clip": 4.0},
    }

    def __init__(self, shadow_mode_enabled: bool = False):
        self.shadow_mode = shadow_mode_enabled
        self.active_archetype = BeachArchetype.GOLDEN_QUARTZ
        self.harvested_shadow_samples: int = 0

    def classify_beach_archetype(self, bgr_frame: np.ndarray) -> Dict[str, Any]:
        """
        Classifies beach archetype by analyzing sand/water luminance, hue distribution,
        and textural gradient energy.
        """
        lab = cv2.cvtColor(bgr_frame, cv2.COLOR_BGR2LAB)
        l_channel = lab[:, :, 0]
        a_channel = lab[:, :, 1]
        b_channel = lab[:, :, 2]

        mean_l = float(np.mean(l_channel))
        mean_b = float(np.mean(b_channel))

        # Check for Volcanic Black Sand (very low luminance overall, dark sand baseline)
        if mean_l < 75.0:
            archetype = BeachArchetype.VOLCANIC_BLACK
        # Check for Estuarine / Turbid brown water (high yellowness/brownness in b channel)
        elif mean_b > 140.0:
            archetype = BeachArchetype.ESTUARINE_TURBID
        # Check for pebble/shingle (high texture variance, moderate luminance)
        elif float(np.std(l_channel)) > 60.0:
            archetype = BeachArchetype.PEBBLE_SHINGLE
        else:
            archetype = BeachArchetype.GOLDEN_QUARTZ

        self.active_archetype = archetype
        config = self.ARCHETYPE_THRESHOLDS[archetype]

        return {
            "archetype": archetype.value,
            "mean_luminance": round(mean_l, 1),
            "turbidity_index": round(mean_b, 1),
            "adapted_confidence_threshold": config["confidence_thresh"],
            "clahe_clip_limit": config["clahe_clip"],
            "shadow_mode_active": self.shadow_mode,
        }

    def adapt_frame(self, bgr_frame: np.ndarray) -> np.ndarray:
        """
        Applies archetype-adapted Contrast Limited Adaptive Histogram Equalization (CLAHE)
        in Lab color space to enhance rip current sediment plumes and foam edges.
        """
        config = self.ARCHETYPE_THRESHOLDS[self.active_archetype]
        clip_limit = config["clahe_clip"]

        lab = cv2.cvtColor(bgr_frame, cv2.COLOR_BGR2LAB)
        l, a, b = cv2.split(lab)

        clahe = cv2.createCLAHE(clipLimit=clip_limit, tileGridSize=(8, 8))
        l_enhanced = clahe.apply(l)

        enhanced_lab = cv2.merge([l_enhanced, a, b])
        enhanced_bgr = cv2.cvtColor(enhanced_lab, cv2.COLOR_LAB2BGR)
        return enhanced_bgr

    def evaluate_shadow_mode_sample(
        self,
        confidence: float,
        frame_rgb: np.ndarray,
    ) -> bool:
        """
        During 14-day initial beach trial, flags borderline samples (0.35 <= conf <= 0.65)
        for localized active learning harvesting without alarming public sirens.
        """
        if not self.shadow_mode:
            return False

        if 0.35 <= confidence <= 0.65:
            self.harvested_shadow_samples += 1
            return True
        return False
