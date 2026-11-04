"""Customized QTextEdit for rich text, screenshots, drag-drop, and clickable links."""

import base64
import uuid
from datetime import datetime
from pathlib import Path
import re
from typing import Dict, Optional, Tuple
from PySide6.QtCore import QBuffer, QIODevice, QMimeData, QPoint, Qt, QUrl, Signal
from PySide6.QtGui import (
    QColor,
    QDesktopServices,
    QDragEnterEvent,
    QDropEvent,
    QFont,
    QImage,
    QKeyEvent,
    QMouseEvent,
    QTextCharFormat,
    QTextCursor,
    QTextDocument,
)
from PySide6.QtWidgets import (
    QApplication,
    QFileDialog,
    QMenu,
    QMessageBox,
    QTextEdit,
)
from src.core.constants import LOCAL_IMAGE_URL_PREFIX
from src.services.image_service import ImageService


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

        self.setAcceptDrops(True)
        self.setMouseTracking(True)
        self.textChanged.connect(self._on_text_changed)
        self.cursorPositionChanged.connect(self._on_cursor_or_focus)

    def _on_cursor_or_focus(self) -> None:
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

    def mouseMoveEvent(self, event: QMouseEvent) -> None:
        """Shows pointing hand cursor when hovering over hyperlinks or task checkboxes."""
        anchor = self.anchorAt(event.pos())
        if anchor:
            self.viewport().setCursor(Qt.PointingHandCursor)
            if anchor.startswith("task://"):
                self.setToolTip("Click to toggle task completion")
            else:
                self.setToolTip(f"Open link: {anchor}")
        else:
            self.viewport().setCursor(Qt.IBeamCursor)
            self.setToolTip("")
        super().mouseMoveEvent(event)

    def mousePressEvent(self, event: QMouseEvent) -> None:
        self.editor_focused.emit(self.scratchpad_id)
        if event.button() == Qt.LeftButton:
            self._pressed_anchor = self.anchorAt(event.pos())
        else:
            self._pressed_anchor = ""
        super().mousePressEvent(event)

    def mouseReleaseEvent(self, event: QMouseEvent) -> None:
        """Launches external browser when clicking on an anchor or toggles task checkboxes."""
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
        self.editor_focused.emit(self.scratchpad_id)

    def focusInEvent(self, event) -> None:
        """Notifies main window when this editor receives focus for active tracking."""
        super().focusInEvent(event)
        self.editor_focused.emit(self.scratchpad_id)

    def _get_image_at_pos(self, pos: QPoint) -> Optional[Tuple[str, QImage]]:
        """Checks if the given viewport position is over an embedded image.

        Returns (resource_url, qimage) if found, else None.
        """
        cursor = self.cursorForPosition(pos)

        def check_format(c: QTextCursor) -> Optional[str]:
            fmt = c.charFormat()
            if fmt.isImageFormat():
                return fmt.toImageFormat().name()
            return None

        # 1. Direct cursor position check
        name = check_format(cursor)

        # 2. Check char immediately to the left
        if not name:
            c_left = QTextCursor(cursor)
            if c_left.movePosition(QTextCursor.Left, QTextCursor.KeepAnchor):
                name = check_format(c_left)

        # 3. Check char immediately to the right
        if not name:
            c_right = QTextCursor(cursor)
            if c_right.movePosition(QTextCursor.Right, QTextCursor.KeepAnchor):
                name = check_format(c_right)

        if not name:
            return None

        # Retrieve QImage from document resources
        res = self.document().resource(QTextDocument.ImageResource, QUrl(name))
        if isinstance(res, QImage) and not res.isNull():
            return name, res

        return None

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
        img_info = self._get_image_at_pos(event.pos())
        menu = QMenu(self)

        # 1. Image Actions (if right-clicking an embedded screenshot/image)
        if img_info:
            img_url, qimage = img_info
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
