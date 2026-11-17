"""S2 & S3 tests: Offline synthetic M365 PowerShell operations and Launcher Run/Cancel/Results/History/Note insertion."""

from __future__ import annotations

import json
import threading
import time

import pytest
from PySide6.QtCore import Qt
from PySide6.QtTest import QTest

from src.services.m365_company_service import synthetic_directory
from src.services.m365_context_service import CompanyContextService
from src.services.m365_execution_service import (
    M365ExecutionService,
    build_synthetic_catalog_service,
)
from src.ui.components.editor import TechPadEditor
from src.ui.m365.launcher_widget import M365LauncherWidget


@pytest.fixture
def prepared_context():
    directory = synthetic_directory()
    ctx = CompanyContextService(directory)
    company = directory.search("Alpine")[0]
    ctx.select_company(company.company_id)
    ctx.connect_synthetic("Graph")
    ctx.connect_synthetic("ExchangeOnline")
    ctx.confirm_company()
    ctx.set_target("client@alpine.example")
    return ctx


@pytest.fixture
def exec_service(prepared_context):
    return M365ExecutionService(prepared_context, build_synthetic_catalog_service())


def test_s2_synthetic_catalog_loads_all_four_snapshot_operations():
    catalog = build_synthetic_catalog_service()
    assert not catalog.validation_errors
    expected_core_ids = {
        "M365.ENTRA.USER_IDENTITY",
        "M365.ENTRA.USER_LICENSES",
        "M365.ENTRA.USER_SIGNINS",
        "M365.EXCHANGE.MAILBOX_SUMMARY",
    }
    found = {
        op.id
        for cat in catalog.categories
        if cat.kind == "operations"
        for op in catalog.operations(cat.id)
    }
    assert expected_core_ids <= found
    assert {
        "M365.EXCHANGE.FORWARDING_AND_AUTO_REPLY",
        "M365.EXCHANGE.MAILBOX_PERMISSIONS_AUDIT",
        "M365.ENTRA.PASSWORD_AND_ACCOUNT_POSTURE",
        "M365.ENTRA.GROUP_AND_ROLE_MEMBERSHIP",
        "M365.SECURITY.LEGACY_AUTH_AND_LOCKOUT_AUDIT",
        "M365.INTUNE.DEVICE_INVENTORY_AND_OS_POSTURE",
        "M365.ONEDRIVE.CLIENT_SYNC_SIGNINS",
        "M365.SHAREPOINT.EXTERNAL_SHARING_AND_GUEST_POSTURE",
    } <= found
    assert len(found) == 25
    for cat in catalog.categories:
        if cat.kind == "operations":
            assert len(catalog.operations(cat.id)) >= 1, f"Category {cat.id} should have at least 1 script"


def test_s2_user_identity_success_partial_and_errors(exec_service, prepared_context):
    # 1. Standard UPN success
    outcome = exec_service.execute("M365.ENTRA.USER_IDENTITY")
    assert outcome.status == "success"
    assert outcome.operation_outcome == "succeeded"
    assert outcome.result_envelope["data"]["user_principal_name"] == "client@alpine.example"
    assert outcome.result_envelope["data"]["id"] == "40000000-0000-4000-8000-000000000001"
    assert outcome.result_envelope["data"]["account_enabled"] is True
    assert outcome.result_envelope["operation_exit_code"] == 0
    assert prepared_context.target is not None
    assert prepared_context.target.object_id == "40000000-0000-4000-8000-000000000001"

    # 2. Partial user (account_enabled is null -> PROPERTY_UNAVAILABLE warning)
    prepared_context.set_target("partial.user@alpine.example")
    partial_out = exec_service.execute("M365.ENTRA.USER_IDENTITY")
    assert partial_out.status == "partial"
    assert partial_out.operation_outcome == "partially_succeeded"
    assert partial_out.result_envelope["data"]["account_enabled"] is None
    assert partial_out.result_envelope["warnings"][0]["code"] == "PROPERTY_UNAVAILABLE"
    assert partial_out.result_envelope["operation_exit_code"] == 2

    # 3. Missing user -> TARGET_NOT_FOUND
    prepared_context.set_target("missing@alpine.example")
    not_found = exec_service.execute("M365.ENTRA.USER_IDENTITY")
    assert not_found.status == "error"
    assert not_found.result_envelope["errors"][0]["code"] == "TARGET_NOT_FOUND"
    assert not_found.result_envelope["operation_exit_code"] == 30

    # 4. Denied user -> ACCESS_DENIED
    prepared_context.set_target("denied@alpine.example")
    denied = exec_service.execute("M365.ENTRA.USER_IDENTITY")
    assert denied.status == "error"
    assert denied.result_envelope["errors"][0]["code"] == "ACCESS_DENIED"
    assert denied.result_envelope["operation_exit_code"] == 20


