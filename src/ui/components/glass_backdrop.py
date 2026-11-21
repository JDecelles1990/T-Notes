"""Dynamic slow full-spectrum rainbow gradient backdrop and interactive mouse-hover glass effect.

Provides a lightweight architectural visual layer for ``TechPadMainWindow``:

* **Slow Smooth Rainbow Gradient Backdrop:** Continuously and slowly cycles
  through the full 360° rainbow spectrum in deep jewel dark tones and radiant
  aurora nebula light pools rendered into a compact ``96x54`` offscreen buffer
  and smoothly upscaled behind translucent glass panels (~30s per full cycle,
  throttled to ~10 Hz backdrop refreshes for minimal GPU/CPU overhead).
* **Zero-Lag Interactive Mouse-Hover Glass Effect:** A mouse-transparent overlay
  (``AuroraGlassOverlay`` with ``Qt.WA_TransparentForMouseEvents``) using
  dirty-rectangle repaints and exact live viewport-clipped panel bounds so
  moving the mouse or scrolling produces zero lagging wireframe borders.
* **Zero Idle CPU:** Animation ticks only while the target window is visible
  and not minimized, stopping immediately when hidden or minimized to tray.
"""

from __future__ import annotations

import math
from typing import Optional

from PySide6.QtCore import QEvent, QObject, QPoint, QPointF, QRect, QRectF, QTimer, Qt
from PySide6.QtGui import (
    QBrush,
    QColor,
    QImage,
    QLinearGradient,
    QPainter,
    QPainterPath,
    QPen,
    QRadialGradient,
)
from PySide6.QtWidgets import (
    QApplication,
    QDockWidget,
    QGroupBox,
    QListWidget,
    QPlainTextEdit,
    QStatusBar,
    QTabWidget,
    QTextEdit,
    QToolBar,
    QWidget,
)

# Deep, low-glare dark-mode jewel stops spanning the full rainbow wheel.
DARK_RAINBOW_BACKDROP_PALETTE: tuple[str, ...] = (
    "#190a14",  # Deep Ruby Obsidian
    "#1c0e0e",  # Dark Crimson Ember
    "#1a1409",  # Dark Amber Bronze
    "#0f1a0c",  # Deep Moss Emerald
    "#071c18",  # Deep Peacock Teal
    "#071926",  # Abyssal Cyan
    "#09162e",  # Midnight Sapphire
    "#111030",  # Cosmic Indigo
    "#190e2e",  # Royal Amethyst
    "#1e0c21",  # Dark Magenta Plum
)

# Radiant 12-stop full-spectrum rainbow palette for smooth aurora light pools & rims.
RAINBOW_LIGHT_PALETTE: tuple[str, ...] = (
    "#f43f5e",  # Rose Crimson
    "#fb7185",  # Coral Pink
    "#fb923c",  # Warm Sunset Amber
    "#facc15",  # Solar Gold
    "#a3e635",  # Electric Lime
    "#34d399",  # Mint Emerald
    "#22d3ee",  # Prism Cyan
    "#38bdf8",  # Electric Sky Blue
    "#60a5fa",  # Celestial Azure
    "#818cf8",  # Periwinkle Indigo
    "#c084fc",  # Orchid Violet
    "#ec4899",  # Luminous Magenta
)

# Compatibility aliases
DARK_AURORA_PALETTE = DARK_RAINBOW_BACKDROP_PALETTE
GLASS_ACCENT_PALETTE = RAINBOW_LIGHT_PALETTE

BACKDROP_INTERVAL_MS: int = 33
BACKDROP_PHASE_STEP: float = 0.0011  # ~30s per full 360° rainbow cycle
BACKDROP_REDRAW_STRIDE: int = 3  # ~100 ms / 10 Hz full-backdrop refresh (~300 cycle steps)
BACKDROP_CACHE_W: int = 96
BACKDROP_CACHE_H: int = 54
SPOTLIGHT_RADIUS: float = 230.0
SPOTLIGHT_SMOOTHING: float = 1.0  # Direct 1:1 tracking with zero cursor lag
HOVER_EASE_IN: float = 0.35
HOVER_EASE_OUT: float = 0.16

