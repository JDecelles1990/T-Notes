# Company Directory merge prototype and disabled Settings control

Disposition: **PARTIAL — STORAGE GATED**. Independent review required.
No contract, module, storage or release approval is claimed.

## Authority, entry and ownership

Explicit implementation brief permits strictly isolated work while prerequisite
reviews remain pending, and a disabled explained Merge control if durable company
storage is unavailable. Read root AGENTS.md/GEMINI.md revision 2, current Git state,
exchange package including Addenda C/D/E, Notes and corrected Company Directory
checkpoints, existing Settings dialog and company/context boundaries.

Observed contract: company-directory.exchange / 1.0.0-draft.1, DRAFT, APPROVAL PENDING.
Notes corrections: READY_FOR_INDEPENDENT_REVIEW; independent review NOT RUN in record.
Company GUI: CORRECTED, READY_FOR_INDEPENDENT REREVIEW. No approval record was found
in the inspected checkpoints. Production company storage and verified backup adapter
are unavailable. Do not infer approval from author tests or matching hashes.

Branch main, HEAD ef847af18572ce5b82b0dd263b75658efe1caacd; empty index before/after.
No branches/worktrees, stage, commit, push, merge, reset or clean. No production DB,
M365 authentication, PowerShell execution, script registration, F7Hub or TimeSpace
mutation. Pre-existing dirty work is preserved. Settings is the sole modified entry
file; 302 other recorded source/docs/test/asset files retain entry hashes. There
was no overlapping file drift during this task. No company/context/launcher source,
Notes persistence file, contract artifact or existing test was edited.

External evidence, entry hashes and byte-verified Settings backup:
`C:/Users/Jo/.codex/artifacts/tnotes-merge-prototype-d371b5d4c17d43c3bf732d84510c119f/`.
Do not overwrite retained evidence on rereview. candidate-inventory.json lists exact
task file hashes, prerequisite pins and protected entry hashes, excluding itself.

## Candidate scope and architecture

- prototypes/company_directory_merge/company_directory_merge.py: one portable,
  detached in-memory draft planner; standard library plus existing jsonschema only.
- prototypes/company_directory_merge/README.md: API, isolation, draft discrepancies.
- src/ui/dialogs/settings_dialog.py: exactly one new disabled Merge button and visible
  session-only/approval explanation; no handler, picker, adapter or runtime engine import.
- tests/test_company_directory_merge_prototype.py: 65 synthetic cases.
- docs/features/company-directory-merge.md: UI/storage status, mode deferral and future
  F7Hub/TimeSpace adapters and possible explicit communication channels.
- docs/decisions/0012-isolated-directory-merge-prototype.md: isolation decision; preserves
  concurrently owned system-overview.md instead of editing the other task's document.
- This checkpoint and candidate-inventory.json: review handoff and exact identities.

The caller supplies exact raw schema and MERGE_SPEC bytes. DraftContract verifies
schema SHA-256 f82835998fa6d7d7d84aba6c10cd1254638b1f53c710b9456e95d5e83a6ee37a
and policy SHA-256 d01397ac3a964f6d2fb03afeeca82a57119665bbc76be0e4031165ed405e58a4.
These are provisional draft pins, never an approved production contract/version.
No path/default file IO or remote resolution is present in the reusable module.
The application does not import the prototype and no writer is registered.

plan_merge_prototype returns detached candidate, change counts, conflicts, validation
diagnostics, per-company statuses and changed_company_ids. Every returned plan is
prototype_only=True, durable=False, backup_status=NOT IMPLEMENTED. Parser/schema/
semantic failures reject the entire input before planning. Both inputs and the final
result validate; local IDs/scalars/defaults are preserved, safe domains/accounts are
added, capacity overflow skips the whole company's delta and repeats are idempotent.
Planning never stamps timestamps. No plan is an authentication or authorization object.

## Test attempts and actual results

Environment: Windows Qt backend; Python 3.14.5, PySide6 6.12.0, jsonschema 4.26.0.
No dependencies installed/upgraded. Only synthetic data and external temporary paths.

| Attempt | Result |
|---|---|
| focused1 | PASS: 56 cases |
| focused2 | PASS: 64 cases after capacity/default/ID/tenant edge additions |
| full1 | PASS: 340 tests, 7 existing editor deprecation warnings |
| unicode-before | FAIL: one new escaped unpaired-surrogate rejection assertion; 64 deselected |
| focused3 | PASS: 65 cases after strict Unicode rejection |
| full2 | PASS: 341 tests, zero failures, 34 existing editor deprecation warnings |