def test_s2_follow_on_operations_require_resolved_identity_and_succeed(exec_service, prepared_context):
    # Before resolving identity, follow-on operation must fail closed with AUTH_REQUIRED
    assert prepared_context.target is None
    blocked = exec_service.execute("M365.ENTRA.USER_LICENSES")
    assert blocked.status == "error"
    assert blocked.result_envelope["errors"][0]["code"] == "AUTH_REQUIRED"

    # Resolve identity via Get-UserIdentity
    id_out = exec_service.execute("M365.ENTRA.USER_IDENTITY")
    assert id_out.status == "success"

    # 1. Licenses
    lic_out = exec_service.execute("M365.ENTRA.USER_LICENSES")
    assert lic_out.status == "success"
    assert lic_out.result_envelope["data"]["target_user_id"] == "40000000-0000-4000-8000-000000000001"
    assert lic_out.result_envelope["data"]["returned_count"] == 1
    assert lic_out.result_envelope["data"]["licenses"][0]["sku_part_number"] == "ENTERPRISEPACK"

    # 2. Sign-ins (default parameters LookbackDays=7, MaxRecords=20)
    sign_out = exec_service.execute("M365.ENTRA.USER_SIGNINS")
    assert sign_out.status == "success"
    assert sign_out.result_envelope["data"]["returned_count"] == 2
    assert sign_out.result_envelope["data"]["truncated"] is False

    # 3. Sign-ins truncated at MaxRecords=1 -> partial with OUTPUT_LIMIT warning
    trunc_out = exec_service.execute("M365.ENTRA.USER_SIGNINS", {"LookbackDays": 14, "MaxRecords": 1})
    assert trunc_out.status == "partial"
    assert trunc_out.result_envelope["data"]["returned_count"] == 1
    assert trunc_out.result_envelope["data"]["truncated"] is True
    assert trunc_out.result_envelope["warnings"][0]["code"] == "OUTPUT_LIMIT"

    # 4. Invalid parameter rejected before worker
    bad_param = exec_service.execute("M365.ENTRA.USER_SIGNINS", {"LookbackDays": 99})
    assert bad_param.status == "error"
    assert bad_param.result_envelope["errors"][0]["code"] == "INVALID_PARAMETER"

    # 5. Mailbox Summary
    mbx_out = exec_service.execute("M365.EXCHANGE.MAILBOX_SUMMARY")
    assert mbx_out.status == "success"
    assert mbx_out.result_envelope["data"]["mailbox_exists"] is True
    assert mbx_out.result_envelope["data"]["recipient_type_details"] == "UserMailbox"
    assert mbx_out.result_envelope["data"]["primary_smtp_address"] == "client@alpine.example"


