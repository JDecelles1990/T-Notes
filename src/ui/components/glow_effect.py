"""Colorful hover / click glow animations for T-Notes buttons.

Each button gets a ``QGraphicsDropShadowEffect`` driven by a ``GlowAnimator``:

* **Hover:** the glow fades in and slowly cycles through the hue wheel.
* **Click:** the glow flares brighter and wider while the mouse button is held,
  then settles back to the hover level (or fades out if the cursor left).

The effect is disabled while idle so resting buttons render exactly as before
(no blurred text, no per-frame cost).
"""

from typing import Iterable, Optional

from PySide6.QtCore import QEasingCurve, QEvent, QObject, QVariantAnimation, Qt
from PySide6.QtGui import QColor
from PySide6.QtWidgets import QAbstractButton, QGraphicsDropShadowEffect, QPushButton, QToolButton, QWidget

# Vibrant accent palette (matches the technician tab palette).
GLOW_PALETTE: tuple[str, ...] = (
    "#38bdf8", "#34d399", "#a855f7", "#fbbf24", "#f43f5e", "#06b6d4",
    "#fb923c", "#818cf8", "#a3e635", "#ec4899", "#2dd4bf", "#c084fc",
)

HOVER_LEVEL = 1.0
PRESS_LEVEL = 1.7
HOVER_FADE_MS = 180
PRESS_FADE_MS = 90
HUE_CYCLE_MS = 3600


class GlowAnimator(QObject):
    """Drives a colorful animated drop-shadow glow on a single button."""

    def __init__(self, button: QAbstractButton, color: str = GLOW_PALETTE[0]):
        super().__init__(button)
        self._button = button
        self._base = QColor(color)
        self._level = 0.0
        self._target = 0.0
        self._pressed = False
        self._hue_offset = 0.0

        self._effect = QGraphicsDropShadowEffect(button)
        self._effect.setOffset(0, 0)
        self._effect.setBlurRadius(0)
        self._effect.setEnabled(False)
        button.setGraphicsEffect(self._effect)

        self._fade = QVariantAnimation(self)
        self._fade.setEasingCurve(QEasingCurve.OutCubic)
        self._fade.valueChanged.connect(self._on_level)
        self._fade.finished.connect(self._on_fade_finished)

        self._hue = QVariantAnimation(self)
        self._hue.setStartValue(0.0)
        self._hue.setEndValue(1.0)
        self._hue.setDuration(HUE_CYCLE_MS)
        self._hue.setLoopCount(-1)
        self._hue.valueChanged.connect(self._on_hue)

        button.installEventFilter(self)

    # -- state -----------------------------------------------------------------
    @property
    def level(self) -> float:
        """Current glow intensity: 0 idle, ~1 hover, ~1.7 pressed."""
        return self._level

    @property
    def is_glowing(self) -> bool:
        return self._effect.isEnabled()

    @property
    def effect(self) -> QGraphicsDropShadowEffect:
        return self._effect

    # -- animation -------------------------------------------------------------
    def _animate_to(self, target: float, duration: int) -> None:
        self._target = target
        self._fade.stop()
        self._fade.setDuration(duration)
        self._fade.setStartValue(float(self._level))
        self._fade.setEndValue(float(target))
        self._fade.start()

    def _on_level(self, value) -> None:
        self._level = float(value)
        self._apply()

    def _on_hue(self, value) -> None:
        self._hue_offset = float(value)
        if self._level > 0.0:
            self._apply()

    def _on_fade_finished(self) -> None:
        if self._target <= 0.0:
            self._level = 0.0
            self._hue.stop()
            self._apply()

    def _current_color(self) -> QColor:
        h, s, v, _ = self._base.getHsvF()
        hue = (max(h, 0.0) + self._hue_offset) % 1.0
        boost = max(0.0, self._level - HOVER_LEVEL) / (PRESS_LEVEL - HOVER_LEVEL)
        color = QColor.fromHsvF(hue, max(0.35, s - 0.45 * boost), min(1.0, max(v, 0.9) + 0.1 * boost))
        color.setAlpha(int(min(255, 120 + 90 * min(self._level, PRESS_LEVEL))))
        return color

    def _apply(self) -> None:
        if self._level <= 0.01:
            self._effect.setEnabled(False)
            return
        hover_part = min(self._level, HOVER_LEVEL)
        press_part = max(0.0, self._level - HOVER_LEVEL)
        self._effect.setBlurRadius(6.0 + 20.0 * hover_part + 22.0 * press_part)
        self._effect.setColor(self._current_color())
        self._effect.setEnabled(True)

    def reset(self) -> None:
        """Immediately clear any glow (hidden / disabled / destroyed states)."""
        self._fade.stop()
        self._hue.stop()
        self._pressed = False
        self._target = 0.0
        self._level = 0.0
        self._apply()

    # -- events ----------------------------------------------------------------
    def eventFilter(self, watched, event) -> bool:  # noqa: N802 (Qt API)
        button = getattr(self, "_button", None)
        if not button:
            return False
        etype = event.type()
        if etype == QEvent.Enter:
            if button.isEnabled():
                if self._hue.state() != QVariantAnimation.Running:
                    self._hue.start()
                self._animate_to(HOVER_LEVEL, HOVER_FADE_MS)
        elif etype == QEvent.Leave:
            self._pressed = False
            self._animate_to(0.0, HOVER_FADE_MS)
        elif etype == QEvent.MouseButtonPress:
            if button.isEnabled() and event.button() == Qt.LeftButton:
                self._pressed = True
                if self._hue.state() != QVariantAnimation.Running:
                    self._hue.start()
                self._animate_to(PRESS_LEVEL, PRESS_FADE_MS)
        elif etype == QEvent.MouseButtonRelease:
            if self._pressed:
                self._pressed = False
                self._animate_to(HOVER_LEVEL if button.underMouse() else 0.0, HOVER_FADE_MS)
        elif etype in (QEvent.Hide, QEvent.EnabledChange):
            if etype == QEvent.Hide or not button.isEnabled():
                self.reset()
        return False


