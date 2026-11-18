"""Smart Entity Extractor & Tech Quick-Tools modal dialog."""

from __future__ import annotations

from typing import Callable, Optional

from PySide6.QtCore import Qt
from PySide6.QtGui import QKeySequence, QShortcut
from PySide6.QtWidgets import (
    QApplication,
    QDialog,
    QGroupBox,
    QHBoxLayout,
    QLabel,
    QLineEdit,
    QListWidget,
    QListWidgetItem,
    QPushButton,
    QSpinBox,
    QVBoxLayout,
    QWidget,
)

from src.services.tech_tools_service import TechToolsService
from src.ui.components.glow_effect import (
    apply_glow_to_buttons,
    apply_glow_to_inputs,
    pulse_widget_glow,
)
from src.ui.components.panel_transition import animate_dialog_show


class QuickToolsDialog(QDialog):
    """Technician utility modal for extracting note entities and generating secrets/IDs."""

    _CATEGORY_LABELS = (
        ("emails", "👤 Emails / UPNs"),
        ("guids", "🆔 GUIDs / Object IDs"),
        ("ips", "🌐 IPv4 Addresses"),
        ("tickets", "🎫 Ticket IDs"),
        ("urls", "🔗 URLs"),
    )

    def __init__(
        self,
        note_text: str = "",
        on_insert_text: Optional[Callable[[str], None]] = None,
        on_send_to_m365: Optional[Callable[[str, str], None]] = None,
        parent: Optional[QWidget] = None,
    ) -> None:
        super().__init__(parent)
        self.setWindowTitle("⚡ Tech Quick-Tools & Smart Entity Extractor")
        self.setMinimumSize(640, 520)
        self.setModal(True)

        self._note_text = note_text or ""
        self._on_insert_text = on_insert_text
        self._on_send_to_m365 = on_send_to_m365
        self._entities = TechToolsService.extract_entities(self._note_text)
        self._shown_once = False

        self._setup_ui()
        self._populate_entities()
        self._refresh_timestamp()
        self._generate_password()
        self._generate_uuid()

    def _setup_ui(self) -> None:
        layout = QVBoxLayout(self)
        layout.setContentsMargins(16, 16, 16, 16)
        layout.setSpacing(12)

        # Header
        header = QLabel("⚡ Smart Note Extractor & IT Quick Generators")
        header.setStyleSheet("font-size: 13pt; font-weight: bold; color: #7dd3fc;")
        layout.addWidget(header)

        # 1. Extracted Entities Section
        extract_group = QGroupBox("Detected Note Entities (UPNs, GUIDs, IPs, Tickets, URLs)")
        extract_layout = QVBoxLayout(extract_group)
        extract_layout.setSpacing(8)

        filter_row = QHBoxLayout()
        self.txt_filter = QLineEdit()
        self.txt_filter.setPlaceholderText("Filter extracted emails, GUIDs, IPs, URLs, or ticket IDs...")
        self.txt_filter.textChanged.connect(self._populate_entities)
        filter_row.addWidget(self.txt_filter, 1)

        self.lbl_entity_count = QLabel("")
        self.lbl_entity_count.setStyleSheet("color: #34d399; font-weight: bold;")
        filter_row.addWidget(self.lbl_entity_count)
        extract_layout.addLayout(filter_row)

        self.entity_list = QListWidget()
        self.entity_list.setMinimumHeight(150)
        self.entity_list.itemDoubleClicked.connect(lambda _: self._copy_selected_entity())
        self.entity_list.currentItemChanged.connect(lambda *_: self._sync_entity_buttons())
        extract_layout.addWidget(self.entity_list)

        entity_btn_row = QHBoxLayout()
        self.btn_copy_entity = QPushButton("📋 Copy Selected")
        self.btn_copy_entity.clicked.connect(self._copy_selected_entity)
        entity_btn_row.addWidget(self.btn_copy_entity)

        self.btn_insert_entity = QPushButton("📥 Insert into Note")
        self.btn_insert_entity.clicked.connect(self._insert_selected_entity)
        entity_btn_row.addWidget(self.btn_insert_entity)

        self.btn_send_m365 = QPushButton("☁️ Send UPN/GUID to M365 Target")
        self.btn_send_m365.setObjectName("btnPrimary")
        self.btn_send_m365.clicked.connect(self._send_to_m365_clicked)
        entity_btn_row.addWidget(self.btn_send_m365)

        entity_btn_row.addStretch()
        extract_layout.addLayout(entity_btn_row)
        layout.addWidget(extract_group, 1)

        # 2. Tech Generators Section
        gen_group = QGroupBox("Instant IT Generators")
        gen_layout = QVBoxLayout(gen_group)
        gen_layout.setSpacing(8)

        # Password Row
        pw_row = QHBoxLayout()
        pw_lbl = QLabel("Temp Password:")
        pw_lbl.setFixedWidth(105)
        self.spin_pw_len = QSpinBox()
        self.spin_pw_len.setRange(8, 64)
        self.spin_pw_len.setValue(16)
        self.spin_pw_len.setFixedWidth(60)
        self.spin_pw_len.setToolTip("Temporary password character length (8-64)")

        self.txt_password = QLineEdit()
        self.txt_password.setReadOnly(True)
        self.txt_password.setStyleSheet("font-family: Consolas, monospace; color: #4ade80;")

        self.btn_gen_pw = QPushButton("🔐 New")
        self.btn_gen_pw.clicked.connect(self._generate_password)
        self.btn_copy_pw = QPushButton("📋")
        self.btn_copy_pw.setToolTip("Copy Temporary Password")
        self.btn_copy_pw.clicked.connect(lambda: self._copy_text(self.txt_password.text(), "Temp Password"))
        self.btn_insert_pw = QPushButton("📥")
        self.btn_insert_pw.setToolTip("Insert Temporary Password into Note")
        self.btn_insert_pw.clicked.connect(lambda: self._insert_text(self.txt_password.text()))

        for w in (pw_lbl, self.spin_pw_len, self.txt_password, self.btn_gen_pw, self.btn_copy_pw, self.btn_insert_pw):
            pw_row.addWidget(w)
        gen_layout.addLayout(pw_row)

        # UUID Row
        uuid_row = QHBoxLayout()
        uuid_lbl = QLabel("UUID v4:")
        uuid_lbl.setFixedWidth(105)
        self.txt_uuid = QLineEdit()
        self.txt_uuid.setReadOnly(True)
        self.txt_uuid.setStyleSheet("font-family: Consolas, monospace; color: #7dd3fc;")

        self.btn_gen_uuid = QPushButton("🆔 New")
        self.btn_gen_uuid.clicked.connect(self._generate_uuid)
        self.btn_copy_uuid = QPushButton("📋")
        self.btn_copy_uuid.setToolTip("Copy UUID v4")
        self.btn_copy_uuid.clicked.connect(lambda: self._copy_text(self.txt_uuid.text(), "UUID v4"))
        self.btn_insert_uuid = QPushButton("📥")
        self.btn_insert_uuid.setToolTip("Insert UUID v4 into Note")
        self.btn_insert_uuid.clicked.connect(lambda: self._insert_text(self.txt_uuid.text()))

        for w in (uuid_lbl, self.txt_uuid, self.btn_gen_uuid, self.btn_copy_uuid, self.btn_insert_uuid):
            uuid_row.addWidget(w)
        gen_layout.addLayout(uuid_row)

        # Timestamp Row
        ts_row = QHBoxLayout()
        ts_lbl = QLabel("Local + UTC:")
        ts_lbl.setFixedWidth(105)
        self.txt_timestamp = QLineEdit()
        self.txt_timestamp.setReadOnly(True)
        self.txt_timestamp.setStyleSheet("font-family: Consolas, monospace; color: #c4b5fd;")

        self.btn_gen_ts = QPushButton("🕒 Now")
        self.btn_gen_ts.clicked.connect(self._refresh_timestamp)
        self.btn_copy_ts = QPushButton("📋")
        self.btn_copy_ts.setToolTip("Copy Local + UTC Timestamp")
        self.btn_copy_ts.clicked.connect(lambda: self._copy_text(self.txt_timestamp.text(), "Local/UTC Timestamp"))
        self.btn_insert_ts = QPushButton("📥")
        self.btn_insert_ts.setToolTip("Insert Local + UTC Timestamp into Note")
        self.btn_insert_ts.clicked.connect(lambda: self._insert_text(self.txt_timestamp.text()))

        for w in (ts_lbl, self.txt_timestamp, self.btn_gen_ts, self.btn_copy_ts, self.btn_insert_ts):
            ts_row.addWidget(w)
        gen_layout.addLayout(ts_row)

        layout.addWidget(gen_group)

        # Status & Close row
        bottom = QHBoxLayout()
        self.lbl_feedback = QLabel("Ready — double-click any extracted entity to copy.")
        self.lbl_feedback.setStyleSheet("color: #94a3b8; padding: 2px 6px;")
        bottom.addWidget(self.lbl_feedback, 1)

        self.btn_close = QPushButton("Close")
        self.btn_close.setObjectName("btnCancel")
        self.btn_close.clicked.connect(self.accept)
        bottom.addWidget(self.btn_close)
        layout.addLayout(bottom)

        QShortcut(QKeySequence("Escape"), self, self.reject)
        apply_glow_to_buttons([self])
        apply_glow_to_inputs([self])

    def showEvent(self, event) -> None:
        super().showEvent(event)
        if not self._shown_once:
            self._shown_once = True
            animate_dialog_show(self)

    def _populate_entities(self) -> None:
        query = self.txt_filter.text().strip().lower()
        self.entity_list.clear()
        total = 0
        for key, label in self._CATEGORY_LABELS:
            values = self._entities.get(key, [])
            for val in values:
                if query and query not in val.lower() and query not in label.lower():
                    continue
                item = QListWidgetItem(f"{label}:  {val}")
                item.setData(Qt.UserRole, (key, val))
                self.entity_list.addItem(item)
                total += 1
        self.lbl_entity_count.setText(f"{total} found")
        if total > 0:
            self.entity_list.setCurrentRow(0)
        else:
            empty = QListWidgetItem("No matching technical entities detected in the current note.")
            empty.setFlags(Qt.NoItemFlags)
            self.entity_list.addItem(empty)
        self._sync_entity_buttons()

    def _selected_entity(self) -> tuple[str, str]:
        item = self.entity_list.currentItem()
        if not item:
            return "", ""
        data = item.data(Qt.UserRole)
        if isinstance(data, tuple) and len(data) == 2:
            return str(data[0]), str(data[1])
        return "", ""

    def _sync_entity_buttons(self) -> None:
        key, val = self._selected_entity()
        has_sel = bool(val)
        self.btn_copy_entity.setEnabled(has_sel)
        self.btn_insert_entity.setEnabled(has_sel and self._on_insert_text is not None)

        has_upn = bool(self._entities.get("emails"))
        has_guid = bool(self._entities.get("guids"))
        can_send = self._on_send_to_m365 is not None and (
            key in ("emails", "guids") or has_upn or has_guid
        )
        self.btn_send_m365.setEnabled(can_send)

    def _set_feedback(self, msg: str, color: str = "#34d399") -> None:
        self.lbl_feedback.setText(msg)
        self.lbl_feedback.setStyleSheet(f"color: {color}; font-weight: bold; padding: 2px 6px;")
        pulse_widget_glow(self.lbl_feedback, color, 650)

    def _copy_text(self, text: str, label: str = "Value") -> None:
        if not text:
            return
        QApplication.clipboard().setText(text)
        self._set_feedback(f"✓ Copied {label} to clipboard!")

    def _insert_text(self, text: str) -> None:
        if not text or not self._on_insert_text:
            return
        self._on_insert_text(text)
        self._set_feedback("📥 Inserted into active note editor!", "#38bdf8")

    def _copy_selected_entity(self) -> None:
        _, val = self._selected_entity()
        if val:
            self._copy_text(val, val)

    def _insert_selected_entity(self) -> None:
        _, val = self._selected_entity()
        if val:
            self._insert_text(val)

    def _send_to_m365_clicked(self) -> None:
        if not self._on_send_to_m365:
            return
        key, val = self._selected_entity()
        upn = val if key == "emails" else (self._entities["emails"][0] if self._entities.get("emails") else "")
        guid = val if key == "guids" else (self._entities["guids"][0] if self._entities.get("guids") else "")
        if not upn and not guid:
            return
        self._on_send_to_m365(upn, guid)
        self.accept()

    def _generate_password(self) -> None:
        self.txt_password.setText(TechToolsService.generate_temp_password(self.spin_pw_len.value()))

    def _generate_uuid(self) -> None:
        self.txt_uuid.setText(TechToolsService.generate_uuid())

    def _refresh_timestamp(self) -> None:
        self.txt_timestamp.setText(TechToolsService.format_iso_timestamp()["combined"])
