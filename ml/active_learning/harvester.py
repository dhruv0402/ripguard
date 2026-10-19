"""
RipGuard Active Learning & Hard-Negative Mining Pipeline (RLHF / Lifeguard-in-the-Loop)

Provides:
1. ActiveLearningHarvester: Aggregates lifeguard / operator feedback on false positives
   (boat wakes, sandbar shadows, wave breaks) and confirmed true positives into curated
   training manifests for iterative model fine-tuning (continuous learning).
2. EntropyUncertaintyScorer: Computes Shannon entropy over model probability maps to
   flag high-uncertainty regions that require human verification.
"""

import math
import numpy as np
from typing import Dict, Any, List


class EntropyUncertaintyScorer:
    """
    Computes spatial and temporal uncertainty of model predictions.
    Regions with probability close to 0.5 have maximum Shannon entropy:
        H(p) = -p * log2(p) - (1-p) * log2(1-p)
    """

    @staticmethod
    def compute_frame_uncertainty(prob_map: np.ndarray) -> float:
        """
        Computes the normalized mean Shannon entropy across high-activity pixels.
        Returns uncertainty in range [0.0, 1.0].
        """
        if prob_map.size == 0:
            return 0.0

        p = np.clip(prob_map, 1e-6, 1.0 - 1e-6)
        entropy_map = -(p * np.log2(p) + (1.0 - p) * np.log2(1.0 - p))
        
        # Focus on boundary/active zone (where p > 0.1)
        active_mask = p > 0.1
        if not np.any(active_mask):
            return 0.0

        mean_entropy = float(np.mean(entropy_map[active_mask]))
        return min(max(mean_entropy, 0.0), 1.0)


class ActiveLearningHarvester:
    """
    Mines feedback events to generate dataset manifests for continual model retraining.
    Separates hard negative examples (crucial for reducing false alarms in coastal surveillance)
    from confirmed true positives.
    """

    @staticmethod
    def compile_manifest(feedback_records: List[Dict[str, Any]]) -> Dict[str, Any]:
        """
        Takes raw feedback records and formats them into a structured dataset manifest
        compatible with RipVIS benchmark fine-tuning and hard negative mining.
        """
        hard_negatives = []
        confirmed_positives = []
        missed_rips = []

        for record in feedback_records:
            fb_type = record.get("feedback_type", "")
            item = {
                "feedback_id": str(record.get("id")),
                "session_id": str(record.get("session_id")),
                "detection_id": str(record.get("detection_id")) if record.get("detection_id") else None,
                "video_filename": record.get("video_filename", "unknown.mp4"),
                "timestamp_sec": float(record.get("timestamp_sec", 0.0)),
                "bounding_region": record.get("bounding_region"),
                "operator_notes": record.get("operator_notes"),
                "confidence_rating": record.get("confidence_rating"),
                "feedback_type": fb_type,
            }

            if "false_positive" in fb_type:
                hard_negatives.append(item)
            elif fb_type == "confirmed_true_positive":
                confirmed_positives.append(item)
            elif fb_type == "missed_detection":
                missed_rips.append(item)

        return {
            "summary": {
                "total_hard_negatives": len(hard_negatives),
                "total_confirmed_positives": len(confirmed_positives),
                "total_missed_detections": len(missed_rips),
                "retraining_ready": len(hard_negatives) + len(confirmed_positives) > 0,
            },
            "hard_negatives": hard_negatives,
            "confirmed_positives": confirmed_positives,
            "missed_detections": missed_rips,
        }
