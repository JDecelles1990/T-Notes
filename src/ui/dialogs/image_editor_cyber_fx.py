"""Dedicated Cyber Neon Prism visual effects & custom widgets for the Image Editor window.

Scoped exclusively to ``ResizeImageDialog`` / ``TextAnnotationDialog`` so the rest
of T-Notes retains its own theme untouched.
"""

from __future__ import annotations

import math
from typing import Iterable, Optional

from PySide6.QtCore import (
    QEasingCurve,
    QEvent,
    QObject,
    QPoint,
    QPointF,
    QRect,
    QRectF,
    Qt,
    QTimer,
    QVariantAnimation,
    Signal,
)
from PySide6.QtGui import (
    QBrush,
    QColor,
    QConicalGradient,
    QLinearGradient,
    QMouseEvent,
    QPainter,
    QPainterPath,
    QPaintEvent,
    QPen,
    QRadialGradient,
)
from PySide6.QtWidgets import (
    QAbstractButton,
    QAbstractSpinBox,
    QFrame,
    QLineEdit,
    QPlainTextEdit,
    QPushButton,
    QSplitter,
    QSplitterHandle,
    QTextEdit,
    QToolButton,
    QWidget,
)

# High-saturation futuristic cyber-neon spectrum
CYBER_RAINBOW_STOPS: tuple[str, ...] = (
    "#ff007f",  # Hyper Magenta
    "#ff3d7f",  # Laser Pink
    "#ff8c00",  # Solar Neon Orange
    "#ffe600",  # Volt Yellow
    "#00ff9d",  # Cyber Mint
    "#00f0ff",  # Electric Cyan
    "#3b82f6",  # Plasma Blue
    "#9d4edd",  # Ultraviolet
    "#ff00e5",  # Neon Fuchsia
)