def install_glow(button: QAbstractButton, color: Optional[str] = None) -> GlowAnimator:
    """Attach (idempotently) a hover/click glow animation to ``button``."""
    existing = getattr(button, "_glow_animator", None)
    if existing is not None:
        return existing
    animator = GlowAnimator(button, color or GLOW_PALETTE[0])
    button._glow_animator = animator
    return animator


def apply_glow_to_buttons(roots: Iterable[QWidget]) -> int:
    """Install glow on every ``QPushButton`` / ``QToolButton`` under ``roots``.

    Colors cycle through ``GLOW_PALETTE`` so neighboring buttons glow differently.
    Returns the number of buttons newly decorated.
    """
    count = 0
    index = 0
    for root in roots:
        if root is None:
            continue
        candidates = list(root.findChildren(QAbstractButton))
        if isinstance(root, QAbstractButton):
            candidates.insert(0, root)
        for button in candidates:
            if not isinstance(button, (QPushButton, QToolButton)):
                continue
            if getattr(button, "_glow_animator", None) is not None:
                continue
            install_glow(button, GLOW_PALETTE[index % len(GLOW_PALETTE)])
            index += 1
            count += 1
    return count



# =============================================================================
# Enhanced Neon Aurora Input Glows, Gradient Shimmer Bars & Status Pulses
# =============================================================================

from typing import Union as _Union

from PySide6.QtCore import QPointF as _QPointF, QTimer, Qt as _Qt
from PySide6.QtGui import QBrush as _QBrush, QLinearGradient as _QLinearGradient, QPainter as _QPainter
from PySide6.QtWidgets import (
    QAbstractSpinBox as _QAbstractSpinBox,
    QComboBox as _QComboBox,
    QLineEdit as _QLineEdit,
    QPlainTextEdit as _QPlainTextEdit,
)

INPUT_HOVER_LEVEL = 0.85
INPUT_FOCUS_LEVEL = 1.45
INPUT_BASE_BLUR = 18.0
INPUT_MAX_BLUR = 28.0
INPUT_HOVER_MS = 180
INPUT_BLUR_MS = 220


