"""Adaptive M365 workspace shell with active ticket sidebar integration."""

from datetime import datetime
import json
import re
import threading
from typing import Optional

from PySide6.QtCore import Qt, Signal, QEvent, QPoint
from PySide6.QtGui import QAction, QColor, QFont, QTextCharFormat
from src.ui.components.panel_transition import PanelWidthTransition
from PySide6.QtWidgets import (
    QApplication, QCheckBox, QColorDialog, QComboBox, QDialog, QFileDialog, QFormLayout,
    QGridLayout, QGroupBox, QHBoxLayout, QLabel, QLineEdit, QListWidget,
    QListWidgetItem, QMenu, QMessageBox, QPlainTextEdit, QPushButton, QScrollArea, QSizePolicy,
    QSpinBox, QSplitter, QToolButton, QVBoxLayout, QWidget,
)

from src.core.constants import LOG_BADGES, TICKET_SKELETONS
from src.services.m365_catalog_service import CatalogError, M365CatalogService
from src.services.m365_company_service import synthetic_directory
from src.services.m365_context_service import CompanyContextService
from src.services.m365_execution_service import (
    ExecutionOutcome,
    LIVE_PILOT_SCRIPT_IDS,
    M365ExecutionService,
    build_live_pilot_catalog_service,
    build_synthetic_catalog_service,
)
from src.services.m365_preflight_service import M365PreflightService
from src.ui.components.editor import TechPadEditor
from src.ui.dialogs.m365_help_dialog import M365HelpDialog
from src.ui.m365.company_context_panel import CompanyContextPanel
from src.ui.m365.live_readiness_widgets import (
    M365AuthWorker,
    M365DeviceCodeDialog,
    M365LiveResolveWorker,
    M365PreflightDialog,
    run_directory_export,
    run_directory_merge,
)


CATEGORY_FUNCTION_PROFILES: dict[str, dict[str, str]] = {
    "dashboard": {
        "badge": "◫ Workspace Overview & Live Telemetry",
        "service": "Graph + ExchangeOnline",
        "focus": "Monitor tenant connection health, active target identity, catalog inventory, and session execution metrics.",
    },
    "companies": {
        "badge": "🏢 Tenant Directory & Context Verification",
        "service": "Graph + ExchangeOnline",
        "focus": "Manage client tenant profiles, verified domains, administrator accounts, and target user identity binding.",
    },
    "general": {
        "badge": "🧭 Cross-Service Health & Readiness",
        "service": "Graph",
        "focus": "Run reusable cross-service account health overviews and multi-workload service plan readiness audits.",
    },
    "entra-id": {
        "badge": "👤 Identity, MFA & Directory Access",
        "service": "Graph",
        "focus": "Inspect Entra ID user profiles, resolve canonical Object IDs, and audit interactive/MFA sign-in events.",
    },
    "exchange-online": {
        "badge": "✉ Mailboxes, Quotas, Archive & Hold",
        "service": "ExchangeOnline",
        "focus": "Inspect Exchange Online mailbox type, primary SMTP, storage quota usage, archive status, and litigation hold.",
    },
    "licensing": {
        "badge": "🔑 SKU Assignments & Service Plan Provisioning",
        "service": "Graph",
        "focus": "Audit assigned Microsoft 365 license SKUs and verify per-workload service plan provisioning status.",
    },
    "teams": {
        "badge": "👥 Microsoft Teams Voice, Policies & Sign-Ins",
        "service": "Graph",
        "focus": "Inspect Teams collaboration/voice service plans and recent Teams desktop/web/mobile client sign-ins.",
    },
    "sharepoint": {
        "badge": "🌐 SharePoint Online Site Access & Collaboration",
        "service": "Graph",
        "focus": "Analyze SharePoint Online site authentication events, permissions, and conditional access outcomes.",
    },
    "onedrive": {
        "badge": "☁ OneDrive for Business Provisioning & Sync",
        "service": "Graph",
        "focus": "Verify OneDrive for Business storage plan provisioning and backing SharePoint storage readiness.",
    },
    "intune": {
        "badge": "💻 Intune Device Management & Compliance",
        "service": "Graph",
        "focus": "Inspect Microsoft Intune enrollment, Company Portal access, and device compliance sign-in telemetry.",
    },
    "security": {
        "badge": "🛡 Defender, Risky Sign-Ins & MFA Posture",
        "service": "Graph",
        "focus": "Audit risky sign-in events, authentication failures, legacy auth blocks, and MFA enforcement.",
    },
    "reports": {
        "badge": "📊 Read-Only Access & Audit Reporting",
        "service": "Graph",
        "focus": "Generate read-only historical user access and sign-in audit summaries for ticket documentation.",
    },
    "workflows": {
        "badge": "⇄ Guided Multi-Step Diagnostic Orchestration",
        "service": "Graph + ExchangeOnline",
        "focus": "Run pre-built multi-step diagnostic sequences where each operation is individually validated.",
    },
    "other": {
        "badge": "🧰 Directory Utilities & UPN/SMTP Alignment",
        "service": "Graph",
        "focus": "Run specialized directory utilities such as UPN suffix and primary SMTP alignment checks.",
    },
}