# Per-button colorful gradient presets (background top -> mid -> bottom, border, hover, checked)
CYBER_BUTTON_THEMES: dict[str, dict[str, str]] = {
    "cyan": {
        "bg": "qlineargradient(x1:0, y1:0, x2:1, y2:1, stop:0 #00d2ff, stop:0.55 #0077b6, stop:1 #0b2545)",
        "hover": "qlineargradient(x1:0, y1:0, x2:1, y2:1, stop:0 #38f9d7, stop:0.5 #00bbf9, stop:1 #3a0ca3)",
        "checked": "qlineargradient(x1:0, y1:0, x2:1, y2:1, stop:0 #00f5d4, stop:0.5 #00bbf9, stop:1 #4361ee)",
        "border": "#00f0ff",
        "text": "#ffffff",
    },
    "magenta": {
        "bg": "qlineargradient(x1:0, y1:0, x2:1, y2:1, stop:0 #ff007f, stop:0.55 #b5179e, stop:1 #3c096c)",
        "hover": "qlineargradient(x1:0, y1:0, x2:1, y2:1, stop:0 #ff4da6, stop:0.5 #f72585, stop:1 #7209b7)",
        "checked": "qlineargradient(x1:0, y1:0, x2:1, y2:1, stop:0 #ff2a85, stop:0.5 #ff00e5, stop:1 #7b2cbf)",
        "border": "#ff4da6",
        "text": "#ffffff",
    },
    "solar": {
        "bg": "qlineargradient(x1:0, y1:0, x2:1, y2:1, stop:0 #ff9e00, stop:0.55 #ff006e, stop:1 #4a0d36)",
        "hover": "qlineargradient(x1:0, y1:0, x2:1, y2:1, stop:0 #ffd166, stop:0.5 #ff5400, stop:1 #ff006e)",
        "checked": "qlineargradient(x1:0, y1:0, x2:1, y2:1, stop:0 #ffe600, stop:0.5 #ff5400, stop:1 #ff007f)",
        "border": "#ffbe0b",
        "text": "#ffffff",
    },
    "violet": {
        "bg": "qlineargradient(x1:0, y1:0, x2:1, y2:1, stop:0 #9d4edd, stop:0.55 #5a189a, stop:1 #240046)",
        "hover": "qlineargradient(x1:0, y1:0, x2:1, y2:1, stop:0 #c77dff, stop:0.5 #9d4edd, stop:1 #f72585)",
        "checked": "qlineargradient(x1:0, y1:0, x2:1, y2:1, stop:0 #e0aaff, stop:0.5 #b5179e, stop:1 #7209b7)",
        "border": "#c77dff",
        "text": "#ffffff",
    },
    "emerald": {
        "bg": "qlineargradient(x1:0, y1:0, x2:1, y2:1, stop:0 #00e699, stop:0.55 #0096c7, stop:1 #092c3e)",
        "hover": "qlineargradient(x1:0, y1:0, x2:1, y2:1, stop:0 #38ef7d, stop:0.5 #00f5d4, stop:1 #0077b6)",
        "checked": "qlineargradient(x1:0, y1:0, x2:1, y2:1, stop:0 #00ff9d, stop:0.5 #00e5ff, stop:1 #118ab2)",
        "border": "#00ff9d",
        "text": "#ffffff",
    },
    "sunset": {
        "bg": "qlineargradient(x1:0, y1:0, x2:1, y2:1, stop:0 #ffbe0b, stop:0.5 #fb5607, stop:1 #8338ec)",
        "hover": "qlineargradient(x1:0, y1:0, x2:1, y2:1, stop:0 #ffe600, stop:0.5 #ff006e, stop:1 #9d4edd)",
        "checked": "qlineargradient(x1:0, y1:0, x2:1, y2:1, stop:0 #ffea00, stop:0.5 #ff2a85, stop:1 #7b2cbf)",
        "border": "#ff9e00",
        "text": "#ffffff",
    },
    "prism": {
        "bg": "qlineargradient(x1:0, y1:0, x2:1, y2:0, stop:0 #ff007f, stop:0.28 #ff9e00, stop:0.55 #00ff9d, stop:0.8 #00f0ff, stop:1 #9d4edd)",
        "hover": "qlineargradient(x1:0, y1:0, x2:1, y2:0, stop:0 #ff4da6, stop:0.28 #ffe600, stop:0.55 #38ef7d, stop:0.8 #66f7ff, stop:1 #c77dff)",
        "checked": "qlineargradient(x1:0, y1:0, x2:1, y2:0, stop:0 #ff00e5, stop:0.35 #00f0ff, stop:0.7 #00ff9d, stop:1 #ffe600)",
        "border": "#ffffff",
        "text": "#ffffff",
    },
    "indigo": {
        "bg": "qlineargradient(x1:0, y1:0, x2:1, y2:1, stop:0 #4361ee, stop:0.55 #3a0ca3, stop:1 #1a1040)",
        "hover": "qlineargradient(x1:0, y1:0, x2:1, y2:1, stop:0 #4cc9f0, stop:0.5 #4361ee, stop:1 #7209b7)",
        "checked": "qlineargradient(x1:0, y1:0, x2:1, y2:1, stop:0 #00f0ff, stop:0.5 #4361ee, stop:1 #b5179e)",
        "border": "#4cc9f0",
        "text": "#ffffff",
    },
    "crimson": {
        "bg": "qlineargradient(x1:0, y1:0, x2:1, y2:1, stop:0 #ff2a6d, stop:0.55 #b91c1c, stop:1 #3b0722)",
        "hover": "qlineargradient(x1:0, y1:0, x2:1, y2:1, stop:0 #ff5c8a, stop:0.5 #ff0055, stop:1 #ff7b00)",
        "checked": "qlineargradient(x1:0, y1:0, x2:1, y2:1, stop:0 #ff0055, stop:0.5 #ff4d6d, stop:1 #ff9e00)",
        "border": "#ff4d6d",
        "text": "#ffffff",
    },
    "aurora": {
        "bg": "qlineargradient(x1:0, y1:0, x2:1, y2:0, stop:0 #00f5d4, stop:0.45 #3a86ff, stop:1 #ff007f)",
        "hover": "qlineargradient(x1:0, y1:0, x2:1, y2:0, stop:0 #56ffe2, stop:0.45 #60a5fa, stop:1 #ff4da6)",
        "checked": "qlineargradient(x1:0, y1:0, x2:1, y2:0, stop:0 #00ff9d, stop:0.5 #00f0ff, stop:1 #ff00e5)",
        "border": "#7dd3fc",
        "text": "#ffffff",
    },
}


def sample_cyber_rainbow(phase: float, alpha: int = 255) -> QColor:
    """Smoothly interpolates a color along :data:`CYBER_RAINBOW_STOPS`."""
    n = len(CYBER_RAINBOW_STOPS)
    pos = (phase % 1.0) * n
    idx = int(pos) % n
    frac = pos - int(pos)
    c1 = QColor(CYBER_RAINBOW_STOPS[idx])
    c2 = QColor(CYBER_RAINBOW_STOPS[(idx + 1) % n])
    return QColor(
        int(c1.red() + (c2.red() - c1.red()) * frac),
        int(c1.green() + (c2.green() - c1.green()) * frac),
        int(c1.blue() + (c2.blue() - c1.blue()) * frac),
        max(0, min(255, int(alpha))),
    )


