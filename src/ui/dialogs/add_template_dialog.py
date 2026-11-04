"""Modal dialog to create and save rich-text custom ticket templates."""

import base64
from pathlib import Path
import re
from typing import Dict, Optional, Tuple
import uuid

from PIL import Image
from PySide6.QtCore import QBuffer, QByteArray, QIODevice, QMimeData, Qt, QUrl
from PySide6.QtGui import (
    QAction,
    QColor,
    QDragEnterEvent,
    QDropEvent,
    QFont,
    QImage,
    QKeySequence,
    QTextCharFormat,
    QTextBlockFormat,
    QTextCursor,
    QTextDocument,
    QTextListFormat,
)
from PySide6.QtWidgets import (
    QColorDialog,
    QComboBox,
    QDialog,
    QFileDialog,
    QHBoxLayout,
    QLabel,
    QLineEdit,
    QMessageBox,
    QPushButton,
    QTextEdit,
    QToolBar,
    QToolButton,
    QVBoxLayout,
    QWidget,
)

from src.core.constants import JPEG_COMPRESSION_QUALITY, LOCAL_IMAGE_URL_PREFIX
from src.services.image_service import ImageService


class TemplateEditor(QTextEdit):
    """Rich text editor supporting inline images, formatting, drag-and-drop, and full clipboard fidelity."""

    def __init__(self, image_service: Optional[ImageService] = None, parent: Optional[QWidget] = None):
        super().__init__(parent)
        self.image_service = image_service
        self.in_memory_images: Dict[str, bytes] = {}
        self.setAcceptDrops(True)
        self.setStyleSheet("""
            QTextEdit {
                background-color: #1e1e1e;
                color: #cccccc;
                border: 1px solid #3c3c3c;
                border-radius: 4px;
                padding: 8px;
                font-family: -apple-system, BlinkMacSystemFont, "Segoe UI", Roboto, Helvetica, Arial, sans-serif;
                font-size: 10pt;
                selection-background-color: #264f78;
                selection-color: #ffffff;
            }
            QTextEdit:focus {
                border: 1px solid #007acc;
            }
        """)

    def compress_image_to_jpeg(self, source) -> Tuple[str, bytes, QImage]:
        """Compresses source image (bytes or QImage) to JPEG quality 82-85 and returns (image_name, jpeg_bytes, qimage)."""
        image_name = f"{uuid.uuid4().hex}.jpg"
        if self.image_service:
            name, _, jpeg_bytes, qimg = self.image_service.create_embedded_image(source)
            return name, jpeg_bytes, qimg

        # Fallback if image_service is not supplied
        if isinstance(source, QImage):
            qimg = source
        else:
            qimg = QImage()
            qimg.loadFromData(source)

        if qimg.hasAlphaChannel():
            converted = QImage(qimg.size(), QImage.Format_RGB32)
            converted.fill(0xFFFFFF)
            from PySide6.QtGui import QPainter
            painter = QPainter(converted)
            painter.drawImage(0, 0, qimg)
            painter.end()
            qimg = converted
        else:
            qimg = qimg.convertToFormat(QImage.Format_RGB32)

        byte_arr = QByteArray()
        buffer = QBuffer(byte_arr)
        buffer.open(QIODevice.WriteOnly)
        qimg.save(buffer, "JPEG", JPEG_COMPRESSION_QUALITY)
        jpeg_bytes = bytes(byte_arr.data())
        return image_name, jpeg_bytes, qimg

    def insert_image(self, source) -> None:
        """Compresses, caches, registers, and inserts image into the document."""
        try:
            image_name, jpeg_bytes, qimg = self.compress_image_to_jpeg(source)
            self.in_memory_images[image_name] = jpeg_bytes
            resource_url = f"{LOCAL_IMAGE_URL_PREFIX}{image_name}"
            self.document().addResource(QTextDocument.ImageResource, QUrl(resource_url), qimg)

            cursor = self.textCursor()
            cursor.insertImage(resource_url)
            cursor.insertBlock()
            self.setTextCursor(cursor)
        except Exception as e:
            QMessageBox.warning(self, "Image Error", f"Failed to insert image: {e}")

    def canInsertFromMimeData(self, source: QMimeData) -> bool:
        if source.hasImage() or source.hasUrls() or source.hasText() or source.hasHtml():
            return True
        return super().canInsertFromMimeData(source)

    def insertFromMimeData(self, source: QMimeData) -> None:
        """Handles pasting screenshots (Win+Shift+S / Ctrl+V) or image files with automatic compression."""
        if source.hasImage():
            qimage = source.imageData()
            if isinstance(qimage, QImage) and not qimage.isNull():
                self.insert_image(qimage)
                return

        if source.hasUrls():
            for url in source.urls():
                if url.isLocalFile():
                    path = Path(url.toLocalFile())
                    if path.suffix.lower() in (".png", ".jpg", ".jpeg", ".bmp", ".gif", ".webp"):
                        try:
                            with open(path, "rb") as f:
                                self.insert_image(f.read())
                            return
                        except Exception as e:
                            QMessageBox.warning(self, "Image Load Error", f"Could not load image: {e}")

        super().insertFromMimeData(source)

    def dragEnterEvent(self, event: QDragEnterEvent) -> None:
        if event.mimeData().hasUrls() or event.mimeData().hasImage():
            event.acceptProposedAction()
        else:
            super().dragEnterEvent(event)

    def dragMoveEvent(self, event) -> None:
        if event.mimeData().hasUrls() or event.mimeData().hasImage():
            event.acceptProposedAction()
        else:
            super().dragMoveEvent(event)

    def dropEvent(self, event: QDropEvent) -> None:
        if event.mimeData().hasUrls() or event.mimeData().hasImage():
            self.insertFromMimeData(event.mimeData())
            event.acceptProposedAction()
        else:
            super().dropEvent(event)

    def createMimeDataFromSelection(self) -> QMimeData:
        """Preserves formatting and converts internal local image URLs to self-contained Base64 URIs on copy."""
        mime = super().createMimeDataFromSelection()
        if not mime or not mime.hasHtml():
            return mime

        html = mime.html()
        img_pattern = re.compile(r'(<img\s+[^>]*src=["\'])([^"\']+)(["\'][^>]*>)', re.IGNORECASE)

        def repl(m: re.Match) -> str:
            prefix = m.group(1)
            src = m.group(2)
            suffix = m.group(3)
            if src.startswith("data:") or src.startswith("http"):
                return m.group(0)
            raw_name = src.replace(LOCAL_IMAGE_URL_PREFIX, "").split("/")[-1]
            jpeg_bytes = self.in_memory_images.get(raw_name)
            if not jpeg_bytes:
                # Try getting from document resource
                res = self.document().resource(QTextDocument.ImageResource, QUrl(src))
                if isinstance(res, QImage) and not res.isNull():
                    _, jpeg_bytes, _ = self.compress_image_to_jpeg(res)
            if jpeg_bytes:
                b64 = base64.b64encode(jpeg_bytes).decode("ascii")
                return f'{prefix}data:image/jpeg;base64,{b64}{suffix}'
            return m.group(0)

        enriched_html = img_pattern.sub(repl, html)
        mime.setHtml(enriched_html)
        return mime

    def get_self_contained_html(self) -> str:
        """Returns the document HTML with all local image URIs converted to Base64 data URIs."""
        html = self.toHtml()
        img_pattern = re.compile(r'(<img\s+[^>]*src=["\'])([^"\']+)(["\'][^>]*>)', re.IGNORECASE)

        def repl(m: re.Match) -> str:
            prefix = m.group(1)
            src = m.group(2)
            suffix = m.group(3)
            if src.startswith("data:") or src.startswith("http"):
                return m.group(0)
            raw_name = src.replace(LOCAL_IMAGE_URL_PREFIX, "").split("/")[-1]
            jpeg_bytes = self.in_memory_images.get(raw_name)
            if not jpeg_bytes:
                res = self.document().resource(QTextDocument.ImageResource, QUrl(src))
                if isinstance(res, QImage) and not res.isNull():
                    _, jpeg_bytes, _ = self.compress_image_to_jpeg(res)
            if jpeg_bytes:
                b64 = base64.b64encode(jpeg_bytes).decode("ascii")
                return f'{prefix}data:image/jpeg;base64,{b64}{suffix}'
            return m.group(0)

        return img_pattern.sub(repl, html)


