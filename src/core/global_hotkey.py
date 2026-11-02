"""Global system-wide hotkey manager using Win32 RegisterHotKey and PySide6 nativeEventFilter."""

import ctypes
import sys
from typing import Callable, Optional
from PySide6.QtCore import QAbstractNativeEventFilter, QObject, Signal
from PySide6.QtWidgets import QApplication

WM_HOTKEY = 0x0312
MOD_NOREPEAT = 0x4000
VK_F8 = 0x77  # Virtual key code for F8


class WinNativeHotkeyFilter(QAbstractNativeEventFilter):
    """Native event filter intercepting WM_HOTKEY messages on Windows."""

    def __init__(self, hotkey_id: int, callback: Callable[[], None]):
        super().__init__()
        self.hotkey_id = hotkey_id
        self.callback = callback

    def nativeEventFilter(self, event_type, message):
        if sys.platform == "win32":
            try:
                import ctypes.wintypes
                msg = ctypes.wintypes.MSG.from_address(int(message))
                if msg.message == WM_HOTKEY and msg.wParam == self.hotkey_id:
                    self.callback()
                    return True, 0
            except Exception:
                pass
        return False, 0


class GlobalHotkeyManager(QObject):
    """Registers and manages system-wide global hotkeys across all applications."""

    activated = Signal()

    def __init__(self, key_code: int = VK_F8, hotkey_id: int = 1001, parent: Optional[QObject] = None):
        super().__init__(parent)
        self.key_code = key_code
        self.hotkey_id = hotkey_id
        self._filter: Optional[WinNativeHotkeyFilter] = None
        self._is_registered: bool = False

    def register(self) -> bool:
        """Registers the global hotkey with the operating system."""
        if sys.platform != "win32":
            return False

        try:
            user32 = ctypes.windll.user32
            # Attempt with MOD_NOREPEAT first to avoid repeated trigger on long press
            res = user32.RegisterHotKey(0, self.hotkey_id, MOD_NOREPEAT, self.key_code)
            if not res:
                # Fallback without MOD_NOREPEAT on older versions
                res = user32.RegisterHotKey(0, self.hotkey_id, 0, self.key_code)

            if res:
                self._is_registered = True
                self._filter = WinNativeHotkeyFilter(self.hotkey_id, self.activated.emit)
                if app := QApplication.instance():
                    app.installNativeEventFilter(self._filter)
                return True
        except Exception:
            pass
        return False

    def unregister(self) -> None:
        """Unregisters the hotkey from the operating system and removes the filter."""
        if sys.platform == "win32" and self._is_registered:
            try:
                if self._filter:
                    if app := QApplication.instance():
                        app.removeNativeEventFilter(self._filter)
                    self._filter = None
                ctypes.windll.user32.UnregisterHotKey(0, self.hotkey_id)
            except Exception:
                pass
            finally:
                self._is_registered = False

    @property
    def is_registered(self) -> bool:
        """Returns True if the hotkey is actively registered with Windows."""
        return self._is_registered