def style_cyber_button(
    button: QAbstractButton,
    theme_key: str,
    *,
    compact: bool = False,
    radius: int = 6,
) -> None:
    """Applies a colorful glossy Cyber Neon gradient stylesheet to a button."""
    spec = CYBER_BUTTON_THEMES.get(theme_key, CYBER_BUTTON_THEMES["cyan"])
    cls = "QToolButton" if isinstance(button, QToolButton) else "QPushButton"
    pad = "3px 6px" if compact else "5px 12px"
    font_size = "9pt" if compact else "9.5pt"
    button.setProperty("cyberTheme", theme_key)
    button.setStyleSheet(
        f"""
        {cls} {{
            background: {spec['bg']};
            color: {spec['text']};
            border: 1px solid {spec['border']};
            border-radius: {radius}px;
            padding: {pad};
            font-size: {font_size};
            font-weight: 700;
        }}
        {cls}:hover {{
            background: {spec['hover']};
            border: 1px solid #ffffff;
            color: #ffffff;
        }}
        {cls}:pressed {{
            background: {spec['checked']};
            border: 1px solid #ffffff;
            color: #ffffff;
        }}
        {cls}:checked {{
            background: {spec['checked']};
            border: 2px solid #ffffff;
            color: #ffffff;
        }}
        {cls}:disabled {{
            background: #17142b;
            border: 1px solid #302850;
            color: #6b6789;
        }}
        """
    )


class CyberNeonClock(QObject):
    """Single shared animation clock driving all rainbow borders, lines, and glows in a dialog."""

    tick = Signal(float)

    def __init__(
        self,
        owner: QWidget,
        *,
        interval_ms: int = 45,
        cycle_ms: int = 3600,
    ) -> None:
        super().__init__(owner)
        self._owner = owner
        self._phase = 0.0
        self._step = interval_ms / float(max(400, cycle_ms))
        self._timer = QTimer(self)
        self._timer.setInterval(interval_ms)
        self._timer.timeout.connect(self._on_timeout)
        owner.installEventFilter(self)
        if owner.isVisible():
            self._timer.start()

    @property
    def phase(self) -> float:
        return self._phase

    @property
    def is_running(self) -> bool:
        return self._timer.isActive()

    def start(self) -> None:
        if not self._timer.isActive():
            self._timer.start()

    def stop(self) -> None:
        if self._timer.isActive():
            self._timer.stop()

    def advance(self, delta: float = 0.05) -> None:
        """Deterministic helper (also useful in tests) to advance rainbow phase."""
        self._phase = (self._phase + delta) % 1.0
        self.tick.emit(self._phase)

    def _on_timeout(self) -> None:
        try:
            if not self._owner.isVisible():
                self._timer.stop()
                return
        except RuntimeError:
            self._timer.stop()
            return
        self._phase = (self._phase + self._step) % 1.0
        self.tick.emit(self._phase)

    def eventFilter(self, watched: QObject, event: QEvent) -> bool:
        if watched is self._owner:
            etype = event.type()
            if etype == QEvent.Show:
                self.start()
            elif etype in (QEvent.Hide, QEvent.Close):
                self.stop()
        return super().eventFilter(watched, event)