def test_s2_cooperative_cancellation(exec_service, prepared_context):
    prepared_context.set_target("slow@alpine.example")
    cancel_event = threading.Event()

    def trigger_cancel():
        time.sleep(0.15)
        cancel_event.set()

    outcome = exec_service.execute(
        "M365.ENTRA.USER_IDENTITY",
        cancellation=cancel_event,
        on_started=lambda: threading.Thread(target=trigger_cancel, daemon=True).start(),
    )
    assert outcome.status == "cancelled"
    assert outcome.result_envelope["errors"][0]["code"] == "CANCELLED"
    assert outcome.result_envelope["operation_exit_code"] == 40
    assert outcome.history_record["status"] == "cancelled"


def test_s3_launcher_gui_run_results_history_and_safe_ticket_insertion(qapp):
    launcher = M365LauncherWidget(synthetic_mode=False)
    editor = TechPadEditor(scratchpad_id=101, image_service=None)
    editor.setPlainText("Initial ticket troubleshooting note.")
    launcher.set_active_ticket(
        editor,
        ticket_data={"ticket_number": "INC-101", "client_name": "Alpine Health", "title": "User sign-in issue"},
    )
    try:
        launcher.resize(1024, 640)
        launcher.show()
        qapp.processEvents()

        # Click Load Synthetic Snapshot button
        QTest.mouseClick(launcher.btn_load_synthetic_catalog, Qt.LeftButton)
        qapp.processEvents()

        # Select company, connect Graph & Exchange, confirm company, and enter target UPN
        launcher.company_panel.company_combo.setCurrentIndex(1)
        qapp.processEvents()
        QTest.mouseClick(launcher.company_panel.graph_button, Qt.LeftButton)
        QTest.mouseClick(launcher.company_panel.exchange_button, Qt.LeftButton)
        QTest.mouseClick(launcher.company_panel.confirm_button, Qt.LeftButton)
        launcher.company_panel.target_upn.setText("client@alpine.example")
        qapp.processEvents()

        # Navigate to Entra ID category (index 3)
        launcher.navigation.setCurrentRow(3)
        qapp.processEvents()
        assert launcher.operation_list.count() == 6  # Identity, SignIns, MFA, Password Posture, Group/Role, Lockout/Legacy

        # Select Get-UserIdentity and click Run
        for i in range(launcher.operation_list.count()):
            if launcher.operation_list.item(i).data(Qt.UserRole) == "M365.ENTRA.USER_IDENTITY":
                launcher.operation_list.setCurrentRow(i)
                break
        qapp.processEvents()
        assert launcher.btn_run_operation.isEnabled()

        QTest.mouseClick(launcher.btn_run_operation, Qt.LeftButton)
        qapp.processEvents()

        assert launcher.history_list.count() == 1
        assert "M365.ENTRA.USER_IDENTITY" in launcher.results_output.toPlainText()
        assert "client@alpine.example" in launcher.results_output.toPlainText()
        assert launcher.btn_insert_into_ticket.isEnabled()

        # Toggle Raw JSON view and back to Summary View
        QTest.mouseClick(launcher.btn_toggle_json, Qt.LeftButton)
        qapp.processEvents()
        parsed_json = json.loads(launcher.results_output.toPlainText())
        assert parsed_json["script_id"] == "M365.ENTRA.USER_IDENTITY"
        assert parsed_json["status"] == "success"

        QTest.mouseClick(launcher.btn_toggle_json, Qt.LeftButton)
        qapp.processEvents()
        assert "=== M365 Diagnostic Snapshot:" in launcher.results_output.toPlainText()

        # Insert into Active Ticket (single-use preview token)
        QTest.mouseClick(launcher.btn_insert_into_ticket, Qt.LeftButton)
        qapp.processEvents()
        assert "M365.ENTRA.USER_IDENTITY" in editor.toPlainText()
        assert not launcher.btn_insert_into_ticket.isEnabled()
        assert not launcher.insert_current_result_into_ticket()

        # Select Get-UserSignIns, adjust LookbackDays parameter spinbox, and run
        for i in range(launcher.operation_list.count()):
            if launcher.operation_list.item(i).data(Qt.UserRole) == "M365.ENTRA.USER_SIGNINS":
                launcher.operation_list.setCurrentRow(i)
                break
        qapp.processEvents()
        assert "LookbackDays" in launcher._parameter_widgets
        assert "MaxRecords" in launcher._parameter_widgets
        launcher._parameter_widgets["LookbackDays"][1].setValue(14)
        launcher._parameter_widgets["MaxRecords"][1].setValue(10)

        QTest.mouseClick(launcher.btn_run_operation, Qt.LeftButton)
        qapp.processEvents()
        assert launcher.history_list.count() == 2
        assert "M365.ENTRA.USER_SIGNINS" in launcher.results_output.toPlainText()

        # Switching company invalidates note insertion for the old company's result
        launcher.company_panel.company_combo.setCurrentIndex(2)
        qapp.processEvents()
        assert not launcher.insert_current_result_into_ticket()
        assert "changed" in launcher.lbl_results_notice.text().lower()

        # Clear history
        QTest.mouseClick(launcher.btn_clear_history, Qt.LeftButton)
        qapp.processEvents()
        assert launcher.history_list.count() == 0
    finally:
        launcher.close()
        launcher.deleteLater()
        editor.deleteLater()
        qapp.processEvents()


