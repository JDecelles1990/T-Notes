"""Tests for M365 Preflight Readiness, Persistent pwsh Worker, Dual Auth, and Live Pilot Execution."""

from __future__ import annotations

import json
import threading
import uuid
from pathlib import Path

import pytest
from PySide6.QtCore import QCoreApplication, QEvent
from PySide6.QtWidgets import QApplication

from src.database.connection import DatabaseManager
from src.database.migrations import init_database
from src.repositories.image_repository import ImageRepository
from src.repositories.scratchpad_repository import ScratchpadRepository
from src.repositories.session_repository import SessionRepository
from src.services.image_service import ImageService
from src.services.m365_company_service import Administrator, Company, CompanyDirectory
from src.services.m365_connection_manager import LiveConnectionManager
from src.services.m365_context_service import CompanyContextService
from src.services.m365_execution_service import (
    LIVE_PILOT_SCRIPT_IDS,
    M365ExecutionService,
    build_live_pilot_catalog_service,
)
from src.services.m365_preflight_service import M365PreflightService, version_at_least
from src.services.m365_worker_host import M365WorkerHost, WorkerIdentity, discover_pwsh
from src.services.scratchpad_service import ScratchpadService
from src.services.session_service import SessionService
from src.ui.main_window import TechPadMainWindow
from src.ui.m365.launcher_widget import M365LauncherWidget
from src.ui.m365.live_readiness_widgets import M365DeviceCodeDialog, M365PreflightDialog


COMPANY_ID = "10000000-0000-4000-8000-000000000101"
TENANT_ID = "20000000-0000-4000-8000-000000000202"
OTHER_TENANT_ID = "99999999-0000-4000-8000-000000000999"
ADMIN_ID = "30000000-0000-4000-8000-000000000303"
ADMIN_UPN = "alex@contoso.com"
TARGET_UPN = "user@contoso.com"
TARGET_OID = "40000000-0000-4000-8000-000000000404"


@pytest.fixture(scope="module")
def qapp():
    app = QApplication.instance()
    if app is None:
        app = QApplication([])
    return app


def _live_directory() -> CompanyDirectory:
    d = CompanyDirectory()
    admin = Administrator(ADMIN_ID, ADMIN_UPN, "Alex Live")
    d.save(
        Company(
            company_id=COMPANY_ID,
            display_name="Contoso Production",
            tenant_id=TENANT_ID,
            primary_domain="contoso.com",
            administrators=(admin,),
            preferred_administrator_id=ADMIN_ID,
        )
    )
    return d


class _FakeWorkerHost:
    """Deterministic fake matching M365WorkerHost API for offline live-boundary tests."""

    def __init__(self, identity: WorkerIdentity, *, script_behaviors=None) -> None:
        self.identity = identity
        self.started = False
        self.shutdown_calls = 0
        self.sent_commands: list[tuple[str, dict]] = []
        self.script_behaviors = script_behaviors or {}

    @property
    def is_alive(self) -> bool:
        return self.started and self.shutdown_calls == 0

    def start(self) -> None:
        self.started = True

    def shutdown(self, *, force: bool = False) -> None:
        self.shutdown_calls += 1

    def send_command(self, cmd, payload=None, *, timeout_seconds=90.0, cancel_event=None, on_event=None):
        payload = dict(payload or {})
        self.sent_commands.append((cmd, payload))
        if cmd in self.script_behaviors:
            fn = self.script_behaviors[cmd]
            return fn(payload, on_event=on_event, cancel_event=cancel_event)
        return {"ok": True, "data": {}}


# ── Phase 1A: Preflight Tests ────────────────────────────────────────────────


def test_semver_helper_handles_numeric_and_prerelease():
    assert version_at_least("7.6.10", "7.0.0")
    assert version_at_least("2.25.0", "2.0.0")
    assert version_at_least("3.6.0-preview1", "3.0.0")
    assert not version_at_least("1.28.0", "2.0.0")
    assert not version_at_least(None, "2.0.0")


def test_preflight_reports_missing_modules_with_remediation():
    def _fake_probe(_pwsh: Path, names: tuple[str, ...]) -> dict:
        return {
            "pwsh_found": True,
            "version": "7.6.10",
            "edition": "Core",
            "modules": {n: ("2.20.0" if n == "Microsoft.Graph.Authentication" else None) for n in names},
        }

    svc = M365PreflightService(probe_runner=_fake_probe)
    report = svc.run_check()
    assert report.pwsh_ok is True
    assert report.schemas_ok is True
    assert report.modules_ok is False
    assert report.live_ready is False
    assert report.error_code == "MODULE_MISSING"
    assert any("Install-Module Microsoft.Graph.Users -MinimumVersion" in c for c in report.remediation_commands)
    assert any("Install-Module ExchangeOnlineManagement -MinimumVersion" in c for c in report.remediation_commands)
    assert not any("Microsoft.Graph.Authentication" in c for c in report.remediation_commands)