class CyberNeonLine(QWidget):
    """Glowing animated rainbow laser divider line (horizontal or vertical)."""

    def __init__(
        self,
        clock: CyberNeonClock,
        orientation: Qt.Orientation = Qt.Horizontal,
        thickness: int = 3,
        phase_offset: float = 0.0,
        parent: Optional[QWidget] = None,
    ) -> None:
        super().__init__(parent)
        self._clock = clock
        self._orientation = orientation
        self._phase_offset = float(phase_offset)
        self._thickness = max(2, int(thickness))
        if orientation == Qt.Horizontal:
            self.setFixedHeight(self._thickness + 4)
        else:
            self.setFixedWidth(self._thickness + 2)
            self.setMinimumHeight(20)
        self.setAttribute(Qt.WA_TransparentForMouseEvents, True)
        self._clock.tick.connect(self._on_tick)

    def _on_tick(self, _phase: float) -> None:
        try:
            if self.isVisible():
                self.update()
        except RuntimeError:
            pass

    def paintEvent(self, event: QPaintEvent) -> None:
        w, h = self.width(), self.height()
        if w <= 0 or h <= 0:
            return
        painter = QPainter(self)
        painter.setRenderHint(QPainter.Antialiasing, True)
        phase = (self._clock.phase + self._phase_offset) % 1.0

        if self._orientation == Qt.Horizontal:
            grad = QLinearGradient(0.0, 0.0, float(w), 0.0)
            for i in range(6):
                t = i / 5.0
                grad.setColorAt(t, sample_cyber_rainbow(phase + t * 0.75, 240))
            cy = h / 2.0
            # Soft outer neon aura
            aura = QLinearGradient(0.0, 0.0, float(w), 0.0)
            for i in range(6):
                t = i / 5.0
                aura.setColorAt(t, sample_cyber_rainbow(phase + t * 0.75, 95))
            painter.setPen(QPen(QBrush(aura), float(self._thickness + 3), Qt.SolidLine, Qt.RoundCap))
            painter.drawLine(QPointF(2.0, cy), QPointF(w - 2.0, cy))
            # Vivid core
            painter.setPen(QPen(QBrush(grad), float(self._thickness), Qt.SolidLine, Qt.RoundCap))
            painter.drawLine(QPointF(2.0, cy), QPointF(w - 2.0, cy))
            # White-hot specular gleam
            painter.setPen(QPen(QColor(255, 255, 255, 130), 1.0, Qt.SolidLine, Qt.RoundCap))
            painter.drawLine(QPointF(4.0, cy - 0.5), QPointF(w - 4.0, cy - 0.5))
        else:
            grad = QLinearGradient(0.0, 0.0, 0.0, float(h))
            for i in range(5):
                t = i / 4.0
                grad.setColorAt(t, sample_cyber_rainbow(phase + t * 0.75, 235))
            cx = w / 2.0
            aura = QLinearGradient(0.0, 0.0, 0.0, float(h))
            for i in range(5):
                t = i / 4.0
                aura.setColorAt(t, sample_cyber_rainbow(phase + t * 0.75, 90))
            painter.setPen(QPen(QBrush(aura), float(self._thickness + 2), Qt.SolidLine, Qt.RoundCap))
            painter.drawLine(QPointF(cx, 3.0), QPointF(cx, h - 3.0))
            painter.setPen(QPen(QBrush(grad), float(max(1.5, self._thickness - 0.5)), Qt.SolidLine, Qt.RoundCap))
            painter.drawLine(QPointF(cx, 3.0), QPointF(cx, h - 3.0))
        painter.end()


def _paint_cyber_rainbow_frame(
    widget: QWidget,
    phase: float,
    *,
    radius: float = 10.0,
    phase_offset: float = 0.0,
    bg_top: str = "#130b2b",
    bg_bottom: str = "#090617",
    corner_ticks: bool = True,
) -> None:
    """Shared painter rendering cyber-glass surface + rotating rainbow border + HUD ticks."""
    rect = QRectF(widget.rect()).adjusted(1.5, 1.5, -1.5, -1.5)
    if rect.width() <= 4 or rect.height() <= 4:
        return

    painter = QPainter(widget)
    painter.setRenderHint(QPainter.Antialiasing, True)

    path = QPainterPath()
    path.addRoundedRect(rect, radius, radius)

    # 1. Deep cyber-glass body gradient
    bg = QLinearGradient(rect.topLeft(), rect.bottomRight())
    bg.setColorAt(0.0, QColor(bg_top))
    bg.setColorAt(0.55, QColor("#0d0924"))
    bg.setColorAt(1.0, QColor(bg_bottom))
    painter.fillPath(path, QBrush(bg))

    # 2. Subtle glossy top specular sheen
    sheen_rect = QRectF(rect.left() + 1, rect.top() + 1, rect.width() - 2, min(26.0, rect.height() * 0.42))
    sheen_path = QPainterPath()
    sheen_path.addRoundedRect(sheen_rect, max(2.0, radius - 1), max(2.0, radius - 1))
    sheen = QLinearGradient(sheen_rect.topLeft(), sheen_rect.bottomLeft())
    sheen.setColorAt(0.0, QColor(255, 255, 255, 28))
    sheen.setColorAt(1.0, QColor(255, 255, 255, 0))
    painter.fillPath(sheen_path, QBrush(sheen))

    # 3. Animated rainbow perimeter glow + crisp border
    eff_phase = (phase + phase_offset) % 1.0
    grad = QConicalGradient(rect.center(), -eff_phase * 360.0)
    n = len(CYBER_RAINBOW_STOPS)
    for idx, hex_col in enumerate(CYBER_RAINBOW_STOPS):
        grad.setColorAt(idx / float(n), QColor(hex_col))
    grad.setColorAt(1.0, QColor(CYBER_RAINBOW_STOPS[0]))

    # Outer soft bloom stroke
    painter.setPen(QPen(QBrush(grad), 4.0, Qt.SolidLine, Qt.RoundCap, Qt.RoundJoin))
    painter.setOpacity(0.28)
    painter.drawPath(path)

    # Crisp neon tube border
    painter.setOpacity(0.95)
    painter.setPen(QPen(QBrush(grad), 1.6, Qt.SolidLine, Qt.RoundCap, Qt.RoundJoin))
    painter.drawPath(path)

    # 4. Futuristic HUD corner reticles
    if corner_ticks and rect.width() > 60 and rect.height() > 28:
        tick = 8.0
        c_cyan = sample_cyber_rainbow(eff_phase + 0.55, 230)
        c_mag = sample_cyber_rainbow(eff_phase, 230)
        painter.setPen(QPen(c_cyan, 2.0, Qt.SolidLine, Qt.RoundCap))
        # Top-left & bottom-right
        painter.drawLine(QPointF(rect.left() + 2, rect.top() + tick), QPointF(rect.left() + 2, rect.top() + 2))
        painter.drawLine(QPointF(rect.left() + 2, rect.top() + 2), QPointF(rect.left() + tick, rect.top() + 2))
        painter.drawLine(QPointF(rect.right() - tick, rect.bottom() - 2), QPointF(rect.right() - 2, rect.bottom() - 2))
        painter.drawLine(QPointF(rect.right() - 2, rect.bottom() - tick), QPointF(rect.right() - 2, rect.bottom() - 2))

        painter.setPen(QPen(c_mag, 2.0, Qt.SolidLine, Qt.RoundCap))
        # Top-right & bottom-left
        painter.drawLine(QPointF(rect.right() - tick, rect.top() + 2), QPointF(rect.right() - 2, rect.top() + 2))
        painter.drawLine(QPointF(rect.right() - 2, rect.top() + 2), QPointF(rect.right() - 2, rect.top() + tick))
        painter.drawLine(QPointF(rect.left() + 2, rect.bottom() - tick), QPointF(rect.left() + 2, rect.bottom() - 2))
        painter.drawLine(QPointF(rect.left() + 2, rect.bottom() - 2), QPointF(rect.left() + tick, rect.bottom() - 2))

    painter.end()


