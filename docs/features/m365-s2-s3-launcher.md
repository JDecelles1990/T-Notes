# M365 S2 & S3 — Offline Synthetic Snapshot Operations & Functional Launcher

Status: **OFFLINE SYNTHETIC IMPLEMENTATION CANDIDATE — INDEPENDENT REVIEW REQUIRED**
Contract Baseline: `tnotes.m365 / 0.3.0`

## 1. S2 — Offline Synthetic PowerShell Operations Across All Categories (`scripts/m365/`)

Seventeen independent PowerShell 7 operation scripts implement diagnostics across all 11 operation categories (`general`, `entra-id`, `exchange-online`, `licensing`, `teams`, `sharepoint`, `onedrive`, `intune`, `security`, `reports`, `other`) under `scripts/m365/` against the `tnotes.m365 / 0.3.0` Callable ABI v1 (`$Context`, `$Parameters`, `$CancellationToken`):

| Script ID | Script Path | Category | Required Connection | Accepted Target Kinds | Output Schema Fragment |
| :--- | :--- | :--- | :--- | :--- | :--- |
| `M365.GENERAL.TENANT_USER_OVERVIEW` | `scripts/m365/general/tenant-user-overview/Get-TenantUserOverview.ps1` | `general` | `Graph` (`User.Read.All`) | `upn`, `object_id` | `#/$defs/user_identity` |
| `M365.GENERAL.SERVICE_READINESS_AUDIT` | `scripts/m365/general/service-readiness/Get-ServiceReadinessAudit.ps1` | `general` | `Graph` (`LicenseAssignment.Read.All`) | `object_id` | `#/$defs/user_licenses` |
| `M365.ENTRA.USER_IDENTITY` | `scripts/m365/entra-id/user-identity/Get-UserIdentity.ps1` | `entra-id` | `Graph` (`User.Read.All`) | `upn`, `object_id` | `#/$defs/user_identity` |
| `M365.ENTRA.USER_SIGNINS` | `scripts/m365/entra-id/user-signins/Get-UserSignIns.ps1` | `entra-id` | `Graph` (`AuditLog.Read.All`, role `Reports.Reader`) | `object_id` | `#/$defs/user_signins` |
| `M365.ENTRA.USER_MFA_AUDIT` | `scripts/m365/entra-id/user-mfa-audit/Get-UserMfaAudit.ps1` | `entra-id`, `security` | `Graph` (`AuditLog.Read.All`) | `object_id` | `#/$defs/user_signins` |
| `M365.EXCHANGE.MAILBOX_SUMMARY` | `scripts/m365/exchange-online/mailbox-summary/Get-MailboxSummary.ps1` | `exchange-online` | `ExchangeOnline` (`cmdlet.Get-EXOMailbox`, `cmdlet.Get-EXOMailboxStatistics`) | `object_id` | `#/$defs/mailbox_summary` |
| `M365.EXCHANGE.MAILBOX_QUOTA_AND_HOLD` | `scripts/m365/exchange-online/mailbox-quota-hold/Get-MailboxQuotaAndHold.ps1` | `exchange-online` | `ExchangeOnline` (`cmdlet.Get-EXOMailbox`) | `object_id` | `#/$defs/mailbox_summary` |
| `M365.ENTRA.USER_LICENSES` | `scripts/m365/licensing/user-licenses/Get-UserLicenses.ps1` | `licensing` | `Graph` (`LicenseAssignment.Read.All`, role `Directory.Readers`) | `object_id` | `#/$defs/user_licenses` |
| `M365.LICENSING.SERVICE_PLAN_AUDIT` | `scripts/m365/licensing/service-plan-audit/Get-ServicePlanAudit.ps1` | `licensing` | `Graph` (`LicenseAssignment.Read.All`) | `object_id` | `#/$defs/user_licenses` |
| `M365.TEAMS.USER_READINESS` | `scripts/m365/teams/user-readiness/Get-TeamsUserReadiness.ps1` | `teams` | `Graph` (`LicenseAssignment.Read.All`) | `object_id` | `#/$defs/user_licenses` |
| `M365.TEAMS.CLIENT_SIGNINS` | `scripts/m365/teams/client-signins/Get-TeamsClientSignIns.ps1` | `teams` | `Graph` (`AuditLog.Read.All`) | `object_id` | `#/$defs/user_signins` |
| `M365.SHAREPOINT.ACCESS_DIAGNOSTIC` | `scripts/m365/sharepoint/access-diagnostic/Get-SharePointAccessDiagnostic.ps1` | `sharepoint` | `Graph` (`AuditLog.Read.All`) | `object_id` | `#/$defs/user_signins` |
| `M365.ONEDRIVE.SYNC_AND_STORAGE_DIAGNOSTIC` | `scripts/m365/onedrive/sync-diagnostic/Get-OneDriveSyncDiagnostic.ps1` | `onedrive` | `Graph` (`LicenseAssignment.Read.All`) | `object_id` | `#/$defs/user_licenses` |
| `M365.INTUNE.COMPLIANCE_AND_ENROLLMENT` | `scripts/m365/intune/compliance-enrollment/Get-IntuneComplianceDiagnostic.ps1` | `intune` | `Graph` (`AuditLog.Read.All`) | `object_id` | `#/$defs/user_signins` |
| `M365.SECURITY.RISKY_SIGNIN_AUDIT` | `scripts/m365/security/risky-signins/Get-SecurityRiskySignIns.ps1` | `security` | `Graph` (`AuditLog.Read.All`) | `object_id` | `#/$defs/user_signins` |
| `M365.REPORTS.USER_ACCESS_AUDIT_REPORT` | `scripts/m365/reports/user-access-audit/Get-UserAccessAuditReport.ps1` | `reports` | `Graph` (`AuditLog.Read.All`) | `object_id` | `#/$defs/user_signins` |
| `M365.OTHER.UPN_SMTP_ALIGNMENT` | `scripts/m365/other/upn-smtp-alignment/Get-UpnSmtpAlignment.ps1` | `other` | `Graph` (`User.Read.All`) | `upn`, `object_id` | `#/$defs/user_identity` |

