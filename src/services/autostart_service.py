"""Windows Autostart management service via HKCU registry."""

import os
from pathlib import Path
import sys
from typing import Optional

try:
    import winreg
    _WINREG_AVAILABLE = True
except ImportError:
    winreg = None
    _WINREG_AVAILABLE = False

RUN_KEY_PATH = r"Software\Microsoft\Windows\CurrentVersion\Run"
APP_REG_KEY = "TNotes"


class AutostartService:
    """Manages Windows startup registry entry under HKCU (no admin privileges required)."""

    def __init__(self, app_name: str = APP_REG_KEY):
        self.app_name = app_name

    def is_supported(self) -> bool:
        """Returns True if running on Windows with winreg available."""
        return _WINREG_AVAILABLE and sys.platform == "win32"

    def get_launch_command(self) -> str:
        """Constructs the launch command using pythonw (GUI mode) if available."""
        py_exe = Path(sys.executable)
        pythonw_exe = py_exe.parent / "pythonw.exe"
        chosen_exe = pythonw_exe if pythonw_exe.exists() else py_exe

        project_root = Path(__file__).resolve().parent.parent.parent
        main_script = project_root / "src" / "main.py"

        return f'"{chosen_exe}" "{main_script}" --tray'

    def is_enabled(self) -> bool:
        """Checks if the run key exists in HKCU."""
        if not self.is_supported():
            return False
        try:
            with winreg.OpenKey(winreg.HKEY_CURRENT_USER, RUN_KEY_PATH, 0, winreg.KEY_READ) as key:
                val, _ = winreg.QueryValueEx(key, self.app_name)
                return bool(val)
        except (FileNotFoundError, OSError):
            return False

    def set_enabled(self, enabled: bool) -> bool:
        """Enables or disables the Windows startup entry."""
        if not self.is_supported():
            return False

        try:
            with winreg.OpenKey(winreg.HKEY_CURRENT_USER, RUN_KEY_PATH, 0, winreg.KEY_SET_VALUE) as key:
                if enabled:
                    cmd = self.get_launch_command()
                    winreg.SetValueEx(key, self.app_name, 0, winreg.REG_SZ, cmd)
                else:
                    try:
                        winreg.DeleteValue(key, self.app_name)
                    except FileNotFoundError:
                        pass
            return True
        except OSError:
            return False