class CyberRainbowBorderFrame(QFrame):
    """Dark cyber-glass container framed with a rotating rainbow neon tube border."""

    def __init__(
        self,
        clock: CyberNeonClock,
        *,
        radius: float = 10.0,
        phase_offset: float = 0.0,
        corner_ticks: bool = True,
        parent: Optional[QWidget] = None,
    ) -> None:
        super().__init__(parent)
        self._clock = clock
        self._radius = float(radius)
        self._phase_offset = float(phase_offset)
        self._corner_ticks = corner_ticks
        self._clock.tick.connect(self._on_tick)

    def _on_tick(self, _phase: float) -> None:
        try:
            if self.isVisible():
                self.update()
        except RuntimeError:
            pass

    def paintEvent(self, event: QPaintEvent) -> None:
        _paint_cyber_rainbow_frame(
            self,
            self._clock.phase,
            radius=self._radius,
            phase_offset=self._phase_offset,
            corner_ticks=self._corner_ticks,
        )


class _CyberInputBorderOverlay(QWidget):
    """Transparent rainbow neon contour painted directly around an input widget."""

    def __init__(self, target: QWidget, clock: CyberNeonClock, phase_offset: float) -> None:
        super().__init__(target)
        self._target = target
        self._clock = clock
        self._phase_offset = phase_offset
        self._active_boost = 0.0  # 0.0 resting rainbow, 0.55 hover, 1.0 focus
        self.setAttribute(Qt.WA_TransparentForMouseEvents, True)
        self.setAttribute(Qt.WA_NoSystemBackground, True)
        self.setGeometry(target.rect())
        self.show()
        self.raise_()

    def set_boost(self, boost: float) -> None:
        self._active_boost = max(0.0, min(1.0, float(boost)))
        self.update()

    def paintEvent(self, event: QPaintEvent) -> None:
        rect = QRectF(self.rect()).adjusted(1.0, 1.0, -1.0, -1.0)
        if rect.width() <= 4 or rect.height() <= 4:
            return
        painter = QPainter(self)
        painter.setRenderHint(QPainter.Antialiasing, True)
        phase = (self._clock.phase + self._phase_offset) % 1.0

        grad = QLinearGradient(rect.topLeft(), rect.bottomRight())
        for i in range(6):
            t = i / 5.0
            grad.setColorAt(t, sample_cyber_rainbow(phase + t * 0.85, 255))

        path = QPainterPath()
        path.addRoundedRect(rect, 6.0, 6.0)

        # Outer halo layer (amplifies on hover/focus)
        outer_alpha = 0.28 + 0.42 * self._active_boost
        outer_width = 2.8 + 2.4 * self._active_boost
        painter.setOpacity(outer_alpha)
        painter.setPen(QPen(QBrush(grad), outer_width, Qt.SolidLine, Qt.RoundCap, Qt.RoundJoin))
        painter.drawPath(path)

        # Crisp color-changing rainbow tube border
        painter.setOpacity(0.88 + 0.12 * self._active_boost)
        painter.setPen(QPen(QBrush(grad), 1.6 + 0.5 * self._active_boost, Qt.SolidLine, Qt.RoundCap, Qt.RoundJoin))
        painter.drawPath(path)

        # Crisp vector ▲ / ▼ chevron triangles on QSpinBox up/down buttons
        if isinstance(self._target, QAbstractSpinBox):
            w_r, h_r = float(self.width()), float(self.height())
            cx = w_r - 10.5
            up_y = h_r * 0.28
            dn_y = h_r * 0.72
            painter.setOpacity(0.95)
            painter.setPen(Qt.NoPen)
            painter.setBrush(QColor("#ffffff"))
            up_tri = QPainterPath()
            up_tri.moveTo(cx, up_y - 2.6)
            up_tri.lineTo(cx - 3.6, up_y + 2.2)
            up_tri.lineTo(cx + 3.6, up_y + 2.2)
            up_tri.closeSubpath()
            painter.drawPath(up_tri)

            dn_tri = QPainterPath()
            dn_tri.moveTo(cx, dn_y + 2.6)
            dn_tri.lineTo(cx - 3.6, dn_y - 2.2)
            dn_tri.lineTo(cx + 3.6, dn_y - 2.2)
            dn_tri.closeSubpath()
            painter.drawPath(dn_tri)

        painter.end()


