"""Customized QTextEdit for rich text, screenshots, drag-drop, and clickable links."""

from datetime import datetime
from pathlib import Path
import re
from typing import Dict, Optional
from PySide6.QtCore import QMimeData, QPoint, Qt, QUrl, Signal
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
from PySide6.QtWidgets import QMenu, QMessageBox, QTextEdit
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

    def keyPressEvent(self, event: QKeyEvent) -> None:
        """Handles browser-style tab shortcuts and auto-formats typed URLs."""
        mods = event.modifiers()
        has_ctrl = bool(mods & Qt.ControlModifier)
        has_shift = bool(mods & Qt.ShiftModifier)

        # 1. Slide / Move tab left or right: Ctrl+Shift+PageDown / PageUp
        if has_ctrl and has_shift:
            if event.key() == Qt.Key_PageDown:
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

    def focusInEvent(self, event) -> None:
        """Notifies main window when this editor receives focus for active tracking."""
        super().focusInEvent(event)
        self.editor_focused.emit(self.scratchpad_id)

    def contextMenuEvent(self, event) -> None:
        """Provides enhanced context menu with screenshot paste and technician quick-actions."""
        menu = self.createStandardContextMenu()
        menu.addSeparator()

        act_checklist = menu.addAction("☑ Insert Checklist Item (Ctrl+Alt+L)")
        act_checklist.triggered.connect(self.insert_checklist_item)

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
