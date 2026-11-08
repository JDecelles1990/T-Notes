"""Customized QTextEdit for rich text, screenshots, drag-drop, and clickable links."""

import base64
import uuid
from datetime import datetime
from pathlib import Path
import re
from typing import Dict, Optional, Tuple
from PySide6.QtCore import QBuffer, QEvent, QIODevice, QMimeData, QPoint, QRect, Qt, QUrl, Signal
from PySide6.QtGui import (
    QColor,
    QDesktopServices,
    QDragEnterEvent,
    QDropEvent,
    QFont,
    QImage,
    QKeyEvent,
    QMouseEvent,
    QPainter,
    QPen,
    QTextCharFormat,
    QTextCursor,
    QTextDocument,
    QTextImageFormat,
)
from PySide6.QtWidgets import (
    QApplication,
    QDialog,
    QFileDialog,
    QMenu,
    QMessageBox,
    QTextEdit,
    QToolTip,
)
from src.core.constants import LOCAL_IMAGE_URL_PREFIX
from src.services.image_service import ImageService
from src.ui.dialogs.resize_image_dialog import ResizeImageDialog


class TechPadEditor(QTextEdit):
    """Custom editor with image clipboard/drop capture, clickable links, and auto-save signaling."""

    content_modified = Signal(int)     # Emits scratchpad_id
    image_inserted = Signal(str)       # Emits image_name
    move_tab_requested = Signal(int)   # Emits relative delta (-1 for left, +1 for right)
    switch_tab_requested = Signal(int) # Emits relative delta (-1 for previous, +1 for next)
    checklist_stats_changed = Signal(int, int, int)  # Emits scratchpad_id, completed, total
    editor_focused = Signal(int)                      # Emits scratchpad_id when focus enters editor

    URL_PATTERN = re.compile(r'((?:https?://|www\.)[^\s<>"\'\)]+)', re.IGNORECASE)
    CHECKBOX_UNCHECKED_HTML = '<a href="task://toggle" style="color: #4ade80; text-decoration: none; font-family: Consolas, monospace; font-size: 13px; font-weight: bold;">[ ]</a>&nbsp;'
    CHECKBOX_CHECKED_HTML = '<a href="task://toggle" style="color: #4ade80; text-decoration: none; font-family: Consolas, monospace; font-size: 13px; font-weight: bold;">[✔]</a>&nbsp;'

    def __init__(self, scratchpad_id: int, image_service: ImageService, parent=None):
        super().__init__(parent)
        self.scratchpad_id = scratchpad_id
        self.image_service = image_service

        # In-memory dictionary holding unsaved image bytes {image_name: bytes}
        self.in_memory_images: Dict[str, bytes] = {}
        self._pressed_anchor = ""

        # Image selection & interactive resize tracking
        self._selected_image_pos: Optional[int] = None
        self._is_resizing_image: bool = False
        self._resize_start_pos: QPoint = QPoint()
        self._resize_orig_width: int = 0
        self._resize_orig_height: int = 0
        self._resize_current_width: int = 0
        self._resize_current_height: int = 0
        self._resize_aspect_ratio: float = 1.0

        self.setAcceptDrops(True)
        self.setMouseTracking(True)
        self.viewport().installEventFilter(self)
        self.textChanged.connect(self._on_text_changed)
        self.cursorPositionChanged.connect(self._on_cursor_or_focus)

    def _on_cursor_or_focus(self) -> None:
        self.setFocus()
        self.editor_focused.emit(self.scratchpad_id)

    def _on_text_changed(self) -> None:
        self.content_modified.emit(self.scratchpad_id)
        self._emit_checklist_stats()

    @classmethod
    def linkify_text(cls, text: str) -> str:
        """Converts bare URLs in plain text to styled clickable HTML anchors."""
        def repl(match):
            url = match.group(0)
            href = url if url.lower().startswith(('http://', 'https://')) else f'http://{url}'
            return f'<a href="{href}" style="color: #4fc1ff; text-decoration: underline;">{url}</a>'
        return cls.URL_PATTERN.sub(repl, text)

    def get_checklist_stats(self) -> tuple[int, int]:
        """Calculates (completed_count, total_count) of checklist items in the document."""
        text = self.toPlainText()
        total = 0
        completed = 0
        for line in text.splitlines():
            trimmed = line.strip()
            if trimmed.startswith("[ ]") or trimmed.startswith("- [ ]"):
                total += 1
            elif any(trimmed.startswith(prefix) for prefix in ("[✔]", "[x]", "[X]", "- [x]", "- [X]", "- [✔]")):
                total += 1
                completed += 1
        return completed, total

    def _emit_checklist_stats(self) -> None:
        """Emits checklist progress statistics for tab header updates."""
        completed, total = self.get_checklist_stats()
        self.checklist_stats_changed.emit(self.scratchpad_id, completed, total)

    def insert_checklist_item(self) -> None:
        """Inserts a new interactive checklist item at current cursor position."""
        cursor = self.textCursor()
        cursor.insertHtml(self.CHECKBOX_UNCHECKED_HTML)
        self.setTextCursor(cursor)
        self._emit_checklist_stats()

    def _toggle_checkbox_at(self, pos: QPoint) -> None:
        """Toggles checklist checkbox [ ] <-> [✔] and updates strikethrough styling."""
        cursor = self.cursorForPosition(pos)
        block = cursor.block()
        block_text = block.text()

        # Position relative to block
        pos_in_block = cursor.position() - block.position()

        # Isolate line within soft breaks (\u2028)
        line_start = block_text.rfind('\u2028', 0, max(0, pos_in_block))
        line_start = 0 if line_start == -1 else line_start + 1
        line_end = block_text.find('\u2028', pos_in_block)
        line_end = len(block_text) if line_end == -1 else line_end
        line_text = block_text[line_start:line_end]

        if "[ ]" in line_text:
            idx = line_text.find("[ ]")
            start = block.position() + line_start + idx
            end = start + 3
            cursor.setPosition(start)
            cursor.setPosition(end, QTextCursor.KeepAnchor)
            btn_fmt = QTextCharFormat()
            btn_fmt.setForeground(QColor("#4ade80"))
            btn_fmt.setFontWeight(QFont.Bold)
            btn_fmt.setFontFamilies(["Consolas"])
            btn_fmt.setAnchor(True)
            btn_fmt.setAnchorHref("task://toggle")
            cursor.insertText("[✔]", btn_fmt)
            # Apply strikethrough to text following the checkbox on this line
            text_start = end
            text_end = block.position() + line_end
            if text_end > text_start:
                cursor.setPosition(text_start)
                cursor.setPosition(text_end, QTextCursor.KeepAnchor)
                fmt = QTextCharFormat()
                fmt.setFontStrikeOut(True)
                fmt.setForeground(QColor("#888888"))
                cursor.mergeCharFormat(fmt)
        elif any(sym in line_text for sym in ("[✔]", "[x]", "[X]")):
            match_sym = "[✔]" if "[✔]" in line_text else ("[x]" if "[x]" in line_text else "[X]")
            idx = line_text.find(match_sym)
            start = block.position() + line_start + idx
            end = start + len(match_sym)
            cursor.setPosition(start)
            cursor.setPosition(end, QTextCursor.KeepAnchor)
            btn_fmt = QTextCharFormat()
            btn_fmt.setForeground(QColor("#007acc"))
            btn_fmt.setFontWeight(QFont.Bold)
            btn_fmt.setFontFamilies(["Consolas"])
            btn_fmt.setAnchor(True)
            btn_fmt.setAnchorHref("task://toggle")
            cursor.insertText("[ ]", btn_fmt)
            # Remove strikethrough from text following the checkbox on this line
            text_start = end
            text_end = block.position() + line_end
            if text_end > text_start:
                cursor.setPosition(text_start)
                cursor.setPosition(text_end, QTextCursor.KeepAnchor)
                fmt = QTextCharFormat()
                fmt.setFontStrikeOut(False)
                fmt.setForeground(QColor("#cccccc"))
                cursor.mergeCharFormat(fmt)

        self._emit_checklist_stats()
        self._on_text_changed()

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

    def _enrich_html_with_base64_images(self, html: str) -> Tuple[str, Optional[QImage]]:
        """Converts internal 'image://local/...' URIs into embedded 'data:image/jpeg;base64,...' URIs.

        Guarantees full fidelity when pasting formatted text, colors, and screenshots into
        external applications (Microsoft Word, Outlook, Teams, Slack, Google Docs, Chrome, etc.).
        """
        img_pattern = re.compile(r'(<img\s+[^>]*src=["\'])([^"\']+)(["\'][^>]*>)', re.IGNORECASE)
        first_qimage: Optional[QImage] = None

        def repl(m: re.Match) -> str:
            nonlocal first_qimage
            prefix = m.group(1)
            src = m.group(2)
            suffix = m.group(3)

            # Skip if already a data URI or external web URL
            if src.startswith("data:") or src.startswith("http://") or src.startswith("https://"):
                return m.group(0)

            # Extract resource filename (e.g. from image://local/abc.jpg)
            raw_name = src.replace(LOCAL_IMAGE_URL_PREFIX, "").split("/")[-1]

            jpeg_bytes: Optional[bytes] = None

            # 1. Check in-memory cache
            if raw_name in self.in_memory_images:
                jpeg_bytes = self.in_memory_images[raw_name]

            # 2. Check database repository if available
            if not jpeg_bytes and self.image_service and getattr(self.image_service, "repo", None):
                try:
                    jpeg_bytes = self.image_service.repo.get_image(self.scratchpad_id, raw_name)
                    if not jpeg_bytes and hasattr(self.image_service.repo, "db"):
                        conn = self.image_service.repo.db.get_connection()
                        row = conn.execute(
                            "SELECT image_data FROM scratchpad_images WHERE image_name = ?",
                            (raw_name,),
                        ).fetchone()
                        if row:
                            jpeg_bytes = row["image_data"]
                except Exception:
                    pass

            # 3. Retrieve QImage from QTextDocument resources
            res = self.document().resource(QTextDocument.ImageResource, QUrl(src))
            if not isinstance(res, QImage) or res.isNull():
                res = self.document().resource(QTextDocument.ImageResource, QUrl(f"{LOCAL_IMAGE_URL_PREFIX}{raw_name}"))
            if not isinstance(res, QImage) or res.isNull():
                res = self.document().resource(QTextDocument.ImageResource, QUrl(raw_name))

            if isinstance(res, QImage) and not res.isNull():
                if first_qimage is None:
                    first_qimage = res
                if not jpeg_bytes:
                    buffer = QBuffer()
                    buffer.open(QIODevice.WriteOnly)
                    res.save(buffer, "JPEG", 85)
                    jpeg_bytes = bytes(buffer.data())
                    buffer.close()
            elif jpeg_bytes and first_qimage is None:
                loaded_img = QImage()
                if loaded_img.loadFromData(jpeg_bytes, "JPEG"):
                    first_qimage = loaded_img

            if jpeg_bytes:
                b64 = base64.b64encode(jpeg_bytes).decode("ascii")
                data_uri = f"data:image/jpeg;base64,{b64}"
                return f"{prefix}{data_uri}{suffix}"

            return m.group(0)

        enriched_html = img_pattern.sub(repl, html)

        # Sanitize task://toggle anchors for external applications so they don't appear as dead links
        enriched_html = re.sub(
            r'<a\s+[^>]*href=["\']task://toggle["\'][^>]*>(.*?)</a>',
            r'<span style="font-family: Consolas, monospace; font-size: 13px; font-weight: bold; color: #4ade80;">\1</span>',
            enriched_html,
            flags=re.IGNORECASE | re.DOTALL,
        )

        return enriched_html, first_qimage

    def createMimeDataFromSelection(self) -> QMimeData:
        """Generates self-contained clipboard data preserving rich text, colors, and embedded images.

        When highlighting text, formatting, and images, the images are embedded as Base64 data URIs
        inside the HTML clipboard payload. Raw bitmap data is also populated whenever an image is
        selected so that chat apps, image viewers, and file-drop targets can paste the image directly.
        """
        mime_data = super().createMimeDataFromSelection()
        if not mime_data:
            return mime_data

        if mime_data.hasHtml():
            html = mime_data.html()
            enriched_html, first_qimage = self._enrich_html_with_base64_images(html)
            mime_data.setHtml(enriched_html)

            # Always populate raw bitmap data if an image is part of the selection!
            # Enables pasting images into chat boxes (Antigravity, Slack, Teams, Discord),
            # web forms, Paint, and graphics software even when text is also highlighted.
            if first_qimage is not None and not first_qimage.isNull():
                mime_data.setImageData(first_qimage)

            # In plain text, replace Unicode object replacement character \uFFFC with [Screenshot]
            # and collapse excessive blank lines so terminal/text pastes are neat and clean.
            plain_text = mime_data.text()
            if "\uFFFC" in plain_text:
                plain_text = plain_text.replace("\uFFFC", " [Screenshot] ")
            plain_text = re.sub(r'\n{3,}', '\n\n', plain_text)
            mime_data.setText(plain_text)

        return mime_data

    def copy_formatted_note(self) -> None:
        """Copies the entire note with rich formatting, colors, and embedded Base64 images to clipboard."""
        full_html = self.toHtml()
        enriched_html, first_qimage = self._enrich_html_with_base64_images(full_html)

        clean_plain = self.toPlainText().replace("\uFFFC", " [Screenshot] ")
        clean_plain = re.sub(r'\n{3,}', '\n\n', clean_plain)

        mime_data = QMimeData()
        mime_data.setHtml(enriched_html)
        mime_data.setText(clean_plain)
        if first_qimage is not None and not first_qimage.isNull():
            mime_data.setImageData(first_qimage)

        QApplication.clipboard().setMimeData(mime_data)

    def keyPressEvent(self, event: QKeyEvent) -> None:
        """Handles browser-style tab shortcuts and auto-formats typed URLs."""
        mods = event.modifiers()
        has_ctrl = bool(mods & Qt.ControlModifier)
        has_shift = bool(mods & Qt.ShiftModifier)

        # Handle image deletion when an image is selected
        if self._selected_image_pos is not None:
            if event.key() in (Qt.Key_Delete, Qt.Key_Backspace):
                c = self.textCursor()
                c.setPosition(self._selected_image_pos)
                c.setPosition(self._selected_image_pos + 1, QTextCursor.KeepAnchor)
                c.removeSelectedText()
                self._selected_image_pos = None
                self.viewport().update()
                event.accept()
                return
            elif not has_ctrl and not bool(mods & Qt.AltModifier):
                self._selected_image_pos = None
                self.viewport().update()

        # 1. Slide / Move tab left or right: Ctrl+Shift+PageDown / PageUp
        if has_ctrl and has_shift:
            if event.key() == Qt.Key_C:
                self.copy_formatted_note()
                if parent_win := self.window():
                    if hasattr(parent_win, "status_bar"):
                        parent_win.status_bar.showMessage("✓ Copied formatted note (rich text & images) to clipboard!", 3500)
                event.accept()
                return
            elif event.key() == Qt.Key_PageDown:
                self.move_tab_requested.emit(+1)
                event.accept()
                return
            elif event.key() == Qt.Key_PageUp:
                self.move_tab_requested.emit(-1)
                event.accept()
                return

        # 2. Switch tab next or previous: Ctrl+PageDown / PageUp
        if has_ctrl and not has_shift:
            if event.key() == Qt.Key_PageDown:
                self.switch_tab_requested.emit(+1)
                event.accept()
                return
            elif event.key() == Qt.Key_PageUp:
                self.switch_tab_requested.emit(-1)
                event.accept()
                return

        # 3. Insert / Toggle Checklist Item: Ctrl+Alt+L
        if has_ctrl and bool(mods & Qt.AltModifier) and event.key() == Qt.Key_L:
            self.insert_checklist_item()
            event.accept()
            return

        # 4. Handle Enter continuation for checklists
        if event.key() in (Qt.Key_Return, Qt.Key_Enter):
            cursor = self.textCursor()
            block = cursor.block()
            text = block.text().strip()
            if text in ("[ ]", "[✔]", "[x]", "[X]", "- [ ]", "- [x]"):
                # Empty checkbox line: user pressed enter to finish list
                cursor.select(QTextCursor.BlockUnderCursor)
                cursor.insertText("")
                event.accept()
                self._emit_checklist_stats()
                return
            elif text.startswith(("[ ]", "[✔]", "[x]", "[X]", "- [ ]", "- [x]")):
                # Checklist line with text: continue checklist on next line
                super().keyPressEvent(event)
                self.insert_checklist_item()
                event.accept()
                return

        super().keyPressEvent(event)

        # 5. Auto-convert [] or [ ] or - [ ] typed at line start when pressing space
        if event.key() == Qt.Key_Space:
            cursor = self.textCursor()
            block = cursor.block()
            text = block.text()
            trimmed = text.strip()
            if trimmed in ("[]", "[ ]", "- []", "- [ ]"):
                cursor.setPosition(block.position())
                cursor.setPosition(block.position() + len(text), QTextCursor.KeepAnchor)
                cursor.insertHtml(self.CHECKBOX_UNCHECKED_HTML)
                self.setTextCursor(cursor)
                self._emit_checklist_stats()
                return
            self._auto_link_preceding_word()

        elif event.key() in (Qt.Key_Return, Qt.Key_Enter):
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

    def insert_template_html(self, html: str) -> None:
        """
        Inserts structured or custom template HTML at the current cursor position, unpacking
        any embedded Base64 data URIs into local JPEG resources and updating in-memory caches.
        """
        data_uri_pattern = re.compile(
            r'''src=["']data:image/([a-zA-Z0-9]+);base64,([A-Za-z0-9+/=\s]+)["']''',
            re.IGNORECASE,
        )

        def repl(match: re.Match) -> str:
            b64_str = match.group(2).replace("\n", "").replace("\r", "").strip()
            try:
                raw_bytes = base64.b64decode(b64_str)
                if self.image_service:
                    image_name, resource_url, jpeg_bytes, qimage = self.image_service.create_embedded_image(raw_bytes)
                else:
                    image_name = f"{uuid.uuid4().hex}.jpg"
                    resource_url = f"{LOCAL_IMAGE_URL_PREFIX}{image_name}"
                    qimage = QImage()
                    qimage.loadFromData(raw_bytes)
                    jpeg_bytes = raw_bytes

                self.in_memory_images[image_name] = jpeg_bytes
                if self.image_service:
                    self.image_service.register_image_in_document(self.document(), image_name, qimage)
                else:
                    self.document().addResource(QTextDocument.ImageResource, QUrl(resource_url), qimage)
                return f'src="{resource_url}"'
            except Exception:
                return match.group(0)

        processed_html = data_uri_pattern.sub(repl, html)
        cursor = self.textCursor()
        cursor.insertHtml(processed_html)
        self.setTextCursor(cursor)
        self.ensureCursorVisible()
        self._on_text_changed()

    def load_content(self, html_content: str) -> None:
        """Populates document and loads all stored images from SQLite into document resources."""
        self.blockSignals(True)
        self.image_service.load_scratchpad_images_into_document(self.scratchpad_id, self.document())
        self.setHtml(html_content)
        self.blockSignals(False)
        self._emit_checklist_stats()

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

    def _get_resize_handle_rect(self, rect: QRect) -> QRect:
        """Calculates bottom-right corner resize handle bounding box for an image."""
        handle_size = 9
        return QRect(rect.right() - handle_size + 1, rect.bottom() - handle_size + 1, handle_size, handle_size)

    def _get_image_info_at_doc_pos(self, doc_pos: int) -> Optional[dict]:
        """Returns geometry and metadata for the image at character index doc_pos."""
        if doc_pos < 0 or doc_pos >= self.document().characterCount():
            return None
        c = self.textCursor()
        c.setPosition(doc_pos)
        c.setPosition(doc_pos + 1, QTextCursor.KeepAnchor)
        fmt = c.charFormat()
        if not fmt.isImageFormat():
            return None
        img_fmt = fmt.toImageFormat()
        name = img_fmt.name()

        res = self.document().resource(QTextDocument.ImageResource, QUrl(name))
        if not isinstance(res, QImage) or res.isNull():
            raw_name = name.replace(LOCAL_IMAGE_URL_PREFIX, "").split("/")[-1]
            res = self.document().resource(QTextDocument.ImageResource, QUrl(f"{LOCAL_IMAGE_URL_PREFIX}{raw_name}"))
        if not isinstance(res, QImage) or res.isNull():
            raw_name = name.replace(LOCAL_IMAGE_URL_PREFIX, "").split("/")[-1]
            res = self.document().resource(QTextDocument.ImageResource, QUrl(raw_name))

        orig_w = res.width() if isinstance(res, QImage) and not res.isNull() else 100
        orig_h = res.height() if isinstance(res, QImage) and not res.isNull() else 100
        curr_w = int(img_fmt.width()) if img_fmt.width() > 0 else orig_w
        curr_h = int(img_fmt.height()) if img_fmt.height() > 0 else orig_h

        c0 = self.textCursor()
        c0.setPosition(doc_pos)
        c1 = self.textCursor()
        c1.setPosition(doc_pos + 1)
        r0 = self.cursorRect(c0)
        r1 = self.cursorRect(c1)
        w = r1.left() - r0.left()
        h = r0.height()
        rect = QRect(r0.left(), r0.top(), max(1, w if w > 0 else curr_w), max(1, h if h > 0 else curr_h))

        return {
            "pos": doc_pos,
            "name": name,
            "qimage": res,
            "current_width": curr_w,
            "current_height": curr_h,
            "original_width": orig_w,
            "original_height": orig_h,
            "rect": rect,
        }

    def _get_image_info_at_pos(self, pt: QPoint) -> Optional[dict]:
        """Checks if viewport position pt intersects an embedded image."""
        c = self.cursorForPosition(pt)
        pos = c.position()
        doc_len = self.document().characterCount()

        # Check candidate character positions around the hit point
        for candidate in (pos, pos - 1, pos + 1):
            if 0 <= candidate < doc_len:
                info = self._get_image_info_at_doc_pos(candidate)
                if info and info["rect"].adjusted(-3, -3, 3, 3).contains(pt):
                    return info

        return None

    def _get_image_at_pos(self, pos: QPoint) -> Optional[Tuple[str, QImage]]:
        """Checks if the given viewport position is over an embedded image (legacy/public API)."""
        info = self._get_image_info_at_pos(pos)
        if info and isinstance(info["qimage"], QImage) and not info["qimage"].isNull():
            return info["name"], info["qimage"]
        return None

    def _apply_image_size(self, pos: int, width: int, height: int) -> None:
        """Applies new width and height to the QTextImageFormat at character index pos."""
        if pos < 0 or pos >= self.document().characterCount():
            return
        c = self.textCursor()
        c.setPosition(pos)
        c.setPosition(pos + 1, QTextCursor.KeepAnchor)
        fmt = c.charFormat()
        if fmt.isImageFormat():
            img_fmt = fmt.toImageFormat()
            img_fmt.setWidth(float(width))
            img_fmt.setHeight(float(height))
            c.setCharFormat(img_fmt)
            self.viewport().update()

    def resize_image_at(self, pos: int, width: int, height: int) -> None:
        """Public API allowing programmatic proportional or custom image resizing."""
        self._apply_image_size(pos, width, height)

    def _quick_resize_image(self, info: dict, mode) -> None:
        """Resizes image via context menu preset or fits pane width."""
        pos = info["pos"]
        orig_w = info["original_width"]
        orig_h = info["original_height"]
        aspect = orig_w / max(1, orig_h)

        if mode == "fit":
            # Compute available width inside this editor pane (works in both normal and split views)
            avail_w = max(50, self.viewport().width() - 24)
            new_w = max(50, min(orig_w, avail_w))
            new_h = max(20, int(round(new_w / aspect)))
        else:
            pct = float(mode)
            new_w = max(20, int(round(orig_w * pct)))
            new_h = max(20, int(round(orig_h * pct)))

        self._apply_image_size(pos, new_w, new_h)
        if parent_win := self.window():
            if hasattr(parent_win, "status_bar"):
                parent_win.status_bar.showMessage(f"✓ Resized image to {new_w} × {new_h} px", 3000)

    def _open_resize_dialog(self, info: dict) -> None:
        """Opens the ResizeImageDialog for custom dimensions with aspect ratio lock."""
        pos = info["pos"]
        avail_w = max(50, self.viewport().width() - 24)
        dlg = ResizeImageDialog(
            current_width=info["current_width"],
            current_height=info["current_height"],
            original_width=info["original_width"],
            original_height=info["original_height"],
            max_pane_width=avail_w,
            parent=self,
        )
        if dlg.exec() == QDialog.Accepted:
            new_w, new_h = dlg.get_dimensions()
            self._apply_image_size(pos, new_w, new_h)
            if parent_win := self.window():
                if hasattr(parent_win, "status_bar"):
                    parent_win.status_bar.showMessage(f"✓ Resized image to {new_w} × {new_h} px", 3000)

    def mouseMoveEvent(self, event: QMouseEvent) -> None:
        # 1. Active interactive resize dragging
        if getattr(self, "_is_resizing_image", False) and self._selected_image_pos is not None:
            dx = event.pos().x() - self._resize_start_pos.x()
            dy = event.pos().y() - self._resize_start_pos.y()
            if event.modifiers() & Qt.ShiftModifier:
                new_w = max(20, int(self._resize_orig_width + dx))
                new_h = max(20, int(self._resize_orig_height + dy))
            else:
                new_w = max(20, int(self._resize_orig_width + dx))
                new_h = max(20, int(round(new_w / self._resize_aspect_ratio)))
            self._resize_current_width = new_w
            self._resize_current_height = new_h
            self.viewport().setCursor(Qt.SizeFDiagCursor)
            self.viewport().update()
            QToolTip.showText(self.mapToGlobal(event.pos()), f"{new_w} × {new_h} px (Hold Shift to unconstrain)", self)
            event.accept()
            return

        # 2. Check hover over corner resize handle of currently selected image
        if self._selected_image_pos is not None:
            info = self._get_image_info_at_doc_pos(self._selected_image_pos)
            if info:
                handle_rect = self._get_resize_handle_rect(info["rect"])
                if handle_rect.adjusted(-4, -4, 4, 4).contains(event.pos()):
                    self.viewport().setCursor(Qt.SizeFDiagCursor)
                    self.setToolTip("Drag to resize image (Hold Shift to unlock aspect ratio)")
                    super().mouseMoveEvent(event)
                    return

        # 3. Check hover over any image
        info = self._get_image_info_at_pos(event.pos())
        if info:
            self.viewport().setCursor(Qt.PointingHandCursor)
            self.setToolTip("Click to select image • Double-click or Right-click to resize")
            super().mouseMoveEvent(event)
            return

        # 4. Standard link and checklist anchors
        anchor = self.anchorAt(event.pos())
        if anchor:
            if anchor.startswith("task://"):
                self.viewport().setCursor(Qt.PointingHandCursor)
                self.setToolTip("Click to toggle task completion")
            else:
                self.viewport().setCursor(Qt.PointingHandCursor)
                self.setToolTip(f"Open link: {anchor}")
        else:
            self.viewport().setCursor(Qt.IBeamCursor)
            self.setToolTip("")
        super().mouseMoveEvent(event)

    def eventFilter(self, watched, event):
        if watched == self.viewport() and event.type() in (QEvent.MouseButtonPress, QEvent.FocusIn):
            self.setFocus()
            self.editor_focused.emit(self.scratchpad_id)
        return super().eventFilter(watched, event)

    def mousePressEvent(self, event: QMouseEvent) -> None:
        self.setFocus()
        self.editor_focused.emit(self.scratchpad_id)
        if event.button() == Qt.LeftButton:
            # 1. Check if clicking on the resize handle of an already selected image
            if self._selected_image_pos is not None:
                img_info = self._get_image_info_at_doc_pos(self._selected_image_pos)
                if img_info:
                    handle_rect = self._get_resize_handle_rect(img_info["rect"])
                    if handle_rect.adjusted(-4, -4, 4, 4).contains(event.pos()):
                        self._is_resizing_image = True
                        self._resize_start_pos = event.pos()
                        self._resize_orig_width = img_info["current_width"]
                        self._resize_orig_height = img_info["current_height"]
                        self._resize_current_width = img_info["current_width"]
                        self._resize_current_height = img_info["current_height"]
                        self._resize_aspect_ratio = img_info["original_width"] / max(1, img_info["original_height"])
                        event.accept()
                        return

            # 2. Check if clicking on an image to select it
            clicked_img = self._get_image_info_at_pos(event.pos())
            if clicked_img:
                self._selected_image_pos = clicked_img["pos"]
                self.viewport().update()
                c = self.textCursor()
                c.setPosition(clicked_img["pos"] + 1)
                self.setTextCursor(c)
                event.accept()
                return
            else:
                if self._selected_image_pos is not None:
                    self._selected_image_pos = None
                    self.viewport().update()

            self._pressed_anchor = self.anchorAt(event.pos())
        else:
            self._pressed_anchor = ""
        super().mousePressEvent(event)

    def mouseDoubleClickEvent(self, event: QMouseEvent) -> None:
        """Opens ResizeImageDialog if double-clicking an embedded image."""
        img_info = self._get_image_info_at_pos(event.pos())
        if img_info:
            self._open_resize_dialog(img_info)
            event.accept()
            return
        super().mouseDoubleClickEvent(event)

    def mouseReleaseEvent(self, event: QMouseEvent) -> None:
        """Applies dragged resize dimensions, launches external links, or toggles task checkboxes."""
        if getattr(self, "_is_resizing_image", False) and self._selected_image_pos is not None:
            self._is_resizing_image = False
            new_w = getattr(self, "_resize_current_width", 0)
            new_h = getattr(self, "_resize_current_height", 0)
            if new_w > 0 and new_h > 0:
                self._apply_image_size(self._selected_image_pos, new_w, new_h)
                if parent_win := self.window():
                    if hasattr(parent_win, "status_bar"):
                        parent_win.status_bar.showMessage(f"✓ Resized image to {new_w} × {new_h} px", 3000)
            self.viewport().setCursor(Qt.IBeamCursor)
            self.viewport().update()
            event.accept()
            return

        if event.button() == Qt.LeftButton:
            anchor = self.anchorAt(event.pos())
            if anchor and anchor == self._pressed_anchor:
                if anchor.startswith("task://"):
                    self._toggle_checkbox_at(event.pos())
                    event.accept()
                    return
                target_url = anchor if not anchor.startswith("www.") else f"http://{anchor}"
                QDesktopServices.openUrl(QUrl(target_url))
                event.accept()
                return

            # Direct click on bracket checkboxes even if anchor wasn't hit
            cursor = self.cursorForPosition(event.pos())
            block = cursor.block()
            line_text = block.text()
            pos_in_block = cursor.position() - block.position()
            for sym in ("[ ]", "[✔]", "[x]", "[X]"):
                if sym in line_text:
                    idx = line_text.find(sym)
                    if abs(pos_in_block - idx) <= 4:
                        self._toggle_checkbox_at(event.pos())
                        event.accept()
                        return
        super().mouseReleaseEvent(event)
        self.setFocus()
        self.editor_focused.emit(self.scratchpad_id)

    def paintEvent(self, event) -> None:
        super().paintEvent(event)
        if self._selected_image_pos is not None:
            img_info = self._get_image_info_at_doc_pos(self._selected_image_pos)
            if img_info:
                rect = img_info["rect"]
                painter = QPainter(self.viewport())
                painter.setRenderHint(QPainter.Antialiasing)

                # Selection outline
                pen = QPen(QColor("#007acc"), 2, Qt.SolidLine)
                painter.setPen(pen)
                painter.setBrush(Qt.NoBrush)
                painter.drawRect(rect)

                # Corner resize handle
                handle_rect = self._get_resize_handle_rect(rect)
                painter.setPen(QPen(QColor("#ffffff"), 1))
                painter.setBrush(QColor("#007acc"))
                painter.drawRect(handle_rect)

                # Rubber-band preview during drag resizing
                if getattr(self, "_is_resizing_image", False):
                    preview_w = getattr(self, "_resize_current_width", rect.width())
                    preview_h = getattr(self, "_resize_current_height", rect.height())
                    preview_rect = QRect(rect.left(), rect.top(), preview_w, preview_h)

                    preview_pen = QPen(QColor("#60a5fa"), 2, Qt.DashLine)
                    painter.setPen(preview_pen)
                    painter.setBrush(QColor(96, 165, 250, 35))
                    painter.drawRect(preview_rect)

                    dim_text = f" {preview_w} × {preview_h} px "
                    metrics = painter.fontMetrics()
                    text_w = metrics.horizontalAdvance(dim_text) + 8
                    text_h = metrics.height() + 4
                    badge_rect = QRect(preview_rect.right() - text_w, preview_rect.bottom() + 4, text_w, text_h)
                    painter.setPen(Qt.NoPen)
                    painter.setBrush(QColor(30, 30, 30, 220))
                    painter.drawRoundedRect(badge_rect, 3, 3)
                    painter.setPen(QColor("#ffffff"))
                    painter.drawText(badge_rect, Qt.AlignCenter, dim_text)

                painter.end()

    def focusInEvent(self, event) -> None:
        """Notifies main window when this editor receives focus for active tracking."""
        super().focusInEvent(event)
        self.setFocus()
        self.editor_focused.emit(self.scratchpad_id)

    def _copy_image_to_clipboard(self, qimage: QImage) -> None:
        """Copies image to system clipboard and notifies status bar."""
        QApplication.clipboard().setImage(qimage)
        if parent_win := self.window():
            if hasattr(parent_win, "status_bar"):
                parent_win.status_bar.showMessage("✓ Copied image to clipboard!", 3000)

    def _save_image_to_file(self, image_url: str, qimage: QImage) -> None:
        """Prompts save dialog and exports the image to PNG or JPEG on disk."""
        base_name = image_url.replace(LOCAL_IMAGE_URL_PREFIX, "").split("/")[-1]
        if not base_name.lower().endswith((".png", ".jpg", ".jpeg")):
            base_name = f"{base_name}.png"

        file_path, _ = QFileDialog.getSaveFileName(
            self,
            "Save Image As",
            base_name,
            "PNG Image (*.png);;JPEG Image (*.jpg *.jpeg);;All Files (*)",
        )
        if not file_path:
            return

        # Check if we have original JPEG bytes cached in memory or in SQLite
        raw_name = image_url.replace(LOCAL_IMAGE_URL_PREFIX, "")
        raw_bytes = self.in_memory_images.get(raw_name)
        if not raw_bytes and self.image_service:
            raw_bytes = self.image_service.repo.get_image(self.scratchpad_id, raw_name)

        if raw_bytes and (file_path.lower().endswith(".jpg") or file_path.lower().endswith(".jpeg")):
            with open(file_path, "wb") as f:
                f.write(raw_bytes)
        else:
            qimage.save(file_path)

        if parent_win := self.window():
            if hasattr(parent_win, "status_bar"):
                parent_win.status_bar.showMessage(f"✓ Saved image to {file_path}", 3500)

    def contextMenuEvent(self, event) -> None:
        """Provides enhanced context menu with image copy/export and technician quick-actions."""
        img_info_full = self._get_image_info_at_pos(event.pos())
        menu = QMenu(self)

        # 1. Image Actions (if right-clicking an embedded screenshot/image)
        if img_info_full:
            self._selected_image_pos = img_info_full["pos"]
            self.viewport().update()
            img_url = img_info_full["name"]
            qimage = img_info_full["qimage"]

            # Submenu: 📏 Quick Resize
            menu_resize = menu.addMenu("📏 Quick Resize")
            menu_resize.setToolTip("Quickly scale image to preset percentage or fit pane")

            act_fit = menu_resize.addAction("Fit to Pane Width")
            act_fit.triggered.connect(lambda checked=False, i=img_info_full: self._quick_resize_image(i, "fit"))

            menu_resize.addSeparator()
            act_100 = menu_resize.addAction("100% (Original Size)")
            act_100.triggered.connect(lambda checked=False, i=img_info_full: self._quick_resize_image(i, 1.0))

            act_75 = menu_resize.addAction("75%")
            act_75.triggered.connect(lambda checked=False, i=img_info_full: self._quick_resize_image(i, 0.75))

            act_50 = menu_resize.addAction("50%")
            act_50.triggered.connect(lambda checked=False, i=img_info_full: self._quick_resize_image(i, 0.50))

            act_25 = menu_resize.addAction("25%")
            act_25.triggered.connect(lambda checked=False, i=img_info_full: self._quick_resize_image(i, 0.25))

            act_dialog = menu.addAction("📐 Custom Resize...")
            act_dialog.setToolTip("Open resize dialog with custom dimensions and aspect ratio lock")
            act_dialog.triggered.connect(lambda checked=False, i=img_info_full: self._open_resize_dialog(i))

            menu.addSeparator()

            act_copy_img = menu.addAction("📋 Copy Image")
            act_copy_img.setToolTip("Copies raw image data to clipboard")
            act_copy_img.triggered.connect(lambda: self._copy_image_to_clipboard(qimage))

            act_save_img = menu.addAction("💾 Save Image As...")
            act_save_img.setToolTip("Export image to PNG or JPEG file on disk")
            act_save_img.triggered.connect(lambda: self._save_image_to_file(img_url, qimage))

            menu.addSeparator()

        # 2. Standard text editing context actions (Undo, Redo, Cut, Copy, Paste, Select All)
        standard_menu = self.createStandardContextMenu()
        for act in standard_menu.actions():
            menu.addAction(act)

        menu.addSeparator()

        act_copy_note = menu.addAction("📋 Copy Entire Formatted Note (Ctrl+Shift+C)")
        act_copy_note.setToolTip("Copies all note text, formatting, colors, and embedded images to clipboard")
        act_copy_note.triggered.connect(self._copy_entire_formatted_note_action)

        menu.addSeparator()

        # 3. Technician quick formatting actions
        act_checklist = menu.addAction("☑ Insert Checklist Item (Ctrl+Alt+L)")
        act_checklist.triggered.connect(self.insert_checklist_item)

        act_timestamp = menu.addAction("🕒 Insert Timestamp (F5 / Ctrl+Alt+T)")
        act_timestamp.triggered.connect(self._insert_timestamp)

        act_code = menu.addAction("</> Insert Code Block (Ctrl+Alt+C)")
        act_code.triggered.connect(self._insert_code_block)

        menu.exec(event.globalPos())

    def _copy_entire_formatted_note_action(self) -> None:
        """Copies the whole formatted note and surfaces a status bar message."""
        self.copy_formatted_note()
        if parent_win := self.window():
            if hasattr(parent_win, "status_bar"):
                parent_win.status_bar.showMessage("✓ Copied formatted note (rich text & images) to clipboard!", 3500)

    def _insert_timestamp(self) -> None:
        now_str = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
        self.textCursor().insertHtml(f"<strong>[{now_str}]</strong> ")

    def _insert_code_block(self) -> None:
        cursor = self.textCursor()
        selected = cursor.selectedText()
        content = selected if selected else "# CLI / PowerShell Log"
        html = f'<div style="background-color: #252526; border: 1px solid #3c3c3c; border-radius: 4px; padding: 6px; font-family: Consolas, monospace; color: #9cdcfe;"><code>{content}</code></div><br>'
        cursor.insertHtml(html)
