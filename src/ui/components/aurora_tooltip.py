"""Global Neon Aurora hover tooltip overlay for T-Notes.

Replaces Qt's default flat tooltip box across the entire application via a
lightweight ``QApplication`` event filter—without modifying any buttons,
button styles, or widget event handlers.

Visual design:
- **Dynamic flowing rainbow text:** high-contrast luminous pastel-neon rainbow
  gradient smoothly scrolling across crisp, drop-shadowed typography.
- **Shining jewel-tone aurora background:** deep midnight sapphire, royal
  amethyst, and emerald-teal glass surface with gently drifting aurora pools,
  a glossy crystal top reflection, and a periodic diagonal specular sheen sweep.
- **Shining iridescent neon borders:** rotating rainbow ``QConicalGradient``
  perimeter with multi-layer translucent outer neon halo glow, chrome-bright
  inner specular bevel, and orbiting starlight border glints.
- **Smooth appear/disappear transitions:** ``windowOpacity`` fade + subtle
  floating vertical glide, respecting ``panel_transition.TRANSITIONS_ENABLED``
  so automated tests remain deterministic and synchronous.
- **Zero idle CPU:** the animation timer runs strictly while the tooltip is
  visible and stops immediately when hidden.
"""

from __future__ import annotations

import html as html_lib
import math
import re
from typing import Optional

from PySide6.QtCore import (
    QEasingCurve,
    QEvent,
    QModelIndex,
    QObject,
    QPersistentModelIndex,
    QPoint,
    QPointF,
    QRect,
    QRectF,
    QSize,
    Qt,
    QTimer,
    QVariantAnimation,
)
from PySide6.QtGui import (
    QBrush,
    QColor,
    QConicalGradient,
    QFont,
    QFontMetricsF,
    QGradient,
    QGuiApplication,
    QHelpEvent,
    QImage,
    QLinearGradient,
    QPainter,
    QPainterPath,
    QPaintEvent,
    QPen,
    QRadialGradient,
    QTextLayout,
    QTextOption,
)
from PySide6.QtWidgets import (
    QAbstractItemView,
    QAbstractScrollArea,
    QApplication,
    QMenu,
    QTabBar,
    QToolButton,
    QToolTip,
    QWidget,
)

from src.ui.components import panel_transition

# Visual geometry constants
GLOW_MARGIN: int = 11
CORNER_RADIUS: float = 10.0
PAD_X: int = 13
PAD_Y: int = 8
MAX_CONTENT_WIDTH: int = 360
CURSOR_OFFSET_X: int = 14
CURSOR_OFFSET_Y: int = 22
APPEAR_SLIDE_PX: int = 6
DISAPPEAR_SLIDE_PX: int = 3

# Timing constants
ANIMATION_INTERVAL_MS: int = 33  # ~30 FPS while visible only
PHASE_STEP_PER_TICK: float = 0.0085  # ~3.9s full prismatic cycle
APPEAR_DURATION_MS: int = 175
DISAPPEAR_DURATION_MS: int = 135

# Luminous pastel-neon rainbow stops for crisp flowing text over dark jewel glass
AURORA_TEXT_PALETTE: tuple[tuple[float, str], ...] = (
    (0.00, "#ff80df"),  # Luminous Neon Pink
    (0.16, "#ffd166"),  # Radiant Solar Gold
    (0.33, "#6ef3b8"),  # Electric Mint Emerald
    (0.50, "#5ceeff"),  # Ice Electric Cyan
    (0.67, "#8ab4ff"),  # Sky Sapphire Glow
    (0.84, "#d49bff"),  # Iridescent Lavender
    (1.00, "#ff80df"),  # Seamless wrap
)

# Vivid iridescent jewel-neon stops for rotating glowing borders & outer aura
AURORA_BORDER_PALETTE: tuple[tuple[float, str], ...] = (
    (0.00, "#00f5ff"),  # Electric Cyan
    (0.14, "#38bdf8"),  # Sapphire Sky
    (0.28, "#818cf8"),  # Cosmic Indigo
    (0.42, "#c084fc"),  # Royal Amethyst
    (0.57, "#f472b6"),  # Prism Rose
    (0.71, "#fbbf24"),  # Solar Gold
    (0.85, "#34d399"),  # Radiant Emerald
    (1.00, "#00f5ff"),  # Seamless wrap
)

_HTML_TAG_RE = re.compile(
    r"<\s*/?\s*(?:b|i|u|s|br|p|div|span|font|strong|em|ul|ol|li|code|pre|html|body|a|h[1-6]|small|big|sup|sub|hr|table|tr|td|th)\b[^>]*>",
    re.IGNORECASE,
)
_TAG_BREAK_RE = re.compile(r"<\s*(?:br\s*/?|/\s*p|/\s*div|/\s*li|hr\s*/?)\s*>", re.IGNORECASE)


