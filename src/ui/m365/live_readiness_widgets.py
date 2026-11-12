"""Live Pilot readiness, device-code sign-in, and SQLite directory export/merge dialogs."""

from __future__ import annotations

from pathlib import Path
import threading
from typing import Optional

from PySide6.QtCore import Qt, QThread, QUrl, Signal
from PySide6.QtGui import QDesktopServices
from PySide6.QtWidgets import (
    QApplication,
    QDialog,
    QDialogButtonBox,
    QFileDialog,
    QHBoxLayout,
    QLabel,
    QMessageBox,
    QPlainTextEdit,
    QPushButton,
    QVBoxLayout,
)

from src.services.m365_preflight_service import M365PreflightService, PreflightReport


class M365AuthWorker(QThread):
    """Runs interactive live M365 authentication off the Qt UI event loop."""

    event_received = Signal(dict)
    completed = Signal(object, str)  # (LiveConnectionState | None, error_text)

    def __init__(
        self,
        context_service,
        service: str,
        *,
        auth_mode: str,
        cancel_event: threading.Event,
        parent=None,
    ) -> None:
        super().__init__(parent)
        self._context_service = context_service
        self._service = service
        self._auth_mode = auth_mode
        self._cancel_event = cancel_event

    def run(self) -> None:
        try:
            state = self._context_service.connect_live(
                self._service,
                auth_mode=self._auth_mode,
                cancel_event=self._cancel_event,
                on_event=self._emit_worker_event,
            )
            self.completed.emit(state, "")
        except Exception as exc:
            self.completed.emit(None, str(exc))

    def _emit_worker_event(self, frame: dict) -> None:
        self.event_received.emit(dict(frame))


class M365LiveResolveWorker(QThread):
    """Runs `M365.ENTRA.USER_IDENTITY` off the Qt UI thread to bind a real Entra target."""

    completed = Signal(object, str)  # (ExecutionOutcome | None, error_text)

    def __init__(self, execution_service, *, ticket_id=None, parent=None) -> None:
        super().__init__(parent)
        self._execution_service = execution_service
        self._ticket_id = ticket_id

    def run(self) -> None:
        try:
            outcome = self._execution_service.resolve_live_target(ticket_id=self._ticket_id)
            self.completed.emit(outcome, "")
        except Exception as exc:
            self.completed.emit(None, str(exc))


