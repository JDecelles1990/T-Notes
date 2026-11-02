# TechPad Architecture & Design Specification

## 1. System Overview
**TechPad** is an ultra-responsive, dark-mode desktop scratchpad application engineered specifically for IT support technicians, MSP engineers, and systems administrators. It bridges fast multi-tab note-taking with local SQLite persistence, embedded JPEG image handling, full-text search, and one-click export for ticketing systems (ServiceNow, HaloPSA, Jira, ConnectWise).

---

## 2. Layered Architecture

```
+-------------------------------------------------------------+
|                     Presentation (ui/)                      |
|  MainWindow | TabWidget | TechPadEditor | ToolBar | Drawer  |
+-------------------------------------------------------------+
                             | (Calls Services only)
                             v
+-------------------------------------------------------------+
|                      Services (services/)                   |
|  ScratchpadService | ImageService | SessionService          |
|  (Business logic, validation, debouncing, JPEG compression) |
+-------------------------------------------------------------+
                             | (Calls Repositories)
                             v
+-------------------------------------------------------------+
|                  Repositories (repositories/)               |
|  ScratchpadRepository | ImageRepository | SessionRepository |
|  (SQL transactions, atomic updates, FTS5 queries)           |
+-------------------------------------------------------------+
                             | (Direct SQLite connection)
                             v
+-------------------------------------------------------------+
|                     Database (database/)                    |
|  Connection Manager (WAL mode, Foreign Keys, FTS5 Virtual)  |
+-------------------------------------------------------------+
```

### Layer Rules & Boundaries
- **No SQL in UI:** Components in `src/ui/` never execute SQL queries directly. All actions flow through `src/services/`.
- **Atomic Operations:** Repositories wrap multi-statement updates in `with connection:` atomic blocks.
- **SQLite Concurrency:** SQLite is initialized with WAL mode (`PRAGMA journal_mode = WAL;`) and enforced foreign keys (`PRAGMA foreign_keys = ON;`).

---

## 3. Database Schema

### `scratchpads`
Stores active and archived ticket records.
- `id` (INTEGER PRIMARY KEY AUTOINCREMENT)
- `ticket_number` (TEXT NOT NULL)
- `client_name` (TEXT)
- `title` (TEXT)
- `content_html` (TEXT)
- `status` (TEXT: 'active' | 'archived' | 'deleted')
- `tab_order` (INTEGER)
- `created_at` (DATETIME)
- `updated_at` (DATETIME)

### `scratchpad_images`
Dedicated binary BLOB storage for inline screenshots.
- `id` (INTEGER PRIMARY KEY AUTOINCREMENT)
- `scratchpad_id` (INTEGER REFERENCES scratchpads(id) ON DELETE CASCADE)
- `image_name` (TEXT NOT NULL, e.g. `<uuid>.jpg`)
- `image_data` (BLOB NOT NULL)
- `mime_type` (TEXT DEFAULT 'image/jpeg')
- `created_at` (DATETIME)

### `app_session`
Maintains workspace state across restarts.
- `id` (INTEGER PRIMARY KEY CHECK (id = 1))
- `active_scratchpad_id` (INTEGER REFERENCES scratchpads(id) ON DELETE SET NULL)
- `window_geometry` (TEXT)
- `history_drawer_open` (INTEGER)
- `updated_at` (DATETIME)

### `scratchpad_fts` (FTS5)
Full-Text Search virtual table synchronizing with `scratchpads` via automatic triggers on `INSERT`, `UPDATE`, and `DELETE`.

---

## 4. Screenshot & Image Pipeline
1. **Capture & Interception:** User pastes screenshot (`Win + Shift + S` / `Ctrl + V`) or drops an image file onto `TechPadEditor`.
2. **Compression:** Image is compressed to JPEG at 85% quality factor via `QBuffer` and Pillow. This reduces raw clipboard screenshots from 8–15 MB down to 100–300 KB without sacrificing console font clarity.
3. **Internal Resource Registration:** The image is assigned a unique URI (`image://local/<uuid>.jpg`) and registered with `document().addResource(QTextDocument.ImageResource, ...)`.
4. **Persistence & Garbage Collection:** During auto-save, `ImageService` compares images referenced in the document HTML with stored BLOBs, persisting new images and purging unreferenced/deleted images.

---

## 5. Auto-Saving & Session Restoration
- **1500ms Debounce:** Keystrokes restart a single-shot timer. Once the technician stops typing for 1500ms, the document HTML and new image BLOBs persist seamlessly to SQLite.
- **Forced Sync:** Tab switches, new tab requests, and window close events (`closeEvent`) immediately trigger a synchronous flush.
- **Session Recovery:** On reboot, `SessionService` restores all active tabs in order, selects the previously active tab, and restores window size and position.