class CyberNeonInputHalo(QObject):
    """Wraps a textbox/spinbox with an animated color-changing rainbow neon border."""

    def __init__(self, widget: QWidget, clock: CyberNeonClock, phase_offset: float = 0.0) -> None:
        super().__init__(widget)
        self._widget = widget
        self._clock = clock
        self._hovered = False
        self._focused = widget.hasFocus()
        self._overlay = _CyberInputBorderOverlay(widget, clock, phase_offset)

        widget.installEventFilter(self)
        if isinstance(widget, QAbstractSpinBox) and widget.lineEdit():
            widget.lineEdit().installEventFilter(self)
        self._clock.tick.connect(self._on_tick)
        self._sync_boost()

    @property
    def overlay(self) -> QWidget:
        return self._overlay

    def _sync_boost(self) -> None:
        boost = 1.0 if self._focused else (0.55 if self._hovered else 0.0)
        try:
            self._overlay.set_boost(boost)
        except RuntimeError:
            pass

    def _on_tick(self, _phase: float) -> None:
        try:
            if self._widget.isVisible():
                self._overlay.update()
        except RuntimeError:
            pass

    def eventFilter(self, watched: QObject, event: QEvent) -> bool:
        etype = event.type()
        if watched is self._widget and etype in (QEvent.Resize, QEvent.Show, QEvent.LayoutRequest):
            try:
                self._overlay.setGeometry(self._widget.rect())
                self._overlay.raise_()
            except RuntimeError:
                pass
        elif etype in (QEvent.Enter, QEvent.HoverEnter):
            self._hovered = True
            self._sync_boost()
        elif etype in (QEvent.Leave, QEvent.HoverLeave):
            if watched is self._widget:
                self._hovered = False
                self._sync_boost()
        elif etype == QEvent.FocusIn:
            self._focused = True
            self._sync_boost()
        elif etype == QEvent.FocusOut:
            try:
                still_focused = self._widget.hasFocus()
                if not still_focused and isinstance(self._widget, QAbstractSpinBox) and self._widget.lineEdit():
                    still_focused = self._widget.lineEdit().hasFocus()
            except RuntimeError:
                still_focused = False
            self._focused = bool(still_focused)
            self._sync_boost()
        return super().eventFilter(watched, event)


def install_cyber_input_halos(roots: Iterable[QWidget], clock: CyberNeonClock) -> int:
    """Installs animated rainbow neon borders on all textboxes & spinboxes under *roots*."""
    target_types = (QTextEdit, QPlainTextEdit, QLineEdit, QAbstractSpinBox)
    count = 0
    seen: set[int] = set()
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
            if isinstance(widget, QLineEdit) and isinstance(parent, QAbstractSpinBox):
                continue
            wid = id(widget)
            if wid in seen:
                continue
            seen.add(wid)
            if getattr(widget, "_cyber_input_halo", None) is None:
                halo = CyberNeonInputHalo(widget, clock, phase_offset=(count * 0.17) % 1.0)
                widget._cyber_input_halo = halo  # type: ignore[attr-defined]
                count += 1
    return count


