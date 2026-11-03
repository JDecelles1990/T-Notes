"""Company and identity views. All metadata and context logic lives in services."""

from dataclasses import replace
import re
from uuid import uuid4

from PySide6.QtCore import Qt, QTimer
from PySide6.QtWidgets import (
    QComboBox, QDialog, QDialogButtonBox, QFormLayout, QGridLayout, QLabel,
    QLineEdit, QPlainTextEdit, QPushButton, QVBoxLayout, QWidget,
)

from src.services.m365_company_service import Administrator, Company, CLOUDS


def label(parent, value=""):
    widget = QLabel(value, parent)
    widget.setTextFormat(Qt.PlainText)
    widget.setWordWrap(True)
    return widget


def entry(parent, name, hint, limit=254):
    widget = QLineEdit(parent)
    widget.setAccessibleName(name)
    widget.setPlaceholderText(hint)
    widget.setMaxLength(limit)
    widget.setClearButtonEnabled(True)
    return widget


class MultilineEntry(QPlainTextEdit):
    """Multiline plain text entry for lossless metadata lists."""

    def __init__(self, parent=None, accessible_name="", hint=""):
        super().__init__(parent)
        if accessible_name:
            self.setAccessibleName(accessible_name)
        if hint:
            self.setPlaceholderText(hint)
        self.setMaximumHeight(90)

    def text(self):
        return self.toPlainText()

    def setText(self, value):
        self.setPlainText(value)


class ProfileDialog(QDialog):
    """Edit RAM-only metadata; validation failures keep the form open."""

    def __init__(self, directory, company=None, parent=None):
        super().__init__(parent)
        self.setWindowTitle("Edit Company — session only" if company else "Add Company — session only")
        self.directory, self.original, self.result_company = directory, company, None
        layout = QFormLayout(self)
        self.fields = {}
        for key, caption, limit in (("display_name", "Company name", 128), ("tenant_id", "Tenant UUID", 36),
                                    ("primary_domain", "Primary domain", 253)):
            edit = entry(self, caption, caption, limit)
            value = getattr(company, key) if company else ""
            edit.setText(value)
            self.fields[key] = edit
            layout.addRow(caption, edit)
        domains_caption = "Additional domains (one per line or comma-separated)"
        domains_edit = MultilineEntry(self, domains_caption, "One domain per line or comma-separated")
        domains_value = getattr(company, "additional_verified_domains") if company else ()
        domains_edit.setText("\n".join(domains_value) if isinstance(domains_value, (list, tuple)) else str(domains_value or ""))
        self.fields["additional_verified_domains"] = domains_edit
        layout.addRow(domains_caption, domains_edit)
        notes_edit = entry(self, "Non-secret notes only", "Non-secret notes only", 1024)
        notes_value = getattr(company, "notes") if company else ""
        notes_edit.setText(notes_value)
        self.fields["notes"] = notes_edit
        layout.addRow("Non-secret notes only", notes_edit)
        self.cloud = QComboBox(self)
        self.cloud.setAccessibleName("Preferred cloud environment")
        self.cloud.addItems(CLOUDS)
        if company:
            self.cloud.setCurrentText(company.preferred_cloud)
        layout.addRow("Preferred cloud", self.cloud)
        layout.addRow(label(self, "Domain metadata is an unverified local hint. Never enter passwords, tokens or credentials."))
        self.error = label(self)
        layout.addRow(self.error)
        buttons = QDialogButtonBox(QDialogButtonBox.Save | QDialogButtonBox.Cancel, self)
        buttons.accepted.connect(self._save)
        buttons.rejected.connect(self.reject)
        layout.addRow(buttons)

    def _save(self):
        try:
            values = {key: edit.text() for key, edit in self.fields.items()}
            values["additional_verified_domains"] = tuple(
                s.strip() for s in re.split(r"[\r\n,]+", values["additional_verified_domains"]) if s.strip()
            )
            values["preferred_cloud"] = self.cloud.currentText()
            company = replace(self.original, **values) if self.original else Company(str(uuid4()), **values)
            self.result_company = self.directory.save(company)
            self.accept()
        except ValueError as exc:
            self.error.setText(str(exc))


