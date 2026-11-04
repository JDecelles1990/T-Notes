"""Adaptive M365 workspace shell with active ticket sidebar integration."""

from datetime import datetime
from typing import Optional

from PySide6.QtCore import Qt, Signal, QEvent, QPoint
from PySide6.QtGui import QAction, QColor, QFont, QTextCharFormat
from PySide6.QtWidgets import (
    QApplication, QColorDialog, QComboBox, QFileDialog, QGridLayout,
    QGroupBox, QHBoxLayout, QLabel, QLineEdit, QListWidget, QListWidgetItem,
    QMenu, QPlainTextEdit, QPushButton, QScrollArea, QSplitter, QToolButton,
    QVBoxLayout, QWidget,
)

from src.core.constants import LOG_BADGES, TICKET_SKELETONS
from src.services.m365_catalog_service import CatalogError, M365CatalogService
from src.services.m365_company_service import synthetic_directory
from src.services.m365_context_service import CompanyContextService
from src.ui.components.editor import TechPadEditor
from src.ui.m365.company_context_panel import CompanyContextPanel


class HoverToolButton(QToolButton):
    """QToolButton that displays its popup menu on hover or click."""

    def enterEvent(self, event) -> None:
        super().enterEvent(event)
        menu = self.menu()
        if menu and not menu.isVisible() and self.isEnabled():
            menu.popup(self.mapToGlobal(QPoint(0, self.height())))