def test_preflight_reports_ready_when_all_modules_satisfied():
    def _fake_probe(_pwsh: Path, names: tuple[str, ...]) -> dict:
        versions = {
            "Microsoft.Graph.Authentication": "2.25.0",
            "Microsoft.Graph.Users": "2.25.0",
            "Microsoft.Graph.Reports": "2.25.0",
            "ExchangeOnlineManagement": "3.6.0",
        }
        return {
            "pwsh_found": True,
            "version": "7.6.10",
            "edition": "Core",
            "modules": {n: versions.get(n, "2.0.0") for n in names},
        }

    svc = M365PreflightService(probe_runner=_fake_probe)
    report = svc.run_check()
    assert report.live_ready is True
    assert report.error_code is None
    assert report.remediation_commands == ()


def test_preflight_reports_unsupported_powershell_version():
    svc = M365PreflightService(
        probe_runner=lambda _p, _n: {"pwsh_found": True, "version": "5.1.19041", "edition": "Desktop", "modules": {}}
    )
    report = svc.run_check()
    assert report.pwsh_ok is False
    assert report.live_ready is False
    assert report.error_code == "PS_VERSION_UNSUPPORTED"


def test_preflight_real_workstation_probe():
    pwsh = discover_pwsh()
    assert pwsh is not None and pwsh.is_file()
    report = M365PreflightService(pwsh_path=pwsh).run_check()
    assert report.pwsh_ok is True
    assert report.schemas_ok is True


# ── Phase 1B: Real Persistent PowerShell Worker Tests ────────────────────────


def test_real_worker_host_ping_fail_closed_operation_and_shutdown():
    pwsh = discover_pwsh()
    assert pwsh is not None
    identity = WorkerIdentity(
        worker_id=str(uuid.uuid4()),
        company_id=COMPANY_ID,
        tenant_id=TENANT_ID,
        admin_identity_ref=str(uuid.uuid4()),
        session_generation=1,
    )
    host = M365WorkerHost(identity, pwsh_path=pwsh)
    try:
        host.start()
        assert host.is_alive
        ping = host.send_command("ping")
        assert ping["ok"] is True
        assert int(ping["data"]["pid"]) == host.pid

        # Even if someone tries invoke_operation without Microsoft.Graph installed,
        # M365WorkerHost.ps1 MUST fail closed with MODULE_MISSING and NEVER fall back to synthetic fixture data!
        script_path = Path("scripts/m365/entra-id/user-identity/Get-UserIdentity.ps1").resolve()
        protocol_path = Path("prototypes/m365_official_engine/protocol.ps1").resolve()
        op_resp = host.send_command(
            "invoke_operation",
            {
                "protocol_path": str(protocol_path),
                "script_path": str(script_path),
                "context": {
                    "contract_version": "0.3.0",
                    "correlation_id": str(uuid.uuid4()),
                    "script_id": "M365.ENTRA.USER_IDENTITY",
                    "company_id": COMPANY_ID,
                    "tenant_id": TENANT_ID,
                    "admin_identity_ref": identity.admin_identity_ref,
                    "session_generation": 1,
                    "target": {"kind": "upn", "value": "user@contoso.com"},
                    "ticket_context": None,
                    "release_binding": {
                        "script_version": "0.3.0-synthetic.1",
                        "script_sha256": "0" * 64,
                        "manifest_sha256": "0" * 64,
                        "output_schema_sha256": "0" * 64,
                    },
                    "verified_account_upn": ADMIN_UPN,
                    "connections": [],
                },
                "parameters": {},
                "required_modules": [
                    {"name": "NonExistent.M365.Module", "minimum_version": "99.0.0", "maximum_version": "99.9.0"}
                ],
                "required_cmdlets": ["Get-MgUser"],
                "connection_requirements": [],
                "already_cancelled": False,
            },
        )
        assert op_resp["ok"] is True
        op_data = op_resp["data"]
        assert op_data["status"] == "error"
        assert op_data["errors"][0]["code"] == "MODULE_MISSING"
        assert op_data["data"] is None
    finally:
        host.shutdown()
    assert not host.is_alive


# ── Phase 1B & 3: LiveConnectionManager & Live Pilot Execution ───────────────