class M365DeviceCodeDialog(QDialog):
    """Modal progress/code dialog for Microsoft 365 Device Code authentication."""

    def __init__(
        self,
        service: str,
        tenant_id: str,
        admin_upn: str,
        cancel_event: threading.Event,
        parent=None,
    ) -> None:
        super().__init__(parent)
        self._cancel_event = cancel_event
        self._verification_url = "https://microsoft.com/devicelogin"
        self._user_code = ""
        self.setWindowTitle(f"Microsoft 365 Device Code Sign-In — {service}")
        self.setMinimumWidth(460)

        layout = QVBoxLayout(self)
        header = QLabel(
            f"Sign in to {service} for tenant {tenant_id}\n"
            f"Expected admin account: {admin_upn}\n\n"
            "Use this flow to paste the device code into an isolated InPrivate browser profile.",
            self,
        )
        header.setWordWrap(True)
        layout.addWidget(header)

        self.lbl_code = QLabel("Code: Waiting for Microsoft sign-in prompt...", self)
        self.lbl_code.setTextInteractionFlags(Qt.TextSelectableByMouse)
        self.lbl_code.setStyleSheet(
            "font-family: Consolas, 'Courier New', monospace; font-size: 16px; font-weight: bold; "
            "padding: 8px; background-color: #161b22; border: 1px solid #30363d; border-radius: 4px; "
            "color: #58a6ff;"
        )
        layout.addWidget(self.lbl_code)

        self.lbl_url = QLabel(f"Verification URL: {self._verification_url}", self)
        self.lbl_url.setTextInteractionFlags(Qt.TextSelectableByMouse)
        layout.addWidget(self.lbl_url)

        actions_row = QHBoxLayout()
        self.btn_copy_code = QPushButton("Copy Device Code", self)
        self.btn_copy_code.setEnabled(False)
        self.btn_copy_code.clicked.connect(self._copy_code)
        actions_row.addWidget(self.btn_copy_code)

        self.btn_open_url = QPushButton("Open Verification Page", self)
        self.btn_open_url.clicked.connect(self._open_url)
        actions_row.addWidget(self.btn_open_url)
        layout.addLayout(actions_row)

        self.lbl_status = QLabel("Starting PowerShell 7 worker...", self)
        self.lbl_status.setWordWrap(True)
        layout.addWidget(self.lbl_status)

        self.btn_cancel = QPushButton("Cancel Sign-In", self)
        self.btn_cancel.clicked.connect(self._request_cancel)
        layout.addWidget(self.btn_cancel)

    def handle_worker_event(self, frame: dict) -> None:
        event_kind = frame.get("event")
        if event_kind == "device_code":
            code = str(frame.get("user_code") or "").strip()
            url = str(frame.get("verification_uri") or "https://microsoft.com/devicelogin").strip()
            self._verification_url = url
            self.lbl_url.setText(f"Verification URL: {url}")
            if code:
                self._user_code = code
                self.lbl_code.setText(f"Code: {code}")
                self.btn_copy_code.setEnabled(True)
            msg = str(frame.get("message") or "").strip()
            self.lbl_status.setText(msg or "Open the URL in your browser and enter the code above.")
        elif event_kind == "auth_notice":
            msg = str(frame.get("message") or "").strip()
            if msg:
                self.lbl_status.setText(msg)

    def _copy_code(self) -> None:
        if self._user_code:
            QApplication.clipboard().setText(self._user_code)
            self.lbl_status.setText(f"Copied device code '{self._user_code}' to clipboard.")

    def _open_url(self) -> None:
        QDesktopServices.openUrl(QUrl(self._verification_url))

    def _request_cancel(self) -> None:
        self._cancel_event.set()
        self.btn_cancel.setEnabled(False)
        self.lbl_status.setText("Cancelling sign-in...")

    def reject(self) -> None:
        self._cancel_event.set()
        super().reject()


class M365PreflightDialog(QDialog):
    """Displays workstation readiness for Live Pilot M365 PowerShell execution."""

    def __init__(
        self,
        preflight_service: M365PreflightService,
        report: Optional[PreflightReport] = None,
        parent=None,
    ) -> None:
        super().__init__(parent)
        self._service = preflight_service
        self._report = report
        self.setWindowTitle("M365 Live Tenant Readiness Check")
        self.setMinimumSize(620, 460)

        layout = QVBoxLayout(self)
        self.lbl_summary = QLabel(self)
        self.lbl_summary.setWordWrap(True)
        layout.addWidget(self.lbl_summary)

        self.details = QPlainTextEdit(self)
        self.details.setReadOnly(True)
        layout.addWidget(self.details, 1)

        btn_row = QHBoxLayout()
        self.btn_recheck = QPushButton("Re-check Environment", self)
        self.btn_recheck.clicked.connect(self.refresh_report)
        btn_row.addWidget(self.btn_recheck)

        self.btn_copy_install = QPushButton("Copy Missing Install Commands", self)
        self.btn_copy_install.clicked.connect(self._copy_install_commands)
        btn_row.addWidget(self.btn_copy_install)

        btn_box = QDialogButtonBox(QDialogButtonBox.Close, self)
        btn_box.rejected.connect(self.reject)
        btn_box.accepted.connect(self.accept)
        btn_row.addWidget(btn_box)
        layout.addLayout(btn_row)

        if self._report is None:
            self.refresh_report()
        else:
            self._render_report(self._report)

    def refresh_report(self) -> PreflightReport:
        self._report = self._service.run_check()
        self._render_report(self._report)
        return self._report

    def _render_report(self, report: PreflightReport) -> None:
        status_txt = "READY FOR LIVE PILOT" if report.live_ready else f"NOT READY ({report.error_code or 'PREREQUISITE_MISSING'})"
        self.lbl_summary.setText(f"Status: {status_txt}\n{report.summary}")

        lines = [
            f"PowerShell 7 Core: {'OK' if report.pwsh_ok else 'MISSING/UNSUPPORTED'} "
            f"(version={report.pwsh_version or 'none'}, edition={report.pwsh_edition or 'unknown'}, path={report.pwsh_path or 'not found'})",
            f"Contract Schemas (tnotes.m365 / 0.3.0): {'OK' if report.schemas_ok else 'INVALID'}",
            "",
            "Required PowerShell Modules (derived from pinned pilot manifests):",
        ]
        for mod in report.module_checks:
            state = "OK" if mod.satisfied else "MISSING"
            lines.append(
                f"  - [{state}] {mod.name} (minimum {mod.minimum_version}; "
                f"installed: {mod.installed_version or 'none installed'})"
            )
            if not mod.satisfied:
                lines.append(f"      Install manually: {mod.install_command}")
                lines.append(f"      Required for: {', '.join(mod.required_by)}")
        if report.schema_errors:
            lines.append("")
            lines.append("Schema validation errors:")
            for err in report.schema_errors:
                lines.append(f"  * {err}")

        self.details.setPlainText("\n".join(lines))
        self.btn_copy_install.setEnabled(bool(report.remediation_commands))

    def _copy_install_commands(self) -> None:
        if self._report is None:
            return
        cmds = "\n".join(self._report.remediation_commands)
        if not cmds:
            return
        QApplication.clipboard().setText(cmds)
        QMessageBox.information(
            self,
            "Install Commands Copied",
            "Copied PowerShell -Scope CurrentUser install commands to the clipboard.\n"
            "Run them in PowerShell 7, then click 'Re-check Environment'.",
        )