class AddTemplateDialog(QDialog):
    """
    Dialog for creating and adding a new technician template with rich text formatting,
    color pickers, clipboard image support, and template persistence.
    """

    def __init__(
        self,
        parent: Optional[QWidget] = None,
        image_service: Optional[ImageService] = None,
        initial_title: str = "",
        initial_content: str = "",
    ):
        super().__init__(parent)
        self.image_service = image_service
        self.setWindowTitle("Add New Template")
        self.setModal(True)
        self.setMinimumSize(620, 520)
        self.resize(680, 560)

        self._setup_ui(initial_title, initial_content)

    def _setup_ui(self, initial_title: str, initial_content: str) -> None:
        layout = QVBoxLayout(self)
        layout.setSpacing(10)
        layout.setContentsMargins(16, 16, 16, 16)

        # 1. Top Section: Title
        lbl_title = QLabel("Title")
        lbl_title.setStyleSheet("font-weight: bold; color: #9cdcfe; font-size: 11pt;")
        layout.addWidget(lbl_title)

        self.txt_title = QLineEdit(initial_title)
        self.txt_title.setPlaceholderText("Enter template title (e.g. Standard Incident Triage, Firewall Rules Review)")
        self.txt_title.setStyleSheet("""
            QLineEdit {
                background-color: #252526;
                color: #ffffff;
                border: 1px solid #3c3c3c;
                border-radius: 4px;
                padding: 6px 10px;
                font-size: 10pt;
            }
            QLineEdit:focus {
                border: 1px solid #007acc;
            }
        """)
        layout.addWidget(self.txt_title)

        # 2. Formatting Mini-Toolbar
        toolbar_container = QWidget()
        toolbar_layout = QHBoxLayout(toolbar_container)
        toolbar_layout.setContentsMargins(0, 4, 0, 4)
        toolbar_layout.setSpacing(4)

        btn_style = """
            QToolButton {
                background-color: #2d2d2d;
                border: 1px solid #3c3c3c;
                border-radius: 3px;
                padding: 4px 8px;
                color: #d4d4d4;
                font-weight: 500;
                font-size: 11px;
            }
            QToolButton:hover {
                background-color: #383838;
                border: 1px solid #007acc;
                color: #ffffff;
            }
            QToolButton:pressed, QToolButton:checked {
                background-color: #0e639c;
                border: 1px solid #1177bb;
                color: #ffffff;
            }
        """

        # Font styles: Bold, Italic, Underline, Strikethrough
        self.btn_bold = QToolButton()
        self.btn_bold.setText("B")
        self.btn_bold.setCheckable(True)
        self.btn_bold.setToolTip("Bold (Ctrl+B)")
        self.btn_bold.setShortcut(QKeySequence("Ctrl+B"))
        self.btn_bold.setStyleSheet(btn_style + "font-weight: bold;")
        self.btn_bold.clicked.connect(self._toggle_bold)
        toolbar_layout.addWidget(self.btn_bold)

        self.btn_italic = QToolButton()
        self.btn_italic.setText("I")
        self.btn_italic.setCheckable(True)
        self.btn_italic.setToolTip("Italic (Ctrl+I)")
        self.btn_italic.setShortcut(QKeySequence("Ctrl+I"))
        self.btn_italic.setStyleSheet(btn_style + "font-style: italic;")
        self.btn_italic.clicked.connect(self._toggle_italic)
        toolbar_layout.addWidget(self.btn_italic)

        self.btn_underline = QToolButton()
        self.btn_underline.setText("U")
        self.btn_underline.setCheckable(True)
        self.btn_underline.setToolTip("Underline (Ctrl+U)")
        self.btn_underline.setShortcut(QKeySequence("Ctrl+U"))
        self.btn_underline.setStyleSheet(btn_style + "text-decoration: underline;")
        self.btn_underline.clicked.connect(self._toggle_underline)
        toolbar_layout.addWidget(self.btn_underline)

        self.btn_strike = QToolButton()
        self.btn_strike.setText("S")
        self.btn_strike.setCheckable(True)
        self.btn_strike.setToolTip("Strikethrough")
        self.btn_strike.setStyleSheet(btn_style + "text-decoration: line-through;")
        self.btn_strike.clicked.connect(self._toggle_strikethrough)
        toolbar_layout.addWidget(self.btn_strike)

        # Separator
        toolbar_layout.addWidget(self._create_separator())

        # Colors: Text Color & Highlight Color
        self.btn_color = QToolButton()
        self.btn_color.setText("🎨")
        self.btn_color.setToolTip("Text Color")
        self.btn_color.setStyleSheet(btn_style)
        self.btn_color.clicked.connect(self._pick_text_color)
        toolbar_layout.addWidget(self.btn_color)

        self.btn_highlight = QToolButton()
        self.btn_highlight.setText("🖍️")
        self.btn_highlight.setToolTip("Highlighted Text Background Color")
        self.btn_highlight.setStyleSheet(btn_style)
        self.btn_highlight.clicked.connect(self._pick_highlight_color)
        toolbar_layout.addWidget(self.btn_highlight)

        # Separator
        toolbar_layout.addWidget(self._create_separator())

        # Headings selector
        self.combo_heading = QComboBox()
        self.combo_heading.addItems(["Normal Text", "Heading 1", "Heading 2", "Heading 3"])
        self.combo_heading.setStyleSheet("""
            QComboBox {
                background-color: #2d2d2d;
                border: 1px solid #3c3c3c;
                border-radius: 3px;
                padding: 3px 8px;
                color: #cccccc;
                font-size: 11px;
            }
            QComboBox:hover {
                border: 1px solid #007acc;
            }
            QComboBox QAbstractItemView {
                background-color: #252526;
                color: #cccccc;
                selection-background-color: #007acc;
            }
        """)
        self.combo_heading.currentIndexChanged.connect(self._apply_heading)
        toolbar_layout.addWidget(self.combo_heading)

        # Lists: Bullet & Numbered
        self.btn_bullet_list = QToolButton()
        self.btn_bullet_list.setText("• List")
        self.btn_bullet_list.setToolTip("Bullet List")
        self.btn_bullet_list.setStyleSheet(btn_style)
        self.btn_bullet_list.clicked.connect(self._insert_bullet_list)
        toolbar_layout.addWidget(self.btn_bullet_list)

        self.btn_num_list = QToolButton()
        self.btn_num_list.setText("1. List")
        self.btn_num_list.setToolTip("Numbered List")
        self.btn_num_list.setStyleSheet(btn_style)
        self.btn_num_list.clicked.connect(self._insert_numbered_list)
        toolbar_layout.addWidget(self.btn_num_list)

        # Code Block
        self.btn_code = QToolButton()
        self.btn_code.setText("</>")
        self.btn_code.setToolTip("Monospace Code Block")
        self.btn_code.setStyleSheet(btn_style)
        self.btn_code.clicked.connect(self._insert_code_block)
        toolbar_layout.addWidget(self.btn_code)

        # Separator
        toolbar_layout.addWidget(self._create_separator())

        # Image Button
        self.btn_image = QToolButton()
        self.btn_image.setText("🖼️ Image")
        self.btn_image.setToolTip("Insert Image (PNG, JPG, JPEG, BMP, WEBP, GIF)")
        self.btn_image.setStyleSheet(btn_style + "padding: 4px 10px; font-weight: bold; color: #60a5fa;")
        self.btn_image.clicked.connect(self._pick_image)
        toolbar_layout.addWidget(self.btn_image)

        toolbar_layout.addStretch()
        layout.addWidget(toolbar_container)

        # 3. Down Section: Template Text Editor
        lbl_template = QLabel("Template")
        lbl_template.setStyleSheet("font-weight: bold; color: #9cdcfe; font-size: 11pt;")
        layout.addWidget(lbl_template)

        self.editor = TemplateEditor(image_service=self.image_service)
        if initial_content:
            self.editor.setHtml(initial_content)
        self.editor.cursorPositionChanged.connect(self._update_format_buttons)
        layout.addWidget(self.editor)

        # 4. Bottom Action Buttons
        bottom_layout = QHBoxLayout()
        bottom_layout.addStretch()

        self.btn_cancel = QPushButton("Cancel")
        self.btn_cancel.setStyleSheet("""
            QPushButton {
                background-color: #2d2d2d;
                border: 1px solid #3c3c3c;
                border-radius: 4px;
                padding: 6px 16px;
                color: #cccccc;
                font-weight: 500;
            }
            QPushButton:hover {
                background-color: #383838;
                color: #ffffff;
            }
        """)
        self.btn_cancel.clicked.connect(self.reject)

        self.btn_save = QPushButton("Save Template")
        self.btn_save.setDefault(True)
        self.btn_save.setStyleSheet("""
            QPushButton {
                background-color: #007acc;
                border: 1px solid #0098ff;
                border-radius: 4px;
                padding: 6px 18px;
                color: #ffffff;
                font-weight: bold;
            }
            QPushButton:hover {
                background-color: #0098ff;
            }
            QPushButton:pressed {
                background-color: #005a9e;
            }
        """)
        self.btn_save.clicked.connect(self._on_save_clicked)

        bottom_layout.addWidget(self.btn_cancel)
        bottom_layout.addWidget(self.btn_save)
        layout.addLayout(bottom_layout)

    def _create_separator(self) -> QWidget:
        sep = QWidget()
        sep.setFixedWidth(1)
        sep.setStyleSheet("background-color: #3c3c3c; margin: 4px 2px;")
        return sep

    def _toggle_bold(self) -> None:
        fmt = QTextCharFormat()
        fmt.setFontWeight(QFont.Bold if self.btn_bold.isChecked() else QFont.Normal)
        self.editor.mergeCurrentCharFormat(fmt)
        self.editor.setFocus()

    def _toggle_italic(self) -> None:
        fmt = QTextCharFormat()
        fmt.setFontItalic(self.btn_italic.isChecked())
        self.editor.mergeCurrentCharFormat(fmt)
        self.editor.setFocus()

    def _toggle_underline(self) -> None:
        fmt = QTextCharFormat()
        fmt.setFontUnderline(self.btn_underline.isChecked())
        self.editor.mergeCurrentCharFormat(fmt)
        self.editor.setFocus()

    def _toggle_strikethrough(self) -> None:
        fmt = QTextCharFormat()
        fmt.setFontStrikeOut(self.btn_strike.isChecked())
        self.editor.mergeCurrentCharFormat(fmt)
        self.editor.setFocus()

    def _pick_text_color(self) -> None:
        color = QColorDialog.getColor(Qt.white, self, "Select Text Color")
        if color.isValid():
            fmt = QTextCharFormat()
            fmt.setForeground(color)
            self.editor.mergeCurrentCharFormat(fmt)
        self.editor.setFocus()

    def _pick_highlight_color(self) -> None:
        color = QColorDialog.getColor(QColor("#264f78"), self, "Select Highlight Color")
        if color.isValid():
            fmt = QTextCharFormat()
            fmt.setBackground(color)
            self.editor.mergeCurrentCharFormat(fmt)
        self.editor.setFocus()

    def _apply_heading(self, index: int) -> None:
        cursor = self.editor.textCursor()
        fmt = QTextCharFormat()
        if index == 1:
            fmt.setFontPointSize(16)
            fmt.setFontWeight(QFont.Bold)
            fmt.setForeground(QColor("#4fc1ff"))
        elif index == 2:
            fmt.setFontPointSize(14)
            fmt.setFontWeight(QFont.Bold)
            fmt.setForeground(QColor("#9cdcfe"))
        elif index == 3:
            fmt.setFontPointSize(12)
            fmt.setFontWeight(QFont.Bold)
            fmt.setForeground(QColor("#dcdcaa"))
        else:
            fmt.setFontPointSize(10)
            fmt.setFontWeight(QFont.Normal)
            fmt.setForeground(QColor("#cccccc"))
        cursor.mergeCharFormat(fmt)
        self.editor.mergeCurrentCharFormat(fmt)
        self.editor.setFocus()

    def _insert_bullet_list(self) -> None:
        cursor = self.editor.textCursor()
        cursor.createList(QTextListFormat.ListDisc)
        self.editor.setFocus()

    def _insert_numbered_list(self) -> None:
        cursor = self.editor.textCursor()
        cursor.createList(QTextListFormat.ListDecimal)
        self.editor.setFocus()

    def _insert_code_block(self) -> None:
        cursor = self.editor.textCursor()
        selected = cursor.selectedText()
        if selected:
            html = f'<div style="background-color: #252526; border: 1px solid #3c3c3c; border-radius: 4px; padding: 6px; font-family: Consolas, monospace; color: #9cdcfe;"><code>{selected}</code></div><br>'
        else:
            html = '<div style="background-color: #252526; border: 1px solid #3c3c3c; border-radius: 4px; padding: 6px; font-family: Consolas, monospace; color: #9cdcfe;"><code># Script / Command / Output</code></div><br>'
        cursor.insertHtml(html)
        self.editor.setFocus()

    def _pick_image(self) -> None:
        file_path, _ = QFileDialog.getOpenFileName(
            self,
            "Insert Image into Template",
            "",
            "Images (*.png *.jpg *.jpeg *.bmp *.webp *.gif);;All Files (*)",
        )
        if file_path:
            try:
                with open(file_path, "rb") as f:
                    data = f.read()
                self.editor.insert_image(data)
            except Exception as e:
                QMessageBox.warning(self, "Image Error", f"Could not load image: {e}")
        self.editor.setFocus()

    def _update_format_buttons(self) -> None:
        fmt = self.editor.currentCharFormat()
        self.btn_bold.blockSignals(True)
        self.btn_italic.blockSignals(True)
        self.btn_underline.blockSignals(True)
        self.btn_strike.blockSignals(True)

        self.btn_bold.setChecked(fmt.fontWeight() == QFont.Bold)
        self.btn_italic.setChecked(fmt.fontItalic())
        self.btn_underline.setChecked(fmt.fontUnderline())
        self.btn_strike.setChecked(fmt.fontStrikeOut())

        self.btn_bold.blockSignals(False)
        self.btn_italic.blockSignals(False)
        self.btn_underline.blockSignals(False)
        self.btn_strike.blockSignals(False)

    def _on_save_clicked(self) -> None:
        title = self.txt_title.text().strip()
        if not title:
            QMessageBox.warning(self, "Missing Title", "Please enter a title for the template.")
            self.txt_title.setFocus()
            return

        plain_text = self.editor.toPlainText().strip()
        if not plain_text and not self.editor.in_memory_images:
            QMessageBox.warning(self, "Missing Content", "Please enter template text or add an image.")
            self.editor.setFocus()
            return

        self.accept()

    def get_template_data(self) -> Tuple[str, str]:
        """Returns (title, content_html) with all images bundled as Base64 data URIs."""
        title = self.txt_title.text().strip()
        content_html = self.editor.get_self_contained_html()
        return title, content_html