def test_live_connection_manager_browser_device_code_and_mismatch_rejection():
    workers: list[_FakeWorkerHost] = []

    def _factory(identity: WorkerIdentity) -> _FakeWorkerHost:
        def _connect_graph(payload, on_event=None, cancel_event=None):
            if payload["auth_mode"] == "device_code" and on_event is not None:
                on_event(
                    {
                        "type": "event",
                        "event": "device_code",
                        "verification_uri": "https://microsoft.com/devicelogin",
                        "user_code": "XYZ98765",
                        "message": "To sign in, open https://microsoft.com/devicelogin and enter the code XYZ98765",
                    }
                )
            return {
                "ok": True,
                "data": {
                    "service": "Graph",
                    "tenant_id": TENANT_ID,
                    "account_upn": ADMIN_UPN,
                    "scopes": payload["scopes"],
                    "auth_mode": payload["auth_mode"],
                    "verified": True,
                },
            }

        def _connect_exo(payload, **_kw):
            # Simulate wrong tenant signed into browser
            return {
                "ok": True,
                "data": {
                    "service": "ExchangeOnline",
                    "tenant_id": OTHER_TENANT_ID,
                    "account_upn": ADMIN_UPN,
                    "effective_roles": ["cmdlet.Get-EXOMailbox", "cmdlet.Get-EXOMailboxStatistics"],
                    "verified": True,
                },
            }

        w = _FakeWorkerHost(
            identity,
            script_behaviors={"connect_graph": _connect_graph, "connect_exchange": _connect_exo},
        )
        workers.append(w)
        return w

    mgr = LiveConnectionManager(worker_factory=_factory)
    events: list[dict] = []
    graph_state = mgr.connect_service(
        service="Graph",
        company_id=COMPANY_ID,
        tenant_id=TENANT_ID,
        admin_identity_ref=str(uuid.uuid4()),
        expected_account_upn=ADMIN_UPN,
        session_generation=1,
        auth_mode="device_code",
        on_event=events.append,
    )
    assert graph_state.state == "verified"
    assert graph_state.auth_mode == "device_code"
    assert len(events) == 1 and events[0]["user_code"] == "XYZ98765"

    # Mismatched tenant from EXO sign-in MUST fail closed with TENANT_MISMATCH
    exo_state = mgr.connect_service(
        service="ExchangeOnline",
        company_id=COMPANY_ID,
        tenant_id=TENANT_ID,
        admin_identity_ref=workers[0].identity.admin_identity_ref,
        expected_account_upn=ADMIN_UPN,
        session_generation=1,
        auth_mode="browser",
    )
    assert exo_state.state == "error"
    assert exo_state.error_code == "TENANT_MISMATCH"

    # Switching context generation synchronously shuts down old worker
    mgr.connect_service(
        service="Graph",
        company_id=COMPANY_ID,
        tenant_id=TENANT_ID,
        admin_identity_ref=str(uuid.uuid4()),
        expected_account_upn=ADMIN_UPN,
        session_generation=2,
        auth_mode="browser",
    )
    assert len(workers) == 2
    assert workers[0].shutdown_calls == 1
    mgr.clear()
    assert workers[1].shutdown_calls == 1


