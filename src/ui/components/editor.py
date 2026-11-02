"""Customized QTextEdit for rich text, screenshots, drag-drop, and clickable links."""

from datetime import datetime
from pathlib import Path
from typing import Dict, Optional
from PySide6.QtCore import QMimeData, QPoint, Qt, QUrl, Signal
from PySide6.QtGui import (
    QDesktopServices,
    QDragEnterEvent,
    QDropEvent,
    QImage,
    QMouseEvent,
    QPainter,
    QTextCursor,
    QTextDocument,
)
from PySide6.QtWidgets import QMenu, QMessageBox, QTextEdit
from src.services.image_service import ImageService


class TechPadEditor(QTextEdit):
    """Custom editor with image clipboard/drop capture, clickable links, and auto-save signaling."""

    content_modified = Signal(int)  # Emits scratchpad_id
    image_inserted = Signal(str)    # Emits image_name

    def __init__(self, scratchpad_id: int, image_service: ImageService, parent=None):
        super().__init__(parent)
        self.scratchpad_id = scratchpad_id
        self.image_service = image_service

        # In-memory dictionary holding unsaved image bytes {image_name: bytes}
        self.in_memory_images: Dict[str, bytes] = {}

        self.setAcceptDrops(True)
        self.setMouseTracking(True)
        self.textChanged.connect(self._on_text_changed)

    def _on_text_changed(self) -> None:
        self.content_modified.emit(self.scratchpad_id)

    def canInsertFromMimeData(self, source: QMimeData) -> bool:
        """Enables paste if clipboard contains image or URLs or text."""
        if source.hasImage() or source.hasUrls() or source.hasText():
            return True
        return super().canInsertFromMimeData(source)

    def insertFromMimeData(self, source: QMimeData) -> None:
        """Catches screenshots from clipboard (Win+Shift+S / Ctrl+V) and compresses them to JPEG."""
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

        super().insertFromMimeData(source)

    def insert_embedded_image(self, source) -> None:
        """
        Compresses image to JPEG (85% quality), adds to document resources,
        caches bytes for auto-save, and inserts image into the cursor.
        """
        image_name, resource_url, jpeg_bytes, qimage = self.image_service.create_embedded_image(source)

        # Cache bytes in memory for synchronization with SQLite
        self.in_memory_images[image_name] = jpeg_bytes

        # Register in Qt QTextDocument
        self.image_service.register_image_in_document(self.document(), image_name, qimage)

        # Insert into cursor
        cursor = self.textCursor()
        cursor.insertImage(resource_url)
        cursor.insertBlock()  # Add space after image
        self.setTextCursor(cursor)
        self.image_inserted.emit(image_name)

    def load_content(self, html_content: str) -> None:
        """Populates document and loads all stored images from SQLite into document resources."""
        self.blockSignals(True)
        # Register saved images from DB into document resources
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

    def mousePressEvent(self, event: QMouseEvent) -> None:
        """Opens hyperlinks when clicked."""
        if event.button() == Qt.LeftButton:
            anchor = self.anchorAt(event.pos())
            if anchor and (anchor.startswith("http://") or anchor.startswith("https://") or anchor.startswith("mailto:")):
                QDesktopServices.openUrl(QUrl(anchor))
                event.accept()
                return
        super().mousePressEvent(event)

    def contextMenuEvent(self, event) -> None:
        """Provides enhanced context menu with screenshot paste and technician quick-actions."""
        menu = self.createStandardContextMenu()
        menu.addSeparator()

        act_timestamp = menu.addAction("🕒 Insert Timestamp")
        act_timestamp.triggered.connect(self._insert_timestamp)

        act_code = menu.addAction("</> Insert Code Block")
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

