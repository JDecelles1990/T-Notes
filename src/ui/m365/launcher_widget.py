"""Adaptive M365 workspace shell, independent of ticket and backend ownership."""

from PySide6.QtCore import Qt, Signal, QEvent
from PySide6.QtWidgets import (
    QComboBox, QGridLayout, QGroupBox, QHBoxLayout, QLabel, QLineEdit,
    QListWidget, QListWidgetItem, QPlainTextEdit, QPushButton, QScrollArea,
    QSplitter, QToolButton, QVBoxLayout, QWidget,
)

from src.services.m365_catalog_service import CatalogError, M365CatalogService


class M365LauncherWidget(QWidget):
    """Adaptive M365 workspace shell with responsive reflow and collapsible sidebars."""

    back_requested = Signal()

    def __init__(self, parent=None, *, catalog_service=None):
        super().__init__(parent)
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
        self.ticket_panel_toggle.setText("Active Ticket Notes (future)")
        self.ticket_panel_toggle.setToolTip("Show or hide the future ticket sidebar placeholder")
        self.ticket_panel_toggle.setAccessibleName("Show future active ticket notes panel")
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
        self.navigation.currentItemChanged.connect(self._category_changed)
        self.search_input.textChanged.connect(self._refresh_operations)
        self.risk_filter.currentIndexChanged.connect(self._refresh_operations)
        self.lifecycle_filter.currentIndexChanged.connect(self._refresh_operations)
        self.operation_list.currentItemChanged.connect(self._operation_changed)
        self.navigation.setCurrentRow(0)

        self._arrange_content_columns(2)
        scroll.setWidget(content)

        # Pane 2: Ticket Sidebar Placeholder
        self.ticket_sidebar = QGroupBox("Active Ticket Notes", self.workspace_splitter)
        self.ticket_sidebar.setMinimumWidth(110)
        sidebar_layout = QVBoxLayout(self.ticket_sidebar)
        sidebar_layout.setContentsMargins(8, 12, 8, 8)
        placeholder = QLabel(
            "Reserved for future ticket integration.\n"
            "Use Back to T-Notes to edit existing notes.", self.ticket_sidebar
        )
        placeholder.setWordWrap(True)
        sidebar_layout.addWidget(placeholder)
        sidebar_layout.addStretch()

        self.nav_toggle.toggled.connect(self._on_nav_toggled)
        self.ticket_panel_toggle.toggled.connect(self._on_ticket_panel_toggled)

        self.workspace_splitter.setStretchFactor(0, 0)
        self.workspace_splitter.setStretchFactor(1, 1)
        self.workspace_splitter.setStretchFactor(2, 0)
        self.workspace_splitter.setSizes([130, 580, 140])
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
            message = "No company selected. Company and verified tenant connections are not configured."
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
            sizes[2] = 140
            self.workspace_splitter.setSizes(sizes)

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
