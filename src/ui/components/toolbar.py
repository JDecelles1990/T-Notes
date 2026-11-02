"""Formatting micro-toolbar for technician rich-text editing with shortcuts, opacity slider, and settings."""

from datetime import datetime
from typing import Callable, Optional
from PySide6.QtCore import Qt, Signal
from PySide6.QtGui import QAction, QColor, QFont, QIcon, QKeySequence, QTextCharFormat, QTextCursor
from PySide6.QtWidgets import (
    QColorDialog,
    QFileDialog,
    QHBoxLayout,
    QLabel,
    QMenu,
    QSizePolicy,
    QSlider,
    QToolBar,
    QToolButton,
    QWidget,
)
from src.core.constants import LOG_BADGES, TICKET_SKELETONS
from src.ui.components.stopwatch_widget import TicketStopwatchWidget


class TechPadToolBar(QToolBar):
    """Two-row technician formatting and system toolbar with zero overflow button."""

    image_requested = Signal()
    timestamp_requested = Signal()
    skeleton_selected = Signal(str)
    export_note_requested = Signal()
    code_block_requested = Signal()
    opacity_changed = Signal(int)       # Emits opacity value (60 to 100)
    history_requested = Signal()        # Emits when history button clicked
    settings_requested = Signal()       # Emits when gear icon clicked

    def __init__(self, parent: Optional[QWidget] = None):
        super().__init__("Formatting", parent)
        self.setMovable(False)
        self.setFloatable(False)
        self._current_editor = None

        # Row 2 Toolbar: Ticket Workflow, Stopwatch & System Tools
        self.secondary_toolbar = QToolBar("Workflow & Tools", parent)
        self.secondary_toolbar.setMovable(False)
        self.secondary_toolbar.setFloatable(False)

        self._setup_actions()
        self._suppress_extension_buttons()

    def set_active_editor(self, editor) -> None:
        """Binds toolbar formatting actions to the currently active editor."""
        self._current_editor = editor

    def _suppress_extension_buttons(self) -> None:
        """Suppresses the 3-dots overflow extension button across both toolbars."""
        for tb in (self, getattr(self, "secondary_toolbar", None)):
            if tb is not None:
                ext = tb.findChild(QToolButton, "qt_toolbar_ext_button")
                if ext:
                    ext.setVisible(False)
                    ext.setMaximumSize(0, 0)
                    ext.resize(0, 0)

    def showEvent(self, event) -> None:
        super().showEvent(event)
        self._suppress_extension_buttons()

    def resizeEvent(self, event) -> None:
        super().resizeEvent(event)
        self._suppress_extension_buttons()

    def _setup_actions(self) -> None:
        # Standard formatting: Bold, Italic, Underline
        self.act_bold = self.addAction("B")
        self.act_bold.setToolTip("Bold (Ctrl+B)")
        self.act_bold.setShortcut(QKeySequence("Ctrl+B"))
        self.act_bold.setCheckable(True)
        self.act_bold.triggered.connect(self._toggle_bold)

        self.act_italic = self.addAction("I")
        self.act_italic.setToolTip("Italic (Ctrl+I)")
        self.act_italic.setShortcut(QKeySequence("Ctrl+I"))
        self.act_italic.setCheckable(True)
        self.act_italic.triggered.connect(self._toggle_italic)

        self.act_underline = self.addAction("U")
        self.act_underline.setToolTip("Underline (Ctrl+U)")
        self.act_underline.setShortcut(QKeySequence("Ctrl+U"))
        self.act_underline.setCheckable(True)
        self.act_underline.triggered.connect(self._toggle_underline)

        self.addSeparator()

        # Monospace Code Block (Ctrl+Alt+C)
        self.act_code = self.addAction("</>")
        self.act_code.setToolTip("Monospace Code Block (Ctrl+Alt+C)")
        self.act_code.setShortcut(QKeySequence("Ctrl+Alt+C"))
        self.act_code.triggered.connect(self._insert_or_toggle_code_block)

        # Log Triage Badges Menu / Quick Buttons
        btn_badge = QToolButton(self)
        btn_badge.setText("🏷️ Tag")
        btn_badge.setPopupMode(QToolButton.InstantPopup)
        btn_badge.setToolTip("Insert Log Triage Badge (Alt+1..4)")
        badge_menu = QMenu(btn_badge)

        badge_shortcuts = {
            "PASS": "Alt+1",
            "FAIL": "Alt+2",
            "WARN": "Alt+3",
            "INFO": "Alt+4",
        }

        for tag_key, info in LOG_BADGES.items():
            sc = badge_shortcuts.get(tag_key, "")
            label = f"{info['label']} ({sc})" if sc else info["label"]
            act = badge_menu.addAction(label)
            if sc:
                act.setShortcut(QKeySequence(sc))
            act.triggered.connect(lambda checked=False, k=tag_key: self._insert_badge(k))
        btn_badge.setMenu(badge_menu)
        self.addWidget(btn_badge)

        # Color picker (Ctrl+Alt+X)
        self.act_color = self.addAction("🎨")
        self.act_color.setToolTip("Text Color (Ctrl+Alt+X)")
        self.act_color.setShortcut(QKeySequence("Ctrl+Alt+X"))
        self.act_color.triggered.connect(self._pick_text_color)

        # Highlight color picker (Ctrl+Alt+H)
        self.act_highlight = self.addAction("🖍️")
        self.act_highlight.setToolTip("Highlight Background Color (Ctrl+Alt+H)")
        self.act_highlight.setShortcut(QKeySequence("Ctrl+Alt+H"))
        self.act_highlight.triggered.connect(self._pick_highlight_color)

        self.addSeparator()

        # Media: Insert Image (Ctrl+Alt+I)
        self.act_image = self.addAction("🖼️")
        self.act_image.setToolTip("Insert Image File... (Ctrl+Alt+I)")
        self.act_image.setShortcut(QKeySequence("Ctrl+Alt+I"))
        self.act_image.triggered.connect(self.image_requested.emit)

        # Timestamp Insertion (F5 / Ctrl+Alt+T)
        self.act_timestamp = self.addAction("🕒")
        self.act_timestamp.setToolTip("Insert Current Timestamp (F5 / Ctrl+Alt+T)")
        self.act_timestamp.setShortcut(QKeySequence("F5"))
        self.act_timestamp.triggered.connect(self._insert_timestamp)

        # Ticket Skeletons Dropdown (Ctrl+Alt+S)
        self.btn_skeleton = QToolButton(self)
        self.btn_skeleton.setText("📋 Template")
        self.btn_skeleton.setPopupMode(QToolButton.InstantPopup)
        self.btn_skeleton.setToolTip("Insert Structured Ticket Skeleton (Ctrl+Alt+S)")
        skeleton_menu = QMenu(self.btn_skeleton)

        for name in TICKET_SKELETONS.keys():
            act = skeleton_menu.addAction(name)
            act.triggered.connect(lambda checked=False, n=name: self.skeleton_selected.emit(n))
        self.btn_skeleton.setMenu(skeleton_menu)
        self.addWidget(self.btn_skeleton)

        self.addSeparator()

        # Copy For Ticket Note (PSA Export - Ctrl+Alt+N)
        self.act_export = self.addAction("📤 Copy Note")
        self.act_export.setToolTip("Copy stripped clean text/markdown for PSA ticket (Ctrl+Alt+N)")
        self.act_export.setShortcut(QKeySequence("Ctrl+Alt+N"))
        self.act_export.triggered.connect(self.export_note_requested.emit)

        # -------------------------------------------------------------
        # Row 2: Workflow, Stopwatch, Opacity & Preferences
        # -------------------------------------------------------------

        # Stopwatch Widget for tracking ticket troubleshooting time
        self.stopwatch = TicketStopwatchWidget(parent=self.secondary_toolbar)
        self.stopwatch.psa_export_requested.connect(self.export_note_requested.emit)
        self.secondary_toolbar.addWidget(self.stopwatch)

        # Separator on row 2
        self.secondary_toolbar.addSeparator()

        # Expanding spacer pushing Opacity & Settings to the right side
        spacer = QWidget(self.secondary_toolbar)
        spacer.setSizePolicy(QSizePolicy.Expanding, QSizePolicy.Preferred)
        self.secondary_toolbar.addWidget(spacer)

        # Opacity Slider (60% to 100%)
        self.lbl_opacity = QLabel("👁️ 100%", self.secondary_toolbar)
        self.lbl_opacity.setStyleSheet("color: #9cdcfe; font-size: 11px; padding-right: 2px;")
        self.secondary_toolbar.addWidget(self.lbl_opacity)

        self.slider_opacity = QSlider(Qt.Horizontal, self.secondary_toolbar)
        self.slider_opacity.setRange(60, 100)
        self.slider_opacity.setValue(100)
        self.slider_opacity.setFixedWidth(85)
        self.slider_opacity.setToolTip("Window Opacity (60% – 100%)")
        self.slider_opacity.setStyleSheet("""
            QSlider::groove:horizontal {
                height: 4px;
                background: #3c3c3c;
                border-radius: 2px;
            }
            QSlider::sub-page:horizontal {
                background: #007acc;
                border-radius: 2px;
            }
            QSlider::handle:horizontal {
                background: #ffffff;
                width: 12px;
                margin-top: -4px;
                margin-bottom: -4px;
                border-radius: 6px;
            }
            QSlider::handle:horizontal:hover {
                background: #4fc1ff;
            }
        """)
        self.slider_opacity.valueChanged.connect(self._on_opacity_changed)
        self.secondary_toolbar.addWidget(self.slider_opacity)

        self.secondary_toolbar.addSeparator()

        # History Section Toggle Button (🕰️)
        self.btn_history = QToolButton(self.secondary_toolbar)
        self.btn_history.setText("🕰️")
        self.btn_history.setToolTip("Ticket History & Archive (Ctrl+H)")
        self.btn_history.setStyleSheet("font-size: 14px; padding: 2px 6px; margin-left: 4px;")
        self.btn_history.clicked.connect(self.history_requested.emit)
        self.secondary_toolbar.addWidget(self.btn_history)

        # Settings Gear Icon Button (⚙️)
        self.btn_settings = QToolButton(self.secondary_toolbar)
        self.btn_settings.setText("⚙️")
        self.btn_settings.setToolTip("Preferences & Settings (Ctrl+,)")
        self.btn_settings.setStyleSheet("font-size: 14px; padding: 2px 6px; margin-left: 4px;")
        self.btn_settings.clicked.connect(self.settings_requested.emit)
        self.secondary_toolbar.addWidget(self.btn_settings)

    def set_opacity_value(self, val: int) -> None:
        """Sets the slider value without emitting signals."""
        self.slider_opacity.blockSignals(True)
        self.slider_opacity.setValue(val)
        self.lbl_opacity.setText(f"👁️ {val}%")
        self.slider_opacity.blockSignals(False)

    def _on_opacity_changed(self, value: int) -> None:
        self.lbl_opacity.setText(f"👁️ {value}%")
        self.opacity_changed.emit(value)

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
            html = f'<div style="background-color: #252526; border: 1px solid #3c3c3c; border-radius: 4px; padding: 6px; font-family: Consolas, monospace; color: #9cdcfe;"><code>{selected}</code></div><br>'
            cursor.insertHtml(html)
        else:
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
