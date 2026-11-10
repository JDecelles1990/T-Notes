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
        etype = event.type()
        button = self._button
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

