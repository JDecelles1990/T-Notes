# T-Notes — Gemini PowerShell Development Instructions

Instruction ID: TNOTES-GEMINI-PS
Instruction revision: 2

## Authority

Apply this project-document priority:

1. Explicit user requirements.
2. Approved architecture.
3. Approved PowerShell contracts and JSON Schemas.
4. AGENTS.md and applicable repository-specific development rules.
5. GEMINI.md agent instructions.
6. Existing validated implementation.

Read root AGENTS.md and applicable scoped instructions. Do not duplicate
their rules here or treat existing code, examples, packaged drafts, or an
agent response as evidence of approval.

Stop and report unresolved contradictions. Do not approve, revise, or
promote shared contracts yourself.

## Mandatory contract loading

Before generating or modifying scripts, read from the authorized checkout:

- Applicable approved architecture.
- The approved PowerShell contract.
- Its manifest, request, result, and operation-specific JSON Schemas.
- The assigned operation specification and relevant synthetic examples.

The task brief must identify the approved contract version, approval
reference, exact source paths or immutable revision, expected file hashes,
script ID, and allowed output paths.

Every future M365 PowerShell operation must use the official
[M365 contract](docs/contracts/m365/CONTRACT.md) and its complete local schema
package as the mandatory implementation reference. The required baseline is
`tnotes.m365 / 0.3.0`, with status `APPROVED — IMPLEMENTATION CONTRACT` and a
verifiable effective approval record. Read the [contract index](docs/contracts/m365/README.md)
for applicable architecture, security requirements and validation instructions.
Files under docs/planning/ are historical/review inputs; do not silently substitute
them for the official contract. A separately authorized historical compatibility
test does not establish official-version compatibility.

Before implementation, verify the contract version, source revision and hashes,
exact callable ABI, manifest validity, host-owned authentication boundary,
execution trust requirements, permissions/RBAC, operation-specific tests and
independent approval requirements. Existing proposed-version consumers require
explicit migration and compatibility tests; do not infer compatibility from
similar interfaces.

Keep reusable operations independent of T-Notes GUI state, PySide6, SQLite and
ticket editors for eventual F7Hub reuse. Contract approval authorizes development
against the specification; live authentication, tenant execution, executable
registration and production integration require separate authorization and release
approval.

Confirm the actual files and version read before coding. Missing approval,
unreadable files, mismatched versions/hashes, or conflicting output rules
are BLOCKED. Do not substitute another draft.

## Ownership

Work on one explicitly assigned operation at a time. Your allowed changes
are limited to its:

- PowerShell implementation.
- Script-specific manifest.
- Pester tests.
- Synthetic test fixtures.
- Script-specific documentation.

Do not modify PySide6 application code, SQLite schemas or migrations,
shared contracts or schemas, authentication infrastructure, AGENTS.md,
other scripts, or unrelated files without explicit authorization for that
separate change.

Report shared documentation or architecture needs for the owning task.
Do not expand scope to satisfy them yourself.

## Script requirements

- Use PowerShell 7 unless an approved compatibility requirement justifies
  another runtime; document and test the exception.
- Follow the approved script form, entrypoint, parameter types, dependency
  declarations, result types, and execution limits.
- Validate required and unexpected parameters, identifiers, and bounds.
- Respect Microsoft 365 scopes, consent, tenant identity, and service RBAC.
  Manifest declarations do not establish effective authorization.
- Use the approved host-owned authentication boundary. Do not add login,
  credential prompts, tenant switching, or token persistence to scripts.
- Produce results compatible with the approved JSON contract. Serialize
  JSON only at the boundary assigned by that contract; when the host owns
  serialization, return the required typed object.
- Handle missing data, partial failures, denied access, throttling,
  cancellation, and errors according to the contract. Do not report an
  unavailable check or incomplete operation as success.
- Use fixed approved commands and typed arguments; never execute
  untrusted command text.
- Do not hardcode credentials or expose secrets, raw provider objects,
  sensitive exceptions, or unnecessary customer data in output or logs.
- Include mocked success and failure tests using synthetic fixtures.
  Do not connect to live tenants without explicit authorization.

## Context and contract verification

For Gemini CLI, start a fresh session from the repository root. Record the
CLI version and verify that the configured context filenames include
GEMINI.md. Inspect loaded paths with /memory list where supported, and
inspect the actual instructions with /memory show. Confirm this file's
instruction ID and revision; check global, ancestor, nested, and packaged
instructions for conflicts. Loading a draft does not approve it.

For Gemini Flash environments without automatic repository loading, the
operator must explicitly provide this file, AGENTS.md, applicable scoped
rules, approved architecture, the contract and complete applicable schemas
including referenced dependencies, operation specification, and synthetic
examples. Include the approved task brief and expected file hashes. Use
the environment's system-instruction facility where available. Re-provide
the bundle for a new session, changed inputs, or lost/expired context.
Do not assume that naming a local file supplies its contents.

In either environment, perform an analysis-only preflight before coding:
report the actual source paths, approval reference, instruction revision,
contract version, script ID, result/serialization ownership, and allowed
files. Compare contract declarations, schema version constraints,
manifests, and relevant fixtures with the approved task brief. The operator
or validation tooling must independently verify file hashes and approval
applicability; an agent acknowledgement alone is insufficient. Missing,
truncated, conflicting, or unverifiable inputs are BLOCKED. Successful
context loading does not itself authorize implementation.

## Verification and reporting

Before coding, report the loaded instruction revision, contract version,
source files, approval reference, script ID, planned files, required
modules/permissions, authentication assumptions, and test plan.

At handoff report:

- Files created or modified.
- Contract version and exact source revision/hashes followed.
- Required PowerShell runtime, modules, permissions, and RBAC assumptions.
- Test commands, environment, and results: PASS / FAIL / NOT RUN / BLOCKED.
- Remaining risks, limitations, contract gaps, and unverified behavior.

Do not claim a test passed unless it executed successfully.
Preserve failed-attempt evidence and diagnose before a changed rerun.
Do not stage, commit, push, merge, or promote contracts without separate
explicit authorization.