def test_s2_mocked_provider_cmdlets_for_all_four_scripts(exec_service):
    """Execute all 4 PowerShell scripts against mocked Graph/Exchange cmdlets inside PowerShell 7."""
    import subprocess
    from src.services.m365_catalog_service import ROOT

    ps_test_script = r"""
$ErrorActionPreference = 'Stop'
. 'C:\Dev\T-Notes\prototypes\m365_official_engine\protocol.ps1'
Initialize-NativeReturnValidation

$cts = [System.Threading.CancellationTokenSource]::new()
$emptyParams = Freeze-Value @{}
$baseConnGraph = @{
    connection_id = 'conn-graph-mock-1'
    service = 'Graph'
    state = 'verified'
    tenant_id = '20000000-0000-4000-8000-000000000001'
    verified_account_upn = 'admin@alpine.example'
    graph_scopes = @('User.Read.All', 'LicenseAssignment.Read.All', 'AuditLog.Read.All')
    effective_roles = @('Directory.Readers', 'Reports.Reader')
    owner_worker_id = 'test-worker-1'
    verified_at = '2026-11-17T00:00:00Z'
    expires_at = $null
}
$baseConnExo = @{
    connection_id = 'conn-exo-mock-1'
    service = 'ExchangeOnline'
    state = 'verified'
    tenant_id = '20000000-0000-4000-8000-000000000001'
    verified_account_upn = 'admin@alpine.example'
    graph_scopes = @()
    effective_roles = @('cmdlet.Get-EXOMailbox', 'cmdlet.Get-EXOMailboxStatistics')
    owner_worker_id = 'test-worker-1'
    verified_at = '2026-11-17T00:00:00Z'
    expires_at = $null
}

# 1. Mock Get-MgUser
function Get-MgUser {
    param([string]$UserId, [string[]]$Property, $ErrorAction)
    return [pscustomobject]@{
        Id = '40000000-0000-4000-8000-000000000001'
        DisplayName = 'Mocked Graph User'
        UserPrincipalName = $UserId
        AccountEnabled = $true
        UserType = 'Member'
    }
}
$ctx1 = Freeze-Value @{
    contract_version = '0.3.0'
    script_id = 'M365.ENTRA.USER_IDENTITY'
    company_id = 'alpine-ski-house'
    correlation_id = 'corr-s2-1'
    tenant_id = '20000000-0000-4000-8000-000000000001'
    admin_identity_ref = 'admin@alpine.example'
    verified_account_upn = 'admin@alpine.example'
    session_generation = [long]1
    ticket_context = $null
    target = @{ kind = 'upn'; value = 'client@alpine.example' }
    connections = @($baseConnGraph)
}
$res1 = & 'C:\Dev\T-Notes\scripts\m365\entra-id\user-identity\Get-UserIdentity.ps1' -Context $ctx1 -Parameters $emptyParams -CancellationToken $cts.Token
Assert-NativeOperationReturn $res1
if ($res1.status -ne 'success' -or $res1.data.display_name -ne 'Mocked Graph User') { throw 'Identity mock failed' }

# 2. Mock Get-MgUserLicenseDetail
function Get-MgUserLicenseDetail {
    param([string]$UserId, [string[]]$Property, $ErrorAction)
    return @(
        [pscustomobject]@{
            Id = 'lic-1'
            SkuId = '6fd2c87f-b296-42f0-b197-1e91e994b900'
            SkuPartNumber = 'SPE_E5'
            ServicePlans = @(
                [pscustomobject]@{
                    ServicePlanId = 'efb87545-963c-4e0d-99df-69c6916d9eb0'
                    ServicePlanName = 'EXCHANGE_S_ENTERPRISE'
                    ProvisioningStatus = 'Success'
                }
            )
        }
    )
}
$ctx2 = Freeze-Value @{
    contract_version = '0.3.0'
    script_id = 'M365.ENTRA.USER_LICENSES'
    company_id = 'alpine-ski-house'
    correlation_id = 'corr-s2-2'
    tenant_id = '20000000-0000-4000-8000-000000000001'
    admin_identity_ref = 'admin@alpine.example'
    verified_account_upn = 'admin@alpine.example'
    session_generation = [long]1
    ticket_context = $null
    target = @{ kind = 'object_id'; value = '40000000-0000-4000-8000-000000000001' }
    connections = @($baseConnGraph)
}
$res2 = & 'C:\Dev\T-Notes\scripts\m365\licensing\user-licenses\Get-UserLicenses.ps1' -Context $ctx2 -Parameters $emptyParams -CancellationToken $cts.Token
Assert-NativeOperationReturn $res2
if ($res2.status -ne 'success' -or $res2.data.licenses[0].sku_part_number -ne 'SPE_E5') { throw 'Licenses mock failed' }

# 3. Mock Get-MgAuditLogSignIn
function Get-MgAuditLogSignIn {
    param([string]$Filter, [int]$Top, [string[]]$Property, $ErrorAction)
    return @(
        [pscustomobject]@{
            Id = 'ev-1'
            UserId = '40000000-0000-4000-8000-000000000001'
            CreatedDateTime = [datetime]::UtcNow.AddMinutes(-15)
            AppDisplayName = 'Azure Portal'
            Status = [pscustomobject]@{ ErrorCode = 0 }
        }
    )
}
$ctx3 = Freeze-Value @{
    contract_version = '0.3.0'
    script_id = 'M365.ENTRA.USER_SIGNINS'
    company_id = 'alpine-ski-house'
    correlation_id = 'corr-s2-3'
    tenant_id = '20000000-0000-4000-8000-000000000001'
    admin_identity_ref = 'admin@alpine.example'
    verified_account_upn = 'admin@alpine.example'
    session_generation = [long]1
    ticket_context = $null
    target = @{ kind = 'object_id'; value = '40000000-0000-4000-8000-000000000001' }
    connections = @($baseConnGraph)
}
$res3 = & 'C:\Dev\T-Notes\scripts\m365\entra-id\user-signins\Get-UserSignIns.ps1' -Context $ctx3 -Parameters (Freeze-Value @{ LookbackDays = 7; MaxRecords = 10 }) -CancellationToken $cts.Token
Assert-NativeOperationReturn $res3
if ($res3.status -ne 'success' -or $res3.data.events[0].app_display_name -ne 'Azure Portal') { throw 'SignIns mock failed' }

# 4. Mock Get-EXOMailbox & Get-EXOMailboxStatistics
function Get-EXOMailbox {
    param([guid]$ExternalDirectoryObjectId, [string[]]$Properties, $ErrorAction)
    return [pscustomobject]@{
        ExternalDirectoryObjectId = $ExternalDirectoryObjectId.ToString()
        ExchangeGuid = '99999999-9999-4999-8999-999999999999'
        RecipientTypeDetails = 'SharedMailbox'
        PrimarySmtpAddress = 'shared@alpine.example'
        ProhibitSendQuota = [pscustomobject]@{
            Value = [pscustomobject]@{} | Add-Member -MemberType ScriptMethod -Name ToBytes -Value { return [long]4096 } -PassThru
        }
    }
}
function Get-EXOMailboxStatistics {
    param([string]$Identity, [string[]]$Properties, $ErrorAction)
    return [pscustomobject]@{
        TotalItemSize = [pscustomobject]@{
            Value = [pscustomobject]@{} | Add-Member -MemberType ScriptMethod -Name ToBytes -Value { return [long]2048 } -PassThru
        }
    }
}
$ctx4 = Freeze-Value @{
    contract_version = '0.3.0'
    script_id = 'M365.EXCHANGE.MAILBOX_SUMMARY'
    company_id = 'alpine-ski-house'
    correlation_id = 'corr-s2-4'
    tenant_id = '20000000-0000-4000-8000-000000000001'
    admin_identity_ref = 'admin@alpine.example'
    verified_account_upn = 'admin@alpine.example'
    session_generation = [long]1
    ticket_context = $null
    target = @{ kind = 'object_id'; value = '40000000-0000-4000-8000-000000000001' }
    connections = @($baseConnExo)
}
$res4 = & 'C:\Dev\T-Notes\scripts\m365\exchange-online\mailbox-summary\Get-MailboxSummary.ps1' -Context $ctx4 -Parameters $emptyParams -CancellationToken $cts.Token
Assert-NativeOperationReturn $res4
if ($res4.status -ne 'success' -or $res4.data.total_item_size_bytes -ne 2048 -or $res4.data.prohibit_send_quota_bytes -ne 4096) { throw 'Mailbox mock failed' }
Write-Output 'ALL_MOCKS_PASSED'
"""
    proc = subprocess.run(
        [str(exec_service.pwsh_path), "-NoLogo", "-NoProfile", "-NonInteractive", "-Command", ps_test_script],
        capture_output=True,
        text=True,
        cwd=str(ROOT),
        timeout=30,
    )
    assert proc.returncode == 0, f"stderr: {proc.stderr}"
    assert "ALL_MOCKS_PASSED" in proc.stdout


