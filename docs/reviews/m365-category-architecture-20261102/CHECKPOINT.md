# M365 category architecture checkpoint

Final disposition: **CATEGORY ARCHITECTURE — READY_FOR_INDEPENDENT_REVIEW**

Date: 2026-11-02. Author implementation and automated validation only;
independent Gemini review is **NOT RUN**. No approval or publication follows
from this disposition.

## Entry state and authority

Canonical repository: `C:\Dev\T-Notes`, branch `main`, base/head
`30eef020e9ef6162ea10321db6741046e7aa2a88` (merged S001 foundation).
The user authorized this category/catalog implementation in the canonical
checkout and prohibited additional branches/worktrees and Git mutation.

Entry work was dirty: modified `docs/decisions/0007-always-on-top-mini-hud.md`,
untracked root `GEMINI.md`, and untracked `docs/planning/`. Their raw identities
were captured before editing in `entry-state.json` and remain preserved.
No existing planning artifact, contract/schema, engine, S001/S002 checkout,
Notes source, database code or production case-note data was edited.
No stage, commit, push, merge, reset, clean, revert or branch/worktree creation
was performed. The Git index bytes, base and branch remain unchanged.

Read instruction sources: user-supplied task/AGENTS guidance, canonical root
AGENTS.md and GEMINI.md (`TNOTES-GEMINI-PS`, revision 1). Root GEMINI.md scopes
future script generation; this task explicitly authorizes GUI/category work
without generating an operation. Existing root guidance was preserved; the
domain guide supplies the contract/engine references required for this task.

Read technical inputs: corrected CONTRACT.md, CONTRACT_CORRECTION_HANDOFF.md,
security-and-execution.md, all seven applicable schemas and dependencies;
offline engine README.md, ENGINE_CHECKPOINT.md, contracts.py semantic validation,
manifest.json and catalog.json. The latter's test-only trust data was not adopted.

Contract: **tnotes.m365 / 0.3.0-proposed.1, PROPOSED, NOT APPROVED**.
Offline engine: **PROVISIONAL OFFLINE, pending independent approval**.

## Delivered behavior

The final ordered category registry contains exactly:

1. Dashboard (`dashboard`)
2. Companies (`companies`)
3. General (`general`)
4. Entra ID (`entra-id`)
5. Exchange Online (`exchange-online`)
6. Licensing (`licensing`)
7. Teams (`teams`)
8. SharePoint (`sharepoint`)
9. OneDrive (`onedrive`)
10. Intune (`intune`)
11. Security (`security`)
12. Reports (`reports`)
13. Workflows (`workflows`)
14. Other (`other`)

Navigation uses stable IDs, descriptions and icons from JSON. Dashboard/Companies
retain disconnected overview/context views. Categories support metadata search,
risk/lifecycle filtering, useful empty states and plain-text read-only details.
Unapproved entries remain unavailable; invalid entries are quarantined, never
redirected to Other. Conflicting operation IDs are rejected together. Corrupt
catalog configuration falls back to an unavailable panel with Back navigation,
preserving access to Notes.

The production registry is empty. `scripts/m365/README.md` establishes the permanent
root, naming, ownership and future registration/test structure. No empty category
directories, administrative PowerShell files or runnable dummy operations exist.
The test manifest is explicitly synthetic, has no corresponding .ps1, and is never
discovered by production. Presentation index references support one authoritative
manifest appearing in multiple reviewed categories without implementation copies.

Collapsible navigation/ticket placeholders, responsive one/two-column layout and
the existing shared Alt+F8/save/focus boundary remain. Scoped launcher styling
keeps newly introduced native controls dark without changing Notes QSS or behavior.

## Exact implementation inventory

Modified existing files (the full allowed existing-file change set):

- `docs/architecture/system-overview.md`
- `pyproject.toml`
- `requirements.txt`
- `src/ui/m365/launcher_widget.py`
- `tests/test_m365_workspace.py` (only the obsolete disabled/12-category shell assertion)

New implementation, tests and domain documentation:

- `assets/m365/categories.json`
- `assets/m365/catalog.json`
- `assets/m365/contract-review-pins.json`
- `docs/decisions/0009-m365-metadata-catalog.md`
- `docs/features/m365-catalog.md`
- `scripts/m365/README.md`
- `src/services/m365_catalog_service.py`
- `tests/fixtures/m365/README.md`
- `tests/fixtures/m365/manifest.json`
- `tests/test_m365_catalog.py`