### Key Security & Contract Invariants
- **Pure PowerShell 7 & F7Hub Portability:** None of the scripts import PySide6/Qt, SQLite, or T-Notes application modules, nor do they invoke `Connect-MgGraph` or `Connect-ExchangeOnline`.
- **Dual Execution Capability:**
  - When provider cmdlets (`Get-MgUser`, `Get-MgUserLicenseDetail`, `Get-MgAuditLogSignIn`, `Get-EXOMailbox`, `Get-EXOMailboxStatistics`) are present or mocked in the worker runspace, the scripts invoke them with fixed typed parameters and verify target output binding (`id`, `user_principal_name`, `ExternalDirectoryObjectId`).
  - When running in the offline synthetic worker without live M365 modules installed, the scripts evaluate deterministic synthetic fixtures supporting `success`, `partial` (`PROPERTY_UNAVAILABLE` and `OUTPUT_LIMIT`), `TARGET_NOT_FOUND`, `MAILBOX_NOT_FOUND`, `ACCESS_DENIED`, `API_THROTTLED`, and cooperative cancellation.
- **Native Return Validation:** Every worker invocation loads `prototypes/m365_official_engine/protocol.ps1`, compiles `TNotesNativeReturnTypes`, and validates the native 5-field `operation_return` (`PSCustomObject` and 1D zero-based `System.Array` via direct CLR calls without ETS script member evaluation) before JSON serialization.
- **Catalog Separation:** The default production catalog (`assets/m365/catalog.json`) remains empty (`"operations": []`). The 4 synthetic operations are registered in `assets/m365/synthetic-catalog.json` (and synchronized into `assets/m365_synthetic/catalog.json` by `build_synthetic_catalog_service()`).

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
- **Per-Category Function Card (`category_function_card`):** Dynamically separates each of the 14 categories (`Dashboard`, `Companies`, `General`, `Entra ID`, `Exchange Online`, `Licensing`, `Teams`, `SharePoint`, `OneDrive`, `Intune`, `Security`, `Reports`, `Workflows`, `Other`) with category-specific telemetry, `⚡ Quick Setup`, `▶ Run Core Snapshot` (`Dashboard`), `🔑 Verify Target Identity` (`Companies`), 3 guided multi-step workflows (`Workflows`), and `▶ Run All <Category>` batch runners across all 11 service categories.
- **Synthetic Catalog Loader (`🧪 Load Synthetic Snapshot`) & Independent 2-Column Workspace Layout:** Loads the 17 offline synthetic operations into the category browser on demand while keeping default startup catalog state empty. In 2-column mode, the center workspace uses two independent vertical column stacks (`3:2` width ratio) so each column sizes to its own content without row-locked whitespace:
  - **Left Column (`_left_col_container`):** `Company Selection` (compact) → `Script Catalog` (expands with stretch `4`, side-by-side filters, and uncapped `operation_list` / `operation_details`) → `Execution Workspace` (expands with stretch `2`).
  - **Right Column (`_right_col_container`):** `Authentication & Tenant Context` → `Parameters` (`QSizePolicy.Maximum`, `maxHeight=165px` with zero vertical stretch so there is no whitespace above or below it) → `Parsed Results` (expands with stretch `3`).
- **Group 3 (`Parameters`):** Compact parameter panel (`maxHeight=165px`) that dynamically constructs bounded input controls (`QSpinBox` for integer bounds such as `LookbackDays` and `MaxRecords`, `QCheckBox` for booleans, `QLineEdit` for strings) from the selected operation's manifest.
- **Group 4 (`Execution Workspace`):** Provides `▶ Run (Synthetic)`, `⏹ Cancel`, `🗑 Clear`, live execution state badge, and a selectable `Session Execution History` list.
- **Group 5 (`Parsed Results`):** Displays the formatted diagnostic summary or `{ } Raw JSON` (sanitized) in a read-only `QPlainTextEdit`, plus `📥 Insert into Active Ticket` which validates the single-use preview token and appends the diagnostic summary directly into the Active Ticket shared document editor.