class _CyberButtonShineOverlay(QWidget):
    """Translucent click-shine overlay rendering specular sweep + electric starburst ripple."""

    def __init__(self, button: QAbstractButton) -> None:
        super().__init__(button)
        self._progress = 0.0
        self._origin = QPointF(button.width() / 2.0, button.height() / 2.0)
        self._hue_seed = (id(button) % 9) / 9.0
        self.setAttribute(Qt.WA_TransparentForMouseEvents, True)
        self.setAttribute(Qt.WA_NoSystemBackground, True)
        self.hide()

    def set_frame(self, progress: float, origin: QPointF) -> None:
        self._progress = max(0.0, min(1.0, float(progress)))
        self._origin = origin
        self.update()

    def paintEvent(self, event: QPaintEvent) -> None:
        w, h = float(self.width()), float(self.height())
        if w <= 2 or h <= 2 or self._progress <= 0.0 or self._progress >= 1.0:
            return
        painter = QPainter(self)
        painter.setRenderHint(QPainter.Antialiasing, True)

        clip_path = QPainterPath()
        clip_path.addRoundedRect(QRectF(0.5, 0.5, w - 1.0, h - 1.0), 6.0, 6.0)
        painter.setClipPath(clip_path)

        p = self._progress
        fade = math.sin(p * math.pi)  # Smooth 0 -> 1 -> 0 envelope

        # 1. Diagonal glossy white + rainbow prismatic light-sweep across the button
        sweep_x = -w * 0.5 + p * (w * 2.1)
        band = max(18.0, w * 0.42)
        sweep = QLinearGradient(sweep_x - band, 0.0, sweep_x + band, h)
        c_prism_a = sample_cyber_rainbow(self._hue_seed + p * 0.6, int(185 * fade))
        c_prism_b = sample_cyber_rainbow(self._hue_seed + p * 0.6 + 0.35, int(185 * fade))
        sweep.setColorAt(0.0, QColor(255, 255, 255, 0))
        sweep.setColorAt(0.28, c_prism_a)
        sweep.setColorAt(0.50, QColor(255, 255, 255, int(235 * fade)))
        sweep.setColorAt(0.72, c_prism_b)
        sweep.setColorAt(1.0, QColor(255, 255, 255, 0))
        painter.fillRect(self.rect(), QBrush(sweep))

        # 2. Expanding electric neon click ripple + bright center spark
        max_r = math.hypot(w, h) * 0.85
        radius = max(3.0, p * max_r)
        ring_color = sample_cyber_rainbow(self._hue_seed + 0.25 + p * 0.8, int(230 * (1.0 - p)))
        painter.setPen(QPen(ring_color, 2.2))
        painter.setBrush(Qt.NoBrush)
        painter.drawEllipse(self._origin, radius, radius)

        if p < 0.45:
            spark_alpha = int(220 * (1.0 - p / 0.45))
            spark_grad = QRadialGradient(self._origin, max(8.0, radius * 0.65))
            spark_grad.setColorAt(0.0, QColor(255, 255, 255, spark_alpha))
            spark_grad.setColorAt(0.55, sample_cyber_rainbow(self._hue_seed + 0.5, int(spark_alpha * 0.6)))
            spark_grad.setColorAt(1.0, QColor(255, 255, 255, 0))
            painter.setPen(Qt.NoPen)
            painter.setBrush(QBrush(spark_grad))
            painter.drawEllipse(self._origin, max(8.0, radius * 0.65), max(8.0, radius * 0.65))

        # 3. Momentary bright neon flash rim
        rim_color = sample_cyber_rainbow(self._hue_seed + p, int(245 * fade))
        painter.setPen(QPen(rim_color, 2.0))
        painter.setBrush(Qt.NoBrush)
        painter.drawRoundedRect(QRectF(1.0, 1.0, w - 2.0, h - 2.0), 5.5, 5.5)
        painter.end()