_PANEL_TYPES = (
    QGroupBox,
    QListWidget,
    QTextEdit,
    QPlainTextEdit,
    QTabWidget,
    QDockWidget,
    QToolBar,
    QStatusBar,
)


def _interpolate_rainbow_hsv(palette: tuple[str, ...], pos_norm: float, alpha: int = 255) -> QColor:
    """Smoothly interpolates color around a cyclic palette in HSV space without banding."""
    n = len(palette)
    if n == 0:
        return QColor(11, 16, 27, alpha)
    pos = (pos_norm % 1.0) * n
    idx = int(pos) % n
    frac = pos - int(pos)
    c1 = QColor(palette[idx])
    c2 = QColor(palette[(idx + 1) % n])

    h1, s1, v1, _ = c1.getHsvF()
    h2, s2, v2, _ = c2.getHsvF()
    h1 = max(0.0, h1)
    h2 = max(0.0, h2)
    dh = h2 - h1
    if dh > 0.5:
        dh -= 1.0
    elif dh < -0.5:
        dh += 1.0
    hue = (h1 + dh * frac) % 1.0
    sat = s1 + (s2 - s1) * frac
    val = v1 + (v2 - v1) * frac
    color = QColor.fromHsvF(hue, min(1.0, max(0.0, sat)), min(1.0, max(0.0, val)))
    color.setAlpha(alpha)
    return color


class AuroraGlassOverlay(QWidget):
    """Non-intrusive translucent overlay painting rainbow glass light & hover highlights."""

    def __init__(self, controller: "AuroraGlassBackdrop", parent: QWidget) -> None:
        super().__init__(parent)
        self._controller = controller
        self.setObjectName("auroraGlassOverlay")
        self.setAttribute(Qt.WA_TransparentForMouseEvents, True)
        self.setAttribute(Qt.WA_NoSystemBackground, True)
        self.setAttribute(Qt.WA_TranslucentBackground, True)
        self.setFocusPolicy(Qt.NoFocus)

    def paintEvent(self, event) -> None:  # noqa: N802 (Qt API)
        if not self.isVisible() or self.width() <= 0 or self.height() <= 0:
            return
        painter = QPainter(self)
        painter.setClipRect(event.rect())
        painter.setRenderHint(QPainter.Antialiasing, True)
        self._controller.paint_glass_overlay(painter, self.rect())
        painter.end()