def test_live_pilot_catalog_exclusion_and_runtime_execution():
    pilot_catalog = build_live_pilot_catalog_service()
    loaded_ids = {
        op.id
        for cat in pilot_catalog.categories
        if cat.kind == "operations"
        for op in pilot_catalog.operations(cat.id)
    }
    assert loaded_ids == set(LIVE_PILOT_SCRIPT_IDS)
    assert "M365.INTUNE.COMPLIANCE_ENROLLMENT_DIAGNOSTIC" not in loaded_ids

    def _invoke(payload, **_kw):
        script_id = payload["context"]["script_id"]
        assert "cmdlet.Get-EXOMailbox" in payload["context"]["connections"][0]["effective_roles"] or script_id == "M365.ENTRA.USER_IDENTITY"
        if script_id == "M365.ENTRA.USER_IDENTITY":
            return {
                "ok": True,
                "data": {
                    "status": "success",
                    "operation_outcome": "succeeded",
                    "data": {
                        "id": TARGET_OID,
                        "display_name": "Live Client User",
                        "user_principal_name": TARGET_UPN,
                        "account_enabled": True,
                        "user_type": "Member",
                    },
                    "warnings": [],
                    "errors": [],
                },
            }
        return {
            "ok": True,
            "data": {
                "status": "success",
                "operation_outcome": "succeeded",
                "data": {
                    "target_user_id": TARGET_OID,
                    "mailbox_exists": True,
                    "recipient_type_details": "UserMailbox",
                    "primary_smtp_address": TARGET_UPN,
                    "total_item_size_bytes": 2048,
                    "prohibit_send_quota_bytes": 53687091200,
                },
                "warnings": [],
                "errors": [],
            },
        }

    def _connect_graph(payload, **_kw):
        return {
            "ok": True,
            "data": {
                "service": "Graph",
                "tenant_id": TENANT_ID,
                "account_upn": ADMIN_UPN,
                "scopes": ["User.Read.All", "AuditLog.Read.All"],
                "verified": True,
            },
        }

    def _connect_exo(payload, **_kw):
        return {
            "ok": True,
            "data": {
                "service": "ExchangeOnline",
                "tenant_id": TENANT_ID,
                "account_upn": ADMIN_UPN,
                "effective_roles": ["cmdlet.Get-EXOMailbox", "cmdlet.Get-EXOMailboxStatistics"],
                "verified": True,
            },
        }

    workers = []

    def _factory(identity: WorkerIdentity) -> _FakeWorkerHost:
        w = _FakeWorkerHost(
            identity,
            script_behaviors={
                "connect_graph": _connect_graph,
                "connect_exchange": _connect_exo,
                "invoke_operation": _invoke,
            },
        )
        workers.append(w)
        return w

    live_mgr = LiveConnectionManager(worker_factory=_factory)
    ctx = CompanyContextService(_live_directory(), live_connection_manager=live_mgr, mode="live")
    ctx.select_company(COMPANY_ID)
    ctx.confirm_company()
    ctx.connect_live("Graph", auth_mode="browser")
    ctx.connect_live("ExchangeOnline", auth_mode="browser")
    ctx.set_target(TARGET_UPN)

    exec_svc = M365ExecutionService(ctx, pilot_catalog)

    # Synthetic-only operations must never run in Live mode
    blocked = exec_svc.execute("M365.INTUNE.COMPLIANCE_ENROLLMENT_DIAGNOSTIC")
    assert blocked.status == "error"

    # Real target resolution via M365.ENTRA.USER_IDENTITY produces runtime provenance
    resolved = exec_svc.resolve_live_target()
    assert resolved.status == "success"
    assert resolved.provenance == "runtime"
    assert resolved.history_record["provenance"] == "runtime"
    assert "Source: Live Microsoft 365 Tenant (runtime)" in resolved.summary_text
    assert ctx.target is not None and ctx.target.object_id == TARGET_OID

    # Downstream mailbox summary unlocks cleanly
    mbx = exec_svc.execute("M365.EXCHANGE.MAILBOX_SUMMARY")
    assert mbx.status == "success"
    assert mbx.provenance == "runtime"

    # Switching mode cleanly terminates live worker
    ctx.set_mode("synthetic")
    assert workers[0].shutdown_calls == 1


# ── UI Tests ─────────────────────────────────────────────────────────────────


def test_preflight_and_device_code_dialogs(qapp):
    svc = M365PreflightService(
        probe_runner=lambda _p, names: {
            "pwsh_found": True,
            "version": "7.6.10",
            "edition": "Core",
            "modules": {n: None for n in names},
        }
    )
    dlg = M365PreflightDialog(svc)
    assert "MODULE_MISSING" in dlg.lbl_summary.text()
    assert dlg.btn_copy_install.isEnabled() is True
    assert "Install-Module" in dlg.details.toPlainText()
    dlg.close()

    ev = threading.Event()
    dc = M365DeviceCodeDialog("Graph", TENANT_ID, ADMIN_UPN, ev)
    dc.handle_worker_event(
        {
            "event": "device_code",
            "verification_uri": "https://microsoft.com/devicelogin",
            "user_code": "HJK4455",
            "message": "Enter code HJK4455 at https://microsoft.com/devicelogin",
        }
    )
    assert "HJK4455" in dc.lbl_code.text()
    assert dc.btn_copy_code.isEnabled() is True
    dc._request_cancel()
    assert ev.is_set() is True


def test_main_window_wires_persistent_directory_and_shuts_down_m365(qapp, tmp_path):
    db = DatabaseManager(tmp_path / "techpad.db")
    init_database(db)
    img_svc = ImageService(ImageRepository(db))
    sp_svc = ScratchpadService(ScratchpadRepository(db), img_svc)
    sess_svc = SessionService(SessionRepository(db), sp_svc)

    win = TechPadMainWindow(sp_svc, img_svc, sess_svc)
    try:
        assert win.m365_company_directory is not None
        assert hasattr(win.m365_company_directory, "export_to_file")
        win.m365_workspace.enable_live_pilot_mode()
        assert win.m365_workspace.context_service.is_live is True
        assert "Live Pilot" in win.m365_workspace.notice_label.text()
        assert win.m365_workspace.operation_list.count() >= 0
    finally:
        win.m365_workspace.shutdown()
        win.quit_application()
        qapp.removeEventFilter(win)
        win.deleteLater()
        QCoreApplication.sendPostedEvents(None, QEvent.DeferredDelete)
        db.close()
