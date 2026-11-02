"""Formatting micro-toolbar for technician rich-text editing."""

from datetime import datetime
from typing import Callable, Optional
from PySide6.QtCore import Qt, Signal
from PySide6.QtGui import QAction, QColor, QFont, QIcon, QTextCharFormat, QTextCursor
from PySide6.QtWidgets import (
    QColorDialog,
    QFileDialog,
    QMenu,
    QToolBar,
    QToolButton,
    QWidget,
)
from src.core.constants import LOG_BADGES, TICKET_SKELETONS


class TechPadToolBar(QToolBar):
    """Compact technician formatting toolbar."""

    image_requested = Signal()
    timestamp_requested = Signal()
    skeleton_selected = Signal(str)
    export_note_requested = Signal()
    code_block_requested = Signal()

    def __init__(self, parent: Optional[QWidget] = None):
        super().__init__("Formatting", parent)
        self.setMovable(False)
        self._current_editor = None
        self._setup_actions()

    def set_active_editor(self, editor) -> None:
        """Binds toolbar formatting actions to the currently active editor."""
        self._current_editor = editor

    def _setup_actions(self) -> None:
        # Standard formatting: Bold, Italic, Underline
        self.act_bold = self.addAction("B")
        self.act_bold.setToolTip("Bold (Ctrl+B)")
        self.act_bold.setShortcut("Ctrl+B")
        self.act_bold.setCheckable(True)
        self.act_bold.triggered.connect(self._toggle_bold)

        self.act_italic = self.addAction("I")
        self.act_italic.setToolTip("Italic (Ctrl+I)")
        self.act_italic.setShortcut("Ctrl+I")
        self.act_italic.setCheckable(True)
        self.act_italic.triggered.connect(self._toggle_italic)

        self.act_underline = self.addAction("U")
        self.act_underline.setToolTip("Underline (Ctrl+U)")
        self.act_underline.setShortcut("Ctrl+U")
        self.act_underline.setCheckable(True)
        self.act_underline.triggered.connect(self._toggle_underline)

        self.addSeparator()

        # Monospace Code Block
        self.act_code = self.addAction("</>")
        self.act_code.setToolTip("Monospace Code Block (PowerShell / CLI Log)")
        self.act_code.triggered.connect(self._insert_or_toggle_code_block)

        # Log Triage Badges Menu / Quick Buttons
        btn_badge = QToolButton(self)
        btn_badge.setText("🏷️ Tag")
        btn_badge.setPopupMode(QToolButton.InstantPopup)
        btn_badge.setToolTip("Insert Log Triage Badge")
        badge_menu = QMenu(btn_badge)

        for tag_key, info in LOG_BADGES.items():
            act = badge_menu.addAction(info["label"])
            act.triggered.connect(lambda checked=False, k=tag_key: self._insert_badge(k))
        btn_badge.setMenu(badge_menu)
        self.addWidget(btn_badge)

        # Color picker
        self.act_color = self.addAction("🎨")
        self.act_color.setToolTip("Text Color")
        self.act_color.triggered.connect(self._pick_text_color)

        # Highlight color picker
        self.act_highlight = self.addAction("🖍️")
        self.act_highlight.setToolTip("Highlight Background Color")
        self.act_highlight.triggered.connect(self._pick_highlight_color)

        self.addSeparator()

        # Media: Insert Image
        self.act_image = self.addAction("🖼️")
        self.act_image.setToolTip("Insert Image File...")
        self.act_image.triggered.connect(self.image_requested.emit)

        # Timestamp Insertion
        self.act_timestamp = self.addAction("🕒")
        self.act_timestamp.setToolTip("Insert Current Timestamp (Ctrl+Shift+T)")
        self.act_timestamp.setShortcut("Ctrl+Shift+T")
        self.act_timestamp.triggered.connect(self._insert_timestamp)

        # Ticket Skeletons Dropdown
        btn_skeleton = QToolButton(self)
        btn_skeleton.setText("📋 Template")
        btn_skeleton.setPopupMode(QToolButton.InstantPopup)
        btn_skeleton.setToolTip("Insert Structured Ticket Skeleton")
        skeleton_menu = QMenu(btn_skeleton)

        for name in TICKET_SKELETONS.keys():
            act = skeleton_menu.addAction(name)
            act.triggered.connect(lambda checked=False, n=name: self.skeleton_selected.emit(n))
        btn_skeleton.setMenu(skeleton_menu)
        self.addWidget(btn_skeleton)

        self.addSeparator()

        # Copy For Ticket Note (PSA Export)
        self.act_export = self.addAction("📤 Copy Note")
        self.act_export.setToolTip("Copy stripped clean text/markdown for PSA ticket")
        self.act_export.triggered.connect(self.export_note_requested.emit)

    def _toggle_bold(self) -> None:
        if self._current_editor:
            fmt = QTextCharFormat()
            fmt.setFontWeight(QFont.Bold if self.act_bold.isChecked() else QFont.Normal)
            self._current_editor.mergeCurrentCharFormat(fmt)

    def _toggle_italic(self) -> None:
        if self._current_editor:
            fmt = QTextCharFormat()
            fmt.setFontItalic(self.act_italic.isChecked())
            self._current_editor.mergeCurrentCharFormat(fmt)

    def _toggle_underline(self) -> None:
        if self._current_editor:
            fmt = QTextCharFormat()
            fmt.setFontUnderline(self.act_underline.isChecked())
            self._current_editor.mergeCurrentCharFormat(fmt)

    def _pick_text_color(self) -> None:
        if not self._current_editor:
            return
        color = QColorDialog.getColor(Qt.white, self, "Select Text Color")
        if color.isValid():
            fmt = QTextCharFormat()
            fmt.setForeground(color)
            self._current_editor.mergeCurrentCharFormat(fmt)

    def _pick_highlight_color(self) -> None:
        if not self._current_editor:
            return
        color = QColorDialog.getColor(QColor("#264f78"), self, "Select Highlight Color")
        if color.isValid():
            fmt = QTextCharFormat()
            fmt.setBackground(color)
            self._current_editor.mergeCurrentCharFormat(fmt)

    def _insert_or_toggle_code_block(self) -> None:
        if not self._current_editor:
            return
        cursor = self._current_editor.textCursor()
        selected = cursor.selectedText()
        if selected:
            # Inline/block code
            html = f'<div style="background-color: #252526; border: 1px solid #3c3c3c; border-radius: 4px; padding: 6px; font-family: Consolas, monospace; color: #9cdcfe;"><code>{selected}</code></div><br>'
            cursor.insertHtml(html)
        else:
            # Insert empty snippet container
            html = '<div style="background-color: #252526; border: 1px solid #3c3c3c; border-radius: 4px; padding: 6px; font-family: Consolas, monospace; color: #9cdcfe;"><code># CLI / PowerShell Output</code></div><br>'
            cursor.insertHtml(html)

    def _insert_badge(self, tag_key: str) -> None:
        if not self._current_editor:
            return
        info = LOG_BADGES.get(tag_key)
        if not info:
            return
        badge_html = f'&nbsp;<span style="background-color: {info["bg_color"]}; color: {info["text_color"]}; border: 1px solid {info["border_color"]}; border-radius: 3px; padding: 2px 6px; font-weight: bold; font-size: 11px;">{info["label"]}</span>&nbsp;'
        cursor = self._current_editor.textCursor()
        cursor.insertHtml(badge_html)

    def _insert_timestamp(self) -> None:
        if not self._current_editor:
            return
        now_str = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
        tag = f'<strong>[{now_str}]</strong> '
        cursor = self._current_editor.textCursor()
        cursor.insertHtml(tag)

    def update_format_states(self, format: QTextCharFormat) -> None:
        """Updates bold/italic/underline action states based on current cursor position."""
        self.act_bold.setChecked(format.fontWeight() == QFont.Bold)
        self.act_italic.setChecked(format.fontItalic())
        self.act_underline.setChecked(format.fontUnderline())

