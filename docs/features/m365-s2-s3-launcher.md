# M365 S2 & S3 — Offline Synthetic Snapshot Operations & Functional Launcher

Status: **OFFLINE SYNTHETIC IMPLEMENTATION CANDIDATE — INDEPENDENT REVIEW REQUIRED**
Contract Baseline: `tnotes.m365 / 0.3.0`

## 1. S2 — Offline Synthetic PowerShell Operations Across All Categories (`scripts/m365/`)

Twenty-five independent PowerShell 7 operation scripts implement diagnostics across all 11 operation categories (`general`, `entra-id`, `exchange-online`, `licensing`, `teams`, `sharepoint`, `onedrive`, `intune`, `security`, `reports`, `other`) under `scripts/m365/` against the `tnotes.m365 / 0.3.0` Normative Callable ABI v1 (`[CmdletBinding()]` with `[System.Collections.Generic.IReadOnlyDictionary[string, object]]$Context`, `$Parameters`, and `[System.Threading.CancellationToken]$CancellationToken`):

| Script ID | Script Path | Category | Required Connection | Accepted Target Kinds | Output Schema Fragment |
| :--- | :--- | :--- | :--- | :--- | :--- |
| `M365.GENERAL.TENANT_USER_OVERVIEW` | `scripts/m365/general/tenant-user-overview/Get-TenantUserOverview.ps1` | `general` | `Graph` (`User.Read.All`) | `upn`, `object_id` | `#/$defs/user_identity` |
| `M365.GENERAL.SERVICE_READINESS_AUDIT` | `scripts/m365/general/service-readiness/Get-ServiceReadinessAudit.ps1` | `general` | `Graph` (`LicenseAssignment.Read.All`, `User.Read.All`) | `object_id` | `#/$defs/user_licenses` |
| `M365.ENTRA.USER_IDENTITY` | `scripts/m365/entra-id/user-identity/Get-UserIdentity.ps1` | `entra-id` | `Graph` (`User.Read.All`) | `upn`, `object_id` | `#/$defs/user_identity` |
| `M365.ENTRA.USER_SIGNINS` | `scripts/m365/entra-id/user-signins/Get-UserSignIns.ps1` | `entra-id` | `Graph` (`AuditLog.Read.All`, role `Reports.Reader`) | `object_id` | `#/$defs/user_signins` |
| `M365.ENTRA.USER_MFA_AUDIT` | `scripts/m365/entra-id/user-mfa-audit/Get-UserMfaAudit.ps1` | `entra-id`, `security` | `Graph` (`AuditLog.Read.All`) | `object_id` | `#/$defs/user_signins` |
| `M365.ENTRA.PASSWORD_AND_ACCOUNT_POSTURE` | `scripts/m365/entra-id/password-account-posture/Get-PasswordAndAccountPosture.ps1` | `entra-id` | `Graph` (`User.Read.All`) | `upn`, `object_id` | `#/$defs/user_identity` |
| `M365.ENTRA.GROUP_AND_ROLE_MEMBERSHIP` | `scripts/m365/entra-id/group-role-membership/Get-GroupAndRoleMembership.ps1` | `entra-id`, `security` | `Graph` (`User.Read.All`) | `upn`, `object_id` | `#/$defs/user_identity` |
| `M365.EXCHANGE.MAILBOX_SUMMARY` | `scripts/m365/exchange-online/mailbox-summary/Get-MailboxSummary.ps1` | `exchange-online` | `ExchangeOnline` (`cmdlet.Get-EXOMailbox`, `cmdlet.Get-EXOMailboxStatistics`) | `object_id` | `#/$defs/mailbox_summary` |
| `M365.EXCHANGE.MAILBOX_QUOTA_AND_HOLD` | `scripts/m365/exchange-online/mailbox-quota-hold/Get-MailboxQuotaAndHold.ps1` | `exchange-online` | `ExchangeOnline` (`cmdlet.Get-EXOMailbox` + `cmdlet.Get-EXOMailboxStatistics`, or `View-Only.Recipients`) | `object_id` | `#/$defs/mailbox_summary` |
| `M365.EXCHANGE.FORWARDING_AND_AUTO_REPLY` | `scripts/m365/exchange-online/forwarding-auto-reply/Get-MailboxForwardingAndAutoReply.ps1` | `exchange-online` | `ExchangeOnline` (`cmdlet.Get-EXOMailbox`, `cmdlet.Get-EXOMailboxStatistics`, optional `Get-MailboxAutoReplyConfiguration`) | `object_id` | `#/$defs/mailbox_summary` |
| `M365.EXCHANGE.MAILBOX_PERMISSIONS_AUDIT` | `scripts/m365/exchange-online/mailbox-permissions/Get-MailboxPermissionsAudit.ps1` | `exchange-online` | `ExchangeOnline` (`cmdlet.Get-EXOMailbox`, `cmdlet.Get-EXOMailboxStatistics`, optional `Get-EXOMailboxPermission`, `Get-EXORecipientPermission`) | `object_id` | `#/$defs/mailbox_summary` |
| `M365.ENTRA.USER_LICENSES` | `scripts/m365/licensing/user-licenses/Get-UserLicenses.ps1` | `licensing` | `Graph` (`LicenseAssignment.Read.All`, role `Directory.Readers`) | `object_id` | `#/$defs/user_licenses` |
| `M365.LICENSING.SERVICE_PLAN_AUDIT` | `scripts/m365/licensing/service-plan-audit/Get-ServicePlanAudit.ps1` | `licensing` | `Graph` (`LicenseAssignment.Read.All`, `User.Read.All`) | `object_id` | `#/$defs/user_licenses` |
| `M365.TEAMS.USER_READINESS` | `scripts/m365/teams/user-readiness/Get-TeamsUserReadiness.ps1` | `teams` | `Graph` (`LicenseAssignment.Read.All`, `User.Read.All`) | `object_id` | `#/$defs/user_licenses` |
| `M365.TEAMS.CLIENT_SIGNINS` | `scripts/m365/teams/client-signins/Get-TeamsClientSignIns.ps1` | `teams` | `Graph` (`AuditLog.Read.All`) | `object_id` | `#/$defs/user_signins` |
| `M365.SHAREPOINT.ACCESS_DIAGNOSTIC` | `scripts/m365/sharepoint/access-diagnostic/Get-SharePointAccessDiagnostic.ps1` | `sharepoint` | `Graph` (`AuditLog.Read.All`) | `object_id` | `#/$defs/user_signins` |
| `M365.SHAREPOINT.EXTERNAL_SHARING_AND_GUEST_POSTURE` | `scripts/m365/sharepoint/external-guest-posture/Get-ExternalSharingAndGuestPosture.ps1` | `sharepoint`, `other` | `Graph` (`User.Read.All`) | `upn`, `object_id` | `#/$defs/user_identity` |
| `M365.ONEDRIVE.SYNC_AND_STORAGE_DIAGNOSTIC` | `scripts/m365/onedrive/sync-diagnostic/Get-OneDriveSyncDiagnostic.ps1` | `onedrive` | `Graph` (`LicenseAssignment.Read.All`, `User.Read.All`) | `object_id` | `#/$defs/user_licenses` |
| `M365.ONEDRIVE.CLIENT_SYNC_SIGNINS` | `scripts/m365/onedrive/client-sync-signins/Get-OneDriveClientSyncSignIns.ps1` | `onedrive` | `Graph` (`AuditLog.Read.All`) | `object_id` | `#/$defs/user_signins` |
| `M365.INTUNE.COMPLIANCE_AND_ENROLLMENT` | `scripts/m365/intune/compliance-enrollment/Get-IntuneComplianceDiagnostic.ps1` | `intune` | `Graph` (`AuditLog.Read.All`) | `object_id` | `#/$defs/user_signins` |
| `M365.INTUNE.DEVICE_INVENTORY_AND_OS_POSTURE` | `scripts/m365/intune/device-inventory/Get-IntuneDeviceInventory.ps1` | `intune` | `Graph` (`AuditLog.Read.All`) | `object_id` | `#/$defs/user_signins` |
| `M365.SECURITY.RISKY_SIGNIN_AUDIT` | `scripts/m365/security/risky-signins/Get-SecurityRiskySignIns.ps1` | `security` | `Graph` (`AuditLog.Read.All`) | `object_id` | `#/$defs/user_signins` |
| `M365.SECURITY.LEGACY_AUTH_AND_LOCKOUT_AUDIT` | `scripts/m365/security/legacy-auth-lockout/Get-LegacyAuthAndLockoutAudit.ps1` | `security`, `entra-id` | `Graph` (`AuditLog.Read.All`) | `object_id` | `#/$defs/user_signins` |
| `M365.REPORTS.USER_ACCESS_AUDIT_REPORT` | `scripts/m365/reports/user-access-audit/Get-UserAccessAuditReport.ps1` | `reports` | `Graph` (`AuditLog.Read.All`) | `object_id` | `#/$defs/user_signins` |
| `M365.OTHER.UPN_SMTP_ALIGNMENT` | `scripts/m365/other/upn-smtp-alignment/Get-UpnSmtpAlignment.ps1` | `other` | `Graph` (`User.Read.All`) | `upn`, `object_id` | `#/$defs/user_identity` |

