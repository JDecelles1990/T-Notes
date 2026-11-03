# T-Notes ↔ PowerShell Shared Execution Contract

Status: **DRAFT** · Contract identifier: `tnotes.m365` · Version: `1.0.0-draft.1` · Dated: 2026-11-02.

This is the proposed source of truth for the T-Notes M365 Launcher GUI, Codex integration work, and Gemini-generated PowerShell scripts. Contract is **not** adopted, not deployed, and no runtime tests have been executed in T-Notes.

## 1. Boundary and ownership

| Owner | Responsibility | Explicitly excluded |
|---|---|---|
| T-Notes GUI/Codex | Company selector; parameter forms; active ticket panel; structured results; risk/approval UX | Hardcoded M365 cmdlet implementations |
| T-Notes application service/Codex | Manifest/schema validation; input validation; active-ticket context; launch/cancel; redact results | Direct SQL in the UI |
| PowerShell host adapter/Codex | Authentication/session ownership, tenant isolation, script allowlist, invocation, exception normalization, JSON envelope | Running arbitrary clipboard/AI-generated commands |
| Individual PowerShell script/Gemini | One operation with documented inputs and a typed result, plus mocked tests | GUI, SQLite, passwords, app tokens, free-form stdout JSON, self-registration |
| Existing scratchpad services | Authoritative notes, autosave, ticket identity and persistence | A second notes database |

The wire format is **transport-independent**. Whether Codex later selects a persistent `pwsh` worker or a bounded subprocess, it must preserve these request/response schemas. Do not commit to a process protocol until the current app lifecycle, PowerShell module requirements, and authentication behavior have been tested.

## 2. Canonical files and precedence

- `CONTRACT.md`: semantics, ownership, security rules and compatibility policy.
- `schemas/script-manifest.schema.json`: registration metadata.
- `schemas/execution-request.schema.json`: normalized invocation parameters and context.
- `schemas/execution-result.schema.json`: normalized outcome.
- `examples/`: illustrative fixtures, **never** credential material.
- Existing `AGENTS.md`: T-Notes engineering boundaries; contract does not override higher priority user requirements or legal/security restrictions.

Production code must validate a manifest and request **before** execution, and validate the response **before** displaying/importing it. A schema validator protects shape but cannot prove authorization, provenance, semantic truth or correctness.

## 3. Identity and MSP tenant rules

- User searches a customer name; the profile retrieves a friendly company name, trusted tenant GUID, tenant domain and assigned administrator UPN. Company catalog must not include passwords.
- Admin account is an **identity hint**, not proof of authorization. Do not treat a domain string as a tenant identity; actual Microsoft tenant GUID must be verified after login.
- Each company maintains its own authorized admin identity. There is no assumed master MSP administrator account, password or GDAP arrangement.
- Authentication is owned by a dedicated connector/host, not by each script. Preferred interactive methods are Microsoft-supported authentication with MFA and Conditional Access; secure session reuse is allowed only if the provider permits it.
- **Neither execution request nor response nor manifest may contain passwords, tokens, secrets or credential objects.** Do not store or auto-submit password-manager passwords through PowerShell. User can consult their password manager independently during the Microsoft login flow.
- On connecting or switching tenants, verify signed-in account, tenant GUID, required scopes and service-specific session. A switch must invalidate/revalidate any prior customer state. Verify again immediately before modifications.
- Graph and Exchange Online connections have different lifecycles; do not assume one shared token or authenticated session. App-only automation is a future separately-approved design.
- `target_user_upn` identifies the person being investigated, not the account used to authenticate. UI should resolve/validate it in the selected tenant; PowerShell must not silently substitute the current admin UPN.

## 4. Script contract

Script ID: stable, globally unique form `M365.<SERVICE>.<OPERATION>`. Examples: `M365.ENTRA.GET_USER_SNAPSHOT`, `M365.EXCHANGE.GET_MAILBOX_REPORT`.