class CyberClickShineEffect(QObject):
    """Triggers a glossy prism light-sweep & neon ripple whenever a button is clicked."""

    def __init__(self, button: QAbstractButton, duration_ms: int = 340) -> None:
        super().__init__(button)
        self._button = button
        self._duration_ms = max(120, int(duration_ms))
        self._overlay = _CyberButtonShineOverlay(button)
        self._origin = QPointF(button.width() / 2.0, button.height() / 2.0)
        self._pressed_recently = False

        self._anim = QVariantAnimation(self)
        self._anim.setStartValue(0.0)
        self._anim.setEndValue(1.0)
        self._anim.setDuration(self._duration_ms)
        self._anim.setEasingCurve(QEasingCurve.OutCubic)
        self._anim.valueChanged.connect(self._on_step)
        self._anim.finished.connect(self._on_finished)

        button.installEventFilter(self)
        button.clicked.connect(self._on_clicked)

    @property
    def is_shining(self) -> bool:
        return self._anim.state() == QVariantAnimation.Running

    def trigger(self, origin: Optional[QPointF] = None) -> None:
        """Plays the shiny sweep + starburst ripple from *origin* (defaults to center)."""
        try:
            self._overlay.setGeometry(self._button.rect())
            self._origin = (
                QPointF(origin)
                if origin is not None
                else QPointF(self._button.width() / 2.0, self._button.height() / 2.0)
            )
            self._overlay.show()
            self._overlay.raise_()
        except RuntimeError:
            return
        self._anim.stop()
        self._anim.start()

    def _on_clicked(self) -> None:
        if self._pressed_recently:
            self._pressed_recently = False
            return
        self.trigger(None)

    def _on_step(self, val) -> None:
        try:
            self._overlay.set_frame(float(val), self._origin)
        except RuntimeError:
            self._anim.stop()

    def _on_finished(self) -> None:
        try:
            self._overlay.hide()
        except RuntimeError:
            pass

    def eventFilter(self, watched: QObject, event: QEvent) -> bool:
        if watched is self._button:
            etype = event.type()
            if etype == QEvent.MouseButtonPress and isinstance(event, QMouseEvent):
                if event.button() == Qt.LeftButton and self._button.isEnabled():
                    self._pressed_recently = True
                    pos = event.position() if hasattr(event, "position") else QPointF(event.pos())
                    self.trigger(pos)
            elif etype == QEvent.Resize:
                try:
                    self._overlay.setGeometry(self._button.rect())
                except RuntimeError:
                    pass
            elif etype == QEvent.Hide:
                self._anim.stop()
                try:
                    self._overlay.hide()
                except RuntimeError:
                    pass
        return super().eventFilter(watched, event)


def apply_cyber_click_shine(roots: Iterable[QWidget]) -> int:
    """Installs :class:`CyberClickShineEffect` on all push/tool buttons under *roots*."""
    count = 0
    seen: set[int] = set()
    for root in roots:
        if root is None:
            continue
        candidates = list(root.findChildren(QAbstractButton))
        if isinstance(root, QAbstractButton):
            candidates.insert(0, root)
        for btn in candidates:
            if not isinstance(btn, (QPushButton, QToolButton)):
                continue
            bid = id(btn)
            if bid in seen:
                continue
            seen.add(bid)
            if getattr(btn, "_cyber_click_shine", None) is None:
                btn._cyber_click_shine = CyberClickShineEffect(btn)  # type: ignore[attr-defined]
                count += 1
    return count


class _CyberNeonSplitterHandle(QSplitterHandle):
    """Animated neon energy splitter handle between canvas and inspector."""

    def __init__(self, orientation: Qt.Orientation, parent: QSplitter, clock: CyberNeonClock) -> None:
        super().__init__(orientation, parent)
        self._clock = clock
        self._hovered = False
        self.setMouseTracking(True)
        self._clock.tick.connect(self._on_tick)

    def _on_tick(self, _phase: float) -> None:
        try:
            if self.isVisible():
                self.update()
        except RuntimeError:
            pass

    def enterEvent(self, event) -> None:
        self._hovered = True
        self.update()
        super().enterEvent(event)

    def leaveEvent(self, event) -> None:
        self._hovered = False
        self.update()
        super().leaveEvent(event)

    def paintEvent(self, event: QPaintEvent) -> None:
        w, h = self.width(), self.height()
        painter = QPainter(self)
        painter.setRenderHint(QPainter.Antialiasing, True)
        painter.fillRect(self.rect(), QColor("#080518"))

        phase = self._clock.phase
        grad = QLinearGradient(0.0, 0.0, 0.0, float(h))
        for i in range(6):
            t = i / 5.0
            grad.setColorAt(t, sample_cyber_rainbow(phase + t * 0.85, 255 if self._hovered else 175))

        cx = w / 2.0
        painter.setPen(QPen(QBrush(grad), 3.0 if self._hovered else 1.8, Qt.SolidLine, Qt.RoundCap))
        painter.drawLine(QPointF(cx, 6.0), QPointF(cx, h - 6.0))

        # Three glowing plasma grip dots at center
        cy = h / 2.0
        for dy in (-14.0, 0.0, 14.0):
            dot_col = sample_cyber_rainbow(phase + (dy + 14.0) * 0.015, 240)
            painter.setPen(Qt.NoPen)
            painter.setBrush(dot_col)
            painter.drawEllipse(QPointF(cx, cy + dy), 2.2 if self._hovered else 1.6, 2.2 if self._hovered else 1.6)
        painter.end()


class CyberNeonSplitter(QSplitter):
    """QSplitter featuring an animated rainbow neon energy handle."""

    def __init__(self, orientation: Qt.Orientation, clock: CyberNeonClock, parent: Optional[QWidget] = None) -> None:
        super().__init__(orientation, parent)
        self._clock = clock
        self.setHandleWidth(6)

    def createHandle(self) -> QSplitterHandle:
        return _CyberNeonSplitterHandle(self.orientation(), self, self._clock)
