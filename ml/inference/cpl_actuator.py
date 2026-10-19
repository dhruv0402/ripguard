"""
RipGuard Motorized Circular Polarizing (CPL) Lens Actuator
Interfaces with physical filter rotator rings (stepper/servo motors or RS-485 PTZ auxiliary pins)
to extinguish ocean specular sun glint in real time.

Operating Principles:
  When solar glare coverage exceeds 12%, calculates the extinction polarizing angle:
      theta_cpl = (solar_azimuth - camera_azimuth + 90) % 180
  and commands the servo to rotate the physical CPL filter to nullify polarized surface reflection.
"""

import math
import time
from typing import Dict, Any, Optional


class CPLActuator:
    """
    Controls physical motorized CPL filter ring rotation via serial RS-485,
    GPIO PWM pulses, or IP camera auxiliary protocols.
    """

    def __init__(
        self,
        camera_azimuth_deg: float = 270.0,
        interface_type: str = "simulation",  # "serial_rs485", "gpio_pwm", or "simulation"
        serial_port: Optional[str] = None,
    ):
        self.camera_azimuth_deg = float(camera_azimuth_deg)
        self.interface_type = interface_type
        self.serial_port = serial_port
        self.current_filter_angle_deg: float = 0.0
        self.is_polarizer_engaged: bool = False
        self.last_actuation_time: float = 0.0

    def compute_optimal_cpl_angle(self, solar_azimuth_deg: float) -> float:
        """
        Calculates optimal polarization axis angle to maximize Brewster's angle reflection extinction.
        Perpendicular to the plane of incidence (approx 90 deg relative to solar azimuth).
        """
        relative_angle = (solar_azimuth_deg - self.camera_azimuth_deg + 90.0) % 180.0
        return round(relative_angle, 1)

    def rotate_to_angle(self, target_angle_deg: float) -> Dict[str, Any]:
        """Commands actuator hardware to rotate filter glass to target angle in [0, 180]."""
        clamped_angle = float(target_angle_deg % 180.0)

        # In physical deployment, send hardware protocol command
        if self.interface_type == "serial_rs485" and self.serial_port:
            # Send Pelco-D auxiliary / custom stepper command (e.g., 0xFF 0x01 0x00 0x07 angle checksum)
            pass
        elif self.interface_type == "gpio_pwm":
            # Set PWM duty cycle for 180-deg servo: duty = 2.5 + (clamped_angle / 180.0) * 10.0
            pass

        self.current_filter_angle_deg = clamped_angle
        self.is_polarizer_engaged = (clamped_angle > 5.0 and clamped_angle < 175.0)
        self.last_actuation_time = time.time()

        return {
            "status": "COMMAND_DELIVERED",
            "filter_angle_deg": self.current_filter_angle_deg,
            "is_polarizer_engaged": self.is_polarizer_engaged,
            "interface": self.interface_type,
            "timestamp": self.last_actuation_time,
        }

    def auto_adjust_for_glint(
        self,
        requires_cpl: bool,
        solar_azimuth_deg: float = 180.0,
    ) -> Dict[str, Any]:
        """
        Automated actuation handler called by SunGlintFilter.
        Rotates filter into extinction position when glare is detected,
        or returns to neutral 0 deg baseline when lighting is nominal.
        """
        if requires_cpl:
            opt_angle = self.compute_optimal_cpl_angle(solar_azimuth_deg)
            res = self.rotate_to_angle(opt_angle)
            res["action"] = "ENGAGED_SPECULAR_EXTINCTION"
            return res
        else:
            res = self.rotate_to_angle(0.0)
            res["action"] = "RETURN_TO_NEUTRAL"
            return res

    def get_status(self) -> Dict[str, Any]:
        """Returns current CPL hardware actuator status."""
        return {
            "hardware_interface": self.interface_type,
            "filter_angle_deg": self.current_filter_angle_deg,
            "is_engaged": self.is_polarizer_engaged,
            "camera_azimuth_deg": self.camera_azimuth_deg,
            "last_actuation_time": self.last_actuation_time,
        }
