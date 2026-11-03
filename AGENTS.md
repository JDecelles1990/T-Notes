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

---

## 5. Documentation Synchronization & Routing Protocol (Mandatory for AI Agents)

To prevent architectural drift and knowledge rot, agents must update the corresponding domain documentation in `docs/` whenever implementing, refactoring, or extending code. Never confine architectural decisions, schema changes, or feature updates exclusively to pull request summaries or commit logs.

### Routing Table

| If You Modify or Touch... | You Must Update... |
| :--- | :--- |
| Database schemas, queries, or tables | `docs/database/schema.md` |
| FTS5 indexing, search triggers, or queries | `docs/database/fts-and-search.md` |
| Image capture, compression, or caching | `docs/architecture/image-pipeline.md` |
| Layer interactions, threading, or app bootstrap | `docs/architecture/system-overview.md` |
| Tab widget behavior, session save/restore | `docs/features/tab-lifecycle.md` |
| `QTextEdit`, key bindings, or formatting | `docs/features/editor-and-formatting.md` |
| History drawer, archiving, or restore actions | `docs/features/history-and-archive.md` |
| Fundamental patterns or library adoptions | Add an ADR in `docs/decisions/XXXX-<title>.md` |

### Rules for Documentation Maintenance
1. **Atomic Documentation Commits:** Any code change that alters component behavior must include the corresponding documentation adjustment within the same task.
2. **Contract Preservation:** Keep data contracts, URI schemes (`image://local/<uuid>`), and database schemas in sync across code and documentation.
3. **No Redundant Summaries:** Update the specific topic file directly; do not bloat the root `README.md` or `AGENTS.md` with operational details.

## 6. Mandatory M365 PowerShell Contract

Every future M365 PowerShell operation must use the official
[M365 contract](docs/contracts/m365/CONTRACT.md) and its complete local schema
package as the mandatory implementation reference. The required baseline is
`tnotes.m365 / 0.3.0`, with status `APPROVED — IMPLEMENTATION CONTRACT` and a
verifiable effective approval record. Read the [contract index](docs/contracts/m365/README.md)
for the applicable architecture, security requirements and validation instructions.

Before implementing or modifying an operation, verify the exact contract version,
source revision and hashes, callable ABI, manifest validity, host-owned authentication
boundary, execution trust requirements, permissions/RBAC, operation-specific tests
and independent approval requirements. Missing approval evidence or incompatible
versions/hashes block implementation; never silently substitute a planning draft
or treat a proposed contract as official. Existing proposed-version consumers need
explicit migration and compatibility tests.

Keep reusable operations independent of T-Notes GUI state, PySide6, SQLite and
ticket editors for eventual F7Hub reuse. Contract approval authorizes development
against the specification; live authentication, tenant execution, executable
registration and production integration require separate authorization and release
approval.
