"""Stopwatch service managing elapsed time calculation, PSA billing formatting, and idle/lock detection."""

import ctypes
import math
import sys
from typing import NamedTuple


class FormattedTime(NamedTuple):
    display: str       # e.g., "00:14:32"
    decimal_hours: str # e.g., "0.25h"
    rounded_15m: str   # e.g., "0.50h" (rounded up to nearest 15m block)


class StopwatchService:
    """Manages stopwatch formatting and workstation idle/lock detection for MSP billing."""

    DEFAULT_IDLE_TIMEOUT_SECONDS: int = 300  # 5 minutes

    @staticmethod
    def format_time(total_seconds: int) -> FormattedTime:
        """Converts raw seconds into standard technician & PSA billing formats."""
        clamped_seconds = max(0, total_seconds)
        hours = clamped_seconds // 3600
        minutes = (clamped_seconds % 3600) // 60
        seconds = clamped_seconds % 60

        display = f"{hours:02d}:{minutes:02d}:{seconds:02d}"
        decimal = f"{clamped_seconds / 3600:.2f}h"

        # 15-minute minimum/increment rounding common in MSP billing
        blocks_15m = max(1, math.ceil(clamped_seconds / 900)) if clamped_seconds > 0 else 0
        rounded = f"{blocks_15m * 0.25:.2f}h"

        return FormattedTime(display=display, decimal_hours=decimal, rounded_15m=rounded)

    @staticmethod
    def format_tab_tag(total_seconds: int) -> str:
        """Formats the minute tag displayed in the tab title (e.g. '(14m)')."""
        if total_seconds > 0:
            return f" ({total_seconds // 60}m)"
        return ""

    @staticmethod
    def is_workstation_locked() -> bool:
        """Checks if the Windows workstation is currently locked or displaying the secure desktop."""
        if sys.platform != "win32":
            return False

        try:
            user32 = ctypes.windll.user32
            # 0x0100 is DESKTOP_SWITCHDESKTOP
            h_desk = user32.OpenInputDesktop(0, False, 0x0100)
            if not h_desk:
                return True
            switched = user32.SwitchDesktop(h_desk)
            user32.CloseDesktop(h_desk)
            return switched == 0
        except Exception:
            return False

    @staticmethod
    def get_system_idle_seconds() -> float:
        """Returns the number of seconds since the last system-wide user input (mouse or keyboard)."""
        if sys.platform != "win32":
            return 0.0

        try:
            class LASTINPUTINFO(ctypes.Structure):
                _fields_ = [
                    ("cbSize", ctypes.c_uint),
                    ("dwTime", ctypes.c_uint),
                ]

            lii = LASTINPUTINFO()
            lii.cbSize = ctypes.sizeof(LASTINPUTINFO)
            if ctypes.windll.user32.GetLastInputInfo(ctypes.byref(lii)):
                millis = ctypes.windll.kernel32.GetTickCount() - lii.dwTime
                return max(0.0, millis / 1000.0)
        except Exception:
            pass
        return 0.0

    @classmethod
    def should_auto_pause(cls, idle_threshold_seconds: int = DEFAULT_IDLE_TIMEOUT_SECONDS) -> bool:
        """Determines if the stopwatch should auto-pause due to workstation lock or 5m+ idle time."""
        if cls.is_workstation_locked():
            return True
        if cls.get_system_idle_seconds() >= idle_threshold_seconds:
            return True
        return False