class InputGlowAnimator(QObject):
    """Animated outer neon glow + rainbow hue cycle for input fields.

    Activates on pointer hover and stays illuminated with a subtle cyan/aurora
    halo while the input widget has keyboard focus. When idle, the underlying
    ``QGraphicsDropShadowEffect`` is disabled so resting rendering stays fast.
    """

    def __init__(self, widget: QWidget) -> None:
        super().__init__(widget)
        self._widget = widget
        self._hovered = False
        self._focused = widget.hasFocus()
        self._level = INPUT_FOCUS_LEVEL if self._focused else 0.0
        self._phase = 0.0
        self._last_paint_phase = -1.0

        self._effect = QGraphicsDropShadowEffect(widget)
        self._effect.setOffset(0.0, 0.0)
        self._effect.setBlurRadius(INPUT_BASE_BLUR)
        self._effect.setColor(QColor(0, 0, 0, 0))
        self._effect.setEnabled(self._level > 0.0)
        widget.setGraphicsEffect(self._effect)

        self._fade_anim = QVariantAnimation(self)
        self._fade_anim.setEasingCurve(QEasingCurve.OutCubic)
        self._fade_anim.valueChanged.connect(self._on_fade_step)
        self._fade_anim.finished.connect(self._on_fade_finished)

        self._hue_timer = QTimer(self)
        self._hue_timer.setInterval(45)
        self._hue_timer.timeout.connect(self._on_hue_tick)

        widget.installEventFilter(self)
        if isinstance(widget, _QComboBox) and widget.isEditable() and widget.lineEdit():
            widget.lineEdit().installEventFilter(self)
        elif isinstance(widget, _QAbstractSpinBox) and widget.lineEdit():
            widget.lineEdit().installEventFilter(self)

        if self._focused:
            self._apply_effect()
            self._hue_timer.start()

    @property
    def level(self) -> float:
        return self._level

    @property
    def is_glowing(self) -> bool:
        return self._level > 0.01

    @property
    def is_hovered(self) -> bool:
        return self._hovered

    @property
    def is_focused(self) -> bool:
        return self._focused

    def _target_level(self) -> float:
        if self._focused:
            return INPUT_FOCUS_LEVEL
        if self._hovered:
            return INPUT_HOVER_LEVEL
        return 0.0

    def _animate_to_target(self) -> None:
        target = self._target_level()
        if abs(target - self._level) < 0.005:
            return
        if target > 0.0 and not self._hue_timer.isActive():
            self._hue_timer.start()
        self._fade_anim.stop()
        self._fade_anim.setStartValue(self._level)
        self._fade_anim.setEndValue(target)
        self._fade_anim.setDuration(INPUT_HOVER_MS if target > self._level else INPUT_BLUR_MS)
        self._fade_anim.start()

    def _on_fade_step(self, value) -> None:
        self._level = float(value)
        self._apply_effect()

    def _on_fade_finished(self) -> None:
        if self._level <= 0.01 and not self._hovered and not self._focused:
            self._level = 0.0
            self._hue_timer.stop()
            self._apply_effect()

    def _on_hue_tick(self) -> None:
        if not self._widget.isVisible():
            self._hue_timer.stop()
            return
        self._phase = (self._phase + 45.0 / HUE_CYCLE_MS) % 1.0
        if self._level > 0.01:
            self._apply_effect()
        else:
            self._hue_timer.stop()

    def _sample_color(self) -> QColor:
        n = len(GLOW_PALETTE)
        pos = (self._phase * n) % n
        idx = int(pos)
        frac = pos - idx
        c1 = QColor(GLOW_PALETTE[idx])
        c2 = QColor(GLOW_PALETTE[(idx + 1) % n])
        r = int(c1.red() + (c2.red() - c1.red()) * frac)
        g = int(c1.green() + (c2.green() - c1.green()) * frac)
        b = int(c1.blue() + (c2.blue() - c1.blue()) * frac)
        return QColor(r, g, b)

    def _apply_effect(self) -> None:
        try:
            active = self._level > 0.01 and self._widget.isEnabled()
        except RuntimeError:
            self._hue_timer.stop()
            return

        if not active:
            self._effect.setEnabled(False)
            self._effect.setColor(QColor(0, 0, 0, 0))
            return

        color = self._sample_color()
        alpha = min(225, int(130 + 65 * self._level))
        color.setAlpha(alpha)
        blur = min(INPUT_MAX_BLUR, INPUT_BASE_BLUR + 6.0 * self._level)
        if not self._effect.isEnabled():
            self._effect.setEnabled(True)
        self._effect.setBlurRadius(blur)
        self._effect.setColor(color)

    def eventFilter(self, watched: QObject, event: QEvent) -> bool:
        etype = event.type()
        if etype in (QEvent.Enter, QEvent.HoverEnter):
            self._hovered = True
            self._animate_to_target()
        elif etype in (QEvent.Leave, QEvent.HoverLeave):
            if watched is self._widget:
                self._hovered = False
                self._animate_to_target()
        elif etype == QEvent.FocusIn:
            self._focused = True
            self._animate_to_target()
        elif etype == QEvent.FocusOut:
            # Stay glowing if focus moved between outer wrapper and inner lineEdit
            try:
                still_focused = self._widget.hasFocus()
                if not still_focused and hasattr(self._widget, "lineEdit") and self._widget.lineEdit():
                    still_focused = self._widget.lineEdit().hasFocus()
            except RuntimeError:
                still_focused = False
            self._focused = bool(still_focused)
            self._animate_to_target()
        elif etype == QEvent.EnabledChange:
            self._apply_effect()
        elif etype == QEvent.Hide:
            self._hovered = False
            self._hue_timer.stop()
        return super().eventFilter(watched, event)


