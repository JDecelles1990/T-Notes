"""Adaptive M365 workspace shell, independent of ticket and backend ownership."""

from PySide6.QtCore import Qt, Signal
from PySide6.QtWidgets import (
    QGridLayout, QGroupBox, QHBoxLayout, QLabel, QListWidget,
    QPushButton, QScrollArea, QSplitter, QToolButton, QVBoxLayout, QWidget,
)


class M365LauncherWidget(QWidget):
    """Adaptive M365 workspace shell with responsive reflow and collapsible sidebars."""

    back_requested = Signal()

    def __init__(self, parent=None):
        super().__init__(parent)
        self.setObjectName("m365LauncherWorkspace")
        self._current_columns = 2

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

        notice = QLabel("GUI foundation only — no Microsoft 365 connection or execution.", self)
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
        self.navigation.addItems([
            "Dashboard", "Companies", "Entra ID", "Exchange Online",
            "Licensing", "Teams", "SharePoint", "OneDrive", "Intune",
            "Security", "Reports", "Workflows",
        ])
        self.navigation.setAccessibleName("Future M365 categories")
        self.navigation.setToolTip("Category navigation is a visual placeholder")
        self.navigation.setEnabled(False)
        self.navigation.setMinimumWidth(110)
        self.navigation.setMaximumWidth(180)

        # Pane 1: Center Scroll Area with Groupboxes
        scroll = QScrollArea(self.workspace_splitter)
        scroll.setWidgetResizable(True)
        scroll.setHorizontalScrollBarPolicy(Qt.ScrollBarAsNeeded)
        scroll.setVerticalScrollBarPolicy(Qt.ScrollBarAsNeeded)
        self.scroll_area = scroll

        content = QWidget(scroll)
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
        center_w = self.scroll_area.viewport().width()
        if center_w < 500 and self._current_columns != 1:
            self._arrange_content_columns(1)
        elif center_w >= 500 and self._current_columns != 2:
            self._arrange_content_columns(2)