def run_directory_export(parent, directory) -> Optional[Path]:
    """Prompt for a destination path and export persisted M365 company metadata to JSON."""
    if not hasattr(directory, "export_to_file"):
        QMessageBox.information(
            parent,
            "Export Unavailable",
            "Company directory persistence is unavailable in this standalone session.",
        )
        return None
    if getattr(directory, "is_synthetic_preview", False) and directory.persisted_count() == 0:
        QMessageBox.information(
            parent,
            "Nothing Persisted Yet",
            "Only the synthetic preview is loaded right now.\n"
            "Add or save a real company first before exporting to JSON.",
        )
        return None

    dest_str, _ = QFileDialog.getSaveFileName(
        parent,
        "Export M365 Company Directory",
        str(Path.home() / "m365-company-directory.json"),
        "JSON Files (*.json)",
    )
    if not dest_str:
        return None
    try:
        out_path = directory.export_to_file(dest_str)
    except Exception as exc:
        QMessageBox.warning(parent, "Export Failed", f"Could not export company directory:\n{exc}")
        return None
    QMessageBox.information(parent, "Export Complete", f"Company directory exported to:\n{out_path}")
    return out_path


def run_directory_merge(parent, directory) -> bool:
    """Prompt for a company-directory JSON file and run an atomic pre-backup Merge."""
    if not hasattr(directory, "merge_from_file"):
        QMessageBox.information(
            parent,
            "Merge Unavailable",
            "Company directory persistence is unavailable in this standalone session.",
        )
        return False

    src_str, _ = QFileDialog.getOpenFileName(
        parent,
        "Merge M365 Company Directory JSON",
        str(Path.home()),
        "JSON Files (*.json)",
    )
    if not src_str:
        return False

    try:
        summary = directory.merge_from_file(src_str)
    except Exception as exc:
        QMessageBox.warning(parent, "Merge Rejected", f"Atomic Merge failed and rolled back cleanly:\n{exc}")
        return False

    backup_line = f"\nPre-merge backup saved:\n{summary.backup_path}" if summary.backup_path else ""
    total_persisted = directory.persisted_count() if hasattr(directory, "persisted_count") else 0
    QMessageBox.information(
        parent,
        "Merge Complete",
        f"Added: {summary.companies_added} | Updated: {summary.companies_updated} | Skipped: {summary.companies_skipped} "
        f"| Admins added: {summary.administrators_added} | Domains added: {summary.domains_added}\n"
        f"Total persisted companies: {total_persisted}{backup_line}",
    )
    return True

