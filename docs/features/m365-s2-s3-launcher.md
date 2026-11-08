# M365 S2 & S3 — Offline Synthetic Snapshot Operations & Functional Launcher

Status: **OFFLINE SYNTHETIC IMPLEMENTATION CANDIDATE — INDEPENDENT REVIEW REQUIRED**
Contract Baseline: `tnotes.m365 / 0.3.0`

## 1. S2 — First Offline Synthetic PowerShell Operations (`scripts/m365/`)

Four independent PowerShell 7 operation scripts implement the User Diagnostic Snapshot workflow under `scripts/m365/` against the `tnotes.m365 / 0.3.0` Callable ABI v1 (`$Context`, `$Parameters`, `$CancellationToken`):

| Script ID | Script Path | Category | Required Connection | Accepted Target Kinds | Output Schema Fragment |
| :--- | :--- | :--- | :--- | :--- | :--- |
| `M365.ENTRA.USER_IDENTITY` | `scripts/m365/entra-id/user-identity/Get-UserIdentity.ps1` | `entra-id` | `Graph` (`User.Read.All`) | `upn`, `object_id` | `#/$defs/user_identity` |
| `M365.ENTRA.USER_LICENSES` | `scripts/m365/licensing/user-licenses/Get-UserLicenses.ps1` | `licensing` | `Graph` (`LicenseAssignment.Read.All`, role `Directory.Readers`) | `object_id` (`requires_resolved_identity: true`) | `#/$defs/user_licenses` |
| `M365.ENTRA.USER_SIGNINS` | `scripts/m365/entra-id/user-signins/Get-UserSignIns.ps1` | `entra-id` | `Graph` (`AuditLog.Read.All`, role `Reports.Reader`) | `object_id` (`requires_resolved_identity: true`) | `#/$defs/user_signins` |
| `M365.EXCHANGE.MAILBOX_SUMMARY` | `scripts/m365/exchange-online/mailbox-summary/Get-MailboxSummary.ps1` | `exchange-online` | `ExchangeOnline` (`cmdlet.Get-EXOMailbox`, `cmdlet.Get-EXOMailboxStatistics`) | `object_id` (`requires_resolved_identity: true`) | `#/$defs/mailbox_summary` |

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

### Presentation Layer (`src/ui/m365/launcher_widget.py`)
- **Synthetic Catalog Loader (`🧪 Load Synthetic Snapshot`):** Loads the 4 S2 snapshot operations into the category browser on demand while keeping default startup catalog state empty.
- **Group 3 (`Parameters`):** Dynamically constructs bounded input controls (`QSpinBox` for integer bounds such as `LookbackDays` and `MaxRecords`, `QCheckBox` for booleans, `QLineEdit` for strings) from the selected operation's manifest.
- **Group 4 (`Execution Workspace`):** Provides `▶ Run (Synthetic)`, `⏹ Cancel`, `🗑 Clear`, live execution state badge, and a selectable `Session Execution History` list.
- **Group 5 (`Parsed Results`):** Displays the formatted diagnostic summary or `{ } Raw JSON` (sanitized) in a read-only `QPlainTextEdit`, plus `📥 Insert into Active Ticket` which validates the single-use preview token and appends the diagnostic summary directly into the Active Ticket shared document editor.