class AdministratorDialog(QDialog):
    def __init__(self, directory, company_id, administrator=None, parent=None):
        super().__init__(parent)
        self.setWindowTitle("Administrator metadata — session only")
        self.directory, self.company_id, self.original = directory, company_id, administrator
        self.result_administrator = None
        layout = QFormLayout(self)
        self.upn = entry(self, "Administrator email / UPN", "admin@example.invalid")
        self.display_label = entry(self, "Administrator label", "Optional label; grants no permissions", 128)
        if administrator:
            self.upn.setText(administrator.upn)
            self.display_label.setText(administrator.display_label)
        layout.addRow("Administrator UPN", self.upn)
        layout.addRow("Display label", self.display_label)
        self.error = label(self)
        layout.addRow(self.error)
        buttons = QDialogButtonBox(QDialogButtonBox.Save | QDialogButtonBox.Cancel, self)
        buttons.accepted.connect(self._save)
        buttons.rejected.connect(self.reject)
        layout.addRow(buttons)

    def _save(self):
        try:
            admin = Administrator(self.original.administrator_id if self.original else str(uuid4()), self.upn.text(), self.display_label.text())
            self.directory.save_administrator(self.company_id, admin)
            self.result_administrator = admin
            self.accept()
        except ValueError as exc:
            self.error.setText(str(exc))


