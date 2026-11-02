"""Collapsible history drawer backed by SQLite FTS5 for searching and restoring tickets."""

from typing import Any, Dict, List, Optional
from PySide6.QtCore import Qt, Signal
from PySide6.QtWidgets import (
    QDockWidget,
    QHBoxLayout,
    QLabel,
    QLineEdit,
    QListWidget,
    QListWidgetItem,
    QMessageBox,
    QPushButton,
    QVBoxLayout,
    QWidget,
)
from src.services.scratchpad_service import ScratchpadService


class HistoryDrawer(QDockWidget):
    """Side drawer for viewing, searching, and restoring archived tickets."""

    restore_requested = Signal(int)  # Emits scratchpad_id
    delete_requested = Signal(int)   # Emits scratchpad_id

    def __init__(self, scratchpad_service: ScratchpadService, parent: Optional[QWidget] = None):
        super().__init__("Ticket Archive & History", parent)
        self.scratchpad_service = scratchpad_service
        self.setAllowedAreas(Qt.LeftDockWidgetArea | Qt.RightDockWidgetArea)
        self.setFeatures(QDockWidget.DockWidgetClosable | QDockWidget.DockWidgetMovable)

        self._setup_ui()
        self.refresh_list()

    def _setup_ui(self) -> None:
        container = QWidget(self)
        layout = QVBoxLayout(container)
        layout.setContentsMargins(10, 10, 10, 10)
        layout.setSpacing(8)

        # FTS5 Search Box
        self.txt_search = QLineEdit()
        self.txt_search.setPlaceholderText("🔍 Search tickets, clients, notes...")
        self.txt_search.setClearButtonEnabled(True)
        self.txt_search.textChanged.connect(self._on_search_changed)
        layout.addWidget(self.txt_search)

        # List of tickets
        self.list_tickets = QListWidget()
        self.list_tickets.itemDoubleClicked.connect(self._on_item_double_clicked)
        self.list_tickets.itemSelectionChanged.connect(self._update_button_states)
        layout.addWidget(self.list_tickets)

        # Action Buttons
        btn_layout = QHBoxLayout()
        self.btn_restore = QPushButton("Restore Tab")
        self.btn_restore.setEnabled(False)
        self.btn_restore.setToolTip("Re-open ticket as an active tab")
        self.btn_restore.clicked.connect(self._on_restore_clicked)

        self.btn_delete = QPushButton("Delete")
        self.btn_delete.setObjectName("btnDanger")
        self.btn_delete.setEnabled(False)
        self.btn_delete.setToolTip("Permanently delete ticket and images")
        self.btn_delete.clicked.connect(self._on_delete_clicked)

        btn_layout.addWidget(self.btn_restore)
        btn_layout.addWidget(self.btn_delete)
        layout.addLayout(btn_layout)

        self.setWidget(container)

    def refresh_list(self) -> None:
        """Fetches archived tickets or runs the current search query."""
        query = self.txt_search.text().strip()
        if query:
            tickets = self.scratchpad_service.search_tickets(query, status="archived")
        else:
            tickets = self.scratchpad_service.get_archived_tickets()

        self.list_tickets.clear()
        for t in tickets:
            item = QListWidgetItem()
            t_num = t.get("ticket_number", "")
            client = t.get("client_name", "")
            title = t.get("title", "")
            date_str = str(t.get("updated_at", ""))[:10]

            header = f"#{t_num}"
            if client:
                header += f" — {client}"
            if title:
                header += f" ({title})"

            clean_preview = self.scratchpad_service.convert_html_to_clean_text(t.get("content_html", ""))
            first_line = clean_preview.split("\n")[0] if clean_preview else "Empty note"
            if len(first_line) > 40:
                first_line = first_line[:37] + "..."

            item.setText(f"{header}\n📅 {date_str} | {first_line}")
            item.setData(Qt.UserRole, t.get("id"))
            self.list_tickets.addItem(item)

        self._update_button_states()

    def _on_search_changed(self, text: str) -> None:
        self.refresh_list()

    def _update_button_states(self) -> None:
        has_selection = bool(self.list_tickets.selectedItems())
        self.btn_restore.setEnabled(has_selection)
        self.btn_delete.setEnabled(has_selection)

    def _get_selected_ticket_id(self) -> Optional[int]:
        selected = self.list_tickets.selectedItems()
        if selected:
            return selected[0].data(Qt.UserRole)
        return None

    def _on_item_double_clicked(self, item: QListWidgetItem) -> None:
        ticket_id = item.data(Qt.UserRole)
        if ticket_id is not None:
            self.restore_requested.emit(ticket_id)

    def _on_restore_clicked(self) -> None:
        ticket_id = self._get_selected_ticket_id()
        if ticket_id is not None:
            self.restore_requested.emit(ticket_id)

    def _on_delete_clicked(self) -> None:
        ticket_id = self._get_selected_ticket_id()
        if ticket_id is None:
            return

        res = QMessageBox.warning(
            self,
            "Confirm Permanent Deletion",
            "Are you sure you want to permanently delete this archived ticket and all its embedded images?\nThis action cannot be undone.",
            QMessageBox.Yes | QMessageBox.No,
            QMessageBox.No,
        )
        if res == QMessageBox.Yes:
            self.delete_requested.emit(ticket_id)