### Key Security & Contract Invariants
- **Pure PowerShell 7 & F7Hub Portability:** None of the scripts import PySide6/Qt, SQLite, or T-Notes application modules, nor do they invoke `Connect-MgGraph` or `Connect-ExchangeOnline`. All 25 scripts are UTF-8 without BOM, LF-only, declare `[CmdletBinding()]` and deeply frozen `IReadOnlyDictionary[string, object]` `$Context` / `$Parameters` ABI v1 inputs, cap error/warning messages at 512 chars, validate `expires_at` / `session_generation` leases, and handle `OperationCanceledException` without leaking raw provider exception text.
- **Dual Execution Capability:**
  - When provider cmdlets (`Get-MgUser`, `Get-MgUserLicenseDetail`, `Get-MgAuditLogSignIn`, `Get-EXOMailbox`, `Get-EXOMailboxStatistics`, plus optional read-only enrichment cmdlets such as `Get-MgUserMemberOf`, `Get-MailboxAutoReplyConfiguration`, `Get-EXOMailboxPermission`, `Get-EXORecipientPermission`) are present or mocked in the worker runspace, all 25 scripts invoke them with fixed typed parameters, enforce tenant/target output binding (`id`, `user_principal_name`, `ExternalDirectoryObjectId`), cap `user_signins` responses at the 50-item schema limit (`OUTPUT_LIMIT`), emit `TELEMETRY_SCOPE` warnings on license/sign-in inferred diagnostics (`M365.INTUNE.COMPLIANCE_AND_ENROLLMENT`, `M365.INTUNE.DEVICE_INVENTORY_AND_OS_POSTURE`, `M365.ONEDRIVE.SYNC_AND_STORAGE_DIAGNOSTIC`), and report empty filtered live results as `success` with informational warnings (`NO_MATCHING_EVENTS`, `NO_RISKY_SIGNINS`, `NO_ACTIVE_LICENSES`, `NO_LOCKOUT_OR_LEGACY_EVENTS`, `NO_ONEDRIVE_SYNC_EVENTS`) rather than synthetic fallback.
  - When running in the offline synthetic worker without live M365 modules installed, the scripts evaluate deterministic synthetic fixtures supporting `success`, `partial` (`PROPERTY_UNAVAILABLE` and `OUTPUT_LIMIT`), `TARGET_NOT_FOUND`, `MAILBOX_NOT_FOUND`, `ACCESS_DENIED`, `API_THROTTLED`, and cooperative cancellation.
