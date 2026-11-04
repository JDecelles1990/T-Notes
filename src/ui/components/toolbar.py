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
    add_template_requested = Signal()   # Emits when '🔳 Add a new template' is clicked
    copy_formatted_requested = Signal() # Emits when rich formatted copy requested
    export_note_requested = Signal()
    code_block_requested = Signal()
    checklist_requested = Signal()      # Emits when checklist button clicked
    split_view_requested = Signal()     # Emits when split view toggle clicked
    mini_hud_requested = Signal()       # Emits when Always-on-Top Mini-HUD toggle clicked
    opacity_changed = Signal(int)       # Emits opacity value (60 to 100)
    history_requested = Signal()        # Emits when history button clicked
    settings_requested = Signal()       # Emits when gear icon clicked
    m365_requested = Signal()           # Workspace navigation only

    def __init__(self, parent: Optional[QWidget] = None):
        super().__init__("Formatting", parent)
        self.setMovable(False)
        self.setFloatable(False)
        self._current_editor = None
        self._is_compact: bool = False

        # Row 2 Toolbar: Ticket Workflow, Stopwatch & System Tools
        self.secondary_toolbar = QToolBar("Workflow & Tools", parent)
        self.secondary_toolbar.setMovable(False)
        self.secondary_toolbar.setFloatable(False)

        self._setup_actions()
        self._suppress_extension_buttons()

    def set_active_editor(self, editor) -> None:
        """Binds toolbar formatting actions to the currently active editor."""
        self._current_editor = editor

    def update_templates_menu(self, custom_templates: Optional[list] = None) -> None:
        """Populates the Template dropdown menu with skeletons, custom templates, and the add action."""
        menu = QMenu(self.btn_skeleton)

        for name in TICKET_SKELETONS.keys():
            act = menu.addAction(name)
            act.triggered.connect(lambda checked=False, n=name: self.skeleton_selected.emit(n))

        if custom_templates:
            menu.addSeparator()
            for item in custom_templates:
                title = item.get("title", "") if isinstance(item, dict) else str(item)
                if title:
                    act = menu.addAction(title)
                    act.triggered.connect(lambda checked=False, t=title: self.skeleton_selected.emit(t))

        menu.addSeparator()
        act_add = menu.addAction("🔳 Add a new template")
        act_add.triggered.connect(self.add_template_requested.emit)

        self.btn_skeleton.setMenu(menu)

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
        self.check_responsive_mode(self.width())

    def resizeEvent(self, event) -> None:
        super().resizeEvent(event)
        self._suppress_extension_buttons()
        self.check_responsive_mode(self.width())

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

        # Text & Highlight Colors (Ctrl+Alt+X / Ctrl+Alt+H)
        self.act_color = self.addAction("🎨")
        self.act_color.setToolTip("Text Color (Ctrl+Alt+X)")
        self.act_color.setShortcut(QKeySequence("Ctrl+Alt+X"))
        self.act_color.triggered.connect(self._pick_text_color)

        self.act_highlight = self.addAction("🖍️")
        self.act_highlight.setToolTip("Highlight Background Color (Ctrl+Alt+H)")
        self.act_highlight.setShortcut(QKeySequence("Ctrl+Alt+H"))
        self.act_highlight.triggered.connect(self._pick_highlight_color)

        self.addSeparator()

        # Monospace Code Block (Ctrl+Alt+C)
        self.act_code = self.addAction("</>")
        self.act_code.setToolTip("Monospace Code Block (Ctrl+Alt+C)")
        self.act_code.setShortcut(QKeySequence("Ctrl+Alt+C"))
        self.act_code.triggered.connect(self._insert_or_toggle_code_block)

        # Log Triage Badges Menu / Quick Buttons
        self.sep_badge = self.addSeparator()
        self.btn_badge = QToolButton(self)
        self.btn_badge.setText("🏷️ Tag")
        self.btn_badge.setPopupMode(QToolButton.InstantPopup)
        self.btn_badge.setToolTip("Insert Log Triage Badge (Alt+1..4)")
        self.badge_menu = QMenu(self.btn_badge)

        badge_shortcuts = {
            "PASS": "Alt+1",
            "FAIL": "Alt+2",
            "WARN": "Alt+3",
            "INFO": "Alt+4",
        }

        for tag_key, info in LOG_BADGES.items():
            sc = badge_shortcuts.get(tag_key, "")
            label = f"{info['label']} ({sc})" if sc else info["label"]
            act = self.badge_menu.addAction(label)
            if sc:
                act.setShortcut(QKeySequence(sc))
            act.triggered.connect(lambda checked=False, k=tag_key: self._insert_badge(k))
        self.btn_badge.setMenu(self.badge_menu)
        self.act_badge = self.addWidget(self.btn_badge)

        self.sep_checklist = self.addSeparator()

        # Interactive Task / Checkbox Button (Ctrl+Alt+L)
        self.act_checklist = self.addAction("☑ Checkbox")
        self.act_checklist.setToolTip("Insert Interactive Checkbox Item (Ctrl+Alt+L)")
        self.act_checklist.setShortcut(QKeySequence("Ctrl+Alt+L"))
        self.act_checklist.triggered.connect(self.checklist_requested.emit)

        self.sep_media = self.addSeparator()

        # Timestamp Action & Toolbar Button (F5 / Ctrl+Alt+T)
        self.act_timestamp = QAction("🕒", self)
        self.act_timestamp.setToolTip("Insert Current Timestamp (F5 / Ctrl+Alt+T)")
        self.act_timestamp.setShortcut(QKeySequence("F5"))
        self.act_timestamp.triggered.connect(self._insert_timestamp)

        self.btn_timestamp = QToolButton(self)
        self.btn_timestamp.setDefaultAction(self.act_timestamp)
        self.act_timestamp_btn = self.addWidget(self.btn_timestamp)

        # Media Action & Toolbar Button (Ctrl+Alt+I)
        self.act_image = QAction("🖼️", self)
        self.act_image.setToolTip("Insert Image File... (Ctrl+Alt+I)")
        self.act_image.setShortcut(QKeySequence("Ctrl+Alt+I"))
        self.act_image.triggered.connect(self.image_requested.emit)

        self.btn_image = QToolButton(self)
        self.btn_image.setDefaultAction(self.act_image)
        self.act_image_btn = self.addWidget(self.btn_image)

        # Responsive More Tools overflow menu button for compact viewports
        self.btn_more = QToolButton(self)
        self.btn_more.setText("More ▾")
        self.btn_more.setObjectName("btnToolbarMore")
        self.btn_more.setToolTip("Additional formatting and insertion tools")
        self.btn_more.setPopupMode(QToolButton.InstantPopup)
        self.menu_more = QMenu(self.btn_more)

        badge_sub = self.menu_more.addMenu("🏷️ Log Badges")
        for tag_key, info in LOG_BADGES.items():
            sc = badge_shortcuts.get(tag_key, "")
            label = f"{info['label']} ({sc})" if sc else info["label"]
            act = badge_sub.addAction(label)
            if sc:
                act.setShortcut(QKeySequence(sc))
            act.triggered.connect(lambda checked=False, k=tag_key: self._insert_badge(k))

        self.menu_more.addSeparator()
        self.menu_more.addAction(self.act_timestamp)
        self.menu_more.addAction(self.act_image)
        self.btn_more.setMenu(self.menu_more)
        self.act_more = self.addWidget(self.btn_more)
        self.act_more.setVisible(False)

        # M365 Launcher button moved to bottom bar (status bar) between HUD and Split buttons
        self._btn_m365 = None

        # -------------------------------------------------------------
        # Row 2: Workflow, Templates, Stopwatch & Utilities
        # -------------------------------------------------------------

        # 1. Stopwatch Widget for tracking ticket troubleshooting time
        self.stopwatch = TicketStopwatchWidget(parent=self.secondary_toolbar)
        self.secondary_toolbar.addWidget(self.stopwatch)

        self.secondary_toolbar.addSeparator()

        # 2. Ticket Skeletons Dropdown (Ctrl+Alt+S)
        self.btn_skeleton = QToolButton(self.secondary_toolbar)
        self.btn_skeleton.setText("📋 Template")
        self.btn_skeleton.setPopupMode(QToolButton.InstantPopup)
        self.btn_skeleton.setToolTip("Insert Structured Ticket Skeleton or Custom Template (Ctrl+Alt+S)")
        self.update_templates_menu()
        self.secondary_toolbar.addWidget(self.btn_skeleton)

        self.secondary_toolbar.addSeparator()

        # 3. Copy Note: Formatted (Rich Text & Images) or Clean PSA (Markdown)
        self.btn_copy_note = QToolButton(self.secondary_toolbar)
        self.btn_copy_note.setText("📋 Copy Note")
        self.btn_copy_note.setPopupMode(QToolButton.MenuButtonPopup)
        self.btn_copy_note.setToolTip("Copy Note: Click to copy rich formatted note with images & colors (Ctrl+Shift+C), or open menu for clean PSA export (Ctrl+Alt+N)")
        self.btn_copy_note.setStyleSheet("padding: 2px 6px;")

        copy_menu = QMenu(self.btn_copy_note)

        self.act_copy_formatted = QAction("📋 Copy Formatted Note (Rich Text & Images)", self.secondary_toolbar)
        self.act_copy_formatted.setShortcut(QKeySequence("Ctrl+Shift+C"))
        self.act_copy_formatted.setToolTip("Preserves colors, headings, code blocks, and embedded images")
        self.act_copy_formatted.triggered.connect(self.copy_formatted_requested.emit)
        copy_menu.addAction(self.act_copy_formatted)

        self.act_export = QAction("📤 Copy Clean Note for Ticket Tool", self.secondary_toolbar)
        self.act_export.setShortcut(QKeySequence("Ctrl+Alt+N"))
        self.act_export.setToolTip("Stripped clean markdown/plain-text for PSA ticket systems (ServiceNow, Jira)")
        self.act_export.triggered.connect(self.export_note_requested.emit)
        copy_menu.addAction(self.act_export)

        self.btn_copy_note.setMenu(copy_menu)
        self.btn_copy_note.clicked.connect(self.copy_formatted_requested.emit)
        self.secondary_toolbar.addWidget(self.btn_copy_note)

        self.stopwatch.psa_export_requested.connect(self.export_note_requested.emit)

        self.secondary_toolbar.addSeparator()

        # 4. Opacity Slider (60% to 100%) - positioned compactly without artificial expanding spacer
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

        # 5. Split View Toggle Button (◫ / Alt+Z)
        self.btn_split = QToolButton(self.secondary_toolbar)
        self.btn_split.setText("◫")
        self.btn_split.setToolTip("Toggle Split View (Alt+Z)")
        self.btn_split.setCheckable(True)
        self.btn_split.setStyleSheet("font-size: 14px; padding: 2px 6px;")
        self.btn_split.clicked.connect(self.split_view_requested.emit)
        self.secondary_toolbar.addWidget(self.btn_split)
        self.act_split = self.btn_split

        # 6. Always-on-Top Mini-HUD Toggle Button (📌 / Alt+T)
        self.btn_pin = QToolButton(self.secondary_toolbar)
        self.btn_pin.setText("📌")
        self.btn_pin.setToolTip("Always-on-Top Mini-HUD Mode (Alt+T)")
        self.btn_pin.setCheckable(True)
        self.btn_pin.setStyleSheet("font-size: 13px; padding: 2px 6px;")
        self.btn_pin.clicked.connect(self.mini_hud_requested.emit)
        self.secondary_toolbar.addWidget(self.btn_pin)

        # 7. History Section Toggle Button (🕰️)
        self.btn_history = QToolButton(self.secondary_toolbar)
        self.btn_history.setText("🕰️")
        self.btn_history.setToolTip("Ticket History & Archive (Ctrl+H)")
        self.btn_history.setStyleSheet("font-size: 14px; padding: 2px 6px;")
        self.btn_history.clicked.connect(self.history_requested.emit)
        self.secondary_toolbar.addWidget(self.btn_history)

        # 7. Settings Gear Icon Button (⚙️)
        self.btn_settings = QToolButton(self.secondary_toolbar)
        self.btn_settings.setText("⚙️")
        self.btn_settings.setToolTip("Preferences & Settings (Ctrl+,)")
        self.btn_settings.setStyleSheet("font-size: 14px; padding: 2px 6px;")
        self.btn_settings.clicked.connect(self.settings_requested.emit)
        self.secondary_toolbar.addWidget(self.btn_settings)

    @property
    def is_compact(self) -> bool:
        """Returns True if the toolbar is currently displayed in compact mode."""
        return getattr(self, "_is_compact", False)

    def set_compact_mode(self, compact: bool) -> None:
        """Toggles between normal and compact layout modes."""
        if getattr(self, "_is_compact", None) == compact:
            return
        self._is_compact = compact

        # Row 1: Move low-priority tools to 'More ▾' menu
        if hasattr(self, "act_badge"):
            self.act_badge.setVisible(not compact)
        if hasattr(self, "sep_badge"):
            self.sep_badge.setVisible(not compact)
        if hasattr(self, "act_timestamp_btn"):
            self.act_timestamp_btn.setVisible(not compact)
        if hasattr(self, "act_image_btn"):
            self.act_image_btn.setVisible(not compact)
        if hasattr(self, "sep_media"):
            self.sep_media.setVisible(not compact)
        if hasattr(self, "act_more"):
            self.act_more.setVisible(compact)

        # Row 2: Compact controls sizing
        if compact:
            self.btn_copy_note.setText("📋 Copy")
            self.btn_skeleton.setText("Template")
            self.slider_opacity.setFixedWidth(50)
            self.lbl_opacity.setText(f"{self.slider_opacity.value()}%")
            for btn in (self.btn_split, self.btn_pin, self.btn_history, self.btn_settings):
                btn.setStyleSheet("font-size: 12px; padding: 2px 3px;")

        else:
            self.btn_copy_note.setText("📋 Copy Note")
            self.btn_skeleton.setText("📋 Template")
            self.slider_opacity.setFixedWidth(85)
            self.lbl_opacity.setText(f"👁️ {self.slider_opacity.value()}%")
            self.btn_split.setStyleSheet("font-size: 14px; padding: 2px 6px;")
            self.btn_pin.setStyleSheet("font-size: 13px; padding: 2px 6px;")
            self.btn_history.setStyleSheet("font-size: 14px; padding: 2px 6px;")
            self.btn_settings.setStyleSheet("font-size: 14px; padding: 2px 6px;")


    def check_responsive_mode(self, available_width: int) -> None:
        """Applies responsive compact mode using actual measured width with hysteresis."""
        if available_width < 775 and not self.is_compact:
            self.set_compact_mode(True)
        elif available_width >= 800 and self.is_compact:
            self.set_compact_mode(False)

    def set_opacity_value(self, val: int) -> None:
        """Sets the slider value without emitting signals."""
        self.slider_opacity.blockSignals(True)
        self.slider_opacity.setValue(val)
        prefix = "" if self.is_compact else "👁️ "
        self.lbl_opacity.setText(f"{prefix}{val}%")
        self.slider_opacity.blockSignals(False)

    @property
    def btn_m365(self):
        if self._btn_m365 is not None:
            return self._btn_m365
        parent = self.parent()
        if parent and hasattr(parent, "btn_m365"):
            return parent.btn_m365
        return None

    @btn_m365.setter
    def btn_m365(self, value):
        self._btn_m365 = value

    def set_mini_hud_state(self, active: bool) -> None:
        """Updates the pin button state to reflect Mini-HUD status."""
        self.btn_pin.blockSignals(True)
        self.btn_pin.setChecked(active)
        self.btn_pin.blockSignals(False)

    def _on_opacity_changed(self, value: int) -> None:
        prefix = "" if self.is_compact else "👁️ "
        self.lbl_opacity.setText(f"{prefix}{value}%")
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
        self._current_editor.setFocus()

    def _insert_timestamp(self) -> None:
        if not self._current_editor:
            return
        now_str = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
        tag = f'<strong>[{now_str}]</strong> '
        cursor = self._current_editor.textCursor()
        cursor.insertHtml(tag)
        self._current_editor.setFocus()

    def update_format_states(self, format: QTextCharFormat) -> None:
        """Updates bold/italic/underline action states based on current cursor position."""
        self.act_bold.setChecked(format.fontWeight() == QFont.Bold)
        self.act_italic.setChecked(format.fontItalic())
        self.act_underline.setChecked(format.fontUnderline())
