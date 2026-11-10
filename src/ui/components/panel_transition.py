"""Smooth slide transitions for toggling side panes (Split, History, Categories, Active Ticket).

``PanelWidthTransition`` animates a pane's width while it opens (slides out from
the edge) or closes (slides back in) and only hides the widget once the close
animation has finished. When animation is not possible (parent not visible, or
``TRANSITIONS_ENABLED`` is ``False``) the pane is shown/hidden immediately, so
every caller keeps the exact same final state.
"""

from typing import Callable, Optional

from PySide6.QtCore import QEasingCurve, QObject, QVariantAnimation
from PySide6.QtWidgets import QWidget

# Global switch (automated tests turn this off so state changes stay synchronous).
TRANSITIONS_ENABLED: bool = True
PANEL_TRANSITION_MS: int = 220
_QT_MAX = 16777215


class PanelWidthTransition(QObject):
    """Animates open/close of a side pane by driving its fixed width."""

    def __init__(self, widget: QWidget, default_width: int = 270, duration: int = PANEL_TRANSITION_MS):
        super().__init__(widget)
        self._widget = widget
        self._default_width = default_width
        self._orig_limits: Optional[tuple[int, int]] = None
        self._target_visible: Optional[bool] = None
        self._callback: Optional[Callable[[], None]] = None
        self.last_width: int = 0

        self._anim = QVariantAnimation(self)
        self._anim.setDuration(duration)
        self._anim.setEasingCurve(QEasingCurve.InOutCubic)
        self._anim.valueChanged.connect(self._on_value)
        self._anim.finished.connect(self._on_finished)

    # -- state -------------------------------------------------------------
    @property
    def running(self) -> bool:
        return self._anim.state() == QVariantAnimation.Running

    @property
    def is_open(self) -> bool:
        """Logical open state: the animation target while running, else real visibility."""
        if self.running and self._target_visible is not None:
            return self._target_visible
        return self._widget.isVisible()

    def animation_allowed(self) -> bool:
        parent = self._widget.parentWidget()
        return bool(TRANSITIONS_ENABLED and parent is not None and parent.isVisible())

    # -- public API ----------------------------------------------------------
    def show_panel(self, target_width: Optional[int] = None, on_finished: Optional[Callable[[], None]] = None) -> None:
        widget = self._widget
        if not self.animation_allowed():
            self.cancel()
            widget.setVisible(True)
            if on_finished:
                on_finished()
            return
        if self.running and self._target_visible:
            return
        if not self.running and widget.isVisible():
            if on_finished:
                on_finished()
            return
        start = max(1, widget.width()) if self.running else 1
        self._begin(True, start, target_width, on_finished)

    def hide_panel(self, on_finished: Optional[Callable[[], None]] = None) -> None:
        widget = self._widget
        if not self.animation_allowed():
            self.cancel()
            widget.setVisible(False)
            if on_finished:
                on_finished()
            return
        if self.running and self._target_visible is False:
            return
        if not self.running and not widget.isVisible():
            if on_finished:
                on_finished()
            return
        if not self.running and widget.width() > 1:
            self.last_width = widget.width()
        self._begin(False, max(1, widget.width()), None, on_finished)

    def set_open(self, visible: bool, target_width: Optional[int] = None) -> None:
        if visible:
            self.show_panel(target_width)
        else:
            self.hide_panel()

    def cancel(self) -> None:
        """Stops any running animation and restores the widget's original size limits."""
        self._anim.stop()
        self._callback = None
        self._target_visible = None
        self._restore_limits()

    # -- internals -----------------------------------------------------------
    def _capture_limits(self) -> None:
        if self._orig_limits is None:
            self._orig_limits = (self._widget.minimumWidth(), self._widget.maximumWidth())

    def _restore_limits(self) -> None:
        if self._orig_limits is not None:
            lo, hi = self._orig_limits
            self._widget.setMinimumWidth(lo)
            self._widget.setMaximumWidth(hi)
            self._orig_limits = None

    def _begin(self, show: bool, start: int, target: Optional[int], on_finished) -> None:
        self._anim.stop()
        self._capture_limits()
        lo, hi = self._orig_limits  # type: ignore[misc]
        self._target_visible = show
        self._callback = on_finished
        if show:
            end = target if target else (self.last_width or self._default_width)
            end = max(lo, min(end, hi if hi < _QT_MAX else end), 2)
            self._widget.setFixedWidth(max(1, start))
            self._widget.show()
        else:
            end = 1
        self._anim.setStartValue(float(start))
        self._anim.setEndValue(float(end))
        self._anim.start()

    def _on_value(self, value) -> None:
        self._widget.setFixedWidth(max(1, int(value)))

    def _on_finished(self) -> None:
        show = self._target_visible
        callback, self._callback = self._callback, None
        if show is False:
            self._widget.hide()
        self._restore_limits()
        self._target_visible = None
        if callback:
            callback()

