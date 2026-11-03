# Portable Company Directory Exchange Contract v1 checkpoint

Disposition: **PORTABLE COMPANY DIRECTORY CONTRACT — READY_FOR_INDEPENDENT_REVIEW**.
Status: **DRAFT — APPROVAL PENDING**. No self-approval or activation.
Contract `company-directory.exchange / 1.0.0-draft.1`, JSON Schema Draft 2020-12.
Schema ID:
`https://company-directory.invalid/exchange/1.0.0-draft.1/company-directory.schema.json`.

## Authority and preservation

Read AGENTS.md, GEMINI.md revision 2, current CompanyDirectory/Administrator/Company
model and envelope, context service, company feature guide, ADR 0010, existing
company checkpoint and independent-review findings, and the separate M365 contract
and JSON Schema conventions. No newer independent approval of the concurrent
company corrections was found in the repository review directory. Current model
inspection is not approval of its concurrent changes.

Git branch main, HEAD ef847af18572ce5b82b0dd263b75658efe1caacd, index empty.
No new branch/worktree or Git mutation. All contract-design writes are new files
under docs/contracts/company-directory. An earlier draft-only three-file package
created during Addendum C was relocated here and revised to the exact identity in
the design brief; no old alternate contract remains. No application source, existing
tests, Notes persistence, M365 UI/contract/engine, S002 or F7Hub was modified by the
design phase. Prior authorized Notes corrections remain a separate uncommitted
candidate, not changes owned by this contract or permission for Merge activation.

## Files and exact identity

candidate-inventory.json lists every package file and raw SHA-256, excluding its
own circular hash, plus inspected compatibility input hashes. Verify its raw hash
at review entry, then every enumerated artifact. Any change requires a new bound
review. This inventory is specific to the design package, not the entire dirty
checkout and not the previous M365-only path manifest.

- company-directory.schema.json: exact closed envelope/company/admin structure.
- README.md: schema identity, parser bounds, normalization, semantics and privacy.
- MERGE_SPEC.md: local-first conflict matrix, deterministic IDs/order/results,
  idempotence, deferred commit timestamps, future transaction/adapter gates.
- COMPATIBILITY.md: explicit in-memory conversion and F7Hub projection gaps.
- BACKUP_SPEC.md: Addendum E verified timestamped JSON backup, no-op behavior,
  publication, collision policy, restore/SQLite boundaries and acceptance matrix.
- exchange-fixtures.json: 38 positive/negative/adversarial validation cases.
- merge-golden-fixtures.json: 12 merge specification examples with expected documents
  and counts; these are not an executable implementation.
- backup-scenarios.json: 11 future backup/rollback acceptance scenarios, NOT RUN.
- validate_design.py: offline bounded parser/schema/semantic design validator only.
- test_contract.py: isolated synthetic validation suite, no GUI/DB/provider/merge.
- CHECKPOINT.md and candidate-inventory.json: review handoff and exact identity.

## Fresh validation evidence

Python 3.14.5; existing jsonschema package, no dependencies added or upgraded.
Evidence is retained outside the repository at
`C:/Users/Jo/.codex/artifacts/tnotes-integrity-a54b4bf6d78a41d1bcf80468a8397c8c/`:
contract-design-attempt1.log, contract-design-final.log and
contract-model-roundtrip.json. Both design-suite executions passed; final fixture
coverage follows incorporation of Addenda D and E. The first run preceded those
final backup scenarios/local-first examples and is not substituted for final evidence.

```powershell
cd C:/Dev/T-Notes
.venv/Scripts/python.exe -B -m unittest discover -s docs/contracts/company-directory -p test_contract.py -v
```

**PASS: 4 unittest methods with subtests** covering all 38 exchange cases,
12 x 3 golden documents, 6 explicit schema-valid/semantically-invalid cases, size
and UTF-8 boundaries. Valid fixtures undergo JSON serialization/validation roundtrip.
**PASS: 3 positive fixtures projected through the current CompanyDirectory model**;
all normalized metadata/IDs round-tripped unchanged. Projection replaces only the
envelope with `{format: m365.company-directory, version: 1, companies: ...}` before
CompanyDirectory.from_metadata, then compares export_metadata against that projection.
This offline model check imports no GUI and opens no database.

**NOT RUN / NOT IMPLEMENTED:** actual merge algorithm/idempotence execution,
Settings Merge, real T-Notes/F7Hub adapter exchange, persistent transactions,
directory backup publication/restore, permission enforcement, rollback/interruption
and filename-collision execution tests. Golden examples and backup acceptance
matrices are design requirements, not substitutes for these future tests.
No full application rerun is claimed for this design-only package. The earlier
Notes candidate's 276-test passing run is separate evidence, not contract approval.

## Semantic limits and decisions requiring review

Schema detects structure/types/bounds and date-time shape/format; explicit semantic
validation detects normalized tenant/company/name/admin uniqueness, default
ownership, domain attribution and timestamp order. The offline validator mirrors
the current model rules but is not a production importer or source of authenticated
identity. Full-result validation, pure merge execution and adapter transactions
remain future work after approval.

Review these proposed policy choices explicitly:

1. Reject an entire imported document containing internally ambiguous domain/tenant
   claims; skip only cross-directory conflicts between separately valid inputs.
   This is stricter than current overlapping-domain model behavior.
2. UTC Z grammar, mandatory concrete fields/timestamps, strict unknown-field/version
   rejection and lossless conversion only for metadata meeting both validators.
3. Preserve all local scalar values, even empty notes/labels, and do not promote a
   conflicting imported primary domain. Only missing safe domains/admins and an
   unambiguous default when local default is null enrich existing records.
4. Preserve local IDs; skip company-ID/tenant and admin-ID/UPN collisions rather
   than inventing random replacements. Match companies solely by tenant UUID.
5. Pure planning never changes modification timestamps. Future transaction commit
   stamps only actually changed records using an explicit instant, with rollback;
   imported timestamps never select conflicting values.
6. Verified application-controlled JSON pre-merge backups for changed plans; no
   backup on no-op. Separately approved recovery must restore directory metadata;
   ordinary Merge is not exact restoration or a whole-application database backup.

Identifiers are not credentials but remain confidential organizational metadata.
Unknown secret/session/target fields reject. No allowlist can prove users did not
paste a secret into the allowed plain-text notes/label fields; no such detection
or provider identity verification is claimed. Diagnostics avoid raw field values.

## Independent reviewer instructions

Bind package/schema/source-input hashes first. Review the complete conflict and
backup matrices against Addenda C/D/E, including whole-import rejection versus
field/company skips, scalar preservation, alias/default mapping, capacity limits,
timestamp determinism and no-op handling. Challenge all fixtures and add temporary
external probes without editing the candidate. Reproduce the isolated command;
verify the model projection independently against the pinned source hash.

Evaluate F7Hub integer-ID mapping, admin/tenant storage gaps and association-safe
restore without modifying F7Hub. Do not infer working adapters from portable golden
documents. Report findings by severity and exact path/line; do not self-correct.
Approval must bind exact bytes/version and explicitly accept or reject the stricter
domain/timestamp rules. Keep schema, pure-module, adapter, backup/recovery, Notes,
company-rereview and activation approvals separate. No Merge control or persistent
import may be enabled by this checkpoint. STOP.