- **Native Return & Deep Immutability Dispatch:** Both host dispatchers (`M365ExecutionService._invoke_powershell_worker` and `M365WorkerHost.ps1`) load `prototypes/m365_official_engine/protocol.ps1`, recursively freeze context and parameter trees via `Freeze-Value` into `ReadOnlyDictionary[string, object]` / `ReadOnlyCollection` objects prior to ABI v1 invocation, compile `TNotesNativeReturnTypes`, and validate the native 5-field `operation_return` (`PSCustomObject` and 1D zero-based `System.Array` via direct CLR calls without ETS script member evaluation) before JSON serialization.
- **Catalog Separation:** The default production catalog (`assets/m365/catalog.json`) remains empty (`"operations": []`). The 25 validated read-only operations are registered in `assets/m365/synthetic-catalog.json` (and synchronized into `assets/m365_synthetic/catalog.json` by `build_synthetic_catalog_service()`).

---

## 2. S3 — Functional T-Notes Launcher (`M365ExecutionService` & `M365LauncherWidget`)

### Service Layer (`src/services/m365_execution_service.py`)
- **`M365ExecutionService`:**
  - Enforces a single-active-operation state machine (`idle`, `running`, `cancelling`, `succeeded`, `partial`, `failed`, `cancelled`, `timeout`).
  - Validates company selection, explicit company confirmation, per-service connection state (`Graph` / `ExchangeOnline`), tenant/account/generation match, parameter bounds (`bind_parameters`), and target resolution (`requires_resolved_identity`).
  - Validates `execution-request`, `invocation_context`, `operation_return`, `execution-result`, `operation-data`, and `history_record` against the 7 official Draft 2020-12 JSON Schemas in `docs/contracts/m365/schemas/`.
  - Automatically retains resolved `(object_id, upn)` in `CompanyContextService` when `M365.ENTRA.USER_IDENTITY` completes with `success` or `partial` so follow-on operations (`Get-UserLicenses`, `Get-UserSignIns`, `Get-MailboxSummary`) can immediately use the canonical `object_id`.
  - Maintains bounded RAM-only session execution history (`max_history = 100`) and single-use `NoteInsertionPreview` tokens bound to `(correlation_id, company_id, tenant_id, session_generation, text_sha256)`.