All remaining new task files are in this checkpoint directory: entry-state,
candidate-inventory, validation-summary, git-checks and verification JSON; this checkpoint and
read-only verification script; eight attempt log/XML pairs; initial/final synthetic
portrait screenshots. `candidate-inventory.json` enumerates exact paths and raw
SHA-256 values, including all retained evidence. It excludes itself and the
derived `verification.json` to avoid circular identities. Existing unrelated
untracked planning/GEMINI files are entry inputs, not new task deliverables.

An ignored, isolated `.venv` and `.cache/` contain dependencies and synthetic test
data; they are not candidate source or operation library content.

## Compatibility and security findings

- Compatible with the proposed manifest schema without modifying protocol fields.
  New manifests use stable primary IDs in the existing free-text category field;
  optional subcategory metadata does not create navigation nesting. Old proposal
  display labels are not silently remapped.
- All seven schema hashes are bound in contract-review-pins.json and unchanged
  against entry data. Pins establish compatibility-review identity only. The
  empty default catalog needs no runtime planning-schema load.
- Added `jsonschema>=4.23,<5` for Draft 2020-12 validation with a local-only registry.
  Semantic checks supplement shape validation for descriptors, output bindings,
  service requirements and RBAC declarations. No network schema retrieval exists.
- This component is presentation-only: every operation is ineligible, including
  future valid metadata. No executable approval, tenant identity, authentication,
  target resolution, effective scopes/RBAC, runtime/module assurance or dispatch
  adapter is implemented or inferred. The production catalog contains no anchors.
- Current contract connections remain Graph/ExchangeOnline; other service adapters,
  tenant-wide target semantics and declarative workflow schemas require separate
  approval. Categories can be empty while those contracts are developed.
- Library manifests and future scripts are separate from external release approval.
  This validator does not verify executable bytes/ACLs or execution-time races.
  Future authorized boundary is GUI -> application service -> catalog/eligibility
  -> approved Python execution adapter -> trusted PowerShell script.
- No execution controls, engine import, provider calls, authentication, credential
  storage, database migrations, note insertion or second editable Notes owner.

## Actual validation

Environment: Windows 11, Python 3.14.5, PySide6 6.12.0, Pillow 13.0.0,
pytest 9.2.0, jsonschema 4.26.0, referencing 0.37.0. Exact package/environment
and per-attempt argv, timing, module counts and outcomes: validation-summary.json.
All database-backed tests use temporary synthetic fixture databases in `.cache/`.

| Gate | Actual outcome | Retained evidence |
|---|---|---|
| Initial focused offscreen attempt | **FAIL** — 91 passed, 12 failed | focused-01.log/xml |
| Corrected Windows focused attempt | **PASS** — 103 passed | focused-windows-02.log/xml |
| First complete Windows regression | **PASS** — 174 passed | full-windows-03.log/xml |
| Final complete Windows regression after scoped styling fix | **PASS** — 174 passed, 0 failures/errors/skips | full-windows-06.log/xml |
| Final 125% Qt scale responsive checks | **PASS** — 8 passed | scale125-07.log/xml |
| Final 150% Qt scale responsive checks | **PASS** — 8 passed | scale150-08.log/xml |
| Source/entry/S002/Git preservation identities | **PASS** | verification.json and verify_checkpoint.py |
| Whitespace check on changed tracked task files | **PASS** | scoped git diff --check |
| Unscoped repository whitespace check | **FAIL** — inherited blank EOF line in dirty ADR 0007 | entry hash preserved; unrelated file not edited |
| Synthetic portrait rendering | **PASS** — final image inspected | catalog-portrait-final.png |
| Physical monitor/DPI interaction and assistive technology acceptance | **NOT RUN** | Automated Qt scaling is separate evidence |
| PowerShell/engine/tenant execution, authentication and live permissions | **NOT RUN** | Deliberately disconnected |
| Independent Gemini review | **NOT RUN** | Instructions below |

