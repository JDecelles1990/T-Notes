# Agent governance and independent review handoff

Status: **RELEASE CANDIDATE — INDEPENDENT REVIEW REQUIRED**.
Required status after independent release approval: **APPROVED — IMPLEMENTATION CONTRACT**.
Read CONTRACT.md, README.md, RELEASE_APPROVAL.md, and all authoritative schemas.
Official contract version: `0.3.0` (promoted from `0.3.0-proposed.1`); pending independent review.

## Ownership and instruction relationship

Priority: explicit user requirements → approved architecture → approved
PowerShell contracts/JSON Schemas → AGENTS.md/scoped rules → GEMINI.md → validated
implementation. Proposed drafts are not approved by their location, version or
inclusion in agent memory. Shared changes need independent review and user approval.

| Owner | Authorized task categories, only when explicitly assigned |
|---|---|
| Codex | PySide6 integration, application services, execution/auth infrastructure, shared contract proposals/governance, integration/regression tests |
| Gemini script agent | One operation script, its manifest, Pester tests, synthetic fixtures and script-specific docs |
| User/independent reviewer | User decides approval and scope; reviewer assesses exact candidate and evidence, not self-approval |

The user separately requested a complete GUI from Gemini. That is a scoped
exception to the default script-agent role, not authority to alter shared schemas,
authentication, SQLite or unrelated code. No delivered GUI was found at inspection;
review any later candidate by exact identity against the approved design and retain
required adjustments as future work. Do not contact the other agent or edit its work.

Root AGENTS.md and installed GEMINI.md revision 1 remain unchanged. The adjacent
GEMINI.md is a proposed handoff copy, not a second installed canonical instruction.
Its presence in nested CLI discovery is a reason to inspect loaded context, never
automatic implementation permission. An operator must select the approved input
inventory and resolve any conflicting global/nested instructions.

## Contract input inventory and context verification

Before script work, supply approval reference, expected exact contract version,
immutable repository revision or exact paths/raw SHA-256s for contract/all schemas
and referenced dependencies, operation spec, script ID and allowed output paths.
Approval must bind semantic decisions as well as bytes. The agent reports actual
files read; operator/tooling independently checks hashes and approval applicability.
No canonical approval registry or file is created by this proposal.

For Gemini CLI: record installed version, start at repo root in a fresh session,
verify configured context filenames, use /memory list where available and /memory
show, inspect instruction ID/revision and global/ancestor/nested/package conflicts,
then require analysis-only contract/version/ownership preflight. Do not use /memory
add to turn an unapproved draft into a persistent rule. Successful loading does
not authorize code. [CLI context](https://geminicli.com/docs/cli/gemini-md/),
[CLI command reference](https://geminicli.com/docs/reference/commands/).

For Flash/web without repo loading: explicitly attach/paste this instruction set,
AGENTS/scoped rules, approved architecture, full contract and applicable schemas,
operation spec and synthetic examples, plus version/hash/approval inventory. Local
filenames alone provide no content. Use available system instructions; re-provide
on new session, revision, expiry or lost context. Require the same preflight.
Do not upload customer data or credentials. [System instruction capability](https://ai.google.dev/gemini-api/docs/text-generation#system-instructions).

## Independent review checklist

1. Reverify branch/HEAD, source snapshot, preservation identities and exact changed
   package inventory; distinguish concurrent GUI/source changes from this proposal.
2. Review all D01–D15 choices, especially editor/cache ownership, strict service
   boundaries, typed script/host ABI, tenant verification and unknown outcomes.
3. Recompute artifact hashes; inspect every schema definition/ref and actual
   result files, including failed attempts; run sufficient fresh offline validation.
4. Challenge fixtures with wrong tenant/admin generation, stale confirmation,
   invalid/extra output, tampered metadata, traversal and secret-bearing content.
5. Verify output semantics, exit mapping, dependency versions, typed payloads and
   partial aggregation; do not mistake reference test helpers for production code.
6. Inspect applicable Microsoft/Qt references and classify native/live/Pester/GUI
   gates as NOT RUN until actually exercised. No approval from empty test results.
7. Record findings and approval recommendation in a new independent report bound
   to exact files/version/hashes. Do not overwrite prior reports or mutate this
   candidate during read-only review.

The next gate is independent read-only review and explicit user decisions. User
approval of a design alone does not authorize runtime implementation, promotion,
Git publication or tenant execution. No commit, push, merge or deletion here.

## Author self-review

Author review found and corrected a fixture inconsistency: the successful mailbox
example had a null quota while the proposed semantics require a partial warning
for unavailable size/quota. Complete-success fixtures now use synthetic numeric
bytes; negative/partial property checks cover both mailbox fields and unavailable
account status. A baseline inventory count was corrected to 17 pre-existing M365
files. All validator failures remain preserved and explained in the validation
document. Remaining D01–D15 decisions and native/live gates are explicit; this
self-review is not independent approval.