def test_s3_launcher_help_button_and_user_guide_dialog(qapp):
    widget = M365LauncherWidget(synthetic_mode=True)
    widget.resize(1100, 800)
    widget.show()
    qapp.processEvents()
    try:
        assert widget.btn_help.isVisible() and widget.btn_help.isEnabled()
        assert widget.btn_help.text() == "?"
        assert widget.btn_help.accessibleName() == "M365 PowerShell Launcher Help"
        assert "M365 PowerShell Launcher" in widget.btn_help.toolTip()
        assert widget.help_dialog is None

        QTest.mouseClick(widget.btn_help, Qt.LeftButton)
        qapp.processEvents()

        assert widget.help_dialog is not None
        assert widget.help_dialog.isVisible()
        guide_text = widget.help_dialog.help_browser.toPlainText()
        assert "Load the Script Catalog" in guide_text
        assert "Company Selection & Tenant Confirmation" in guide_text
        assert "Authentication & Target Identity" in guide_text
        assert "Browse Script Catalog & Configure Parameters" in guide_text
        assert "Run, Cancel & Session Execution History" in guide_text
        assert "Inspect Results & Insert into Active Ticket" in guide_text
        assert "client@alpine.example" in guide_text
        assert "partial.user@alpine.example" in guide_text
        assert "missing@alpine.example" in guide_text
        assert "denied@alpine.example" in guide_text

        QTest.mouseClick(widget.help_dialog.btn_close, Qt.LeftButton)
        qapp.processEvents()
        assert not widget.help_dialog.isVisible()
    finally:
        widget.close()
        widget.deleteLater()
        qapp.processEvents()


