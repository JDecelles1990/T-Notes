"""Modal dialog for resizing and annotating embedded images with drawing, shapes, text, zoom, move, and undo/redo."""

import math
from typing import Optional, Tuple
from PySide6.QtCore import QPoint, QPointF, QRect, QRectF, Qt, Signal
from PySide6.QtGui import (
    QBrush,
    QColor,
    QConicalGradient,
    QFont,
    QFontMetrics,
    QImage,
    QKeySequence,
    QLinearGradient,
    QMouseEvent,
    QPaintEvent,
    QPainter,
    QPainterPath,
    QPen,
    QRadialGradient,
    QShortcut,
)
from PySide6.QtWidgets import (
    QButtonGroup,
    QCheckBox,
    QColorDialog,
    QDialog,
    QDialogButtonBox,
    QFormLayout,
    QFrame,
    QHBoxLayout,
    QLabel,
    QPushButton,
    QSpinBox,
    QSplitter,
    QTextEdit,
    QToolButton,
    QVBoxLayout,
    QWidget,
)
from src.ui.components.glow_effect import apply_glow_to_buttons, apply_glow_to_inputs
from src.ui.components.panel_transition import animate_dialog_show
from src.ui.dialogs.image_editor_cyber_fx import (
    CYBER_RAINBOW_STOPS,
    CyberNeonClock,
    CyberNeonLine,
    CyberNeonSplitter,
    CyberRainbowBorderFrame,
    _paint_cyber_rainbow_frame,
    apply_cyber_click_shine,
    install_cyber_input_halos,
    sample_cyber_rainbow,
    style_cyber_button,
)


class DoubleClickableFrame(QFrame):
    """Cyber-neon toolbar frame emitting double_clicked on empty-area double-clicks."""

    double_clicked = Signal()

    def __init__(
        self,
        parent: Optional[QWidget] = None,
        cyber_clock: Optional[CyberNeonClock] = None,
    ) -> None:
        super().__init__(parent)
        self._cyber_clock = cyber_clock
        if self._cyber_clock is not None:
            self._cyber_clock.tick.connect(self._on_neon_tick)

    def _on_neon_tick(self, _phase: float) -> None:
        try:
            if self.isVisible():
                self.update()
        except RuntimeError:
            pass

    def paintEvent(self, event: QPaintEvent) -> None:
        if self._cyber_clock is not None:
            _paint_cyber_rainbow_frame(
                self,
                self._cyber_clock.phase,
                radius=9.0,
                phase_offset=0.0,
                bg_top="#160c34",
                bg_bottom="#09061b",
                corner_ticks=True,
            )
            return
        super().paintEvent(event)

    def mouseDoubleClickEvent(self, event: QMouseEvent) -> None:
        if event.button() == Qt.LeftButton:
            self.double_clicked.emit()
            event.accept()
            return
        super().mouseDoubleClickEvent(event)


class TextAnnotationDialog(QDialog):
    """Cyber-neon dialog allowing technicians to write text, choose font size, and set border options."""

    def __init__(
        self,
        rect: QRect,
        font_size: int = 18,
        color: QColor = QColor("#ff3b30"),
        parent: Optional[QWidget] = None,
    ):
        super().__init__(parent)
        self.setWindowTitle("Add Text to Image")
        self.resize(420, 290)
        self.setModal(True)
        self._cyber_clock = CyberNeonClock(self)
        self._shown_once = False
        self._setup_ui(rect, font_size, color)

    def paintEvent(self, event: QPaintEvent) -> None:
        painter = QPainter(self)
        painter.setRenderHint(QPainter.Antialiasing, True)
        w, h = float(self.width()), float(self.height())
        bg = QLinearGradient(0.0, 0.0, w, h)
        bg.setColorAt(0.0, QColor("#070417"))
        bg.setColorAt(0.5, QColor("#0d0826"))
        bg.setColorAt(1.0, QColor("#061329"))
        painter.fillRect(self.rect(), QBrush(bg))

        # Subtle neon ambient corner glow
        glow_tl = QRadialGradient(QPointF(0.0, 0.0), max(w, h) * 0.6)
        glow_tl.setColorAt(0.0, QColor(255, 0, 127, 45))
        glow_tl.setColorAt(1.0, QColor(255, 0, 127, 0))
        painter.fillRect(self.rect(), QBrush(glow_tl))

        glow_br = QRadialGradient(QPointF(w, h), max(w, h) * 0.6)
        glow_br.setColorAt(0.0, QColor(0, 240, 255, 45))
        glow_br.setColorAt(1.0, QColor(0, 240, 255, 0))
        painter.fillRect(self.rect(), QBrush(glow_br))
        painter.end()

    def showEvent(self, event) -> None:
        super().showEvent(event)
        if not self._shown_once:
            self._shown_once = True
            animate_dialog_show(self)

    def _setup_ui(self, rect: QRect, font_size: int, color: QColor) -> None:
        layout = QVBoxLayout(self)
        layout.setSpacing(10)
        layout.setContentsMargins(14, 14, 14, 14)

        hdr = QLabel("⚡ CYBER TEXT OVERLAY")
        hdr.setStyleSheet(
            "font-weight: 800; font-size: 10.5pt; letter-spacing: 1.2px; color: #00f0ff;"
        )
        layout.addWidget(hdr)

        info_lbl = QLabel(f"Text Box: <b>{rect.width()} × {rect.height()} px</b> at ({rect.x()}, {rect.y()})")
        info_lbl.setStyleSheet("color: #f472b6; font-size: 8.5pt; font-weight: 600;")
        layout.addWidget(info_lbl)

        layout.addWidget(CyberNeonLine(self._cyber_clock, Qt.Horizontal, thickness=2, phase_offset=0.1))

        self.text_edit = QTextEdit()
        self.text_edit.setPlaceholderText("Type text to place inside rectangle (multi-line supported)...")
        self.text_edit.setAcceptRichText(False)
        self.text_edit.setStyleSheet("""
            QTextEdit {
                background: qlineargradient(
                    x1: 0, y1: 0, x2: 1, y2: 1,
                    stop: 0 #2e0f66,
                    stop: 0.45 #0c2b59,
                    stop: 0.8 #3b0d5e,
                    stop: 1 #4a0b4a
                );
                color: #ffffff;
                border: 2px solid transparent;
                border-radius: 6px;
                padding: 8px;
                font-family: 'Segoe UI', Arial, sans-serif;
                font-size: 10.5pt;
                font-weight: 600;
                selection-background-color: #ff007f;
                selection-color: #ffffff;
            }
        """)
        layout.addWidget(self.text_edit, 1)

        opts_frame = CyberRainbowBorderFrame(self._cyber_clock, radius=8.0, phase_offset=0.45, corner_ticks=False)
        opts_row = QHBoxLayout(opts_frame)
        opts_row.setContentsMargins(10, 7, 10, 7)
        opts_row.setSpacing(10)

        lbl_size = QLabel("Font Size:")
        lbl_size.setStyleSheet("color: #00ff9d; font-weight: 700;")
        opts_row.addWidget(lbl_size)

        self.spin_size = QSpinBox()
        self.spin_size.setRange(8, 96)
        self.spin_size.setValue(font_size)
        self.spin_size.setSuffix(" pt")
        self.spin_size.setMinimumWidth(94)
        opts_row.addWidget(self.spin_size)

        self.chk_border = QCheckBox("🔲 Draw Callout Box")
        self.chk_border.setChecked(False)
        self.chk_border.setToolTip("Draw rounded border box and dark background behind text")
        self.chk_border.setStyleSheet("color: #e0f2fe; font-weight: 600;")
        opts_row.addWidget(self.chk_border)

        opts_row.addStretch()
        layout.addWidget(opts_frame)

        btn_box = QDialogButtonBox(QDialogButtonBox.Ok | QDialogButtonBox.Cancel)
        btn_box.accepted.connect(self.accept)
        btn_box.rejected.connect(self.reject)
        ok_btn = btn_box.button(QDialogButtonBox.Ok)
        cancel_btn = btn_box.button(QDialogButtonBox.Cancel)
        if ok_btn:
            style_cyber_button(ok_btn, "emerald", compact=False, radius=7)
        if cancel_btn:
            style_cyber_button(cancel_btn, "crimson", compact=False, radius=7)
        layout.addWidget(btn_box)

        self.setStyleSheet("""
            QDialog {
                background-color: #070417;
                color: #f1f5f9;
            }
            QLabel {
                color: #e2e8f0;
                background: transparent;
            }
            QSpinBox {
                background: qlineargradient(
                    x1: 0, y1: 0, x2: 1, y2: 1,
                    stop: 0 #31126b,
                    stop: 0.5 #0d2f5e,
                    stop: 1 #4f0e5c
                );
                color: #7df9ff;
                font-weight: 700;
                border: 2px solid transparent;
                border-radius: 6px;
                padding: 4px 8px;
            }
            QSpinBox::up-button, QSpinBox::down-button {
                background: qlineargradient(x1:0, y1:0, x2:0, y2:1, stop:0 #ff007f, stop:1 #4361ee);
                border: none;
                border-radius: 3px;
                width: 16px;
                margin: 1px;
            }
            QSpinBox::up-arrow, QSpinBox::down-arrow {
                image: none;
                width: 0px;
                height: 0px;
            }
            QCheckBox::indicator {
                width: 16px;
                height: 16px;
                border-radius: 4px;
                border: 1.5px solid #00f0ff;
                background: #120b2c;
            }
            QCheckBox::indicator:checked {
                background: qlineargradient(x1:0, y1:0, x2:1, y2:1, stop:0 #ff007f, stop:1 #00f0ff);
                border-color: #ffffff;
            }
        """)

        apply_glow_to_buttons([self])
        apply_glow_to_inputs([self])
        install_cyber_input_halos([self], self._cyber_clock)
        apply_cyber_click_shine([self])

    def get_text(self) -> str:
        return self.text_edit.toPlainText().strip()

    def get_font_size(self) -> int:
        return self.spin_size.value()

    def should_draw_border(self) -> bool:
        return self.chk_border.isChecked()


