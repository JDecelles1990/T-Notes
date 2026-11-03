# Notes data-integrity corrections

Disposition: **DATA-INTEGRITY CORRECTIONS — READY_FOR_INDEPENDENT_REVIEW**.
Author validation only; independent review and commit approval **NOT RUN**.

Branch `main`, HEAD `ef847af18572ce5b82b0dd263b75658efe1caacd`; index empty.
No branch/worktree, stage, commit, push, merge, reset or clean operation.

## Scope and preservation

External evidence and verified entry backups:
`C:/Users/Jo/.codex/artifacts/tnotes-integrity-a54b4bf6d78a41d1bcf80468a8397c8c/`.
entry.json records entry hashes/status; backup/ contains eight byte-verified source
and topic-document originals. preservation.json identifies four concurrent M365
paths changed after entry; none was edited by this task. 278 other entry files
retain their entry hashes. The two root PNGs were left untouched.

Only candidate-inventory.json's task paths belong to this correction. M365 services,
launcher, models, schemas, engine, library, company exports, S002, F7Hub and
production databases were not modified. System overview is concurrently dirty;
ADR 0011 records the Notes interaction change without touching that shared file.

## Corrections

- One save-before-archive barrier handles direct primary and secondary archive,
  both prompted Archive choices and Close Other Tabs. It saves live snapshots
  independently of debounce activity; failure retains editor, dirty ID, undo and
  pending JPEGs. Missing dirty editors explicitly fail. Ctrl+S or Archive retries.
- Quit delegates persistence/acceptance to closeEvent. Failed note, stopwatch,
  order or session persistence cancels shutdown, restores visible Notes and keeps
  F8/tray recovery controls. Application quit follows accepted close only.
- A repository-owned BEGIN IMMEDIATE/connection-context transaction updates HTML,
  referenced JPEG BLOBs and ticket-scoped cleanup together. Missing references,
  missing tickets and ambient transactions reject. No nested committing helpers.
- Immutable application SaveReceipt carries ticket_id, attempted_revision,
  persisted_revision, status and error_code. Exceptions produce no saved receipt.
  The GUI accepts only the committed current revision and retains later edits.
  No PowerShell contract or adapter is modified or approved.

## Validation attempts (all retained externally)

Environment: Windows Qt backend; Python 3.14.5, PySide6 6.12.0, SQLite 3.50.4.

| Attempt | Actual result |
|---|---|
| before | FAIL: 14 failed, 1 passed; all five archive routes archived stale content; Quit tore down controls; transaction/retry assertions failed |
| after1 | PASS: initial 15 new regression cases |
| focused | PASS: 40 Notes-integrity/service/image/database cases |
| full1 | FAIL: 273 passed, 2 existing Alt+F8/HUD cases failed |
| diagnostic | PASS: all 4 parameterizations of the two failing cases in isolation |
| full2 | PASS: 276 passed, zero failures; includes 22 new Notes-integrity cases and concurrent M365 additions |

The initial native focus failures are not relabelled as passes or proven baseline
defects. No competing T-Notes Python process was found at the subsequent process
check. The final code also moves stopwatch pause persistence into the guarded
shutdown preflight, with a new failure test. That change and isolated diagnosis
precede the bounded final full run; no source changes follow full2.
Native logs retain Windows exception diagnostic 0x8001010d while pytest continues
to normal completion. Physical desktop and assistive-technology acceptance NOT RUN.

Commands from C:/Dev/T-Notes, with a fresh external `$out` per run:

```powershell
$env:QT_QPA_PLATFORM = 'windows'
$env:PYTHONDONTWRITEBYTECODE = '1'
.venv/Scripts/python.exe -B -m pytest -q -p no:cacheprovider tests/test_notes_integrity.py --basetemp "$out/temp" --junitxml "$out/result.xml"
.venv/Scripts/python.exe -B -m pytest -q -p no:cacheprovider tests/test_notes_integrity.py tests/test_scratchpad_service.py tests/test_image_service.py tests/test_database.py --basetemp "$out/temp" --junitxml "$out/result.xml"
.venv/Scripts/python.exe -B -m pytest -q -p no:cacheprovider tests/test_m365_workspace.py -k 'alt_f8_preserves_split_ticket_pending_notes_and_timer or alt_f8_safely_leaves_hud' --basetemp "$out/temp" --junitxml "$out/result.xml"
.venv/Scripts/python.exe -B -m pytest -q -p no:cacheprovider --basetemp "$out/temp" --junitxml "$out/result.xml"
```

Actual distinct basetemp/output stems were before, after1, focused, full1,
diagnostic and full2. Logs/XML retain each attempt. Full suite covers the existing
Notes, image and M365 workspace protection tests without weakening their assertions.

Synthetic online SQLite backup uses Connection.backup, then restores into another
isolated database. Four fault-stage tests check integrity_check=ok, empty
foreign_key_check, exact HTML/BLOB contents, unchanged other-ticket images, rollback
and successful retry. No raw live-WAL file copy or real case-note access occurred.

## Independent review instructions (Gemini or another reviewer)

1. Bind HEAD, empty index and raw file hashes to candidate-inventory.json. Stop on
   candidate drift. Do not use the earlier M365-only changed-path inventory as this
   Notes candidate's manifest. Its protected implementation is a separate task.
2. Read AGENTS.md, GEMINI.md, ADR 0011 and updated Notes topic docs. Inspect complete
   code, not only passing tests. Review is read-only; no repairs or Git mutation.
3. Challenge every archive route with failed idle autosave; verify current-revision
   receipt, document/undo/cache retention, missing-editor rejection and Retry.
4. Test visible and hidden Quit/close, including session/stopwatch failures and
   absence of QApplication.quit/F8/tray teardown on failure.
5. Inject HTML/insert/delete/COMMIT failures and missing image references. Verify
   rollback, FTS/integrity, ticket isolation and consistent online backup/restore.
6. Run the focused and full suites into new external paths, retain all failures,
   and report literal PASS/FAIL/NOT RUN. Do not infer physical acceptance.
7. Review concurrency: four M365 entry changes are recorded as external changes,
   not authored corrections. Preserve those files and all other work.

## Limits and next gates

Per-ticket HTML/images are atomic; archive audit updates and multi-ticket batches
are subsequent operations. Previously successful archives in Close Other Tabs are
not undone if a later ticket fails. Session metadata is separate from note commits.
Forced OS termination still loses unsaved RAM edits; no recovery journal is added.
Commit denial tests do not simulate hardware failure or power-loss durability.

Addendum C is a separate, gated follow-on: no company persistence, Merge UI, shared
database or F7Hub integration is activated here. An approved portable multi-admin
JSON Schema and completed independent reviews are required before that activation.
This checkpoint does not self-approve these corrections or clear release gates.