def install_input_glow(widget: QWidget) -> InputGlowAnimator:
    """Attach an :class:`InputGlowAnimator` to *widget* idempotently."""
    existing = getattr(widget, "_input_glow_animator", None)
    if existing is not None:
        return existing
    animator = InputGlowAnimator(widget)
    widget._input_glow_animator = animator  # type: ignore[attr-defined]
    return animator


def apply_glow_to_inputs(roots: Iterable[QWidget]) -> int:
    """Install neon input glow on text/combo/spin inputs under *roots*.

    Internal child line-edits inside spin boxes and combo boxes are skipped
    so double drop-shadow effects are never attached.
    """
    seen: set[int] = set()
    count = 0
    target_types = (_QLineEdit, _QComboBox, _QAbstractSpinBox, _QPlainTextEdit)
    for root in roots:
        if root is None:
            continue
        candidates = list(root.findChildren(QWidget))
        if isinstance(root, QWidget):
            candidates.insert(0, root)
        for widget in candidates:
            if not isinstance(widget, target_types):
                continue
            parent = widget.parentWidget()
            if isinstance(widget, _QLineEdit) and isinstance(parent, (_QComboBox, _QAbstractSpinBox)):
                continue
            wid = id(widget)
            if wid in seen:
                continue
            seen.add(wid)
            if getattr(widget, "_input_glow_animator", None) is None:
                install_input_glow(widget)
                count += 1
    return count


