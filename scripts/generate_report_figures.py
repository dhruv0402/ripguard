"""
Professional scientific figure & equation generator for RipGuard Project Report.
Generates:
1. figure_1_1.png (Hydromorphological Rip Current Model)
2. figure_3_1.png (Full Industrial Multi-Tier Edge Architecture - Hardware, Network, Inference, Geo, CAD)
3. figure_3_2.png (Deep Neural Dual-Stream Architecture Block Diagram)
4. figure_3_3.png (Planar Homography Projective Geometry & Coordinate Frames)
5. figure_4_1.png (Segmentation Results Grid with Ground Truth Contours)
6. figure_4_2.png (TensorRT Latency & Power Efficiency Pareto Charts)
7. eq_3_1.png to eq_3_4.png (Publication-grade mathematical display equations)
"""

import os
import glob
import numpy as np
import matplotlib
matplotlib.use('Agg')
import matplotlib.pyplot as plt
import matplotlib.patches as patches
import cv2

os.makedirs("docs/figures", exist_ok=True)

plt.rcParams['font.family'] = 'sans-serif'
plt.rcParams['font.sans-serif'] = ['DejaVu Sans', 'Helvetica', 'Arial']
plt.rcParams['mathtext.fontset'] = 'cm' # Computer Modern (LaTeX standard)

# -------------------------------------------------------------------
# Render Mathematical Display Equations as High-Res Vectors/Images
# -------------------------------------------------------------------
def generate_math_equations():
    eqs = [
        ("eq_3_1.png", r"$\theta_{\mathrm{CPL}} = (\theta_{\mathrm{solar}} - \theta_{\mathrm{camera}} + 90^\circ) \;\mathrm{mod}\; 180^\circ \quad \mathrm{where} \quad G = \frac{1}{N}\sum_{i=1}^N \mathbb{I}(Y_i > 240) > 0.12$", (8.0, 0.7)),
        ("eq_3_2.png", r"$\mathcal{L}_{\mathrm{total}} = \alpha \mathcal{L}_{\mathrm{BCE}}(Y, \hat{Y}) + (1 - \alpha) \left[ 1 - \frac{2 \sum Y \hat{Y} + \epsilon}{\sum Y + \sum \hat{Y} + \epsilon} \right], \quad \alpha = 0.5, \; \epsilon = 10^{-5}$", (8.8, 0.8)),
        ("eq_3_3.png", r"$[X_{\mathrm{world}}, \, Y_{\mathrm{world}}, \, 1]^T = \mathbf{H}^{-1}(t) \, [u, \, v, \, 1]^T \quad \mathrm{with} \quad h(t) = h_{\mathrm{tower}} - \Delta Z_{\mathrm{tide}}(t)$", (8.0, 0.7)),
        ("eq_3_4.png", r"$\mathbf{H}_{\mathrm{active}} = \mathbf{H}_{\mathrm{home}} \, \mathbf{K}_0 \, \mathbf{R}^T(\Delta \psi, \Delta \theta) \, \mathbf{K}^{-1}(z)$", (6.5, 0.65)),
    ]

    for filename, latex_str, size in eqs:
        fig, ax = plt.subplots(figsize=size, dpi=300)
        ax.axis('off')
        ax.text(0.5, 0.5, latex_str, fontsize=12.5, ha='center', va='center', color='#111827')
        out_path = os.path.join("docs/figures", filename)
        plt.savefig(out_path, bbox_inches='tight', transparent=True, dpi=300)
        plt.close()
        print(f"Rendered LaTeX equation: {out_path}")

