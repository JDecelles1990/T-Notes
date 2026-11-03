# T-Notes M365 — User Diagnostic Snapshot

Status: PROPOSED / NOT APPROVED FOR IMPLEMENTATION  
Spec version: 0.1-draft  
Depends on: `contracts/m365/CONTRACT.md` and `contracts/m365/result.schema.json`  
Target host: T-Notes PySide6 M365 Workspace

## 1. Objective
Show one selected user's account state, M365 license assignments, mailbox properties and recent sign-in evidence in a read-only result panel, while keeping the active ticket notes editable in the collapsible sidebar. Permit a sanitized *Insert Findings into Ticket* action; never inject automatically.

## 2. Key design resolution
The shared contract says *one approved Microsoft 365 operation per script*. Therefore the **User Diagnostic Snapshot is a GUI/service-level workflow**, not one enormous `.ps1` file. Four independently executable scripts return one JSON envelope each. T-Notes combines their `data` objects into a view model; missing/unavailable sections are shown as **unavailable**, not healthy.

| Script ID | Proposed filename | Responsibility | Data source | Risk |
|---|---|---|---|---|
| `M365.ENTRA.USER_IDENTITY` | `Get-UserIdentity.ps1` | Exact target lookup, object ID, display name, UPN, account enabled, user type | `Get-MgUser` | read_only |
| `M365.ENTRA.USER_LICENSES` | `Get-UserLicenses.ps1` | Assigned SKUs and service plans (not a billing analysis) | `Get-MgUserLicenseDetail` | read_only |
| `M365.ENTRA.USER_SIGNINS` | `Get-UserSignIns.ps1` | Bounded recent sign-in events with timestamp, success/failure and sanitized error code | `Get-MgAuditLogSignIn` | read_only |
| `M365.EXCHANGE.MAILBOX_SUMMARY` | `Get-MailboxSummary.ps1` | Mailbox type, SMTP address, mailbox size/quota when available | `Get-EXOMailbox`, `Get-EXOMailboxStatistics` | read_only |

Identity is the *first vertical slice*; only after it is tested should Gemini implement licenses, then sign-ins, then Exchange.

## 3. Input and orchestration
GUI resolves user UPN to a verified Entra object ID using identity lookup. All Graph follow-on operations use object ID. Mailbox lookup uses a verified mailbox identity; if no mailbox exists, return a distinct `MAILBOX_NOT_FOUND` outcome rather than crash.

Required execution context from the host: contract version, correlation UUID, selected company, **verified** tenant GUID and connected administrative identity. User input: target UPN or object ID. Optional workflow input: sign-in lookback (default 7 days; maximum 30 days requested, constrained to actual log retention); maximum records (default 20, cap 50). This is a proposed limit, not a guarantee of records being available.

Connections are owned by the host connection service. Scripts do not call `Connect-MgGraph`, `Connect-ExchangeOnline`, prompt for credentials, obtain passwords, or change a tenant. The host must ensure that the execution session actually carries the authorized identity and tenant. For MSP tenant switching, prefer process-scoped isolated Graph sessions or equivalent safe isolation; never assume a cached account belongs to the selected tenant.

Do not use `-All` on sign-in events. Filter by verified Entra `userId` and a bounded start time using an approved filter implementation; do not interpolate unsanitized user-controlled strings into filters.

## 4. Required permissions and prerequisites
- User identity: `Microsoft.Graph.Users`, typically delegated `User.Read.All` for complete support-oriented user properties; exact least privilege depends on returned properties and tenant rules.
- License details: `Microsoft.Graph.Users`; `LicenseAssignment.Read.All` is the least-privileged delegated Graph permission documented for `licenseDetails`, with supported directory roles as required.
- Sign-in logs: `Microsoft.Graph.Reports`, `AuditLog.Read.All` **plus an appropriate Microsoft Entra role** (e.g. Reports Reader). Conditional Access policy details have separate role/scope restrictions and are excluded from MVP.
- Mailbox information: `ExchangeOnlineManagement`, a connected Exchange Online PowerShell session and appropriate Exchange RBAC read permissions.
- Authentication: Interactive/delegated; the app may remember admin UPN and tenant GUID but no password or token in its own storage.

Do not ask for every permission up front: request only permissions needed by selected checks. Missing access generates a `partial` workflow result with actionable warnings.

## 5. Output contract
Each script must emit exactly one UTF-8 JSON object on stdout compliant with `contracts/m365/result.schema.json` (contract_version `0.1.0` for the current schema). The workflow aggregator's view model is separate from individual script envelopes. Each script populates:

- `contract_version`, `correlation_id`, `script_id`, `status`, `tenant_id`, `data`, `errors`, `warnings`, `started_at`, `completed_at`.
- `status`: success | partial | error | cancelled | timeout.
- `data`: typed, predictable fields; absent/missing should be `null` or a documented unavailable state, **never inferred**.
- On failure, use structured messages with stable error codes such as `AUTH_REQUIRED`, `TENANT_MISMATCH`, `TARGET_NOT_FOUND`, `ACCESS_DENIED`, `MAILBOX_NOT_FOUND`, `API_THROTTLED`, `SERVICE_UNAVAILABLE`, `OUTPUT_LIMIT`.
- Exit codes: 0 success; 2 partial; 10 validation; 20 authentication/authorization; 30 service; 40 timeout/cancel; 50 internal.

The workflow should visibly distinguish `healthy`, `problem detected`, `not evaluated`, `not found` and `access denied`. A missing result is **not** proof of success.

### Suggested data fields (proposed, must be frozen in individual output schemas)
- Identity: `id`, `display_name`, `user_principal_name`, `account_enabled`, `user_type`.
- Licensing: `licenses`: array of `{sku_id, sku_part_number, service_plans:[{service_plan_name, provisioning_status}]}`.
- Sign-ins: `events`: array of `{created_at, app_display_name, status_error_code, success}` plus `lookback_start`, `count_returned`.
- Mailbox: `recipient_type_details`, `primary_smtp_address`, `total_item_size`, `item_count`; quota fields only when reliably returned and normalized.

## 6. UI behavior and ticket notes
- Active ticket notes panel is collapsible and editable, with the same authoritative editor persistence. Do not create an independent autosaving copy of the same ticket.
- Display which checks ran, duration, tenant GUID, target UPN, source and individual section status.
- Offer `Retry check` per failed section, rather than re-running successful operations unnecessarily.
- `Insert Findings into Ticket` shows preview and requires a click; include timestamp, ticket ID, verified tenant name, target user and results, excluding authentication details, unnecessary identifiers and sensitive sign-in/IP/location fields by default.
- Changing company clears previous user resolution and invalidates prior tenant sessions/eligibility in UI and execution worker.

## 7. Security requirements
- No scripts may store or log passwords, access tokens or refresh tokens.
- Never echo raw exceptions, sensitive HTTP headers or raw response payloads into logs.
- Allow only approved catalog scripts, with constrained paths and integrity verification.
- Do not perform account remediation, license changes, mailbox changes, or token revocation as part of this workflow.
- Graph calls and Exchange calls must be bound to the tenant verified by the host.
- Use preapproved fixed cmdlets with typed parameters, not shell expression construction or `Invoke-Expression`.
- Bound runtime, retry counts, record counts and output size; errors and throttling should be handled without UI freezes.

## 8. Test plan / acceptance criteria
1. Exact-match user found with stable object ID.
2. Nonexistent user → structured `TARGET_NOT_FOUND`, not misleading blank success.
3. Wrong tenant/authenticated admin mismatch → execution refused, no network request.
4. Missing license assignments → empty array and explicit 'no licenses', not a parser failure.
5. Missing sign-in permissions → section unavailable and overall partial, identity still visible.
6. Sign-in list empty → 'no records in examined period', not 'no sign-in problems'.
7. No Exchange Online mailbox / absent access → section status differentiates each cause.
8. Network timeout, API throttling, cancellation → bounded response and compliant status/exit code.
9. Exactly one valid JSON envelope on stdout; no extraneous banners or progress output.
10. Verify valid/invalid fixtures against result schema; run Pester mocks without real tenant credentials.
11. Verify notes panel does not lose edits or timer state while checks run and when switching workspaces.
12. Verify output cannot leak secrets or cross-tenant results after company switch.

## 9. Open decisions before implementation
- Fix contract label discrepancy: CONTRACT.md says `0.1.0-draft`, schema requires `0.1.0`. Choose canonical version before implementing.
- Define schema and validation for script **manifests** and execution requests; currently only result schema exists.
- Approve `data` sub-schemas for each operation and how a workflow aggregates `partial` outcomes.
- Agree on session process model for Graph and Exchange, including target tenant isolation and cancellation.
- Define stable formatting for mailbox bytes/quota (prefer numeric bytes where feasible, with display formatting in PySide6).

**Status: SPEC READY FOR REVIEW; no scripts implemented.**
