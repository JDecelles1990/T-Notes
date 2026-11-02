"""Modal dialog for editing ticket metadata (ticket number, client, subject)."""

from typing import Optional
from PySide6.QtCore import Qt
from PySide6.QtWidgets import (
    QDialog,
    QDialogButtonBox,
    QFormLayout,
    QHBoxLayout,
    QLabel,
    QLineEdit,
    QPushButton,
    QVBoxLayout,
)


class EditTicketDialog(QDialog):
    """Dialog for modifying ticket metadata."""

    def __init__(
        self,
        ticket_number: str = "",
        client_name: str = "",
        title: str = "",
        parent: Optional[QDialog] = None,
    ):
        super().__init__(parent)
        self.setWindowTitle("Edit Ticket Metadata")
        self.setMinimumWidth(420)
        self.setModal(True)

        self._ticket_number = ticket_number
        self._client_name = client_name
        self._title = title

        self._setup_ui()
        self._update_preview()

    def _setup_ui(self) -> None:
        layout = QVBoxLayout(self)
        layout.setSpacing(14)
        layout.setContentsMargins(18, 18, 18, 18)

        # Form fields
        form = QFormLayout()
        form.setSpacing(10)

        self.txt_ticket = QLineEdit(self._ticket_number)
        self.txt_ticket.setPlaceholderText("e.g. INC-4092, #10293")
        self.txt_ticket.textChanged.connect(self._update_preview)

        self.txt_client = QLineEdit(self._client_name)
        self.txt_client.setPlaceholderText("e.g. Acme Corp, HR Dept")
        self.txt_client.textChanged.connect(self._update_preview)

        self.txt_title = QLineEdit(self._title)
        self.txt_title.setPlaceholderText("e.g. VPN Disconnect, DNS Resolution Issue")
        self.txt_title.textChanged.connect(self._update_preview)

        form.addRow("Ticket #:", self.txt_ticket)
        form.addRow("Client / Team:", self.txt_client)
        form.addRow("Subject / Summary:", self.txt_title)
        layout.addLayout(form)

        # Live tab title preview
        self.lbl_preview = QLabel()
        self.lbl_preview.setStyleSheet("color: #9cdcfe; font-style: italic; padding: 4px;")
        layout.addWidget(self.lbl_preview)

        # Action Buttons
        btn_layout = QHBoxLayout()
        btn_layout.addStretch()

        self.btn_cancel = QPushButton("Cancel")
        self.btn_cancel.setObjectName("btnCancel")
        self.btn_cancel.clicked.connect(self.reject)

        self.btn_save = QPushButton("Save Details")
        self.btn_save.setDefault(True)
        self.btn_save.clicked.connect(self.accept)

        btn_layout.addWidget(self.btn_cancel)
        btn_layout.addWidget(self.btn_save)
        layout.addLayout(btn_layout)

    def _update_preview(self) -> None:
        ticket = self.txt_ticket.text().strip() or "Untitled"
        client = self.txt_client.text().strip()
        title = self.txt_title.text().strip()

        secondary = client or title or "Scratchpad"
        self.lbl_preview.setText(f"Tab Preview:  #{ticket} — {secondary}")

    def get_data(self) -> dict:
        """Returns the edited ticket details."""
        return {
            "ticket_number": self.txt_ticket.text().strip(),
            "client_name": self.txt_client.text().strip(),
            "title": self.txt_title.text().strip(),
        }