### Presentation Layer (`src/ui/m365/launcher_widget.py` & `src/ui/dialogs/m365_help_dialog.py`)
- **Workspace Help Guide (`?` / `M365HelpDialog`):** A compact `?` button (`btn_help`) in the top-right header next to `Back to T-Notes` opens a dark-themed modal `M365HelpDialog` containing a 6-step technician workflow guide, a Synthetic Test Identities Cheat Sheet (`client@alpine.example`, `partial.user@alpine.example`, `missing@alpine.example`, `denied@alpine.example`), and keyboard shortcut references.
- **Per-Category Function Card (`category_function_card`):** Dynamically separates each of the 14 categories (`Dashboard`, `Companies`, `General`, `Entra ID`, `Exchange Online`, `Licensing`, `Teams`, `SharePoint`, `OneDrive`, `Intune`, `Security`, `Reports`, `Workflows`, `Other`) with category-specific telemetry, `⚡ Quick Setup`, `▶ Run Core Snapshot` (`Dashboard`), `🔑 Verify Target Identity` (`Companies`), 5 guided multi-step workflows (`Workflows`: Full User Snapshot, Security Triage, Collaboration Readiness, Mailbox & Delivery Triage, Account Lockout & Auth Triage), and `▶ Run All <Category>` batch runners across all 11 service categories.
- **Synthetic Catalog Loader (`🧪 Load Synthetic Snapshot`) & Independent 2-Column Workspace Layout:** Loads the 25 offline synthetic operations into the category browser on demand while keeping default startup catalog state empty. In 2-column mode, the center workspace uses two independent vertical column stacks (`3:2` width ratio) so each column sizes to its own content without row-locked whitespace:
  - **Left Column (`_left_col_container`):** `Company Selection` (compact) → `Script Catalog` (expands with stretch `4`, side-by-side filters, and uncapped `operation_list` / `operation_details`) → `Execution Workspace` (expands with stretch `2`).
  - **Right Column (`_right_col_container`):** `Authentication & Tenant Context` → `Parameters` (`QSizePolicy.Maximum`, `maxHeight=165px` with zero vertical stretch so there is no whitespace above or below it) → `Parsed Results` (expands with stretch `3`).