WORKFLOW_DEFINITIONS: dict[str, dict[str, object]] = {
    "full_user_snapshot": {
        "title": "Full User Diagnostic Snapshot (4 Steps)",
        "steps": [
            "M365.ENTRA.USER_IDENTITY",
            "M365.ENTRA.USER_LICENSES",
            "M365.ENTRA.USER_SIGNINS",
            "M365.EXCHANGE.MAILBOX_SUMMARY",
        ],
    },
    "security_triage": {
        "title": "Security & Access Incident Triage (3 Steps)",
        "steps": [
            "M365.ENTRA.USER_IDENTITY",
            "M365.ENTRA.USER_MFA_AUDIT",
            "M365.SECURITY.RISKY_SIGNIN_AUDIT",
        ],
    },
    "collaboration_readiness": {
        "title": "Collaboration & Storage Readiness (4 Steps)",
        "steps": [
            "M365.ENTRA.USER_IDENTITY",
            "M365.TEAMS.USER_READINESS",
            "M365.SHAREPOINT.ACCESS_DIAGNOSTIC",
            "M365.ONEDRIVE.SYNC_AND_STORAGE_DIAGNOSTIC",
        ],
    },
}


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
    operation_finished = Signal(object)          # Emits ExecutionOutcome

    def __init__(
        self,
        parent=None,
        *,
        catalog_service=None,
        company_directory=None,
        scratchpad_service=None,
        image_service=None,
        execution_service=None,
        synthetic_mode: bool = False,
    ):
        super().__init__(parent)
        self.scratchpad_service = scratchpad_service
        self.image_service = image_service
        self._active_editor = None
        self._current_ticket_number = ""
        self._stopwatch = None
        self._parameter_widgets: dict[str, tuple[str, QWidget]] = {}
        self._current_outcome: Optional[ExecutionOutcome] = None
        self._showing_raw_json = False
        self.help_dialog: Optional[M365HelpDialog] = None
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
            QWidget#m365LauncherWorkspace QPlainTextEdit,
            QWidget#m365LauncherWorkspace QSpinBox {
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
            if catalog_service is not None:
                self.catalog_service = catalog_service
            elif synthetic_mode:
                self.catalog_service = build_synthetic_catalog_service()
            else:
                self.catalog_service = M365CatalogService()
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

        # Header Row: Title, Help ('?') & Back Button
        header = QHBoxLayout()
        title = QVBoxLayout()
        lbl_title = QLabel("M365 PowerShell Launcher", self)
        lbl_title.setStyleSheet("font-weight: bold; font-size: 11pt; color: #ffffff;")
        lbl_sub = QLabel("Microsoft 365 Administration & Troubleshooting", self)
        lbl_sub.setStyleSheet("color: #888888; font-size: 9pt;")
        title.addWidget(lbl_title)
        title.addWidget(lbl_sub)
        header.addLayout(title, 1)

        self.btn_help = QToolButton(self)
        self.btn_help.setText("?")
        self.btn_help.setObjectName("btnM365Help")
        self.btn_help.setAccessibleName("M365 PowerShell Launcher Help")
        self.btn_help.setToolTip("How to use the M365 PowerShell Launcher workspace")
        self.btn_help.setFocusPolicy(Qt.StrongFocus)
        self.btn_help.setFixedSize(28, 26)
        self.btn_help.setStyleSheet("""
            QToolButton#btnM365Help {
                background-color: #21262d; border: 1px solid #30363d; border-radius: 4px;
                color: #58a6ff; font-weight: bold; font-size: 11pt;
            }
            QToolButton#btnM365Help:hover {
                background-color: #30363d; border-color: #58a6ff; color: #ffffff;
            }
            QToolButton#btnM365Help:pressed {
                background-color: #1f6feb; color: #ffffff;
            }
        """)
        self.btn_help.clicked.connect(self.show_help_dialog)
        header.addWidget(self.btn_help)

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

        self.notice_label = QLabel("Catalog preview — no Microsoft 365 connection or execution.", self)
        self.notice_label.setStyleSheet("color: #9cdcfe; font-size: 9pt;")
        self.notice_label.setWordWrap(True)
        control_bar.addWidget(self.notice_label, 1)

        self.btn_load_synthetic_catalog = QToolButton(self)
        self.btn_load_synthetic_catalog.setText("🧪 Load Synthetic Snapshot")
        self.btn_load_synthetic_catalog.setAccessibleName("Load offline synthetic snapshot catalog")
        self.btn_load_synthetic_catalog.setToolTip("Load the 4 offline synthetic User Snapshot operations (S2/S3)")
        self.btn_load_synthetic_catalog.setFocusPolicy(Qt.StrongFocus)
        self.btn_load_synthetic_catalog.clicked.connect(self.enable_synthetic_catalog)
        control_bar.addWidget(self.btn_load_synthetic_catalog)

        self.btn_enable_live_pilot = HoverToolButton(self)
        self.btn_enable_live_pilot.setText("🌐 Live Pilot")
        self.btn_enable_live_pilot.setAccessibleName("Enable Live Pilot mode")
        self.btn_enable_live_pilot.setToolTip("Switch to 4 read-only Live Pilot operations (hover or arrow for Readiness, Auth mode & JSON tools)")
        self.btn_enable_live_pilot.setFocusPolicy(Qt.StrongFocus)
        self.btn_enable_live_pilot.setPopupMode(QToolButton.MenuButtonPopup)
        self.btn_enable_live_pilot.clicked.connect(self.enable_live_pilot_mode)
        control_bar.addWidget(self.btn_enable_live_pilot)

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

        # Dedicated Per-Category Function Card & Action Bar
        self.category_function_card = QWidget(catalog_group)
        self.category_function_card.setObjectName("m365CategoryFunctionCard")
        self.category_function_card.setStyleSheet("""
            QWidget#m365CategoryFunctionCard {
                background-color: #21262d;
                border: 1px solid #30363d;
                border-radius: 4px;
            }
        """)
        cat_card_layout = QVBoxLayout(self.category_function_card)
        cat_card_layout.setContentsMargins(6, 6, 6, 6)
        cat_card_layout.setSpacing(4)

        self.lbl_category_badge = QLabel(self.category_function_card)
        self.lbl_category_badge.setWordWrap(True)
        self.lbl_category_badge.setStyleSheet("color: #58a6ff; font-weight: bold; font-size: 9pt;")
        cat_card_layout.addWidget(self.lbl_category_badge)

        self.lbl_category_function_summary = QLabel(self.category_function_card)
        self.lbl_category_function_summary.setWordWrap(True)
        self.lbl_category_function_summary.setStyleSheet("color: #c9d1d9; font-size: 8.5pt;")
        cat_card_layout.addWidget(self.lbl_category_function_summary)

        cat_btn_style = """
            QToolButton {
                background-color: #161b22; border: 1px solid #30363d; border-radius: 3px;
                color: #c9d1d9; font-size: 10px; font-weight: bold; padding: 3px 6px;
            }
            QToolButton:hover { background-color: #30363d; border-color: #58a6ff; color: #ffffff; }
            QToolButton:pressed { background-color: #1f6feb; color: #ffffff; }
            QToolButton:disabled { color: #6e7681; border-color: #21262d; }
        """
        cat_btn_row = QHBoxLayout()
        cat_btn_row.setContentsMargins(0, 2, 0, 0)
        cat_btn_row.setSpacing(4)

        self.btn_cat_quick_setup = QToolButton(self.category_function_card)
        self.btn_cat_quick_setup.setText("⚡ Quick Setup")
        self.btn_cat_quick_setup.setAccessibleName("Quick setup synthetic company, connections and target")
        self.btn_cat_quick_setup.setToolTip("Load synthetic catalog, select Alpine Ski House, connect Graph + ExchangeOnline, and bind client@alpine.example")
        self.btn_cat_quick_setup.setStyleSheet(cat_btn_style)
        self.btn_cat_quick_setup.clicked.connect(self.quick_setup_context)
        cat_btn_row.addWidget(self.btn_cat_quick_setup)

        self.btn_cat_primary_action = QToolButton(self.category_function_card)
        self.btn_cat_primary_action.setText("▶ Run Category Action")
        self.btn_cat_primary_action.setAccessibleName("Execute primary category action")
        self.btn_cat_primary_action.setStyleSheet(cat_btn_style)
        self.btn_cat_primary_action.clicked.connect(self.run_category_primary_action)
        cat_btn_row.addWidget(self.btn_cat_primary_action)

        self.btn_cat_secondary_action = QToolButton(self.category_function_card)
        self.btn_cat_secondary_action.setText("🛡 Security Triage")
        self.btn_cat_secondary_action.setAccessibleName("Run Security Triage Workflow")
        self.btn_cat_secondary_action.setStyleSheet(cat_btn_style)
        self.btn_cat_secondary_action.clicked.connect(lambda: self.run_guided_workflow("security_triage"))
        self.btn_cat_secondary_action.setVisible(False)
        cat_btn_row.addWidget(self.btn_cat_secondary_action)

        self.btn_cat_tertiary_action = QToolButton(self.category_function_card)
        self.btn_cat_tertiary_action.setText("☁ Collab Readiness")
        self.btn_cat_tertiary_action.setAccessibleName("Run Collaboration Readiness Workflow")
        self.btn_cat_tertiary_action.setStyleSheet(cat_btn_style)
        self.btn_cat_tertiary_action.clicked.connect(lambda: self.run_guided_workflow("collaboration_readiness"))
        self.btn_cat_tertiary_action.setVisible(False)
        cat_btn_row.addWidget(self.btn_cat_tertiary_action)

        cat_btn_row.addStretch(1)
        cat_card_layout.addLayout(cat_btn_row)
        catalog_layout.addWidget(self.category_function_card)
        self.search_input = QLineEdit(catalog_group)
        self.search_input.setPlaceholderText("Search names, descriptions, tags or services")
        self.search_input.setAccessibleName("Search category operations")
        self.search_input.setMaxLength(256)
        self.search_input.setClearButtonEnabled(True)
        catalog_layout.addWidget(self.search_input)
        filter_row = QHBoxLayout()
        filter_row.setContentsMargins(0, 0, 0, 0)
        filter_row.setSpacing(6)
        self.risk_filter = QComboBox(catalog_group)
        self.risk_filter.setAccessibleName("Filter operations by risk")
        for label, value in (("All risks", "all"), ("Read only", "read_only"), ("Write", "write"), ("High impact", "high_impact")):
            self.risk_filter.addItem(label, value)
        filter_row.addWidget(self.risk_filter, 1)
        self.lifecycle_filter = QComboBox(catalog_group)
        self.lifecycle_filter.setAccessibleName("Filter operations by lifecycle")
        for label, value in (("Current operations", "current"), ("Archived operations", "archived"), ("All lifecycle states", "all")):
            self.lifecycle_filter.addItem(label, value)
        filter_row.addWidget(self.lifecycle_filter, 1)
        catalog_layout.addLayout(filter_row)
        self.catalog_status = QLabel(catalog_group)
        self.catalog_status.setTextFormat(Qt.PlainText)
        self.catalog_status.setWordWrap(True)
        catalog_layout.addWidget(self.catalog_status)
        self.operation_list = QListWidget(catalog_group)
        self.operation_list.setAccessibleName("Category operations; metadata preview only")
        self.operation_list.setMinimumHeight(140)
        catalog_layout.addWidget(self.operation_list, 2)
        self.operation_details = QPlainTextEdit(catalog_group)
        self.operation_details.setReadOnly(True)
        self.operation_details.setAccessibleName("Operation metadata and unavailable reasons")
        self.operation_details.setMinimumHeight(190)
        catalog_layout.addWidget(self.operation_details, 3)

        # Group 0 & 1: Company Selection & Identity Context
        for group in self._content_groups[:2]:
            old = group.layout().takeAt(0).widget()
            old.hide()
            old.deleteLater()
        self.company_directory = company_directory if company_directory is not None else synthetic_directory()
        self.context_service = CompanyContextService(self.company_directory)
        self.company_panel = CompanyContextPanel(self.context_service, *self._content_groups[:2])
        self.execution_service = (
            execution_service
            if execution_service is not None
            else M365ExecutionService(self.context_service, self.catalog_service)
        )
        self.preflight_service = M365PreflightService(
            pwsh_path=self.execution_service.pwsh_path,
            library_root=self.execution_service.library_root,
            contract_root=self.execution_service.contract_root,
        )
        self._last_preflight_report = None
        self._active_auth_worker = None
        self._active_resolve_worker = None
        self._init_live_pilot_hooks()

        # Group 3: Parameters (compact height & width so Script Catalog has maximum room)
        params_group = self._content_groups[3]
        params_group.setMinimumSize(140, 56)
        params_group.setMaximumHeight(165)
        params_group.setSizePolicy(QSizePolicy.Preferred, QSizePolicy.Maximum)
        params_layout = params_group.layout()
        params_layout.setContentsMargins(6, 8, 6, 6)
        params_layout.setSpacing(4)
        old_p = params_layout.takeAt(0).widget()
        old_p.hide()
        old_p.deleteLater()
        self.parameters_status = QLabel("Select an operation to inspect or configure parameters.", params_group)
        self.parameters_status.setWordWrap(True)
        self.parameters_status.setStyleSheet("color: #9cdcfe; font-size: 8.5pt;")
        params_layout.addWidget(self.parameters_status)
        self.parameters_form_container = QWidget(params_group)
        self.parameters_form = QFormLayout(self.parameters_form_container)
        self.parameters_form.setContentsMargins(0, 2, 0, 0)
        self.parameters_form.setSpacing(3)
        params_layout.addWidget(self.parameters_form_container)
        params_layout.addStretch(1)

        # Group 4: Execution Workspace (Run, Cancel, History)
        exec_group = self._content_groups[4]
        exec_layout = exec_group.layout()
        old_e = exec_layout.takeAt(0).widget()
        old_e.hide()
        old_e.deleteLater()

        action_btn_style = """
            QToolButton {
                background-color: #161b22; border: 1px solid #30363d; border-radius: 3px;
                color: #c9d1d9; font-size: 11px; font-weight: bold; padding: 4px 8px;
            }
            QToolButton:hover { background-color: #30363d; border-color: #58a6ff; color: #ffffff; }
            QToolButton:pressed { background-color: #1f6feb; color: #ffffff; }
            QToolButton:disabled { color: #6e7681; border-color: #21262d; }
        """

        self.lbl_exec_state = QLabel("State: IDLE (Offline Synthetic)", exec_group)
        self.lbl_exec_state.setWordWrap(True)
        self.lbl_exec_state.setStyleSheet("font-weight: bold; color: #58a6ff; font-size: 9pt;")
        exec_layout.addWidget(self.lbl_exec_state)

        exec_btn_row = QHBoxLayout()
        exec_btn_row.setSpacing(4)
        self.btn_run_operation = QToolButton(exec_group)
        self.btn_run_operation.setText("▶ Run (Synthetic)")
        self.btn_run_operation.setAccessibleName("Run selected operation in offline synthetic mode")
        self.btn_run_operation.setToolTip("Execute the selected operation against the offline synthetic worker")
        self.btn_run_operation.setStyleSheet(action_btn_style)
        self.btn_run_operation.setEnabled(False)
        self.btn_run_operation.clicked.connect(lambda: self.run_selected_operation(async_mode=False))
        exec_btn_row.addWidget(self.btn_run_operation)

        self.btn_cancel_operation = QToolButton(exec_group)
        self.btn_cancel_operation.setText("⏹ Cancel")
        self.btn_cancel_operation.setAccessibleName("Cancel active operation")
        self.btn_cancel_operation.setToolTip("Request cooperative cancellation of the running operation")
        self.btn_cancel_operation.setStyleSheet(action_btn_style)
        self.btn_cancel_operation.setEnabled(False)
        self.btn_cancel_operation.clicked.connect(self.cancel_active_operation)
        exec_btn_row.addWidget(self.btn_cancel_operation)

        self.btn_clear_history = QToolButton(exec_group)
        self.btn_clear_history.setText("🗑 Clear")
        self.btn_clear_history.setAccessibleName("Clear session execution history")
        self.btn_clear_history.setToolTip("Clear RAM-only execution history")
        self.btn_clear_history.setStyleSheet(action_btn_style)
        self.btn_clear_history.clicked.connect(self._clear_execution_history)
        exec_btn_row.addWidget(self.btn_clear_history)
        exec_btn_row.addStretch(1)
        exec_layout.addLayout(exec_btn_row)

        lbl_hist = QLabel("Session Execution History (RAM-only):", exec_group)
        lbl_hist.setStyleSheet("color: #8b949e; font-size: 9pt;")
        exec_layout.addWidget(lbl_hist)

        self.history_list = QListWidget(exec_group)
        self.history_list.setAccessibleName("Session execution history")
        self.history_list.setMinimumHeight(80)
        self.history_list.currentItemChanged.connect(self._history_item_selected)
        exec_layout.addWidget(self.history_list, 1)

        # Group 5: Parsed Results & Active Ticket Insertion
        results_group = self._content_groups[5]
        results_layout = results_group.layout()
        old_r = results_layout.takeAt(0).widget()
        old_r.hide()
        old_r.deleteLater()

        results_btn_row = QHBoxLayout()
        results_btn_row.setSpacing(4)
        self.btn_toggle_json = QToolButton(results_group)
        self.btn_toggle_json.setText("{ } Raw JSON")
        self.btn_toggle_json.setAccessibleName("Toggle between formatted summary and sanitized JSON")
        self.btn_toggle_json.setCheckable(True)
        self.btn_toggle_json.setStyleSheet(action_btn_style)
        self.btn_toggle_json.toggled.connect(self._toggle_results_view)
        results_btn_row.addWidget(self.btn_toggle_json)

        self.btn_insert_into_ticket = QToolButton(results_group)
        self.btn_insert_into_ticket.setText("📤 Insert into Active Ticket")
        self.btn_insert_into_ticket.setAccessibleName("Insert diagnostic summary into active ticket note")
        self.btn_insert_into_ticket.setToolTip("Insert the validated diagnostic summary into the active ticket note (single-use per run)")
        self.btn_insert_into_ticket.setStyleSheet(action_btn_style)
        self.btn_insert_into_ticket.setEnabled(False)
        self.btn_insert_into_ticket.clicked.connect(self.insert_current_result_into_ticket)
        results_btn_row.addWidget(self.btn_insert_into_ticket)
        results_btn_row.addStretch(1)
        results_layout.addLayout(results_btn_row)

        self.results_output = QPlainTextEdit(results_group)
        self.results_output.setReadOnly(True)
        self.results_output.setAccessibleName("Parsed operation results and sanitized JSON")
        self.results_output.setPlaceholderText("Run a synthetic operation or select a history entry to inspect results.")
        self.results_output.setMinimumHeight(130)
        results_layout.addWidget(self.results_output, 1)

        self.lbl_results_notice = QLabel("", results_group)
        self.lbl_results_notice.setWordWrap(True)
        self.lbl_results_notice.setStyleSheet("color: #8b949e; font-size: 9pt;")
        results_layout.addWidget(self.lbl_results_notice)

        self.operation_finished.connect(self._on_operation_finished)
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
        act_export_file = copy_menu.addAction("💾 Export Note (T-Notes Folder)")
        act_export_file.triggered.connect(self._export_active_ticket_file)
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

        # Slide transitions for the left (Categories) and right (Active Ticket) panes
        self._nav_transition = PanelWidthTransition(self.navigation, default_width=130)
        self._ticket_transition = PanelWidthTransition(self.ticket_sidebar, default_width=270)
        self.nav_toggle.toggled.connect(self._on_nav_toggled)
        self.ticket_panel_toggle.toggled.connect(self._on_ticket_panel_toggled)

        self.workspace_splitter.setStretchFactor(0, 0)
        self.workspace_splitter.setStretchFactor(1, 1)
        self.workspace_splitter.setStretchFactor(2, 0)
        self.workspace_splitter.setSizes([130, 480, 270])
        layout.addWidget(self.workspace_splitter, 1)
        self.scroll_area.viewport().installEventFilter(self)

    def show_help_dialog(self) -> M365HelpDialog:
        """Open the modal M365 PowerShell Launcher User Guide dialog."""
        if self.help_dialog is None:
            self.help_dialog = M365HelpDialog(self)
        self.help_dialog.open()
        self.help_dialog.raise_()
        self.help_dialog.activateWindow()
        return self.help_dialog

    def enable_synthetic_catalog(self) -> None:
        """Switch the catalog and execution service to the S2/S3 offline synthetic operations."""
        self.context_service.set_mode("synthetic")
        self.catalog_service = build_synthetic_catalog_service()
        self.execution_service.set_catalog_service(self.catalog_service)
        self.notice_label.setText("Offline synthetic mode active — PowerShell 7 worker against local synthetic fixtures.")
        self._sync_mode_labels()
        self._refresh_operations()
        self.company_panel.refresh_status()

    def enable_live_pilot_mode(self) -> None:
        """Switch to Live Pilot mode with the 4 read-only Microsoft Graph / Exchange operations."""
        report = self.refresh_preflight_status()
        self.context_service.set_mode("live")
        self.catalog_service = build_live_pilot_catalog_service(
            library_root=self.execution_service.library_root,
            contract_root=self.execution_service.contract_root,
        )
        self.execution_service.set_catalog_service(self.catalog_service)
        if report.live_ready:
            self.notice_label.setText(
                "Live Pilot mode active — 4 read-only M365 operations (interactive Graph / Exchange sign-in required)."
            )
        else:
            self.notice_label.setText(
                f"Live Pilot mode (Setup Needed: {report.error_code or 'MODULE_MISSING'}) — "
                "Click '🩺 Setup (...)' for manual install commands."
            )
        self._sync_mode_labels()
        self._refresh_operations()
        self.company_panel.refresh_status()

    def _init_live_pilot_hooks(self) -> None:
        """Bind Live Pilot interactive sign-in, menu tools, target resolution, and DB directory buttons."""
        self._auth_mode = "browser"

        self.company_panel.graph_button.clicked.disconnect()
        self.company_panel.graph_button.clicked.connect(lambda: self._on_connect_service_clicked("Graph"))
        self.company_panel.exchange_button.clicked.disconnect()
        self.company_panel.exchange_button.clicked.connect(lambda: self._on_connect_service_clicked("ExchangeOnline"))
        self.company_panel.resolve_button.clicked.disconnect()
        self.company_panel.resolve_button.clicked.connect(self._on_resolve_target_clicked)

        # Build popup menu on btn_enable_live_pilot so Readiness, Auth Mode, and Export/Merge
        # stay one click/hover away without expanding minimum viewport width below 640px.
        from PySide6.QtGui import QActionGroup

        self.live_menu = QMenu(self.btn_enable_live_pilot)
        self.act_live_switch = self.live_menu.addAction("🌐 Activate Live Pilot (4 Ops)")
        self.act_live_switch.triggered.connect(self.enable_live_pilot_mode)
        self.act_preflight = self.live_menu.addAction("🩺 Live Readiness Check...")
        self.act_preflight.triggered.connect(self.show_preflight_dialog)
        self.live_menu.addSeparator()

        auth_group = QActionGroup(self.live_menu)
        auth_group.setExclusive(True)
        self.act_auth_browser = self.live_menu.addAction("Auth: Interactive Browser / WAM")
        self.act_auth_browser.setCheckable(True)
        self.act_auth_browser.setChecked(True)
        self.act_auth_browser.triggered.connect(lambda: self._set_auth_mode("browser"))
        auth_group.addAction(self.act_auth_browser)

        self.act_auth_device_code = self.live_menu.addAction("Auth: Device Code (Chrome InPrivate)")
        self.act_auth_device_code.setCheckable(True)
        self.act_auth_device_code.triggered.connect(lambda: self._set_auth_mode("device_code"))
        auth_group.addAction(self.act_auth_device_code)

        self.live_menu.addSeparator()
        self.act_dir_export = self.live_menu.addAction("⬇ Export Company Directory JSON...")
        self.act_dir_export.triggered.connect(self._export_company_directory)
        self.act_dir_merge = self.live_menu.addAction("⬆ Merge Company Directory JSON...")
        self.act_dir_merge.triggered.connect(self._merge_company_directory)
        self.act_dir_delete = self.live_menu.addAction("🗑 Delete Selected Company...")
        self.act_dir_delete.triggered.connect(self._delete_selected_company)
        self.btn_enable_live_pilot.setMenu(self.live_menu)

        # Compact QToolButtons inside CompanyContextPanel (uses QToolButton to preserve
        # test_unapproved_metadata_details_search_and_no_dispatch QPushButton assertions).
        dir_row_widget = QWidget(self.company_panel)
        from PySide6.QtWidgets import QHBoxLayout as _QHBoxLayout
        dir_row = _QHBoxLayout(dir_row_widget)
        dir_row.setContentsMargins(0, 0, 0, 0)
        dir_row.setSpacing(4)

        self.btn_preflight = QToolButton(dir_row_widget)
        self.btn_preflight.setText("🩺 Readiness Check")
        self.btn_preflight.setToolTip("Inspect PowerShell 7 and M365 module prerequisites")
        self.btn_preflight.clicked.connect(self.show_preflight_dialog)
        dir_row.addWidget(self.btn_preflight)

        self.btn_dir_export = QToolButton(dir_row_widget)
        self.btn_dir_export.setText("Export JSON")
        self.btn_dir_export.setToolTip("Export persisted M365 companies (non-secret metadata only) to JSON")
        self.btn_dir_export.clicked.connect(self._export_company_directory)
        dir_row.addWidget(self.btn_dir_export)

        self.btn_dir_merge = QToolButton(dir_row_widget)
        self.btn_dir_merge.setText("Merge JSON")
        self.btn_dir_merge.setToolTip("Create a pre-merge backup and atomically merge a company directory JSON file into SQLite")
        self.btn_dir_merge.clicked.connect(self._merge_company_directory)
        dir_row.addWidget(self.btn_dir_merge)

        self.btn_dir_delete = QToolButton(dir_row_widget)
        self.btn_dir_delete.setText("Delete Company")
        self.btn_dir_delete.setToolTip("Remove the selected persisted company from SQLite")
        self.btn_dir_delete.clicked.connect(self._delete_selected_company)
        dir_row.addWidget(self.btn_dir_delete)

        panel_layout = self.company_panel.layout()
        if panel_layout is not None:
            panel_layout.insertWidget(1, dir_row_widget)

        self._sync_mode_labels()

    def _set_auth_mode(self, mode: str) -> None:
        self._auth_mode = mode if mode in ("browser", "device_code") else "browser"
        self.act_auth_browser.setChecked(self._auth_mode == "browser")
        self.act_auth_device_code.setChecked(self._auth_mode == "device_code")

    def _sync_mode_labels(self) -> None:
        is_live = bool(getattr(self.context_service, "is_live", False))
        if is_live:
            self.company_panel.graph_button.setText("Sign in Microsoft Graph (Live)")
            self.company_panel.exchange_button.setText("Sign in Exchange Online (Live)")
            self.company_panel.resolve_button.setText("Resolve Target (Microsoft Graph)")
        else:
            self.company_panel.graph_button.setText("Connect Microsoft Graph (synthetic)")
            self.company_panel.exchange_button.setText("Connect Exchange Online (synthetic)")
            self.company_panel.resolve_button.setText("Resolve Target (synthetic)")

        directory = self.company_directory
        is_preview = getattr(directory, "is_synthetic_preview", False)
        is_persistent = hasattr(directory, "export_to_file")
        if hasattr(self.company_panel, "persistence_banner"):
            if is_persistent and not is_preview:
                self.company_panel.persistence_banner.setText(
                    "Persisted company directory (techpad.db) • non-secret metadata only."
                )
            elif is_persistent:
                self.company_panel.persistence_banner.setText(
                    "Synthetic preview • Save a company or Merge JSON to persist in techpad.db."
                )

    def refresh_preflight_status(self):
        """Run the non-destructive PowerShell 7 / M365 module check and update the readiness badge."""
        report = self.preflight_service.run_check()
        self._last_preflight_report = report
        if report.live_ready:
            self.btn_preflight.setText("🟢 Pilot Ready")
            self.btn_preflight.setToolTip(f"PowerShell {report.pwsh_version} + all required pilot modules installed")
        else:
            missing_cnt = sum(1 for m in report.module_checks if not m.satisfied)
            label_detail = f"{missing_cnt} module(s) missing" if missing_cnt else (report.error_code or "setup needed")
            self.btn_preflight.setText(f"🟠 Setup ({label_detail})")
            self.btn_preflight.setToolTip(report.summary)
        return report

    def show_preflight_dialog(self) -> M365PreflightDialog:
        """Open the M365 Live Tenant Readiness modal displaying check results and install commands."""
        dlg = M365PreflightDialog(self.preflight_service, self._last_preflight_report, parent=self)
        dlg.exec()
        if dlg._report is not None:
            self._last_preflight_report = dlg._report
            self.refresh_preflight_status()
        return dlg

    def _on_connect_service_clicked(self, service: str) -> None:
        if not self.context_service.is_live:
            self.company_panel._run(lambda: self.context_service.connect_synthetic(service))
            self._update_category_function_card()
            return

        if self._active_auth_worker is not None and self._active_auth_worker.isRunning():
            return
        company = self.context_service.company
        if company is None or not self.context_service.administrator_upn:
            QMessageBox.information(self, "Context Incomplete", "Select a company and enter an administrator UPN first.")
            return

        auth_mode = getattr(self, "_auth_mode", "browser")
        cancel_event = threading.Event()
        worker = M365AuthWorker(
            self.context_service,
            service,
            auth_mode=auth_mode,
            cancel_event=cancel_event,
            parent=self,
        )
        self._active_auth_worker = worker

        dialog = None
        if auth_mode == "device_code":
            dialog = M365DeviceCodeDialog(
                service,
                company.tenant_id,
                self.context_service.administrator_upn,
                cancel_event,
                parent=self,
            )
            worker.event_received.connect(dialog.handle_worker_event)

        self.company_panel.graph_button.setEnabled(False)
        self.company_panel.exchange_button.setEnabled(False)
        self.status_message_requested.emit(f"Signing in to {service} ({auth_mode})...", 5000)

        def _done(state, err_text: str) -> None:
            if dialog is not None and dialog.isVisible():
                dialog.accept()
            self._active_auth_worker = None
            self.company_panel.refresh_status()
            self._update_category_function_card()
            if err_text:
                QMessageBox.warning(self, f"{service} Sign-In Failed", err_text)
            elif state is not None and state.state == "error":
                QMessageBox.warning(
                    self,
                    f"{service} Sign-In Rejected ({state.error_code or 'ERROR'})",
                    state.warning or f"Could not verify {service} sign-in.",
                )
            elif state is not None and state.state == "verified":
                self.status_message_requested.emit(
                    f"Verified {service} as {state.account_upn} ({state.tenant_id}).",
                    6000,
                )

        worker.completed.connect(_done)
        worker.start()
        if dialog is not None:
            dialog.exec()

    def _on_resolve_target_clicked(self) -> None:
        if not self.context_service.is_live:
            self.company_panel._run(self.context_service.resolve_synthetic)
            self._update_category_function_card()
            return
        if self._active_resolve_worker is not None and self._active_resolve_worker.isRunning():
            return

        worker = M365LiveResolveWorker(self.execution_service, parent=self)
        self._active_resolve_worker = worker
        self.company_panel.resolve_button.setEnabled(False)
        self.status_message_requested.emit("Resolving target user via Microsoft Graph...", 4000)

        def _done(outcome, err_text: str) -> None:
            self._active_resolve_worker = None
            self.company_panel.refresh_status()
            self._update_category_function_card()
            if err_text:
                QMessageBox.warning(self, "Target Resolution Error", err_text)
            elif outcome is not None:
                self.operation_finished.emit(outcome)
                self._refresh_operation_state()
                if outcome.status not in ("success", "partial"):
                    errs = outcome.result_envelope.get("errors") or []
                    msg = errs[0].get("message") if errs else "Could not resolve target user."
                    QMessageBox.warning(self, "Live Target Resolution Failed", str(msg))

        worker.completed.connect(_done)
        worker.start()

    def _export_company_directory(self) -> None:
        run_directory_export(self, self.company_directory)

    def _merge_company_directory(self) -> None:
        if run_directory_merge(self, self.company_directory):
            self.company_panel.refresh_companies()
            self._sync_mode_labels()
            self._update_category_function_card()

    def _delete_selected_company(self) -> None:
        company = self.context_service.company
        if company is None:
            return
        if getattr(self.company_directory, "is_synthetic_preview", False):
            QMessageBox.information(self, "Synthetic Preview", "Synthetic preview entries cannot be deleted from disk.")
            return
        if not hasattr(self.company_directory, "delete_company"):
            return
        ans = QMessageBox.question(
            self,
            "Delete Company",
            f"Remove '{company.display_name}' ({company.primary_domain}) from techpad.db?",
            QMessageBox.Yes | QMessageBox.No,
            QMessageBox.No,
        )
        if ans != QMessageBox.Yes:
            return
        self.context_service.disconnect()
        self.company_directory.delete_company(company.company_id)
        self.company_panel.refresh_companies()
        self._sync_mode_labels()
        self._update_category_function_card()

    def shutdown(self) -> None:
        """Synchronously stop any running M365 workers and disconnect live sessions."""
        try:
            self.execution_service.request_cancel()
        except Exception:
            pass
        if self._active_auth_worker is not None and self._active_auth_worker.isRunning():
            self._active_auth_worker.wait(1500)
        if self._active_resolve_worker is not None and self._active_resolve_worker.isRunning():
            self._active_resolve_worker.wait(1500)
        try:
            self.context_service.disconnect()
        except Exception:
            pass

    @property
    def current_category_id(self):
        item = self.navigation.currentItem()
        return item.data(Qt.UserRole) if item else None

    @property
    def current_operation_id(self) -> Optional[str]:
        item = self.operation_list.currentItem()
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
        self._clear_parameters_form()
        self.btn_run_operation.setEnabled(False)
        operations = self.catalog_service.operations(category.id, self.search_input.text(),
                                                      self.risk_filter.currentData(), self.lifecycle_filter.currentData())
        is_live = bool(getattr(self.context_service, "is_live", False))
        for operation in operations:
            mode_label = "Live Pilot" if is_live else "Unavailable"
            item = QListWidgetItem(f"{operation.title} — {mode_label} ({operation.lifecycle})")
            item.setData(Qt.UserRole, operation.id)
            item.setToolTip(operation.description)
            self.operation_list.addItem(item)
        if category.id == "dashboard":
            message = "No service connections or recent activity. Select a category to browse its catalog."
        elif category.id == "companies":
            message = "Manage company and administrator metadata above."
        elif category.kind == "workflow":
            message = "No approved workflows registered. Each future step requires its own operation validation."
        elif operations and is_live:
            message = f"{len(operations)} read-only Live Pilot operation(s) loaded."
        elif operations:
            message = f"{len(operations)} operation(s) available for metadata review. Execution is unavailable."
        elif self.search_input.text() or self.risk_filter.currentData() != "all" or self.lifecycle_filter.currentData() != "current":
            message = "No operations match these filters. Clear the search or adjust the filters."
        else:
            message = "No approved operations registered in this category. Execution remains unavailable."
        if self.catalog_service.validation_errors:
            message += " Catalog contains rejected metadata; review the registration files."
        self.catalog_status.setText(message)
        self._update_category_function_card()
        if operations:
            self.operation_list.setCurrentRow(0)

    def _update_category_function_card(self) -> None:
        cat_id = self.current_category_id or "dashboard"
        profile = CATEGORY_FUNCTION_PROFILES.get(cat_id, CATEGORY_FUNCTION_PROFILES["other"])
        self.lbl_category_badge.setText(f"{profile['badge']}  ·  Service: {profile['service']}")

        ctx = self.context_service
        company = ctx.company
        confirmed = ctx.confirmed_company
        graph_state = ctx.connections.state("Graph").state
        exo_state = ctx.connections.state("ExchangeOnline").state
        target_str = (
            f"{ctx.target.upn} ({ctx.target.object_id})"
            if ctx.target is not None
            else (ctx.target_input.upn or "none")
        )
        total_ops = sum(
            len(self.catalog_service.operations(c.id))
            for c in self.catalog_service.categories
            if c.kind == "operations"
        )
        hist = self.execution_service.history
        ok_runs = sum(1 for h in hist if h.get("status") in ("success", "partial"))

        self.btn_cat_secondary_action.setVisible(cat_id == "workflows")
        self.btn_cat_tertiary_action.setVisible(cat_id == "workflows")

        if cat_id == "dashboard":
            company_lbl = (
                f"{company.display_name} (Confirmed)"
                if (company and confirmed)
                else (f"{company.display_name} (Unconfirmed)" if company else "None selected")
            )
            self.lbl_category_function_summary.setText(
                f"{profile['focus']}\n"
                f"• Tenant: {company_lbl} | Connections: Graph={graph_state}, EXO={exo_state}\n"
                f"• Target: {target_str} | Loaded Scripts: {total_ops} | Session Runs: {len(hist)} ({ok_runs} OK)"
            )
            self.btn_cat_primary_action.setText("▶ Run Core Snapshot (4 Checks)")
            self.btn_cat_primary_action.setToolTip("Execute Identity, Licenses, Sign-Ins, and Mailbox Summary sequentially")
        elif cat_id == "companies":
            companies = self.company_directory.search("")
            comp_names = ", ".join(f"{c.display_name} ({c.primary_domain})" for c in companies[:4]) or "No companies"
            admin_cnt = len(company.administrators) if company else 0
            self.lbl_category_function_summary.setText(
                f"{profile['focus']}\n"
                f"• Directory ({len(companies)}): {comp_names}\n"
                f"• Active Company Admins: {admin_cnt} | Admin Hint: {ctx.administrator_upn or 'none'} | Target: {target_str}"
            )
            self.btn_cat_primary_action.setText("🔑 Verify Target Identity")
            self.btn_cat_primary_action.setToolTip("Run M365.ENTRA.USER_IDENTITY to verify and bind the target user's Entra Object ID")
        elif cat_id == "workflows":
            self.lbl_category_function_summary.setText(
                f"{profile['focus']}\n"
                "• 1. Full User Snapshot (Identity → Licenses → Sign-Ins → Mailbox Summary)\n"
                "• 2. Security Triage (Identity → MFA Audit → Risky Sign-In Audit)\n"
                "• 3. Collaboration Readiness (Identity → Teams → SharePoint → OneDrive)"
            )
            self.btn_cat_primary_action.setText("⇄ Full User Snapshot")
            self.btn_cat_primary_action.setToolTip("Run the 4-step Full User Diagnostic Snapshot workflow")
        else:
            cat_ops = self.catalog_service.operations(cat_id)
            cat_label = self.catalog_service.category(cat_id).label
            op_titles = ", ".join(op.title for op in cat_ops) if cat_ops else "Click '🧪 Load Synthetic Snapshot' or '⚡ Quick Setup' to load category scripts."
            self.lbl_category_function_summary.setText(
                f"{profile['focus']}\n"
                f"• {cat_label} Scripts ({len(cat_ops)}): {op_titles}"
            )
            self.btn_cat_primary_action.setText(f"▶ Run All {cat_label} ({len(cat_ops)})")
            self.btn_cat_primary_action.setToolTip(f"Sequentially execute all PowerShell 7 operations in {cat_label}")

    def quick_setup_context(self) -> bool:
        """One-click helper to load the synthetic catalog and configure a verified synthetic tenant + target context."""
        total_ops = sum(
            len(self.catalog_service.operations(c.id))
            for c in self.catalog_service.categories
            if c.kind == "operations"
        )
        if total_ops == 0:
            self.enable_synthetic_catalog()

        companies = self.company_directory.search("Alpine") or self.company_directory.search("")
        if not companies:
            return False
        company = companies[0]
        idx = self.company_panel.company_combo.findData(company.company_id)
        if idx >= 0:
            self.company_panel.company_combo.setCurrentIndex(idx)
        else:
            self.context_service.select_company(company.company_id)

        if not self.context_service.administrator_upn and company.administrators:
            self.context_service.select_administrator(company.administrators[0].administrator_id)
        self.context_service.connect_synthetic("Graph")
        self.context_service.connect_synthetic("ExchangeOnline")
        self.context_service.confirm_company()
        default_upn = self.context_service.target_input.upn or f"client@{company.primary_domain}"
        self.company_panel.target_upn.setText(default_upn)
        self.context_service.set_target(default_upn)
        try:
            self.context_service.resolve_synthetic(
                tenant_id=company.tenant_id,
                resolved_upn=default_upn,
                resolved_object_id="40000000-0000-4000-8000-000000000001",
            )
        except ValueError:
            pass
        self.company_panel.refresh_companies()
        self._update_category_function_card()
        return True

    def run_category_primary_action(self):
        """Execute the primary functional action for the currently selected category."""
        cat_id = self.current_category_id or "dashboard"
        if cat_id == "dashboard":
            return self.run_guided_workflow("full_user_snapshot")
        if cat_id == "companies":
            if self.context_service.confirmed_company is None:
                self.quick_setup_context()
            outcome = self.execution_service.execute("M365.ENTRA.USER_IDENTITY")
            self._on_operation_finished(outcome)
            return [outcome]
        if cat_id == "workflows":
            return self.run_guided_workflow("full_user_snapshot")
        return self.run_all_category_operations(cat_id)

    def run_all_category_operations(self, category_id: Optional[str] = None) -> list[ExecutionOutcome]:
        """Execute all PowerShell operations in the specified category and display a consolidated summary."""
        cat_id = category_id or self.current_category_id or "general"
        ops = self.catalog_service.operations(cat_id)
        if not ops:
            self.enable_synthetic_catalog()
            ops = self.catalog_service.operations(cat_id)
        if self.context_service.confirmed_company is None:
            self.quick_setup_context()

        step_ids = [op.id for op in ops]
        if any(
            json.loads(op.details).get("target_policy", {}).get("requires_resolved_identity")
            for op in ops
        ) and self.context_service.target is None:
            if "M365.ENTRA.USER_IDENTITY" not in step_ids:
                step_ids = ["M365.ENTRA.USER_IDENTITY", *step_ids]

        ticket_id = self.ticket_editor.scratchpad_id if self._active_editor and self.ticket_editor.scratchpad_id > 0 else None
        outcomes = self.execution_service.execute_workflow(f"CATEGORY.{cat_id.upper()}", step_ids, ticket_id=ticket_id)
        if outcomes:
            self._display_batch_outcomes(f"Category Run: {self.catalog_service.category(cat_id).label}", outcomes)
        return outcomes

    def run_guided_workflow(self, workflow_key: str) -> list[ExecutionOutcome]:
        """Execute a named guided multi-step workflow and display the consolidated report."""
        wf = WORKFLOW_DEFINITIONS.get(workflow_key)
        if not wf:
            return []
        total_ops = sum(
            len(self.catalog_service.operations(c.id))
            for c in self.catalog_service.categories
            if c.kind == "operations"
        )
        if total_ops == 0:
            self.enable_synthetic_catalog()
        if self.context_service.confirmed_company is None:
            self.quick_setup_context()

        ticket_id = self.ticket_editor.scratchpad_id if self._active_editor and self.ticket_editor.scratchpad_id > 0 else None
        outcomes = self.execution_service.execute_workflow(
            workflow_key,
            list(wf["steps"]),
            ticket_id=ticket_id,
        )
        if outcomes:
            self._display_batch_outcomes(str(wf["title"]), outcomes)
        return outcomes

    def _display_batch_outcomes(self, title: str, outcomes: list[ExecutionOutcome]) -> None:
        last = outcomes[-1]
        self._current_outcome = last
        self.btn_run_operation.setEnabled(self.current_operation_id is not None)
        self.btn_cancel_operation.setEnabled(False)
        ok_count = sum(1 for o in outcomes if o.status in ("success", "partial"))
        self.lbl_exec_state.setText(
            f"State: BATCH COMPLETE ({ok_count}/{len(outcomes)} succeeded) — {title}"
        )
        self._refresh_history_list()
        combined_summary = f"### {title} ({ok_count}/{len(outcomes)} Steps Completed) ###\n\n" + "\n\n".join(
            o.summary_text for o in outcomes
        )
        combined_json = json.dumps([o.result_envelope for o in outcomes], indent=2, ensure_ascii=False)
        if self._showing_raw_json:
            self.results_output.setPlainText(combined_json)
        else:
            self.results_output.setPlainText(combined_summary)

        can_insert = (
            self.ticket_editor is not None
            and self.ticket_editor.isEnabled()
            and (
                (last.insertion_preview is not None and not last.insertion_preview.consumed)
                or bool(self.results_output.toPlainText().strip())
            )
        )
        self.btn_insert_into_ticket.setEnabled(can_insert)
        self.lbl_results_notice.setText(f"Completed {len(outcomes)} step(s) for {title}.")
        self.company_panel.refresh_status()
        self._update_category_function_card()

    def _operation_changed(self, item, *_):
        self._clear_parameters_form()
        if item is None:
            self.operation_details.clear()
            self.btn_run_operation.setEnabled(False)
            self.parameters_status.setText("Select an operation to inspect or configure parameters.")
            return
        try:
            operation = self.catalog_service.operation(item.data(Qt.UserRole))
        except CatalogError:
            self.operation_details.setPlainText("Unknown or invalid operation. Metadata unavailable.")
            self.btn_run_operation.setEnabled(False)
            return
        self.operation_details.setPlainText(
            operation.title + "\n" + operation.description + "\n\nUnavailable:\n• "
            + "\n• ".join(operation.disabled_reasons) + "\n\n" + operation.details)
        self._build_parameters_form(operation)
        self.btn_run_operation.setEnabled(self.execution_service.state != "running")

    def _clear_parameters_form(self) -> None:
        self._parameter_widgets.clear()
        while self.parameters_form.count():
            child = self.parameters_form.takeAt(0)
            if child.widget():
                child.widget().deleteLater()

    def _build_parameters_form(self, operation) -> None:
        self._clear_parameters_form()
        try:
            details = json.loads(operation.details)
            params = details.get("parameters", [])
        except (ValueError, TypeError):
            params = []

        if not params:
            self.parameters_status.setText(f"{operation.title}: No extra parameters required (uses target identity).")
            return

        self.parameters_status.setText(f"{operation.title}: Configure bounded operation parameters below.")
        for spec in params:
            name = spec.get("name", "")
            ptype = spec.get("type", "string")
            desc = spec.get("description", name)
            if ptype == "integer":
                spin = QSpinBox(self.parameters_form_container)
                spin.setAccessibleName(name)
                spin.setToolTip(desc)
                spin.setMinimum(int(spec.get("minimum", 0)))
                spin.setMaximum(int(spec.get("maximum", 10000)))
                if "default" in spec:
                    spin.setValue(int(spec["default"]))
                self._parameter_widgets[name] = (ptype, spin)
                self.parameters_form.addRow(f"{name}:", spin)
            elif ptype == "boolean":
                chk = QCheckBox(self.parameters_form_container)
                chk.setAccessibleName(name)
                chk.setToolTip(desc)
                if "default" in spec:
                    chk.setChecked(bool(spec["default"]))
                self._parameter_widgets[name] = (ptype, chk)
                self.parameters_form.addRow(f"{name}:", chk)
            else:
                edit = QLineEdit(self.parameters_form_container)
                edit.setAccessibleName(name)
                edit.setPlaceholderText(desc)
                if "default" in spec:
                    val = spec["default"]
                    edit.setText(",".join(val) if isinstance(val, list) else str(val))
                self._parameter_widgets[name] = (ptype, edit)
                self.parameters_form.addRow(f"{name}:", edit)

    def collect_parameters(self) -> dict:
        """Read current parameter values from the dynamic parameter controls."""
        values: dict = {}
        for name, (ptype, widget) in self._parameter_widgets.items():
            if ptype == "integer" and isinstance(widget, QSpinBox):
                values[name] = int(widget.value())
            elif ptype == "boolean" and isinstance(widget, QCheckBox):
                values[name] = bool(widget.isChecked())
            elif isinstance(widget, QLineEdit):
                raw = widget.text().strip()
                if ptype == "string_array":
                    values[name] = [s.strip() for s in raw.split(",") if s.strip()] if raw else []
                elif ptype == "number":
                    try:
                        values[name] = float(raw)
                    except ValueError:
                        values[name] = raw
                else:
                    values[name] = raw
        return values

    def run_selected_operation(self, *, async_mode: bool = False) -> Optional[ExecutionOutcome]:
        """Execute the currently selected operation through M365ExecutionService."""
        script_id = self.current_operation_id
        if not script_id:
            return None
        params = self.collect_parameters()
        ticket_id = self.ticket_editor.scratchpad_id if self._active_editor and self.ticket_editor.scratchpad_id > 0 else None
        self.lbl_exec_state.setText(f"State: RUNNING ({script_id})...")
        self.btn_run_operation.setEnabled(False)
        self.btn_cancel_operation.setEnabled(True)

        if async_mode:
            def _worker():
                outcome = self.execution_service.execute(script_id, params, ticket_id=ticket_id)
                self.operation_finished.emit(outcome)

            t = threading.Thread(target=_worker, daemon=True)
            t.start()
            return None

        outcome = self.execution_service.execute(script_id, params, ticket_id=ticket_id)
        self._on_operation_finished(outcome)
        return outcome

    def cancel_active_operation(self) -> bool:
        """Request cooperative cancellation of the active operation."""
        cancelled = self.execution_service.request_cancel()
        if cancelled:
            self.lbl_exec_state.setText("State: CANCELLING...")
        return cancelled

    def _on_operation_finished(self, outcome: ExecutionOutcome) -> None:
        self._current_outcome = outcome
        self.btn_run_operation.setEnabled(self.current_operation_id is not None)
        self.btn_cancel_operation.setEnabled(False)
        self.lbl_exec_state.setText(
            f"State: {outcome.status.upper()} ({outcome.operation_outcome}) — {outcome.script_id}"
        )
        self._refresh_history_list()
        self._display_outcome(outcome)
        self.company_panel.refresh_status()
        self._update_category_function_card()

    def _refresh_history_list(self) -> None:
        self.history_list.blockSignals(True)
        self.history_list.clear()
        for rec in self.execution_service.history:
            dur = f"{rec['duration_ms']}ms" if rec.get("duration_ms") is not None else "0ms"
            label_txt = f"[{rec['status'].upper()}] {rec['script_id']} ({dur}) · {rec['completed_at']}"
            item = QListWidgetItem(label_txt)
            item.setData(Qt.UserRole, rec["correlation_id"])
            self.history_list.addItem(item)
        if self.history_list.count() > 0:
            self.history_list.setCurrentRow(0)
        self.history_list.blockSignals(False)

    def _history_item_selected(self, item: Optional[QListWidgetItem], *_) -> None:
        if item is None:
            return
        cid = item.data(Qt.UserRole)
        outcome = self.execution_service.get_outcome(cid)
        if outcome is not None:
            self._current_outcome = outcome
            self._display_outcome(outcome)

    def _display_outcome(self, outcome: ExecutionOutcome) -> None:
        if self._showing_raw_json:
            self.results_output.setPlainText(outcome.sanitized_json)
        else:
            self.results_output.setPlainText(outcome.summary_text)
        if outcome.insertion_preview is not None:
            can_insert = (not outcome.insertion_preview.consumed) and (self.ticket_editor is not None and self.ticket_editor.isEnabled())
        else:
            can_insert = (self.ticket_editor is not None and self.ticket_editor.isEnabled()) and bool(self.results_output.toPlainText().strip())
        self.btn_insert_into_ticket.setEnabled(can_insert)
        if outcome.insertion_preview is not None and outcome.insertion_preview.consumed:
            self.lbl_results_notice.setText("Note insertion complete for this correlation ID.")
        elif outcome.status in ("success", "partial"):
            self.lbl_results_notice.setText("Ready to insert validated summary into Active Ticket Notes.")
        else:
            self.lbl_results_notice.setText(f"Run ended with status '{outcome.status}'; note insertion unavailable.")

    def _toggle_results_view(self, checked: bool) -> None:
        self._showing_raw_json = checked
        self.btn_toggle_json.setText("📋 Summary View" if checked else "{ } Raw JSON")
        if self._current_outcome is not None:
            self._display_outcome(self._current_outcome)

    def _clear_execution_history(self) -> None:
        self.execution_service.clear_history()
        self.history_list.clear()
        self._current_outcome = None
        self.results_output.clear()
        self.btn_insert_into_ticket.setEnabled(False)
        self.lbl_results_notice.setText("Session history cleared.")
        self.lbl_exec_state.setText("State: IDLE (Offline Synthetic)")

    def insert_current_result_into_ticket(self) -> bool:
        """Insert the current outcome or results preview into the active ticket editor inside a formatted monospace container."""
        if not hasattr(self, "ticket_editor") or self.ticket_editor is None or not self.ticket_editor.isEnabled():
            self.lbl_results_notice.setText("No active ticket editor is available for note insertion.")
            return False

        if self._current_outcome is not None and self._current_outcome.insertion_preview is not None:
            if self._current_outcome.insertion_preview.consumed:
                self.lbl_results_notice.setText("This result preview has already been inserted into the ticket.")
                self.btn_insert_into_ticket.setEnabled(False)
                return False
            token = self._current_outcome.insertion_preview.token
            try:
                self.execution_service.insert_into_active_ticket(token, self.ticket_editor)
                self._display_outcome(self._current_outcome)
                self.status_message_requested.emit("✓ Inserted M365 diagnostic summary into Active Ticket note!", 3500)
                return True
            except ValueError as exc:
                self.lbl_results_notice.setText(str(exc))
                self.btn_insert_into_ticket.setEnabled(False)
                return False

        # Fallback: format and insert current results output in styled monospace block
        output_text = self.results_output.toPlainText().strip()
        if not output_text:
            self.lbl_results_notice.setText("No output available to insert.")
            return False

        script_id = (self._current_outcome.script_id if self._current_outcome else None) or self.current_operation_id or "M365 PowerShell"
        timestamp = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
        import html
        escaped_text = html.escape(output_text)
        formatted_html = (
            f'<div style="background-color: #252526; border: 1px solid #3c3c3c; border-radius: 4px; padding: 8px; font-family: Consolas, monospace; color: #9cdcfe;">'
            f'<div style="color: #4fc1ff; font-weight: bold; margin-bottom: 4px;">=== M365 Output: {script_id} ({timestamp}) ===</div>'
            f'<pre style="margin: 0; white-space: pre-wrap; font-family: Consolas, monospace; color: #cccccc;"><code>{escaped_text}</code></pre>'
            f'</div><br>'
        )

        cursor = self.ticket_editor.textCursor()
        cursor.insertHtml(formatted_html)
        self.ticket_editor.setTextCursor(cursor)
        self.ticket_editor.ensureCursorVisible()

        self.status_message_requested.emit(f"✓ Inserted M365 output ({script_id}) into Active Ticket note!", 3500)
        self.lbl_results_notice.setText(f"✓ Inserted into Active Ticket at {timestamp}.")
        return True

    def _on_nav_toggled(self, visible: bool) -> None:
        """Slides the Categories pane open/closed (instant when animation is unavailable)."""
        self._nav_transition.set_open(visible)

    def _on_ticket_panel_toggled(self, visible: bool) -> None:
        """Slides the Active Ticket pane open/closed (instant when animation is unavailable)."""
        self._ticket_transition.set_open(visible)

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
            if self._current_outcome is not None:
                self._display_outcome(self._current_outcome)
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
        if self._current_outcome is not None:
            self._display_outcome(self._current_outcome)

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

    def _export_active_ticket_file(self) -> None:
        if self._active_editor:
            self.save_requested.emit(self.ticket_editor.scratchpad_id)
            clean_text = self.ticket_editor.toPlainText().replace('\uFFFC', '')
            clean_text = re.sub(r'\n{3,}', '\n\n', clean_text).strip()
            if self.scratchpad_service:
                try:
                    file_path, filename = self.scratchpad_service.export_ticket_to_file(
                        scratchpad_id=self.ticket_editor.scratchpad_id,
                        text_content=clean_text,
                    )
                    t_label = f"#{self._current_ticket_number}".strip() if self._current_ticket_number else ""
                    rel_path = f"{file_path.parent.name}/{filename}"
                    msg = f"✓ Exported note ({t_label}) to T-Notes/{rel_path}" if t_label else f"✓ Exported note to T-Notes/{rel_path}"
                    self.status_message_requested.emit(msg, 4000)
                except Exception as e:
                    self.status_message_requested.emit(f"Export Failed: {e}", 4000)

    def _arrange_content_columns(self, num_columns: int) -> None:
        """Arranges existing groupboxes into 1 or 2 columns without recreation."""
        for group in self._content_groups:
            self.content_layout.removeWidget(group)

        if not hasattr(self, "_left_col_container"):
            self._left_col_container = QWidget(self.content_widget)
            self._left_col_layout = QVBoxLayout(self._left_col_container)
            self._left_col_layout.setContentsMargins(0, 0, 0, 0)
            self._left_col_layout.setSpacing(8)

            self._right_col_container = QWidget(self.content_widget)
            self._right_col_layout = QVBoxLayout(self._right_col_container)
            self._right_col_layout.setContentsMargins(0, 0, 0, 0)
            self._right_col_layout.setSpacing(8)

        for group in self._content_groups:
            self._left_col_layout.removeWidget(group)
            self._right_col_layout.removeWidget(group)
        self.content_layout.removeWidget(self._left_col_container)
        self.content_layout.removeWidget(self._right_col_container)

        for col in range(2):
            self.content_layout.setColumnStretch(col, 0)
        for row in range(6):
            self.content_layout.setRowStretch(row, 0)

        self._current_columns = num_columns
        if num_columns == 1:
            self._left_col_container.hide()
            self._right_col_container.hide()
            for index, group in enumerate(self._content_groups):
                group.setParent(self.content_widget)
                group.show()
                self.content_layout.addWidget(group, index, 0)
            self.content_layout.setColumnStretch(0, 1)
            self.content_layout.setRowStretch(2, 4)  # Script Catalog (larger)
            self.content_layout.setRowStretch(3, 0)  # Parameters (compact, no vertical stretch)
            self.content_layout.setRowStretch(4, 2)  # Execution Workspace
            self.content_layout.setRowStretch(5, 3)  # Parsed Results
            self.content_widget.setMinimumSize(220, 6 * 75)
        else:
            self._left_col_container.show()
            self._right_col_container.show()
            # Left Column (60% width): Company Selection (compact) + Script Catalog (expands to fill height) + Execution Workspace
            self._left_col_layout.addWidget(self._content_groups[0], 0)
            self._left_col_layout.addWidget(self._content_groups[2], 4)
            self._left_col_layout.addWidget(self._content_groups[4], 2)
            # Right Column (40% width): Authentication & Tenant Context + Parameters (compact, zero dead space) + Parsed Results (expands)
            self._right_col_layout.addWidget(self._content_groups[1], 0)
            self._right_col_layout.addWidget(self._content_groups[3], 0)
            self._right_col_layout.addWidget(self._content_groups[5], 3)
            for group in self._content_groups:
                group.show()
            self.content_layout.addWidget(self._left_col_container, 0, 0)
            self.content_layout.addWidget(self._right_col_container, 0, 1)
            self.content_layout.setColumnStretch(0, 3)
            self.content_layout.setColumnStretch(1, 2)
            self.content_layout.setRowStretch(0, 1)
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
