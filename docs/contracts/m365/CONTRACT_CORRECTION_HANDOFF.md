# Contract correction checkpoint

Status: **CONTRACT_CORRECTED — READY_FOR_REVIEW**
Contract: `tnotes.m365 / 0.3.0-proposed.1`. Date: 2026-11-02.
Scope: existing proposal and offline validation assets only; approval, canonical
promotion and implementation remain separate gates.

## Exact files changed

All paths below are relative to this checkpoint's directory. Entry identities
are in `validation/correction-baseline.json`; fresh candidate identities are in
`validation/correction-results.json` (artifacts array).

Modified existing files:

- `AGENT_HANDOFF.md`
- `CONTRACT.md`
- `GEMINI.md`
- `README.md`
- `examples/fixtures.json`
- `schemas/common.schema.json`
- `schemas/company-profile.schema.json`
- `schemas/error.schema.json`
- `schemas/execution-request.schema.json`
- `schemas/execution-result.schema.json`
- `schemas/operation-data.schema.json`
- `schemas/script-manifest.schema.json`
- `security-and-execution.md`
- `user-snapshot.md`
- `validation-and-roadmap.md`
- `validation/validate_contract.py`
- `workspace-architecture.md`

New files, including generated evidence:

- `CONTRACT_CORRECTION_HANDOFF.md`
- `examples/mock-compatibility.json`
- `validation/correction-baseline.json`
- `validation/correction-results-20261102T231348-70847299.json`
- `validation/correction-results-20261102T231941-41d04d19.json`
- `validation/correction-results.json`
- `validation/correction_checks.py`

## Finding completion

| Finding | Status | Saved correction |
|---|---|---|
| B1 | COMPLETE | Exact Context/Parameters/CancellationToken ABI, immutable typed context, verified account/tenant/owned leases, operation_return, partial/errors, cancellation control frames, shutdown and logical/process outcomes |
| B3 | COMPLETE | target_policy accepts UPN/object ID, resolved identity and payload field binding; required services, scopes, service-qualified role groups, disabled eligibility reasons; synthetic additional script without host ID switch |
| B2 | COMPLETE | Durable current-revision HTML/image SaveReceipt; false Saved forbidden; failed save retains document/images; hidden registry, blocked transitions/Quit and explicit latest-revision Retry |
| I1 | COMPLETE | UTC Z and calendar/parsed-time comparisons, monotonic durations; RAM history covers preflight rejection, auth, queue/run, partial/error/crash/cancel/timeout and separate retries |
| I2 | COMPLETE | Type-applicable descriptor constraints, scalar enums/defaults, array/item bounds, inverted ranges, integer/boolean distinction, case-insensitive duplicates and reserved names |
| I3 | COMPLETE | Separate Graph/Exchange state/ownership/account/expiry/permission interface; external approval/hash/dependency/path/pinned-byte trust interface |
| I4 | COMPLETE | Identity accepts UPN or Entra ID; correct result field equality; downstream exact resolved ID and Exchange directory-ID mapping |

COMPLETE describes contract corrections and offline mock coverage. It does not
assert any production persistence, connection, trust or worker implementation.

## Contract and schema decisions

- Incompatible required fields advance the proposal from 0.2.0-proposed.1 to
  **0.3.0-proposed.1**; no compatibility alias or implicit downgrade.
- Keep exactly seven JSON Schemas. Shared internal mock records are definitions
  in common.schema.json; six entry schemas use the same local reviewed registry.
- Adapter owns serialization, actual verified context, connections, timing and
  logical operation_exit_code. Scripts emit one operation_return object.
- Persistent process exit is separate; cancel control is a bounded, matching
  in-flight frame, never another operation. Unknown effects cannot auto-retry.
- Manifests bind targets, services, permissions, descriptors and selected payload;
  release_binding pins script/version, raw manifest and payload-schema hashes.
  External inventory additionally covers schema dependencies and pinned bytes.
- Notes/images require one original save owner and truthful revision receipt.
  Existing separate writes do not yet satisfy the future durable save contract.
- History is sanitized RAM metadata; durable retention remains unapproved.

## Actual validation

- **PASS** — fresh offline validator; exact check count, command, engine, UTC times
  and per-check outcomes are in `validation/correction-results.json` and the
  immutable final attempt `validation/correction-results-20261102T231941-41d04d19.json`.
- **PASS** — first correction attempt: 578 checks, zero failures, retained in
  `validation/correction-results-20261102T231348-70847299.json`. Final added checks
  cover cancellation matching/arbitration, ABI mapping and runtime/module gates.
- **PASS** — preservation predicates verify all entry files outside the explicit
  correction scope, including source, root GEMINI.md, unrelated ADR 0007,
  previous planning packages, source snapshot and original results*.json.
- **NOT RUN** — production parser/worker, Pester operation scripts, real executable
  trust/ACL/reparse checks, save-failure injection/hidden-editor/Quit behaviour,
  existing application suites, native GUI and live Graph/Exchange authentication.
- **NOT RUN** — independent review of this correction candidate.

The WindowsApps Python alias failed during discovery, before tests; the installed
Python 3.14.5 path from retained evidence was then verified and used. Initial
sandbox write denial was resolved by scoped access. These are environment events,
not passing product tests. All correction attempts and original evidence remain.

## Remaining corrections and next steps

No B1–B3/I1–I4 contract correction is intentionally left open. Independent review
may identify further corrections. D01–D15 approval decisions and future native,
security, persistence and live-service gates remain explicit; do not treat these
requirements as implemented or enable executable actions on this evidence.

1. Gemini performs a fresh independent **read-only** review of this exact bundle.
2. Recompute the final report's artifact hashes and entry preservation hashes;
   read every schema, fixture and both validation modules, not only this checkpoint.
3. Review B1, B3, B2 in that order, then I1–I4. Challenge both accepted/rejected
   target kinds, descriptor contradictions, owned versus foreign leases, stale
   cancellation/generation, schema/hash tampering, partial/crash outcomes and
   failed Save/Quit while editors/images are hidden or pending.
4. Re-run offline validation with the command below if fresh review evidence is
   needed; omit --attempt-name so a new unique attempt is preserved. Do not edit
   contract files or overwrite the original independent CHANGES_REQUIRED review.
5. Report PASS / FAIL / NOT RUN literally, finding IDs and exact path/hash binding
   in a new independent review. Any approval recommendation goes to the user;
   no promotion, scripts, authentication, GUI, migration, commit, push or merge.

```powershell
& 'C:\Users\Jo\AppData\Local\Python\pythoncore-3.14-64\python.exe' -B `
  'docs/planning/m365/03_codex_reviews/architecture-contract-proposal-20261102/validation/validate_contract.py'
```

Protected source, S001/S002 and production notes were not changed. No worktree,
branch, environment, application, backend, commit, push or merge was created.
