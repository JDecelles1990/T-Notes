# Provisional offline engine checkpoint

Disposition: **ENGINE READY FOR INDEPENDENT REVIEW**.
Implementation remains **PROVISIONAL OFFLINE** pending independent approval.
Contract: `tnotes.m365 / 0.3.0-proposed.1`, pending independent approval.
All implementation is confined to this directory. No production M365 operation,
authentication adapter, GUI, SQLite or active-note integration exists here.

## Saved implementation

| File | Purpose |
|---|---|
| host.py | Public Engine/Execution API, pinned catalog, external-anchor checks, local schema helper, dispatch, response validation and safe host failures |
| contracts.py | Strict parser, normalization, calendar checks, parameter binding, target/context/result binding, logical exits and sanitization |
| win_process.py | Windows read-pinned files/ancestors, suspended startup, owned Job Object, async bounded IO, cancellation, deadline and verified cleanup |
| worker.ps1 / protocol.ps1 / schema-check.ps1 | Fixed test adapter, immutable ABI binding, bounded cancel control reader and pinned local Draft 2020-12 validation |
| scripts/Fixture-Operation.ps1 | Deterministic ABI fixture only; success/error/partial/wait/immutability/pipeline-error cases; no service calls |
| manifest.json / catalog.json / trust-anchor.json | Explicit synthetic manifest, executable/asset allowlist and externally supplied expected-anchor identity |
| synthetic-context.json | Fixed synthetic company/tenant/account/generation; no real connection verification |
| tests/test_engine.py / run_tests.py | Real Windows/Python/PowerShell integration tests, isolated semantic tests and immutable per-attempt evidence |
| tests/fixtures/Fault-Worker.ps1 / Child-Sleeper.ps1 | Adversarial protocol and descendant-cleanup fixtures; never production operations |
| prepare_fixtures.py | Explicit development-only authoring of pinned synthetic assets; never invoked by the host |
| examples/ | Valid request and actual schema-valid synthetic success/error/partial response examples |

The final exact inventory and SHA-256 values are saved in
evidence/implementation-inventory.json. Generated negative manifests, catalogs and
anchors are inspectable fixtures, not independent approval or normal application
configuration.

## Readiness and compatibility

- Gate 1: 21 corrected contract artifact hashes independently recomputed by the
  implementation task; all match. B1/B2/B3/I1-I4 are COMPLETE per saved handoff.
- B1: exact Context/Parameters/CancellationToken names and read-only nested types;
  one operation_return and one adapter-owned wire envelope. Native fixture proves
  string/integer and nested immutability; other parameter kinds have semantic tests.
- B3/I2: schema-valid metadata, explicit target kinds, local payload definition,
  pinned release binding, typed/default/bounds/enum/duplicate validation. Only the
  synthetic Graph lease and no-module test fixture are supported; other service
  requirements fail closed.
- I1/I4: UTC Z, real calendar checks, monotonic host duration, UPN/object-ID return
  equality and exact correlation/context/release binding. No workflow or persistent
  history service is implemented.
- I3: executable, local asset and dependency hash checks with Windows read-pinned
  handles. Synthetic context is explicitly simulated. Real Graph/Exchange auth and
  effective permission validation are unsupported and cannot be inferred here.
- B2: deliberately outside this engine; no notes, images, saves or storage APIs.
- Cancellation: matching contract cancel_control, idempotent terminal cause, no
  rollback/automatic retry. Persistent session reuse is unsupported; each dispatch
  uses a fresh owned worker and normal idle-EOF shutdown.

## Actual evidence and preservation

**PASS — final suite: 38 tests, 0 engine failures**, using actual Python 3.14.5 and
PowerShell 7.6.9 on Windows. This includes real cross-process tests plus focused
parameter/parser/file-lock checks; it is not a claim of 38 live M365 operations.
Final immutable report: evidence/tests-20261102T234813Z-52f6c56b.json.
Exact command: installed Python with -B and this directory's run_tests.py;
the complete argv, per-case telemetry and timings are retained in that report.

Earlier complete attempts (34 PASS and 38 PASS) and the two failing smoke attempts
remain preserved. A later smoke test passed its engine case but the aggregate
entry preservation gate failed; that historical FAIL was not relabelled.
See evidence/DIAGNOSES.md. The final report explicitly separates engine status
PASS from full-entry byte preservation FAIL. All 21 contract hashes still match.

The native cleanup test observed four owned processes (worker, console hosts and
synthetic child) and verified zero active processes after forced cancellation.
Cooperative cancellation and timeout also verified zero remaining job processes.
Structured errors/partial responses retained logical exits 20/2 with OS exit 0;
a test crash retained OS exit 23 while rejecting the pending success.

The checkpoint and diagnostic narrative were finalized after the native run.
No engine code, executable fixtures or pinned configuration changed after that
run. Use implementation-inventory.json for final document identities and the
native attempt for the exact tested runtime identities.

All 21 contract artifacts and original contract validation/review evidence are
preserved. Root GEMINI.md and the unrelated dirty ADR 0007 retain their entry bytes.
The broad entry-byte preservation check found eight canonical UI/docs/test files
changed concurrently outside this prototype. They are listed with entry and
observed hashes in test evidence. Neither LF nor CRLF normalization accounts for
the drift. This agent did not write those files and did not revert them; their
origin is not established. Preserve that observation as FAIL for full byte
preservation, separately from the engine test result. Do not claim all canonical
source bytes were unchanged.

## Limits and independent Gemini review

This is an author-tested PROVISIONAL OFFLINE ENGINE, not independently verified or
production ready. Windows Job Objects are owned-process cleanup, not a hostile-code
sandbox. Runtime trust covers the declared installed files, not the entire OS or
every possible external broker. Pattern-based redaction is not universal secret
detection; no raw stderr or provider exceptions are retained. Only pinned synthetic
identities/targets may be used. No runtime download/install or automatic trust
refresh is permitted. A single Engine instance permits one call at a time; app-wide
coordination and persistent worker reuse remain future work.

Gemini should review read-only: recompute the 21 contract hashes and final inventory,
inspect both Python and PowerShell validation/error paths and every Windows ownership
cleanup path, then run the README command against the existing pins. Do not run
prepare_fixtures.py to make mismatched trust pass. Preserve every failed attempt;
report engine test outcomes, preservation drift and unsupported/live gates separately.
Save a new independent report bound to exact reviewed hashes. Do not alter the
original CHANGES_REQUIRED review, corrected contract, S001/S002 or production app.

After explicit user approval only, a future application service may wrap Engine
outside the Qt main loop. Keep Graph and Exchange auth adapters, company selection,
SQLite and note insertion separate. Review approval alone grants no integration,
tenant execution, commit, push or merge authority.
