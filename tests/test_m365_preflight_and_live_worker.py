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
        assert "Live Tenant" in win.m365_workspace.notice_label.text()
        assert win.m365_workspace.catalog_service.validation_errors == ()
        assert len(win.m365_workspace.catalog_service._operations) == 25
    finally:
        win.m365_workspace.shutdown()
        win.quit_application()
        qapp.removeEventFilter(win)
        win.deleteLater()
        QCoreApplication.sendPostedEvents(None, QEvent.DeferredDelete)
        db.close()


def test_live_tenant_25_catalog_unapproved_op_rejection_and_exo_view_only_role():
    """Verify all 25 read-only ops are live-enabled, unapproved ops fail closed, and EXO View-Only Recipients passes."""
    live_cat = build_live_pilot_catalog_service()
    assert live_cat.validation_errors == ()
    live_ids = set(live_cat._operations.keys())
    assert len(live_ids) == 25
    assert live_ids == set(LIVE_PILOT_SCRIPT_IDS)

    created_hosts: list[_FakeWorkerHost] = []

    def _make_host(identity: WorkerIdentity) -> _FakeWorkerHost:
        h = _FakeWorkerHost(
            identity,
            script_behaviors={
                "connect_exchange": lambda _p, **_k: {
                    "ok": True,
                    "data": {
                        "service": "ExchangeOnline",
                        "tenant_id": TENANT_ID,
                        "account_upn": ADMIN_UPN,
                        "effective_roles": ["View-Only.Recipients"],
                        "verified": True,
                    },
                },
                "invoke_operation": lambda p, **_k: {
                    "ok": True,
                    "data": {
                        "status": "success",
                        "operation_outcome": "succeeded",
                        "data": {
                            "target_user_id": TARGET_OID,
                            "mailbox_exists": True,
                            "recipient_type_details": "UserMailbox",
                            "primary_smtp_address": TARGET_UPN,
                            "total_item_size_bytes": 1000,
                            "prohibit_send_quota_bytes": 2000,
                        },
                        "warnings": [],
                        "errors": [],
                    },
                },
            },
        )
        created_hosts.append(h)
        return h

    ctx = CompanyContextService(_live_directory())
    ctx._live_connections = LiveConnectionManager(worker_factory=_make_host)
    ctx.set_mode("live")
    ctx.select_company(COMPANY_ID)
    ctx.confirm_company()

    svc = M365ExecutionService(ctx, catalog_service=live_cat)
    rejected = svc.execute("M365.INTUNE.UNAPPROVED_WRITE")
    assert rejected.status == "error"

    exo_state = ctx.connect_live("ExchangeOnline")
    assert exo_state.state == "verified"
    ctx.set_target(TARGET_UPN)
    ctx.record_live_target(tenant_id=TENANT_ID, resolved_upn=TARGET_UPN, resolved_object_id=TARGET_OID)

    eligible, reasons = svc.check_operation_eligibility("M365.EXCHANGE.MAILBOX_QUOTA_AND_HOLD")
    assert eligible, reasons
    outcome = svc.execute("M365.EXCHANGE.MAILBOX_QUOTA_AND_HOLD", {"IncludeArchiveCheck": True})
    assert outcome.status == "success"
    assert outcome.provenance == "runtime"
    assert outcome.result_envelope["data"]["primary_smtp_address"] == TARGET_UPN
    ctx.connections.clear()


