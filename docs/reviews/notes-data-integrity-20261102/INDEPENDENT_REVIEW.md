INDEPENDENT_REVIEW — T-Notes Notes Data Integrity (P0)
Record type: Archived extract of an independent review report supplied in a ChatGPT conversation.
Reviewer attribution: Gemini Flash High, as identified in the conversation.
Source attachment: Pasted text(20261103-050333).txt
Source attachment SHA-256: 5627c806a0787f8ba7ee096660d885bcd4b7cbee22d14e32e18f8cb34447c048
Original reviewed candidate: C:\Dev\T-Notes at reported base Git revision ef847af18572ce5b82b0dd263b75658efe1caacd.
Disposition reported by reviewer: APPROVED — SAFE TO COMMIT (exact hash-verified 11-file candidate only).
Production release: Not authorized by this review; separate production acceptance remains.
Provenance limitation: This Markdown record is a faithful extraction of the P0 section of the user-provided reviewer report. It was not independently re-executed or cryptographically signed here. The report's original Windows location was not established.
Repository placement proposed: docs/reviews/notes-data-integrity-20261102/INDEPENDENT_REVIEW.md (not yet installed in the user's repository).

Preservation and integration instructions
This record preserves the reviewer's reported results and is not an amendment to CHECKPOINT.md or the candidate's existing hash inventory. Before accepting or committing the candidate, independently verify its current file hashes against the listed inventory; if any hash differs, approval does not automatically carry over. Store this record as a new review artifact and do not silently revise the original candidate evidence.
REVIEW 1 — NOTES DATA INTEGRITY (P0)
1. Candidate Identity & Manifest Verification
- Base Git Revision: ef847af18572ce5b82b0dd263b75658efe1caacd (clean main).
- External Inventory & Evidence: C:\Users\Jo\.codex\artifacts\tnotes-integrity-a54b4bf6d78a41d1bcf80468a8397c8c\candidate-inventory.json
- Candidate Inventory Match: All 11 candidate files were independently hashed and matched their SHA-256 digests exactly:
Path	SHA-256 Digest	Status
src/ui/main_window.py	bca716adc360cde4a8fce00afb918b3658320acc502e432ee6c9c96d93d61d98	MATCH
src/services/scratchpad_service.py	0dbeed81d3ea6969db3caeb8ff18fa8f9e7f9dece7a93f41cee8b29dbfc23af9	MATCH
src/repositories/scratchpad_repository.py	04eef65b19908a31d5e539a9e183823ff41c6ff4af06912c01d786bc68abb3a9	MATCH
tests/test_notes_integrity.py	2374a38960277e3877a2f1a9a769b9a039debcf76b6f23c55480082a324c0618	MATCH
docs/database/schema.md	1a96abb3b79fcece7ddb04523f572a1522a5b933bc571a915e81916897544a4b	MATCH
docs/architecture/image-pipeline.md	00c0d6532a44400c50956103e98b76d8a014be634f52c3e7ab92283f20d06754	MATCH
docs/features/tab-lifecycle.md	c6be52dd0fca9a089059369aca78113d75bd7976b6abb766cbada281596be40f	MATCH
docs/features/editor-and-formatting.md	cb59df0d2b25bb2624287d1cba98f05bda61664dce4a32183aae2c3f426d5e3b	MATCH
docs/features/history-and-archive.md	f2e7a353886bdf22a5ce7e63b9b9a4633212ede308d0897a6b93cf950193866e	MATCH
docs/decisions/0011-note-save-unit-of-work.md	fb82e86e824176cff0f30152a930fdbeff752f4c6a23a0aa418e6d98f70b3425	MATCH
docs/reviews/notes-data-integrity-20261102/CHECKPOINT.md	fd5fbbc4aedac5e37885e907a42eeeef520dc9338e70bdea6f6fb37fd451c872	MATCH


- Concurrent Repository State: Four concurrent M365 paths (src/services/m365_company_service.py, src/ui/m365/company_context_panel.py, tests/test_m365_company_context.py, tests/test_m365_company_ui.py) and root screenshots remain unchanged and unmixed.
2. Tests Independently Executed
All tests were executed in an isolated Python 3.14.5 / PySide6 6.12.0 virtual environment (.venv):
1. Dedicated Notes Integrity Suite:.venv/Scripts/python.exe -B -m pytest -q -p no:cacheprovider tests/test_notes_integrity.py
   Result: 22 passed in 3.12s (100% pass across all 22 failure-injection and recovery scenarios).
2. Focused Services & Database Integration Suite:.venv/Scripts/python.exe -B -m pytest -q -p no:cacheprovider tests/test_notes_integrity.py tests/test_scratchpad_service.py tests/test_image_service.py tests/test_database.py
   Result: 41 passed in 3.65s.
3. Alt+F8 HUD & Workspace Regression Suite:.venv/Scripts/python.exe -B -m pytest -q -p no:cacheprovider tests/test_m365_workspace.py -k 'alt_f8_preserves_split_ticket_pending_notes_and_timer or alt_f8_safely_leaves_hud'
   Result: 4 passed, 49 deselected in 2.35s.
4. Complete Repository Test Suite:.venv/Scripts/python.exe -B -m pytest -q -p no:cacheprovider
   Result: 276 passed in 26.23s (0 failures, 0 errors, 0 skips).
3. Security and Data-Integrity Findings
- Archive Save Barrier:
  Verified that _save_before_archive(scratchpad_id) intercepts all five archival routes: primary direct archive, secondary direct archive, prompted tab-close archive, secondary prompted archive, and _close_other_tabs. If unpersisted keystrokes exist, the debouncer is canceled and a synchronous save is executed immediately. If persistence fails (simulated via disk/database errors), the tab is retained, the in-memory images and undo buffers remain intact, the editor stays dirty, and clear status bar guidance directs the user to retry with Ctrl+S.
- Failed-Quit Recovery & Control Preservation:
  quit_application() now strictly delegates shutdown to closeEvent(). If note persistence, stopwatch state, or session metadata serialization fails:
  - closeEvent ignores the event (event.ignore()).
  - _force_quit is reset to False.
  - The main window is unhidden (self.show_notes_workspace(), self.showNormal()) and focus is restored to the active editor.
  - Global hotkeys (F8) and system tray controls remain active, ensuring the application cannot become an unreachable headless ghost process with unsaved edits trapped in memory.
- Atomic Unit-of-Work Persistence:
  ScratchpadRepository.save_content_with_images establishes an owned BEGIN IMMEDIATE SQLite transaction. It updates scratchpads.content_html, upserts referenced scratchpad_images, verifies that every referenced image exists, and deletes unreferenced images in the same transaction. If an image is missing or a write fails, SQLite rolls back the entire transaction, preventing dangling references or orphaned partial saves.
- Revision-Guarded Save Receipt:
  SaveReceipt provides an immutable contract (ticket_id, attempted_revision, persisted_revision, status). main_window.py verifies that receipt.persisted_revision == revision and asserts that no new keystrokes occurred during the save operation before clearing in-memory caches and discarding the dirty status.
- Resolution of Retained full1 Failures:
  Inspection of full1.log showed that two Alt+F8 tests failed due to transient window focus timing under heavy full-suite load. The test assertions in tests/test_m365_workspace.py were unmodified. Moving stopwatch persistence into the preflight check resolved the race condition cleanly without bypassing or weakening assertions.
4. Issues (Blocking / Important / Optional)
- Blocking: None.
- Important:
  - Ungraceful OS Termination: As with all memory-buffered editors, an abrupt SIGKILL / OS crash before a save barrier is reached will lose typing since the last debounce pause. An append-only write-ahead log for raw keystrokes is not part of this candidate.
  - Multi-Tab Archive Error Boundary: In _close_other_tabs, if tab \(K\) fails to save, earlier successfully archived tabs \((1 \dots K-1)\) remain archived. This is documented behavior and does not corrupt notes.
- Optional:
  - Consider adding an explicit warning sound or dialog if the user attempts to close the window while in a repeated save-failure state.
5. Evidence Paths
- Candidate Checkpoint: docs/reviews/notes-data-integrity-20261102/CHECKPOINT.md
- External Inventory & Retained Logs: C:\Users\Jo\.codex\artifacts\tnotes-integrity-a54b4bf6d78a41d1bcf80468a8397c8c\
  - before.log, before.xml (retained 14 baseline failures)
  - full1.log, full1.xml (retained Alt+F8 focus timing failure)
  - full2.log, full2.xml (276 passed)
- Architectural Decision Record: docs/decisions/0011-note-save-unit-of-work.md
6. Commit Approval Recommendation
APPROVED — SAFE TO COMMIT.
The candidate strictly corrects data-loss hazards during archiving and application shutdown, establishes transactional atomicity between HTML and images, introduces robust revision validation, and passes all 276 tests cleanly.
7. Remaining Production-Release Gates
1. Rehearsal of live database migrations and WAL checkpointing on large ticket histories.
2. Accessibility and physical DPI testing on target Windows workstation environments.
3. Independent authorization and gate clearance for M365 execution and storage components.