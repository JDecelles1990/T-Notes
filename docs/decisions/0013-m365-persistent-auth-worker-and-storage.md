# [ADR-0013] M365 Persistent Auth Worker, Dual Interactive Login, and SQLite Company Storage

- **Status:** Accepted
- **Date:** 2026-11-12
- **Author(s):** T-Notes Engineering
- **Deciders:** Project Maintainer

---

## 1. Context and Problem Statement

T-Notes S2/S3 established offline synthetic execution of PowerShell 7 M365 operations against pinned `tnotes.m365 / 0.3.0` contracts using ephemeral per-call `pwsh` processes and an in-memory `CompanyDirectory` preloaded with `.example` fixtures. Transitioning to live read-only Microsoft 365 tenant diagnostics for MSP technicians introduced three constraints:
1. Interactive `Connect-MgGraph` and `Connect-ExchangeOnline` sessions (including isolated Chrome/Edge InPrivate sign-ins) cannot survive across ephemeral one-shot `pwsh` invocations without writing token caches to disk.
2. All 4 cmdlet-capable scripts contain `# Offline synthetic fixture evaluation` fallback paths when Microsoft Graph / EXO cmdlets are not loaded; live mode must never silently return synthetic fixture data.
3. Customer company profiles and admin UPNs must persist across restarts in `techpad.db` without polluting the database with `.example` synthetic records or breaking `CompanyDirectory`'s Qt/SQLite-free portability for F7Hub reuse.

---

## 2. Decision Drivers
- **Zero Disk Token Persistence:** Keep M365 authentication sessions strictly in process RAM via `Connect-MgGraph -ContextScope Process` and `Connect-ExchangeOnline` in one owned persistent worker, torn down via a Windows Job Object (`KILL_ON_JOB_CLOSE`).
- **Dual Auth Workflows:** Support both default WAM/System Browser interactive login and `-UseDeviceCode` / `-Device` with real-time device-code UI modals so MSP technicians can sign into isolated InPrivate browser profiles per client tenant.
- **Immutable Contract Integrity:** Preserve byte-for-byte SHA-256 parity across `docs/contracts/m365/`, `prototypes/m365_official_engine/`, `assets/m365/catalog.json`, and existing S2 scripts.
- **Strict Synthetic vs Live Separation:** Exclude the 13 synthetic-only scripts from Live Pilot Mode (`4` read-only cmdlet-backed pilot operations only), enforce `"verified"` connection leases (`"runtime"` provenance), and fail closed if required modules/cmdlets are absent.

---

## 3. Considered Options
1. **MSAL Token Cache on Disk + One-Shot `pwsh`:** Store refresh tokens in DPAPI/keyring and invoke `pwsh` per operation. Rejected due to expanded secret-at-rest surface and cross-tenant session contamination risk.
2. **Modify All 17 `.ps1` Scripts In-Place:** Rewrite scripts to drop synthetic fallback branches and inject new parameters. Rejected because it breaks pinned SHA-256 S1/S2 parity and mixes pilot readiness with unported workloads.
3. **Persistent Owned `pwsh` Worker Host + SQLite Company Repository + Host-Side Pre-Invocation Guard (Chosen):** Keep all pinned scripts/contracts unmodified; add `scripts/m365/_host/M365WorkerHost.ps1` + `LiveConnectionManager` + `M365PreflightService` + `M365CompanyRepository`/`PersistentCompanyDirectory`.

---

## 4. Decision Outcome
**Chosen Option:** Persistent Owned `pwsh` Worker Host + SQLite Company Repository + Host-Side Pre-Invocation Guard

### Rationale
- One persistent `M365WorkerHost` bound to `(company_id, tenant_id, admin_identity_ref, session_generation)` retains Graph and Exchange Online REST sessions in RAM inside a Windows Job Object and terminates synchronously on switch/disconnect/exit.
- Intercepting `[Console]::Out` inside `M365WorkerHost.ps1` with a synchronized `TextWriter` captures MSAL/EXO device-code prompts as structured JSON events without corrupting the line-delimited stdin/stdout JSON protocol.
- Checking `Import-Module`, `Get-MgContext` / `Get-ConnectionInformation`, and `Get-Command` for required cmdlets (`Get-MgUser`, `Get-MgUserLicenseDetail`, `Get-MgAuditLogSignIn`, `Get-EXOMailbox`, `Get-EXOMailboxStatistics`) *before* invoking `& $scriptPath` prevents silent fallback into synthetic fixtures while preserving existing SHA-256 pins.
- Separating `M365CompanyRepository` (SQLite tables `m365_directory_meta`, `m365_companies`, `m365_administrators`) and `PersistentCompanyDirectory` from `CompanyDirectory` retains full F7Hub portability and keeps `.example` records strictly in RAM.

---

## 5. Consequences

### Positive Consequences
- Technicians sign in once per customer session (Graph + Exchange Online) and can reuse Chrome InPrivate via Device Code.
- Workstation readiness (`pwsh >= 7.0.0`, schema integrity, manifest-derived modules) is surfaced upfront via `M365PreflightService` with copyable `-Scope CurrentUser` install commands.
- Customer tenant profiles persist across restarts with JSON Export and atomic pre-backup Merge.

### Negative Consequences / Trade-offs
- Exchange Online live sessions hold an interactive session open until Disconnect or window close; mitigated cleanly via idle expiration checks and synchronous Job Object termination.
- The other 13 workload scripts remain accessible exclusively in Offline Synthetic Snapshot mode until their PowerShell implementations gain live Microsoft cmdlets and pilot promotion.

---

## 6. Implementation Notes & Validation
- Database schema & migration: `src/database/schema.sql`, `src/database/migrations.py`, `docs/database/schema.md`
- Persistence & atomic merge: `src/repositories/m365_company_repository.py`, `src/services/m365_company_store.py`, `tests/test_m365_company_repository.py`
- Preflight, worker host, dual auth & Live Pilot: `src/services/m365_preflight_service.py`, `src/services/m365_worker_host.py`, `scripts/m365/_host/M365WorkerHost.ps1`, `src/services/m365_connection_manager.py`, `src/services/m365_context_service.py`, `src/services/m365_execution_service.py`, `src/ui/m365/live_readiness_widgets.py`, `tests/test_m365_preflight_and_live_worker.py`