The first full run predates the final Unicode correction and is not final-candidate
evidence. The failing Unicode case is retained unchanged and passes in focused3/full2.
Native logs retain Windows exception diagnostic 0x8001010d, followed by pytest normal
completion/exit 0. Physical desktop/DPI and assistive-technology acceptance NOT RUN.
A native Settings capture (settings-disabled.png) was inspected at 440x344; the reason
is visible and Merge disabled. That capture overlapped full1; full2 ran without it.

Commands from C:/Dev/T-Notes (use fresh $out paths, never reuse basetemp):

```powershell
$env:QT_QPA_PLATFORM = 'windows'
$env:PYTHONDONTWRITEBYTECODE = '1'
.venv/Scripts/python.exe -B -m pytest -q -p no:cacheprovider tests/test_company_directory_merge_prototype.py --basetemp "$out/focused-temp" --junitxml "$out/focused.xml"
.venv/Scripts/python.exe -B -m pytest -q -p no:cacheprovider tests/test_company_directory_merge_prototype.py -k unpaired --junitxml "$out/unicode.xml"
.venv/Scripts/python.exe -B -m pytest -q -p no:cacheprovider --basetemp "$out/full-temp" --junitxml "$out/full.xml"
```

Tests exercise new tenants, enrichment, aliases, casefolded UPNs, default adoption/
conflicts, empty label and scalar preservation, duplicate imports, reordered inputs,
cross-tenant domains/IDs, capacity, full-input rejection including invalid trailing
records, exact draft pins, parser bounds and all 38 exchange fixtures. All 12 golden
candidate documents match; inconsistent draft administrator counts are discussed below.
Settings tests verify exactly one Merge button, disabled click/reject without preference
mutation, session-only explanation and no runtime integration. Static core import
checks restrict dependencies to standard library/jsonschema. Full suite covers existing
Notes integrity, image and M365 workspace/launcher protections without changing assertions.

## Unresolved contract issues and limits

1. Draft new-company golden scenarios expect zero administrators_added despite adding
   two accounts. Prototype correctly reports two. golden-count-discrepancies.json lists
   all mismatches. Candidate documents match; full golden counts do NOT conform. The
   draft files remain preserved and need independent correction/approval, not rebasing.
2. Diagnostics use canonical incoming company/admin indices, making equivalent reordered
   inputs deterministic. The draft discusses source indices; reconcile this convention
   during review before production acceptance.
3. Escaped unpaired Unicode surrogates are rejected as INVALID_UNICODE, beyond the
   original draft fixture set. This closes a strict UTF-8 serialization hole; schema
   and design-harness hardening need their own review, not edits by this prototype.

NOT IMPLEMENTED / NOT RUN: active file picker cancellation flow, backup creation and
verification failures, persistent commit/rollback/interruption, directory restore,
storage-level stale-plan guards, durable company imports and actual other-app adapters.
The disabled UI cannot reach any of these paths. No simulated storage test is presented
as adapter acceptance. Existing profiles remain session-only. A directory JSON backup
would not cover unrelated Notes DB state; no backup writer exists in this milestone.

Optional MSP/Single Company mode and Department are deferred. They would broaden the
concurrently reviewed context UI and preference/storage contracts; existing searchable
selection and 14-category sidebar remain. Future mode/department must be app-local,
preserving stable IDs and not extending the portable exchange schema for display.

## Independent review and next gates

Verify HEAD/index and every candidate/preserved hash before review. Stop on task-file
drift; report external work separately. Inspect complete module and Settings change.
Challenge parser bounds, Unicode, normalized identity and ID collisions, defaults,
capacity rollback, stale/ambiguous references and idempotence. Reproduce focused/full
tests with isolated paths; retain failures and separate native/physical evidence.
Confirm no application import/handler/storage or process/network path exists.

Resolve schema/policy/golden-count issues and obtain independent contract approval,
Notes review and company GUI rereview. Then review portable module and each application's
storage/backup/recovery adapter before activation. Activation needs bounded picker IO,
full-result validation, verified destination JSON backup before writes, transactional
rollback, committed timestamps and accurate summaries/no-op reporting. No reviewer or
approval of this prototype may infer production persistence or live tenant authority.
No F7Hub/TimeSpace source or live database sharing is authorized by this checkpoint.
