# Company directory, multi-admin identity and launcher checkpoint

Disposition: **COMPANY DIRECTORY CORRECTED — READY_FOR_INDEPENDENT REREVIEW**.
Independent review findings corrected:
- P1: Lossless multiline editing representation for additional verified domains; preserves all validated domains across create, reopen, edit and save; eliminates 2,000-character QLineEdit boundary corruption; name-only edit preserves original domains identically.
- P2: Explicit type and format validation for created_at and updated_at; rejects integers, nulls, booleans, floats, empty strings, malformed dates and non-UTC timezone offsets with documented ValueError; prevents automatic coercion and verifies existing directory is never partially modified.
Production storage/authentication/dispatch: **BLOCKED BY SEPARATE GATES**, not implemented.

Base: clean `main`, `ef847af18572ce5b82b0dd263b75658efe1caacd`.
No other branch/worktree was created. No stage, commit, push, merge, reset, clean
or F7Hub mutation. All four modified entry paths are explicitly listed below;
273 other snapshotted source/docs/test/library/asset files retain entry bytes.
Root instructions, official/proposed contracts, catalog pins, engine and Notes
implementation are unchanged. Entry and authority identities are retained in
entry.json and authority.json. Production databases were not opened by this task.

## Exact implementation inventory

| Path | Change |
|---|---|
| src/services/m365_company_service.py | NEW: immutable metadata, validation, multi-admin CRUD/defaults, search, JSON-native versioned export/import seam, synthetic fixtures |
| src/services/m365_context_service.py | NEW: separate synthetic service states, target identifiers, context generation/confirmation/invalidation, fail-closed eligibility |
| src/ui/m365/company_context_panel.py | NEW: company/admin forms and selectors, confirmation, synthetic connections, client target/status UI |
| src/ui/m365/launcher_widget.py | MODIFIED: replace two placeholders, inject session directory/context panel; preserve catalog/sidebar |
| tests/test_m365_company_context.py | NEW: 43 synthetic service cases including temporary test-only SQLite roundtrip |
| tests/test_m365_company_ui.py | NEW: 11 GUI cases, responsive controls and Notes regression protection |
| tests/test_m365_catalog.py | MODIFIED: explicit new-control allowlist and retain no catalog execution buttons |
| docs/features/m365-company-directory.md | NEW: model, ownership, storage/auth/engine gates, portability and migration |
| docs/decisions/0010-m365-company-context-boundary.md | NEW: domain/context separation decision |
| docs/architecture/system-overview.md | MODIFIED: service/UI ownership routing |
| docs/features/m365-catalog.md | MODIFIED: link directory milestone and retain provisional catalog gate |

This review directory contains CHECKPOINT.md, attempts.md, verify_candidate.py,
candidate-inventory.json, entry.json, authority.json, retained per-attempt log/XML
pairs and synthetic preview PNGs. **candidate-inventory.json enumerates every
task-owned changed/untracked file**, with exact raw SHA-256 hashes for all except
the inventory itself. It separately records two concurrently created root PNG
pathnames; their contents were not read, copied, hashed or modified by this task.
This avoids circular self-hashing. No historical review file was overwritten.

## Behavior and boundaries

Search companies by partial name or any configured domain, sorted case-insensitively;
Add/Edit in RAM with stable company UUIDs and explicit company confirmation. Empty
selection and empty search results are safe. Each company owns zero/multiple admin
records with stable record UUID, UPN, label and optional default reference. Support
search, Add/Edit/Remove/Set Default and reject case-insensitive duplicate UPNs.

Selected company/tenant and admin hints never become authenticated evidence.
Graph/Exchange fixture states are independent; actual verified tenant/admin stay
none. Client UPN/object ID is separate, with unresolved/synthetic/mismatch states;
Verified target stays none. Company/admin/hint/revision changes and Disconnect
invalidate transient refs, generation, target, confirmation and connections.
Connection changes invalidate target resolution and confirmation. Expiry disables
any future use and never reconnects. Polling stops while the launcher is hidden.

Profiles contain only declared non-secret metadata. No password controls, tokens,
credential exports, auth cache or authentication adapter. Free-text notes/labels
are explicitly non-secret fields; allowlisting cannot identify secrets a user
manually pastes there. Export/import is an in-memory version-1 seam, not a file UI
or production repository. A temporary SQLite fixture proves metadata reload only.

Eligibility always returns false; no execution API, worker or engine connection
exists. TargetInput exposes a structured candidate-contract identifier, never a
PowerShell command. The existing fourteen-category sidebar and Notes ownership
remain intact. The service modules have only standard-library dependencies plus
their own company service, allowing a future F7Hub storage/workspace adapter
without a shared live database.

