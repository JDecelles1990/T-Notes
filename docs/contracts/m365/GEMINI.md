# T-Notes M365 script-agent handoff — proposed review copy

Instruction ID: TNOTES-M365-PROPOSAL. Status: PROPOSED, not implementation authority.
Installed root GEMINI.md remains unchanged. This file is for review and explicit
provisioning after approval; loading it does not approve any contract.

## Authority and inputs

Follow explicit user requirements, approved architecture, approved PowerShell
contracts/JSON Schemas, AGENTS.md/scoped rules, GEMINI.md, then validated code in
that order. Read root rules rather than duplicating them. Stop on contradictions.

Before generating/modifying scripts, read the approved contract, all applicable
manifest/request/result/error/data schemas and referenced dependencies, operation
spec, relevant architecture and synthetic examples from the authorized checkout.
Require an approval reference, expected exact version/source hashes, stable script
ID and allowed paths. Report actual inputs read. `0.3.0` in this package
is an official release candidate, not final approval. Missing, unapproved, mismatched or truncated inputs
are BLOCKED. Do not choose a different draft or silently change shared definitions.

## Scope

Implement only one assigned PowerShell operation, its manifest, script-specific
Pester tests, synthetic JSON fixtures and script documentation. Do not edit GUI,
PySide6 internals, database schemas/migrations, authentication infrastructure,
shared contracts/schemas, root instructions or unrelated scripts/files without
explicit authorization for a separate task. A separately authorized GUI task is
not permission to change any other boundary.

Use PowerShell 7 unless approved compatibility requires otherwise. Validate typed
parameters/targets/bounds and required modules, scopes, tenant and service RBAC.
Use host-owned authentication; no Connect commands/password prompts/token storage
inside operations. Never hardcode credentials or expose raw SDK objects, sensitive
errors/logs or customer fixtures. No live tenant operation without authorization.

Follow the **approved** script/host ABI: this proposal uses one .ps1 returning one
typed operation_return (status, operation_outcome, data, warnings, errors) using
the exact Context/Parameters/CancellationToken signature in CONTRACT.md; only the
fixed host adapter emits the JSON envelope. Preserve read-only nested context,
owned service leases, target_policy and manifest-selected payload binding.
Never mix serializers, write banners/progress to stdout, execute user expressions,
or access T-Notes SQLite/notes. Return partial/error/timeout/cancel semantics safely;
unknown remote effects are not rollback or retry permission.

Require mocked Pester success/failure tests, zero-provider-call assertions on
invalid context, exact typed arguments, denied/not-found/partial/throttled cases,
stable arrays/nulls, cancellation and safe output. Validate final wire and typed
data against approved schemas at the host boundary. Never claim unexecuted tests
passed. Preserve failed attempts and diagnose before a changed rerun.

## Context loading and handoff

CLI: start at repository root; record CLI version and configured context files;
inspect /memory list where supported and /memory show for the expected instruction
ID/revision and conflicting global/nested/package rules. Flash/web: operator must
explicitly supply instructions, AGENTS, approved architecture, full contract/schema
bundle, operation spec, synthetic examples and approval/version/hash inventory
each session. Naming local paths is not file provisioning. Re-provide lost/expired
context. See AGENT_HANDOFF.md for the full procedure and official references.

Before coding, report actual version/files, script ID, result ownership, scope,
modules/permissions/RBAC and test plan. Operator/tooling independently verifies
hashes and approval. At completion report files created/modified, exact contract
version and source identities, runtime/modules/permissions, commands/environment
and PASS / FAIL / NOT RUN / BLOCKED results, risks and limitations. Do not stage,
commit, push, merge or promote contracts without separate authorization.
