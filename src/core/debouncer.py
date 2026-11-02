"""Debounce timer utility using PySide6 QTimer."""

from typing import Callable, Optional
from PySide6.QtCore import QObject, QTimer, Signal


class DebounceTimer(QObject):
    """Encapsulates a debounced action that triggers only after an idle period."""

    timeout = Signal()

    def __init__(self, delay_ms: int = 1500, callback: Optional[Callable[[], None]] = None, parent: Optional[QObject] = None):
        super().__init__(parent)
        self.delay_ms = delay_ms
        self._callback = callback
        self._timer = QTimer(self)
        self._timer.setSingleShot(True)
        self._timer.timeout.connect(self._on_timeout)
        if callback is not None:
            self.timeout.connect(callback)

    def trigger(self) -> None:
        """Restarts the debounce timer countdown."""
        self._timer.start(self.delay_ms)

    def flush(self) -> None:
        """Immediately executes the pending callback if the timer is active."""
        if self._timer.isActive():
            self._timer.stop()
            self._on_timeout()

    def cancel(self) -> None:
        """Stops the timer without executing the callback."""
        self._timer.stop()

    def is_active(self) -> bool:
        """Returns True if a debounced callback is currently pending."""
        return self._timer.isActive()

    def _on_timeout(self) -> None:
        self.timeout.emit()