class CompanyContextPanel(QWidget):
    """Two group contents sharing one service, without owning Notes or a worker."""

    def __init__(self, context, company_group, identity_group):
        super().__init__(company_group)
        self.context = context
        self.directory = context.directory
        layout = QVBoxLayout(self)
        layout.setContentsMargins(0, 0, 0, 0)
        layout.addWidget(label(self, "Synthetic preview • changes last for this session only."))
        self.company_search = entry(self, "Search companies by name or domain", "Search company name or domain")
        self.company_combo = QComboBox(self)
        self.company_combo.setAccessibleName("Company selector")
        self.company_combo.setMinimumContentsLength(8)
        self.company_combo.setSizeAdjustPolicy(QComboBox.AdjustToMinimumContentsLengthWithIcon)
        layout.addWidget(self.company_search)
        layout.addWidget(self.company_combo)
        buttons = QGridLayout()
        self.add_company = QPushButton("+ Company", self)
        self.edit_company = QPushButton("Edit Company", self)
        buttons.addWidget(self.add_company, 0, 0)
        buttons.addWidget(self.edit_company, 0, 1)
        layout.addLayout(buttons)
        self.selected_tenant = label(self)
        self.selected_tenant.setMinimumHeight(self.selected_tenant.fontMetrics().lineSpacing() * 6)
        layout.addWidget(self.selected_tenant)
        self.confirm_button = QPushButton("Confirm Company Selection", self)
        layout.addWidget(self.confirm_button)
        self.confirmation = label(self)
        layout.addWidget(self.confirmation)
        self.error = label(self)
        layout.addWidget(self.error)
        company_group.layout().addWidget(self)

        identity = QWidget(identity_group)
        auth = QVBoxLayout(identity)
        auth.setContentsMargins(0, 0, 0, 0)
        self.administrator_search = entry(identity, "Search administrator accounts", "Search administrator UPN or label")
        self.administrator_combo = QComboBox(identity)
        self.administrator_combo.setAccessibleName("Administrator selector")
        self.administrator_combo.setMinimumContentsLength(8)
        self.administrator_combo.setSizeAdjustPolicy(QComboBox.AdjustToMinimumContentsLengthWithIcon)
        auth.addWidget(self.administrator_search)
        auth.addWidget(self.administrator_combo)
        admin_buttons = QGridLayout()
        self.admin_add, self.admin_edit = QPushButton("+ Admin", identity), QPushButton("Edit", identity)
        self.admin_remove, self.admin_default = QPushButton("Remove", identity), QPushButton("Set Default", identity)
        for i, button in enumerate((self.admin_add, self.admin_edit, self.admin_remove, self.admin_default)):
            admin_buttons.addWidget(button, i // 2, i % 2)
        auth.addLayout(admin_buttons)
        self.admin_upn = entry(identity, "Administrator sign-in hint", "Administrator email / UPN — not authenticated")
        auth.addWidget(self.admin_upn)
        self.graph_button = QPushButton("Connect Microsoft Graph (synthetic)", identity)
        self.exchange_button = QPushButton("Connect Exchange Online (synthetic)", identity)
        self.disconnect_button = QPushButton("Disconnect", identity)
        for button in (self.graph_button, self.exchange_button, self.disconnect_button):
            auth.addWidget(button)
        self.connection_status = label(identity)
        self.connection_status.setMinimumHeight(self.connection_status.fontMetrics().lineSpacing() * 6)
        auth.addWidget(self.connection_status)
        self.verified_identity = label(identity, "Verified tenant: none. Authenticated administrator: none.")
        self.verified_identity.setMinimumHeight(self.verified_identity.fontMetrics().lineSpacing() * 2)
        auth.addWidget(self.verified_identity)
        self.target_upn = entry(identity, "Client email / UPN", "Target client email / UPN")
        self.target_object_id = entry(identity, "Client Entra object ID", "Optional target Entra object UUID", 36)
        auth.addWidget(self.target_upn)
        auth.addWidget(self.target_object_id)
        self.resolve_button = QPushButton("Resolve Target (synthetic)", identity)
        auth.addWidget(self.resolve_button)
        self.target_status = label(identity)
        self.target_status.setMinimumHeight(self.target_status.fontMetrics().lineSpacing() * 9)
        auth.addWidget(self.target_status)
        self.eligibility_status = label(identity)
        auth.addWidget(self.eligibility_status)
        identity_group.layout().addWidget(identity)

        self.company_search.textChanged.connect(self.refresh_companies)
        self.company_combo.currentIndexChanged.connect(self._company_changed)
        self.administrator_search.textChanged.connect(self.refresh_administrators)
        self.administrator_combo.currentIndexChanged.connect(self._administrator_changed)
        self.add_company.clicked.connect(lambda: self._company_dialog(False))
        self.edit_company.clicked.connect(lambda: self._company_dialog(True))
        self.admin_add.clicked.connect(lambda: self._admin_dialog(False))
        self.admin_edit.clicked.connect(lambda: self._admin_dialog(True))
        self.admin_remove.clicked.connect(self._remove_admin)
        self.admin_default.clicked.connect(self._default_admin)
        self.admin_upn.textChanged.connect(self._admin_hint_changed)
        self.confirm_button.clicked.connect(lambda: self._run(self.context.confirm_company))
        self.graph_button.clicked.connect(lambda: self._run(lambda: self.context.connect_synthetic("Graph")))
        self.exchange_button.clicked.connect(lambda: self._run(lambda: self.context.connect_synthetic("ExchangeOnline")))
        self.disconnect_button.clicked.connect(self._disconnect)
        self.target_upn.textChanged.connect(self._target_changed)
        self.target_object_id.textChanged.connect(self._target_changed)
        self.resolve_button.clicked.connect(lambda: self._run(self.context.resolve_synthetic))
        self.refresh_companies()
        self.timer = QTimer(self)
        self.timer.setInterval(1000)
        self.timer.timeout.connect(self.refresh_status)

    def showEvent(self, event):
        super().showEvent(event)
        self.refresh_status()
        self.timer.start()

    def hideEvent(self, event):
        self.timer.stop()
        super().hideEvent(event)

    def _run(self, action):
        try:
            action()
            self.error.clear()
        except ValueError as exc:
            self.error.setText(str(exc))
        self.refresh_status()

    def refresh_companies(self, *_):
        self.context.synchronize()
        companies = self.directory.search(self.company_search.text())
        if self.context.company_id and self.context.company_id not in {c.company_id for c in companies}:
            self.context.select_company(None)
        self.company_combo.blockSignals(True)
        self.company_combo.clear()
        self.company_combo.addItem("Select company…" if companies else "No matching companies — add a company", None)
        for company in companies:
            self.company_combo.addItem(f"{company.display_name} · {company.primary_domain}", company.company_id)
        self.company_combo.setCurrentIndex(max(0, self.company_combo.findData(self.context.company_id)))
        self.company_combo.blockSignals(False)
        self.refresh_administrators()
        self._sync_inputs()
        self.refresh_status()

    def _company_changed(self, *_):
        self.context.select_company(self.company_combo.currentData())
        self.administrator_search.blockSignals(True)
        self.administrator_search.clear()
        self.administrator_search.blockSignals(False)
        self.refresh_administrators()
        self._sync_inputs()
        self.refresh_status()

    def refresh_administrators(self, *_):
        company = self.context.company
        admins = self.directory.administrators(company.company_id, self.administrator_search.text()) if company else ()
        if self.context.administrator_id and self.context.administrator_id not in {a.administrator_id for a in admins}:
            self.context.select_administrator(None)
        self.administrator_combo.blockSignals(True)
        self.administrator_combo.clear()
        self.administrator_combo.addItem("Select administrator…" if admins else "No accounts — add administrator", None)
        for admin in admins:
            suffix = " (default)" if company.preferred_administrator_id == admin.administrator_id else ""
            self.administrator_combo.addItem(f"{admin.upn} · {admin.display_label}{suffix}", admin.administrator_id)
        self.administrator_combo.setCurrentIndex(max(0, self.administrator_combo.findData(self.context.administrator_id)))
        self.administrator_combo.blockSignals(False)
        self._sync_inputs()
        self.refresh_status()

    def _administrator_changed(self, *_):
        self.context.select_administrator(self.administrator_combo.currentData())
        self._sync_inputs()
        self.refresh_status()

    def _sync_inputs(self):
        for edit, value in ((self.admin_upn, self.context.administrator_upn),
                            (self.target_upn, self.context.target_input.upn), (self.target_object_id, self.context.target_input.object_id)):
            edit.blockSignals(True)
            edit.setText(value)
            edit.blockSignals(False)

    def _admin_hint_changed(self, value):
        try:
            self.context.set_administrator_upn(value)
            self.error.clear()
        except ValueError as exc:
            self.context.set_administrator_upn("")
            self.error.setText(str(exc))
        self.administrator_combo.blockSignals(True)
        self.administrator_combo.setCurrentIndex(max(0, self.administrator_combo.findData(self.context.administrator_id)))
        self.administrator_combo.blockSignals(False)
        self.target_upn.blockSignals(True)
        self.target_object_id.blockSignals(True)
        self.target_upn.setText(self.context.target_input.upn)
        self.target_object_id.setText(self.context.target_input.object_id)
        self.target_upn.blockSignals(False)
        self.target_object_id.blockSignals(False)
        self.refresh_status()

    def _target_changed(self, *_):
        self._run(lambda: self.context.set_target(self.target_upn.text(), self.target_object_id.text()))

    def _company_dialog(self, editing):
        dialog = ProfileDialog(self.directory, self.context.company if editing else None, self)
        if dialog.exec() == QDialog.Accepted:
            self.context.select_company(dialog.result_company.company_id)
            self.company_search.clear()
            self.refresh_companies()

    def _selected_admin(self):
        company = self.context.company
        return next((a for a in company.administrators if a.administrator_id == self.context.administrator_id), None) if company else None

    def _admin_dialog(self, editing):
        if self.context.company is None:
            return
        dialog = AdministratorDialog(self.directory, self.context.company_id, self._selected_admin() if editing else None, self)
        if dialog.exec() == QDialog.Accepted:
            self.context.synchronize()
            self.context.select_administrator(dialog.result_administrator.administrator_id)
            self.administrator_search.clear()
            self.refresh_administrators()

    def _remove_admin(self):
        if self.context.administrator_id:
            self.directory.remove_administrator(self.context.company_id, self.context.administrator_id)
            self.context.synchronize()
            self.refresh_administrators()

    def _default_admin(self):
        if self.context.administrator_id:
            self.directory.set_default(self.context.company_id, self.context.administrator_id)
            self.context.synchronize()
            self.refresh_administrators()

    def _disconnect(self):
        self.context.disconnect()
        self._sync_inputs()
        self.refresh_status()

    def refresh_status(self):
        company = self.context.company
        self.selected_tenant.setText(f"Selected: {company.display_name}\nTenant (unverified):\n{company.tenant_id}\nCloud preference: {company.preferred_cloud}" if company else "No company selected. Tenant: none.")
        self.confirmation.setText("Company selection confirmed locally — authentication still required." if self.context.confirmed_company else "Company selection not confirmed.")
        for button in (self.edit_company, self.confirm_button, self.admin_add):
            button.setEnabled(company is not None)
        for button in (self.admin_edit, self.admin_remove, self.admin_default):
            button.setEnabled(self._selected_admin() is not None)
        for button in (self.graph_button, self.exchange_button):
            button.setEnabled(company is not None and bool(self.context.administrator_upn))
        self.resolve_button.setEnabled(company is not None and bool(self.context.target_input.upn or self.context.target_input.object_id))
        self.connection_status.setText("\n".join(f"{s}: {self.context.connections.state(s).state} (synthetic)\n{self.context.connections.state(s).warning}" for s in ("Graph", "ExchangeOnline")))
        target = self.context.target
        value = self.context.target_status + "\nVerified target: none."
        if target:
            value += f"\nSynthetic fixture: {target.upn}\nObject ID: {target.object_id}\nTenant: {target.tenant_id}"
        if company and self.context.target_input.upn:
            target_domain = self.context.target_input.upn.rsplit("@", 1)[1].lower()
            if target_domain not in (company.primary_domain, *company.additional_verified_domains):
                value += "\nCompany/domain mismatch warning — check tenant and target. Domains cannot establish tenant identity."
        self.target_status.setText(value)
        self.context.eligibility()  # Recheck expiration and context on each refresh.
        self.eligibility_status.setText("Available operations: none in this synthetic preview.\nLive authentication and execution require separate approval.")
