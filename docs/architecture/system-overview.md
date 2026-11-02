# System Overview & Architecture

## 1. Architectural Blueprint

T-Notes is engineered using a clean, layered architecture separating user interface presentation, business workflows, data access, and database storage.

```mermaid
flowchart TD
    subgraph Presentation ["Presentation Layer (src/ui/)"]
        MW["MainWindow"]
        TW["TechPadTabWidget"]
        ED["TechPadEditor (Custom QTextEdit)"]
        TB["TechPadToolBar"]
        HD["HistoryDrawer (QDockWidget)"]
        ETD["EditTicketDialog"]
    end

    subgraph Services ["Service Layer (src/services/)"]
        SPS["ScratchpadService<br/>• Auto-save orchestration<br/>• Note export<br/>• Skeleton formatting"]
        IMS["ImageService<br/>• JPEG 85% compression<br/>• Resource URI mapping<br/>• Orphan image pruning"]
        SES["SessionService<br/>• Workspace state restoration<br/>• Tab order serialization"]
        DBT["DebounceTimer<br/>• 1500ms QTimer debounce"]
    end

    subgraph Repositories ["Repository Layer (src/repositories/)"]
        SPR["ScratchpadRepository"]
        IMR["ImageRepository"]
        SER["SessionRepository"]
    end

    subgraph Database ["Storage Layer (src/database/)"]
        DBM["DatabaseManager<br/>• WAL Mode<br/>• Foreign Keys Enforced"]
        T_PADS[("scratchpads")]
        T_IMGS[("scratchpad_images")]
        T_SESS[("app_session")]
        T_FTS[("scratchpad_fts (FTS5)")]
    end

    MW --> TW
    TW --> ED
    MW --> TB
    MW --> HD
    MW --> ETD

    TW --> SPS
    ED --> IMS
    ED --> DBT
    DBT --> SPS
    MW --> SES
    HD --> SPS

    SPS --> SPR
    IMS --> IMR
    SES --> SER

    SPR --> T_PADS
    SPR --> T_FTS
    IMR --> T_IMGS
    SER --> T_SESS
```

---

## 2. Layer Boundaries & Responsibilities

### Presentation Layer (`src/ui/`)
- **Role:** Handles user input, window layouts, rendering, shortcuts, and event handling.
- **Rule:** UI components must **never** execute raw SQL queries. All data operations are delegated exclusively to `src/services/`.
- **Components:**
  - `MainWindow`: Orchestrates application lifecycle, dock panels, status bar, and central tabs.
  - `TechPadTabWidget`: Movable, closable tabs with double-click modal trigger.
  - `TechPadEditor`: Subclass of `QTextEdit` intercepting clipboard images, drag-and-drop, and clickable URLs.
  - `TechPadToolBar`: Compact micro-controls for rich text, monospace code blocks, triage badges, and templates.
  - `HistoryDrawer`: Collapsible side drawer with real-time FTS5 search.

### Service Layer (`src/services/`)
- **Role:** Encapsulates business logic, data formatting, debounced auto-saving, media compression, and session reconciliation.
- **Components:**
  - `ScratchpadService`: Ticket CRUD, note conversion for PSA tools ("Copy for Ticket Note"), and skeleton templates.
  - `ImageService`: Image conversion, JPEG 85% compression, resource URL management, and synchronization/pruning.
  - `SessionService`: Loads and saves workspace session (active tabs, active index, window geometry).

### Repository Layer (`src/repositories/`)
- **Role:** Manages SQL transactions, query parameterization, and row-to-dictionary mapping.
- **Rule:** Uses atomic transactions (`with connection:`) for all modifying operations.
- **Components:**
  - `ScratchpadRepository`: CRUD operations and FTS5 search queries.
  - `ImageRepository`: BLOB storage and cascading garbage collection.
  - `SessionRepository`: Singleton session row management.

### Database Layer (`src/database/`)
- **Role:** SQLite connection lifecycle, PRAGMA configuration, schema initialization, and migration execution.
- **PRAGMAs Enforced:**
  - `PRAGMA journal_mode = WAL;` (Write-Ahead Logging for high-concurrency read/write)
  - `PRAGMA foreign_keys = ON;` (Referential integrity and cascade deletion)
  - `PRAGMA busy_timeout = 5000;` (Graceful handling of locked databases)

---

## 3. Threading Model & Responsibilities

T-Notes operates within the standard PySide6 / Qt Event Loop:
1. **Main GUI Event Loop:** Handles keyboard strokes, mouse interactions, clipboard paste interception, cursor positioning, and UI rendering.
2. **Debounced Non-Blocking Writes:** Rather than writing to SQLite on every keystroke, user input triggers a 1500ms `DebounceTimer` (`QTimer.setSingleShot(True)`). The database transaction executes only after user typing pauses, ensuring the UI remains ultra-responsive.
3. **Synchronous Boundary Flushes:** To guarantee data safety, synchronous flushes are triggered upon:
   - Switching between tabs (`currentChanged`).
   - Closing an active tab (`tabCloseRequested`).
   - Window closing (`closeEvent`).
4. **Lightweight Transactions:** Because images are pre-compressed to compact JPEGs (typically 100–300 KB) and SQLite runs in WAL mode, database operations execute in milliseconds without freezing the main thread.

---

## 4. Application Lifecycle

### Bootstrap & Workspace Restoration Sequence
When `src/main.py` is executed:
1. `QApplication` is initialized with high-DPI scaling enabled.
2. Clean technician dark theme (`assets/styles/dark_theme.qss`) is loaded and applied.
3. `DatabaseManager` opens `techpad.db`, activates WAL mode, and verifies table schemas via `init_database()`.
4. `SessionService.restore_workspace()` runs:
   - Queries `scratchpads` for all records with `status = 'active'` ordered by `tab_order ASC`.
   - If no active scratchpads exist, an initial scratchpad (`INC-1001`) is automatically generated.
   - Restores window geometry and History Drawer visibility from `app_session`.
   - Opens each active ticket in its respective tab and restores the focused tab.

### Teardown & Exit Sequence
When the application receives a `closeEvent`:
1. `MainWindow.closeEvent` intercepts window closure.
2. `MainWindow.flush_all_saves()` immediately executes any pending debounced timers.
3. Tab order is serialized and updated in `scratchpads`.
4. The focused tab ID, window geometry hex string, and drawer visibility state are saved to `app_session`.
5. Database connections are closed cleanly.
