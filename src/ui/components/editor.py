"""Customized QTextEdit for rich text, screenshots, drag-drop, and clickable links."""

from datetime import datetime
from pathlib import Path
import re
from typing import Dict, Optional
from PySide6.QtCore import QMimeData, QPoint, Qt, QUrl, Signal
from PySide6.QtGui import (
    QDesktopServices,
    QDragEnterEvent,
    QDropEvent,
    QImage,
    QKeyEvent,
    QMouseEvent,
    QTextCursor,
    QTextDocument,
)
from PySide6.QtWidgets import QMenu, QMessageBox, QTextEdit
from src.services.image_service import ImageService


class TechPadEditor(QTextEdit):
    """Custom editor with image clipboard/drop capture, clickable links, and auto-save signaling."""

    content_modified = Signal(int)  # Emits scratchpad_id
    image_inserted = Signal(str)    # Emits image_name

    URL_PATTERN = re.compile(r'((?:https?://|www\.)[^\s<>"\'\)]+)', re.IGNORECASE)

    def __init__(self, scratchpad_id: int, image_service: ImageService, parent=None):
        super().__init__(parent)
        self.scratchpad_id = scratchpad_id
        self.image_service = image_service

        # In-memory dictionary holding unsaved image bytes {image_name: bytes}
        self.in_memory_images: Dict[str, bytes] = {}
        self._pressed_anchor = ""

        self.setAcceptDrops(True)
        self.setMouseTracking(True)
        self.textChanged.connect(self._on_text_changed)

    def _on_text_changed(self) -> None:
        self.content_modified.emit(self.scratchpad_id)

    @classmethod
    def linkify_text(cls, text: str) -> str:
        """Converts bare URLs in plain text to styled clickable HTML anchors."""
        def repl(match):
            url = match.group(0)
            href = url if url.lower().startswith(('http://', 'https://')) else f'http://{url}'
            return f'<a href="{href}" style="color: #4fc1ff; text-decoration: underline;">{url}</a>'
        return cls.URL_PATTERN.sub(repl, text)

    def canInsertFromMimeData(self, source: QMimeData) -> bool:
        """Enables paste if clipboard contains image or URLs or text."""
        if source.hasImage() or source.hasUrls() or source.hasText():
            return True
        return super().canInsertFromMimeData(source)

    def insertFromMimeData(self, source: QMimeData) -> None:
        """Catches screenshots from clipboard (Win+Shift+S / Ctrl+V), files, and auto-linkifies text."""
        if source.hasImage():
            qimage = source.imageData()
            if isinstance(qimage, QImage) and not qimage.isNull():
                self.insert_embedded_image(qimage)
                return

        # Check for dropped/copied file URLs
        if source.hasUrls():
            urls = source.urls()
            for url in urls:
                if url.isLocalFile():
                    file_path = Path(url.toLocalFile())
                    if file_path.suffix.lower() in (".png", ".jpg", ".jpeg", ".bmp", ".gif", ".webp"):
                        try:
                            with open(file_path, "rb") as f:
                                data = f.read()
                            self.insert_embedded_image(data)
                            return
                        except Exception as e:
                            QMessageBox.warning(self, "Image Load Error", f"Could not load image: {e}")

        # Auto-detect URLs in plain-text paste
        if source.hasText() and not source.hasHtml():
            text = source.text()
            if self.URL_PATTERN.search(text):
                html = self.linkify_text(text).replace("\n", "<br>")
                self.textCursor().insertHtml(html)
                return

        super().insertFromMimeData(source)

    def keyPressEvent(self, event: QKeyEvent) -> None:
        """Auto-formats typed URLs as hyperlinks when space or enter is pressed."""
        super().keyPressEvent(event)
        if event.key() in (Qt.Key_Space, Qt.Key_Return, Qt.Key_Enter):
            self._auto_link_preceding_word()

    def _auto_link_preceding_word(self) -> None:
        """Checks the word before the cursor and converts it to an anchor if it's a URL."""
        cursor = self.textCursor()
        cursor.movePosition(QTextCursor.Left, QTextCursor.KeepAnchor, 1)
        cursor.movePosition(QTextCursor.PreviousWord, QTextCursor.KeepAnchor)
        selected = cursor.selectedText().strip()
        if self.URL_PATTERN.fullmatch(selected):
            href = selected if selected.lower().startswith(('http://', 'https://')) else f'http://{selected}'
            cursor.insertHtml(f'<a href="{href}" style="color: #4fc1ff; text-decoration: underline;">{selected}</a>&nbsp;')

    def insert_embedded_image(self, source) -> None:
        """
        Compresses image to JPEG (85% quality), adds to document resources,
        caches bytes for auto-save, and inserts image into the cursor.
        """
        image_name, resource_url, jpeg_bytes, qimage = self.image_service.create_embedded_image(source)
        self.in_memory_images[image_name] = jpeg_bytes
        self.image_service.register_image_in_document(self.document(), image_name, qimage)

        cursor = self.textCursor()
        cursor.insertImage(resource_url)
        cursor.insertBlock()
        self.setTextCursor(cursor)
        self.image_inserted.emit(image_name)

    def load_content(self, html_content: str) -> None:
        """Populates document and loads all stored images from SQLite into document resources."""
        self.blockSignals(True)
        self.image_service.load_scratchpad_images_into_document(self.scratchpad_id, self.document())
        self.setHtml(html_content)
        self.blockSignals(False)

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

    def mouseMoveEvent(self, event: QMouseEvent) -> None:
        """Shows pointing hand cursor when hovering over hyperlinks."""
        anchor = self.anchorAt(event.pos())
        if anchor:
            self.viewport().setCursor(Qt.PointingHandCursor)
            self.setToolTip(f"Open link: {anchor}")
        else:
            self.viewport().setCursor(Qt.IBeamCursor)
            self.setToolTip("")
        super().mouseMoveEvent(event)

    def mousePressEvent(self, event: QMouseEvent) -> None:
        if event.button() == Qt.LeftButton:
            self._pressed_anchor = self.anchorAt(event.pos())
        else:
            self._pressed_anchor = ""
        super().mousePressEvent(event)

    def mouseReleaseEvent(self, event: QMouseEvent) -> None:
        """Launches external browser when clicking on an anchor."""
        if event.button() == Qt.LeftButton:
            anchor = self.anchorAt(event.pos())
            if anchor and anchor == self._pressed_anchor:
                target_url = anchor if not anchor.startswith("www.") else f"http://{anchor}"
                QDesktopServices.openUrl(QUrl(target_url))
                event.accept()
                return
        super().mouseReleaseEvent(event)

    def contextMenuEvent(self, event) -> None:
        """Provides enhanced context menu with screenshot paste and technician quick-actions."""
        menu = self.createStandardContextMenu()
        menu.addSeparator()

        act_timestamp = menu.addAction("🕒 Insert Timestamp (F5 / Ctrl+Alt+T)")
        act_timestamp.triggered.connect(self._insert_timestamp)

        act_code = menu.addAction("</> Insert Code Block (Ctrl+Alt+C)")
        act_code.triggered.connect(self._insert_code_block)

        menu.exec(event.globalPos())

    def _insert_timestamp(self) -> None:
        now_str = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
        self.textCursor().insertHtml(f"<strong>[{now_str}]</strong> ")

    def _insert_code_block(self) -> None:
        cursor = self.textCursor()
        selected = cursor.selectedText()
        content = selected if selected else "# CLI / PowerShell Log"
        html = f'<div style="background-color: #252526; border: 1px solid #3c3c3c; border-radius: 4px; padding: 6px; font-family: Consolas, monospace; color: #9cdcfe;"><code>{content}</code></div><br>'
        cursor.insertHtml(html)