class M365LauncherWidget(QWidget):
    """Adaptive M365 workspace shell with responsive reflow and active ticket sidebar."""

    back_requested = Signal()
    note_modified = Signal(int)                  # Emits scratchpad_id
    save_requested = Signal(int)                  # Emits scratchpad_id
    status_message_requested = Signal(str, int)  # Emits (message, timeout_ms)

    def __init__(
        self,
        parent=None,
        *,
        catalog_service=None,
        company_directory=None,
        scratchpad_service=None,
        image_service=None,
    ):
        super().__init__(parent)
        self.scratchpad_service = scratchpad_service
        self.image_service = image_service
        self._active_editor = None
        self._current_ticket_number = ""
        self._stopwatch = None
        self.setObjectName("m365LauncherWorkspace")
        self.setAttribute(Qt.WA_StyledBackground, True)
        self.setStyleSheet("""
            QWidget#m365LauncherWorkspace, QWidget#m365CatalogContent,
            QWidget#m365LauncherWorkspace QScrollArea { background-color: #1e1e1e; }
            QWidget#m365LauncherWorkspace QGroupBox {
                background-color: #252526; border: 1px solid #444444;
                border-radius: 4px; margin-top: 9px; color: #cccccc;
            }
            QWidget#m365LauncherWorkspace QGroupBox::title {
                subcontrol-origin: margin; left: 8px; padding: 0 3px;
            }
            QWidget#m365LauncherWorkspace QComboBox,
            QWidget#m365LauncherWorkspace QPlainTextEdit {
                background-color: #2d2d30; color: #cccccc;
                border: 1px solid #444444; border-radius: 3px; padding: 4px;
            }
            QWidget#m365LauncherWorkspace QComboBox QAbstractItemView {
                background-color: #2d2d30; color: #cccccc;
                selection-background-color: #094771;
            }
        """)
        self._current_columns = 2
        try:
            self.catalog_service = catalog_service if catalog_service is not None else M365CatalogService()
        except (CatalogError, OSError, ImportError):
            # A catalog failure must not prevent startup or access to the Notes workspace.
            self.catalog_service = None
            layout = QVBoxLayout(self)
            notice = QLabel("M365 catalog unavailable. Review the local registry and schema dependencies.", self)
            notice.setWordWrap(True)
            layout.addWidget(notice)
            self.back_button = QPushButton("Back to T-Notes", self)
            self.back_button.setAccessibleName("Back to T-Notes")
            self.back_button.setToolTip("Return to the existing ticket notes workspace (Alt+F8)")
            self.back_button.clicked.connect(self.back_requested.emit)
            layout.addWidget(self.back_button)
            layout.addStretch()
            return

        layout = QVBoxLayout(self)
        layout.setContentsMargins(8, 8, 8, 8)
        layout.setSpacing(6)

        # Header Row: Title & Back Button
        header = QHBoxLayout()
        title = QVBoxLayout()
        lbl_title = QLabel("M365 PowerShell Launcher", self)
        lbl_title.setStyleSheet("font-weight: bold; font-size: 11pt; color: #ffffff;")
        lbl_sub = QLabel("Microsoft 365 Administration & Troubleshooting", self)
        lbl_sub.setStyleSheet("color: #888888; font-size: 9pt;")
        title.addWidget(lbl_title)
        title.addWidget(lbl_sub)
        header.addLayout(title, 1)

        self.back_button = QPushButton("Back to T-Notes", self)
        self.back_button.setObjectName("btnBackToNotes")
        self.back_button.setAccessibleName("Back to T-Notes")
        self.back_button.setToolTip("Return to the existing ticket notes workspace (Alt+F8)")
        self.back_button.setFocusPolicy(Qt.StrongFocus)
        self.back_button.clicked.connect(self.back_requested.emit)
        header.addWidget(self.back_button)
        layout.addLayout(header)

        # Control & Notice Bar
        control_bar = QHBoxLayout()
        control_bar.setSpacing(8)

        self.nav_toggle = QToolButton(self)
        self.nav_toggle.setText("☰ Categories")
        self.nav_toggle.setToolTip("Show or hide the category navigation sidebar")
        self.nav_toggle.setAccessibleName("Toggle category navigation panel")
        self.nav_toggle.setFocusPolicy(Qt.StrongFocus)
        self.nav_toggle.setCheckable(True)
        self.nav_toggle.setChecked(True)
        control_bar.addWidget(self.nav_toggle)

        notice = QLabel("Catalog preview — no Microsoft 365 connection or execution.", self)
        notice.setStyleSheet("color: #9cdcfe; font-size: 9pt;")
        notice.setWordWrap(True)
        control_bar.addWidget(notice, 1)

        self.ticket_panel_toggle = QToolButton(self)
        self.ticket_panel_toggle.setText("Active Ticket")
        self.ticket_panel_toggle.setToolTip("Show or hide the active ticket sidebar placeholder")
        self.ticket_panel_toggle.setAccessibleName("Show active ticket notes panel")
        self.ticket_panel_toggle.setFocusPolicy(Qt.StrongFocus)
        self.ticket_panel_toggle.setCheckable(True)
        self.ticket_panel_toggle.setChecked(True)
        control_bar.addWidget(self.ticket_panel_toggle)
        layout.addLayout(control_bar)

        # 3-Pane Splitter
        self.workspace_splitter = QSplitter(Qt.Horizontal, self)
        self.workspace_splitter.setChildrenCollapsible(True)

        # Pane 0: Category Navigation List
        self.navigation = QListWidget(self.workspace_splitter)
        for category in self.catalog_service.categories:
            item = QListWidgetItem(f"{category.icon} {category.label}")
            item.setData(Qt.UserRole, category.id)
            item.setData(Qt.AccessibleTextRole, category.label)
            item.setToolTip(category.description)
            self.navigation.addItem(item)
        self.navigation.setAccessibleName("M365 categories")
        self.navigation.setToolTip("Choose a category to browse its operation metadata")
        self.navigation.setFocusPolicy(Qt.StrongFocus)
        self.navigation.setMinimumWidth(110)
        self.navigation.setMaximumWidth(180)

        # Pane 1: Center Scroll Area with Groupboxes
        scroll = QScrollArea(self.workspace_splitter)
        scroll.setWidgetResizable(True)
        scroll.setHorizontalScrollBarPolicy(Qt.ScrollBarAsNeeded)
        scroll.setVerticalScrollBarPolicy(Qt.ScrollBarAsNeeded)
        self.scroll_area = scroll

        content = QWidget(scroll)
        content.setObjectName("m365CatalogContent")
        self.content_widget = content
        self.content_layout = QGridLayout(content)
        self.content_layout.setContentsMargins(6, 6, 6, 6)
        self.content_layout.setSpacing(8)

        self._content_groups = []
        for label in (
            "Company Selection", "Authentication & Tenant Context", "Script Catalog",
            "Parameters", "Execution Workspace", "Parsed Results",
        ):
            group = QGroupBox(label, content)
            group.setMinimumSize(170, 70)
            group_layout = QVBoxLayout(group)
            group_layout.setContentsMargins(8, 12, 8, 8)
            placeholder = QLabel("Placeholder — not implemented", group)
            placeholder.setStyleSheet("color: #888888; font-style: italic;")
            placeholder.setWordWrap(True)
            group_layout.addWidget(placeholder)
            self._content_groups.append(group)

        catalog_group = self._content_groups[2]
        catalog_layout = catalog_group.layout()
        old_placeholder = catalog_layout.takeAt(0).widget()
        old_placeholder.hide()
        old_placeholder.deleteLater()
        self.category_title = QLabel(catalog_group)
        self.category_title.setTextFormat(Qt.PlainText)
        self.category_title.setWordWrap(True)
        self.category_title.setStyleSheet("font-weight: bold;")
        self.category_description = QLabel(catalog_group)
        self.category_description.setTextFormat(Qt.PlainText)
        self.category_description.setWordWrap(True)
        catalog_layout.addWidget(self.category_title)
        catalog_layout.addWidget(self.category_description)
        self.search_input = QLineEdit(catalog_group)
        self.search_input.setPlaceholderText("Search names, descriptions, tags or services")
        self.search_input.setAccessibleName("Search category operations")
        self.search_input.setMaxLength(256)
        self.search_input.setClearButtonEnabled(True)
        catalog_layout.addWidget(self.search_input)
        self.risk_filter = QComboBox(catalog_group)
        self.risk_filter.setAccessibleName("Filter operations by risk")
        for label, value in (("All risks", "all"), ("Read only", "read_only"), ("Write", "write"), ("High impact", "high_impact")):
            self.risk_filter.addItem(label, value)
        catalog_layout.addWidget(self.risk_filter)
        self.lifecycle_filter = QComboBox(catalog_group)
        self.lifecycle_filter.setAccessibleName("Filter operations by lifecycle")
        for label, value in (("Current operations", "current"), ("Archived operations", "archived"), ("All lifecycle states", "all")):
            self.lifecycle_filter.addItem(label, value)
        catalog_layout.addWidget(self.lifecycle_filter)
        self.catalog_status = QLabel(catalog_group)
        self.catalog_status.setTextFormat(Qt.PlainText)
        self.catalog_status.setWordWrap(True)
        catalog_layout.addWidget(self.catalog_status)
        self.operation_list = QListWidget(catalog_group)
        self.operation_list.setAccessibleName("Category operations; metadata preview only")
        self.operation_list.setMinimumHeight(90)
        self.operation_list.setMaximumHeight(180)
        catalog_layout.addWidget(self.operation_list)
        self.operation_details = QPlainTextEdit(catalog_group)
        self.operation_details.setReadOnly(True)
        self.operation_details.setAccessibleName("Operation metadata and unavailable reasons")
        self.operation_details.setMinimumHeight(130)
        self.operation_details.setMaximumHeight(230)
        catalog_layout.addWidget(self.operation_details)
        # Synthetic metadata/context only. No Notes DB, auth adapter or engine ownership.
        for group in self._content_groups[:2]:
            old = group.layout().takeAt(0).widget()
            old.hide()
            old.deleteLater()
        self.company_directory = company_directory if company_directory is not None else synthetic_directory()
        self.context_service = CompanyContextService(self.company_directory)
        self.company_panel = CompanyContextPanel(self.context_service, *self._content_groups[:2])
        self.navigation.currentItemChanged.connect(self._category_changed)
        self.search_input.textChanged.connect(self._refresh_operations)
        self.risk_filter.currentIndexChanged.connect(self._refresh_operations)
        self.lifecycle_filter.currentIndexChanged.connect(self._refresh_operations)
        self.operation_list.currentItemChanged.connect(self._operation_changed)
        self.navigation.setCurrentRow(0)

        self._arrange_content_columns(2)
        scroll.setWidget(content)

        # Pane 2: Active Ticket Sidebar
        self.ticket_sidebar = QGroupBox("Active Ticket Notes", self.workspace_splitter)
        self.ticket_sidebar.setMinimumWidth(220)
        sidebar_layout = QVBoxLayout(self.ticket_sidebar)
        sidebar_layout.setContentsMargins(6, 10, 6, 6)
        sidebar_layout.setSpacing(4)

        # 1. Header Card (Ticket details & stopwatch)
        self.ticket_header_card = QWidget(self.ticket_sidebar)
        self.ticket_header_card.setObjectName("ticketHeaderCard")
        self.ticket_header_card.setStyleSheet("""
            QWidget#ticketHeaderCard {
                background-color: #21262d;
                border: 1px solid #30363d;
                border-radius: 4px;
            }
        """)
        header_card_layout = QVBoxLayout(self.ticket_header_card)
        header_card_layout.setContentsMargins(6, 6, 6, 6)
        header_card_layout.setSpacing(4)

        # Top row: Ticket ID Badge + Client Name + Corner Action Buttons
        id_client_row = QHBoxLayout()
        id_client_row.setContentsMargins(0, 0, 0, 0)
        id_client_row.setSpacing(4)

        self.lbl_ticket_id = QLabel("#INC-000", self.ticket_header_card)
        self.lbl_ticket_id.setStyleSheet(
            "font-weight: bold; font-size: 11px; color: #58a6ff; "
            "background-color: #161b22; border: 1px solid #30363d; "
            "border-radius: 3px; padding: 1px 5px;"
        )
        id_client_row.addWidget(self.lbl_ticket_id)

        self.lbl_ticket_client = QLabel("Client: N/A", self.ticket_header_card)
        self.lbl_ticket_client.setStyleSheet("color: #8b949e; font-size: 11px;")
        id_client_row.addWidget(self.lbl_ticket_client)

        id_client_row.addStretch(1)

        corner_btn_style = """
            QToolButton {
                background-color: #161b22; border: 1px solid #30363d; border-radius: 3px;
                color: #c9d1d9; font-family: 'Segoe UI Symbol', 'Segoe UI Emoji', Consolas, sans-serif;
                font-size: 11px; font-weight: bold; padding: 1px 2px;
            }
            QToolButton:hover { background-color: #30363d; border-color: #58a6ff; color: #ffffff; }
            QToolButton:pressed { background-color: #1f6feb; color: #ffffff; }
            QToolButton::menu-indicator { image: none; width: 0px; }
        """

        self.btn_template = QToolButton(self.ticket_header_card)
        self.btn_template.setText("🗒️")
        self.btn_template.setFixedSize(26, 22)
        self.btn_template.setPopupMode(QToolButton.InstantPopup)
        self.btn_template.setToolTip("Insert Structured Ticket Template (Ctrl+Alt+S)")
        self.btn_template.setStyleSheet(corner_btn_style)
        template_menu = QMenu(self.btn_template)
        for name in TICKET_SKELETONS.keys():
            act = template_menu.addAction(name)
            act.triggered.connect(lambda checked=False, n=name: self._insert_template(n))
        self.btn_template.setMenu(template_menu)
        id_client_row.addWidget(self.btn_template)

        self.btn_copy_note = QToolButton(self.ticket_header_card)
        self.btn_copy_note.setText("📋")
        self.btn_copy_note.setFixedSize(26, 22)
        self.btn_copy_note.setPopupMode(QToolButton.MenuButtonPopup)
        self.btn_copy_note.setToolTip("Copy Note: Click to copy rich note (Ctrl+Shift+C), or open menu for clean PSA export (Ctrl+Alt+N)")
        self.btn_copy_note.setStyleSheet(corner_btn_style)
        copy_menu = QMenu(self.btn_copy_note)
        act_copy_rich = copy_menu.addAction("📋 Copy Formatted Note (Rich Text & Images)")
        act_copy_rich.triggered.connect(self._copy_formatted_note)
        act_copy_clean = copy_menu.addAction("📤 Copy Clean Note for Ticket Tool")
        act_copy_clean.triggered.connect(self._copy_clean_note)
        self.btn_copy_note.setMenu(copy_menu)
        self.btn_copy_note.clicked.connect(self._copy_formatted_note)
        id_client_row.addWidget(self.btn_copy_note)

        self.btn_more = HoverToolButton(self.ticket_header_card)
        self.btn_more.setText("...")
        self.btn_more.setFixedSize(26, 22)
        self.btn_more.setPopupMode(QToolButton.InstantPopup)
        self.btn_more.setToolTip("Text Features & Formatting (Click or Hover)")
        self.btn_more.setStyleSheet(corner_btn_style)

        self.menu_text_features = QMenu(self.btn_more)
        self.btn_more.setMenu(self.menu_text_features)
        id_client_row.addWidget(self.btn_more)

        # Actions inside self.menu_text_features
        self.act_bold = self.menu_text_features.addAction("B  Bold (Ctrl+B)")
        self.act_bold.setCheckable(True)
        self.act_bold.triggered.connect(self._toggle_bold)

        self.act_italic = self.menu_text_features.addAction("I   Italic (Ctrl+I)")
        self.act_italic.setCheckable(True)
        self.act_italic.triggered.connect(self._toggle_italic)

        self.act_underline = self.menu_text_features.addAction("U  Underline (Ctrl+U)")
        self.act_underline.setCheckable(True)
        self.act_underline.triggered.connect(self._toggle_underline)

        self.menu_text_features.addSeparator()

        self.act_color = self.menu_text_features.addAction("🎨 Text Color... (Ctrl+Alt+X)")
        self.act_color.triggered.connect(self._pick_text_color)

        self.act_highlight = self.menu_text_features.addAction("🖍️ Highlight Color... (Ctrl+Alt+H)")
        self.act_highlight.triggered.connect(self._pick_highlight_color)

        self.act_code = self.menu_text_features.addAction("</> Monospace Code Block (Ctrl+Alt+C)")
        self.act_code.triggered.connect(self._insert_code_block)

        self.menu_text_features.addSeparator()

        self.menu_badge = QMenu("🏷️ Log Badges", self.menu_text_features)
        for tag_key, info in LOG_BADGES.items():
            b_act = self.menu_badge.addAction(info["label"])
            b_act.triggered.connect(lambda checked=False, k=tag_key: self._insert_badge(k))
        self.menu_text_features.addMenu(self.menu_badge)

        self.menu_text_features.addSeparator()

        self.act_checklist = self.menu_text_features.addAction("☑ Checkbox (Ctrl+Alt+L)")
        self.act_checklist.triggered.connect(self._insert_checklist)

        self.act_timestamp = self.menu_text_features.addAction("🕒 Current Timestamp (F5)")
        self.act_timestamp.triggered.connect(self._insert_timestamp)

        self.act_image = self.menu_text_features.addAction("🖼️ Insert Image File... (Ctrl+Alt+I)")
        self.act_image.triggered.connect(self._insert_image)

        # Backward compatibility aliases for existing tests/references
        for act in (
            self.act_bold, self.act_italic, self.act_underline,
            self.act_color, self.act_highlight, self.act_code,
            self.act_checklist, self.act_timestamp, self.act_image,
        ):
            act.click = act.trigger

        self.btn_bold = self.act_bold
        self.btn_italic = self.act_italic
        self.btn_underline = self.act_underline
        self.btn_color = self.act_color
        self.btn_highlight = self.act_highlight
        self.btn_code = self.act_code
        self.btn_checklist = self.act_checklist
        self.btn_timestamp = self.act_timestamp
        self.btn_image = self.act_image
        self.btn_badge = self.menu_badge
        self.btn_badge.menu = lambda: self.menu_badge

        header_card_layout.addLayout(id_client_row)

        # Subject row
        self.lbl_ticket_subject = QLabel("Subject: N/A", self.ticket_header_card)
        self.lbl_ticket_subject.setStyleSheet("color: #c9d1d9; font-size: 11px;")
        self.lbl_ticket_subject.setWordWrap(True)
        header_card_layout.addWidget(self.lbl_ticket_subject)

        # Stopwatch row
        stopwatch_row = QHBoxLayout()
        stopwatch_row.setContentsMargins(0, 0, 0, 0)
        stopwatch_row.setSpacing(4)

        self.lbl_sidebar_stopwatch = QLabel("⏱️ 00:00:00", self.ticket_header_card)
        self.lbl_sidebar_stopwatch.setStyleSheet(
            "font-family: Consolas, 'Courier New', monospace; font-size: 12px; "
            "font-weight: bold; color: #58a6ff; padding: 2px 4px; "
            "background-color: #161b22; border: 1px solid #30363d; border-radius: 3px;"
        )
        self.lbl_sidebar_stopwatch.setToolTip("Active ticket troubleshooting stopwatch")
        stopwatch_row.addWidget(self.lbl_sidebar_stopwatch, 1)

        self.btn_sidebar_stopwatch_toggle = QToolButton(self.ticket_header_card)
        self.btn_sidebar_stopwatch_toggle.setText("▶")
        self.btn_sidebar_stopwatch_toggle.setFixedSize(26, 22)
        self.btn_sidebar_stopwatch_toggle.setToolTip("Start / Pause Stopwatch")
        self.btn_sidebar_stopwatch_toggle.setStyleSheet("""
            QToolButton {
                background-color: #161b22; border: 1px solid #30363d; border-radius: 3px;
                font-family: 'Segoe UI Symbol', 'Segoe UI Emoji', sans-serif;
                font-size: 11px; color: #58a6ff; font-weight: bold;
            }
            QToolButton:hover { background-color: #30363d; border-color: #58a6ff; color: #79c0ff; }
        """)
        self.btn_sidebar_stopwatch_toggle.clicked.connect(self._toggle_stopwatch)
        stopwatch_row.addWidget(self.btn_sidebar_stopwatch_toggle)

        self.btn_sidebar_stopwatch_reset = QToolButton(self.ticket_header_card)
        self.btn_sidebar_stopwatch_reset.setText("↺")
        self.btn_sidebar_stopwatch_reset.setFixedSize(26, 22)
        self.btn_sidebar_stopwatch_reset.setToolTip("Reset Timer to 00:00:00")
        self.btn_sidebar_stopwatch_reset.setStyleSheet("""
            QToolButton {
                background-color: #161b22; border: 1px solid #30363d; border-radius: 3px;
                font-family: 'Segoe UI Symbol', 'Segoe UI Emoji', sans-serif;
                font-size: 12px; color: #8b949e; font-weight: bold;
            }
            QToolButton:hover { background-color: #30363d; border-color: #f85149; color: #f85149; }
        """)
        self.btn_sidebar_stopwatch_reset.clicked.connect(self._reset_stopwatch)
        stopwatch_row.addWidget(self.btn_sidebar_stopwatch_reset)

        header_card_layout.addLayout(stopwatch_row)
        sidebar_layout.addWidget(self.ticket_header_card)

        # 2. Note Editor (Reclaimed vertical space from toolbar rows)
        self.ticket_editor = TechPadEditor(scratchpad_id=0, image_service=self.image_service, parent=self.ticket_sidebar)
        self.ticket_editor.setPlaceholderText("Ticket notes...")
        self.ticket_editor.currentCharFormatChanged.connect(self._update_format_states)
        self.ticket_editor.content_modified.connect(self._on_editor_content_modified)
        sidebar_layout.addWidget(self.ticket_editor, 1)

        self.nav_toggle.toggled.connect(self._on_nav_toggled)
        self.ticket_panel_toggle.toggled.connect(self._on_ticket_panel_toggled)

        self.workspace_splitter.setStretchFactor(0, 0)
        self.workspace_splitter.setStretchFactor(1, 1)
        self.workspace_splitter.setStretchFactor(2, 0)
        self.workspace_splitter.setSizes([130, 480, 270])
        layout.addWidget(self.workspace_splitter, 1)
        self.scroll_area.viewport().installEventFilter(self)

    @property
    def current_category_id(self):
        item = self.navigation.currentItem()
        return item.data(Qt.UserRole) if item else None

    def _category_changed(self, *_):
        category = self.catalog_service.category(self.current_category_id)
        self.category_title.setText(category.label)
        self.category_description.setText(category.description)
        for control in (self.search_input, self.risk_filter, self.lifecycle_filter):
            control.setEnabled(category.kind == "operations")
        self._refresh_operations()

    def _refresh_operations(self, *_):
        category = self.catalog_service.category(self.current_category_id)
        self.operation_list.clear()
        self.operation_details.clear()
        operations = self.catalog_service.operations(category.id, self.search_input.text(),
                                                      self.risk_filter.currentData(), self.lifecycle_filter.currentData())
        for operation in operations:
            item = QListWidgetItem(f"{operation.title} — Unavailable ({operation.lifecycle})")
            item.setData(Qt.UserRole, operation.id)
            item.setToolTip(operation.description)
            self.operation_list.addItem(item)
        if category.id == "dashboard":
            message = "No service connections or recent activity. Select a category to browse its catalog."
        elif category.id == "companies":
            message = "Manage session-only company and administrator metadata above. Authentication and execution remain unavailable."
        elif category.kind == "workflow":
            message = "No approved workflows registered. Each future step requires its own operation validation."
        elif operations:
            message = f"{len(operations)} operation(s) available for metadata review. Execution is unavailable."
        elif self.search_input.text() or self.risk_filter.currentData() != "all" or self.lifecycle_filter.currentData() != "current":
            message = "No operations match these filters. Clear the search or adjust the filters."
        else:
            message = "No approved operations registered in this category. Execution remains unavailable."
        if self.catalog_service.validation_errors:
            message += " Catalog contains rejected metadata; review the registration files."
        self.catalog_status.setText(message)
        if operations:
            self.operation_list.setCurrentRow(0)

    def _operation_changed(self, item, *_):
        if item is None:
            self.operation_details.clear()
            return
        try:
            operation = self.catalog_service.operation(item.data(Qt.UserRole))
        except CatalogError:
            self.operation_details.setPlainText("Unknown or invalid operation. Metadata unavailable.")
            return
        self.operation_details.setPlainText(
            operation.title + "\n" + operation.description + "\n\nUnavailable:\n• "
            + "\n• ".join(operation.disabled_reasons) + "\n\n" + operation.details)

    def _on_nav_toggled(self, visible: bool) -> None:
        self.navigation.setVisible(visible)
        if visible and self.navigation.width() == 0:
            sizes = self.workspace_splitter.sizes()
            sizes[0] = 130
            self.workspace_splitter.setSizes(sizes)

    def _on_ticket_panel_toggled(self, visible: bool) -> None:
        self.ticket_sidebar.setVisible(visible)
        if visible and self.ticket_sidebar.width() == 0:
            sizes = self.workspace_splitter.sizes()
            sizes[2] = 270
            self.workspace_splitter.setSizes(sizes)

    def set_active_ticket(
        self,
        editor: Optional[TechPadEditor],
        ticket_data: Optional[dict] = None,
        scratchpad_service=None,
        image_service=None,
        stopwatch=None,
    ) -> None:
        """Loads and binds the active ticket from T-Notes into the sidebar."""
        if scratchpad_service is not None:
            self.scratchpad_service = scratchpad_service
        if image_service is not None:
            self.image_service = image_service
            self.ticket_editor.image_service = image_service

        # Rebind stopwatch synchronization
        if self._stopwatch is not None:
            try:
                self._stopwatch.time_updated.disconnect(self._on_stopwatch_tick)
            except (RuntimeError, TypeError):
                pass
        self._stopwatch = stopwatch
        if self._stopwatch is not None:
            self._stopwatch.time_updated.connect(self._on_stopwatch_tick)
            self._update_stopwatch_ui()

        self._active_editor = editor
        if editor is None:
            self.lbl_ticket_id.setText("No Ticket")
            self.lbl_ticket_client.setText("Client: N/A")
            self.lbl_ticket_subject.setText("Open a ticket in T-Notes to view and edit notes.")
            self.btn_template.setEnabled(False)
            self.btn_copy_note.setEnabled(False)
            self.btn_more.setEnabled(False)
            self.ticket_editor.setEnabled(False)
            self.ticket_editor.setPlainText("")
            return

        self.btn_template.setEnabled(True)
        self.btn_copy_note.setEnabled(True)
        self.btn_more.setEnabled(True)
        self.ticket_editor.setEnabled(True)
        self.ticket_editor.scratchpad_id = editor.scratchpad_id
        self.ticket_editor.in_memory_images = editor.in_memory_images
        self.ticket_editor.setDocument(editor.document())

        ticket = ticket_data or (self.scratchpad_service.get_ticket(editor.scratchpad_id) if self.scratchpad_service else None) or {}
        t_num = ticket.get("ticket_number", "")
        self._current_ticket_number = t_num
        client = ticket.get("client_name", "") or "N/A"
        title = ticket.get("title", "") or "N/A"

        self.lbl_ticket_id.setText(f"#{t_num}" if t_num else "Ticket")
        self.lbl_ticket_client.setText(f"Client: {client}")
        self.lbl_ticket_subject.setText(f"Subject: {title}")

    def _on_stopwatch_tick(self, sid: int, elapsed_seconds: int) -> None:
        self._update_stopwatch_ui()

    def _update_stopwatch_ui(self) -> None:
        if self._stopwatch:
            self.lbl_sidebar_stopwatch.setText(self._stopwatch.lbl_time.text())
            self.btn_sidebar_stopwatch_toggle.setText(self._stopwatch.btn_toggle.text())

    def _toggle_stopwatch(self) -> None:
        if self._stopwatch:
            self._stopwatch.toggle_timer()
            self._update_stopwatch_ui()

    def _reset_stopwatch(self) -> None:
        if self._stopwatch:
            self._stopwatch.reset_timer()
            self._update_stopwatch_ui()

    def _on_editor_content_modified(self, scratchpad_id: int) -> None:
        self.note_modified.emit(scratchpad_id)

    def _update_format_states(self, format: QTextCharFormat) -> None:
        self.act_bold.setChecked(format.fontWeight() == QFont.Bold)
        self.act_italic.setChecked(format.fontItalic())
        self.act_underline.setChecked(format.fontUnderline())

    def _toggle_bold(self) -> None:
        fmt = QTextCharFormat()
        fmt.setFontWeight(QFont.Bold if self.act_bold.isChecked() else QFont.Normal)
        self.ticket_editor.mergeCurrentCharFormat(fmt)
        self.ticket_editor.setFocus()

    def _toggle_italic(self) -> None:
        fmt = QTextCharFormat()
        fmt.setFontItalic(self.act_italic.isChecked())
        self.ticket_editor.mergeCurrentCharFormat(fmt)
        self.ticket_editor.setFocus()

    def _toggle_underline(self) -> None:
        fmt = QTextCharFormat()
        fmt.setFontUnderline(self.act_underline.isChecked())
        self.ticket_editor.mergeCurrentCharFormat(fmt)
        self.ticket_editor.setFocus()

    def _pick_text_color(self) -> None:
        color = QColorDialog.getColor(Qt.white, self, "Select Text Color")
        if color.isValid():
            fmt = QTextCharFormat()
            fmt.setForeground(color)
            self.ticket_editor.mergeCurrentCharFormat(fmt)
        self.ticket_editor.setFocus()

    def _pick_highlight_color(self) -> None:
        color = QColorDialog.getColor(QColor("#264f78"), self, "Select Highlight Color")
        if color.isValid():
            fmt = QTextCharFormat()
            fmt.setBackground(color)
            self.ticket_editor.mergeCurrentCharFormat(fmt)
        self.ticket_editor.setFocus()

    def _insert_code_block(self) -> None:
        cursor = self.ticket_editor.textCursor()
        selected = cursor.selectedText()
        content = selected if selected else "# CLI / PowerShell Output"
        html = f'<div style="background-color: #252526; border: 1px solid #3c3c3c; border-radius: 4px; padding: 6px; font-family: Consolas, monospace; color: #9cdcfe;"><code>{content}</code></div><br>'
        cursor.insertHtml(html)
        self.ticket_editor.setFocus()

    def _insert_badge(self, tag_key: str) -> None:
        info = LOG_BADGES.get(tag_key)
        if not info:
            return
        badge_html = f'&nbsp;<span style="background-color: {info["bg_color"]}; color: {info["text_color"]}; border: 1px solid {info["border_color"]}; border-radius: 3px; padding: 2px 6px; font-weight: bold; font-size: 11px;">{info["label"]}</span>&nbsp;'
        cursor = self.ticket_editor.textCursor()
        cursor.insertHtml(badge_html)
        self.ticket_editor.setFocus()

    def _insert_checklist(self) -> None:
        self.ticket_editor.insert_checklist_item()
        self.ticket_editor.setFocus()

    def _insert_timestamp(self) -> None:
        now_str = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
        tag = f'<strong>[{now_str}]</strong> '
        cursor = self.ticket_editor.textCursor()
        cursor.insertHtml(tag)
        self.ticket_editor.setFocus()

    def _insert_image(self) -> None:
        file_path, _ = QFileDialog.getOpenFileName(
            self,
            "Select Screenshot or Image",
            "",
            "Images (*.png *.jpg *.jpeg *.bmp *.webp *.gif)",
        )
        if file_path:
            with open(file_path, "rb") as f:
                data = f.read()
            self.ticket_editor.insert_embedded_image(data)
        self.ticket_editor.setFocus()

    def _insert_template(self, skeleton_name: str) -> None:
        if self.scratchpad_service:
            html = self.scratchpad_service.get_skeleton_html(skeleton_name)
        else:
            html = TICKET_SKELETONS.get(skeleton_name, "")
        if html:
            if hasattr(self.ticket_editor, "insert_template_html"):
                self.ticket_editor.insert_template_html(html)
            else:
                self.ticket_editor.textCursor().insertHtml(html)
        self.ticket_editor.setFocus()

    def update_templates_menu(self, custom_templates: Optional[list] = None) -> None:
        """Updates the sidebar template menu with built-in and custom templates."""
        if not hasattr(self, "btn_template"):
            return
        template_menu = QMenu(self.btn_template)
        for name in TICKET_SKELETONS.keys():
            act = template_menu.addAction(name)
            act.triggered.connect(lambda checked=False, n=name: self._insert_template(n))
        if custom_templates:
            template_menu.addSeparator()
            for item in custom_templates:
                title = item.get("title", "") if isinstance(item, dict) else str(item)
                if title:
                    act = template_menu.addAction(title)
                    act.triggered.connect(lambda checked=False, t=title: self._insert_template(t))
        self.btn_template.setMenu(template_menu)

    def _copy_formatted_note(self) -> None:
        if self._active_editor:
            self.save_requested.emit(self.ticket_editor.scratchpad_id)
            self.ticket_editor.copy_formatted_note()
            t_label = f"#{self._current_ticket_number}".strip() if self._current_ticket_number else ""
            msg = f"✓ Copied formatted note ({t_label}) with rich text & images to clipboard!" if t_label else "✓ Copied formatted note with rich text & images to clipboard!"
            self.status_message_requested.emit(msg, 3500)

    def _copy_clean_note(self) -> None:
        if self._active_editor:
            self.save_requested.emit(self.ticket_editor.scratchpad_id)
            if self.scratchpad_service:
                clean_text = self.scratchpad_service.export_as_plain_ticket_note(self.ticket_editor.scratchpad_id)
            else:
                clean_text = self.ticket_editor.toPlainText()
            QApplication.clipboard().setText(clean_text)
            t_label = f"#{self._current_ticket_number}".strip() if self._current_ticket_number else ""
            msg = f"✓ Copied clean note ({t_label}) for ticketing system to clipboard!" if t_label else "✓ Copied clean note for ticketing system to clipboard!"
            self.status_message_requested.emit(msg, 3500)

    def _arrange_content_columns(self, num_columns: int) -> None:
        """Arranges existing groupboxes into 1 or 2 columns without recreation."""
        for group in self._content_groups:
            self.content_layout.removeWidget(group)

        for index, group in enumerate(self._content_groups):
            if num_columns == 1:
                self.content_layout.addWidget(group, index, 0)
            else:
                self.content_layout.addWidget(group, index // 2, index % 2)

        self._current_columns = num_columns
        if num_columns == 1:
            self.content_widget.setMinimumSize(220, 6 * 75)
        else:
            self.content_widget.setMinimumSize(360, 3 * 75)

    def resizeEvent(self, event) -> None:
        super().resizeEvent(event)
        self._reflow_content()

    def eventFilter(self, watched, event):
        if watched is self.scroll_area.viewport() and event.type() == QEvent.Resize:
            self._reflow_content()
        return super().eventFilter(watched, event)

    def _reflow_content(self):
        if not hasattr(self, "scroll_area"):
            return
        center_w = self.scroll_area.viewport().width()
        if center_w < 500 and self._current_columns != 1:
            self._arrange_content_columns(1)
        elif center_w >= 500 and self._current_columns != 2:
            self._arrange_content_columns(2)
