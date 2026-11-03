# Framework checkpoint at priority change

Status: **PARTIAL IMPLEMENTATION — CHECKPOINT_SAVED**.
The user redirected this session to official contract promotion before the
framework's documentation, portability guide and independent-review handoff were
finished. This checkpoint does not mark that earlier assignment complete.

Implemented files: validate_operation.py, Inspect-Operation.ps1,
test_validator.py, run_tests.py, Framework.Tests.ps1, Run-FrameworkTests.ps1.
Entry identities: entry-preservation.json. Evidence and diagnosis: evidence/.

Actual final framework run before redirection:
`evidence/tests-20261103T010321.045889Z-b8f74e31.json`: 38 Python tests PASS;
Pester 3.4.0: 2 PASS; Python 3.14.5; PowerShell 7.6.9.
Earlier 30-test attempt had 2 failures, retained with its diagnosis.
`evidence/user-identity-attempt-01.json`: structural/synthetic PASS,
VALIDATED_CANDIDATE, dispatchable=false. No operation execution occurred.

CLI from repository root:

```powershell
.venv/Scripts/python.exe -B scripts/m365/tooling/operation-validation/validate_operation.py --package scripts/m365/entra-id/user-identity --library-root scripts/m365 --contract-root docs/planning/m365/03_codex_reviews/architecture-contract-proposal-20261102 --contract-pins assets/m365/contract-review-pins.json --report "$env:TEMP/user-identity-new-attempt.json"
```

The report destination must be new and outside immutable packages. Exit codes:
0 PASS, 1 FAIL, 2 required dependency NOT RUN. JSON reports include per-category
checks, hashes, runtimes, blocking findings, candidate disposition and explicit
non-dispatchability. Local static checks cannot prove security or authorization.
No production approval verifier exists: APPROVED_RELEASE requests reject.
Installed Graph module hashes/live SDK compatibility remain NOT RUN.

Compatibility is EXACT `tnotes.m365 / 0.3.0-proposed.1`. Official v0.3.0 migration
is pending, including the test suite's canonical-root constant. Do not change
historical operation bytes or pins to make mismatches pass. The historical
proposal path above remains the compatible input after canonical promotion.
The framework imports no app/UI/SQLite modules and owns no authentication.
Future F7Hub adoption still requires independent review and host/trust adapters.
