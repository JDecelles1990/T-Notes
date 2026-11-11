"""Modal dialog for resizing and annotating embedded images with drawing, shapes, text, zoom, and undo/redo."""

from typing import Optional, Tuple
from PySide6.QtCore import QPoint, QPointF, QRect, Qt, Signal
from PySide6.QtGui import (
    QColor,
    QFont,
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


class ImageAnnotationCanvas(QWidget):
    """Interactive canvas allowing technicians to draw, circle, add rectangles, and place text with zoom/pan."""

    zoom_changed = Signal(float)

    TOOL_PEN = "pen"
    TOOL_CIRCLE = "circle"
    TOOL_RECTANGLE = "rectangle"
    TOOL_TEXT = "text"

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
        self.setCursor(Qt.CrossCursor)

        # Base and working images (ARGB32 format for crisp alpha painting)
        self._base_image: QImage = image.copy().convertToFormat(QImage.Format_ARGB32_Premultiplied)
        self._current_image: QImage = self._base_image.copy()

        # Undo / Redo history stacks
        self._undo_stack: list[QImage] = []
        self._redo_stack: list[QImage] = []

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
        """Sets the active font size for text annotation."""
        self._font_size = max(8, min(96, size))

    def get_font_size(self) -> int:
        return self._font_size

    # -- History & State Management --------------------------------------------
    def _save_undo_state(self) -> None:
        """Pushes working image snapshot to undo stack and clears redo stack."""
        self._undo_stack.append(self._current_image.copy())
        self._redo_stack.clear()
        if len(self._undo_stack) > 30:
            self._undo_stack.pop(0)

    def undo(self) -> None:
        """Reverses the last annotation change."""
        if self._undo_stack:
            self._redo_stack.append(self._current_image.copy())
            self._current_image = self._undo_stack.pop()
            self._was_annotated = len(self._undo_stack) > 0
            self.update()

    def redo(self) -> None:
        """Re-applies the previously undone annotation change."""
        if self._redo_stack:
            self._undo_stack.append(self._current_image.copy())
            self._current_image = self._redo_stack.pop()
            self._was_annotated = True
            self.update()

    def reset_image(self) -> None:
        """Resets the image back to its original unmodified state."""
        if not self._base_image.isNull():
            self._save_undo_state()
            self._current_image = self._base_image.copy()
            self._was_annotated = False
            self.update()

    def can_undo(self) -> bool:
        return len(self._undo_stack) > 0

    def can_redo(self) -> bool:
        return len(self._redo_stack) > 0

    def was_annotated(self) -> bool:
        return self._was_annotated

    def get_annotated_image(self) -> QImage:
        return self._current_image

    # -- Tool & Palette Configuration -----------------------------------------
    def set_tool(self, tool_name: str) -> None:
        self._active_tool = tool_name
        self._update_cursor()

    def _update_cursor(self) -> None:
        if self._is_panning:
            self.setCursor(Qt.ClosedHandCursor)
        elif self._active_tool == self.TOOL_TEXT:
            self.setCursor(Qt.IBeamCursor)
        else:
            self.setCursor(Qt.CrossCursor)

    def set_color(self, color: QColor) -> None:
        self._current_color = color

    def set_stroke_width(self, width: int) -> None:
        self._stroke_width = max(1, width)

    # -- Painting & Mouse Handlers ---------------------------------------------
    def paintEvent(self, event: QPaintEvent) -> None:
        painter = QPainter(self)
        painter.setRenderHint(QPainter.Antialiasing)
        painter.setRenderHint(QPainter.SmoothPixmapTransform)

        # Background canvas frame
        painter.fillRect(self.rect(), QColor("#1e1e1e"))

        rect = self.get_image_display_rect()
        if rect.isValid() and not self._current_image.isNull():
            # Render working image
            painter.drawImage(rect, self._current_image)

            # Image frame border
            painter.setPen(QPen(QColor("#3c3c3c"), 1))
            painter.drawRect(rect)

            # Interactive shape drag preview overlay
            if self._is_drawing and self._drag_start and self._drag_current:
                scale_x = rect.width() / self._current_image.width()
                scale_y = rect.height() / self._current_image.height()

                vp_start = QPoint(
                    int(rect.x() + self._drag_start.x() * scale_x),
                    int(rect.y() + self._drag_start.y() * scale_y),
                )
                vp_curr = QPoint(
                    int(rect.x() + self._drag_current.x() * scale_x),
                    int(rect.y() + self._drag_current.y() * scale_y),
                )
                preview_rect = QRect(vp_start, vp_curr).normalized()

                if self._active_tool == self.TOOL_RECTANGLE:
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
                    # Paint-style dashed bounding rectangle with subtle tinted fill
                    dash_pen = QPen(self._current_color, 1, Qt.DashLine)
                    painter.setPen(dash_pen)
                    painter.setBrush(QColor(self._current_color.red(), self._current_color.green(), self._current_color.blue(), 25))
                    painter.drawRect(preview_rect)
                    # Text box label preview
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
            # Pan vertically / horizontally with wheel
            dy = event.angleDelta().y() // 8
            dx = event.angleDelta().x() // 8
            self._pan_offset += QPoint(dx, dy)
            self.update()
            event.accept()
        else:
            super().wheelEvent(event)

    def mousePressEvent(self, event: QMouseEvent) -> None:
        # 1. Pan with Middle-click or Right-click
        if event.button() in (Qt.MiddleButton, Qt.RightButton):
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

        # 2. Text Tool: Begin click-and-drag text bounding rectangle (Paint style)
        if self._active_tool == self.TOOL_TEXT:
            self._is_drawing = True
            self._drag_start = img_pt
            self._drag_current = img_pt
            event.accept()
            return

        # 3. Drawing tools (Pen, Circle, Rectangle)
        self._save_undo_state()
        self._is_drawing = True
        self._drag_start = img_pt
        self._drag_current = img_pt
        self._freehand_points = [img_pt]

    def mouseMoveEvent(self, event: QMouseEvent) -> None:
        pos = event.position().toPoint() if hasattr(event, "position") else event.pos()

        # Handle panning drag
        if self._is_panning:
            self._pan_offset = pos - self._pan_start
            self.update()
            event.accept()
            return

        if not self._is_drawing:
            return

        img_pt = self.viewport_to_image_coords(pos, clamp=True)
        if not img_pt:
            return

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

    def mouseReleaseEvent(self, event: QMouseEvent) -> None:
        if self._is_panning and event.button() in (Qt.MiddleButton, Qt.RightButton, Qt.LeftButton):
            self._is_panning = False
            self._update_cursor()
            event.accept()
            return

        if not self._is_drawing or event.button() != Qt.LeftButton:
            return
        self._is_drawing = False

        if self._active_tool == self.TOOL_TEXT and self._drag_start and self._drag_current:
            # Calculate user-dragged text rectangle
            shape_rect = QRect(self._drag_start, self._drag_current).normalized()
            if shape_rect.width() < 24 or shape_rect.height() < 20:
                # If clicked without dragging a bounding box, expand to generous default box
                shape_rect = QRect(self._drag_start.x(), self._drag_start.y(), 260, max(50, self._font_size * 3))

            # Clamp bounding box to image boundaries
            img_w = self._current_image.width()
            img_h = self._current_image.height()
            shape_rect = shape_rect.intersected(QRect(0, 0, img_w, img_h))

            # Prompt technician for text and font size inside the rectangle
            self._prompt_and_add_text_rect(shape_rect)

        elif self._active_tool == self.TOOL_PEN and len(self._freehand_points) == 1:
            painter = QPainter(self._current_image)
            painter.setRenderHint(QPainter.Antialiasing)
            painter.setPen(QPen(self._current_color, self._stroke_width, Qt.SolidLine, Qt.RoundCap, Qt.RoundJoin))
            pt = self._freehand_points[0]
            painter.drawPoint(pt)
            painter.end()
            self._was_annotated = True

        elif self._active_tool in (self.TOOL_RECTANGLE, self.TOOL_CIRCLE) and self._drag_start and self._drag_current:
            shape_rect = QRect(self._drag_start, self._drag_current).normalized()
            if shape_rect.width() > 2 or shape_rect.height() > 2:
                painter = QPainter(self._current_image)
                painter.setRenderHint(QPainter.Antialiasing)
                painter.setPen(QPen(self._current_color, self._stroke_width, Qt.SolidLine, Qt.RoundCap, Qt.RoundJoin))
                painter.setBrush(Qt.NoBrush)
                if self._active_tool == self.TOOL_RECTANGLE:
                    painter.drawRect(shape_rect)
                elif self._active_tool == self.TOOL_CIRCLE:
                    painter.drawEllipse(shape_rect)
                painter.end()
                self._was_annotated = True
            else:
                # Discard unused undo state if drag was negligible
                if self._undo_stack:
                    self._undo_stack.pop()

        self._drag_start = None
        self._drag_current = None
        self._freehand_points.clear()
        self.update()

    def add_text_in_rect(
        self,
        rect: QRect,
        text: str,
        font_size: Optional[int] = None,
        draw_border: bool = False,
    ) -> None:
        """Renders text inside the specified bounding rectangle with high-contrast shadow and optional callout border."""
        if not text.strip():
            return
        self._save_undo_state()
        size = font_size if font_size is not None else self._font_size

        painter = QPainter(self._current_image)
        painter.setRenderHint(QPainter.Antialiasing)

        # Optional callout border box around text
        if draw_border:
            border_pen = QPen(self._current_color, max(1, self._stroke_width // 2), Qt.SolidLine)
            painter.setPen(border_pen)
            painter.setBrush(QColor(0, 0, 0, 160))  # Semi-transparent dark background for readability
            painter.drawRoundedRect(rect, 4, 4)

        font = QFont("Arial", size, QFont.Bold)
        painter.setFont(font)

        text_rect = rect.adjusted(6, 6, -6, -6) if draw_border else rect

        # High-contrast 8-way outline/shadow for readability over any background
        painter.setPen(QColor(0, 0, 0, 230))
        for dx, dy in ((-2, -2), (-2, 2), (2, -2), (2, 2), (0, 2), (2, 0), (0, -2), (-2, 0), (-1, -1), (1, 1)):
            painter.drawText(text_rect.translated(dx, dy), Qt.TextWordWrap | Qt.AlignLeft | Qt.AlignTop, text.strip())

        # Primary text in selected color
        painter.setPen(self._current_color)
        painter.drawText(text_rect, Qt.TextWordWrap | Qt.AlignLeft | Qt.AlignTop, text.strip())
        painter.end()

        self._was_annotated = True
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
    """Dialog allowing technicians to resize an image, apply drawings/callouts/text, zoom, and maximize."""

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
        self.canvas: Optional[ImageAnnotationCanvas] = None

        if self._image and not self._image.isNull():
            self.resize(1020, 680)
            self.setMinimumSize(820, 520)
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

            self.btn_tool_pen = QToolButton()
            self.btn_tool_pen.setText("✏️ Draw")
            self.btn_tool_pen.setCheckable(True)
            self.btn_tool_pen.setChecked(True)
            self.btn_tool_pen.setToolTip("Freehand drawing pen")
            self.btn_tool_pen.clicked.connect(lambda: self._set_canvas_tool(ImageAnnotationCanvas.TOOL_PEN))
            self.tool_group.addButton(self.btn_tool_pen)
            tb_layout.addWidget(self.btn_tool_pen)

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
            self.btn_maximize = QPushButton("⛶ Maximize")
            self.btn_maximize.setToolTip("Toggle full screen (F11 or double-click top bar)")
            self.btn_maximize.clicked.connect(self._toggle_maximize)
            tb_layout.addWidget(self.btn_maximize)

            main_layout.addWidget(toolbar_box)

            # Keyboard shortcuts for undo/redo, zoom, and maximize
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

    def _toggle_maximize(self) -> None:
        """Toggles window between maximized (full screen) and normal restored geometry."""
        if self.isMaximized():
            self.showNormal()
            if hasattr(self, "btn_maximize"):
                self.btn_maximize.setText("⛶ Maximize")
                self.btn_maximize.setToolTip("Maximize Image Editor to full screen (F11 or double-click top bar)")
        else:
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