class AuroraGlassBackdrop(QObject):
    """Manages slow rainbow gradient backdrop and interactive mouse-hover glass refraction."""

    def __init__(self, window: QWidget) -> None:
        super().__init__(window)
        self._window = window
        self._phase: float = 0.0
        self._hover_level: float = 0.0
        self._hovered: bool = False
        self._tick_count: int = 0
        self._target_pos: QPointF = QPointF(window.width() * 0.5, window.height() * 0.4)
        self._spotlight_pos: QPointF = QPointF(self._target_pos)
        self._last_painted_spotlight: Optional[QPointF] = None
        self._hovered_panel: Optional[QWidget] = None
        self._last_painted_panel_rect: Optional[QRect] = None

        self._backdrop_cache = QImage(BACKDROP_CACHE_W, BACKDROP_CACHE_H, QImage.Format_ARGB32_Premultiplied)
        self._backdrop_dirty: bool = True

        self._overlay = AuroraGlassOverlay(self, window)
        self._overlay.setGeometry(window.rect())
        self._overlay.show()
        self._overlay.raise_()

        self._timer = QTimer(self)
        self._timer.setInterval(BACKDROP_INTERVAL_MS)
        self._timer.timeout.connect(self._on_tick)

        window.installEventFilter(self)
        if app := QApplication.instance():
            app.installEventFilter(self)
        self.destroyed.connect(self._cleanup_filters)

        if self._should_animate():
            self._timer.start()

    # -- Public properties & helpers ------------------------------------------

    @property
    def phase(self) -> float:
        return self._phase

    @property
    def hover_level(self) -> float:
        return self._hover_level

    @property
    def spotlight_pos(self) -> QPointF:
        return QPointF(self._spotlight_pos)

    @property
    def hovered_panel_rect(self) -> Optional[QRectF]:
        return self._compute_live_panel_rect(self._hovered_panel)

    @property
    def overlay(self) -> AuroraGlassOverlay:
        return self._overlay

    @property
    def is_active(self) -> bool:
        return self._timer.isActive()

    def sample_backdrop_color(self, offset: float = 0.0, alpha: int = 255) -> QColor:
        """Returns the current HSV-interpolated dark rainbow backdrop color."""
        return _interpolate_rainbow_hsv(DARK_RAINBOW_BACKDROP_PALETTE, self._phase + offset, alpha=alpha)

    def sample_accent_color(self, offset: float = 0.0, alpha: int = 255) -> QColor:
        """Returns the current HSV-interpolated rainbow light color at normalized offset."""
        return _interpolate_rainbow_hsv(RAINBOW_LIGHT_PALETTE, self._phase + offset, alpha=alpha)

    def set_cursor_pos(self, local_pos: QPointF, hovered: bool = True) -> None:
        """Updates spotlight position immediately (used by pointer events and tests)."""
        old_pos = QPointF(self._spotlight_pos) if self._hover_level > 0.01 else None
        self._target_pos = QPointF(local_pos)
        self._spotlight_pos = QPointF(local_pos)
        self._hovered = bool(hovered)
        if self._hovered:
            self._hover_level = max(self._hover_level, 0.90)
            self._update_hovered_panel_at(local_pos)
        else:
            self._hover_level = 0.0
            self._hovered_panel = None
        self._update_overlay_region(old_pos, self._spotlight_pos if self._hovered else None)

    def step_animation(self, steps: int = 1) -> None:
        """Advances the rainbow cycle deterministically for smooth frame progression."""
        for _ in range(max(1, int(steps))):
            self._advance_state()
        self._backdrop_dirty = True
        self._request_full_repaint()

    # -- Lifecycle & Event Filtering ------------------------------------------

    def _cleanup_filters(self) -> None:
        self._timer.stop()
        if app := QApplication.instance():
            try:
                app.removeEventFilter(self)
            except RuntimeError:
                pass

    def _should_animate(self) -> bool:
        try:
            return bool(self._window.isVisible() and not self._window.isMinimized())
        except RuntimeError:
            return False

    def _sync_timer_state(self) -> None:
        if self._should_animate():
            if not self._timer.isActive():
                self._timer.start()
        else:
            if self._timer.isActive():
                self._timer.stop()

    def _sync_overlay_geometry(self) -> None:
        try:
            self._overlay.setGeometry(self._window.rect())
            self._overlay.raise_()
        except RuntimeError:
            pass

    def _advance_state(self) -> bool:
        """Advances rainbow phase and hover easing; returns True if hover level changed."""
        self._phase = (self._phase + BACKDROP_PHASE_STEP) % 1.0
        prev_level = self._hover_level
        target_hover = 1.0 if self._hovered else 0.0
        rate = HOVER_EASE_IN if target_hover > self._hover_level else HOVER_EASE_OUT
        self._hover_level += (target_hover - self._hover_level) * rate
        if abs(target_hover - self._hover_level) < 0.01:
            self._hover_level = target_hover

        dx = self._target_pos.x() - self._spotlight_pos.x()
        dy = self._target_pos.y() - self._spotlight_pos.y()
        self._spotlight_pos = QPointF(
            self._spotlight_pos.x() + dx * SPOTLIGHT_SMOOTHING,
            self._spotlight_pos.y() + dy * SPOTLIGHT_SMOOTHING,
        )
        return abs(self._hover_level - prev_level) > 0.002

    def _spotlight_dirty_rect(self, center: QPointF) -> QRect:
        pad = int(SPOTLIGHT_RADIUS + 20)
        return QRect(
            int(center.x()) - pad,
            int(center.y()) - pad,
            pad * 2,
            pad * 2,
        ).intersected(self._overlay.rect())

    def _update_overlay_region(self, old_pos: Optional[QPointF], new_pos: Optional[QPointF]) -> None:
        try:
            dirty = QRect()
            if old_pos is not None:
                dirty = dirty.united(self._spotlight_dirty_rect(old_pos))
            if new_pos is not None:
                dirty = dirty.united(self._spotlight_dirty_rect(new_pos))
            if self._last_painted_panel_rect is not None:
                dirty = dirty.united(self._last_painted_panel_rect.adjusted(-4, -4, 4, 4))
            live_panel_rect = self._compute_live_panel_rect(self._hovered_panel)
            if live_panel_rect is not None:
                dirty = dirty.united(live_panel_rect.toAlignedRect().adjusted(-4, -4, 4, 4))
            dirty = dirty.intersected(self._overlay.rect())
            if not dirty.isEmpty():
                self._overlay.update(dirty)
        except RuntimeError:
            self._timer.stop()

    def _request_full_repaint(self) -> None:
        try:
            self._window.update()
            self._overlay.update()
        except RuntimeError:
            self._timer.stop()

    def _on_tick(self) -> None:
        if not self._should_animate():
            self._timer.stop()
            return
        if self._hovered:
            self._update_hovered_panel_at(self._spotlight_pos)
        hover_changed = self._advance_state()
        self._tick_count = (self._tick_count + 1) % BACKDROP_REDRAW_STRIDE

        if self._tick_count == 0:
            self._backdrop_dirty = True
            self._request_full_repaint()
        elif hover_changed:
            pos = self._spotlight_pos
            self._update_overlay_region(self._last_painted_spotlight or pos, pos)

    def _compute_live_panel_rect(self, panel: Optional[QWidget]) -> Optional[QRectF]:
        """Computes *panel*'s exact current rectangle clipped to all visible ancestor viewports."""
        if panel is None:
            return None
        try:
            if not panel.isVisible() or panel.window() is not self._window:
                return None
            top_left = panel.mapTo(self._window, QPoint(0, 0))
            rect = QRectF(top_left.x(), top_left.y(), panel.width(), panel.height())
            if isinstance(panel, QGroupBox):
                # dark_theme.qss sets margin-top: 12px on QGroupBox
                rect.adjust(0.0, 12.0, 0.0, 0.0)

            curr = panel.parentWidget()
            while curr is not None and curr is not self._window:
                if not curr.isVisible():
                    return None
                anc_tl = curr.mapTo(self._window, QPoint(0, 0))
                anc_rect = QRectF(anc_tl.x(), anc_tl.y(), curr.width(), curr.height())
                rect = rect.intersected(anc_rect)
                if rect.isEmpty():
                    return None
                curr = curr.parentWidget()

            rect = rect.intersected(QRectF(self._window.rect()))
            return rect if rect.width() > 4.0 and rect.height() > 4.0 else None
        except RuntimeError:
            return None

    def _update_hovered_panel_at(self, local_pos: QPointF) -> None:
        """Resolves the nearest glass container panel under *local_pos* in window coordinates."""
        try:
            hit = self._window.childAt(QPoint(int(local_pos.x()), int(local_pos.y())))
        except RuntimeError:
            self._hovered_panel = None
            return

        panel: Optional[QWidget] = None
        curr = hit
        while curr is not None and curr is not self._window:
            if isinstance(curr, _PANEL_TYPES) and curr.isVisible():
                panel = curr
                break
            curr = curr.parentWidget()

        self._hovered_panel = panel

    def eventFilter(self, watched: QObject, event: QEvent) -> bool:  # noqa: N802 (Qt API)
        etype = event.type()
        if watched is self._window:
            if etype in (QEvent.Resize, QEvent.LayoutRequest):
                self._sync_overlay_geometry()
            elif etype == QEvent.Show:
                self._sync_overlay_geometry()
                self._backdrop_dirty = True
                self._sync_timer_state()
            elif etype in (QEvent.Hide, QEvent.Close):
                self._hovered = False
                self._hovered_panel = None
                self._timer.stop()
            elif etype == QEvent.WindowStateChange:
                self._sync_timer_state()
            elif etype == QEvent.Leave:
                old_pos = QPointF(self._spotlight_pos)
                self._hovered = False
                self._hovered_panel = None
                self._update_overlay_region(old_pos, None)
            return False

        if etype in (QEvent.MouseMove, QEvent.HoverMove, QEvent.Wheel):
            if self._should_animate() and isinstance(watched, QWidget):
                try:
                    if watched.window() is self._window:
                        global_pos = (
                            event.globalPosition().toPoint()
                            if hasattr(event, "globalPosition")
                            else watched.mapToGlobal(event.position().toPoint())
                        )
                        local = QPointF(self._window.mapFromGlobal(global_pos))
                        old_pos = QPointF(self._spotlight_pos) if self._hover_level > 0.01 else None
                        self._target_pos = local
                        self._spotlight_pos = local
                        if not self._hovered:
                            self._hovered = True
                            self._hover_level = max(self._hover_level, 0.35)
                        self._update_hovered_panel_at(local)
                        self._update_overlay_region(old_pos, local)
                except (RuntimeError, AttributeError):
                    pass
        return False

    # -- Custom Painting -------------------------------------------------------

    def _rebuild_backdrop_cache(self) -> None:
        """Renders the rainbow backdrop into a compact 96x54 offscreen image (400x less GPU fill)."""
        w = float(BACKDROP_CACHE_W)
        h = float(BACKDROP_CACHE_H)
        self._backdrop_cache.fill(Qt.transparent)
        p = QPainter(self._backdrop_cache)
        p.setRenderHint(QPainter.Antialiasing, True)

        angle = self._phase * math.tau
        dx = math.cos(angle) * 0.25
        dy = math.sin(angle) * 0.25
        base_grad = QLinearGradient(
            QPointF(w * (0.15 + dx), h * (0.0 + dy)),
            QPointF(w * (0.85 - dx), h * (1.0 - dy)),
        )
        base_grad.setColorAt(0.00, self.sample_backdrop_color(0.00))
        base_grad.setColorAt(0.35, self.sample_backdrop_color(0.18))
        base_grad.setColorAt(0.70, self.sample_backdrop_color(0.36))
        base_grad.setColorAt(1.00, self.sample_backdrop_color(0.54))
        p.fillRect(0, 0, BACKDROP_CACHE_W, BACKDROP_CACHE_H, QBrush(base_grad))

        blobs = (
            (0.22 + 0.16 * math.sin(angle), 0.22 + 0.14 * math.cos(angle * 0.9), max(w, h) * 0.62, 0.00, 82),
            (0.80 + 0.14 * math.cos(angle * 0.8), 0.34 + 0.16 * math.sin(angle * 1.1), max(w, h) * 0.56, 0.33, 72),
            (0.46 + 0.20 * math.sin(angle * 1.2 + 1.4), 0.84 + 0.10 * math.cos(angle), max(w, h) * 0.64, 0.67, 64),
        )
        for cx_frac, cy_frac, radius, hue_off, peak_alpha in blobs:
            center = QPointF(w * cx_frac, h * cy_frac)
            glow = QRadialGradient(center, radius)
            glow.setColorAt(0.0, self.sample_accent_color(hue_off, alpha=peak_alpha))
            glow.setColorAt(0.50, self.sample_accent_color(hue_off + 0.10, alpha=int(peak_alpha * 0.42)))
            glow.setColorAt(1.0, QColor(0, 0, 0, 0))
            p.fillRect(0, 0, BACKDROP_CACHE_W, BACKDROP_CACHE_H, QBrush(glow))

        p.end()
        self._backdrop_dirty = False

    def paint_backdrop(self, painter: QPainter, rect: QRect) -> None:
        """Draws the cached smooth rainbow gradient backdrop upscaled cleanly to *rect*."""
        if rect.width() <= 0 or rect.height() <= 0:
            return
        if self._backdrop_dirty:
            self._rebuild_backdrop_cache()

        painter.save()
        painter.setRenderHint(QPainter.SmoothPixmapTransform, True)
        painter.drawImage(rect, self._backdrop_cache)
        painter.restore()

    def paint_glass_overlay(self, painter: QPainter, rect: QRect) -> None:
        """Paints slow rainbow ambient glass sheen and zero-lag cursor-tracking spotlight."""
        w = float(rect.width())
        h = float(rect.height())
        if w <= 0.0 or h <= 0.0:
            return

        painter.save()

        # 1. Slow rainbow-shifting full-window translucent glass ambient wash
        ambient = QLinearGradient(QPointF(0.0, 0.0), QPointF(w, h))
        ambient.setColorAt(0.00, self.sample_accent_color(0.00, alpha=16))
        ambient.setColorAt(0.35, self.sample_accent_color(0.22, alpha=12))
        ambient.setColorAt(0.70, self.sample_accent_color(0.45, alpha=14))
        ambient.setColorAt(1.00, self.sample_accent_color(0.68, alpha=18))
        painter.fillRect(rect, QBrush(ambient))

        # 2. Zero-lag interactive cursor-following frosted rainbow spotlight (no drifting borders)
        if self._hover_level > 0.01:
            self._last_painted_spotlight = QPointF(self._spotlight_pos)
            lens = QRadialGradient(self._spotlight_pos, SPOTLIGHT_RADIUS)
            lens.setColorAt(0.0, self.sample_accent_color(0.08, alpha=int(34 * self._hover_level)))
            lens.setColorAt(0.42, self.sample_accent_color(0.26, alpha=int(18 * self._hover_level)))
            lens.setColorAt(0.80, self.sample_accent_color(0.48, alpha=int(6 * self._hover_level)))
            lens.setColorAt(1.0, QColor(255, 255, 255, 0))
            painter.fillRect(rect, QBrush(lens))

            # Colorful rainbow radial border rim + top specular edge clipped cleanly to visible box bounds
            panel_rect = self._compute_live_panel_rect(self._hovered_panel)
            if panel_rect is not None:
                self._last_painted_panel_rect = panel_rect.toAlignedRect()
                painter.save()
                painter.setClipRect(panel_rect)

                inner_glow = QRadialGradient(self._spotlight_pos, 180.0)
                inner_glow.setColorAt(0.0, self.sample_accent_color(0.0, alpha=int(22 * self._hover_level)))
                inner_glow.setColorAt(0.65, self.sample_accent_color(0.18, alpha=int(9 * self._hover_level)))
                inner_glow.setColorAt(1.0, QColor(255, 255, 255, 0))
                painter.fillRect(panel_rect, QBrush(inner_glow))

                bordered = panel_rect.adjusted(0.75, 0.75, -0.75, -0.75)
                rim_grad = QRadialGradient(self._spotlight_pos, 240.0)
                rim_grad.setColorAt(0.0, self.sample_accent_color(0.0, alpha=int(190 * self._hover_level)))
                rim_grad.setColorAt(0.50, self.sample_accent_color(0.22, alpha=int(130 * self._hover_level)))
                rim_grad.setColorAt(1.0, self.sample_accent_color(0.44, alpha=int(45 * self._hover_level)))

                path = QPainterPath()
                path.addRoundedRect(bordered, 6.0, 6.0)
                painter.strokePath(path, QPen(QBrush(rim_grad), 1.5))

                top_highlight = QLinearGradient(
                    QPointF(bordered.left(), bordered.top()),
                    QPointF(bordered.right(), bordered.top()),
                )
                cx_norm = max(
                    0.0,
                    min(1.0, (self._spotlight_pos.x() - bordered.left()) / max(1.0, bordered.width())),
                )
                top_highlight.setColorAt(0.0, QColor(255, 255, 255, 0))
                if cx_norm > 0.08:
                    top_highlight.setColorAt(max(0.0, cx_norm - 0.18), QColor(255, 255, 255, 0))
                top_highlight.setColorAt(cx_norm, QColor(248, 250, 252, int(120 * self._hover_level)))
                if cx_norm < 0.92:
                    top_highlight.setColorAt(min(1.0, cx_norm + 0.18), QColor(255, 255, 255, 0))
                top_highlight.setColorAt(1.0, QColor(255, 255, 255, 0))
                painter.setPen(QPen(QBrush(top_highlight), 1.5))
                painter.drawLine(
                    QPointF(bordered.left() + 6.0, bordered.top()),
                    QPointF(bordered.right() - 6.0, bordered.top()),
                )
                painter.restore()
            else:
                self._last_painted_panel_rect = None
        else:
            self._last_painted_spotlight = None
            self._last_painted_panel_rect = None

        painter.restore()


def install_glass_backdrop(window: QWidget) -> AuroraGlassBackdrop:
    """Attaches (idempotently) the slow rainbow gradient backdrop and hover glass overlay."""
    existing = getattr(window, "_glass_backdrop", None)
    if existing is not None:
        return existing
    backdrop = AuroraGlassBackdrop(window)
    window._glass_backdrop = backdrop  # type: ignore[attr-defined]
    return backdrop
