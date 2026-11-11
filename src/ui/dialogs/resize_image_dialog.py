"""Modal dialog for resizing and annotating embedded images with drawing, shapes, text, zoom, move, and undo/redo."""

import math
from typing import Optional, Tuple
from PySide6.QtCore import QPoint, QPointF, QRect, QRectF, Qt, Signal
from PySide6.QtGui import (
    QColor,
    QFont,
    QFontMetrics,
    QImage,
    QKeySequence,
    QMouseEvent,
    QPaintEvent,
    QPainter,
    QPen,
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
from src.ui.components.glow_effect import apply_glow_to_buttons


class DoubleClickableFrame(QFrame):
    """Toolbar frame that emits double_clicked when double-clicking on empty areas."""

    double_clicked = Signal()

    def mouseDoubleClickEvent(self, event: QMouseEvent) -> None:
        if event.button() == Qt.LeftButton:
            self.double_clicked.emit()
            event.accept()
            return
        super().mouseDoubleClickEvent(event)


class TextAnnotationDialog(QDialog):
    """Dialog allowing technicians to write text, choose font size, and set border options."""

    def __init__(
        self,
        rect: QRect,
        font_size: int = 18,
        color: QColor = QColor("#ff3b30"),
        parent: Optional[QWidget] = None,
    ):
        super().__init__(parent)
        self.setWindowTitle("Add Text to Image")
        self.resize(380, 240)
        self.setModal(True)
        self._setup_ui(rect, font_size, color)

    def _setup_ui(self, rect: QRect, font_size: int, color: QColor) -> None:
        layout = QVBoxLayout(self)
        layout.setSpacing(8)
        layout.setContentsMargins(12, 12, 12, 12)

        info_lbl = QLabel(f"Text Box: <b>{rect.width()} × {rect.height()} px</b> at ({rect.x()}, {rect.y()})")
        info_lbl.setStyleSheet("color: #888888; font-size: 8.5pt;")
        layout.addWidget(info_lbl)

        self.text_edit = QTextEdit()
        self.text_edit.setPlaceholderText("Type text to place inside rectangle (multi-line supported)...")
        self.text_edit.setAcceptRichText(False)
        self.text_edit.setStyleSheet("""
            QTextEdit {
                background-color: #1e1e1e;
                color: #ffffff;
                border: 1px solid #3c3c3c;
                border-radius: 4px;
                padding: 6px;
                font-family: Arial, sans-serif;
                font-size: 10pt;
            }
            QTextEdit:focus {
                border-color: #007acc;
            }
        """)
        layout.addWidget(self.text_edit, 1)

        opts_row = QHBoxLayout()
        opts_row.setSpacing(8)

        lbl_size = QLabel("Font Size:")
        lbl_size.setStyleSheet("color: #9cdcfe; font-weight: bold;")
        opts_row.addWidget(lbl_size)

        self.spin_size = QSpinBox()
        self.spin_size.setRange(8, 96)
        self.spin_size.setValue(font_size)
        self.spin_size.setSuffix(" pt")
        opts_row.addWidget(self.spin_size)

        self.chk_border = QCheckBox("🔲 Draw Callout Box")
        self.chk_border.setChecked(False)
        self.chk_border.setToolTip("Draw rounded border box and dark background behind text")
        self.chk_border.setStyleSheet("color: #cccccc;")
        opts_row.addWidget(self.chk_border)

        opts_row.addStretch()
        layout.addLayout(opts_row)

        btn_box = QDialogButtonBox(QDialogButtonBox.Ok | QDialogButtonBox.Cancel)
        btn_box.accepted.connect(self.accept)
        btn_box.rejected.connect(self.reject)
        layout.addWidget(btn_box)

        self.setStyleSheet("""
            QDialog {
                background-color: #252526;
                color: #cccccc;
            }
            QLabel {
                color: #cccccc;
            }
            QSpinBox {
                background-color: #1e1e1e;
                color: #cccccc;
                border: 1px solid #3c3c3c;
                border-radius: 4px;
                padding: 3px 6px;
            }
            QPushButton {
                background-color: #333333;
                color: #cccccc;
                border: 1px solid #3c3c3c;
                border-radius: 4px;
                padding: 4px 12px;
            }
            QPushButton:hover {
                background-color: #3e3e42;
                border-color: #007acc;
                color: #ffffff;
            }
        """)

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

    def __init__(self, image: QImage, parent: Optional[QWidget] = None):
        super().__init__(parent)
        self.setMinimumSize(420, 320)
        self.setMouseTracking(True)
        self.setFocusPolicy(Qt.StrongFocus)
        self.setCursor(Qt.CrossCursor)

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

    def get_selection_handle_at(self, vp_pos: QPoint) -> tuple[int, Optional[AnnotationItem]]:
        """Hit-tests the active selected item to determine if vp_pos touches rotation handle, corners, edges, or body."""
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

        # 3. Edges of the rectangle (8px margin around perimeter for easy moving)
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

        # 4. Inside the body
        if local_box.contains(local_x, local_y):
            return (self.HANDLE_BODY, self._selected_item)

        return (self.HANDLE_NONE, None)

    # -- Painting & Mouse Handlers ---------------------------------------------
    def paintEvent(self, event: QPaintEvent) -> None:
        painter = QPainter(self)
        painter.setRenderHint(QPainter.Antialiasing)
        painter.setRenderHint(QPainter.SmoothPixmapTransform)

        # Background canvas frame
        painter.fillRect(self.rect(), QColor("#1e1e1e"))

        rect = self.get_image_display_rect()
        if rect.isValid() and not self._current_image.isNull():
            # 1. Render baked working image
            painter.drawImage(rect, self._current_image)

            # 2. Image frame border
            painter.setPen(QPen(QColor("#3c3c3c"), 1))
            painter.drawRect(rect)

            scale_x = rect.width() / self._current_image.width()
            scale_y = rect.height() / self._current_image.height()

            # 3. Selection outline, rotation handle, corners, and edges around selected item
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

                # Dashed selection outline with accent tint
                sel_pen = QPen(QColor("#007acc"), 1.5, Qt.DashLine)
                painter.setPen(sel_pen)
                painter.setBrush(QColor(0, 122, 204, 35))
                painter.drawRect(local_box)

                # Rotation stem and handle
                stem_top = local_box.top() - 24.0
                painter.setPen(QPen(QColor("#007acc"), 1.5, Qt.SolidLine))
                painter.drawLine(QPointF(0.0, local_box.top()), QPointF(0.0, stem_top))

                # Circular rotation handle
                painter.setBrush(QColor("#00e5ff"))
                painter.setPen(QPen(QColor("#ffffff"), 1.5))
                painter.drawEllipse(QPointF(0.0, stem_top), 5.5, 5.5)

                # Corner grab handles
                painter.setBrush(QColor("#ffffff"))
                painter.setPen(QPen(QColor("#007acc"), 1.5))
                h_size = 7.0
                for hx, hy in (
                    (local_box.left(), local_box.top()),
                    (local_box.right(), local_box.top()),
                    (local_box.left(), local_box.bottom()),
                    (local_box.right(), local_box.bottom()),
                ):
                    painter.drawRect(QRectF(hx - h_size / 2.0, hy - h_size / 2.0, h_size, h_size))

                # Edge mid-handles
                painter.setBrush(QColor("#ffffff"))
                painter.setPen(QPen(QColor("#007acc"), 1.0))
                m_size = 5.0
                for hx, hy in (
                    (0.0, local_box.top()),
                    (0.0, local_box.bottom()),
                    (local_box.left(), 0.0),
                    (local_box.right(), 0.0),
                ):
                    painter.drawRect(QRectF(hx - m_size / 2.0, hy - m_size / 2.0, m_size, m_size))

                painter.restore()

                # Live angle badge when rotating
                if self._is_rotating:
                    angle_deg = int(round(self._selected_item.rotation)) % 360
                    badge_text = f"⟳ {angle_deg}°"
                    if self._shift_pressed:
                        badge_text += " (Snap 15°)"
                    painter.setFont(QFont("Arial", 9, QFont.Bold))
                    fm = QFontMetrics(painter.font())
                    tw = fm.horizontalAdvance(badge_text) + 16
                    th = fm.height() + 8
                    badge_rect = QRectF(center_x - tw / 2.0, center_y - vp_h / 2.0 - 55.0, tw, th)
                    painter.setBrush(QColor(0, 0, 0, 200))
                    painter.setPen(QPen(QColor("#00e5ff"), 1.5))
                    painter.drawRoundedRect(badge_rect, 4.0, 4.0)
                    painter.setPen(QColor("#ffffff"))
                    painter.drawText(badge_rect, Qt.AlignCenter, badge_text)

            # 4. Interactive shape drag preview overlay
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

                if self._active_tool == self.TOOL_LINE:
                    line_pen = QPen(self._current_color, max(1, int(self._stroke_width * scale_x)), Qt.SolidLine, Qt.RoundCap, Qt.RoundJoin)
                    painter.setPen(line_pen)
                    painter.drawLine(vp_start, vp_curr)
                elif self._active_tool == self.TOOL_RECTANGLE:
                    preview_pen = QPen(self._current_color, max(1, int(self._stroke_width * scale_x)), Qt.SolidLine)
                    painter.setPen(preview_pen)
                    painter.setBrush(Qt.NoBrush)
                    painter.drawRect(preview_rect)
                elif self._active_tool == self.TOOL_CIRCLE:
                    preview_pen = QPen(self._current_color, max(1, int(self._stroke_width * scale_x)), Qt.SolidLine)
                    painter.setPen(preview_pen)
                    painter.setBrush(Qt.NoBrush)
                    painter.drawEllipse(preview_rect)
                elif self._active_tool == self.TOOL_TEXT:
                    dash_pen = QPen(self._current_color, 1, Qt.DashLine)
                    painter.setPen(dash_pen)
                    painter.setBrush(QColor(self._current_color.red(), self._current_color.green(), self._current_color.blue(), 25))
                    painter.drawRect(preview_rect)
                    painter.setPen(self._current_color)
                    font_preview = QFont("Arial", max(8, int(self._font_size * scale_x)))
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
        img_pt = self.viewport_to_image_coords(pos)
        if not img_pt:
            return

        # 2. Check if clicking on active handle of currently selected item
        handle, item = self.get_selection_handle_at(pos)
        if item and handle != self.HANDLE_NONE:
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
                self.setCursor(Qt.PointingHandCursor)
                event.accept()
                return

            # Handle corner resizing
            elif handle in (self.HANDLE_CORNER_TL, self.HANDLE_CORNER_TR, self.HANDLE_CORNER_BR, self.HANDLE_CORNER_BL):
                self._save_undo_state()
                self._action_mode = self.ACTION_RESIZE
                self._is_resizing = True
                self._resize_handle = handle
                self._resize_initial_rect = QRect(item.rect)
                self._resize_initial_pos = img_pt
                self._resize_initial_center = QPointF(item.get_bounding_rect().center())
                event.accept()
                return

            # Handle edge clicking or body clicking -> MOVE!
            elif handle in (
                self.HANDLE_EDGE_TOP,
                self.HANDLE_EDGE_BOTTOM,
                self.HANDLE_EDGE_LEFT,
                self.HANDLE_EDGE_RIGHT,
                self.HANDLE_BODY,
            ):
                self._save_undo_state()
                self._action_mode = self.ACTION_MOVE
                self._is_moving_item = True
                self._move_item_start = img_pt
                self._move_item_prev = img_pt
                self.setCursor(Qt.SizeAllCursor)
                event.accept()
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
        if self._action_mode == self.ACTION_RESIZE and self._selected_item:
            img_pt = self.viewport_to_image_coords(pos, clamp=True)
            if img_pt and self._selected_item.rect.isValid():
                center = self._resize_initial_center
                rot = self._selected_item.rotation
                p_curr = self._unrotate_pt(img_pt, center, rot)
                p_start = self._unrotate_pt(self._resize_initial_pos, center, rot)
                dx = int(p_curr.x() - p_start.x())
                dy = int(p_curr.y() - p_start.y())

                init_r = self._resize_initial_rect
                min_s = 20
                if self._resize_handle == self.HANDLE_CORNER_BR:
                    nw = max(min_s, init_r.width() + dx)
                    nh = max(min_s, init_r.height() + dy)
                    self._selected_item.rect = QRect(init_r.left(), init_r.top(), nw, nh)
                elif self._resize_handle == self.HANDLE_CORNER_TL:
                    nl = min(init_r.right() - min_s, init_r.left() + dx)
                    nt = min(init_r.bottom() - min_s, init_r.top() + dy)
                    self._selected_item.rect = QRect(nl, nt, init_r.right() - nl, init_r.bottom() - nt)
                elif self._resize_handle == self.HANDLE_CORNER_TR:
                    nr = max(init_r.left() + min_s, init_r.right() + dx)
                    nt = min(init_r.bottom() - min_s, init_r.top() + dy)
                    self._selected_item.rect = QRect(init_r.left(), nt, nr - init_r.left(), init_r.bottom() - nt)
                elif self._resize_handle == self.HANDLE_CORNER_BL:
                    nl = min(init_r.right() - min_s, init_r.left() + dx)
                    nb = max(init_r.top() + min_s, init_r.bottom() + dy)
                    self._selected_item.rect = QRect(nl, init_r.top(), init_r.right() - nl, nb - init_r.top())

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
            if handle == self.HANDLE_ROTATE:
                self.setCursor(Qt.PointingHandCursor)
            elif handle in (self.HANDLE_CORNER_TL, self.HANDLE_CORNER_BR):
                self.setCursor(Qt.SizeFDiagCursor)
            elif handle in (self.HANDLE_CORNER_TR, self.HANDLE_CORNER_BL):
                self.setCursor(Qt.SizeBDiagCursor)
            elif handle in (
                self.HANDLE_EDGE_TOP,
                self.HANDLE_EDGE_BOTTOM,
                self.HANDLE_EDGE_LEFT,
                self.HANDLE_EDGE_RIGHT,
                self.HANDLE_BODY,
            ):
                self.setCursor(Qt.SizeAllCursor)
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
    """Dialog allowing technicians to resize an image, apply/move drawings/shapes/text, zoom, and maximize."""

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

        if self._image and not self._image.isNull():
            self.resize(1020, 680)
            self.setMinimumSize(820, 520)
            self.setWindowState(self.windowState() | Qt.WindowMaximized)
        else:
            self.setMinimumWidth(380)

        self._setup_ui()
        self._apply_styling()

    def _setup_ui(self) -> None:
        main_layout = QVBoxLayout(self)
        main_layout.setSpacing(10)
        main_layout.setContentsMargins(14, 12, 14, 12)

        # 1. Top Annotation Toolbar (if image is available)
        if self._image and not self._image.isNull():
            toolbar_box = DoubleClickableFrame()
            toolbar_box.setObjectName("annotationToolbar")
            toolbar_box.double_clicked.connect(self._toggle_maximize)
            toolbar_box.setToolTip("Double-click top bar to toggle full screen")

            tb_layout = QHBoxLayout(toolbar_box)
            tb_layout.setContentsMargins(6, 4, 6, 4)
            tb_layout.setSpacing(6)

            # Tool Selection Buttons
            self.tool_group = QButtonGroup(self)
            self.tool_group.setExclusive(True)

            self.btn_tool_select = QToolButton()
            self.btn_tool_select.setText("↖️ Select / Move")
            self.btn_tool_select.setCheckable(True)
            self.btn_tool_select.setToolTip("Select and drag to move text, shapes, or drawings (Delete to remove)")
            self.btn_tool_select.clicked.connect(lambda: self._set_canvas_tool(ImageAnnotationCanvas.TOOL_SELECT))
            self.tool_group.addButton(self.btn_tool_select)
            tb_layout.addWidget(self.btn_tool_select)

            self.btn_tool_pen = QToolButton()
            self.btn_tool_pen.setText("✏️ Draw")
            self.btn_tool_pen.setCheckable(True)
            self.btn_tool_pen.setChecked(True)
            self.btn_tool_pen.setToolTip("Freehand drawing pen")
            self.btn_tool_pen.clicked.connect(lambda: self._set_canvas_tool(ImageAnnotationCanvas.TOOL_PEN))
            self.tool_group.addButton(self.btn_tool_pen)
            tb_layout.addWidget(self.btn_tool_pen)

            self.btn_tool_line = QToolButton()
            self.btn_tool_line.setText("📏 Line")
            self.btn_tool_line.setCheckable(True)
            self.btn_tool_line.setToolTip("Draw straight line (Hold Shift for straight horizontal, vertical, or 45° snap)")
            self.btn_tool_line.clicked.connect(lambda: self._set_canvas_tool(ImageAnnotationCanvas.TOOL_LINE))
            self.tool_group.addButton(self.btn_tool_line)
            tb_layout.addWidget(self.btn_tool_line)

            self.btn_tool_circle = QToolButton()
            self.btn_tool_circle.setText("⭕ Circle")
            self.btn_tool_circle.setCheckable(True)
            self.btn_tool_circle.setToolTip("Draw circle or ellipse callout")
            self.btn_tool_circle.clicked.connect(lambda: self._set_canvas_tool(ImageAnnotationCanvas.TOOL_CIRCLE))
            self.tool_group.addButton(self.btn_tool_circle)
            tb_layout.addWidget(self.btn_tool_circle)

            self.btn_tool_rect = QToolButton()
            self.btn_tool_rect.setText("🔲 Rectangle")
            self.btn_tool_rect.setCheckable(True)
            self.btn_tool_rect.setToolTip("Draw rectangle callout box")
            self.btn_tool_rect.clicked.connect(lambda: self._set_canvas_tool(ImageAnnotationCanvas.TOOL_RECTANGLE))
            self.tool_group.addButton(self.btn_tool_rect)
            tb_layout.addWidget(self.btn_tool_rect)

            self.btn_tool_text = QToolButton()
            self.btn_tool_text.setText("🔤 Text")
            self.btn_tool_text.setCheckable(True)
            self.btn_tool_text.setToolTip("Click and drag rectangle on image to add custom text (Paint style)")
            self.btn_tool_text.clicked.connect(lambda: self._set_canvas_tool(ImageAnnotationCanvas.TOOL_TEXT))
            self.tool_group.addButton(self.btn_tool_text)
            tb_layout.addWidget(self.btn_tool_text)

            self.btn_rotate_90 = QToolButton()
            self.btn_rotate_90.setText("⟳ Rotate 90°")
            self.btn_rotate_90.setToolTip("Rotate selected form or text 90° clockwise (Ctrl+R)")
            self.btn_rotate_90.clicked.connect(self._on_rotate_90)
            tb_layout.addWidget(self.btn_rotate_90)

            tb_layout.addSpacing(6)

            # Font Size Selector for Text
            lbl_font = QLabel("Font:")
            lbl_font.setStyleSheet("color: #9cdcfe; font-weight: bold;")
            tb_layout.addWidget(lbl_font)

            self.spin_font_size = QSpinBox()
            self.spin_font_size.setRange(8, 96)
            self.spin_font_size.setValue(18)
            self.spin_font_size.setSuffix(" pt")
            self.spin_font_size.setToolTip("Font size for text overlay (8 to 96 pt)")
            self.spin_font_size.valueChanged.connect(self._on_font_size_changed)
            tb_layout.addWidget(self.spin_font_size)

            tb_layout.addSpacing(6)

            # Color Swatches Palette
            lbl_color = QLabel("Color:")
            lbl_color.setStyleSheet("color: #9cdcfe; font-weight: bold;")
            tb_layout.addWidget(lbl_color)

            self.color_group = QButtonGroup(self)
            self.color_group.setExclusive(True)

            for hex_color, name in ImageAnnotationCanvas.COLOR_PALETTE:
                btn_c = QToolButton()
                btn_c.setFixedSize(22, 22)
                btn_c.setCheckable(True)
                btn_c.setToolTip(f"{name} ({hex_color})")
                btn_c.setStyleSheet(f"""
                    QToolButton {{
                        background-color: {hex_color};
                        border: 2px solid #3c3c3c;
                        border-radius: 11px;
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
            self.btn_custom_color.setText("🎨 More...")
            self.btn_custom_color.setToolTip("Choose custom color")
            self.btn_custom_color.clicked.connect(self._choose_custom_color)
            tb_layout.addWidget(self.btn_custom_color)

            tb_layout.addSpacing(6)

            # Stroke Width Selection
            lbl_width = QLabel("Line:")
            lbl_width.setStyleSheet("color: #9cdcfe; font-weight: bold;")
            tb_layout.addWidget(lbl_width)

            self.btn_stroke_thin = QToolButton()
            self.btn_stroke_thin.setText("2px")
            self.btn_stroke_thin.setCheckable(True)
            self.btn_stroke_thin.clicked.connect(lambda: self._set_stroke_width(2))
            tb_layout.addWidget(self.btn_stroke_thin)

            self.btn_stroke_med = QToolButton()
            self.btn_stroke_med.setText("4px")
            self.btn_stroke_med.setCheckable(True)
            self.btn_stroke_med.setChecked(True)
            self.btn_stroke_med.clicked.connect(lambda: self._set_stroke_width(4))
            tb_layout.addWidget(self.btn_stroke_med)

            self.btn_stroke_thick = QToolButton()
            self.btn_stroke_thick.setText("8px")
            self.btn_stroke_thick.setCheckable(True)
            self.btn_stroke_thick.clicked.connect(lambda: self._set_stroke_width(8))
            tb_layout.addWidget(self.btn_stroke_thick)

            stroke_grp = QButtonGroup(self)
            stroke_grp.addButton(self.btn_stroke_thin)
            stroke_grp.addButton(self.btn_stroke_med)
            stroke_grp.addButton(self.btn_stroke_thick)

            tb_layout.addSpacing(6)

            # Zoom In / Out / Reset Controls
            lbl_zoom = QLabel("Zoom:")
            lbl_zoom.setStyleSheet("color: #9cdcfe; font-weight: bold;")
            tb_layout.addWidget(lbl_zoom)

            self.btn_zoom_out = QToolButton()
            self.btn_zoom_out.setText("➖")
            self.btn_zoom_out.setToolTip("Zoom out (Ctrl+- or Ctrl+Wheel Down)")
            self.btn_zoom_out.clicked.connect(self._on_zoom_out)
            tb_layout.addWidget(self.btn_zoom_out)

            self.lbl_zoom_val = QLabel("100%")
            self.lbl_zoom_val.setStyleSheet("color: #cccccc; min-width: 36px; qproperty-alignment: AlignCenter;")
            tb_layout.addWidget(self.lbl_zoom_val)

            self.btn_zoom_in = QToolButton()
            self.btn_zoom_in.setText("➕")
            self.btn_zoom_in.setToolTip("Zoom in (Ctrl++ or Ctrl+Wheel Up)")
            self.btn_zoom_in.clicked.connect(self._on_zoom_in)
            tb_layout.addWidget(self.btn_zoom_in)

            self.btn_zoom_reset = QToolButton()
            self.btn_zoom_reset.setText("1:1")
            self.btn_zoom_reset.setToolTip("Reset Zoom to 100% (Ctrl+0)")
            self.btn_zoom_reset.clicked.connect(self._on_zoom_reset)
            tb_layout.addWidget(self.btn_zoom_reset)

            tb_layout.addStretch()

            # Reversal / History Buttons
            self.btn_undo = QPushButton("↺ Undo")
            self.btn_undo.setToolTip("Undo last annotation step (Ctrl+Z)")
            self.btn_undo.clicked.connect(self._on_undo)
            tb_layout.addWidget(self.btn_undo)

            self.btn_redo = QPushButton("↻ Redo")
            self.btn_redo.setToolTip("Redo undone step (Ctrl+Y)")
            self.btn_redo.clicked.connect(self._on_redo)
            tb_layout.addWidget(self.btn_redo)

            self.btn_reset = QPushButton("🔄 Reset Image")
            self.btn_reset.setToolTip("Clear all annotations and restore original image")
            self.btn_reset.clicked.connect(self._on_reset)
            tb_layout.addWidget(self.btn_reset)

            # Full Screen Maximize / Restore Button
            init_max = bool(self.windowState() & Qt.WindowMaximized)
            self.btn_maximize = QPushButton("❐ Restore" if init_max else "⛶ Maximize")
            self.btn_maximize.setToolTip(
                "Restore Image Editor to normal window size (F11 or double-click top bar)"
                if init_max
                else "Toggle full screen (F11 or double-click top bar)"
            )
            self.btn_maximize.clicked.connect(self._toggle_maximize)
            tb_layout.addWidget(self.btn_maximize)

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

        # 2. Main Body: Splitter with Canvas (Left) and Dimensions/Presets (Right)
        if self._image and not self._image.isNull():
            body_splitter = QSplitter(Qt.Horizontal)
            body_splitter.setStyleSheet("QSplitter::handle { background-color: #333333; width: 4px; }")

            # Left Canvas
            self.canvas = ImageAnnotationCanvas(self._image, self)
            self.canvas.zoom_changed.connect(self._on_zoom_changed)
            self.canvas.tool_changed.connect(self._sync_toolbar_tool_buttons)
            body_splitter.addWidget(self.canvas)

            # Right Side Panel: Dimensions Form & Presets
            side_panel = QFrame()
            side_panel.setFixedWidth(270)
            side_layout = QVBoxLayout(side_panel)
            side_layout.setContentsMargins(8, 0, 0, 0)
            side_layout.setSpacing(10)

            lbl_dim_title = QLabel("📐 Resize Dimensions")
            lbl_dim_title.setStyleSheet("font-weight: bold; font-size: 10pt; color: #9cdcfe;")
            side_layout.addWidget(lbl_dim_title)

            info_text = f"Original: <b>{self._orig_w} × {self._orig_h} px</b>"
            self.lbl_info = QLabel(info_text)
            self.lbl_info.setStyleSheet("color: #888888; font-size: 8.5pt;")
            side_layout.addWidget(self.lbl_info)

            form = QFormLayout()
            form.setSpacing(8)

            self.spin_width = QSpinBox()
            self.spin_width.setRange(20, 5000)
            self.spin_width.setSingleStep(10)
            self.spin_width.setSuffix(" px")
            self.spin_width.setValue(self._curr_w)
            self.spin_width.valueChanged.connect(self._on_width_changed)
            form.addRow("Width:", self.spin_width)

            self.spin_height = QSpinBox()
            self.spin_height.setRange(20, 5000)
            self.spin_height.setSingleStep(10)
            self.spin_height.setSuffix(" px")
            self.spin_height.setValue(self._curr_h)
            self.spin_height.valueChanged.connect(self._on_height_changed)
            form.addRow("Height:", self.spin_height)
            side_layout.addLayout(form)

            self.chk_lock_aspect = QCheckBox("🔗 Lock aspect ratio")
            self.chk_lock_aspect.setChecked(True)
            self.chk_lock_aspect.setStyleSheet("color: #cccccc; font-size: 9pt;")
            side_layout.addWidget(self.chk_lock_aspect)

            # Presets Box
            lbl_presets = QLabel("Quick Presets:")
            lbl_presets.setStyleSheet("color: #9cdcfe; font-weight: bold; font-size: 9pt; margin-top: 6px;")
            side_layout.addWidget(lbl_presets)

            grid_presets = QHBoxLayout()
            grid_presets.setSpacing(4)
            for label, pct in [("25%", 0.25), ("50%", 0.50), ("75%", 0.75), ("100%", 1.0)]:
                btn = QPushButton(label)
                btn.setFixedHeight(24)
                btn.clicked.connect(lambda checked=False, p=pct: self._apply_preset_percentage(p))
                grid_presets.addWidget(btn)
            side_layout.addLayout(grid_presets)

            self.btn_fit_pane = QPushButton("Fit to Pane Width")
            self.btn_fit_pane.setFixedHeight(26)
            self.btn_fit_pane.setToolTip(f"Scales image to fit editor pane (max {self._max_pane_w} px)")
            self.btn_fit_pane.clicked.connect(self._apply_preset_fit_pane)
            side_layout.addWidget(self.btn_fit_pane)

            side_layout.addStretch()
            body_splitter.addWidget(side_panel)
            body_splitter.setSizes([720, 270])
            main_layout.addWidget(body_splitter, 1)

        else:
            # Standalone Dimensions View (Fallback when no QImage instance provided)
            header_frame = QFrame()
            header_layout = QVBoxLayout(header_frame)
            header_layout.setContentsMargins(0, 0, 0, 0)
            header_layout.setSpacing(4)

            lbl_title = QLabel("📐 Resize Image Dimensions")
            lbl_title.setStyleSheet("font-weight: bold; font-size: 11pt; color: #9cdcfe;")
            header_layout.addWidget(lbl_title)

            info_text = f"Original Size: <b>{self._orig_w} × {self._orig_h} px</b> | Current: <b>{self._curr_w} × {self._curr_h} px</b>"
            self.lbl_info = QLabel(info_text)
            self.lbl_info.setStyleSheet("color: #888888; font-size: 9pt;")
            header_layout.addWidget(self.lbl_info)
            main_layout.addWidget(header_frame)

            form = QFormLayout()
            form.setSpacing(10)

            self.spin_width = QSpinBox()
            self.spin_width.setRange(20, 5000)
            self.spin_width.setSingleStep(10)
            self.spin_width.setSuffix(" px")
            self.spin_width.setValue(self._curr_w)
            self.spin_width.valueChanged.connect(self._on_width_changed)
            form.addRow("Width:", self.spin_width)

            self.spin_height = QSpinBox()
            self.spin_height.setRange(20, 5000)
            self.spin_height.setSingleStep(10)
            self.spin_height.setSuffix(" px")
            self.spin_height.setValue(self._curr_h)
            self.spin_height.valueChanged.connect(self._on_height_changed)
            form.addRow("Height:", self.spin_height)
            main_layout.addLayout(form)

            self.chk_lock_aspect = QCheckBox("🔗 Lock aspect ratio")
            self.chk_lock_aspect.setChecked(True)
            self.chk_lock_aspect.setStyleSheet("color: #cccccc; font-size: 9pt;")
            main_layout.addWidget(self.chk_lock_aspect)

            preset_box = QFrame()
            preset_layout = QVBoxLayout(preset_box)
            preset_layout.setContentsMargins(0, 4, 0, 4)
            preset_layout.setSpacing(6)

            lbl_presets = QLabel("Quick Presets:")
            lbl_presets.setStyleSheet("color: #9cdcfe; font-weight: bold; font-size: 9pt;")
            preset_layout.addWidget(lbl_presets)

            presets_row = QHBoxLayout()
            presets_row.setSpacing(6)

            for label, pct in [("25%", 0.25), ("50%", 0.50), ("75%", 0.75), ("100%", 1.0)]:
                btn = QPushButton(label)
                btn.setFixedHeight(26)
                btn.clicked.connect(lambda checked=False, p=pct: self._apply_preset_percentage(p))
                presets_row.addWidget(btn)

            self.btn_fit_pane = QPushButton("Fit to Pane Width")
            self.btn_fit_pane.setFixedHeight(26)
            self.btn_fit_pane.setToolTip(f"Scales image to fit editor pane (max {self._max_pane_w} px)")
            self.btn_fit_pane.clicked.connect(self._apply_preset_fit_pane)
            presets_row.addWidget(self.btn_fit_pane)

            preset_layout.addLayout(presets_row)
            main_layout.addWidget(preset_box)

        # 3. Bottom Dialog Buttons
        self.button_box = QDialogButtonBox(QDialogButtonBox.Ok | QDialogButtonBox.Cancel)
        self.button_box.accepted.connect(self.accept)
        self.button_box.rejected.connect(self.reject)
        main_layout.addWidget(self.button_box)

        apply_glow_to_buttons([self])

    def showEvent(self, event) -> None:
        super().showEvent(event)
        if not self._has_shown:
            self._has_shown = True
            if self._image and not self._image.isNull():
                self.setWindowState(self.windowState() | Qt.WindowMaximized)
                if hasattr(self, "btn_maximize"):
                    self.btn_maximize.setText("❐ Restore")
                    self.btn_maximize.setToolTip("Restore Image Editor to normal window size (F11 or double-click top bar)")

    def changeEvent(self, event) -> None:
        super().changeEvent(event)
        if hasattr(self, "btn_maximize"):
            if self.isMaximized() or bool(self.windowState() & Qt.WindowMaximized):
                self.btn_maximize.setText("❐ Restore")
                self.btn_maximize.setToolTip("Restore Image Editor to normal window size (F11 or double-click top bar)")
            else:
                self.btn_maximize.setText("⛶ Maximize")
                self.btn_maximize.setToolTip("Maximize Image Editor to full screen (F11 or double-click top bar)")

    def _toggle_maximize(self) -> None:
        """Toggles window between maximized (full screen) and normal restored geometry."""
        if self.isMaximized() or bool(self.windowState() & Qt.WindowMaximized):
            self.setWindowState(self.windowState() & ~Qt.WindowMaximized)
            if self.isVisible():
                self.showNormal()
            if hasattr(self, "btn_maximize"):
                self.btn_maximize.setText("⛶ Maximize")
                self.btn_maximize.setToolTip("Maximize Image Editor to full screen (F11 or double-click top bar)")
        else:
            self.setWindowState(self.windowState() | Qt.WindowMaximized)
            if self.isVisible():
                self.showMaximized()
            if hasattr(self, "btn_maximize"):
                self.btn_maximize.setText("❐ Restore")
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

    def _on_undo(self) -> None:
        if self.canvas:
            self.canvas.undo()

    def _on_redo(self) -> None:
        if self.canvas:
            self.canvas.redo()

    def _on_reset(self) -> None:
        if self.canvas:
            self.canvas.reset_image()

    def _on_rotate_90(self) -> None:
        if self.canvas:
            self.canvas.rotate_selected_item(90.0)

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

    def _apply_styling(self) -> None:
        self.setStyleSheet("""
            QDialog {
                background-color: #252526;
                color: #cccccc;
            }
            QLabel {
                color: #cccccc;
            }
            QFrame#annotationToolbar {
                background-color: #1e1e1e;
                border: 1px solid #3c3c3c;
                border-radius: 4px;
            }
            QToolButton {
                background-color: #2d2d30;
                color: #cccccc;
                border: 1px solid #3c3c3c;
                border-radius: 4px;
                padding: 4px 8px;
                font-size: 9pt;
            }
            QToolButton:hover {
                background-color: #383838;
                border-color: #007acc;
                color: #ffffff;
            }
            QToolButton:checked {
                background-color: #0e639c;
                border-color: #1177bb;
                color: #ffffff;
            }
            QSpinBox {
                background-color: #1e1e1e;
                color: #cccccc;
                border: 1px solid #3c3c3c;
                border-radius: 4px;
                padding: 4px 8px;
            }
            QSpinBox:focus {
                border-color: #007acc;
            }
            QPushButton {
                background-color: #333333;
                color: #cccccc;
                border: 1px solid #3c3c3c;
                border-radius: 4px;
                padding: 4px 10px;
                font-size: 9pt;
            }
            QPushButton:hover {
                background-color: #3e3e42;
                border-color: #007acc;
                color: #ffffff;
            }
            QPushButton:pressed {
                background-color: #0e639c;
            }
        """)

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