def test_s3_all_categories_separated_and_executable(qapp):
    widget = M365LauncherWidget(synthetic_mode=True)
    widget.resize(1100, 800)
    widget.show()
    qapp.processEvents()
    try:
        # 1. Verify Quick Setup configures context in one click
        assert widget.quick_setup_context() is True
        assert widget.context_service.confirmed_company is not None
        assert widget.context_service.target is not None

        # 2. Verify each of the 14 categories updates the separated category function card
        badges_seen = set()
        for row in range(widget.navigation.count()):
            widget.navigation.setCurrentRow(row)
            qapp.processEvents()
            cat_id = widget.current_category_id
            assert widget.category_function_card.isVisible()
            badge_text = widget.lbl_category_badge.text()
            assert badge_text
            badges_seen.add((cat_id, badge_text))
            if cat_id == "workflows":
                assert widget.btn_cat_secondary_action.isVisible()
                assert widget.btn_cat_tertiary_action.isVisible()
                assert widget.btn_cat_quaternary_action.isVisible()
                assert widget.btn_cat_quinary_action.isVisible()
            else:
                assert not widget.btn_cat_secondary_action.isVisible()
                assert not widget.btn_cat_quaternary_action.isVisible()
                assert not widget.btn_cat_quinary_action.isVisible()

        assert len(badges_seen) == 14

        # 3. Execute a category primary action on a newly added service category (e.g., Teams)
        teams_row = [widget.navigation.item(i).data(Qt.UserRole) for i in range(14)].index("teams")
        widget.navigation.setCurrentRow(teams_row)
        qapp.processEvents()
        teams_outcomes = widget.run_category_primary_action()
        assert len(teams_outcomes) == 2
        assert all(o.status == "success" for o in teams_outcomes)

        # 4. Execute Security Triage, Mailbox & Delivery Triage, and Lockout Triage guided workflows
        sec_outcomes = widget.run_guided_workflow("security_triage")
        assert len(sec_outcomes) == 3
        assert all(o.status == "success" for o in sec_outcomes)
        assert "Security & Access Incident Triage" in widget.results_output.toPlainText()

        mbx_outcomes = widget.run_guided_workflow("mailbox_delivery_triage")
        assert len(mbx_outcomes) == 4
        assert all(o.status == "success" for o in mbx_outcomes)
        assert "Mailbox & Delivery Triage" in widget.results_output.toPlainText()

        lock_outcomes = widget.run_guided_workflow("lockout_and_auth_triage")
        assert len(lock_outcomes) == 4
        assert all(o.status == "success" for o in lock_outcomes)
        assert "Account Lockout & Auth Triage" in widget.results_output.toPlainText()

        # 5. Verify Script Catalog groupbox is larger than Parameters groupbox and Parameters has no wasted vertical gap
        catalog_group = widget._content_groups[2]
        params_group = widget._content_groups[3]
        auth_group = widget._content_groups[1]
        results_group = widget._content_groups[5]
        assert catalog_group.width() > params_group.width()
        assert catalog_group.height() > params_group.height()
        # Verify Parameters sits directly below Authentication & Tenant Context and directly above Parsed Results
        assert params_group.geometry().top() - auth_group.geometry().bottom() <= 16
        assert results_group.geometry().top() - params_group.geometry().bottom() <= 16
    finally:
        widget.close()
        widget.deleteLater()
        qapp.processEvents()