- Every script requires a validated manifest conforming to `schemas/script-manifest.schema.json`.
- All parameters listed as required in the manifest must be present, validated and type-checked. Reject unspecified parameters (unless an explicit future contract revision permits them).
- Script should expose a single approved PowerShell function named in `entrypoint`; put its implementation in an allowlisted `.psm1` module for the host to import into the authenticated worker. Exact PowerShell host bridge design remains subject to the first technical spike.
- The host passes `Context` (verified tenant, actual admin account, target user where relevant) and `Parameters` (script-specific, typed values). Scripts **do not** perform login, create/migrate SQLite tables, or write note/ticket data.
- Script returns a `PSCustomObject` with `Data` (serializable object, not raw Microsoft SDK objects) and optional `Warnings` (array of non-sensitive messages). Normalization, result envelope and JSON serialization belong solely to the host adapter. Scripts signal failed execution via terminating errors, which the host maps to sanitized error codes.
- No `Write-Host`, `Format-Table`, uncontrolled progress output or textual JSON on the success pipeline. Never use `Invoke-Expression`, execute untrusted command text, or load an unreviewed script directly. Scrub M365 response properties before returning.
- Use `-ErrorAction Stop` for appropriate calls and catch/translate exceptions at the host boundary. Do not swallow failures as success.
- Where appropriate scripts should be idempotent, support cancellation and follow explicit per-command timeout limits. A read-only label means the *implementation* was reviewed to avoid side effects; it is not inferred from the cmdlet name alone.

## 5. Request and result envelopes

Conform to `schemas/execution-request.schema.json` and `schemas/execution-result.schema.json`.

Request fields:

- `contract_version`: exact matching version.
- `request_id`: UUID for correlating records.
- `script_id`: validated allowlisted script ID.
- `context`: `company_id` (local opaque key), verified `tenant_id` GUID, `admin_upn`, `target_user_upn` (optional), `ticket_id` (optional, for T-Notes association only); no secrets.
- `parameters`: manifest-defined argument values (no extra parameters).

Result fields:

- `contract_version`, `request_id`, `script_id`, verified `tenant_id`, `status` (`success`, `partial`, `failed`, `cancelled`), `data` (object or null), `warnings` (array of plain strings), `errors` (array of code/message/retryable objects), `started_at_utc`, `finished_at_utc`, `duration_ms`.
- Timestamp values use ISO-8601 with UTC `Z`; data is intentionally script-specific, and each script should define/document a typed data payload schema before production acceptance.
- `success`: `data` object and empty `errors`; `failed`/`cancelled`: at least one error; `partial`: explicit warnings and/or errors; app must not treat partial results as verified success.
- No fake success values, exception stack traces, raw tokens or full identity-provider payloads in user-visible output.

## 6. Risk, permissions and approvals

- `read`: safe inspection, no planned server-side modifications. Default initial scope.
- `change`: modifies settings/data; require explicit preview, company/tenant/target confirmation and verified permissions.
- `high_impact`: revokes sessions, disables access, changes privileged memberships or destructive actions; requires a stronger explicit confirmation/authorization policy; not part of MVP.
- Manifest includes necessary Graph scopes and role guidance, but role metadata is not proof. Actual execution requires successful provider-side RBAC/consent checks.
- Verify what-if support per cmdlet; `-WhatIf` is never a substitute for access controls or preview.
- Never auto-run an administrative change based solely on an AI suggestion or content in a ticket/note.

## 7. Collapsible active T-Notes ticket side panel

Required UX: In the M365 workspace, display a **collapsible/resizable dock or splitter panel** containing the same authoritative active T-Notes ticket and allowing live note editing while operations run asynchronously.

Requirements:

1. Panel identifies ticket number, company and issue subject from existing T-Notes records; switching tickets updates context only through explicit selection and guards against cross-customer mix-ups.
2. No duplicate independent note object, database or save loop. Existing `ScratchpadService` owns persistence. Codex must inspect `TechPadEditor`, `QTextDocument` lifecycle, tab split view, debounced saves, and close-to-tray behavior before choosing reuse/reparent/shared-document approach.
3. Unsaved edits survive panel collapse, workspace navigation, ticket changes, window hiding, normal shutdown, worker cancellation and module errors.
4. A PowerShell result may be inserted into the active ticket **only on a visible user action**, with ticket ID and tenant cross-check, preview and redaction. Never silently overwrite typed notes.
5. PowerShell tasks run outside the Qt GUI thread; results/errors cannot freeze typing. Worker exit, cancellation, and program shutdown are coordinated without losing notes.
6. When panel is collapsed, note state remains preserved and no second editor is silently spawned.