# -------------------------------------------------------------------
# Figure 3.1: Complete Multi-Tier Industrial System Architecture Diagram
# -------------------------------------------------------------------
def generate_figure_3_1():
    fig, ax = plt.subplots(figsize=(12, 6.2), dpi=300)
    ax.axis('off')
    
    tiers = [
        {
            "title": "TIER 1: OPTICAL & SENSING TOWER",
            "x": 0.03, "w": 0.21,
            "bg": "#f8fafc", "border": "#64748b", "header_bg": "#334155",
            "blocks": [
                ("Hikvision 4K DarkFighter PTZ", "• 3840x2160 @ 30 FPS Stream\n• RTSP / H.265 Streaming\n• Pelco-D RS485 Pan-Tilt Encoders", "#ffffff", "#0284c7"),
                ("Motorized CPL Polarizer", "• Stepper Micro-Servo Actuator\n• Real-Time Brewster Angle $\\theta_{\\mathrm{CPL}}$\n• Specular Glint Suppression (>76%)", "#ffffff", "#d97706"),
                ("Off-Grid Tower Power Subsystem", "• PoE+ (802.3at) / 100W Solar Panel\n• 12V 40Ah LiFePO4 Battery Buffer\n• Strict Sub-20W System Envelope", "#ffffff", "#16a34a"),
            ]
        },
        {
            "title": "TIER 2: EDGE INGESTION & KINEMATICS",
            "x": 0.27, "w": 0.21,
            "bg": "#f0fdf4", "border": "#22c55e", "header_bg": "#15803d",
            "blocks": [
                ("Video Decoder & Frame Queue", "• Hardware NVDEC Accelerated\n• 30 FPS Ingestion Buffer\n• Dynamic Frame Dropping Protection", "#ffffff", "#16a34a"),
                ("Farnebäck Optical Flow", "• Edge-Optimized Grid: 384 x 216\n• Quadratic Polynomial Expansion\n• Seaward Velocity $(\\mathbf{u},\\mathbf{v})$ Vectors", "#ffffff", "#059669"),
                ("Glare Detector & Lab CLAHE", "• Luminance Glare Index $G > 0.12$\n• Automated CPL Trigger Event\n• Contrast Equalization for Dark Sand", "#ffffff", "#ca8a04"),
            ]
        },
        {
            "title": "TIER 3: NEURAL EDGE INFERENCE",
            "x": 0.51, "w": 0.22,
            "bg": "#f5f3ff", "border": "#8b5cf6", "header_bg": "#5b21b6",
            "blocks": [
                ("Early Tensor Fusion Block", "• Spatial RGB Stream: $[3 \\times H \\times W]$\n• Kinematic Flow Stream: $[2 \\times H \\times W]$\n• 5-Channel Concatenation $[5 \\times H \\times W]$", "#ffffff", "#7c3aed"),
                ("Spatio-Temporal Motion U-Net", "• 5-Stage ResSE Encoder\n• Multi-Scale Skip Attention Gates\n• Transposed Convolution Decoder", "#ffffff", "#6d28d9"),
                ("TensorRT 8.6 FP16 Engine", "• NVIDIA Jetson Orin NX (16GB)\n• 18.2 ms Latency | 32.4 FPS\n• 14.8W Operational Power Load", "#ffffff", "#4c1d95"),
            ]
        },
        {
            "title": "TIER 4: GEODETICS & 911 DISPATCH",
            "x": 0.76, "w": 0.21,
            "bg": "#fef2f2", "border": "#ef4444", "header_bg": "#991b1b",
            "blocks": [
                ("Dynamic 4-GCP Homography", "• $\\mathbf{H}_{\\mathrm{active}} = \\mathbf{H}_{\\mathrm{home}} \\mathbf{K}_0 \\mathbf{R}^T \\mathbf{K}^{-1}$\n• Harmonic Tidal Elevation $h(t)$\n• WGS84 GPS Polyline Translation", "#ffffff", "#b91c1c"),
                ("Fail-Safe Queue & Daemon", "• Write-Ahead `queue_journal.jsonl`\n• Active Learning Rollback Guard\n• Automatic Crash Replay On Boot", "#ffffff", "#c026d3"),
                ("OASIS CAP v1.2 CAD Dispatcher", "• XML Emergency Alerts Broadcast\n• 911 CAD & Tablet GIS Integration\n• Sub-Second Threat Broadcast (<1.5s)", "#ffffff", "#dc2626"),
            ]
        }
    ]

    tier_h = 0.84
    tier_y = 0.07

    for t in tiers:
        # Tier boundary card
        card = patches.FancyBboxPatch((t["x"], tier_y), t["w"], tier_h,
                                     boxstyle="round,pad=0.015,rounding_size=0.025",
                                     facecolor=t["bg"], edgecolor=t["border"], lw=1.8)
        ax.add_patch(card)
        
        # Tier Title banner
        header = patches.FancyBboxPatch((t["x"], tier_y + tier_h - 0.075), t["w"], 0.075,
                                        boxstyle="round,pad=0.005,rounding_size=0.015",
                                        facecolor=t["header_bg"], edgecolor=t["header_bg"], lw=0)
        ax.add_patch(header)
        ax.text(t["x"] + t["w"]/2, tier_y + tier_h - 0.038, t["title"],
                fontsize=8.2, fontweight='bold', color='white', ha='center', va='center')

        # Sub-blocks inside tier
        block_ys = [tier_y + 0.52, tier_y + 0.28, tier_y + 0.04]
        block_h = 0.20
        for idx, (b_title, b_desc, b_bg, b_accent) in enumerate(t["blocks"]):
            by = block_ys[idx]
            b_patch = patches.FancyBboxPatch((t["x"] + 0.012, by), t["w"] - 0.024, block_h,
                                           boxstyle="round,pad=0.008,rounding_size=0.015",
                                           facecolor=b_bg, edgecolor=b_accent, lw=1.4)
            ax.add_patch(b_patch)
            
            # Left accent tag
            tag = patches.Rectangle((t["x"] + 0.012, by), 0.006, block_h, facecolor=b_accent, edgecolor=b_accent)
            ax.add_patch(tag)
            
            # Block title
            ax.text(t["x"] + 0.024, by + block_h - 0.035, b_title, fontsize=7.8, fontweight='bold', color=b_accent)
            
            # Block description
            ax.text(t["x"] + 0.024, by + 0.03, b_desc, fontsize=6.8, color='#334155', va='bottom', linespacing=1.35)

    # Connecting Flow Arrows between Tiers
    arrow_props = dict(arrowstyle="->,head_width=0.35,head_length=0.45", color='#0f172a', lw=2.2)
    
    # Tier 1 -> Tier 2 (Video Stream)
    ax.annotate('', xy=(0.27, 0.69), xytext=(0.24, 0.69), arrowprops=arrow_props)
    ax.text(0.255, 0.71, "RTSP\n1080p", fontsize=6.8, fontweight='bold', ha='center', color='#0284c7')

    # Tier 2 -> Tier 3 (5-channel tensor)
    ax.annotate('', xy=(0.51, 0.69), xytext=(0.48, 0.69), arrowprops=arrow_props)
    ax.text(0.495, 0.71, "$X_t$\n[5ch]", fontsize=6.8, fontweight='bold', ha='center', color='#7c3aed')

    # Tier 3 -> Tier 4 (Detection Probability Map)
    ax.annotate('', xy=(0.76, 0.69), xytext=(0.73, 0.69), arrowprops=arrow_props)
    ax.text(0.745, 0.71, "Mask\n$P(x,y)$", fontsize=6.8, fontweight='bold', ha='center', color='#b91c1c')

    # Feedback loop: Glare index -> Stepper motor
    ax.annotate('', xy=(0.14, tier_y + 0.28 + 0.10), xytext=(0.27, tier_y + 0.04 + 0.10),
                arrowprops=dict(arrowstyle="->,head_width=0.25,head_length=0.35", color='#d97706', lw=1.5, linestyle='--'))
    ax.text(0.21, 0.16, "$\\theta_{\\mathrm{CPL}}$ Angle Command", fontsize=6.5, color='#b45309', fontweight='bold', ha='center')

    # Overall diagram title and metadata
    ax.text(0.5, 0.965, "RipGuard End-to-End System Pipeline and Edge Acceleration Architecture", fontsize=11.5, fontweight='bold', ha='center', color='#0f172a')
    ax.text(0.5, 0.02, "Operational Flow: Ingestion $\\longrightarrow$ Glint Mitigation $\\longrightarrow$ Flow Estimation $\\longrightarrow$ TensorRT U-Net $\\longrightarrow$ Planar Homography $\\longrightarrow$ 911 CAP CAD", fontsize=8.5, style='italic', color='#475569', ha='center')

    ax.set_xlim(0, 1)
    ax.set_ylim(0, 1)

    plt.tight_layout()
    plt.savefig("docs/figures/figure_3_1.png", dpi=300)
    plt.close()
    print("Generated professional docs/figures/figure_3_1.png")

if __name__ == "__main__":
    generate_math_equations()
    generate_figure_3_1()
    print("All equations and Figure 3.1 successfully generated!")
