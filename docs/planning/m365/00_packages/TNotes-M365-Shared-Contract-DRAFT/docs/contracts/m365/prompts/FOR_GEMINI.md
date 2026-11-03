# Gemini Flash task — One PowerShell script at a time

You are implementing exactly **one** T-Notes M365 script as an isolated deliverable.

BEFORE CODING: Read `AGENTS.md`, `ARCHITECTURE.md`, `docs/contracts/m365/CONTRACT.md` and all three JSON schemas. Read relevant example request/response/manifest fixtures. Confirm actual files were read; if unavailable, STOP and request that the owner provide them.

Report: contract version, script ID, service, required Graph scopes and tenant roles, risk, inputs, return object, errors, tests and exact planned files.

Produce a narrowly scoped, allowlisted `.psm1` PowerShell module containing the manifest-named function only; a manifest conforming to schema; Pester mocked unit tests for success, not-found, permission-denied, invalid input and wrong-tenant behavior; and short usage documentation. Actual authentication belongs to the host adapter. Return typed non-secret `Data` and `Warnings`; do not JSON-serialize or write to SQLite; do not call `Connect-MgGraph` or `Connect-ExchangeOnline` in the script.

No live tenant commands, no hardcoded customer credentials, no password-manager access, no schema or existing GUI/database modifications, no automatic push/merge. STOP and report a contract gap rather than invent a new schema field. Use `PASS/FAIL/NOT RUN/BLOCKED` with test evidence. Independent review required before integration.

FIRST ASSIGNED SCRIPT (when explicitly authorized later): `M365.ENTRA.GET_USER_SNAPSHOT` as specified in `examples/entra-user-snapshot.manifest.json`.