The GUI architecture is a proposal; Codex must inspect the current `QSplitter`/Mini-HUD/keyboard interception and propose a reversible minimal slice before coding.

## 8. Logging, privacy and error hygiene

- Do not log secrets, authentication challenge contents, full raw SDK objects, passwords, tokens, password-manager data or full sign-in payloads.
- T-Notes may log non-secret metadata: request ID, script ID/hash, company opaque ID, verified tenant GUID, status, duration, redacted error codes and user-confirmed audit actions.
- User UPNs, email addresses, mailbox contents, sign-in logs and ticket notes are personal or customer data: respect employer authorization and retention rules, avoid uploading these to public repos and public AI services.
- Output is untrusted: escape rich text/HTML, limit content size, allow safe ticket-note preview and clean cancellation/timeout.
- Never assume a script's success means the intended remediation is verified. Add separate checks and evidence where appropriate.

## 9. Agent governance and compatibility

The canonical contract is shared by Codex and Gemini. Neither agent may silently edit it while implementing a script or GUI slice. Treat proposed changes as a separate versioned, reviewed task.

Before coding an agent must report:

1. Confirmed contract version and file paths actually read.
2. Stable script ID, ownership and scope.
3. Required scopes/roles, target identifiers, input and output types.
4. Failure modes and test plan.
5. Exact changed-file list and exclusions.

For `1.0.0-draft.1`, all changes are still reviewable. After approval/freeze, breaking changes need a new major version, coordinated consumer updates and migration tests. Nonbreaking field additions need documented minor version and schema compatibility tests. Fixes/documentation corrections may use a patch version. No agent can self-approve a schema change.

### Suggested addition to existing root AGENTS.md (DO NOT overwrite existing rules)

> All M365 GUI/PowerShell work must follow `docs/contracts/m365/CONTRACT.md` and all JSON schemas in `docs/contracts/m365/schemas/`. Read these files before changing M365 code. Report contract version, manifest/script ID and tests. Do not modify contracts while implementing a script or GUI slice; request review for changes. Never store credentials or run unauthorized live tenant operations.

## 10. Acceptance gates

- Schema examples validate; invalid/missing extra property, bad GUID, mismatched version and extra output fields are rejected.
- New scripts pass mocked unit tests (Pester or equivalent), including error and tenant-mismatch cases.
- UI tests ensure active ticket note state survives workspace/panel toggles, ticket switch, global shortcuts, Mini-HUD, split view and closing to tray.
- Integration tests reject wrong tenant/account, rejected scope/role, invalid manifest/result, unapproved write actions and unsafe script paths.
- Native Windows tests verify actual interactive authentication, module compatibility and worker lifecycle in an approved test tenant (not in production by default).
- Reports state `PASS`, `FAIL`, `NOT RUN` or `BLOCKED` for each relevant gate, with evidence and limitations.

## 11. Explicitly deferred

Actual company catalog persistence, OS credential storage, password-manager integration, session multiplexing architecture, batch commands, live tenant access, full role matrix, detailed service-specific data schemas, cancellation transport, script signing/hash publication and connection pooling require separate decisions after architecture inspection. This document **does not** authorize implementation.

### Current reference documentation (verified 2026-11-02)

- Microsoft Graph authentication: https://learn.microsoft.com/powershell/microsoftgraph/authentication-commands?view=graph-powershell-1.0
- Connect-MgGraph: https://learn.microsoft.com/powershell/module/microsoft.graph.authentication/connect-mggraph?view=graph-powershell-1.0
- Get-MgContext: https://learn.microsoft.com/powershell/module/microsoft.graph.authentication/get-mgcontext?view=graph-powershell-1.0
- Exchange Online: https://learn.microsoft.com/powershell/module/exchangepowershell/connect-exchangeonline
- Pester mocking: https://pester.dev/docs/v5/usage/mocking
