# AGENTS.md — Development Rules & Operating Standards

## 1. Architectural Boundaries
- **Layer Separation:** 
  - `ui/` components must never execute raw SQL statements.
  - `ui/` communicates strictly with `services/`.
  - `services/` contains business logic, validation, debouncing, and compression workflows.
  - `repositories/` owns database queries and transactions.
- **SQLite Concurrency & Integrity:**
  - Always enable WAL mode (`PRAGMA journal_mode = WAL;`) and enforce foreign keys (`PRAGMA foreign_keys = ON;`).
  - Use atomic transactions (`with connection:`) for operations spanning multiple tables.

## 2. Editor & Media Guidelines
- **Image Pipeline:**
  - Never save uncompressed raw BMP/PNG screenshots to the database.
  - Convert all clipboard image captures and dropped files to JPEG with a quality factor of 82–85.
  - Store image data in the `scratchpad_images` table as a `BLOB`.
  - Embed images into `QTextDocument` via `document().addResource(QTextDocument.ImageResource, QUrl("image://local/..."), qimage)`.
- **Formatting Tools:**
  - Provide inline formatting via standard `QTextCursor` manipulations to avoid corrupting HTML state.
  - Code block formatting must apply a distinct monospace font family (`Consolas`, `Courier New`) and a container style.

## 3. Auto-Saving & Session State
- **Debounced Writes:**
  - Implement auto-saving using a 1500ms `QTimer` (`setSingleShot(True)`).
  - Every keystroke or content change restarts the timer; persistence triggers only after user typing pauses.
  - Force an immediate sync to SQLite on tab switch or window close (`closeEvent`).
- **Session State:**
  - Store active tab IDs, tab indices (`tab_order`), and `is_selected` state in the `app_session` table.
  - On launch, restore tabs in order and set `setCurrentIndex()` to the saved active tab.

## 4. UI/UX & Styling
- **Theme:** Consistent dark mode using clean QSS. Avoid high-contrast bright backgrounds.
- **Micro-Controls:** Use compact emoji and concise text labels for toolbars to conserve screen space.
- **Non-Blocking UI:** Heavy exports or complex searches over massive datasets must run off the main event loop or use lightweight chunking.