def test_live_mocked_cmdlets_for_all_13_upgraded_scripts():
    """Execute all 13 newly upgraded .ps1 scripts against mocked Graph/EXO cmdlets and validate 0.3.0 schemas."""
    import subprocess

    exec_service = M365ExecutionService(CompanyContextService(_live_directory()))
    ps_script = r"""
$ErrorActionPreference = 'Stop'
. 'C:\Dev\T-Notes\prototypes\m365_official_engine\protocol.ps1'
Initialize-NativeReturnValidation
$cts = [System.Threading.CancellationTokenSource]::new()

$graphConn = [pscustomobject]@{
    service = 'Graph'
    state = 'verified'
    tenant_id = '20000000-0000-4000-8000-000000000202'
    verified_account_upn = 'alex@contoso.com'
    graph_scopes = @('User.Read.All', 'LicenseAssignment.Read.All', 'AuditLog.Read.All')
    effective_roles = @('Directory.Readers', 'Reports.Reader', 'Security.Reader')
}
$exoConn = [pscustomobject]@{
    service = 'ExchangeOnline'
    state = 'verified'
    tenant_id = '20000000-0000-4000-8000-000000000202'
    verified_account_upn = 'alex@contoso.com'
    graph_scopes = @()
    effective_roles = @('View-Only.Recipients')
}

function New-Ctx([string]$ScriptId, [string]$Kind, [string]$Val, $Conn) {
    return [pscustomobject]@{
        contract_version = '0.3.0'
        script_id = $ScriptId
        tenant_id = '20000000-0000-4000-8000-000000000202'
        verified_account_upn = 'alex@contoso.com'
        target = [pscustomobject]@{ kind = $Kind; value = $Val }
        connections = @($Conn)
    }
}

$oid = '40000000-0000-4000-8000-000000000404'
$upn = 'user@contoso.com'

function Get-MgUser {
    param([string]$UserId, [string[]]$Property, $ErrorAction)
    $now = [datetime]::UtcNow
    if ($UserId -match 'guest') {
        return [pscustomobject]@{
            Id = '40000000-0000-4000-8000-000000000499'
            DisplayName = 'Guest Partner'
            UserPrincipalName = $UserId
            AccountEnabled = $true
            UserType = 'Guest'
            ExternalUserState = 'PendingAcceptance'
            ExternalUserStateChangeDateTime = $now.AddDays(-5)
            CreationType = 'Invitation'
            Mail = 'guest.partner@external.example'
            OtherMails = @('guest.partner@external.example')
            ProxyAddresses = @()
        }
    }
    return [pscustomobject]@{
        Id = $oid
        DisplayName = 'Live User'
        UserPrincipalName = $upn
        AccountEnabled = $true
        UserType = 'Member'
        Mail = 'user@mailmismatch.com'
        ProxyAddresses = @('SMTP:user@mailmismatch.com', 'smtp:alias@contoso.com')
        LastPasswordChangeDateTime = $now.AddDays(-120)
        PasswordPolicies = 'DisablePasswordExpiration'
        OnPremisesSyncEnabled = $true
        OnPremisesLastSyncDateTime = $now.AddMinutes(-15)
        SignInSessionsValidFromDateTime = $now.AddDays(-10)
        ExternalUserState = $null
        CreationType = 'Local'
    }
}

function Get-MgUserMemberOf {
    param([string]$UserId, [switch]$All, $ErrorAction)
    return @(
        [pscustomobject]@{
            Id = 'grp-m365-1'
            DisplayName = 'Engineering Collab'
            GroupTypes = @('Unified')
            SecurityEnabled = $true
            MailEnabled = $true
            AdditionalProperties = @{ '@odata.type' = '#microsoft.graph.group' }
        },
        [pscustomobject]@{
            Id = 'grp-sec-1'
            DisplayName = 'VPN-Users'
            GroupTypes = @()
            SecurityEnabled = $true
            MailEnabled = $false
            AdditionalProperties = @{ '@odata.type' = '#microsoft.graph.group' }
        },
        [pscustomobject]@{
            Id = 'role-helpdesk-1'
            DisplayName = 'Helpdesk Administrator'
            RoleTemplateId = '729827e3-9c14-49f7-bb1b-9608f156bbb8'
            AdditionalProperties = @{ '@odata.type' = '#microsoft.graph.directoryRole' }
        }
    )
}

function Get-MgUserLicenseDetail {
    param([string]$UserId, $ErrorAction)
    return @(
        [pscustomobject]@{
            Id = 'lic-1'
            SkuId = '6fd2c87f-b296-42f0-b197-1e91e994b900'
            SkuPartNumber = 'SPE_E5'
            ServicePlans = @(
                [pscustomobject]@{ ServicePlanId = '11111111-1111-4111-8111-111111111111'; ServicePlanName = 'EXCHANGE_S_ENTERPRISE'; ProvisioningStatus = 'Success' },
                [pscustomobject]@{ ServicePlanId = '22222222-2222-4222-8222-222222222222'; ServicePlanName = 'SHAREPOINTENTERPRISE'; ProvisioningStatus = 'Success' },
                [pscustomobject]@{ ServicePlanId = '33333333-3333-4333-8333-333333333333'; ServicePlanName = 'TEAMS1'; ProvisioningStatus = 'Success' },
                [pscustomobject]@{ ServicePlanId = '44444444-4444-4444-8444-444444444444'; ServicePlanName = 'ONEDRIVE_BASIC'; ProvisioningStatus = 'PendingInput' }
            )
        }
    )
}

function Get-MgAuditLogSignIn {
    param([string]$Filter, [int]$Top, [string[]]$Property, $ErrorAction)
    $now = [datetime]::UtcNow
    return @(
        [pscustomobject]@{
            Id = 's1'; UserId = $oid; CreatedDateTime = $now.AddMinutes(-10)
            AppDisplayName = 'Microsoft Teams'; ResourceDisplayName = 'Microsoft Teams Services'
            ClientAppUsed = 'Mobile Apps and Desktop clients'; AuthenticationRequirement = 'multiFactorAuthentication'
            ConditionalAccessStatus = 'failure'; IsInteractive = $true; RiskLevelDuringSignIn = 'medium'; RiskState = 'atRisk'
            MfaDetail = [pscustomobject]@{ AuthMethod = 'PhoneAppNotification' }
            DeviceDetail = [pscustomobject]@{ OperatingSystem = 'Windows 11'; IsCompliant = $false; IsManaged = $true; TrustType = 'AzureAdJoined' }
            Status = [pscustomobject]@{ ErrorCode = 50074 }
        },
        [pscustomobject]@{
            Id = 's2'; UserId = $oid; CreatedDateTime = $now.AddMinutes(-20)
            AppDisplayName = 'Office 365 SharePoint Online'; ResourceDisplayName = 'Office 365 SharePoint Online'
            ClientAppUsed = 'Browser'; AuthenticationRequirement = 'singleFactorAuthentication'
            ConditionalAccessStatus = 'success'; IsInteractive = $true; RiskLevelDuringSignIn = 'none'; RiskState = 'none'
            DeviceDetail = [pscustomobject]@{ OperatingSystem = 'Windows 11'; IsCompliant = $true; IsManaged = $true }
            Status = [pscustomobject]@{ ErrorCode = 0 }
        },
        [pscustomobject]@{
            Id = 's3'; UserId = $oid; CreatedDateTime = $now.AddMinutes(-30)
            AppDisplayName = 'Microsoft Intune Company Portal'; ResourceDisplayName = 'Microsoft Intune'
            ClientAppUsed = 'Mobile Apps and Desktop clients'; AuthenticationRequirement = 'multiFactorAuthentication'
            ConditionalAccessStatus = 'success'; IsInteractive = $true; RiskLevelDuringSignIn = 'none'; RiskState = 'none'
            DeviceDetail = [pscustomobject]@{ DeviceId = 'dev-corp-1'; DisplayName = 'WS-CORP-01'; OperatingSystem = 'Windows 11'; Browser = 'Edge'; IsCompliant = $false; IsManaged = $true; TrustType = 'AzureAdJoined' }
            Status = [pscustomobject]@{ ErrorCode = 0 }
        },
        [pscustomobject]@{
            Id = 's4'; UserId = $oid; CreatedDateTime = $now.AddMinutes(-40)
            AppDisplayName = 'Microsoft OneDrive Sync Engine'; ResourceDisplayName = 'Microsoft OneDrive'
            ClientAppUsed = 'Mobile Apps and Desktop clients'; AuthenticationRequirement = 'multiFactorAuthentication'
            ConditionalAccessStatus = 'failure'; IsInteractive = $false; RiskLevelDuringSignIn = 'none'; RiskState = 'none'
            DeviceDetail = [pscustomobject]@{ DeviceId = 'dev-corp-1'; DisplayName = 'WS-CORP-01'; OperatingSystem = 'Windows 11'; IsCompliant = $true; IsManaged = $true; TrustType = 'AzureAdJoined' }
            Status = [pscustomobject]@{ ErrorCode = 50076; FailureReason = 'MFA challenge required for OneDrive sync.' }
        },
        [pscustomobject]@{
            Id = 's5'; UserId = $oid; CreatedDateTime = $now.AddMinutes(-50)
            AppDisplayName = 'Exchange Online'; ResourceDisplayName = 'Exchange Online'
            ClientAppUsed = 'IMAP4'; IpAddress = '198.51.100.77'; AuthenticationRequirement = 'singleFactorAuthentication'
            ConditionalAccessStatus = 'notApplied'; IsInteractive = $false; RiskLevelDuringSignIn = 'none'; RiskState = 'none'
            DeviceDetail = [pscustomobject]@{ DeviceId = 'dev-byod-2'; DisplayName = 'iPhone-BYOD'; OperatingSystem = 'iOS 17'; Browser = 'Mobile Safari'; IsCompliant = $false; IsManaged = $false; TrustType = 'Workplace' }
            Status = [pscustomobject]@{ ErrorCode = 50053; FailureReason = 'Smart Lockout triggered.' }
        }
    )
}

function Get-EXOMailbox {
    param([guid]$ExternalDirectoryObjectId, [string[]]$Properties, $ErrorAction)
    return [pscustomobject]@{
        ExternalDirectoryObjectId = $ExternalDirectoryObjectId.ToString()
        RecipientTypeDetails = 'UserMailbox'
        PrimarySmtpAddress = $upn
        ProhibitSendQuota = '50 GB (53,687,091,200 bytes)'
        LitigationHoldEnabled = $true
        RetentionHoldEnabled = $false
        InPlaceHolds = @('hold-1')
        ArchiveStatus = 'Active'
        ForwardingSmtpAddress = 'smtp:forward@external.invalid'
        ForwardingAddress = $null
        DeliverToMailboxAndForward = $true
        HiddenFromAddressListsEnabled = $true
        GrantSendOnBehalfTo = @('manager@contoso.com')
    }
}

function Get-MailboxAutoReplyConfiguration {
    param([string]$Identity, $ErrorAction)
    return [pscustomobject]@{
        AutoReplyState = 'Scheduled'
        StartTime = '2026-11-15T00:00:00Z'
        EndTime = '2026-11-20T00:00:00Z'
        ExternalAudience = 'All'
    }
}

function Get-EXOMailboxPermission {
    param([string]$Identity, $ErrorAction)
    return @(
        [pscustomobject]@{ User = 'NT AUTHORITY\SELF'; AccessRights = @('FullAccess'); Deny = $false },
        [pscustomobject]@{ User = 'delegate.one@contoso.com'; AccessRights = @('FullAccess'); Deny = $false }
    )
}

function Get-EXORecipientPermission {
    param([string]$Identity, $ErrorAction)
    return @(
        [pscustomobject]@{ Trustee = 'NT AUTHORITY\SELF'; AccessRights = @('SendAs') },
        [pscustomobject]@{ Trustee = 'shared.sender@contoso.com'; AccessRights = @('SendAs') }
    )
}

function Get-EXOMailboxStatistics {
    param([string]$Identity, [switch]$Archive, $ErrorAction)
    if ($Archive) {
        return [pscustomobject]@{ TotalItemSize = '4 GB (4,294,967,296 bytes)' }
    }
    return [pscustomobject]@{ TotalItemSize = '46 GB (49,392,123,904 bytes)' }
}

$results = @{}

$r1 = & 'C:\Dev\T-Notes\scripts\m365\general\tenant-user-overview\Get-TenantUserOverview.ps1' -Context (New-Ctx 'M365.GENERAL.TENANT_USER_OVERVIEW' 'upn' $upn $graphConn) -Parameters @{ VerifyDomainMatch = $true } -CancellationToken $cts.Token
Assert-NativeOperationReturn $r1; $results['M365.GENERAL.TENANT_USER_OVERVIEW'] = $r1

$r2 = & 'C:\Dev\T-Notes\scripts\m365\other\upn-smtp-alignment\Get-UpnSmtpAlignment.ps1' -Context (New-Ctx 'M365.OTHER.UPN_SMTP_ALIGNMENT' 'upn' $upn $graphConn) -Parameters @{ StrictDomainCheck = $true } -CancellationToken $cts.Token
Assert-NativeOperationReturn $r2; $results['M365.OTHER.UPN_SMTP_ALIGNMENT'] = $r2

$r3 = & 'C:\Dev\T-Notes\scripts\m365\general\service-readiness\Get-ServiceReadinessAudit.ps1' -Context (New-Ctx 'M365.GENERAL.SERVICE_READINESS_AUDIT' 'object_id' $oid $graphConn) -Parameters @{ IncludeCollaborationPlans = $true } -CancellationToken $cts.Token
Assert-NativeOperationReturn $r3; $results['M365.GENERAL.SERVICE_READINESS_AUDIT'] = $r3

$r4 = & 'C:\Dev\T-Notes\scripts\m365\licensing\service-plan-audit\Get-ServicePlanAudit.ps1' -Context (New-Ctx 'M365.LICENSING.SERVICE_PLAN_AUDIT' 'object_id' $oid $graphConn) -Parameters @{ OnlyProvisionedPlans = $true } -CancellationToken $cts.Token
Assert-NativeOperationReturn $r4; $results['M365.LICENSING.SERVICE_PLAN_AUDIT'] = $r4

$r5 = & 'C:\Dev\T-Notes\scripts\m365\onedrive\sync-diagnostic\Get-OneDriveSyncDiagnostic.ps1' -Context (New-Ctx 'M365.ONEDRIVE.SYNC_AND_STORAGE_DIAGNOSTIC' 'object_id' $oid $graphConn) -Parameters @{ IncludeSharePointPlan = $true } -CancellationToken $cts.Token
Assert-NativeOperationReturn $r5; $results['M365.ONEDRIVE.SYNC_AND_STORAGE_DIAGNOSTIC'] = $r5

$r6 = & 'C:\Dev\T-Notes\scripts\m365\teams\user-readiness\Get-TeamsUserReadiness.ps1' -Context (New-Ctx 'M365.TEAMS.USER_READINESS' 'object_id' $oid $graphConn) -Parameters @{ IncludeVoicePlans = $true } -CancellationToken $cts.Token
Assert-NativeOperationReturn $r6; $results['M365.TEAMS.USER_READINESS'] = $r6

$r7 = & 'C:\Dev\T-Notes\scripts\m365\entra-id\user-mfa-audit\Get-UserMfaAudit.ps1' -Context (New-Ctx 'M365.ENTRA.USER_MFA_AUDIT' 'object_id' $oid $graphConn) -Parameters @{ LookbackDays = 7; MaxRecords = 10 } -CancellationToken $cts.Token
Assert-NativeOperationReturn $r7; $results['M365.ENTRA.USER_MFA_AUDIT'] = $r7

$r8 = & 'C:\Dev\T-Notes\scripts\m365\security\risky-signins\Get-SecurityRiskySignIns.ps1' -Context (New-Ctx 'M365.SECURITY.RISKY_SIGNIN_AUDIT' 'object_id' $oid $graphConn) -Parameters @{ LookbackDays = 14; MaxRecords = 20 } -CancellationToken $cts.Token
Assert-NativeOperationReturn $r8; $results['M365.SECURITY.RISKY_SIGNIN_AUDIT'] = $r8

$r9 = & 'C:\Dev\T-Notes\scripts\m365\teams\client-signins\Get-TeamsClientSignIns.ps1' -Context (New-Ctx 'M365.TEAMS.CLIENT_SIGNINS' 'object_id' $oid $graphConn) -Parameters @{ LookbackDays = 14; MaxRecords = 20 } -CancellationToken $cts.Token
Assert-NativeOperationReturn $r9; $results['M365.TEAMS.CLIENT_SIGNINS'] = $r9

$r10 = & 'C:\Dev\T-Notes\scripts\m365\intune\compliance-enrollment\Get-IntuneComplianceDiagnostic.ps1' -Context (New-Ctx 'M365.INTUNE.COMPLIANCE_AND_ENROLLMENT' 'object_id' $oid $graphConn) -Parameters @{ LookbackDays = 14; MaxRecords = 20 } -CancellationToken $cts.Token
Assert-NativeOperationReturn $r10; $results['M365.INTUNE.COMPLIANCE_AND_ENROLLMENT'] = $r10

$r11 = & 'C:\Dev\T-Notes\scripts\m365\reports\user-access-audit\Get-UserAccessAuditReport.ps1' -Context (New-Ctx 'M365.REPORTS.USER_ACCESS_AUDIT_REPORT' 'object_id' $oid $graphConn) -Parameters @{ LookbackDays = 14; MaxRecords = 20 } -CancellationToken $cts.Token
Assert-NativeOperationReturn $r11; $results['M365.REPORTS.USER_ACCESS_AUDIT_REPORT'] = $r11

$r12 = & 'C:\Dev\T-Notes\scripts\m365\sharepoint\access-diagnostic\Get-SharePointAccessDiagnostic.ps1' -Context (New-Ctx 'M365.SHAREPOINT.ACCESS_DIAGNOSTIC' 'object_id' $oid $graphConn) -Parameters @{ LookbackDays = 14; MaxRecords = 20 } -CancellationToken $cts.Token
Assert-NativeOperationReturn $r12; $results['M365.SHAREPOINT.ACCESS_DIAGNOSTIC'] = $r12

$r13 = & 'C:\Dev\T-Notes\scripts\m365\exchange-online\mailbox-quota-hold\Get-MailboxQuotaAndHold.ps1' -Context (New-Ctx 'M365.EXCHANGE.MAILBOX_QUOTA_AND_HOLD' 'object_id' $oid $exoConn) -Parameters @{ IncludeArchiveCheck = $true } -CancellationToken $cts.Token
Assert-NativeOperationReturn $r13; $results['M365.EXCHANGE.MAILBOX_QUOTA_AND_HOLD'] = $r13

$r14 = & 'C:\Dev\T-Notes\scripts\m365\exchange-online\forwarding-auto-reply\Get-MailboxForwardingAndAutoReply.ps1' -Context (New-Ctx 'M365.EXCHANGE.FORWARDING_AND_AUTO_REPLY' 'object_id' $oid $exoConn) -Parameters @{ IncludeAutoReplyCheck = $true; WarnOnExternalForwarding = $true } -CancellationToken $cts.Token
Assert-NativeOperationReturn $r14; $results['M365.EXCHANGE.FORWARDING_AND_AUTO_REPLY'] = $r14

$r15 = & 'C:\Dev\T-Notes\scripts\m365\exchange-online\mailbox-permissions\Get-MailboxPermissionsAudit.ps1' -Context (New-Ctx 'M365.EXCHANGE.MAILBOX_PERMISSIONS_AUDIT' 'object_id' $oid $exoConn) -Parameters @{ IncludeSendAsCheck = $true; MaxDelegates = 20 } -CancellationToken $cts.Token
Assert-NativeOperationReturn $r15; $results['M365.EXCHANGE.MAILBOX_PERMISSIONS_AUDIT'] = $r15

$r16 = & 'C:\Dev\T-Notes\scripts\m365\entra-id\password-account-posture\Get-PasswordAndAccountPosture.ps1' -Context (New-Ctx 'M365.ENTRA.PASSWORD_AND_ACCOUNT_POSTURE' 'upn' $upn $graphConn) -Parameters @{ PasswordAgeWarningDays = 90 } -CancellationToken $cts.Token
Assert-NativeOperationReturn $r16; $results['M365.ENTRA.PASSWORD_AND_ACCOUNT_POSTURE'] = $r16

$r17 = & 'C:\Dev\T-Notes\scripts\m365\entra-id\group-role-membership\Get-GroupAndRoleMembership.ps1' -Context (New-Ctx 'M365.ENTRA.GROUP_AND_ROLE_MEMBERSHIP' 'upn' $upn $graphConn) -Parameters @{ IncludeAdminRoles = $true; MaxGroups = 25 } -CancellationToken $cts.Token
Assert-NativeOperationReturn $r17; $results['M365.ENTRA.GROUP_AND_ROLE_MEMBERSHIP'] = $r17

$r18 = & 'C:\Dev\T-Notes\scripts\m365\security\legacy-auth-lockout\Get-LegacyAuthAndLockoutAudit.ps1' -Context (New-Ctx 'M365.SECURITY.LEGACY_AUTH_AND_LOCKOUT_AUDIT' 'object_id' $oid $graphConn) -Parameters @{ LookbackDays = 14; MaxRecords = 25 } -CancellationToken $cts.Token
Assert-NativeOperationReturn $r18; $results['M365.SECURITY.LEGACY_AUTH_AND_LOCKOUT_AUDIT'] = $r18

$r19 = & 'C:\Dev\T-Notes\scripts\m365\intune\device-inventory\Get-IntuneDeviceInventory.ps1' -Context (New-Ctx 'M365.INTUNE.DEVICE_INVENTORY_AND_OS_POSTURE' 'object_id' $oid $graphConn) -Parameters @{ LookbackDays = 14; MaxRecords = 25 } -CancellationToken $cts.Token
Assert-NativeOperationReturn $r19; $results['M365.INTUNE.DEVICE_INVENTORY_AND_OS_POSTURE'] = $r19

$r20 = & 'C:\Dev\T-Notes\scripts\m365\onedrive\client-sync-signins\Get-OneDriveClientSyncSignIns.ps1' -Context (New-Ctx 'M365.ONEDRIVE.CLIENT_SYNC_SIGNINS' 'object_id' $oid $graphConn) -Parameters @{ LookbackDays = 14; MaxRecords = 20 } -CancellationToken $cts.Token
Assert-NativeOperationReturn $r20; $results['M365.ONEDRIVE.CLIENT_SYNC_SIGNINS'] = $r20

$r21 = & 'C:\Dev\T-Notes\scripts\m365\sharepoint\external-guest-posture\Get-ExternalSharingAndGuestPosture.ps1' -Context (New-Ctx 'M365.SHAREPOINT.EXTERNAL_SHARING_AND_GUEST_POSTURE' 'upn' 'guest.partner_external.example#EXT#@contoso.onmicrosoft.com' $graphConn) -Parameters @{ WarnOnUnacceptedInvitation = $true } -CancellationToken $cts.Token
Assert-NativeOperationReturn $r21; $results['M365.SHAREPOINT.EXTERNAL_SHARING_AND_GUEST_POSTURE'] = $r21

# Empty-result live verification (no synthetic fallback)
function Get-MgUserLicenseDetail { param([string]$UserId, $ErrorAction) return @() }
function Get-MgAuditLogSignIn { param([string]$Filter, [int]$Top, [string[]]$Property, $ErrorAction) return @() }

$emptyLic = & 'C:\Dev\T-Notes\scripts\m365\licensing\service-plan-audit\Get-ServicePlanAudit.ps1' -Context (New-Ctx 'M365.LICENSING.SERVICE_PLAN_AUDIT' 'object_id' $oid $graphConn) -Parameters @{} -CancellationToken $cts.Token
Assert-NativeOperationReturn $emptyLic; $results['EMPTY_LIC'] = $emptyLic

$emptyRisk = & 'C:\Dev\T-Notes\scripts\m365\security\risky-signins\Get-SecurityRiskySignIns.ps1' -Context (New-Ctx 'M365.SECURITY.RISKY_SIGNIN_AUDIT' 'object_id' $oid $graphConn) -Parameters @{} -CancellationToken $cts.Token
Assert-NativeOperationReturn $emptyRisk; $results['EMPTY_RISK'] = $emptyRisk

$emptyLockout = & 'C:\Dev\T-Notes\scripts\m365\security\legacy-auth-lockout\Get-LegacyAuthAndLockoutAudit.ps1' -Context (New-Ctx 'M365.SECURITY.LEGACY_AUTH_AND_LOCKOUT_AUDIT' 'object_id' $oid $graphConn) -Parameters @{} -CancellationToken $cts.Token
Assert-NativeOperationReturn $emptyLockout; $results['EMPTY_LOCKOUT'] = $emptyLockout

$emptyOneDrive = & 'C:\Dev\T-Notes\scripts\m365\onedrive\client-sync-signins\Get-OneDriveClientSyncSignIns.ps1' -Context (New-Ctx 'M365.ONEDRIVE.CLIENT_SYNC_SIGNINS' 'object_id' $oid $graphConn) -Parameters @{} -CancellationToken $cts.Token
Assert-NativeOperationReturn $emptyOneDrive; $results['EMPTY_ONEDRIVE'] = $emptyOneDrive

ConvertTo-Json -InputObject $results -Depth 15 -Compress
"""
    proc = subprocess.run(
        [str(exec_service.pwsh_path), "-NoLogo", "-NoProfile", "-NonInteractive", "-Command", ps_script],
        capture_output=True,
        text=True,
        cwd=str(Path(__file__).resolve().parent.parent),
        timeout=45,
    )
    assert proc.returncode == 0, f"stderr: {proc.stderr}"
    parsed = json.loads(proc.stdout.strip())
    assert len(parsed) == 25

    schema_map = {
        "M365.GENERAL.TENANT_USER_OVERVIEW": "/$defs/user_identity",
        "M365.OTHER.UPN_SMTP_ALIGNMENT": "/$defs/user_identity",
        "M365.GENERAL.SERVICE_READINESS_AUDIT": "/$defs/user_licenses",
        "M365.LICENSING.SERVICE_PLAN_AUDIT": "/$defs/user_licenses",
        "M365.ONEDRIVE.SYNC_AND_STORAGE_DIAGNOSTIC": "/$defs/user_licenses",
        "M365.TEAMS.USER_READINESS": "/$defs/user_licenses",
        "M365.ENTRA.USER_MFA_AUDIT": "/$defs/user_signins",
        "M365.SECURITY.RISKY_SIGNIN_AUDIT": "/$defs/user_signins",
        "M365.TEAMS.CLIENT_SIGNINS": "/$defs/user_signins",
        "M365.INTUNE.COMPLIANCE_AND_ENROLLMENT": "/$defs/user_signins",
        "M365.REPORTS.USER_ACCESS_AUDIT_REPORT": "/$defs/user_signins",
        "M365.SHAREPOINT.ACCESS_DIAGNOSTIC": "/$defs/user_signins",
        "M365.EXCHANGE.MAILBOX_QUOTA_AND_HOLD": "/$defs/mailbox_summary",
        "M365.EXCHANGE.FORWARDING_AND_AUTO_REPLY": "/$defs/mailbox_summary",
        "M365.EXCHANGE.MAILBOX_PERMISSIONS_AUDIT": "/$defs/mailbox_summary",
        "M365.ENTRA.PASSWORD_AND_ACCOUNT_POSTURE": "/$defs/user_identity",
        "M365.ENTRA.GROUP_AND_ROLE_MEMBERSHIP": "/$defs/user_identity",
        "M365.SECURITY.LEGACY_AUTH_AND_LOCKOUT_AUDIT": "/$defs/user_signins",
        "M365.INTUNE.DEVICE_INVENTORY_AND_OS_POSTURE": "/$defs/user_signins",
        "M365.ONEDRIVE.CLIENT_SYNC_SIGNINS": "/$defs/user_signins",
        "M365.SHAREPOINT.EXTERNAL_SHARING_AND_GUEST_POSTURE": "/$defs/user_identity",
    }

    for sid, frag in schema_map.items():
        ret = parsed[sid]
        exec_service._validate_schema("common", ret, fragment="/$defs/operation_return")
        assert ret["status"] == "success", f"{sid} failed: {ret}"
        exec_service._validate_schema("operation-data", ret["data"], fragment=frag)

    assert any(w["code"] == "UPN_SMTP_DOMAIN_MISMATCH" for w in parsed["M365.OTHER.UPN_SMTP_ALIGNMENT"]["warnings"])
    assert any(w["code"] == "TELEMETRY_SCOPE" for w in parsed["M365.ONEDRIVE.SYNC_AND_STORAGE_DIAGNOSTIC"]["warnings"])
    assert any(w["code"] == "CONDITIONAL_ACCESS_FAILURE" for w in parsed["M365.ENTRA.USER_MFA_AUDIT"]["warnings"])
    assert any(w["code"] == "RISK_DETECTED" for w in parsed["M365.SECURITY.RISKY_SIGNIN_AUDIT"]["warnings"])
    assert parsed["M365.TEAMS.CLIENT_SIGNINS"]["data"]["returned_count"] == 1

    intune_warnings = {w["code"] for w in parsed["M365.INTUNE.COMPLIANCE_AND_ENROLLMENT"]["warnings"]}
    assert {"TELEMETRY_SCOPE", "NONCOMPLIANT_DEVICE_SIGNIN"}.issubset(intune_warnings)
    assert any(w["code"] == "AUDIT_SUMMARY" for w in parsed["M365.REPORTS.USER_ACCESS_AUDIT_REPORT"]["warnings"])
    assert parsed["M365.SHAREPOINT.ACCESS_DIAGNOSTIC"]["data"]["returned_count"] == 2

    exo_warnings = {w["code"] for w in parsed["M365.EXCHANGE.MAILBOX_QUOTA_AND_HOLD"]["warnings"]}
    assert {"HOLD_STATUS", "QUOTA_HIGH", "ARCHIVE_SUMMARY"}.issubset(exo_warnings)
    assert parsed["M365.EXCHANGE.MAILBOX_QUOTA_AND_HOLD"]["data"]["total_item_size_bytes"] == 49392123904
    assert parsed["M365.EXCHANGE.MAILBOX_QUOTA_AND_HOLD"]["data"]["prohibit_send_quota_bytes"] == 53687091200

    # Empty live tenant sets succeed with informational warnings and never fall back to synthetic data
    assert parsed["EMPTY_LIC"]["status"] == "success"
    assert parsed["EMPTY_LIC"]["data"]["returned_count"] == 0
    assert any(w["code"] == "NO_ACTIVE_LICENSES" for w in parsed["EMPTY_LIC"]["warnings"])

    assert parsed["EMPTY_RISK"]["status"] == "success"
    assert parsed["EMPTY_RISK"]["data"]["returned_count"] == 0
    assert any(w["code"] == "NO_RISKY_SIGNINS" for w in parsed["EMPTY_RISK"]["warnings"])

    assert parsed["EMPTY_LOCKOUT"]["status"] == "success"
    assert parsed["EMPTY_LOCKOUT"]["data"]["returned_count"] == 0
    assert any(w["code"] == "NO_LOCKOUT_OR_LEGACY_EVENTS" for w in parsed["EMPTY_LOCKOUT"]["warnings"])

    assert parsed["EMPTY_ONEDRIVE"]["status"] == "success"
    assert parsed["EMPTY_ONEDRIVE"]["data"]["returned_count"] == 0
    assert any(w["code"] == "NO_ONEDRIVE_SYNC_EVENTS" for w in parsed["EMPTY_ONEDRIVE"]["warnings"])

    # Structured warning checks for the 8 technician diagnostic scripts
    fwd_warnings = {w["code"] for w in parsed["M365.EXCHANGE.FORWARDING_AND_AUTO_REPLY"]["warnings"]}
    assert {"EXTERNAL_FORWARDING_ACTIVE", "AUTO_REPLY_STATUS", "GAL_VISIBILITY"}.issubset(fwd_warnings)

    perm_warnings = {w["code"] for w in parsed["M365.EXCHANGE.MAILBOX_PERMISSIONS_AUDIT"]["warnings"]}
    assert {"FULL_ACCESS_DELEGATES", "SEND_AS_DELEGATES", "SEND_ON_BEHALF_DELEGATES", "DELEGATE_AUDIT_SCOPE"}.issubset(perm_warnings)

    pwd_warnings = {w["code"] for w in parsed["M365.ENTRA.PASSWORD_AND_ACCOUNT_POSTURE"]["warnings"]}
    assert {"PASSWORD_AGE_SUMMARY", "PASSWORD_NEVER_EXPIRES", "HYBRID_SYNC_STATUS", "SESSION_REVOCATION_STATE"}.issubset(pwd_warnings)

    grp_warnings = {w["code"] for w in parsed["M365.ENTRA.GROUP_AND_ROLE_MEMBERSHIP"]["warnings"]}
    assert {"GROUP_MEMBERSHIP_SUMMARY", "ADMIN_ROLE_DETECTED", "MEMBERSHIP_TELEMETRY_SCOPE"}.issubset(grp_warnings)

    lock_warnings = {w["code"] for w in parsed["M365.SECURITY.LEGACY_AUTH_AND_LOCKOUT_AUDIT"]["warnings"]}
    assert {"SMART_LOCKOUT_DETECTED", "LEGACY_AUTH_DETECTED", "LOCKOUT_OR_FAILURE_SUMMARY"}.issubset(lock_warnings)

    dev_warnings = {w["code"] for w in parsed["M365.INTUNE.DEVICE_INVENTORY_AND_OS_POSTURE"]["warnings"]}
    assert {"DEVICE_INVENTORY_SUMMARY", "UNMANAGED_DEVICE_DETECTED", "NONCOMPLIANT_DEVICE_SIGNIN", "TELEMETRY_SCOPE"}.issubset(dev_warnings)

    od_warnings = {w["code"] for w in parsed["M365.ONEDRIVE.CLIENT_SYNC_SIGNINS"]["warnings"]}
    assert {"ONEDRIVE_SYNC_SUMMARY", "SYNC_AUTH_FAILURE"}.issubset(od_warnings)

    sp_warnings = {w["code"] for w in parsed["M365.SHAREPOINT.EXTERNAL_SHARING_AND_GUEST_POSTURE"]["warnings"]}
    assert {"EXTERNAL_GUEST_POSTURE", "GUEST_INVITATION_PENDING"}.issubset(sp_warnings)
    assert parsed["M365.SHAREPOINT.EXTERNAL_SHARING_AND_GUEST_POSTURE"]["data"]["user_type"] == "Guest"

