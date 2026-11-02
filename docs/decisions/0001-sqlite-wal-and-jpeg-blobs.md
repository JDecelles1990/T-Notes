# [ADR-0001] SQLite WAL Mode & Embedded JPEG BLOB Storage

- **Status:** Accepted
- **Date:** 2026-11-01
- **Author(s):** Systems Architecture Team
- **Deciders:** Principal Desktop Architect

---

## 1. Context and Problem Statement
IT support technicians frequently capture screenshots (`Win + Shift + S`) containing error messages, network outputs, and server dialogs. 

We faced two critical engineering challenges:
1. **File Storage vs. Database Storage:** Storing images as loose files in an `app_data/images/` filesystem directory leads to orphan file drift, complex synchronization when copying or moving files, broken relative paths, and messy backup routines.
2. **Storage Footprint & Database Bloat:** Storing uncompressed raw clipboard bitmaps (32-bit ARGB) directly in SQLite causes the database file to grow by 50–100 MB per week, degrading read performance and backup times.

---

## 2. Decision Drivers
- **Atomic Portability:** The technician's entire workspace, history, and embedded images must reside in a single portable `.db` file for trivial backup and migration.
- **UI Responsiveness:** Saving notes and images must not freeze or stutter the PySide6 main event loop.
- **Data Integrity:** Deleting a ticket or backspacing an image from a note must clean up the associated image bytes without orphaned disk clutter.
- **Font Clarity:** Text in command-line terminals and error messages must remain 100% legible despite compression.

---

## 3. Considered Options
1. **Option 1 (Loose Files on Disk):** Store metadata in SQLite and save PNG/JPEG files in a local folder, referencing absolute or relative paths in the HTML.
2. **Option 2 (Raw Uncompressed BLOBs in SQLite):** Store raw clipboard bitmaps directly in SQLite as BLOBs or Base64 data URIs.
3. **Option 3 (SQLite WAL Mode with 85% JPEG BLOBs & Garbage Collection):** Convert and compress all incoming screenshots to JPEG (quality 85) via Qt `QBuffer` and store them in a dedicated `scratchpad_images` table with an internal URI scheme (`image://local/<uuid>.jpg`).

---

## 4. Decision Outcome
**Chosen Option:** Option 3 (SQLite WAL Mode with 85% JPEG BLOBs & Garbage Collection).

### Rationale
- **Single-File Backup:** By storing images inside `scratchpad_images`, the entire application state is encapsulated in `techpad.db`. Technicians can back up, move, or sync their notes simply by copying one file.
- **Drastic Space Savings:** An 85% quality JPEG achieves a 94–96% size reduction over raw 32-bit ARGB clipboard captures while preserving crisp text readability for console logs and system dialogs.
- **Non-Blocking Concurrency:** Enabling SQLite Write-Ahead Logging (`PRAGMA journal_mode = WAL;`) allows background auto-saves to commit image BLOBs in milliseconds without locking read queries or causing GUI micro-stutters.
- **Automated Garbage Collection:** During debounced saves, `ImageService` compares HTML references with SQLite rows, automatically pruning any images that were deleted from notes.

---

## 5. Consequences

### Positive Consequences
- **Zero File Drift:** No dangling image files left behind in temp folders.
- **ACID Atomicity:** Ticket deletions cleanly cascade to images via `ON DELETE CASCADE`.
- **Lean Database Footprint:** Even with dozens of daily screenshots, database growth remains bounded to a few megabytes per month.
- **Full Offline Isolation:** No network calls or cloud dependencies required.

### Negative Consequences / Trade-offs
- **Lossy Compression for Gradients:** JPEG compression is lossy; extremely subtle color gradients may show mild artifacts. However, for IT documentation (text, dialogs, graphs), 85% quality is visually indistinguishable from source screenshots.
- **Database Vacuuming:** Deleting large volumes of tickets marks SQLite pages as free but does not immediately shrink the `.db` file on disk until `VACUUM` is executed.

---

## 6. Implementation Notes & Validation
- Implemented in:
  - `src/services/image_service.py` (`compress_qimage_to_jpeg`, `sync_scratchpad_images`)
  - `src/repositories/image_repository.py`
  - `src/database/schema.sql` (`scratchpad_images` table with cascade foreign key)
- Automated tests verifying this ADR:
  - `tests/test_image_service.py::test_compress_qimage_to_jpeg`
  - `tests/test_image_service.py::test_sync_scratchpad_images`
  - `tests/test_database.py::test_cascade_deletion_of_images`