- **Group 3 (`Parameters`):** Compact parameter panel (`maxHeight=165px`) that dynamically constructs bounded input controls (`QSpinBox` for integer bounds such as `LookbackDays` and `MaxRecords`, `QCheckBox` for booleans, `QLineEdit` for strings) from the selected operation's manifest.
- **Group 4 (`Execution Workspace`):** Provides `▶ Run (Synthetic)`, `⏹ Cancel`, `🗑 Clear`, live execution state badge, and a selectable `Session Execution History` list.
- **Group 5 (`Parsed Results`):** Displays the formatted diagnostic summary or `{ } Raw JSON` (sanitized) in a read-only `QPlainTextEdit`, plus `📥 Insert into Active Ticket` which validates the single-use preview token and appends the diagnostic summary directly into the Active Ticket shared document editor.


## Pane slide transitions

The left Categories pane and right Active Ticket pane slide open/closed (~220ms) when toggled from the launcher bar or the status-bar `☰ Categories` / `Active Ticket` buttons (`PanelWidthTransition`; see `docs/architecture/system-overview.md` section 7). Panes keep their `110–180px` / `220px+` width limits after each transition, and toggles are instant when the launcher page is not visible.


---

## 3. Live Tenant Mode, Preflight Readiness & Persistent Auth Worker Host

Building on the validated `tnotes.m365 / 0.3.0` contract without altering pinned files under `docs/contracts/m365/`, `prototypes/m365_official_engine/`, or `assets/m365/catalog.json`, the M365 workspace separates **Offline Synthetic Snapshot (25 scripts)** from **Live Tenant Mode (25 read-only operations)**:

- **Live Preflight Readiness (`src/services/m365_preflight_service.py` & `M365PreflightDialog`)**:
  - Dynamically inspects all 25 live operation manifests (`LIVE_PILOT_MANIFEST_PATHS`) for required PowerShell 7 version and SemVer module constraints (`Microsoft.Graph.Authentication`, `Microsoft.Graph.Users`, `Microsoft.Graph.Reports`, `ExchangeOnlineManagement`), validates the local `tnotes.m365 / 0.3.0` schema bundle, and surfaces copyable `-Scope CurrentUser` install commands without silent module auto-installation. Minimal Graph scopes (`User.Read.All`, `LicenseAssignment.Read.All`, `AuditLog.Read.All`) are requested at sign-in.
- **Persistent Isolated Worker & Dual Interactive Sign-In (`src/services/m365_worker_host.py`, `scripts/m365/_host/M365WorkerHost.ps1`, `src/services/m365_connection_manager.py`)**:
  - Spawns one persistent `pwsh` process per active `(company_id, admin_identity_ref, session_generation)` bound inside a Windows Job Object (`JOB_OBJECT_LIMIT_KILL_ON_JOB_CLOSE`) and terminated synchronously on company/admin switch, Disconnect, mode switch, or app exit (`MainWindow.closeEvent`).
  - Supports **Interactive Browser / WAM** (`browser`) and **Device Code (Chrome InPrivate)** (`device_code` with `M365DeviceCodeDialog`) without persisting tokens on disk.
  - Hard-verifies `Get-MgContext` and `Get-ConnectionInformation` against the confirmed `Company` tenant GUID and expected administrator UPN, failing closed on `TENANT_MISMATCH` or `ACCOUNT_MISMATCH`.
- **Hard Mode & Synthetic Isolation (`src/services/m365_execution_service.py`)**:
  - `build_live_pilot_catalog_service()` exposes all 25 cmdlet-backed read-only scripts (`LIVE_PILOT_SCRIPT_IDS`). Any unapproved or write operation not in `LIVE_PILOT_SCRIPT_IDS` is excluded in Live mode and rejected fail-closed at execution time.
  - `M365ExecutionService` evaluates Exchange Online `required_roles` `any_of` groups (`_has_satisfied_exo_roles`) against verified EXO session cmdlets/RBAC roles (`cmdlet.Get-EXOMailbox`, `cmdlet.Get-EXOMailboxStatistics`, or `View-Only.Recipients`).
  - `M365WorkerHost.ps1` validates module availability, live Graph/EXO session binding, and required cmdlets (`Get-MgUser`, `Get-MgUserLicenseDetail`, `Get-MgAuditLogSignIn`, `Get-EXOMailbox`, `Get-EXOMailboxStatistics`) **before** invoking any script so live executions fail closed with `MODULE_MISSING` or `AUTH_REQUIRED` instead of falling back to offline fixture branches. Live executions emit `"provenance": "runtime"`.