def test_technician_8_operations_synthetic_execution(exec_service, prepared_context):
    """Verify all 8 newly added IT technician diagnostic scripts pass contract & parameter checks in synthetic mode."""
    prepared_context.set_target("", "40000000-0000-4000-8000-000000000003")
    prepared_context.resolve_synthetic()

    fwd = exec_service.execute(
        "M365.EXCHANGE.FORWARDING_AND_AUTO_REPLY",
        {"IncludeAutoReplyCheck": True, "WarnOnExternalForwarding": True},
    )
    assert fwd.status == "success"
    fwd_codes = {w["code"] for w in fwd.result_envelope["warnings"]}
    assert {"EXTERNAL_FORWARDING_ACTIVE", "AUTO_REPLY_STATUS", "GAL_VISIBILITY"}.issubset(fwd_codes)

    perms = exec_service.execute(
        "M365.EXCHANGE.MAILBOX_PERMISSIONS_AUDIT",
        {"IncludeSendAsCheck": True, "MaxDelegates": 10},
    )
    assert perms.status == "success"
    perms_codes = {w["code"] for w in perms.result_envelope["warnings"]}
    assert {"FULL_ACCESS_DELEGATES", "SEND_AS_DELEGATES", "SEND_ON_BEHALF_DELEGATES", "DELEGATE_AUDIT_SCOPE"}.issubset(perms_codes)

    pwd = exec_service.execute(
        "M365.ENTRA.PASSWORD_AND_ACCOUNT_POSTURE",
        {"PasswordAgeWarningDays": 90},
    )
    assert pwd.status == "success"
    pwd_codes = {w["code"] for w in pwd.result_envelope["warnings"]}
    assert {"PASSWORD_AGE_SUMMARY", "PASSWORD_NEVER_EXPIRES", "HYBRID_SYNC_STATUS", "SESSION_REVOCATION_STATE"}.issubset(pwd_codes)

    grp = exec_service.execute(
        "M365.ENTRA.GROUP_AND_ROLE_MEMBERSHIP",
        {"IncludeAdminRoles": True, "MaxGroups": 15},
    )
    assert grp.status == "success"
    grp_codes = {w["code"] for w in grp.result_envelope["warnings"]}
    assert {"GROUP_MEMBERSHIP_SUMMARY", "ADMIN_ROLE_DETECTED", "MEMBERSHIP_TELEMETRY_SCOPE"}.issubset(grp_codes)

    lock = exec_service.execute(
        "M365.SECURITY.LEGACY_AUTH_AND_LOCKOUT_AUDIT",
        {"LookbackDays": 14, "MaxRecords": 25},
    )
    assert lock.status == "success"
    lock_codes = {w["code"] for w in lock.result_envelope["warnings"]}
    assert {"SMART_LOCKOUT_DETECTED", "LEGACY_AUTH_DETECTED", "LOCKOUT_OR_FAILURE_SUMMARY"}.issubset(lock_codes)

    dev = exec_service.execute(
        "M365.INTUNE.DEVICE_INVENTORY_AND_OS_POSTURE",
        {"LookbackDays": 14, "MaxRecords": 25},
    )
    assert dev.status == "success"
    dev_codes = {w["code"] for w in dev.result_envelope["warnings"]}
    assert {"DEVICE_INVENTORY_SUMMARY", "UNMANAGED_DEVICE_DETECTED", "NONCOMPLIANT_DEVICE_SIGNIN", "TELEMETRY_SCOPE"}.issubset(dev_codes)

    od = exec_service.execute(
        "M365.ONEDRIVE.CLIENT_SYNC_SIGNINS",
        {"LookbackDays": 14, "MaxRecords": 20},
    )
    assert od.status == "success"
    assert any(w["code"] == "ONEDRIVE_SYNC_SUMMARY" for w in od.result_envelope["warnings"])

    prepared_context.set_target("guest.partner_external#EXT#@alpine.example", "")
    prepared_context.resolve_synthetic()
    sp = exec_service.execute(
        "M365.SHAREPOINT.EXTERNAL_SHARING_AND_GUEST_POSTURE",
        {"WarnOnUnacceptedInvitation": True},
    )
    assert sp.status == "success"
    sp_codes = {w["code"] for w in sp.result_envelope["warnings"]}
    assert {"EXTERNAL_GUEST_POSTURE", "GUEST_INVITATION_PENDING"}.issubset(sp_codes)





