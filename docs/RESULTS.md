# RipGuard Model Evaluation & Analysis Results

## 1. Executive Summary & Philosophy

Rip current segmentation from video is an **active, unsolved computer vision research problem** (the focal topic of CVPR 2025 RipVIS and the NTIRE 2026 challenge). In coastal environments, rip currents lack rigid boundaries, morph dynamically with breaking surf, and are easily confounded by whitewater foam, sandbars, and shifting surface illumination.

RipGuard is designed as an honest decision-support tool. It does **not** claim to have solved rip current detection, nor does it present synthetic or inflated metrics. This document records the empirical results measured against the real CVPR 2025 **RipVIS** dataset.

---

## 2. Quantitative Benchmark Results

Model architecture evaluated:
- **Model:** U-Net with ResNet-34 encoder (ImageNet pretrained initialization)
- **Loss:** Combined Dice + Binary Cross-Entropy (BCE) Loss (\(0.5 \times \text{BCE} + 0.5 \times \text{Dice}\))
- **Optimizer:** AdamW (\(\text{lr}=10^{-4}\))
- **Input resolution:** \(512 \times 512\) px
- **Evaluation split:** RipVIS held-out test split (106 frames across diverse beach videos with both positive rip currents and negative control sequences)

### Measured Metrics across Model Iterations

| Benchmark Run / Model Version | Split & Scale | Mean IoU | Dice / F1 | Precision | Recall | Key Insights |
|---|---|---|---|---|---|---|
| **v1: `ripguard_unet_resnet34_v1`** | `ripvis_test` (106 frames) | **0.3211** | **0.4973** | **0.4554** | **0.5478** | Baseline single-frame U-Net with ResNet34 and DiceBCE loss. |
| **v2: `ripguard_unet_v2_augmented_expanded`** | `ripvis_test_expanded` (131 frames) | **0.2185** | **0.3072** | **0.2744** | **0.3490** | Evaluated on broader multi-beach test footage with complex breaking sandbars (`RipVIS-066`), illustrating significant out-of-distribution domain shift. |
| **v3: `ripguard_unet_v3_motion_farneback`** | `ripvis_test_expanded` (131 frames) | **0.1872** | **0.2851** | **0.2268** | **0.3838** | 5-channel spatio-temporal input `[RGB + vx + vy]` using dense Farnebäck optical flow. Flow channels boost seaward motion recall ($0.3838$ vs $0.3490$), but boundary noise from turbulent foam spray dampens single-pixel IoU precision. |

---

## 3. Qualitative Failure Mode Analysis: What the Model Gets Right vs. Wrong

Through inspecting video predictions and frame-level overlays, several distinct patterns emerge:

### What the Model Does Well
1. **Prominent Channel Identification:**
   When a rip current cuts a distinct, darker, or discolored channel through breaking sandbar surf, the model consistently predicts high confidence (>0.75) centered over the neck of the current.
2. **Negative Video Discrimination:**
   On calm water scenes without rip currents, predicted maximum confidence remains low (<0.25), avoiding spurious full-frame alerts.
3. **Temporal Window Clustering:**
   Using the inference post-processor's window aggregation (`_merge_into_windows`), transient single-frame spikes are smoothed out into discrete, actionable alert intervals.

### Failure Modes & Root Causes
1. **Whitewater / Foam Confusion (False Positives):**
   - *Observation:* The edges of heavy breaking waves where churning white foam collides with offshore currents often receive moderate confidence (0.45 – 0.60).
   - *Cause:* Static single-frame texture features for turbulent whitewater and agitated rip current heads have overlapping color histograms and high-frequency edge responses.
2. **Low-Contrast Rip Currents in Deep/Calm Water (False Negatives):**
   - *Observation:* Under overcast skies or in deeper water where the rip current manifests primarily as seaward surface velocity rather than color disruption, the model's confidence drops below the 0.50 detection threshold.
   - *Cause:* Static 2D CNNs cannot infer velocity or motion vectors. Rip currents are defined fundamentally by *water motion over time*, not static surface appearance alone.
3. **Sun Glint & Specular Reflection:**
   - *Observation:* Direct midday sun glint across wave troughs occasionally breaks up continuous segmentation masks into fragmented patches.

---

## 4. Key Recommendations for Future Iterations

1. **Temporal Context (Optical Flow / 3D CNN / Video Transformers):**
   Incorporating sequential frame deltas (e.g., optical flow or multi-frame temporal attention windows) would allow the network to separate seaward flow from landward wave propagation, drastically reducing whitewater false alarms.
2. **Temporal Confidence Aggregation (TCA):**
   Adopting the TCA post-processing method proposed in the CVPR 2025 RipVIS paper to enforce consistency across video timelines.
3. **Ensemble & Higher-Capacity Encoders:**
   Benchmarking ConvNeXt-Base or Swin-Transformer backbones once dedicated GPU infrastructure is provisioned.