class AuroraAccentBar(QWidget):
    """Thin 2-3px animated multi-color neon aurora gradient shimmer strip.

    Can be placed standalone or attached via :meth:`attach_to` along the top
    or bottom edge of a target bar without disturbing the bar's action layout.
    """

    def __init__(
        self,
        parent: _Union[QWidget, None] = None,
        height: int = 2,
        edge: str = "bottom",
        interval_ms: int = 50,
    ) -> None:
        super().__init__(parent)
        self._height = max(1, int(height))
        self._edge = edge
        self._phase = 0.0
        self._step = interval_ms / float(HUE_CYCLE_MS * 1.4)
        self._attached_target: _Union[QWidget, None] = None

        self.setFixedHeight(self._height)
        self.setAttribute(_Qt.WA_TransparentForMouseEvents, True)
        self.setAttribute(_Qt.WA_NoSystemBackground, True)

        self._timer = QTimer(self)
        self._timer.setInterval(interval_ms)
        self._timer.timeout.connect(self._tick)
        if parent is None or parent.isVisible():
            self._timer.start()

    @property
    def phase(self) -> float:
        return self._phase

    def attach_to(self, target: QWidget, edge: str = "bottom") -> "AuroraAccentBar":
        """Pin this bar along the *edge* ('top' or 'bottom') of *target*."""
        self._edge = edge
        self._attached_target = target
        self.setParent(target)
        target.installEventFilter(self)
        self._sync_geometry()
        self.show()
        self.raise_()
        if target.isVisible():
            self._timer.start()
        return self

    def _sync_geometry(self) -> None:
        if self._attached_target is None:
            return
        w = max(1, self._attached_target.width())
        y = 0 if self._edge == "top" else max(0, self._attached_target.height() - self._height)
        self.setGeometry(0, y, w, self._height)

    def _tick(self) -> None:
        if not self.isVisible():
            self._timer.stop()
            return
        self._phase = (self._phase + self._step) % 1.0
        self.update()

    def showEvent(self, event) -> None:  # type: ignore[override]
        super().showEvent(event)
        if not self._timer.isActive():
            self._timer.start()

    def hideEvent(self, event) -> None:  # type: ignore[override]
        super().hideEvent(event)
        self._timer.stop()

    def eventFilter(self, watched: QObject, event: QEvent) -> bool:
        if watched is self._attached_target:
            etype = event.type()
            if etype in (QEvent.Resize, QEvent.Show, QEvent.LayoutRequest):
                self._sync_geometry()
                self.raise_()
            elif etype == QEvent.Hide:
                self._timer.stop()
        return super().eventFilter(watched, event)

    def paintEvent(self, event) -> None:  # type: ignore[override]
        w = self.width()
        h = self.height()
        if w <= 0 or h <= 0:
            return
        painter = _QPainter(self)
        painter.setRenderHint(_QPainter.Antialiasing, False)

        grad = _QLinearGradient(_QPointF(0.0, 0.0), _QPointF(float(w), 0.0))
        stops = 5
        n = len(GLOW_PALETTE)
        for i in range(stops + 1):
            t = i / float(stops)
            palette_pos = ((self._phase + t * 0.65) * n) % n
            idx = int(palette_pos)
            frac = palette_pos - idx
            c1 = QColor(GLOW_PALETTE[idx])
            c2 = QColor(GLOW_PALETTE[(idx + 1) % n])
            col = QColor(
                int(c1.red() + (c2.red() - c1.red()) * frac),
                int(c1.green() + (c2.green() - c1.green()) * frac),
                int(c1.blue() + (c2.blue() - c1.blue()) * frac),
                215,
            )
            grad.setColorAt(t, col)
        painter.fillRect(0, 0, w, h, _QBrush(grad))
        painter.end()


def pulse_widget_glow(
    widget: _Union[QWidget, None],
    color: _Union[str, QColor] = "#38bdf8",
    duration_ms: int = 750,
) -> None:
    """Briefly flash a glowing halo around *widget* (e.g. saved/copied pill).

    Safely no-ops if *widget* already owns a dedicated glow animator so we
    never overwrite a button or input's persistent effect.
    """
    if widget is None:
        return
    if getattr(widget, "_glow_animator", None) is not None or getattr(
        widget, "_input_glow_animator", None
    ) is not None:
        return

    existing_anim = getattr(widget, "_pulse_glow_anim", None)
    if existing_anim is not None:
        existing_anim.stop()

    effect = widget.graphicsEffect()
    if not isinstance(effect, QGraphicsDropShadowEffect) or not getattr(
        widget, "_owns_pulse_effect", False
    ):
        effect = QGraphicsDropShadowEffect(widget)
        effect.setOffset(0.0, 0.0)
        widget._owns_pulse_effect = True  # type: ignore[attr-defined]
        widget.setGraphicsEffect(effect)

    base_color = QColor(color) if isinstance(color, str) else QColor(color)
    effect.setColor(base_color)
    effect.setBlurRadius(22.0)
    effect.setEnabled(True)

    anim = QVariantAnimation(widget)
    anim.setStartValue(1.0)
    anim.setEndValue(0.0)
    anim.setDuration(max(120, int(duration_ms)))
    anim.setEasingCurve(QEasingCurve.OutCubic)

    def _on_step(val) -> None:
        try:
            factor = float(val)
            c = QColor(base_color)
            c.setAlpha(int(220 * factor))
            effect.setColor(c)
            effect.setBlurRadius(22.0 * factor)
        except RuntimeError:
            anim.stop()

    def _on_done() -> None:
        try:
            effect.setEnabled(False)
            effect.setColor(QColor(0, 0, 0, 0))
        except RuntimeError:
            pass

    anim.valueChanged.connect(_on_step)
    anim.finished.connect(_on_done)
    widget._pulse_glow_anim = anim  # type: ignore[attr-defined]
    anim.start()
