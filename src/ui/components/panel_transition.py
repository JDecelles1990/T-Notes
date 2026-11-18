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



# =============================================================================
# Smooth Content Cross-Fades, Slide/Fade Overlay Bars & Dialog Entrances
# =============================================================================

from typing import Optional as _Optional

from PySide6.QtCore import (
    QEasingCurve as _QEasingCurve,
    QPoint as _QPoint,
    QPropertyAnimation as _QPropertyAnimation,
    QObject as _QObject,
)
from PySide6.QtWidgets import (
    QGraphicsOpacityEffect as _QGraphicsOpacityEffect,
    QWidget as _QWidget,
)

FADE_TRANSITION_MS = 160
BAR_SLIDE_FADE_MS = 180
DIALOG_FADE_MS = 165


class WidgetFadeTransition(_QObject):
    """Temporary opacity fade-in for content panes (e.g. tab or workspace switches).

    Always detaches its ``QGraphicsOpacityEffect`` (via ``setGraphicsEffect(None)``)
    when complete or cancelled so child controls' persistent ``GlowAnimator`` /
    ``InputGlowAnimator`` drop-shadow halos remain unclipped.
    """

    def __init__(self, target: _QWidget, duration_ms: int = FADE_TRANSITION_MS) -> None:
        super().__init__(target)
        self._target = target
        self._duration_ms = max(40, int(duration_ms))
        self._effect: _Optional[_QGraphicsOpacityEffect] = None
        self._anim: _Optional[_QPropertyAnimation] = None

    @property
    def is_running(self) -> bool:
        return bool(self._anim is not None and self._anim.state() == _QPropertyAnimation.Running)

    def _clear_effect(self) -> None:
        try:
            current = self._target.graphicsEffect()
            if current is self._effect and self._effect is not None:
                self._target.setGraphicsEffect(None)
        except RuntimeError:
            pass
        self._effect = None

    def stop(self) -> None:
        if self._anim is not None:
            self._anim.stop()
            self._anim = None
        self._clear_effect()

    def fade_in(self, start_opacity: float = 0.25) -> None:
        """Fade *target* smoothly to full opacity, or skip immediately if disabled."""
        self.stop()
        if not TRANSITIONS_ENABLED:
            return

        # Never clobber a non-fade graphics effect already owned by target
        if self._target.graphicsEffect() is not None:
            return

        effect = _QGraphicsOpacityEffect(self._target)
        effect.setOpacity(max(0.0, min(1.0, float(start_opacity))))
        self._effect = effect
        self._target.setGraphicsEffect(effect)

        anim = _QPropertyAnimation(effect, b"opacity", self)
        anim.setDuration(self._duration_ms)
        anim.setStartValue(effect.opacity())
        anim.setEndValue(1.0)
        anim.setEasingCurve(_QEasingCurve.OutCubic)
        anim.finished.connect(self._on_finished)
        self._anim = anim
        anim.start()

    def _on_finished(self) -> None:
        self._anim = None
        self._clear_effect()


def fade_in_widget(target: _Optional[_QWidget], duration_ms: int = FADE_TRANSITION_MS) -> None:
    """Convenience helper to fade *target* in without leaving lingering effects."""
    if target is None:
        return
    transition = getattr(target, "_widget_fade_transition", None)
    if not isinstance(transition, WidgetFadeTransition):
        transition = WidgetFadeTransition(target, duration_ms=duration_ms)
        target._widget_fade_transition = transition  # type: ignore[attr-defined]
    transition.fade_in()


class SlideFadeBarTransition(_QObject):
    """Smooth top-down slide + fade entrance for floating bars (e.g. Find bar)."""

    def __init__(self, bar: _QWidget, duration_ms: int = BAR_SLIDE_FADE_MS) -> None:
        super().__init__(bar)
        self._bar = bar
        self._duration_ms = max(40, int(duration_ms))
        self._pos_anim: _Optional[_QPropertyAnimation] = None
        self._fade = WidgetFadeTransition(bar, duration_ms=self._duration_ms)

    @property
    def is_running(self) -> bool:
        pos_active = self._pos_anim is not None and self._pos_anim.state() == _QPropertyAnimation.Running
        return bool(pos_active or self._fade.is_running)

    def show_animated(self, final_pos: _QPoint) -> None:
        if self._pos_anim is not None:
            self._pos_anim.stop()
            self._pos_anim = None

        if not TRANSITIONS_ENABLED:
            self._fade.stop()
            self._bar.move(final_pos)
            return

        start_pos = _QPoint(final_pos.x(), final_pos.y() - 10)
        self._bar.move(start_pos)
        self._fade.fade_in(start_opacity=0.1)

        anim = _QPropertyAnimation(self._bar, b"pos", self)
        anim.setDuration(self._duration_ms)
        anim.setStartValue(start_pos)
        anim.setEndValue(final_pos)
        anim.setEasingCurve(_QEasingCurve.OutCubic)
        anim.finished.connect(self._on_pos_finished)
        self._pos_anim = anim
        anim.start()

    def _on_pos_finished(self) -> None:
        self._pos_anim = None


def animate_bar_show(
    bar: _Optional[_QWidget],
    final_pos: _Optional[_QPoint] = None,
    duration_ms: int = BAR_SLIDE_FADE_MS,
) -> None:
    """Slide and fade *bar* into *final_pos* (respects ``TRANSITIONS_ENABLED``)."""
    if bar is None:
        return
    target_pos = final_pos if final_pos is not None else bar.pos()
    transition = getattr(bar, "_slide_fade_transition", None)
    if not isinstance(transition, SlideFadeBarTransition):
        transition = SlideFadeBarTransition(bar, duration_ms=duration_ms)
        bar._slide_fade_transition = transition  # type: ignore[attr-defined]
    transition.show_animated(target_pos)


def animate_dialog_show(dialog: _Optional[_QWidget], duration_ms: int = DIALOG_FADE_MS) -> None:
    """Fade in a modal or utility dialog using ``windowOpacity``.

    Using ``windowOpacity`` rather than ``QGraphicsOpacityEffect`` keeps every
    child button and input glow completely unclipped while opening smoothly.
    """
    if dialog is None:
        return
    existing = getattr(dialog, "_dialog_fade_anim", None)
    if existing is not None:
        existing.stop()

    if not TRANSITIONS_ENABLED or not dialog.isWindow():
        try:
            dialog.setWindowOpacity(1.0)
        except RuntimeError:
            pass
        return

    try:
        dialog.setWindowOpacity(0.0)
    except RuntimeError:
        return

    anim = _QPropertyAnimation(dialog, b"windowOpacity", dialog)
    anim.setDuration(max(50, int(duration_ms)))
    anim.setStartValue(0.0)
    anim.setEndValue(1.0)
    anim.setEasingCurve(_QEasingCurve.OutCubic)
    anim.finished.connect(lambda: dialog.setWindowOpacity(1.0))
    dialog._dialog_fade_anim = anim  # type: ignore[attr-defined]
    anim.start()