class AnnotationItem:
    """Represents a movable, rotatable, re-editable vector annotation object on the canvas."""

    TYPE_PEN = "pen"
    TYPE_LINE = "line"
    TYPE_CIRCLE = "circle"
    TYPE_RECTANGLE = "rectangle"
    TYPE_TEXT = "text"

    def __init__(
        self,
        item_type: str,
        color: QColor,
        stroke_width: int = 4,
        rect: Optional[QRect] = None,
        points: Optional[list[QPoint]] = None,
        text: str = "",
        font_size: int = 18,
        draw_border: bool = False,
        rotation: float = 0.0,
    ):
        self.item_type = item_type
        self.color = QColor(color)
        self.stroke_width = stroke_width
        self.rect = QRect(rect) if rect else QRect()
        self.points = [QPoint(p) for p in points] if points else []
        self.text = text
        self.font_size = font_size
        self.draw_border = draw_border
        self.rotation = float(rotation) % 360.0

    def clone(self) -> "AnnotationItem":
        return AnnotationItem(
            item_type=self.item_type,
            color=QColor(self.color),
            stroke_width=self.stroke_width,
            rect=QRect(self.rect) if self.rect.isValid() else None,
            points=[QPoint(p) for p in self.points],
            text=self.text,
            font_size=self.font_size,
            draw_border=self.draw_border,
            rotation=self.rotation,
        )

    def rotate(self, angle_degrees: float) -> None:
        """Rotates this item clockwise by angle_degrees."""
        self.rotation = (self.rotation + angle_degrees) % 360.0

    def get_bounding_rect(self) -> QRect:
        """Returns the bounding box of this shape or text box in image pixel coordinates."""
        if self.item_type in (self.TYPE_RECTANGLE, self.TYPE_CIRCLE, self.TYPE_TEXT):
            return self.rect.normalized()
        elif self.item_type in (self.TYPE_PEN, self.TYPE_LINE) and self.points:
            xs = [p.x() for p in self.points]
            ys = [p.y() for p in self.points]
            margin = max(6, self.stroke_width // 2 + 4)
            return QRect(
                min(xs) - margin,
                min(ys) - margin,
                max(xs) - min(xs) + margin * 2,
                max(ys) - min(ys) + margin * 2,
            ).normalized()
        return QRect()

    def contains_point(self, pt: QPoint) -> bool:
        """Hit test checking whether point pt intersects this item for selection."""
        b_rect = self.get_bounding_rect()
        if not b_rect.isValid():
            return False

        check_pt = pt
        if abs(self.rotation) > 0.001:
            center = b_rect.center()
            rad = math.radians(-self.rotation)
            cos_a = math.cos(rad)
            sin_a = math.sin(rad)
            dx = pt.x() - center.x()
            dy = pt.y() - center.y()
            check_pt = QPoint(
                int(round(center.x() + dx * cos_a - dy * sin_a)),
                int(round(center.y() + dx * sin_a + dy * cos_a)),
            )

        if not b_rect.adjusted(-8, -8, 8, 8).contains(check_pt):
            return False

        if self.item_type in (self.TYPE_RECTANGLE, self.TYPE_CIRCLE, self.TYPE_TEXT):
            return b_rect.adjusted(-4, -4, 4, 4).contains(check_pt)

        elif self.item_type in (self.TYPE_PEN, self.TYPE_LINE):
            margin = max(6, self.stroke_width + 4)
            for p in self.points:
                if (p.x() - check_pt.x()) ** 2 + (p.y() - check_pt.y()) ** 2 <= margin ** 2:
                    return True
            for i in range(len(self.points) - 1):
                p1 = self.points[i]
                p2 = self.points[i + 1]
                if self._dist_to_segment(check_pt, p1, p2) <= margin:
                    return True
            return False
        return False

    @staticmethod
    def _dist_to_segment(p: QPoint, p1: QPoint, p2: QPoint) -> float:
        l2 = (p1.x() - p2.x()) ** 2 + (p1.y() - p2.y()) ** 2
        if l2 == 0:
            return math.hypot(p.x() - p1.x(), p.y() - p1.y())
        t = max(0.0, min(1.0, ((p.x() - p1.x()) * (p2.x() - p1.x()) + (p.y() - p1.y()) * (p2.y() - p1.y())) / l2))
        proj_x = p1.x() + t * (p2.x() - p1.x())
        proj_y = p1.y() + t * (p2.y() - p1.y())
        return math.hypot(p.x() - proj_x, p.y() - proj_y)

    def translate(self, dx: int, dy: int) -> None:
        """Moves this item by (dx, dy) pixels."""
        if self.rect.isValid():
            self.rect.translate(dx, dy)
        if self.points:
            for p in self.points:
                p.setX(p.x() + dx)
                p.setY(p.y() + dy)

    def resize_to_bounding_rect(self, new_bounds: QRect, initial_item: "AnnotationItem") -> None:
        """Resizes this item (rect-based shape/text or point-based pen/line drawing) to fit new_bounds."""
        norm_bounds = new_bounds.normalized()
        if self.item_type in (self.TYPE_RECTANGLE, self.TYPE_CIRCLE, self.TYPE_TEXT):
            self.rect = QRect(norm_bounds)
        elif self.item_type in (self.TYPE_PEN, self.TYPE_LINE) and initial_item.points:
            margin = max(6, self.stroke_width // 2 + 4)
            init_xs = [p.x() for p in initial_item.points]
            init_ys = [p.y() for p in initial_item.points]
            min_x, max_x = min(init_xs), max(init_xs)
            min_y, max_y = min(init_ys), max(init_ys)
            old_span_x = max_x - min_x
            old_span_y = max_y - min_y

            target_left = norm_bounds.left() + margin
            target_top = norm_bounds.top() + margin
            target_span_x = max(2, norm_bounds.width() - 2 * margin)
            target_span_y = max(2, norm_bounds.height() - 2 * margin)

            new_points: list[QPoint] = []
            for p in initial_item.points:
                if old_span_x > 0:
                    nx = int(round(target_left + (p.x() - min_x) * (target_span_x / old_span_x)))
                else:
                    nx = norm_bounds.center().x()
                if old_span_y > 0:
                    ny = int(round(target_top + (p.y() - min_y) * (target_span_y / old_span_y)))
                else:
                    ny = norm_bounds.center().y()
                new_points.append(QPoint(nx, ny))
            self.points = new_points

    def render(self, painter: QPainter) -> None:
        """Renders this item onto a QPainter at image coordinates."""
        painter.save()
        painter.setRenderHint(QPainter.Antialiasing)

        b_rect = self.get_bounding_rect()
        if not b_rect.isValid():
            painter.restore()
            return

        center = b_rect.center()
        if abs(self.rotation) > 0.001:
            painter.translate(center.x(), center.y())
            painter.rotate(self.rotation)
            painter.translate(-center.x(), -center.y())

        if self.item_type == self.TYPE_PEN and len(self.points) > 0:
            painter.setPen(QPen(self.color, self.stroke_width, Qt.SolidLine, Qt.RoundCap, Qt.RoundJoin))
            if len(self.points) == 1:
                painter.drawPoint(self.points[0])
            else:
                for i in range(len(self.points) - 1):
                    painter.drawLine(self.points[i], self.points[i + 1])

        elif self.item_type == self.TYPE_LINE and len(self.points) >= 2:
            painter.setPen(QPen(self.color, self.stroke_width, Qt.SolidLine, Qt.RoundCap, Qt.RoundJoin))
            painter.drawLine(self.points[0], self.points[1])

        elif self.item_type == self.TYPE_RECTANGLE:
            painter.setPen(QPen(self.color, self.stroke_width, Qt.SolidLine, Qt.RoundCap, Qt.RoundJoin))
            painter.setBrush(Qt.NoBrush)
            painter.drawRect(self.rect)

        elif self.item_type == self.TYPE_CIRCLE:
            painter.setPen(QPen(self.color, self.stroke_width, Qt.SolidLine, Qt.RoundCap, Qt.RoundJoin))
            painter.setBrush(Qt.NoBrush)
            painter.drawEllipse(self.rect)

        elif self.item_type == self.TYPE_TEXT and self.text:
            if self.draw_border:
                border_pen = QPen(self.color, max(1, self.stroke_width // 2), Qt.SolidLine)
                painter.setPen(border_pen)
                painter.setBrush(QColor(0, 0, 0, 160))
                painter.drawRoundedRect(self.rect, 4, 4)

            font = QFont("Arial", self.font_size, QFont.Bold)
            painter.setFont(font)
            text_rect = self.rect.adjusted(6, 6, -6, -6) if self.draw_border else self.rect

            # 8-way drop shadow for high contrast on any background
            painter.setPen(QColor(0, 0, 0, 230))
            for dx, dy in ((-2, -2), (-2, 2), (2, -2), (2, 2), (0, 2), (2, 0), (0, -2), (-2, 0), (-1, -1), (1, 1)):
                painter.drawText(text_rect.translated(dx, dy), Qt.TextWordWrap | Qt.AlignLeft | Qt.AlignTop, self.text)

            painter.setPen(self.color)
            painter.drawText(text_rect, Qt.TextWordWrap | Qt.AlignLeft | Qt.AlignTop, self.text)

        painter.restore()


class ImageAnnotationCanvas(QWidget):
    """Interactive canvas allowing technicians to draw, circle, add rectangles, move forms, and place text with zoom/pan."""

    zoom_changed = Signal(float)
    tool_changed = Signal(str)

    TOOL_SELECT = "select"
    TOOL_PEN = "pen"
    TOOL_LINE = "line"
    TOOL_CIRCLE = "circle"
    TOOL_RECTANGLE = "rectangle"
    TOOL_TEXT = "text"

    HANDLE_NONE = 0
    HANDLE_ROTATE = 1
    HANDLE_CORNER_TL = 2
    HANDLE_CORNER_TR = 3
    HANDLE_CORNER_BR = 4
    HANDLE_CORNER_BL = 5
    HANDLE_EDGE_TOP = 6
    HANDLE_EDGE_BOTTOM = 7
    HANDLE_EDGE_LEFT = 8
    HANDLE_EDGE_RIGHT = 9
    HANDLE_BODY = 10
    HANDLE_SIDE_TOP = 11
    HANDLE_SIDE_BOTTOM = 12
    HANDLE_SIDE_LEFT = 13
    HANDLE_SIDE_RIGHT = 14

    RESIZE_HANDLES = (
        HANDLE_CORNER_TL,
        HANDLE_CORNER_TR,
        HANDLE_CORNER_BR,
        HANDLE_CORNER_BL,
        HANDLE_SIDE_TOP,
        HANDLE_SIDE_BOTTOM,
        HANDLE_SIDE_LEFT,
        HANDLE_SIDE_RIGHT,
    )

    ACTION_NONE = 0
    ACTION_PAN = 1
    ACTION_DRAW = 2
    ACTION_MOVE = 3
    ACTION_ROTATE = 4
    ACTION_RESIZE = 5

    COLOR_PALETTE = [
        ("#ff3b30", "Red"),
        ("#ffcc00", "Yellow"),
        ("#34c759", "Green"),
        ("#00e5ff", "Cyan"),
        ("#ffffff", "White"),
        ("#000000", "Black"),
    ]

    def __init__(
        self,
        image: QImage,
        parent: Optional[QWidget] = None,
        cyber_clock: Optional[CyberNeonClock] = None,
    ):
        super().__init__(parent)
        self.setMinimumSize(420, 320)
        self.setMouseTracking(True)
        self.setFocusPolicy(Qt.StrongFocus)
        self.setCursor(Qt.CrossCursor)
        self._cyber_clock = cyber_clock
        if self._cyber_clock is not None:
            self._cyber_clock.tick.connect(self._on_neon_tick)

        # Base pristine image (ARGB32 format for crisp alpha painting)
        self._base_image: QImage = image.copy().convertToFormat(QImage.Format_ARGB32_Premultiplied)
        self._current_image: QImage = self._base_image.copy()

        # Vector annotation items
        self._items: list[AnnotationItem] = []
        self._selected_item: Optional[AnnotationItem] = None

        # Interactive manipulation states
        self._action_mode: int = self.ACTION_NONE
        self._is_moving_item: bool = False
        self._is_rotating: bool = False
        self._is_resizing: bool = False
        self._shift_pressed: bool = False

        self._move_item_start: QPoint = QPoint()
        self._move_item_prev: QPoint = QPoint()

        self._rotate_start_angle: float = 0.0
        self._rotate_initial_angle: float = 0.0

        self._resize_handle: int = self.HANDLE_NONE
        self._resize_initial_item: Optional[AnnotationItem] = None
        self._resize_initial_rect: QRect = QRect()
        self._resize_initial_pos: QPoint = QPoint()
        self._resize_initial_center: QPointF = QPointF()

        # Undo / Redo history stacks (stores snapshots of items list)
        self._undo_stack: list[list[AnnotationItem]] = []
        self._redo_stack: list[list[AnnotationItem]] = []

        # Current tool settings
        self._active_tool: str = self.TOOL_PEN
        self._current_color: QColor = QColor("#ff3b30")
        self._stroke_width: int = 4
        self._font_size: int = 18

        # Zoom & Pan state
        self._zoom_factor: float = 1.0  # Range 0.25 to 5.0
        self._pan_offset: QPoint = QPoint(0, 0)
        self._is_panning: bool = False
        self._pan_start: QPoint = QPoint()

        # Drawing state
        self._is_drawing: bool = False
        self._drag_start: Optional[QPoint] = None
        self._drag_current: Optional[QPoint] = None
        self._freehand_points: list[QPoint] = []
        self._was_annotated: bool = False

    # -- Coordinate Mapping & Zoom ---------------------------------------------
    def get_image_display_rect(self) -> QRect:
        """Calculates scaled image bounding box centered in the canvas with zoom and pan applied."""
        if self._current_image.isNull():
            return QRect()
        canvas_w = self.width()
        canvas_h = self.height()
        img_w = self._current_image.width()
        img_h = self._current_image.height()
        if img_w <= 0 or img_h <= 0 or canvas_w <= 0 or canvas_h <= 0:
            return QRect()

        fit_scale = min(canvas_w / img_w, canvas_h / img_h)
        scale = fit_scale * self._zoom_factor
        scaled_w = max(1, int(img_w * scale))
        scaled_h = max(1, int(img_h * scale))
        x = (canvas_w - scaled_w) // 2 + self._pan_offset.x()
        y = (canvas_h - scaled_h) // 2 + self._pan_offset.y()
        return QRect(x, y, scaled_w, scaled_h)

    def viewport_to_image_coords(self, pt: QPoint, clamp: bool = False) -> Optional[QPoint]:
        """Translates canvas viewport point to original image pixel coordinates."""
        rect = self.get_image_display_rect()
        if not clamp and not rect.contains(pt):
            return None
        img_w = self._current_image.width()
        img_h = self._current_image.height()
        if rect.width() <= 0 or rect.height() <= 0:
            return None
        x = int((pt.x() - rect.x()) * (img_w / rect.width()))
        y = int((pt.y() - rect.y()) * (img_h / rect.height()))
        return QPoint(max(0, min(img_w - 1, x)), max(0, min(img_h - 1, y)))

    # -- Zoom Controls ---------------------------------------------------------
    def zoom_in(self) -> None:
        """Zooms in by 25% up to 500%."""
        self.set_zoom_factor(self._zoom_factor * 1.25)

    def zoom_out(self) -> None:
        """Zooms out by 20% down to 25%."""
        self.set_zoom_factor(self._zoom_factor / 1.25)

    def reset_zoom(self) -> None:
        """Resets zoom back to fit (100%) and centers pan."""
        self._zoom_factor = 1.0
        self._pan_offset = QPoint(0, 0)
        self.zoom_changed.emit(self._zoom_factor)
        self.update()

    def set_zoom_factor(self, factor: float) -> None:
        """Sets clamped zoom factor (0.25 to 5.0) and updates display."""
        new_factor = max(0.25, min(5.0, factor))
        if abs(new_factor - self._zoom_factor) > 0.001:
            self._zoom_factor = new_factor
            if self._zoom_factor <= 1.0:
                self._pan_offset = QPoint(0, 0)
            self.zoom_changed.emit(self._zoom_factor)
            self.update()

    def get_zoom_factor(self) -> float:
        return self._zoom_factor

    def set_font_size(self, size: int) -> None:
        """Sets active font size and applies to selected text item if any."""
        self._font_size = max(8, min(96, size))
        if self._selected_item and self._selected_item.item_type == AnnotationItem.TYPE_TEXT:
            self._save_undo_state()
            self._selected_item.font_size = self._font_size
            self._regenerate_current_image()
            self.update()

    def get_font_size(self) -> int:
        return self._font_size

    # -- History & State Management --------------------------------------------
    def _save_undo_state(self) -> None:
        """Pushes working items snapshot to undo stack and clears redo stack."""
        self._undo_stack.append([item.clone() for item in self._items])
        self._redo_stack.clear()
        if len(self._undo_stack) > 40:
            self._undo_stack.pop(0)

    def undo(self) -> None:
        """Reverses the last annotation change."""
        if self._undo_stack:
            self._redo_stack.append([item.clone() for item in self._items])
            self._items = self._undo_stack.pop()
            self._selected_item = None
            self._was_annotated = len(self._items) > 0 or len(self._undo_stack) > 0
            self._regenerate_current_image()
            self.update()

    def redo(self) -> None:
        """Re-applies the previously undone annotation change."""
        if self._redo_stack:
            self._undo_stack.append([item.clone() for item in self._items])
            self._items = self._redo_stack.pop()
            self._selected_item = None
            self._was_annotated = True
            self._regenerate_current_image()
            self.update()

    def reset_image(self) -> None:
        """Resets the image back to its original unmodified state."""
        self._save_undo_state()
        self._items.clear()
        self._selected_item = None
        self._was_annotated = False
        self._regenerate_current_image()
        self.update()

    def can_undo(self) -> bool:
        return len(self._undo_stack) > 0

    def can_redo(self) -> bool:
        return len(self._redo_stack) > 0

    def was_annotated(self) -> bool:
        return self._was_annotated or len(self._items) > 0

    def get_annotated_image(self) -> QImage:
        return self._current_image

    def _regenerate_current_image(self) -> None:
        """Bakes all current annotation items onto clean copy of base image for display/export."""
        baked = self._base_image.copy()
        painter = QPainter(baked)
        painter.setRenderHint(QPainter.Antialiasing)
        for item in self._items:
            item.render(painter)
        painter.end()
        self._current_image = baked

    # -- Tool, Selection & Move Configuration ----------------------------------
    def set_tool(self, tool_name: str) -> None:
        self._active_tool = tool_name
        if tool_name != self.TOOL_SELECT:
            self._selected_item = None
        self._update_cursor()
        self.tool_changed.emit(tool_name)
        self.update()

    def _update_cursor(self) -> None:
        if self._is_panning:
            self.setCursor(Qt.ClosedHandCursor)
        elif self._is_moving_item:
            self.setCursor(Qt.SizeAllCursor)
        elif self._active_tool == self.TOOL_SELECT:
            self.setCursor(Qt.ArrowCursor)
        elif self._active_tool == self.TOOL_TEXT:
            self.setCursor(Qt.IBeamCursor)
        else:
            self.setCursor(Qt.CrossCursor)

    def set_color(self, color: QColor) -> None:
        self._current_color = color
        if self._selected_item:
            self._save_undo_state()
            self._selected_item.color = QColor(color)
            self._regenerate_current_image()
            self.update()

    def set_stroke_width(self, width: int) -> None:
        self._stroke_width = max(1, width)
        if self._selected_item and self._selected_item.item_type != AnnotationItem.TYPE_TEXT:
            self._save_undo_state()
            self._selected_item.stroke_width = self._stroke_width
            self._regenerate_current_image()
            self.update()

    def select_item_at(self, img_pt: QPoint) -> Optional[AnnotationItem]:
        """Finds topmost item under img_pt and marks it selected."""
        for item in reversed(self._items):
            if item.contains_point(img_pt):
                self._selected_item = item
                self.update()
                return item
        self._selected_item = None
        self.update()
        return None

    def get_items(self) -> list[AnnotationItem]:
        return self._items

    def get_selected_item(self) -> Optional[AnnotationItem]:
        return self._selected_item

    def delete_selected_item(self) -> bool:
        """Deletes the currently selected item and refreshes canvas."""
        if self._selected_item and self._selected_item in self._items:
            self._save_undo_state()
            self._items.remove(self._selected_item)
            self._selected_item = None
            self._regenerate_current_image()
            self.update()
            return True
        return False

    def move_selected_item(self, dx: int, dy: int) -> bool:
        """Moves the currently selected item by (dx, dy) pixels."""
        if self._selected_item:
            self._save_undo_state()
            self._selected_item.translate(dx, dy)
            self._regenerate_current_image()
            self.update()
            return True
        return False

    def rotate_selected_item(self, angle: float = 90.0) -> bool:
        """Rotates the currently selected item by angle degrees clockwise and records undo state."""
        item = self._selected_item
        if not item and self._items:
            item = self._items[-1]
            self._selected_item = item
        if item:
            self._save_undo_state()
            item.rotate(angle)
            self._was_annotated = True
            self._regenerate_current_image()
            self.update()
            return True
        return False

    @staticmethod
    def _unrotate_pt(pt: QPoint, center: QPointF, angle_degrees: float) -> QPointF:
        rad = math.radians(-angle_degrees)
        cos_a = math.cos(rad)
        sin_a = math.sin(rad)
        dx = pt.x() - center.x()
        dy = pt.y() - center.y()
        return QPointF(
            center.x() + dx * cos_a - dy * sin_a,
            center.y() + dx * sin_a + dy * cos_a,
        )

    @staticmethod
    def snap_to_straight_line(p1: QPoint, p2: QPoint) -> QPoint:
        """Snaps p2 relative to p1 to the nearest horizontal, vertical, or 45-degree diagonal line (Paint style)."""
        dx = p2.x() - p1.x()
        dy = p2.y() - p1.y()
        if dx == 0 and dy == 0:
            return p2

        angle = math.degrees(math.atan2(dy, dx))
        snapped_angle = round(angle / 45.0) * 45.0
        dist = math.hypot(dx, dy)

        snapped_rad = math.radians(snapped_angle)
        new_dx = int(round(dist * math.cos(snapped_rad)))
        new_dy = int(round(dist * math.sin(snapped_rad)))
        return QPoint(p1.x() + new_dx, p1.y() + new_dy)

    @classmethod
    def _cursor_for_handle(cls, handle: int):
        """Returns the Qt cursor shape appropriate for the given selection handle."""
        if handle == cls.HANDLE_ROTATE:
            return Qt.PointingHandCursor
        if handle in (cls.HANDLE_CORNER_TL, cls.HANDLE_CORNER_BR):
            return Qt.SizeFDiagCursor
        if handle in (cls.HANDLE_CORNER_TR, cls.HANDLE_CORNER_BL):
            return Qt.SizeBDiagCursor
        if handle in (cls.HANDLE_SIDE_TOP, cls.HANDLE_SIDE_BOTTOM):
            return Qt.SizeVerCursor
        if handle in (cls.HANDLE_SIDE_LEFT, cls.HANDLE_SIDE_RIGHT):
            return Qt.SizeHorCursor
        if handle in (
            cls.HANDLE_EDGE_TOP,
            cls.HANDLE_EDGE_BOTTOM,
            cls.HANDLE_EDGE_LEFT,
            cls.HANDLE_EDGE_RIGHT,
            cls.HANDLE_BODY,
        ):
            return Qt.SizeAllCursor
        return Qt.ArrowCursor

    def get_selection_handle_at(self, vp_pos: QPoint) -> tuple[int, Optional[AnnotationItem]]:
        """Hit-tests the active selected item to determine if vp_pos touches rotation handle, corners, side resize handles, edges, or body."""
        if not self._selected_item:
            return (self.HANDLE_NONE, None)

        rect = self.get_image_display_rect()
        if not rect.isValid() or self._current_image.isNull() or self._current_image.width() <= 0 or self._current_image.height() <= 0:
            return (self.HANDLE_NONE, None)

        scale_x = rect.width() / self._current_image.width()
        scale_y = rect.height() / self._current_image.height()
        b_rect = self._selected_item.get_bounding_rect()
        if not b_rect.isValid():
            return (self.HANDLE_NONE, None)

        center_x = rect.x() + b_rect.center().x() * scale_x
        center_y = rect.y() + b_rect.center().y() * scale_y
        vp_w = max(16.0, b_rect.width() * scale_x)
        vp_h = max(16.0, b_rect.height() * scale_y)
        local_box = QRectF(-vp_w / 2.0 - 4.0, -vp_h / 2.0 - 4.0, vp_w + 8.0, vp_h + 8.0)

        # Unrotate the viewport position into local coordinates
        dx = vp_pos.x() - center_x
        dy = vp_pos.y() - center_y
        rad = math.radians(-self._selected_item.rotation)
        cos_a = math.cos(rad)
        sin_a = math.sin(rad)
        local_x = dx * cos_a - dy * sin_a
        local_y = dx * sin_a + dy * cos_a

        # 1. Rotation handle: (0, local_box.top() - 24)
        rot_y = local_box.top() - 24.0
        if math.hypot(local_x - 0.0, local_y - rot_y) <= 12.0:
            return (self.HANDLE_ROTATE, self._selected_item)

        # 2. Corner handles (10px hit radius)
        if math.hypot(local_x - local_box.left(), local_y - local_box.top()) <= 10.0:
            return (self.HANDLE_CORNER_TL, self._selected_item)
        if math.hypot(local_x - local_box.right(), local_y - local_box.top()) <= 10.0:
            return (self.HANDLE_CORNER_TR, self._selected_item)
        if math.hypot(local_x - local_box.right(), local_y - local_box.bottom()) <= 10.0:
            return (self.HANDLE_CORNER_BR, self._selected_item)
        if math.hypot(local_x - local_box.left(), local_y - local_box.bottom()) <= 10.0:
            return (self.HANDLE_CORNER_BL, self._selected_item)

        # 3. Side midpoint resize handles (9px hit radius)
        if math.hypot(local_x - 0.0, local_y - local_box.top()) <= 9.0:
            return (self.HANDLE_SIDE_TOP, self._selected_item)
        if math.hypot(local_x - 0.0, local_y - local_box.bottom()) <= 9.0:
            return (self.HANDLE_SIDE_BOTTOM, self._selected_item)
        if math.hypot(local_x - local_box.left(), local_y - 0.0) <= 9.0:
            return (self.HANDLE_SIDE_LEFT, self._selected_item)
        if math.hypot(local_x - local_box.right(), local_y - 0.0) <= 9.0:
            return (self.HANDLE_SIDE_RIGHT, self._selected_item)

        # 4. Edges of the rectangle (8px margin around perimeter for easy moving)
        margin = 8.0
        on_top = abs(local_y - local_box.top()) <= margin and (local_box.left() - margin <= local_x <= local_box.right() + margin)
        if on_top:
            return (self.HANDLE_EDGE_TOP, self._selected_item)
        on_bottom = abs(local_y - local_box.bottom()) <= margin and (local_box.left() - margin <= local_x <= local_box.right() + margin)
        if on_bottom:
            return (self.HANDLE_EDGE_BOTTOM, self._selected_item)
        on_left = abs(local_x - local_box.left()) <= margin and (local_box.top() - margin <= local_y <= local_box.bottom() + margin)
        if on_left:
            return (self.HANDLE_EDGE_LEFT, self._selected_item)
        on_right = abs(local_x - local_box.right()) <= margin and (local_box.top() - margin <= local_y <= local_box.bottom() + margin)
        if on_right:
            return (self.HANDLE_EDGE_RIGHT, self._selected_item)

        # 5. Inside the body
        if local_box.contains(local_x, local_y):
            return (self.HANDLE_BODY, self._selected_item)

        return (self.HANDLE_NONE, None)

    def _on_neon_tick(self, _phase: float) -> None:
        try:
            if self.isVisible():
                self.update()
        except RuntimeError:
            pass

    # -- Painting & Mouse Handlers ---------------------------------------------
    def paintEvent(self, event: QPaintEvent) -> None:
        painter = QPainter(self)
        painter.setRenderHint(QPainter.Antialiasing)
        painter.setRenderHint(QPainter.SmoothPixmapTransform)

        phase = self._cyber_clock.phase if self._cyber_clock is not None else 0.0
        w, h = float(self.width()), float(self.height())

        # 0. Futuristic Cyber-Void Backdrop + Holographic Neon Blueprint Grid
        bg = QLinearGradient(0.0, 0.0, w, h)
        bg.setColorAt(0.0, QColor("#060414"))
        bg.setColorAt(0.5, QColor("#0b0724"))
        bg.setColorAt(1.0, QColor("#061326"))
        painter.fillRect(self.rect(), QBrush(bg))

        # Subtle holographic grid lines (viewport only — never baked into image)
        grid_step = 28
        grid_cyan = sample_cyber_rainbow(phase + 0.55, 22)
        grid_mag = sample_cyber_rainbow(phase, 18)
        painter.setPen(QPen(grid_cyan, 1.0))
        for gx in range(0, self.width(), grid_step):
            painter.drawLine(gx, 0, gx, self.height())
        painter.setPen(QPen(grid_mag, 1.0))
        for gy in range(0, self.height(), grid_step):
            painter.drawLine(0, gy, self.width(), gy)

        # Outer holographic canvas rim
        rim_grad = QLinearGradient(0.0, 0.0, w, h)
        for i in range(5):
            t = i / 4.0
            rim_grad.setColorAt(t, sample_cyber_rainbow(phase + t * 0.75, 165))
        painter.setPen(QPen(QBrush(rim_grad), 1.6))
        painter.setBrush(Qt.NoBrush)
        painter.drawRoundedRect(QRectF(1.0, 1.0, max(1.0, w - 2.0), max(1.0, h - 2.0)), 8.0, 8.0)

        rect = self.get_image_display_rect()
        if rect.isValid() and not self._current_image.isNull():
            # 1. Animated Rainbow Neon Aura & Prism Frame around Displayed Image
            frame_grad = QLinearGradient(float(rect.left()), float(rect.top()), float(rect.right()), float(rect.bottom()))
            for i in range(6):
                t = i / 5.0
                frame_grad.setColorAt(t, sample_cyber_rainbow(phase + t * 0.85, 255))

            painter.save()
            painter.setOpacity(0.32)
            painter.setPen(QPen(QBrush(frame_grad), 6.0, Qt.SolidLine, Qt.RoundCap, Qt.RoundJoin))
            painter.drawRect(rect.adjusted(-1, -1, 1, 1))
            painter.restore()

            # Render baked working image
            painter.drawImage(rect, self._current_image)

            # Crisp neon rainbow image frame border
            painter.setPen(QPen(QBrush(frame_grad), 1.8))
            painter.setBrush(Qt.NoBrush)
            painter.drawRect(rect)

            # Futuristic L-shaped corner targeting reticles outside image bounds
            ret = 12
            c_a = sample_cyber_rainbow(phase + 0.55, 235)
            c_b = sample_cyber_rainbow(phase, 235)
            r_out = rect.adjusted(-5, -5, 5, 5)
            painter.setPen(QPen(c_a, 2.2, Qt.SolidLine, Qt.RoundCap))
            painter.drawLine(r_out.left(), r_out.top() + ret, r_out.left(), r_out.top())
            painter.drawLine(r_out.left(), r_out.top(), r_out.left() + ret, r_out.top())
            painter.drawLine(r_out.right() - ret, r_out.bottom(), r_out.right(), r_out.bottom())
            painter.drawLine(r_out.right(), r_out.bottom() - ret, r_out.right(), r_out.bottom())
            painter.setPen(QPen(c_b, 2.2, Qt.SolidLine, Qt.RoundCap))
            painter.drawLine(r_out.right() - ret, r_out.top(), r_out.right(), r_out.top())
            painter.drawLine(r_out.right(), r_out.top(), r_out.right(), r_out.top() + ret)
            painter.drawLine(r_out.left(), r_out.bottom() - ret, r_out.left(), r_out.bottom())
            painter.drawLine(r_out.left(), r_out.bottom(), r_out.left() + ret, r_out.bottom())

            scale_x = rect.width() / self._current_image.width()
            scale_y = rect.height() / self._current_image.height()

            # 3. Cyber-Neon Selection outline, rotation handle, corners, and edges around selected item
            if self._selected_item:
                b_rect = self._selected_item.get_bounding_rect()
                center_x = rect.x() + b_rect.center().x() * scale_x
                center_y = rect.y() + b_rect.center().y() * scale_y
                vp_w = max(16.0, b_rect.width() * scale_x)
                vp_h = max(16.0, b_rect.height() * scale_y)
                local_box = QRectF(-vp_w / 2.0 - 4.0, -vp_h / 2.0 - 4.0, vp_w + 8.0, vp_h + 8.0)

                painter.save()
                painter.translate(center_x, center_y)
                painter.rotate(self._selected_item.rotation)

                # Animated rainbow neon dashed selection outline + soft glowing tint
                sel_grad = QLinearGradient(local_box.topLeft(), local_box.bottomRight())
                for i in range(5):
                    t = i / 4.0
                    sel_grad.setColorAt(t, sample_cyber_rainbow(phase + t * 0.9, 255))
                sel_pen = QPen(QBrush(sel_grad), 2.0, Qt.DashLine)
                painter.setPen(sel_pen)
                tint = sample_cyber_rainbow(phase + 0.5, 36)
                painter.setBrush(tint)
                painter.drawRect(local_box)

                # Rotation stem and luminous plasma orb handle
                stem_top = local_box.top() - 24.0
                painter.setPen(QPen(sample_cyber_rainbow(phase + 0.55, 240), 2.0, Qt.SolidLine))
                painter.drawLine(QPointF(0.0, local_box.top()), QPointF(0.0, stem_top))

                orb_grad = QRadialGradient(QPointF(0.0, stem_top), 7.0)
                orb_grad.setColorAt(0.0, QColor("#ffffff"))
                orb_grad.setColorAt(0.55, sample_cyber_rainbow(phase + 0.5, 255))
                orb_grad.setColorAt(1.0, sample_cyber_rainbow(phase, 255))
                painter.setBrush(QBrush(orb_grad))
                painter.setPen(QPen(QColor("#ffffff"), 1.5))
                painter.drawEllipse(QPointF(0.0, stem_top), 6.0, 6.0)

                # Glowing neon corner grab handles
                painter.setBrush(QColor("#0d0824"))
                painter.setPen(QPen(sample_cyber_rainbow(phase + 0.55, 255), 2.0))
                h_size = 8.5
                for hx, hy in (
                    (local_box.left(), local_box.top()),
                    (local_box.right(), local_box.top()),
                    (local_box.left(), local_box.bottom()),
                    (local_box.right(), local_box.bottom()),
                ):
                    painter.drawRoundedRect(QRectF(hx - h_size / 2.0, hy - h_size / 2.0, h_size, h_size), 2.0, 2.0)

                # Neon magenta edge mid-handles
                painter.setBrush(QColor("#14092e"))
                painter.setPen(QPen(sample_cyber_rainbow(phase, 255), 1.8))
                m_size = 7.5
                for hx, hy in (
                    (0.0, local_box.top()),
                    (0.0, local_box.bottom()),
                    (local_box.left(), 0.0),
                    (local_box.right(), 0.0),
                ):
                    painter.drawRoundedRect(QRectF(hx - m_size / 2.0, hy - m_size / 2.0, m_size, m_size), 2.0, 2.0)

                painter.restore()

                # Live holographic status badge when rotating or resizing
                if self._is_rotating or self._is_resizing:
                    if self._is_rotating:
                        angle_deg = int(round(self._selected_item.rotation)) % 360
                        badge_text = f"⟳ {angle_deg}°"
                        if self._shift_pressed:
                            badge_text += " (Snap 15°)"
                    else:
                        badge_text = f"📐 {b_rect.width()} × {b_rect.height()} px"
                    painter.setFont(QFont("Segoe UI", 9, QFont.Bold))
                    fm = QFontMetrics(painter.font())
                    tw = fm.horizontalAdvance(badge_text) + 18
                    th = fm.height() + 10
                    badge_rect = QRectF(center_x - tw / 2.0, center_y - vp_h / 2.0 - 55.0, tw, th)
                    badge_bg = QLinearGradient(badge_rect.topLeft(), badge_rect.bottomRight())
                    badge_bg.setColorAt(0.0, QColor(24, 12, 56, 235))
                    badge_bg.setColorAt(1.0, QColor(8, 22, 48, 235))
                    painter.setBrush(QBrush(badge_bg))
                    painter.setPen(QPen(sample_cyber_rainbow(phase + 0.5, 255), 1.8))
                    painter.drawRoundedRect(badge_rect, 6.0, 6.0)
                    painter.setPen(QColor("#ffffff"))
                    painter.drawText(badge_rect, Qt.AlignCenter, badge_text)

            # 4. Interactive shape drag preview overlay (with neon outer glow bloom)
            if self._is_drawing and self._drag_start and self._drag_current:
                vp_start = QPoint(
                    int(rect.x() + self._drag_start.x() * scale_x),
                    int(rect.y() + self._drag_start.y() * scale_y),
                )
                vp_curr = QPoint(
                    int(rect.x() + self._drag_current.x() * scale_x),
                    int(rect.y() + self._drag_current.y() * scale_y),
                )
                preview_rect = QRect(vp_start, vp_curr).normalized()
                glow_col = QColor(self._current_color)
                glow_col.setAlpha(95)
                stroke_px = max(1, int(self._stroke_width * scale_x))

                if self._active_tool == self.TOOL_LINE:
                    painter.setPen(QPen(glow_col, stroke_px + 5, Qt.SolidLine, Qt.RoundCap, Qt.RoundJoin))
                    painter.drawLine(vp_start, vp_curr)
                    line_pen = QPen(self._current_color, stroke_px, Qt.SolidLine, Qt.RoundCap, Qt.RoundJoin)
                    painter.setPen(line_pen)
                    painter.drawLine(vp_start, vp_curr)
                elif self._active_tool == self.TOOL_RECTANGLE:
                    painter.setBrush(Qt.NoBrush)
                    painter.setPen(QPen(glow_col, stroke_px + 5, Qt.SolidLine))
                    painter.drawRect(preview_rect)
                    painter.setPen(QPen(self._current_color, stroke_px, Qt.SolidLine))
                    painter.drawRect(preview_rect)
                elif self._active_tool == self.TOOL_CIRCLE:
                    painter.setBrush(Qt.NoBrush)
                    painter.setPen(QPen(glow_col, stroke_px + 5, Qt.SolidLine))
                    painter.drawEllipse(preview_rect)
                    painter.setPen(QPen(self._current_color, stroke_px, Qt.SolidLine))
                    painter.drawEllipse(preview_rect)
                elif self._active_tool == self.TOOL_TEXT:
                    txt_grad = QLinearGradient(float(preview_rect.left()), float(preview_rect.top()), float(preview_rect.right()), float(preview_rect.bottom()))
                    txt_grad.setColorAt(0.0, sample_cyber_rainbow(phase, 255))
                    txt_grad.setColorAt(0.5, sample_cyber_rainbow(phase + 0.45, 255))
                    txt_grad.setColorAt(1.0, sample_cyber_rainbow(phase + 0.8, 255))
                    dash_pen = QPen(QBrush(txt_grad), 2.0, Qt.DashLine)
                    painter.setPen(dash_pen)
                    painter.setBrush(QColor(self._current_color.red(), self._current_color.green(), self._current_color.blue(), 35))
                    painter.drawRect(preview_rect)
                    painter.setPen(self._current_color)
                    font_preview = QFont("Segoe UI", max(8, int(self._font_size * scale_x)), QFont.Bold)
                    painter.setFont(font_preview)
                    painter.drawText(preview_rect.adjusted(4, 4, -4, -4), Qt.AlignLeft | Qt.AlignTop, "🔤 Text Box...")

    def wheelEvent(self, event) -> None:
        """Handles Ctrl+Mouse Wheel for zooming and standard wheel for panning when zoomed in."""
        if event.modifiers() & Qt.ControlModifier:
            delta = event.angleDelta().y()
            if delta > 0:
                self.zoom_in()
            elif delta < 0:
                self.zoom_out()
            event.accept()
        elif self._zoom_factor > 1.0:
            dy = event.angleDelta().y() // 8
            dx = event.angleDelta().x() // 8
            self._pan_offset += QPoint(dx, dy)
            self.update()
            event.accept()
        else:
            super().wheelEvent(event)

    def mousePressEvent(self, event: QMouseEvent) -> None:
        self.setFocus()

        # 1. Pan with Middle-click or Right-click
        if event.button() in (Qt.MiddleButton, Qt.RightButton):
            self._action_mode = self.ACTION_PAN
            self._is_panning = True
            pos = event.position().toPoint() if hasattr(event, "position") else event.pos()
            self._pan_start = pos - self._pan_offset
            self.setCursor(Qt.ClosedHandCursor)
            event.accept()
            return

        if event.button() != Qt.LeftButton:
            return

        pos = event.position().toPoint() if hasattr(event, "position") else event.pos()
        clamped_pt = self.viewport_to_image_coords(pos, clamp=True)

        # 2. Check if clicking on active handle of currently selected item (works even near image borders)
        handle, item = self.get_selection_handle_at(pos)
        if item and handle != self.HANDLE_NONE and clamped_pt is not None:
            # Handle rotation
            if handle == self.HANDLE_ROTATE:
                self._save_undo_state()
                self._action_mode = self.ACTION_ROTATE
                self._is_rotating = True
                rect = self.get_image_display_rect()
                scale_x = rect.width() / self._current_image.width()
                scale_y = rect.height() / self._current_image.height()
                b_rect = item.get_bounding_rect()
                center_x = rect.x() + b_rect.center().x() * scale_x
                center_y = rect.y() + b_rect.center().y() * scale_y
                self._rotate_start_angle = math.degrees(math.atan2(pos.y() - center_y, pos.x() - center_x))
                self._rotate_initial_angle = item.rotation
                self.setCursor(self._cursor_for_handle(handle))
                event.accept()
                return

            # Handle corner or side midpoint resizing for all item types
            if handle in self.RESIZE_HANDLES:
                self._save_undo_state()
                self._action_mode = self.ACTION_RESIZE
                self._is_resizing = True
                self._resize_handle = handle
                self._resize_initial_item = item.clone()
                self._resize_initial_rect = QRect(item.get_bounding_rect())
                self._resize_initial_pos = clamped_pt
                self._resize_initial_center = QPointF(self._resize_initial_rect.center())
                self.setCursor(self._cursor_for_handle(handle))
                event.accept()
                return

            # Handle edge clicking or body clicking -> MOVE!
            if handle in (
                self.HANDLE_EDGE_TOP,
                self.HANDLE_EDGE_BOTTOM,
                self.HANDLE_EDGE_LEFT,
                self.HANDLE_EDGE_RIGHT,
                self.HANDLE_BODY,
            ):
                self._save_undo_state()
                self._action_mode = self.ACTION_MOVE
                self._is_moving_item = True
                self._move_item_start = clamped_pt
                self._move_item_prev = clamped_pt
                self.setCursor(Qt.SizeAllCursor)
                event.accept()
                return

        img_pt = self.viewport_to_image_coords(pos)
        if not img_pt:
            return

        # 3. Not touching the selected item's handles; check if clicking another item
        hit_other = self.select_item_at(img_pt)
        if hit_other:
            self._save_undo_state()
            self._action_mode = self.ACTION_MOVE
            self._is_moving_item = True
            self._move_item_start = img_pt
            self._move_item_prev = img_pt
            self.setCursor(Qt.SizeAllCursor)
            event.accept()
            return

        # 4. Clicking empty space
        if self._active_tool == self.TOOL_SELECT:
            self._selected_item = None
            self.update()
            return

        # 5. Drawing tool on empty space
        self._selected_item = None
        self._save_undo_state()
        self._action_mode = self.ACTION_DRAW
        self._is_drawing = True
        self._drag_start = img_pt
        self._drag_current = img_pt
        self._freehand_points = [img_pt]
        self.update()

    def mouseMoveEvent(self, event: QMouseEvent) -> None:
        pos = event.position().toPoint() if hasattr(event, "position") else event.pos()
        self._shift_pressed = bool(event.modifiers() & Qt.ShiftModifier)

        # 1. Panning canvas
        if self._action_mode == self.ACTION_PAN and self._is_panning:
            self._pan_offset = pos - self._pan_start
            self.update()
            event.accept()
            return

        # 2. Rotating selected item
        if self._action_mode == self.ACTION_ROTATE and self._selected_item:
            rect = self.get_image_display_rect()
            if rect.isValid() and not self._current_image.isNull():
                scale_x = rect.width() / self._current_image.width()
                scale_y = rect.height() / self._current_image.height()
                b_rect = self._selected_item.get_bounding_rect()
                center_x = rect.x() + b_rect.center().x() * scale_x
                center_y = rect.y() + b_rect.center().y() * scale_y
                curr_angle = math.degrees(math.atan2(pos.y() - center_y, pos.x() - center_x))
                delta = curr_angle - self._rotate_start_angle
                new_angle = (self._rotate_initial_angle + delta) % 360.0
                if event.modifiers() & Qt.ShiftModifier:
                    new_angle = round(new_angle / 15.0) * 15.0
                self._selected_item.rotation = new_angle
                self._regenerate_current_image()
                self.update()
            event.accept()
            return

        # 3. Resizing selected item
        if self._action_mode == self.ACTION_RESIZE and self._selected_item and self._resize_initial_item:
            img_pt = self.viewport_to_image_coords(pos, clamp=True)
            if img_pt:
                center = self._resize_initial_center
                rot = self._selected_item.rotation
                p_curr = self._unrotate_pt(img_pt, center, rot)
                p_start = self._unrotate_pt(self._resize_initial_pos, center, rot)
                dx = int(round(p_curr.x() - p_start.x()))
                dy = int(round(p_curr.y() - p_start.y()))

                init_r = self._resize_initial_rect
                left = init_r.left()
                top = init_r.top()
                right = init_r.left() + init_r.width()
                bottom = init_r.top() + init_r.height()
                min_s = 16

                if self._resize_handle in (self.HANDLE_CORNER_TL, self.HANDLE_CORNER_BL, self.HANDLE_SIDE_LEFT):
                    left = min(right - min_s, left + dx)
                if self._resize_handle in (self.HANDLE_CORNER_TR, self.HANDLE_CORNER_BR, self.HANDLE_SIDE_RIGHT):
                    right = max(left + min_s, right + dx)
                if self._resize_handle in (self.HANDLE_CORNER_TL, self.HANDLE_CORNER_TR, self.HANDLE_SIDE_TOP):
                    top = min(bottom - min_s, top + dy)
                if self._resize_handle in (self.HANDLE_CORNER_BL, self.HANDLE_CORNER_BR, self.HANDLE_SIDE_BOTTOM):
                    bottom = max(top + min_s, bottom + dy)

                self._selected_item.resize_to_bounding_rect(
                    QRect(left, top, right - left, bottom - top),
                    self._resize_initial_item,
                )
                self._was_annotated = True
                self._regenerate_current_image()
                self.update()
            event.accept()
            return

        # 4. Moving selected item
        if self._action_mode == self.ACTION_MOVE and self._selected_item:
            img_pt = self.viewport_to_image_coords(pos, clamp=True)
            if img_pt:
                dx = img_pt.x() - self._move_item_prev.x()
                dy = img_pt.y() - self._move_item_prev.y()
                if dx != 0 or dy != 0:
                    self._selected_item.translate(dx, dy)
                    self._move_item_prev = img_pt
                    self._regenerate_current_image()
                    self.update()
            event.accept()
            return

        # 5. Drawing mode
        if self._action_mode == self.ACTION_DRAW and self._is_drawing:
            img_pt = self.viewport_to_image_coords(pos, clamp=True)
            if img_pt:
                if self._active_tool == self.TOOL_LINE and self._drag_start:
                    if event.modifiers() & Qt.ShiftModifier:
                        self._drag_current = self.snap_to_straight_line(self._drag_start, img_pt)
                    else:
                        self._drag_current = img_pt
                else:
                    self._drag_current = img_pt

                if self._active_tool == self.TOOL_PEN:
                    prev_pt = self._freehand_points[-1]
                    painter = QPainter(self._current_image)
                    painter.setRenderHint(QPainter.Antialiasing)
                    painter.setPen(QPen(self._current_color, self._stroke_width, Qt.SolidLine, Qt.RoundCap, Qt.RoundJoin))
                    painter.drawLine(prev_pt, img_pt)
                    painter.end()
                    self._freehand_points.append(img_pt)
                    self._was_annotated = True
                self.update()
            return

        # 6. Hover cursor update
        handle, item = self.get_selection_handle_at(pos)
        if item and handle != self.HANDLE_NONE:
            self.setCursor(self._cursor_for_handle(handle))
            return

        # If hovering over any other item on the canvas
        img_pt = self.viewport_to_image_coords(pos)
        if img_pt and any(it.contains_point(img_pt) for it in self._items):
            self.setCursor(Qt.SizeAllCursor)
            return

        self._update_cursor()

    def mouseReleaseEvent(self, event: QMouseEvent) -> None:
        if self._action_mode == self.ACTION_PAN:
            self._action_mode = self.ACTION_NONE
            self._is_panning = False
            self._update_cursor()
            event.accept()
            return

        if self._action_mode == self.ACTION_ROTATE:
            self._action_mode = self.ACTION_NONE
            self._is_rotating = False
            if self._selected_item and abs(self._selected_item.rotation - self._rotate_initial_angle) < 0.01 and self._undo_stack:
                self._undo_stack.pop()
            self._regenerate_current_image()
            self._update_cursor()
            self.update()
            event.accept()
            return

        if self._action_mode == self.ACTION_RESIZE:
            self._action_mode = self.ACTION_NONE
            self._is_resizing = False
            if self._selected_item and self._selected_item.get_bounding_rect() == self._resize_initial_rect and self._undo_stack:
                self._undo_stack.pop()
            self._resize_initial_item = None
            self._regenerate_current_image()
            self._update_cursor()
            self.update()
            event.accept()
            return

        if self._action_mode == self.ACTION_MOVE:
            self._action_mode = self.ACTION_NONE
            self._is_moving_item = False
            if self._move_item_prev == self._move_item_start and self._undo_stack:
                self._undo_stack.pop()
            self._regenerate_current_image()
            self._update_cursor()
            self.update()
            event.accept()
            return

        if self._action_mode == self.ACTION_DRAW:
            self._action_mode = self.ACTION_NONE
            self._is_drawing = False

            if self._active_tool == self.TOOL_TEXT and self._drag_start and self._drag_current:
                shape_rect = QRect(self._drag_start, self._drag_current).normalized()
                if shape_rect.width() < 24 or shape_rect.height() < 20:
                    shape_rect = QRect(self._drag_start.x(), self._drag_start.y(), 260, max(50, self._font_size * 3))
                img_w = self._current_image.width()
                img_h = self._current_image.height()
                shape_rect = shape_rect.intersected(QRect(0, 0, img_w, img_h))
                self._prompt_and_add_text_rect(shape_rect)

            elif self._active_tool == self.TOOL_PEN and len(self._freehand_points) >= 1:
                item = AnnotationItem(
                    AnnotationItem.TYPE_PEN,
                    self._current_color,
                    self._stroke_width,
                    points=self._freehand_points,
                )
                self._items.append(item)
                self._selected_item = item
                self._was_annotated = True
                self._regenerate_current_image()

            elif self._active_tool == self.TOOL_LINE and self._drag_start and self._drag_current:
                end_pt = self._drag_current
                if (event.modifiers() & Qt.ShiftModifier) or self._shift_pressed:
                    end_pt = self.snap_to_straight_line(self._drag_start, end_pt)
                dist = math.hypot(end_pt.x() - self._drag_start.x(), end_pt.y() - self._drag_start.y())
                if dist >= 3:
                    item = AnnotationItem(
                        AnnotationItem.TYPE_LINE,
                        self._current_color,
                        self._stroke_width,
                        points=[self._drag_start, end_pt],
                    )
                    self._items.append(item)
                    self._selected_item = item
                    self._was_annotated = True
                    self._regenerate_current_image()
                    self.set_tool(self.TOOL_SELECT)
                else:
                    if self._undo_stack:
                        self._undo_stack.pop()

            elif self._active_tool in (self.TOOL_RECTANGLE, self.TOOL_CIRCLE) and self._drag_start and self._drag_current:
                shape_rect = QRect(self._drag_start, self._drag_current).normalized()
                if shape_rect.width() > 2 or shape_rect.height() > 2:
                    item_type = AnnotationItem.TYPE_RECTANGLE if self._active_tool == self.TOOL_RECTANGLE else AnnotationItem.TYPE_CIRCLE
                    item = AnnotationItem(
                        item_type,
                        self._current_color,
                        self._stroke_width,
                        rect=shape_rect,
                    )
                    self._items.append(item)
                    self._selected_item = item
                    self._was_annotated = True
                    self._regenerate_current_image()
                    self.set_tool(self.TOOL_SELECT)
                else:
                    if self._undo_stack:
                        self._undo_stack.pop()

            self._drag_start = None
            self._drag_current = None
            self._freehand_points.clear()
            self._update_cursor()
            self.update()

    def mouseDoubleClickEvent(self, event: QMouseEvent) -> None:
        """Double clicking a text item in Select mode re-opens dialog to edit its text."""
        if event.button() == Qt.LeftButton:
            pos = event.position().toPoint() if hasattr(event, "position") else event.pos()
            img_pt = self.viewport_to_image_coords(pos)
            if img_pt:
                for item in reversed(self._items):
                    if item.contains_point(img_pt):
                        self._selected_item = item
                        if item.item_type == AnnotationItem.TYPE_TEXT:
                            dlg = TextAnnotationDialog(item.rect, item.font_size, item.color, self)
                            dlg.text_edit.setPlainText(item.text)
                            dlg.chk_border.setChecked(item.draw_border)
                            if dlg.exec() == QDialog.Accepted:
                                new_text = dlg.get_text()
                                if new_text:
                                    self._save_undo_state()
                                    item.text = new_text
                                    item.font_size = dlg.get_font_size()
                                    item.draw_border = dlg.should_draw_border()
                                    self._regenerate_current_image()
                                    self.update()
                        self.update()
                        event.accept()
                        return
        super().mouseDoubleClickEvent(event)

    def keyPressEvent(self, event) -> None:
        """Allows deleting, nudging, and rotating selected forms using keyboard shortcuts."""
        if not self._selected_item and self._items and event.key() in (
            Qt.Key_BracketLeft, Qt.Key_BracketRight,
            Qt.Key_Left, Qt.Key_Right, Qt.Key_Up, Qt.Key_Down,
            Qt.Key_Delete, Qt.Key_Backspace,
        ):
            self._selected_item = self._items[-1]
            self.update()

        if self._selected_item:
            if event.key() in (Qt.Key_Delete, Qt.Key_Backspace):
                self.delete_selected_item()
                event.accept()
                return

            # Rotate shortcuts: [ (rotate -15°) and ] (rotate +15°)
            if event.key() == Qt.Key_BracketLeft:
                self.rotate_selected_item(-15.0)
                event.accept()
                return
            elif event.key() == Qt.Key_BracketRight:
                self.rotate_selected_item(15.0)
                event.accept()
                return

            step = 10 if event.modifiers() & Qt.ShiftModifier else 1
            dx, dy = 0, 0
            if event.key() == Qt.Key_Left:
                dx = -step
            elif event.key() == Qt.Key_Right:
                dx = step
            elif event.key() == Qt.Key_Up:
                dy = -step
            elif event.key() == Qt.Key_Down:
                dy = step

            if dx != 0 or dy != 0:
                self.move_selected_item(dx, dy)
                event.accept()
                return

            if event.key() == Qt.Key_Escape:
                self._selected_item = None
                self.update()
                event.accept()
                return

        super().keyPressEvent(event)

    def add_text_in_rect(
        self,
        rect: QRect,
        text: str,
        font_size: Optional[int] = None,
        draw_border: bool = False,
    ) -> None:
        """Renders text inside specified bounding rectangle and registers as movable annotation item."""
        if not text.strip():
            return
        self._save_undo_state()
        size = font_size if font_size is not None else self._font_size

        item = AnnotationItem(
            item_type=AnnotationItem.TYPE_TEXT,
            color=self._current_color,
            stroke_width=self._stroke_width,
            rect=rect,
            text=text.strip(),
            font_size=size,
            draw_border=draw_border,
        )
        self._items.append(item)
        self._selected_item = item
        self._was_annotated = True
        self._regenerate_current_image()
        self.set_tool(self.TOOL_SELECT)
        self.update()

    def add_text_at(self, img_pt: QPoint, text: str) -> None:
        """Draws text starting at specified pixel point (backward-compatible API)."""
        if not text.strip():
            return
        rect = QRect(img_pt.x(), img_pt.y(), 300, max(60, self._font_size * 3))
        self.add_text_in_rect(rect, text, self._font_size, draw_border=False)

    def _prompt_and_add_text_rect(self, rect: QRect) -> None:
        """Prompts for text and renders it inside the user's dragged bounding rectangle."""
        dlg = TextAnnotationDialog(rect, self._font_size, self._current_color, self)
        if dlg.exec() == QDialog.Accepted:
            text = dlg.get_text()
            chosen_size = dlg.get_font_size()
            draw_border = dlg.should_draw_border()
            if text:
                self.add_text_in_rect(rect, text, chosen_size, draw_border)


class ResizeImageDialog(QDialog):
    """Cyber-Neon Studio Image Editor dialog for resizing, annotating, moving, zooming, and fullscreen editing."""

    _TOOL_HUD_LABELS: dict[str, tuple[str, str]] = {
        ImageAnnotationCanvas.TOOL_SELECT: ("↖️ SELECT / MOVE", "#00f0ff"),
        ImageAnnotationCanvas.TOOL_PEN: ("✏️ NEON PEN", "#ff007f"),
        ImageAnnotationCanvas.TOOL_LINE: ("📏 LASER LINE", "#ffbe0b"),
        ImageAnnotationCanvas.TOOL_CIRCLE: ("⭕ PLASMA CIRCLE", "#c77dff"),
        ImageAnnotationCanvas.TOOL_RECTANGLE: ("🔲 CYBER RECT", "#00ff9d"),
        ImageAnnotationCanvas.TOOL_TEXT: ("🔤 HOLO TEXT", "#ff7b00"),
    }

    def __init__(
        self,
        current_width: int,
        current_height: int,
        original_width: int,
        original_height: int,
        max_pane_width: int = 800,
        image: Optional[QImage] = None,
        parent: Optional[QWidget] = None,
    ):
        super().__init__(parent)
        self.setWindowTitle("Image Editor")
        self.setModal(True)

        # Enable OS Minimize and Maximize/Restore buttons for double-click title bar maximize
        self.setWindowFlags(self.windowFlags() | Qt.WindowMinMaxButtonsHint)

        self._image = image
        self._orig_w = max(1, original_width)
        self._orig_h = max(1, original_height)
        self._curr_w = max(1, current_width)
        self._curr_h = max(1, current_height)
        self._max_pane_w = max(50, max_pane_width)
        self._aspect_ratio = self._orig_w / self._orig_h

        self._updating = False
        self._has_shown = False
        self.canvas: Optional[ImageAnnotationCanvas] = None
        self._cyber_clock = CyberNeonClock(self)

        if self._image and not self._image.isNull():
            self.resize(1020, 680)
            self.setMinimumSize(820, 520)
            self.setWindowState(self.windowState() | Qt.WindowMaximized)
        else:
            self.setMinimumWidth(420)

        self._setup_ui()
        self._apply_styling()

    def paintEvent(self, event: QPaintEvent) -> None:
        """Paints deep cyber-void gradient backdrop with ambient synthwave neon nebulas."""
        painter = QPainter(self)
        painter.setRenderHint(QPainter.Antialiasing, True)
        w, h = float(self.width()), float(self.height())
        phase = self._cyber_clock.phase

        bg = QLinearGradient(0.0, 0.0, w, h)
        bg.setColorAt(0.0, QColor("#050311"))
        bg.setColorAt(0.5, QColor("#0b0722"))
        bg.setColorAt(1.0, QColor("#061326"))
        painter.fillRect(self.rect(), QBrush(bg))

        # Shifting ambient cyber-neon corner glows
        c1 = sample_cyber_rainbow(phase, 36)
        c2 = sample_cyber_rainbow(phase + 0.45, 36)
        c3 = sample_cyber_rainbow(phase + 0.78, 28)

        g1 = QRadialGradient(QPointF(0.0, 0.0), max(w, h) * 0.55)
        g1.setColorAt(0.0, c1)
        g1.setColorAt(1.0, QColor(0, 0, 0, 0))
        painter.fillRect(self.rect(), QBrush(g1))

        g2 = QRadialGradient(QPointF(w, h), max(w, h) * 0.55)
        g2.setColorAt(0.0, c2)
        g2.setColorAt(1.0, QColor(0, 0, 0, 0))
        painter.fillRect(self.rect(), QBrush(g2))

        g3 = QRadialGradient(QPointF(w * 0.85, 0.0), max(w, h) * 0.42)
        g3.setColorAt(0.0, c3)
        g3.setColorAt(1.0, QColor(0, 0, 0, 0))
        painter.fillRect(self.rect(), QBrush(g3))
        painter.end()

    def _setup_ui(self) -> None:
        main_layout = QVBoxLayout(self)
        main_layout.setSpacing(8)
        main_layout.setContentsMargins(12, 10, 12, 10)

        # 1. Top Cyber-Neon Single-Line Annotation Toolbar (if image is available)
        if self._image and not self._image.isNull():
            toolbar_box = DoubleClickableFrame(cyber_clock=self._cyber_clock)
            toolbar_box.setObjectName("annotationToolbar")
            toolbar_box.double_clicked.connect(self._toggle_maximize)
            toolbar_box.setToolTip("Double-click top bar to toggle full screen")

            tb_layout = QHBoxLayout(toolbar_box)
            tb_layout.setContentsMargins(6, 5, 6, 5)
            tb_layout.setSpacing(3)

            # Drawing / Shape Tools (each styled with its own colorful cyber gradient)
            self.tool_group = QButtonGroup(self)
            self.tool_group.setExclusive(True)

            self.btn_tool_select = QToolButton()
            self.btn_tool_select.setText("↖️")
            self.btn_tool_select.setCheckable(True)
            self.btn_tool_select.setToolTip("Select / Move (V) — Select and drag to move text, shapes, or drawings (Delete to remove)")
            self.btn_tool_select.clicked.connect(lambda: self._set_canvas_tool(ImageAnnotationCanvas.TOOL_SELECT))
            style_cyber_button(self.btn_tool_select, "cyan", compact=True, radius=6)
            self.tool_group.addButton(self.btn_tool_select)
            tb_layout.addWidget(self.btn_tool_select)

            self.btn_tool_pen = QToolButton()
            self.btn_tool_pen.setText("✏️")
            self.btn_tool_pen.setCheckable(True)
            self.btn_tool_pen.setChecked(True)
            self.btn_tool_pen.setToolTip("Draw (P) — Freehand drawing pen")
            self.btn_tool_pen.clicked.connect(lambda: self._set_canvas_tool(ImageAnnotationCanvas.TOOL_PEN))
            style_cyber_button(self.btn_tool_pen, "magenta", compact=True, radius=6)
            self.tool_group.addButton(self.btn_tool_pen)
            tb_layout.addWidget(self.btn_tool_pen)

            self.btn_tool_line = QToolButton()
            self.btn_tool_line.setText("📏")
            self.btn_tool_line.setCheckable(True)
            self.btn_tool_line.setToolTip("Line (L) — Draw straight line (Hold Shift for straight horizontal, vertical, or 45° snap)")
            self.btn_tool_line.clicked.connect(lambda: self._set_canvas_tool(ImageAnnotationCanvas.TOOL_LINE))
            style_cyber_button(self.btn_tool_line, "solar", compact=True, radius=6)
            self.tool_group.addButton(self.btn_tool_line)
            tb_layout.addWidget(self.btn_tool_line)

            self.btn_tool_circle = QToolButton()
            self.btn_tool_circle.setText("⭕")
            self.btn_tool_circle.setCheckable(True)
            self.btn_tool_circle.setToolTip("Circle (C) — Draw circle or ellipse callout")
            self.btn_tool_circle.clicked.connect(lambda: self._set_canvas_tool(ImageAnnotationCanvas.TOOL_CIRCLE))
            style_cyber_button(self.btn_tool_circle, "violet", compact=True, radius=6)
            self.tool_group.addButton(self.btn_tool_circle)
            tb_layout.addWidget(self.btn_tool_circle)

            self.btn_tool_rect = QToolButton()
            self.btn_tool_rect.setText("🔲")
            self.btn_tool_rect.setCheckable(True)
            self.btn_tool_rect.setToolTip("Rectangle (R) — Draw rectangle callout box")
            self.btn_tool_rect.clicked.connect(lambda: self._set_canvas_tool(ImageAnnotationCanvas.TOOL_RECTANGLE))
            style_cyber_button(self.btn_tool_rect, "emerald", compact=True, radius=6)
            self.tool_group.addButton(self.btn_tool_rect)
            tb_layout.addWidget(self.btn_tool_rect)

            self.btn_tool_text = QToolButton()
            self.btn_tool_text.setText("🔤")
            self.btn_tool_text.setCheckable(True)
            self.btn_tool_text.setToolTip("Text (T) — Click and drag rectangle on image to add custom text (Paint style)")
            self.btn_tool_text.clicked.connect(lambda: self._set_canvas_tool(ImageAnnotationCanvas.TOOL_TEXT))
            style_cyber_button(self.btn_tool_text, "sunset", compact=True, radius=6)
            self.tool_group.addButton(self.btn_tool_text)
            tb_layout.addWidget(self.btn_tool_text)

            self.btn_rotate_90 = QToolButton()
            self.btn_rotate_90.setText("⟳")
            self.btn_rotate_90.setToolTip("Rotate 90° (Ctrl+R) — Rotate selected form or text 90° clockwise")
            self.btn_rotate_90.clicked.connect(self._on_rotate_90)
            style_cyber_button(self.btn_rotate_90, "indigo", compact=True, radius=6)
            tb_layout.addWidget(self.btn_rotate_90)

            tb_layout.addWidget(CyberNeonLine(self._cyber_clock, Qt.Vertical, thickness=2, phase_offset=0.1))

            # Font Size SpinBox (gradient textbox + animated rainbow border)
            self.spin_font_size = QSpinBox()
            self.spin_font_size.setRange(8, 96)
            self.spin_font_size.setValue(18)
            self.spin_font_size.setSuffix(" pt")
            self.spin_font_size.setMinimumWidth(68)
            self.spin_font_size.setToolTip("Font size for text overlay (8 to 96 pt)")
            self.spin_font_size.valueChanged.connect(self._on_font_size_changed)
            tb_layout.addWidget(self.spin_font_size)

            tb_layout.addWidget(CyberNeonLine(self._cyber_clock, Qt.Vertical, thickness=2, phase_offset=0.3))

            # Glowing Gem Color Swatches + Prismatic Custom Color Picker
            self.color_group = QButtonGroup(self)
            self.color_group.setExclusive(True)

            for hex_color, name in ImageAnnotationCanvas.COLOR_PALETTE:
                btn_c = QToolButton()
                btn_c.setFixedSize(19, 19)
                btn_c.setCheckable(True)
                btn_c.setToolTip(f"{name} ({hex_color})")
                btn_c.setStyleSheet(f"""
                    QToolButton {{
                        background: qradialgradient(
                            cx: 0.35, cy: 0.35, radius: 0.7,
                            fx: 0.3, fy: 0.3,
                            stop: 0 #ffffff,
                            stop: 0.25 {hex_color},
                            stop: 1 {hex_color}
                        );
                        border: 2px solid #4c3b82;
                        border-radius: 9px;
                        padding: 0px;
                    }}
                    QToolButton:hover {{
                        border: 2px solid #00f0ff;
                    }}
                    QToolButton:checked {{
                        border: 2px solid #ffffff;
                    }}
                """)
                if hex_color == "#ff3b30":
                    btn_c.setChecked(True)
                btn_c.clicked.connect(lambda checked=False, col=hex_color: self._set_canvas_color(QColor(col)))
                self.color_group.addButton(btn_c)
                tb_layout.addWidget(btn_c)

            self.btn_custom_color = QToolButton()
            self.btn_custom_color.setText("🎨")
            self.btn_custom_color.setToolTip("Choose custom color")
            self.btn_custom_color.clicked.connect(self._choose_custom_color)
            style_cyber_button(self.btn_custom_color, "prism", compact=True, radius=6)
            tb_layout.addWidget(self.btn_custom_color)

            tb_layout.addWidget(CyberNeonLine(self._cyber_clock, Qt.Vertical, thickness=2, phase_offset=0.5))

            # Stroke Width Selection (stepped neon energy progression)
            self.btn_stroke_thin = QToolButton()
            self.btn_stroke_thin.setText("2px")
            self.btn_stroke_thin.setToolTip("Line width: 2px")
            self.btn_stroke_thin.setCheckable(True)
            self.btn_stroke_thin.clicked.connect(lambda: self._set_stroke_width(2))
            style_cyber_button(self.btn_stroke_thin, "cyan", compact=True, radius=6)
            tb_layout.addWidget(self.btn_stroke_thin)

            self.btn_stroke_med = QToolButton()
            self.btn_stroke_med.setText("4px")
            self.btn_stroke_med.setToolTip("Line width: 4px")
            self.btn_stroke_med.setCheckable(True)
            self.btn_stroke_med.setChecked(True)
            self.btn_stroke_med.clicked.connect(lambda: self._set_stroke_width(4))
            style_cyber_button(self.btn_stroke_med, "emerald", compact=True, radius=6)
            tb_layout.addWidget(self.btn_stroke_med)

            self.btn_stroke_thick = QToolButton()
            self.btn_stroke_thick.setText("8px")
            self.btn_stroke_thick.setToolTip("Line width: 8px")
            self.btn_stroke_thick.setCheckable(True)
            self.btn_stroke_thick.clicked.connect(lambda: self._set_stroke_width(8))
            style_cyber_button(self.btn_stroke_thick, "solar", compact=True, radius=6)
            tb_layout.addWidget(self.btn_stroke_thick)

            self.btn_stroke_xthick = QToolButton()
            self.btn_stroke_xthick.setText("12px")
            self.btn_stroke_xthick.setToolTip("Line width: 12px")
            self.btn_stroke_xthick.setCheckable(True)
            self.btn_stroke_xthick.clicked.connect(lambda: self._set_stroke_width(12))
            style_cyber_button(self.btn_stroke_xthick, "magenta", compact=True, radius=6)
            tb_layout.addWidget(self.btn_stroke_xthick)

            self.stroke_grp = QButtonGroup(self)
            self.stroke_grp.addButton(self.btn_stroke_thin)
            self.stroke_grp.addButton(self.btn_stroke_med)
            self.stroke_grp.addButton(self.btn_stroke_thick)
            self.stroke_grp.addButton(self.btn_stroke_xthick)

            tb_layout.addWidget(CyberNeonLine(self._cyber_clock, Qt.Vertical, thickness=2, phase_offset=0.7))

            # Zoom In / Out / Reset Controls
            self.btn_zoom_out = QToolButton()
            self.btn_zoom_out.setText("➖")
            self.btn_zoom_out.setToolTip("Zoom out (Ctrl+- or Ctrl+Wheel Down)")
            self.btn_zoom_out.clicked.connect(self._on_zoom_out)
            style_cyber_button(self.btn_zoom_out, "indigo", compact=True, radius=6)
            tb_layout.addWidget(self.btn_zoom_out)

            self.lbl_zoom_val = QLabel("100%")
            self.lbl_zoom_val.setToolTip("Current zoom level")
            self.lbl_zoom_val.setStyleSheet(
                "color: #00f0ff; font-family: Consolas, monospace; font-weight: 800; "
                "font-size: 8.5pt; min-width: 38px; padding: 2px 4px; "
                "background: qlineargradient(x1:0, y1:0, x2:1, y2:1, stop:0 #180e3b, stop:1 #0b2442); "
                "border: 1px solid #00f0ff; border-radius: 5px; qproperty-alignment: AlignCenter;"
            )
            tb_layout.addWidget(self.lbl_zoom_val)

            self.btn_zoom_in = QToolButton()
            self.btn_zoom_in.setText("➕")
            self.btn_zoom_in.setToolTip("Zoom in (Ctrl++ or Ctrl+Wheel Up)")
            self.btn_zoom_in.clicked.connect(self._on_zoom_in)
            style_cyber_button(self.btn_zoom_in, "cyan", compact=True, radius=6)
            tb_layout.addWidget(self.btn_zoom_in)

            self.btn_zoom_reset = QToolButton()
            self.btn_zoom_reset.setText("1:1")
            self.btn_zoom_reset.setToolTip("Reset Zoom to 100% (Ctrl+0)")
            self.btn_zoom_reset.clicked.connect(self._on_zoom_reset)
            style_cyber_button(self.btn_zoom_reset, "emerald", compact=True, radius=6)
            tb_layout.addWidget(self.btn_zoom_reset)

            tb_layout.addStretch()

            # History & Window Controls
            self.btn_undo = QPushButton("↺")
            self.btn_undo.setToolTip("Undo last annotation step (Ctrl+Z)")
            self.btn_undo.clicked.connect(self._on_undo)
            style_cyber_button(self.btn_undo, "indigo", compact=True, radius=6)
            tb_layout.addWidget(self.btn_undo)

            self.btn_redo = QPushButton("↻")
            self.btn_redo.setToolTip("Redo undone step (Ctrl+Y)")
            self.btn_redo.clicked.connect(self._on_redo)
            style_cyber_button(self.btn_redo, "violet", compact=True, radius=6)
            tb_layout.addWidget(self.btn_redo)

            self.btn_reset = QPushButton("🔄")
            self.btn_reset.setToolTip("Reset Image — Clear all annotations and restore original image")
            self.btn_reset.clicked.connect(self._on_reset)
            style_cyber_button(self.btn_reset, "crimson", compact=True, radius=6)
            tb_layout.addWidget(self.btn_reset)

            init_max = bool(self.windowState() & Qt.WindowMaximized)
            self.btn_maximize = QPushButton("❐" if init_max else "⛶")
            self.btn_maximize.setToolTip(
                "Restore Image Editor to normal window size (F11 or double-click top bar)"
                if init_max
                else "Toggle full screen (F11 or double-click top bar)"
            )
            self.btn_maximize.clicked.connect(self._toggle_maximize)
            style_cyber_button(self.btn_maximize, "aurora", compact=True, radius=6)
            tb_layout.addWidget(self.btn_maximize)

            self._toolbar_text_buttons = [
                self.btn_tool_select,
                self.btn_tool_pen,
                self.btn_tool_line,
                self.btn_tool_circle,
                self.btn_tool_rect,
                self.btn_tool_text,
                self.btn_rotate_90,
                self.btn_custom_color,
                self.btn_stroke_thin,
                self.btn_stroke_med,
                self.btn_stroke_thick,
                self.btn_stroke_xthick,
                self.btn_zoom_out,
                self.btn_zoom_in,
                self.btn_zoom_reset,
                self.btn_undo,
                self.btn_redo,
                self.btn_reset,
                self.btn_maximize,
            ]

            main_layout.addWidget(toolbar_box)

            # Keyboard shortcuts for tools, undo/redo, zoom, and maximize
            QShortcut(QKeySequence("V"), self, lambda: self.btn_tool_select.click())
            QShortcut(QKeySequence("P"), self, lambda: self.btn_tool_pen.click())
            QShortcut(QKeySequence("L"), self, lambda: self.btn_tool_line.click())
            QShortcut(QKeySequence("C"), self, lambda: self.btn_tool_circle.click())
            QShortcut(QKeySequence("R"), self, lambda: self.btn_tool_rect.click())
            QShortcut(QKeySequence("T"), self, lambda: self.btn_tool_text.click())
            QShortcut(QKeySequence("Ctrl+R"), self, self._on_rotate_90)
            QShortcut(QKeySequence("Ctrl+Z"), self, self._on_undo)
            QShortcut(QKeySequence("Ctrl+Y"), self, self._on_redo)
            QShortcut(QKeySequence("Ctrl+Shift+Z"), self, self._on_redo)
            QShortcut(QKeySequence("Ctrl++"), self, self._on_zoom_in)
            QShortcut(QKeySequence("Ctrl+="), self, self._on_zoom_in)
            QShortcut(QKeySequence("Ctrl+-"), self, self._on_zoom_out)
            QShortcut(QKeySequence("Ctrl+0"), self, self._on_zoom_reset)
            QShortcut(QKeySequence("F11"), self, self._toggle_maximize)

        # 2. Main Body: Cyber Neon Splitter with Canvas (Left) and Futuristic Studio Inspector (Right)
        if self._image and not self._image.isNull():
            body_splitter = CyberNeonSplitter(Qt.Horizontal, self._cyber_clock)

            # Left Canvas (Cyber-Space Holographic Workbench)
            self.canvas = ImageAnnotationCanvas(self._image, self, cyber_clock=self._cyber_clock)
            self.canvas.zoom_changed.connect(self._on_zoom_changed)
            self.canvas.tool_changed.connect(self._sync_toolbar_tool_buttons)
            body_splitter.addWidget(self.canvas)

            # Right Cyber Studio Inspector Sidebar
            side_panel = QFrame()
            side_panel.setObjectName("cyberInspectorPanel")
            side_panel.setFixedWidth(274)
            side_layout = QVBoxLayout(side_panel)
            side_layout.setContentsMargins(6, 0, 0, 0)
            side_layout.setSpacing(8)

            # 2a. Cyber Studio Live HUD Header Card
            hud_card = CyberRainbowBorderFrame(self._cyber_clock, radius=10.0, phase_offset=0.15)
            hud_layout = QVBoxLayout(hud_card)
            hud_layout.setContentsMargins(10, 8, 10, 8)
            hud_layout.setSpacing(4)

            lbl_studio = QLabel("⚡ CYBER NEON STUDIO")
            lbl_studio.setStyleSheet(
                "font-weight: 800; font-size: 10pt; letter-spacing: 1.2px; color: #00f0ff;"
            )
            hud_layout.addWidget(lbl_studio)

            self.lbl_cyber_hud_status = QLabel("✏️ NEON PEN  •  100%")
            self.lbl_cyber_hud_status.setStyleSheet(
                "font-family: Consolas, monospace; font-size: 8.5pt; font-weight: 700; "
                "color: #ff4da6; background: rgba(255, 0, 127, 0.14); "
                "border: 1px solid rgba(255, 77, 166, 0.45); border-radius: 5px; padding: 3px 6px;"
            )
            hud_layout.addWidget(self.lbl_cyber_hud_status)
            side_layout.addWidget(hud_card)

            side_layout.addWidget(CyberNeonLine(self._cyber_clock, Qt.Horizontal, thickness=2, phase_offset=0.25))

            # 2b. Dimensions Control Card
            dim_card = CyberRainbowBorderFrame(self._cyber_clock, radius=10.0, phase_offset=0.45)
            dim_layout = QVBoxLayout(dim_card)
            dim_layout.setContentsMargins(10, 10, 10, 10)
            dim_layout.setSpacing(8)

            lbl_dim_title = QLabel("📐 RESIZE DIMENSIONS")
            lbl_dim_title.setStyleSheet("font-weight: 800; font-size: 9.5pt; letter-spacing: 0.8px; color: #00ff9d;")
            dim_layout.addWidget(lbl_dim_title)

            info_text = f"Original: <b>{self._orig_w} × {self._orig_h} px</b>"
            self.lbl_info = QLabel(info_text)
            self.lbl_info.setStyleSheet("color: #c4b5fd; font-size: 8.5pt;")
            dim_layout.addWidget(self.lbl_info)

            form = QFormLayout()
            form.setSpacing(8)

            self.spin_width = QSpinBox()
            self.spin_width.setRange(20, 5000)
            self.spin_width.setSingleStep(10)
            self.spin_width.setSuffix(" px")
            self.spin_width.setValue(self._curr_w)
            self.spin_width.valueChanged.connect(self._on_width_changed)
            lbl_w = QLabel("Width:")
            lbl_w.setStyleSheet("color: #00f0ff; font-weight: 700;")
            form.addRow(lbl_w, self.spin_width)

            self.spin_height = QSpinBox()
            self.spin_height.setRange(20, 5000)
            self.spin_height.setSingleStep(10)
            self.spin_height.setSuffix(" px")
            self.spin_height.setValue(self._curr_h)
            self.spin_height.valueChanged.connect(self._on_height_changed)
            lbl_h = QLabel("Height:")
            lbl_h.setStyleSheet("color: #ff4da6; font-weight: 700;")
            form.addRow(lbl_h, self.spin_height)
            dim_layout.addLayout(form)

            self.chk_lock_aspect = QCheckBox("🔗 Lock aspect ratio")
            self.chk_lock_aspect.setChecked(True)
            self.chk_lock_aspect.setStyleSheet("color: #e0f2fe; font-size: 9pt; font-weight: 600;")
            dim_layout.addWidget(self.chk_lock_aspect)
            side_layout.addWidget(dim_card)

            side_layout.addWidget(CyberNeonLine(self._cyber_clock, Qt.Horizontal, thickness=2, phase_offset=0.6))

            # 2c. Quick Scale Presets Card
            preset_card = CyberRainbowBorderFrame(self._cyber_clock, radius=10.0, phase_offset=0.75)
            preset_card_layout = QVBoxLayout(preset_card)
            preset_card_layout.setContentsMargins(10, 10, 10, 10)
            preset_card_layout.setSpacing(7)

            lbl_presets = QLabel("🚀 QUICK SCALE PRESETS")
            lbl_presets.setStyleSheet("color: #ffbe0b; font-weight: 800; font-size: 9pt; letter-spacing: 0.8px;")
            preset_card_layout.addWidget(lbl_presets)

            grid_presets = QHBoxLayout()
            grid_presets.setSpacing(5)
            for (label, pct), theme_key in zip(
                [("25%", 0.25), ("50%", 0.50), ("75%", 0.75), ("100%", 1.0)],
                ["cyan", "emerald", "sunset", "magenta"],
            ):
                btn = QPushButton(label)
                btn.setFixedHeight(28)
                style_cyber_button(btn, theme_key, compact=True, radius=6)
                btn.clicked.connect(lambda checked=False, p=pct: self._apply_preset_percentage(p))
                grid_presets.addWidget(btn)
            preset_card_layout.addLayout(grid_presets)

            self.btn_fit_pane = QPushButton("Fit to Pane Width")
            self.btn_fit_pane.setFixedHeight(30)
            self.btn_fit_pane.setToolTip(f"Scales image to fit editor pane (max {self._max_pane_w} px)")
            style_cyber_button(self.btn_fit_pane, "aurora", compact=False, radius=7)
            self.btn_fit_pane.clicked.connect(self._apply_preset_fit_pane)
            preset_card_layout.addWidget(self.btn_fit_pane)
            side_layout.addWidget(preset_card)

            side_layout.addWidget(CyberNeonLine(self._cyber_clock, Qt.Horizontal, thickness=2, phase_offset=0.9))

            # 2d. Futuristic Hotkeys Cheat-Sheet Micro-HUD
            keys_card = CyberRainbowBorderFrame(self._cyber_clock, radius=10.0, phase_offset=0.05, corner_ticks=False)
            keys_layout = QVBoxLayout(keys_card)
            keys_layout.setContentsMargins(10, 8, 10, 8)
            keys_layout.setSpacing(4)

            lbl_keys_hdr = QLabel("⌨️ CYBER SHORTCUTS")
            lbl_keys_hdr.setStyleSheet("color: #c77dff; font-weight: 800; font-size: 8.5pt; letter-spacing: 0.8px;")
            keys_layout.addWidget(lbl_keys_hdr)

            lbl_keys_body = QLabel(
                "<span style='color:#00f0ff'><b>V</b></span> Select • "
                "<span style='color:#ff4da6'><b>P</b></span> Pen • "
                "<span style='color:#ffbe0b'><b>L</b></span> Line<br>"
                "<span style='color:#c77dff'><b>C</b></span> Circle • "
                "<span style='color:#00ff9d'><b>R</b></span> Rect • "
                "<span style='color:#ff7b00'><b>T</b></span> Text<br>"
                "<span style='color:#38bdf8'><b>Ctrl+R</b></span> Rotate • "
                "<span style='color:#f472b6'><b>F11</b></span> Fullscreen"
            )
            lbl_keys_body.setStyleSheet("color: #cbd5e1; font-size: 8pt; line-height: 1.35;")
            keys_layout.addWidget(lbl_keys_body)
            side_layout.addWidget(keys_card)

            side_layout.addStretch()
            body_splitter.addWidget(side_panel)
            body_splitter.setSizes([720, 274])
            main_layout.addWidget(body_splitter, 1)

        else:
            # Standalone Cyber-Neon Dimensions View (Fallback when no QImage instance provided)
            header_frame = CyberRainbowBorderFrame(self._cyber_clock, radius=10.0, phase_offset=0.1)
            header_layout = QVBoxLayout(header_frame)
            header_layout.setContentsMargins(12, 10, 12, 10)
            header_layout.setSpacing(4)

            lbl_title = QLabel("📐 CYBER IMAGE RESIZER")
            lbl_title.setStyleSheet("font-weight: 800; font-size: 11pt; letter-spacing: 1px; color: #00f0ff;")
            header_layout.addWidget(lbl_title)

            info_text = f"Original Size: <b>{self._orig_w} × {self._orig_h} px</b> | Current: <b>{self._curr_w} × {self._curr_h} px</b>"
            self.lbl_info = QLabel(info_text)
            self.lbl_info.setStyleSheet("color: #f472b6; font-size: 9pt;")
            header_layout.addWidget(self.lbl_info)
            main_layout.addWidget(header_frame)

            main_layout.addWidget(CyberNeonLine(self._cyber_clock, Qt.Horizontal, thickness=2, phase_offset=0.35))

            form_card = CyberRainbowBorderFrame(self._cyber_clock, radius=10.0, phase_offset=0.5)
            form_card_layout = QVBoxLayout(form_card)
            form_card_layout.setContentsMargins(12, 10, 12, 10)
            form_card_layout.setSpacing(8)

            form = QFormLayout()
            form.setSpacing(10)

            self.spin_width = QSpinBox()
            self.spin_width.setRange(20, 5000)
            self.spin_width.setSingleStep(10)
            self.spin_width.setSuffix(" px")
            self.spin_width.setValue(self._curr_w)
            self.spin_width.valueChanged.connect(self._on_width_changed)
            lbl_w = QLabel("Width:")
            lbl_w.setStyleSheet("color: #00f0ff; font-weight: 700;")
            form.addRow(lbl_w, self.spin_width)

            self.spin_height = QSpinBox()
            self.spin_height.setRange(20, 5000)
            self.spin_height.setSingleStep(10)
            self.spin_height.setSuffix(" px")
            self.spin_height.setValue(self._curr_h)
            self.spin_height.valueChanged.connect(self._on_height_changed)
            lbl_h = QLabel("Height:")
            lbl_h.setStyleSheet("color: #ff4da6; font-weight: 700;")
            form.addRow(lbl_h, self.spin_height)
            form_card_layout.addLayout(form)

            self.chk_lock_aspect = QCheckBox("🔗 Lock aspect ratio")
            self.chk_lock_aspect.setChecked(True)
            self.chk_lock_aspect.setStyleSheet("color: #e0f2fe; font-size: 9pt; font-weight: 600;")
            form_card_layout.addWidget(self.chk_lock_aspect)
            main_layout.addWidget(form_card)

            preset_box = CyberRainbowBorderFrame(self._cyber_clock, radius=10.0, phase_offset=0.8)
            preset_layout = QVBoxLayout(preset_box)
            preset_layout.setContentsMargins(12, 10, 12, 10)
            preset_layout.setSpacing(6)

            lbl_presets = QLabel("🚀 QUICK SCALE PRESETS")
            lbl_presets.setStyleSheet("color: #ffbe0b; font-weight: 800; font-size: 9pt; letter-spacing: 0.8px;")
            preset_layout.addWidget(lbl_presets)

            presets_row = QHBoxLayout()
            presets_row.setSpacing(6)

            for (label, pct), theme_key in zip(
                [("25%", 0.25), ("50%", 0.50), ("75%", 0.75), ("100%", 1.0)],
                ["cyan", "emerald", "sunset", "magenta"],
            ):
                btn = QPushButton(label)
                btn.setFixedHeight(28)
                style_cyber_button(btn, theme_key, compact=True, radius=6)
                btn.clicked.connect(lambda checked=False, p=pct: self._apply_preset_percentage(p))
                presets_row.addWidget(btn)

            self.btn_fit_pane = QPushButton("Fit to Pane Width")
            self.btn_fit_pane.setFixedHeight(28)
            self.btn_fit_pane.setToolTip(f"Scales image to fit editor pane (max {self._max_pane_w} px)")
            style_cyber_button(self.btn_fit_pane, "aurora", compact=True, radius=6)
            self.btn_fit_pane.clicked.connect(self._apply_preset_fit_pane)
            presets_row.addWidget(self.btn_fit_pane)

            preset_layout.addLayout(presets_row)
            main_layout.addWidget(preset_box)

        # 3. Bottom Cyber Action Bar
        bottom_bar = CyberRainbowBorderFrame(self._cyber_clock, radius=9.0, phase_offset=0.55, corner_ticks=False)
        bottom_bar.setObjectName("cyberBottomBar")
        bottom_layout = QHBoxLayout(bottom_bar)
        bottom_layout.setContentsMargins(12, 6, 12, 6)
        bottom_layout.setSpacing(10)

        lbl_footer_tip = QLabel("✨ Cyber Neon Studio  •  Drag: Draw/Move  •  Right-Drag: Pan  •  Ctrl+Scroll: Zoom")
        lbl_footer_tip.setStyleSheet("color: #a5b4fc; font-size: 8.5pt; font-weight: 600;")
        if self._image and not self._image.isNull():
            bottom_layout.addWidget(lbl_footer_tip)
            bottom_layout.addStretch()

        self.button_box = QDialogButtonBox(QDialogButtonBox.Ok | QDialogButtonBox.Cancel)
        self.button_box.accepted.connect(self.accept)
        self.button_box.rejected.connect(self.reject)
        ok_btn = self.button_box.button(QDialogButtonBox.Ok)
        cancel_btn = self.button_box.button(QDialogButtonBox.Cancel)
        if ok_btn:
            style_cyber_button(ok_btn, "emerald", compact=False, radius=7)
        if cancel_btn:
            style_cyber_button(cancel_btn, "crimson", compact=False, radius=7)
        bottom_layout.addWidget(self.button_box)
        main_layout.addWidget(bottom_bar)

        # Install full rainbow glow + input halos + shiny click-sweep effects across the Image Editor
        apply_glow_to_buttons([self])
        apply_glow_to_inputs([self])
        install_cyber_input_halos([self], self._cyber_clock)
        apply_cyber_click_shine([self])

    def showEvent(self, event) -> None:
        super().showEvent(event)
        if not self._has_shown:
            self._has_shown = True
            if self._image and not self._image.isNull():
                self.setWindowState(self.windowState() | Qt.WindowMaximized)
                if hasattr(self, "btn_maximize"):
                    self.btn_maximize.setText("❐")
                    self.btn_maximize.setToolTip("Restore Image Editor to normal window size (F11 or double-click top bar)")
            animate_dialog_show(self)

    def changeEvent(self, event) -> None:
        super().changeEvent(event)
        if hasattr(self, "btn_maximize"):
            if self.isMaximized() or bool(self.windowState() & Qt.WindowMaximized):
                self.btn_maximize.setText("❐")
                self.btn_maximize.setToolTip("Restore Image Editor to normal window size (F11 or double-click top bar)")
            else:
                self.btn_maximize.setText("⛶")
                self.btn_maximize.setToolTip("Maximize Image Editor to full screen (F11 or double-click top bar)")

    def _toggle_maximize(self) -> None:
        """Toggles window between maximized (full screen) and normal restored geometry."""
        if self.isMaximized() or bool(self.windowState() & Qt.WindowMaximized):
            self.setWindowState(self.windowState() & ~Qt.WindowMaximized)
            if self.isVisible():
                self.showNormal()
            if hasattr(self, "btn_maximize"):
                self.btn_maximize.setText("⛶")
                self.btn_maximize.setToolTip("Maximize Image Editor to full screen (F11 or double-click top bar)")
        else:
            self.setWindowState(self.windowState() | Qt.WindowMaximized)
            if self.isVisible():
                self.showMaximized()
            if hasattr(self, "btn_maximize"):
                self.btn_maximize.setText("❐")
                self.btn_maximize.setToolTip("Restore Image Editor to normal window size (F11 or double-click top bar)")

    def _set_canvas_tool(self, tool_name: str) -> None:
        if self.canvas:
            self.canvas.set_tool(tool_name)

    def _set_canvas_color(self, color: QColor) -> None:
        if self.canvas:
            self.canvas.set_color(color)

    def _choose_custom_color(self) -> None:
        if not self.canvas:
            return
        initial = self.canvas._current_color
        chosen = QColorDialog.getColor(initial, self, "Choose Custom Annotation Color")
        if chosen.isValid():
            self._set_canvas_color(chosen)

    def _set_stroke_width(self, width: int) -> None:
        if self.canvas:
            self.canvas.set_stroke_width(width)

    def _on_font_size_changed(self, size: int) -> None:
        if self.canvas:
            self.canvas.set_font_size(size)

    def _on_zoom_in(self) -> None:
        if self.canvas:
            self.canvas.zoom_in()

    def _on_zoom_out(self) -> None:
        if self.canvas:
            self.canvas.zoom_out()

    def _on_zoom_reset(self) -> None:
        if self.canvas:
            self.canvas.reset_zoom()

    def _on_zoom_changed(self, factor: float) -> None:
        pct = int(round(factor * 100))
        if hasattr(self, "lbl_zoom_val"):
            self.lbl_zoom_val.setText(f"{pct}%")
        self._update_cyber_hud_status()

    def _on_undo(self) -> None:
        if self.canvas:
            self.canvas.undo()
            self._update_cyber_hud_status()

    def _on_redo(self) -> None:
        if self.canvas:
            self.canvas.redo()
            self._update_cyber_hud_status()

    def _on_reset(self) -> None:
        if self.canvas:
            self.canvas.reset_image()
            self._update_cyber_hud_status()

    def _on_rotate_90(self) -> None:
        if self.canvas:
            self.canvas.rotate_selected_item(90.0)

    def _update_cyber_hud_status(self, tool_name: Optional[str] = None) -> None:
        """Refreshes the glowing Cyber Studio HUD badge with active tool & zoom telemetry."""
        if not hasattr(self, "lbl_cyber_hud_status"):
            return
        active_tool = tool_name or (self.canvas._active_tool if self.canvas else ImageAnnotationCanvas.TOOL_PEN)
        label, accent = self._TOOL_HUD_LABELS.get(active_tool, ("✏️ NEON PEN", "#ff4da6"))
        zoom_pct = int(round(self.canvas.get_zoom_factor() * 100)) if self.canvas else 100
        self.lbl_cyber_hud_status.setText(f"{label}  •  {zoom_pct}%")
        col = QColor(accent)
        self.lbl_cyber_hud_status.setStyleSheet(
            f"font-family: Consolas, monospace; font-size: 8.5pt; font-weight: 700; "
            f"color: {accent}; background: rgba({col.red()}, {col.green()}, {col.blue()}, 0.16); "
            f"border: 1px solid rgba({col.red()}, {col.green()}, {col.blue()}, 0.65); "
            f"border-radius: 5px; padding: 3px 6px;"
        )

    def _sync_toolbar_tool_buttons(self, tool_name: str) -> None:
        if not hasattr(self, "btn_tool_select"):
            return
        if tool_name == ImageAnnotationCanvas.TOOL_SELECT:
            self.btn_tool_select.setChecked(True)
        elif tool_name == ImageAnnotationCanvas.TOOL_PEN:
            self.btn_tool_pen.setChecked(True)
        elif tool_name == ImageAnnotationCanvas.TOOL_LINE:
            self.btn_tool_line.setChecked(True)
        elif tool_name == ImageAnnotationCanvas.TOOL_CIRCLE:
            self.btn_tool_circle.setChecked(True)
        elif tool_name == ImageAnnotationCanvas.TOOL_RECTANGLE:
            self.btn_tool_rect.setChecked(True)
        elif tool_name == ImageAnnotationCanvas.TOOL_TEXT:
            self.btn_tool_text.setChecked(True)
        self._update_cyber_hud_status(tool_name)

    def _apply_styling(self) -> None:
        self.setStyleSheet("""
            QDialog {
                background-color: #050311;
                color: #f1f5f9;
            }
            QLabel {
                color: #e2e8f0;
                background: transparent;
            }
            QFrame#cyberInspectorPanel {
                background: transparent;
                border: none;
            }
            QFrame#annotationToolbar {
                background: transparent;
                border: none;
            }
            QSpinBox {
                background: qlineargradient(
                    x1: 0, y1: 0, x2: 1, y2: 1,
                    stop: 0 #31126b,
                    stop: 0.45 #0e3163,
                    stop: 1 #520f5e
                );
                color: #7df9ff;
                font-weight: 700;
                font-family: Consolas, 'Segoe UI', monospace;
                border: 2px solid transparent;
                border-radius: 6px;
                padding: 4px 8px;
                selection-background-color: #ff007f;
                selection-color: #ffffff;
            }
            QSpinBox:hover {
                background: qlineargradient(
                    x1: 0, y1: 0, x2: 1, y2: 1,
                    stop: 0 #3f1885,
                    stop: 0.5 #113e7d,
                    stop: 1 #661475
                );
                color: #ffffff;
            }
            QSpinBox:focus {
                background: qlineargradient(
                    x1: 0, y1: 0, x2: 1, y2: 1,
                    stop: 0 #4d1ca3,
                    stop: 0.5 #134a94,
                    stop: 1 #7a188c
                );
                color: #ffffff;
            }
            QSpinBox::up-button, QSpinBox::down-button {
                background: qlineargradient(
                    x1: 0, y1: 0, x2: 0, y2: 1,
                    stop: 0 #ff007f,
                    stop: 1 #4361ee
                );
                border: none;
                border-radius: 3px;
                width: 16px;
                margin: 1px;
            }
            QSpinBox::up-button:hover, QSpinBox::down-button:hover {
                background: qlineargradient(
                    x1: 0, y1: 0, x2: 0, y2: 1,
                    stop: 0 #00f0ff,
                    stop: 1 #ff00e5
                );
            }
            QSpinBox::up-arrow, QSpinBox::down-arrow {
                image: none;
                width: 0px;
                height: 0px;
            }
            QFrame#annotationToolbar QSpinBox {
                padding: 3px 5px;
                font-size: 8.5pt;
            }
            QCheckBox {
                color: #e0f2fe;
                spacing: 7px;
                background: transparent;
            }
            QCheckBox::indicator {
                width: 16px;
                height: 16px;
                border-radius: 4px;
                border: 1.5px solid #00f0ff;
                background: #120b2c;
            }
            QCheckBox::indicator:hover {
                border-color: #ff00e5;
            }
            QCheckBox::indicator:checked {
                background: qlineargradient(
                    x1: 0, y1: 0, x2: 1, y2: 1,
                    stop: 0 #ff007f,
                    stop: 0.5 #9d4edd,
                    stop: 1 #00f0ff
                );
                border-color: #ffffff;
            }
            QToolTip {
                background-color: #0e0826;
                color: #ffffff;
                border: 1.5px solid #00f0ff;
                border-radius: 6px;
                padding: 5px 8px;
            }
        """)
        for btn in getattr(self, "_toolbar_text_buttons", []):
            btn.setMinimumWidth(btn.sizeHint().width())

    def _on_width_changed(self, new_w: int) -> None:
        if self._updating or not self.chk_lock_aspect.isChecked():
            return
        self._updating = True
        try:
            new_h = max(20, int(round(new_w / self._aspect_ratio)))
            self.spin_height.setValue(new_h)
        finally:
            self._updating = False

    def _on_height_changed(self, new_h: int) -> None:
        if self._updating or not self.chk_lock_aspect.isChecked():
            return
        self._updating = True
        try:
            new_w = max(20, int(round(new_h * self._aspect_ratio)))
            self.spin_width.setValue(new_w)
        finally:
            self._updating = False

    def _apply_preset_percentage(self, pct: float) -> None:
        self._updating = True
        try:
            new_w = max(20, int(round(self._orig_w * pct)))
            new_h = max(20, int(round(self._orig_h * pct)))
            self.spin_width.setValue(new_w)
            self.spin_height.setValue(new_h)
        finally:
            self._updating = False

    def _apply_preset_fit_pane(self) -> None:
        self._updating = True
        try:
            target_w = max(50, min(self._orig_w, self._max_pane_w))
            target_h = max(20, int(round(target_w / self._aspect_ratio)))
            self.spin_width.setValue(target_w)
            self.spin_height.setValue(target_h)
        finally:
            self._updating = False

    def get_dimensions(self) -> Tuple[int, int]:
        """Returns the configured (width, height) in pixels."""
        return self.spin_width.value(), self.spin_height.value()

    def was_image_annotated(self) -> bool:
        """Returns True if user made drawings, shapes, or text modifications on the canvas."""
        return self.canvas.was_annotated() if self.canvas else False

    def get_annotated_image(self) -> Optional[QImage]:
        """Returns the modified QImage with baked-in annotations, or None."""
        return self.canvas.get_annotated_image() if self.canvas else None


# Backward-compatible alias for modern naming
ImageEditorDialog = ResizeImageDialog