def normalize_tooltip_text(raw: str) -> str:
    """Converts plain or basic Qt rich-text tooltip strings into clean lines."""
    if not raw:
        return ""
    text = raw
    if _HTML_TAG_RE.search(text):
        text = _TAG_BREAK_RE.sub("\n", text)
        text = _HTML_TAG_RE.sub("", text)
        text = html_lib.unescape(text)
    lines = [line.rstrip() for line in text.replace("\r\n", "\n").replace("\r", "\n").split("\n")]
    # Trim leading/trailing blank lines while preserving internal paragraph breaks
    while lines and not lines[0].strip():
        lines.pop(0)
    while lines and not lines[-1].strip():
        lines.pop()
    return "\n".join(lines)


def _transitions_enabled() -> bool:
    return bool(getattr(panel_transition, "TRANSITIONS_ENABLED", True))


class AuroraToolTipWidget(QWidget):
    """Translucent frameless hover tooltip with flowing rainbow text and glowing jewel-aurora glass."""

    def __init__(self, parent: Optional[QWidget] = None):
        super().__init__(
            parent,
            Qt.ToolTip
            | Qt.FramelessWindowHint
            | Qt.WindowTransparentForInput
            | Qt.NoDropShadowWindowHint,
        )
        self.setObjectName("auroraToolTip")
        self.setAttribute(Qt.WA_TranslucentBackground, True)
        self.setAttribute(Qt.WA_ShowWithoutActivating, True)
        self.setAttribute(Qt.WA_TransparentForMouseEvents, True)
        self.setFocusPolicy(Qt.NoFocus)

        self._text: str = ""
        self._phase: float = 0.0
        self._gleam_boost: float = 0.0
        self._lines: list[tuple[QTextLayout, QPointF]] = []
        self._text_rect: QRectF = QRectF()
        self._target_pos: QPoint = QPoint()
        self._start_y: int = 0
        self._end_y: int = 0
        self._hiding: bool = False
        self._opacity_start: float = 0.0
        self._opacity_end: float = 1.0

        self._font = QFont("Segoe UI", 9)
        self._font.setPointSizeF(9.5)
        self._font.setWeight(QFont.DemiBold)
        self._font.setHintingPreference(QFont.PreferFullHinting)

        # Single lightweight animation timer: runs strictly while visible
        self._anim_timer = QTimer(self)
        self._anim_timer.setInterval(ANIMATION_INTERVAL_MS)
        self._anim_timer.timeout.connect(self._on_anim_tick)

        # Smooth appear / disappear transition driver
        self._transition = QVariantAnimation(self)
        self._transition.valueChanged.connect(self._on_transition_step)
        self._transition.finished.connect(self._on_transition_finished)

    # -- public state accessors ------------------------------------------------
    @property
    def text(self) -> str:
        return self._text

    @property
    def phase(self) -> float:
        return self._phase

    @property
    def is_animating_effects(self) -> bool:
        return self._anim_timer.isActive()

    @property
    def is_transitioning(self) -> bool:
        return self._transition.state() == QVariantAnimation.Running

    @property
    def is_hiding(self) -> bool:
        return self._hiding

    # -- text layout & sizing --------------------------------------------------
    def _rebuild_layout(self, text: str) -> QSize:
        self._text = text
        self._lines = []

        option = QTextOption()
        option.setWrapMode(QTextOption.WrapAtWordBoundaryOrAnywhere)

        fm = QFontMetricsF(self._font)
        line_spacing = max(fm.lineSpacing(), fm.height() + 2.0)

        y = 0.0
        max_w = 0.0
        paragraphs = text.split("\n") if text else [""]

        for para in paragraphs:
            if not para:
                y += line_spacing * 0.65
                continue
            layout = QTextLayout(para, self._font)
            layout.setTextOption(option)
            layout.beginLayout()
            while True:
                line = layout.createLine()
                if not line.isValid():
                    break
                line.setLineWidth(MAX_CONTENT_WIDTH)
                line.setPosition(QPointF(0.0, y))
                max_w = max(max_w, line.naturalTextWidth())
                y += line_spacing
            layout.endLayout()
            self._lines.append((layout, QPointF(0.0, 0.0)))

        content_w = max(28.0, math.ceil(max_w))
        content_h = max(math.ceil(fm.height()), math.ceil(y))
        card_w = int(content_w + PAD_X * 2)
        card_h = int(content_h + PAD_Y * 2)

        total_w = card_w + GLOW_MARGIN * 2
        total_h = card_h + GLOW_MARGIN * 2
        self._text_rect = QRectF(
            GLOW_MARGIN + PAD_X,
            GLOW_MARGIN + PAD_Y,
            content_w,
            content_h,
        )
        return QSize(total_w, total_h)

    def _compute_screen_clamped_pos(self, global_pos: QPoint, size: QSize) -> QPoint:
        """Positions the tooltip cleanly near the pointer inside active monitor bounds."""
        screen = QGuiApplication.screenAt(global_pos) or QGuiApplication.primaryScreen()
        avail = screen.availableGeometry() if screen is not None else QRect(0, 0, 1920, 1080)

        w, h = size.width(), size.height()
        # Anchor the inner card near the cursor, accounting for outer glow margin
        x = global_pos.x() + CURSOR_OFFSET_X - GLOW_MARGIN
        y = global_pos.y() + CURSOR_OFFSET_Y - GLOW_MARGIN

        # Flip above cursor if bottom edge would clip below taskbar/screen bottom
        if y + h > avail.bottom() + 1:
            above_y = global_pos.y() - h - 10 + GLOW_MARGIN
            if above_y >= avail.top():
                y = above_y
            else:
                y = avail.bottom() - h + 1

        # Keep strictly inside horizontal screen bounds (supports negative multi-monitor x/y)
        max_x = avail.right() - w + 1
        max_y = avail.bottom() - h + 1
        x = max(avail.left(), min(x, max_x))
        y = max(avail.top(), min(y, max_y))
        return QPoint(int(x), int(y))

    # -- show / hide with smooth transitions -----------------------------------
    def show_tooltip(self, global_pos: QPoint, raw_text: str) -> bool:
        """Displays or smoothly updates the aurora tooltip at ``global_pos``."""
        text = normalize_tooltip_text(raw_text)
        if not text:
            self.hide_tooltip()
            return False

        was_visible = self.isVisible() and not self._hiding
        text_changed = text != self._text

        size = self._rebuild_layout(text)
        self.resize(size)
        target = self._compute_screen_clamped_pos(global_pos, size)
        self._target_pos = target

        if text_changed or not was_visible:
            self._gleam_boost = 1.0

        if not _transitions_enabled():
            self._transition.stop()
            self._hiding = False
            self.move(target)
            self.setWindowOpacity(1.0)
            self.show()
            self.raise_()
            self._start_anim_timer()
            self.update()
            return True

        # Already fully visible: smoothly reposition & trigger fresh sheen pulse without flicker
        if was_visible and not self.is_transitioning:
            self.move(target)
            self.setWindowOpacity(1.0)
            self.raise_()
            self._start_anim_timer()
            self.update()
            return True

        # Start or reverse into smooth appear transition
        current_opacity = float(self.windowOpacity()) if self.isVisible() else 0.0
        self._transition.stop()
        self._hiding = False
        self._opacity_start = current_opacity
        self._opacity_end = 1.0
        self._start_y = target.y() + APPEAR_SLIDE_PX if current_opacity < 0.25 else self.y()
        self._end_y = target.y()

        self.move(target.x(), self._start_y)
        self.setWindowOpacity(current_opacity)
        if not self.isVisible():
            self.show()
        self.raise_()
        self._start_anim_timer()

        self._transition.setDuration(APPEAR_DURATION_MS)
        self._transition.setEasingCurve(QEasingCurve.OutCubic)
        self._transition.setStartValue(0.0)
        self._transition.setEndValue(1.0)
        self._transition.start()
        self.update()
        return True

    def hide_tooltip(self, immediate: bool = False) -> None:
        """Fades out and hides the tooltip (or hides immediately when requested/in tests)."""
        if not self.isVisible():
            self._hiding = False
            self._transition.stop()
            self._stop_anim_timer()
            return

        if immediate or not _transitions_enabled():
            self._transition.stop()
            self._hiding = False
            self._stop_anim_timer()
            super().hide()
            return

        if self._hiding and self.is_transitioning:
            return

        self._transition.stop()
        self._hiding = True
        self._opacity_start = float(self.windowOpacity())
        self._opacity_end = 0.0
        self._start_y = self.y()
        self._end_y = self.y() + DISAPPEAR_SLIDE_PX

        self._transition.setDuration(DISAPPEAR_DURATION_MS)
        self._transition.setEasingCurve(QEasingCurve.InCubic)
        self._transition.setStartValue(0.0)
        self._transition.setEndValue(1.0)
        self._transition.start()

    # -- animation callbacks ---------------------------------------------------
    def _start_anim_timer(self) -> None:
        if not self._anim_timer.isActive():
            self._anim_timer.start()

    def _stop_anim_timer(self) -> None:
        if self._anim_timer.isActive():
            self._anim_timer.stop()

    def _on_anim_tick(self) -> None:
        if not self.isVisible():
            self._stop_anim_timer()
            return
        self._phase = (self._phase + PHASE_STEP_PER_TICK) % 1.0
        if self._gleam_boost > 0.0:
            self._gleam_boost = max(0.0, self._gleam_boost - 0.06)
        self.update()

    def _on_transition_step(self, value) -> None:
        t = float(value)
        opacity = self._opacity_start + (self._opacity_end - self._opacity_start) * t
        y = int(round(self._start_y + (self._end_y - self._start_y) * t))
        self.setWindowOpacity(max(0.0, min(1.0, opacity)))
        self.move(self._target_pos.x(), y)

    def _on_transition_finished(self) -> None:
        if self._hiding:
            self._hiding = False
            self._stop_anim_timer()
            super().hide()
        else:
            self.setWindowOpacity(1.0)
            self.move(self._target_pos)

    def hideEvent(self, event) -> None:
        self._stop_anim_timer()
        super().hideEvent(event)

    def closeEvent(self, event) -> None:
        self._transition.stop()
        self._stop_anim_timer()
        super().closeEvent(event)

    # -- custom layered Aurora painting ----------------------------------------
    def _make_border_conical(self, center: QPointF, alpha: int = 255, phase_offset: float = 0.0) -> QConicalGradient:
        angle = ((self._phase + phase_offset) % 1.0) * 360.0
        grad = QConicalGradient(center, angle)
        for pos, hex_color in AURORA_BORDER_PALETTE:
            c = QColor(hex_color)
            c.setAlpha(alpha)
            grad.setColorAt(pos, c)
        return grad

    def _render_rainbow_text_image(self, text_rect: QRectF) -> QImage:
        """Renders anti-aliased laid-out lines filled with a smoothly flowing rainbow gradient."""
        dpr = max(1.0, float(self.devicePixelRatioF()))
        img_w = max(1, int(math.ceil((text_rect.width() + 4.0) * dpr)))
        img_h = max(1, int(math.ceil((text_rect.height() + 4.0) * dpr)))

        img = QImage(img_w, img_h, QImage.Format_ARGB32_Premultiplied)
        img.setDevicePixelRatio(dpr)
        img.fill(Qt.transparent)

        tp = QPainter(img)
        tp.setRenderHint(QPainter.Antialiasing, True)
        tp.setRenderHint(QPainter.TextAntialiasing, True)

        # 1. Paint solid white glyphs as alpha mask (preserves kerning, wrapping, full hinting)
        tp.setPen(QColor(255, 255, 255, 255))
        for layout, offset in self._lines:
            layout.draw(tp, QPointF(offset.x() + 1.0, offset.y() + 1.0))

        # 2. Fill glyphs with a continuously flowing diagonal rainbow gradient
        span = max(165.0, text_rect.width() * 1.15)
        flow_shift = self._phase * span
        grad = QLinearGradient(-flow_shift, 0.0, -flow_shift + span, text_rect.height() * 0.45)
        grad.setSpread(QGradient.RepeatSpread)
        for pos, hex_color in AURORA_TEXT_PALETTE:
            grad.setColorAt(pos, QColor(hex_color))

        tp.setCompositionMode(QPainter.CompositionMode_SourceIn)
        tp.fillRect(QRectF(0.0, 0.0, text_rect.width() + 4.0, text_rect.height() + 4.0), QBrush(grad))
        tp.end()
        return img

    def paintEvent(self, event: QPaintEvent) -> None:
        if not self._text:
            return

        painter = QPainter(self)
        painter.setRenderHint(QPainter.Antialiasing, True)
        painter.setRenderHint(QPainter.TextAntialiasing, True)
        painter.setRenderHint(QPainter.SmoothPixmapTransform, True)

        card_rect = QRectF(
            GLOW_MARGIN,
            GLOW_MARGIN,
            self.width() - GLOW_MARGIN * 2,
            self.height() - GLOW_MARGIN * 2,
        )
        if card_rect.width() <= 2 or card_rect.height() <= 2:
            painter.end()
            return

        center = card_rect.center()
        card_path = QPainterPath()
        card_path.addRoundedRect(card_rect, CORNER_RADIUS, CORNER_RADIUS)

        # 1. Multi-layer iridescent outer neon halo (6 smooth overlapping passes in GLOW_MARGIN)
        halo_layers = (
            (7.4, 6.6, 12),
            (5.8, 5.4, 22),
            (4.3, 4.3, 36),
            (3.0, 3.3, 56),
            (1.9, 2.4, 82),
            (0.9, 1.7, 118),
        )
        for expand, pen_width, alpha in halo_layers:
            halo_rect = card_rect.adjusted(-expand, -expand, expand, expand)
            halo_path = QPainterPath()
            halo_path.addRoundedRect(halo_rect, CORNER_RADIUS + expand * 0.65, CORNER_RADIUS + expand * 0.65)
            halo_grad = self._make_border_conical(center, alpha=alpha)
            pen = QPen(QBrush(halo_grad), pen_width)
            pen.setJoinStyle(Qt.RoundJoin)
            painter.setPen(pen)
            painter.setBrush(Qt.NoBrush)
            painter.drawPath(halo_path)

        # 2. Deep jewel-tone aurora glass background (clipped cleanly to rounded card)
        painter.save()
        painter.setClipPath(card_path)

        # Rich jewel diagonal base: midnight sapphire -> royal amethyst -> deep emerald-teal
        bg_grad = QLinearGradient(card_rect.topLeft(), card_rect.bottomRight())
        bg_grad.setColorAt(0.00, QColor(9, 13, 36, 244))    # Midnight Sapphire
        bg_grad.setColorAt(0.38, QColor(26, 13, 56, 245))   # Royal Amethyst
        bg_grad.setColorAt(0.74, QColor(8, 36, 52, 245))    # Deep Jewel Teal
        bg_grad.setColorAt(1.00, QColor(15, 11, 40, 246))   # Cosmic Obsidian Violet
        painter.fillPath(card_path, QBrush(bg_grad))

        # Three slowly drifting radial aurora jewel pools
        angle = self._phase * 2.0 * math.pi
        w = card_rect.width()
        h = card_rect.height()

        pools = (
            (
                QPointF(card_rect.left() + w * (0.24 + 0.14 * math.cos(angle)), card_rect.top() + h * (0.30 + 0.16 * math.sin(angle))),
                max(w, h) * 0.58,
                QColor(0, 224, 255, 74),
                QColor(14, 165, 233, 28),
            ),
            (
                QPointF(card_rect.left() + w * (0.76 + 0.12 * math.sin(angle * 1.15)), card_rect.top() + h * (0.36 + 0.18 * math.cos(angle))),
                max(w, h) * 0.56,
                QColor(192, 132, 252, 76),
                QColor(236, 72, 153, 30),
            ),
            (
                QPointF(card_rect.left() + w * (0.50 + 0.18 * math.cos(angle + 2.2)), card_rect.top() + h * (0.82 + 0.12 * math.sin(angle + 1.4))),
                max(w, h) * 0.52,
                QColor(52, 211, 153, 68),
                QColor(20, 184, 166, 26),
            ),
        )
        for pool_center, radius, c_inner, c_mid in pools:
            rg = QRadialGradient(pool_center, max(24.0, radius))
            rg.setColorAt(0.0, c_inner)
            rg.setColorAt(0.55, c_mid)
            rg.setColorAt(1.0, QColor(0, 0, 0, 0))
            painter.fillRect(card_rect, QBrush(rg))

        # Glossy top-half crystal glass sheen
        sheen_rect = QRectF(card_rect.left(), card_rect.top(), card_rect.width(), card_rect.height() * 0.52)
        sheen = QLinearGradient(sheen_rect.topLeft(), sheen_rect.bottomLeft())
        sheen.setColorAt(0.0, QColor(255, 255, 255, 48))
        sheen.setColorAt(0.35, QColor(186, 230, 253, 18))
        sheen.setColorAt(1.0, QColor(255, 255, 255, 0))
        painter.fillRect(sheen_rect, QBrush(sheen))

        # Animated diagonal jewel shimmer sweep
        sweep_progress = (self._phase * 1.35) % 1.0
        sweep_x = card_rect.left() - w * 0.45 + (w * 1.9) * sweep_progress
        band_w = max(36.0, w * 0.28)
        sweep_alpha = int(min(92, 46 + 40 * self._gleam_boost))
        sweep_grad = QLinearGradient(
            QPointF(sweep_x - band_w, card_rect.top()),
            QPointF(sweep_x + band_w, card_rect.bottom()),
        )
        sweep_grad.setColorAt(0.00, QColor(255, 255, 255, 0))
        sweep_grad.setColorAt(0.42, QColor(165, 243, 252, sweep_alpha // 2))
        sweep_grad.setColorAt(0.50, QColor(255, 255, 255, sweep_alpha))
        sweep_grad.setColorAt(0.58, QColor(232, 121, 249, sweep_alpha // 2))
        sweep_grad.setColorAt(1.00, QColor(255, 255, 255, 0))
        painter.fillRect(card_rect, QBrush(sweep_grad))

        # Subtle bottom internal aurora reflection
        bottom_glow = QLinearGradient(
            QPointF(card_rect.left(), card_rect.bottom() - h * 0.30),
            QPointF(card_rect.left(), card_rect.bottom()),
        )
        bottom_glow.setColorAt(0.0, QColor(0, 0, 0, 0))
        bottom_glow.setColorAt(1.0, QColor(56, 189, 248, 30))
        painter.fillRect(card_rect, QBrush(bottom_glow))

        painter.restore()

        # 3. Primary crisp rotating iridescent rainbow neon border
        border_grad = self._make_border_conical(center, alpha=255)
        border_pen = QPen(QBrush(border_grad), 1.8)
        border_pen.setJoinStyle(Qt.RoundJoin)
        painter.setPen(border_pen)
        painter.setBrush(Qt.NoBrush)
        painter.drawPath(card_path)

        # Chrome-bright inner iridescent specular rim (adds liquid-neon shine)
        inner_rect = card_rect.adjusted(1.3, 1.3, -1.3, -1.3)
        inner_path = QPainterPath()
        inner_path.addRoundedRect(inner_rect, max(2.0, CORNER_RADIUS - 1.3), max(2.0, CORNER_RADIUS - 1.3))
        shine_conical = QConicalGradient(center, ((self._phase * 1.5 + 0.18) % 1.0) * 360.0)
        shine_conical.setColorAt(0.00, QColor(255, 255, 255, 165))
        shine_conical.setColorAt(0.10, QColor(186, 230, 253, 85))
        shine_conical.setColorAt(0.28, QColor(192, 132, 252, 34))
        shine_conical.setColorAt(0.50, QColor(255, 255, 255, 155))
        shine_conical.setColorAt(0.62, QColor(244, 114, 182, 72))
        shine_conical.setColorAt(0.82, QColor(52, 211, 153, 38))
        shine_conical.setColorAt(1.00, QColor(255, 255, 255, 165))
        painter.setPen(QPen(QBrush(shine_conical), 0.9))
        painter.drawPath(inner_path)

        # Orbiting starlight border glints along top & bottom neon edges
        glint_top_x = card_rect.left() + CORNER_RADIUS + (card_rect.width() - 2 * CORNER_RADIUS) * ((self._phase * 1.2) % 1.0)
        glint_bot_x = card_rect.right() - CORNER_RADIUS - (card_rect.width() - 2 * CORNER_RADIUS) * ((self._phase * 1.2 + 0.35) % 1.0)
        for gx, gy, tint in (
            (glint_top_x, card_rect.top() + 0.4, QColor(125, 249, 255, 175)),
            (glint_bot_x, card_rect.bottom() - 0.4, QColor(244, 114, 182, 165)),
        ):
            glint = QRadialGradient(QPointF(gx, gy), 11.0)
            glint.setColorAt(0.0, QColor(255, 255, 255, 235))
            glint.setColorAt(0.32, tint)
            glint.setColorAt(1.0, QColor(255, 255, 255, 0))
            painter.setPen(Qt.NoPen)
            painter.setBrush(QBrush(glint))
            painter.drawEllipse(QPointF(gx, gy), 11.0, 4.2)

        # 4. Crisp dark contrast drop shadow + dynamic flowing rainbow text
        painter.setPen(QColor(3, 2, 12, 225))
        for layout, offset in self._lines:
            layout.draw(
                painter,
                QPointF(
                    self._text_rect.left() + offset.x() + 1.0,
                    self._text_rect.top() + offset.y() + 1.4,
                ),
            )

        rainbow_img = self._render_rainbow_text_image(self._text_rect)
        painter.drawImage(
            QPointF(self._text_rect.left() - 1.0, self._text_rect.top() - 1.0),
            rainbow_img,
        )

        painter.end()


class AuroraToolTipManager(QObject):
    """Application-wide event filter intercepting ``QEvent.ToolTip`` across all widgets."""

    def __init__(self, app: QApplication):
        super().__init__(app)
        self._app = app
        self._widget = AuroraToolTipWidget()
        self._owner: Optional[QWidget] = None
        self._owner_window: Optional[QWidget] = None
        self._active_tab_index: Optional[int] = None
        self._active_model_index: Optional[QPersistentModelIndex] = None
        self._sticky: bool = False
        self._showing: bool = False
        app.installEventFilter(self)

    @property
    def tooltip_widget(self) -> AuroraToolTipWidget:
        return self._widget

    @property
    def active_owner(self) -> Optional[QWidget]:
        return self._owner

    def _clear_owner(self) -> None:
        self._owner = None
        self._owner_window = None
        self._active_tab_index = None
        self._active_model_index = None
        self._sticky = False

    def show_manual(
        self,
        global_pos: QPoint,
        text: str,
        owner: Optional[QWidget] = None,
        *,
        sticky: bool = False,
    ) -> bool:
        """Displays the Aurora tooltip programmatically (e.g. live image drag-resize)."""
        QToolTip.hideText()
        self._owner = owner
        self._owner_window = owner.window() if owner is not None else None
        self._active_tab_index = None
        self._active_model_index = None
        self._sticky = sticky
        self._showing = True
        try:
            shown = self._widget.show_tooltip(global_pos, text)
        finally:
            self._showing = False
        if not shown:
            self._clear_owner()
        return shown

    def hide(self, immediate: bool = False) -> None:
        """Hides the active Aurora tooltip smoothly (or immediately)."""
        self._clear_owner()
        try:
            self._widget.hide_tooltip(immediate=immediate)
        except RuntimeError:
            pass

    def _resolve_tooltip(
        self,
        watched: QWidget,
        local_pos: QPoint,
    ) -> tuple[str, Optional[int], Optional[QModelIndex]]:
        """Resolves hover tooltip text across standard widgets, tabs, item views, menus, and viewports."""
        # Skip our own tooltip window or non-interactive floating tooltip overlays
        if watched is self._widget or watched.windowType() == Qt.ToolTip:
            return "", None, None

        # Match Qt: disabled widgets suppress tooltips unless WA_AlwaysShowToolTips is set
        if not watched.isEnabled() and not watched.testAttribute(Qt.WA_AlwaysShowToolTips):
            return "", None, None

        # 1. QTabBar per-tab tooltip (TechPadTabBar)
        if isinstance(watched, QTabBar):
            idx = watched.tabAt(local_pos)
            if idx >= 0:
                tip = watched.tabToolTip(idx)
                if tip:
                    return tip, idx, None
            return watched.toolTip(), idx if idx >= 0 else None, None

        # 2. QAbstractItemView viewport (QListWidget / QTreeWidget / QTableWidget)
        parent = watched.parentWidget()
        if isinstance(parent, QAbstractItemView) and watched is parent.viewport():
            if not parent.isEnabled() and not parent.testAttribute(Qt.WA_AlwaysShowToolTips):
                return "", None, None
            index = parent.indexAt(local_pos)
            if index.isValid():
                data = index.data(Qt.ToolTipRole)
                if isinstance(data, str) and data:
                    return data, None, index
            tip = watched.toolTip() or parent.toolTip()
            return tip, None, index if index.isValid() else None

        # 3. QMenu action tooltip
        if isinstance(watched, QMenu):
            if watched.toolTipsVisible():
                action = watched.actionAt(local_pos)
                if action is not None:
                    tip = action.toolTip()
                    plain_label = action.text().replace("&", "")
                    if tip and tip != plain_label:
                        return tip, None, None
            return watched.toolTip(), None, None

        # 4. QToolButton (explicit tooltip or defaultAction tooltip)
        if isinstance(watched, QToolButton):
            tip = watched.toolTip()
            if not tip and watched.defaultAction() is not None:
                tip = watched.defaultAction().toolTip()
            return tip, None, None

        # 5. QAbstractScrollArea viewport (e.g. TechPadEditor.viewport() -> TechPadEditor.toolTip())
        if isinstance(parent, QAbstractScrollArea) and watched is parent.viewport():
            tip = watched.toolTip()
            if not tip and (parent.isEnabled() or parent.testAttribute(Qt.WA_AlwaysShowToolTips)):
                tip = parent.toolTip()
            return tip, None, None

        # 6. Standard QWidget (QPushButton, QLabel, QLineEdit, QSlider, QSpinBox, etc.)
        return watched.toolTip(), None, None

    def _is_owner_related(self, obj: QObject) -> bool:
        if self._owner is None:
            return False
        try:
            if obj is self._owner or obj is self._owner_window:
                return True
            parent = self._owner.parentWidget()
            if parent is not None and obj is parent:
                return True
        except RuntimeError:
            self._clear_owner()
        return False

    def eventFilter(self, watched: QObject, event: QEvent) -> bool:
        if watched is self._widget or self._showing:
            return False

        ev_type = event.type()

        # Primary interception: custom Aurora tooltip on hover
        if ev_type == QEvent.ToolTip and isinstance(watched, QWidget) and isinstance(event, QHelpEvent):
            text, tab_idx, model_idx = self._resolve_tooltip(watched, event.pos())
            if text:
                QToolTip.hideText()
                self._owner = watched
                self._owner_window = watched.window()
                self._active_tab_index = tab_idx
                self._active_model_index = (
                    QPersistentModelIndex(model_idx)
                    if model_idx is not None and model_idx.isValid()
                    else None
                )
                self._sticky = False
                self._showing = True
                try:
                    self._widget.show_tooltip(event.globalPos(), text)
                finally:
                    self._showing = False
                event.accept()
                return True

            # Empty tooltip on the active owner dismisses the visible Aurora tooltip
            if self._widget.isVisible() and not self._sticky and self._is_owner_related(watched):
                self.hide()
            return False

        # Nothing further to do when tooltip is completely hidden
        try:
            visible = self._widget.isVisible()
        except RuntimeError:
            return False
        if not visible:
            return False

        # Track sub-item / dynamic tooltip changes during MouseMove on the active owner
        if ev_type == QEvent.MouseMove and isinstance(watched, QWidget) and self._owner is watched:
            if self._sticky:
                return False
            if isinstance(watched, QTabBar):
                idx = watched.tabAt(event.position().toPoint() if hasattr(event, "position") else event.pos())
                if idx != self._active_tab_index:
                    self.hide()
            else:
                parent = watched.parentWidget()
                if isinstance(parent, QAbstractItemView) and watched is parent.viewport():
                    pos = event.position().toPoint() if hasattr(event, "position") else event.pos()
                    cur_idx = parent.indexAt(pos)
                    prev_idx = self._active_model_index
                    if prev_idx is not None and (not prev_idx.isValid() or cur_idx != QModelIndex(prev_idx)):
                        self.hide()
                elif isinstance(parent, QAbstractScrollArea) and watched is parent.viewport():
                    if not watched.toolTip() and not parent.toolTip():
                        self.hide()
                else:
                    if not watched.toolTip():
                        self.hide()
            return False

        # Dismissal triggers
        if ev_type == QEvent.Leave:
            if not self._sticky and self._is_owner_related(watched):
                self.hide()
        elif ev_type in (QEvent.MouseButtonPress, QEvent.MouseButtonDblClick, QEvent.Wheel):
            if not self._sticky:
                self.hide()
        elif ev_type == QEvent.MouseButtonRelease:
            if self._sticky:
                self.hide()
        elif ev_type == QEvent.KeyPress:
            self.hide()
        elif ev_type == QEvent.WindowDeactivate:
            if watched is self._owner_window:
                self.hide(immediate=True)
        elif ev_type == QEvent.ApplicationDeactivate:
            self.hide(immediate=True)
        elif ev_type in (QEvent.Hide, QEvent.Close, QEvent.Destroy):
            if self._is_owner_related(watched):
                self.hide(immediate=True)

        return False


def install_aurora_tooltips(app: Optional[QApplication] = None) -> Optional[AuroraToolTipManager]:
    """Idempotently installs the global Neon Aurora tooltip manager on ``QApplication``."""
    target_app = app or QApplication.instance()
    if target_app is None:
        return None
    existing = getattr(target_app, "_aurora_tooltip_manager", None)
    if isinstance(existing, AuroraToolTipManager):
        try:
            _ = existing.tooltip_widget.objectName()
            return existing
        except RuntimeError:
            pass
    manager = AuroraToolTipManager(target_app)
    target_app._aurora_tooltip_manager = manager
    return manager


def get_aurora_tooltip_manager(app: Optional[QApplication] = None) -> Optional[AuroraToolTipManager]:
    """Returns the installed ``AuroraToolTipManager``, or ``None`` if not yet installed."""
    target_app = app or QApplication.instance()
    if target_app is None:
        return None
    mgr = getattr(target_app, "_aurora_tooltip_manager", None)
    return mgr if isinstance(mgr, AuroraToolTipManager) else None


def show_aurora_tooltip(
    global_pos: QPoint,
    text: str,
    owner: Optional[QWidget] = None,
    *,
    sticky: bool = False,
) -> bool:
    """Programmatically shows the global Aurora tooltip (falling back to installing if needed)."""
    mgr = install_aurora_tooltips()
    if mgr is None:
        return False
    return mgr.show_manual(global_pos, text, owner=owner, sticky=sticky)


def hide_aurora_tooltip(immediate: bool = False) -> None:
    """Programmatically hides the global Aurora tooltip if active."""
    mgr = get_aurora_tooltip_manager()
    if mgr is not None:
        mgr.hide(immediate=immediate)