Final suite breakdown: 55 new catalog tests; 53 workspace tests; 66 existing
database, image, scratchpad, stopwatch and UI integration tests. Notes protection
includes original editor/document/undo ownership, pending text/images and save
failure paths, split/history, Mini-HUD, timing, shortcuts, session restoration,
close/quit and Alt+F8 from new catalog controls. No existing behavioral assertion
was weakened beyond replacing the superseded 12-disabled-category expectation.

Failures and diagnoses remain visible. The first attempt exposed an author defect:
the selected output definition delegated to common.schema.json, but the validator
initially checked fields before dereferencing it. Local pinned reference resolution
was corrected before rerunning. Ten other failures involved existing toolbar/focus
assertions with Qt's offscreen backend; the native Windows run passed those exact
tests. Offscreen has not been certified by this task and its failed result is not
relabelled. Initial standalone visual inspection also found native bright control
backgrounds and a removed placeholder pending deferred deletion; scoped dark QSS
and immediate placeholder hiding fixed those. The initial screenshot remains.

Environment discovery found inaccessible WindowsApps Python aliases, a bare installed
interpreter, and an unusable unrelated virtualenv launcher. No tests ran through
those launchers. The first package download was sandbox-blocked (socket error
10013); scoped approved network access installed dependencies only in this repo's
isolated environment. No production application or test installs dependencies.

Reproduce the final full suite with a **new** synthetic temp/output name:

```powershell
$env:QT_QPA_PLATFORM = 'windows'
$env:PYTHONDONTWRITEBYTECODE = '1'
Remove-Item Env:QT_SCALE_FACTOR -ErrorAction SilentlyContinue
& .venv/Scripts/python.exe -B -m pytest -q -p no:cacheprovider `
  --basetemp .cache/category-review-<unique>
```

For responsive checks, set QT_SCALE_FACTOR to `1.25` or `1.5` in a fresh process
and select the two M365 test modules with
`-k 'navigation_ids or narrow_and_portrait or m365_responsive or m365_collapsible'`.
The existing attempt names are immutable evidence; never reuse their basetemp or
report paths. Physical scaling/monitor acceptance remains separate.

## Independent Gemini review instructions

Start a fresh Gemini session at the canonical root, verify root GEMINI.md ID/revision
and applicable instructions, and perform **read-only independent review** of this
exact candidate. This is a category/catalog review assignment, not operation
generation. Do not edit code, root guidance, contracts, schemas, engine, S001/S002,
existing evidence or production data; do not stage/commit/publish/merge.

1. Read the user task, this checkpoint, domain guide, ADR 0009, full changed source,
   registry files, fixtures and tests. Inspect the actual diffs against the recorded
   base; keep unrelated entry modifications separate.
2. Run `.venv/Scripts/python.exe -B docs/reviews/m365-category-architecture-20261102/verify_checkpoint.py`.
   Recompute candidate-inventory hashes and external entry-preservation evidence.
   Review the complete seven-schema dependency set and compare review pins with
   entry-state identities. Any mismatch invalidates applicability; stop that gate.
3. Review service/UI separation; exactly fourteen IDs/order; General versus Other;
   primary/multiple category references; duplicate/unknown/invalid rejection; strict
   JSON/path/pin behavior; descriptor/default semantics and local schema refs.
4. Challenge the distinction between metadata compatibility and executable approval.
   Confirm an empty production catalog, no fixture trust promotion, no script scan,
   no positive eligibility and no execution path from clicks/Return/double-clicks.
   Check failure containment so Notes and Back remain available on registry failure.
5. Inspect search/filter/retirement behavior, dark styling, narrow/portrait layout,
   sidebar collapse and keyboard accessibility. Read failed attempts and diagnoses
   before using final passes. Do not treat screenshots or Qt scale runs as physical
   acceptance or provider evidence.
6. If fresh test evidence is needed, use the commands above with new isolated paths;
   retain failure evidence and diagnose before any materially changed rerun. Never
   regenerate pins or alter tests just to make the review pass.
7. Save a **new** independent review bound to exact base/path/raw hashes and the
   retained test evidence. Report findings with severity, path/line, reproduction,
   expected/actual behavior and PASS / FAIL / BLOCKED / NOT RUN literally. Report
   category review, contract approval and engine approval as separate statuses.

Any follow-on code corrections, contract promotion, execution integration,
authentication, tenant work or Git publication requires its own authorization.
