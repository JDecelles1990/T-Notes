# First PowerShell operation reference — author checkpoint

Disposition: **POWERSHELL OPERATION PROTOTYPE — READY_FOR_INDEPENDENT_REVIEW**.
Scope: guarded non-dispatchable references and offline tests only. Not production
approval, independent acceptance, live SDK compatibility or engine integration.

## Final validation

- PowerShell **7.6.9**, existing **Pester 3.4.0**.
- **PASS: 60 Pester tests, zero failures**, including 58 synthetic operation cases,
  one reusable-template ABI/guard check and one recursive-binding/direct-guard check.
- **PASS: 58 separately evaluated offline cases**, each returning one typed object
  without incidental streams, plus local schema/design/descriptor checks.
- **PASS: 72 combined compatibility checks** in the final report.
- Final report: tests/evidence/validation-20261103T004733Z-2975eabb.json.
- Report SHA-256: `34b59e01a2606445d3e34717671e1acf4ea9b0afb623d4c418cf98fd0704c070`.
- Exact command: `.venv/Scripts/python.exe -B scripts/m365/entra-id/user-identity/tests/validate.py`.
- The Python runner's exact pwsh argv, source/input hashes, runtime, Pester totals,
  operation returns and timestamps are preserved in that immutable report.
- Earlier failures and intermediate passes are retained; see tests/evidence/DIAGNOSES.md.

## Tested reference identities

| File | SHA-256 |
|---|---|
| Get-UserIdentity.ps1.reference | f9037639c3c5b49477bbd9bd137a9435df2cc7533b604356deffbdf4e947f6ae |
| Operation.Template.ps1.reference | a03b3d2b56e5839712eb9f56fd41c37b7088e61de0d211e05a4527ef59bdc722 |
| operation.design.json | 520894bc868640a0708639c5b7f0d2ef48023977ca6dbbeba6249927c20bf111 |
| tests/validate.py | ec823cf1be675b84007abd46619331edf3bb1a8e0014f84473ca25a7972a0c63 |

SHA256SUMS.json supplies the complete raw-byte inventory, including synthetic
fixtures, tests, read-input identities, documentation and retained evidence. Its
own hash is supplied separately in the final handoff to avoid a self-hash cycle.
No hash in this package is a production trust pin or release approval.

## Preservation

tests/evidence/preservation.json records **PASS** against task entry: 209 existing
repository files and 64 S002 files matched byte-for-byte. Branch main, HEAD
30eef020e9ef6162ea10321db6741046e7aa2a88 and raw index bytes matched entry.
This includes existing contracts/engine files, root GEMINI.md, dirty ADR 0007,
the Notes/GUI code and existing catalog files. No S001 checkout was accessed or
modified; a separate S001 byte baseline was not captured. No staging, branch,
worktree, commit, reset, cleanup, merge, push or database mutation was performed.
All created artifacts belong to this one previously absent operation directory.

## Remaining limits and next review

- **BLOCKED PORTION: creation-date output.** The current user_identity schema
  permits exactly five fields and prohibits extras. The reference requests/returns
  only those five; a creation date needs separately authorized schema/version work.
- **NOT RUN / NOT VERIFIED:** real Microsoft.Graph.Users import/version matrix,
  tenant authentication, real Graph requests, consent/effective scopes/RBAC,
  accountEnabled visibility, guest/dollar-UPN SDK escaping, native provider error
  shapes, real deadline cleanup and engine/GUI/case-note integration.
- Declared module minima and User.Read.All are proposed metadata, not proof of
  prerequisites or authority. No extra write-capable permission is acquired.
- The host owns authentication and live lease verification before invocation and
  acceptance, timeout arbitration, the wire envelope and JSON serialization.
- Contract, engine, operation release/dependencies and any production integration
  require separate independent review and explicit authorization.

Gemini review instructions are in README.md. Review exact bytes read-only; retain
fresh evidence under this operation only if authorized; do not change Notes work,
shared contracts, engine anchors, GUI, S001/S002 or the empty production catalog.
