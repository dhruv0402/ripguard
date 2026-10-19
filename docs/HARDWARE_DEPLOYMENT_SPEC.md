# RipGuard Commercial Field-Trial Hardware Deployment Specification

## 1. Physical Edge Enclosure (Lifeguard Tower Mounting)
* **Chassis Rating:** **IP67 / NEMA 4X** sealed marine enclosure.
* **Material Composition:** Anodized 6061-T6 Aluminum with polyester powder coat to resist marine salt fog corrosion (tested to **ASTM B117 1,000-hour** salt spray exposure).
* **Sealing:** Dual continuous Viton/silicone elastomer O-ring gaskets.
* **Fasteners:** All external bolts, glands, and mounting brackets forged from **Grade 316 Marine Stainless Steel**.
* **Breather Element:** Gore-Tex IP67 protective vent membrane to equalize internal/external atmospheric pressure differentials while preventing moisture ingress.

---

## 2. Thermal Dissipation Architecture & Direct Solar Soak Validation
* **Fanless Solid-State Cooling:** Moving parts (fans) fail within weeks in coastal environments due to salt crystallization. All heat rejection is strictly **fanless and solid-state**.
* **Heat Pipe Routing:** Direct copper heat spreader (0.3mm tolerance) seated on NVIDIA Jetson Orin SoC using high-conductivity thermal interface material (TIM $\ge 8.5\text{ W/m}\cdot\text{K}$), routing heat directly to external finned aluminum chassis.
* **Direct Tropical Sunlight Protocol:**
  * Tower ambient temperature range: **$35^\circ\text{C}$ to $42^\circ\text{C}$**.
  * Direct solar radiative flux: **$1,000\text{ W/m}^2$** (tropical peak irradiance).
  * Shielding: Double-walled ventilated aluminum sun shield over the primary chassis to deflect direct UV and radiative heat loading.
* **Thermal Throttling Protection ([`ml/inference/thermal_governor.py`](file:///Users/dhruvgourisaria/ripguard/ml/inference/thermal_governor.py)):**
  * Sub-20W Jetson Orin 15W mode maintains junction temperature $T_j \le 72^\circ\text{C}$ under nominal conditions.
  * Multi-stage throttling initiates at $75^\circ\text{C}$ (2x frame skipping) and $82^\circ\text{C}$ (emergency 4x frame skipping), ensuring SoC junction temperature never exceeds the $85^\circ\text{C}$ hardware safety limit.

---

## 3. Saline Air Protection & Conformal Coating
* **PCB Conformal Coating:** All printed circuit boards (carrier board, power conversion modules, and Jetson SOM) coated with **IPC-CC-830 certified Type UR (Polyurethane)** or **Type XY (Parylene C)** at 50–75 $\mu\text{m}$ thickness.
* **Connector Protection:** All external I/O (Ethernet, antenna, PTZ RS-485) routed via IP68 sealed M12 / RJ45 circular bayonet connectors with gold-plated pins ($50\mu\text{in}$ Au over Ni).

---

## 4. Electrical, Power & Surge Protection
* **Power Source:** Power over Ethernet (**PoE++ IEEE 802.3bt Type 4**, delivers up to 60W over Cat6A shielded cable) or localized 24V DC solar/battery bank.
* **Lightning & Surge Suppression:**
  * Dual-stage Gas Discharge Tube (GDT) and Bidirectional Transient Voltage Suppressor (TVS) diodes on all copper Ethernet pairs.
  * Rated to withstand **6kV / 3kA** common-mode lightning transients per IEC 61000-4-5.
  * Tower chassis bonded directly to beach tower earth ground rod ($< 10\ \Omega$ earth impedance).

---

## 5. Optical Sensors, Sun Glint & Twilight Filter Actuation
* **Optical Polarizer (CPL):** PTZ camera lens fitted with a motorized 52mm **Circular Polarizing (CPL)** filter driven by stepper motor or servo. When [`SunGlintFilter`](file:///Users/dhruvgourisaria/ripguard/ml/inference/optical_filters.py) detects specular coverage $> 12\%$, the camera rotates the CPL filter by $90^\circ$ relative to solar azimuth to extinguish glare.
* **Low-Light / Twilight Sensor:** Dual-sensor or automated IR-cut filter switching with high-sensitivity Sony STARVIS 2 CMOS sensor (0.001 lux capability) and edge bilateral denoising ([`TwilightAdaptivePreprocessor`](file:///Users/dhruvgourisaria/ripguard/ml/inference/optical_filters.py)).