## Authority, migrations and remaining authorizations

All seven official v0.3.0 candidate schema hashes match the release inventory.
Contract.md SHA-256: d983ed65280b908d173310de6c69170d4708e53a79e2c6a7bf1f8127049faa56.
However RELEASE_APPROVAL.md and README still say RELEASE CANDIDATE / INDEPENDENT
REVIEW REQUIRED. No effective implementation approval exists in those records.
Catalog and engine remain on 0.3.0-proposed.1. No migration is claimed.

1. Accept ongoing case-note data-integrity corrections and verify backup/restore/
   migration/rollback before authorizing persistent company storage.
2. Independently approve official v0.3.0, bound to exact source revision/hashes.
   Migrate catalog root/version/pins, manifests and fixtures with old-version
   rejection tests. Multi-admin metadata remains separate from the shared
   single-admin company-profile wire schema.
3. Separately migrate/retest engine trust anchors, schemas/descriptors/contexts,
   dependency pins, ABI, output binding, cancellation and native cleanup. Obtain
   independent execution-engine approval.
4. Independently approve each operation and host authentication adapter, actual
   tenant/account, service permissions/effective RBAC, and release integration.
   Live Microsoft sign-in and tenant execution require separate explicit authority.

## Validation and limitations

**PASS: final full-windows-09 — 228 tests, zero failures/errors/skips.**
54 new tests plus 174 existing tests, Python 3.14.5 / PySide6 6.12.0 on Windows.
Full-windows-08 also passed 228 before final status-label height adjustment.
Final automated scale reports use scale-final-125 and scale-final-15, selecting
eleven responsive/navigation cases each. Physical desktop/DPI and assistive
technology acceptance: **NOT RUN**. Native exception diagnostic 0x8001010d is
retained in logs and reproduced with the entry launcher; processes completed with
pytest results. See attempts.md for failed attempts and bounded diagnoses.

Coverage includes sorting/search, company/tenant/admin duplicates, identifiers,
default handling, temporary metadata reload, secret/unknown-field rejection,
company/admin/hint/profile switching, expiry, account/tenant/generation/target
mismatch, independent service failures, no network/process dispatch, Notes
document/cursor/image/save/session/HUD/split/shortcut regressions and hidden polling.

Reproduce with a new output location; do not overwrite retained evidence:

```powershell
$env:QT_QPA_PLATFORM = 'windows'
$env:PYTHONDONTWRITEBYTECODE = '1'
.venv/Scripts/python.exe -B -m pytest -q -p no:cacheprovider
.venv/Scripts/python.exe -B docs/reviews/m365-company-directory-20261102/verify_candidate.py
```

## Independent reviewer handoff

Start a fresh read-only review at this checkout. Follow AGENTS.md and GEMINI.md
revision 2. Do not modify code, contracts, Notes, production data, engine, pins,
existing evidence or Git state. Review is not storage/auth/engine/live approval.

1. Run verify_candidate.py. Bind review to base and candidate-inventory raw hashes;
   stop applicability on mismatch. Inspect full new files and four entry diffs.
2. Inspect the complete authority package and distinguish matching candidate hashes
   from effective approval. Confirm catalog/engine remain proposed-version consumers.
3. Challenge stable IDs, duplicate normalization, admin/default lifecycle, unknown
   metadata field rejection, timestamps and secret-free exchange. Keep synthetic
   temp-adapter reload separate from production persistence acceptance.
4. Challenge all context invalidation paths, independent Graph/Exchange expiry,
   tenant/account/target binding, admin versus client identity, domain hints and
   explicit company confirmation. Ensure fixture state cannot become verified or
   dispatch, including clicks, Return, operation double-click and account switching.
5. Check no UI SQL/process calls, second engine, Qt/SQLite in portable services,
   Note persistence edits, production DB access or F7Hub changes. Validate the
   fourteen categories and existing Notes regressions with isolated databases.
6. Review failure history and final tests. Inspect accepted synthetic renders,
   dynamic identity labels, keyboard access and 640/800/1100 widths. Automated
   scaling/screenshots do not establish physical or accessibility acceptance.
7. Write a new independent report bound to exact candidate identity, with severity,
   path/line, reproduction, expected/actual and literal PASS/FAIL/BLOCKED/NOT RUN.
   Keep Phase A review, storage gate, contract, engine, operation and live authority
   separate. No approval or publication is inferred from this checkpoint.
