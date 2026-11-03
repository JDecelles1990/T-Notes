# Entra ID / User Identity — provisional operation-development foundation

Disposition: **POWERSHELL OPERATION PROTOTYPE — READY_FOR_INDEPENDENT_REVIEW**.
This disposition applies only to the guarded offline reference and tests. The
shared contract, execution engine, operation release and live Graph integration
remain unapproved. Nothing here grants production execution authority.

Stable ID: `M365.ENTRA.USER_IDENTITY`. Contract: `tnotes.m365 / 0.3.0-proposed.1`.
Guidance read: root AGENTS.md, root GEMINI.md (`TNOTES-GEMINI-PS`, revision 1),
scripts/m365/README.md, corrected CONTRACT.md, all seven schemas, user-snapshot.md,
security-and-execution.md and the provisional offline ENGINE_CHECKPOINT.md.
The explicit task authorizes provisional references, not approval or integration.

## Files and execution boundary

| File | Purpose |
|---|---|
| Get-UserIdentity.ps1.reference | Worked identity reference with exact ABI and an unconditional execution guard |
| Operation.Template.ps1.reference | Reusable ABI/result/cancellation/host-ownership skeleton |
| operation.design.json | Inert design metadata, deliberately not a manifest |
| COMPATIBILITY.md | Contract mapping, provider design and unresolved approval gates |
| tests/fixtures.json | Synthetic context, provider data, errors and adversarial cases |
| tests/OfflineHarness.ps1 | Fixed-path AST checks, read-only binding and isolated synthetic provider runspaces |
| tests/UserIdentity.Tests.ps1 | Table-driven Pester tests plus template/binding checks |
| tests/Run-OfflineTests.ps1 | Offline Pester runner and synthetic evidence export |
| tests/validate.py | Pinned local schema/descriptor checks and fresh PS7/Pester evidence |
| tests/evidence/ | Entry identities, immutable attempts, diagnosis and preservation evidence |
| SHA256SUMS.json | Exact raw-byte file inventory; excludes itself |

All additions stay in this directory. The task explicitly colocates tests here,
overriding the reserved root README's future central test-directory convention.
Documentation is colocated for the same explicitly restricted scope; no root
README, AGENTS, shared schema, engine, GUI, database or Notes file is changed.

Neither reference has a `.ps1` executable suffix. Both have the exact mandatory
Context/Parameters/CancellationToken signature and immediately throw
`PROVISIONAL_REFERENCE_ONLY`, including when compiled or dot-sourced directly.
Only the test harness removes that exact AST-verified guard in memory. It binds
recursively read-only maps/lists in a fresh runspace with module autoload disabled
and defines a fixed synthetic Get-MgUser stub. The missing-module case deliberately
defines no stub; it cannot autoload Graph. No real SDK is imported. The harness's
command inventory is a review aid, not a hostile-code security sandbox.

The design JSON intentionally has no script_path, executable SHA, approval marker
or production trust pin. Schema validation builds a synthetic manifest projection
in RAM using the shared example's non-approving placeholder hashes. That projection
is neither saved nor registered. The production catalog remains unchanged/empty.

## Tests

Use the existing repository environment; do not install dependencies automatically:

```powershell
.venv/Scripts/python.exe -B scripts/m365/entra-id/user-identity/tests/validate.py
```

The validator invokes the installed `pwsh` with `-NoLogo -NoProfile -NonInteractive`.
It writes a unique `tests/evidence/validation-<UTC>-<nonce>.json`; existing reports
are never replaced. It validates the local schema registry, context, descriptor
semantics, design projection, every actual operation_return and non-null identity
payload. It also rechecks the entry identities of all read planning inputs and
catalog/guidance files. No engine dispatch or contract validation script is run,
because those scripts can write outside this operation directory.

The standalone PowerShell entrypoint is:

```powershell
pwsh -NoLogo -NoProfile -NonInteractive -File scripts/m365/entra-id/user-identity/tests/Run-OfflineTests.ps1
```

JSON from this test runner is synthetic test evidence. The operation references
never serialize JSON. The runner uses installed Pester; absent Pester is explicitly
NOT RUN and is not silently replaced by a claimed Pester pass. Its independently
named offline assertions may still run. Pester 3.4.0 on PowerShell 7.6.9 is the
tested combination; Pester 5 compatibility and an SDK support matrix are unverified.

Tests cover UPN/object ID, guest and dollar-prefix UPN argument preservation, NFC,
invalid identifiers/parameters/context, wrong tenant/account/generation, absent or
expired leases/scopes/module, found/not-found/denied/throttled/unavailable results,
missing/null properties, false account status, malformed/multiple provider results,
target contradictions, cancellation before/after/during a call, sanitized expected
and unexpected errors, strict arrays, exact argument/property selection, recursive
immutability, non-dispatchability and allowlisted privacy-preserving output.
Mocked escaping cases prove argument preservation only, not real SDK URL escaping.

## Independent Gemini review

1. Work read-only against exact SHA256SUMS.json identities. Verify its own digest
   against the handoff, and rehash every listed artifact before review. Read
   tests/evidence/entry-preservation.json and the preservation report; distinguish
   concurrent Notes changes from this operation's allowed scope.
2. Read the corrected contract and all referenced schemas at the recorded hashes.
   Do not promote drafts, regenerate engine anchors or approve this operation.
3. Inspect the reference guard, ABI, defensive preflight, target equality, bounded
   read call, null/partial semantics, exception sanitization and cancellation.
   Check the harness cannot fall through to installed Graph commands.
4. Re-run validate.py only if fresh offline evidence is authorized; it writes only
   a new report inside this directory. Preserve failures and source identities.
   Report actual Pester/runtime versions and distinguish mock PASS from native
   Graph/tenant/engine integration NOT RUN.
5. Review creation-date omission and accountEnabled permission limitations. A
   shared schema change or additional permission requires a separately approved
   task; do not fix either by broadening this implementation.
6. Report blockers and exact affected lines/hashes independently. Do not edit the
   author evidence, Notes/GUI/engine/contracts/S001/S002, install dependencies,
   authenticate, register an operation or stage/commit/push/merge.

Subsequent authorization must separately approve the shared contract and engine,
the operation's exact executable/manifest/dependencies, real host-owned Graph
authentication/permission verification, native synthetic-tenant/module behavior,
SDK error/escaping behavior, deadline cleanup and any catalog/application wiring.
