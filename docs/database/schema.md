# Database Schema & Data Dictionary

## 1. Overview
T-Notes uses SQLite 3 with Write-Ahead Logging (`WAL`) mode enabled. The schema separates metadata, rich-text markup, and binary image attachments into dedicated tables to keep queries lightweight and fast.

---

## 2. Table Specifications

### 2.1 `scratchpads`
Stores active and archived ticket records.

| Column | Type | Constraints | Description |
| :--- | :--- | :--- | :--- |
| `id` | `INTEGER` | `PRIMARY KEY AUTOINCREMENT` | Unique identifier for the scratchpad. |
| `ticket_number` | `TEXT` | `NOT NULL` | Ticket reference number (e.g., `INC-4092`, `#10293`). |
| `client_name` | `TEXT` | `DEFAULT ''` | Client, department, or organization name. |
| `title` | `TEXT` | `DEFAULT ''` | Ticket subject or brief summary. |
| `content_html` | `TEXT` | `DEFAULT ''` | Full rich-text document HTML markup. |
| `status` | `TEXT` | `DEFAULT 'active' CHECK(status IN ('active', 'archived', 'deleted'))` | State of the ticket. |
| `tab_order` | `INTEGER` | `DEFAULT 0` | Display index in the active tab bar. |
| `elapsed_seconds` | `INTEGER` | `DEFAULT 0` | Cumulative troubleshooting time tracked by stopwatch. |
| `archived_at` | `DATETIME` | `DEFAULT NULL` | UTC timestamp when ticket was archived to history. |
| `created_at` | `DATETIME` | `DEFAULT CURRENT_TIMESTAMP` | UTC timestamp of ticket creation. |
| `updated_at` | `DATETIME` | `DEFAULT CURRENT_TIMESTAMP` | UTC timestamp of last content or metadata modification. |

**Indexes:**
```sql
CREATE INDEX IF NOT EXISTS idx_scratchpads_status_order ON scratchpads(status, tab_order);
```

---

### 2.2 `scratchpad_images`
Dedicated binary storage for inline and attached screenshot JPEGs.

| Column | Type | Constraints | Description |
| :--- | :--- | :--- | :--- |
| `id` | `INTEGER` | `PRIMARY KEY AUTOINCREMENT` | Unique identifier for the image record. |
| `scratchpad_id` | `INTEGER` | `NOT NULL`, `FOREIGN KEY REFERENCES scratchpads(id) ON DELETE CASCADE` | Parent scratchpad ID. |
| `image_name` | `TEXT` | `NOT NULL` | Unique file name referenced in HTML (e.g. `550e8400.jpg`). |
| `image_data` | `BLOB` | `NOT NULL` | Compressed JPEG binary bytes (quality factor 85). |
| `mime_type` | `TEXT` | `DEFAULT 'image/jpeg'` | MIME type of the stored image. |
| `created_at` | `DATETIME` | `DEFAULT CURRENT_TIMESTAMP` | UTC timestamp of image ingestion. |

**Indexes:**
```sql
CREATE UNIQUE INDEX IF NOT EXISTS idx_scratchpad_images_name 
ON scratchpad_images(scratchpad_id, image_name);
```

**Cascade Policy:**
When a scratchpad is deleted via `DELETE FROM scratchpads WHERE id = ?`, SQLite's foreign key engine automatically deletes all corresponding image rows in `scratchpad_images`.

---

### 2.3 `app_session`
Stores workspace state across application restarts as a singleton row (`id = 1`).

| Column | Type | Constraints | Description |
| :--- | :--- | :--- | :--- |
| `id` | `INTEGER` | `PRIMARY KEY CHECK (id = 1)` | Singleton identifier. |
| `active_scratchpad_id` | `INTEGER` | `FOREIGN KEY REFERENCES scratchpads(id) ON DELETE SET NULL` | ID of the focused tab when the app closed. |
| `window_geometry` | `TEXT` | `DEFAULT ''` | Hex-encoded Qt window geometry and position. |
| `window_opacity` | `INTEGER` | `DEFAULT 100` | Window opacity level from 60% to 100%. |
| `history_drawer_open` | `INTEGER` | `DEFAULT 0` | Boolean flag (0 or 1) indicating if the History Drawer was visible. |
| `split_view_active` | `INTEGER` | `DEFAULT 0` | Boolean flag (0 or 1) indicating if Split View mode was active. |
| `split_active_scratchpad_id` | `INTEGER` | `FOREIGN KEY REFERENCES scratchpads(id) ON DELETE SET NULL` | ID of the active/focused tab in the secondary split pane. |
| `primary_scratchpad_ids` | `TEXT` | `DEFAULT ''` | JSON string array of scratchpad IDs in display order for the primary pane. |
| `secondary_scratchpad_ids` | `TEXT` | `DEFAULT ''` | JSON string array of scratchpad IDs in display order for the secondary split pane. |
| `split_sizes` | `TEXT` | `DEFAULT ''` | JSON string array of pixel dimensions for the workspace horizontal splitter (`[width_left, width_right]`). |
| `updated_at` | `DATETIME` | `DEFAULT CURRENT_TIMESTAMP` | UTC timestamp of last session sync. |

---

### 2.4 `app_settings`
Stores persistent user preferences as key-value pairs.

| Column | Type | Constraints | Description |
| :--- | :--- | :--- | :--- |
| `key` | `TEXT` | `PRIMARY KEY` | Configuration key (e.g. `ticket_prefix`, `auto_save_delay_ms`). |
| `value` | `TEXT` | `NOT NULL` | String representation of the setting value. |

**Standard Keys:**
- `ticket_prefix`: Default ticket prefix for new tabs (default: `INC-`).
- `auto_save_delay_ms`: Debounced write delay in milliseconds (default: `1500`).
- `jpeg_quality`: Screenshot JPEG compression factor (default: `85`).
- `close_tab_action`: Close button workflow (`prompt` vs `archive`).
- `window_opacity`: Saved default opacity level (default: `100`).

---

### 2.5 `custom_templates`
Stores user-defined rich-text note templates with embedded formatting and images.

| Column | Type | Constraints | Description |
| :--- | :--- | :--- | :--- |
| `id` | `INTEGER` | `PRIMARY KEY AUTOINCREMENT` | Unique identifier for the custom template. |
| `title` | `TEXT` | `NOT NULL UNIQUE` | Unique title shown in the Template dropdown menu. |
| `content_html` | `TEXT` | `NOT NULL DEFAULT ''` | Self-contained rich-text HTML markup with embedded Base64 JPEG images. |
| `created_at` | `DATETIME` | `DEFAULT CURRENT_TIMESTAMP` | UTC timestamp of template creation. |
| `updated_at` | `DATETIME` | `DEFAULT CURRENT_TIMESTAMP` | UTC timestamp of last template edit. |

**Repository Access:**
Managed via `TemplateRepository` (`src/repositories/template_repository.py`) adhering to atomic transaction boundaries (`with connection:`).

---

## 3. SQLite PRAGMA Configuration

Every connection initialized by `DatabaseManager` runs the following PRAGMAs:

```sql
PRAGMA journal_mode = WAL;
PRAGMA foreign_keys = ON;
PRAGMA busy_timeout = 5000;
```

- **WAL Mode (`PRAGMA journal_mode = WAL;`):** Reads and writes do not block each other, preventing UI micro-stutters during debounced background saves.
- **Foreign Keys (`PRAGMA foreign_keys = ON;`):** Enforces referential integrity and activates `ON DELETE CASCADE`.
- **Busy Timeout (`PRAGMA busy_timeout = 5000;`):** Pauses for up to 5 seconds if the database is busy instead of throwing an immediate `sqlite3.OperationalError: database is locked`.

---

## 4. Migration Strategy & Version History

Database migrations are managed idempotently in `src/database/migrations.py`. On startup, `init_database(db_manager)` executes `schema.sql` and checks existing table pragmas to safely upgrade existing installations without data loss:

### 4.1 Implemented Migrations

1. **`app_session` Column Migration (`window_opacity`)**:
   - *Problem:* In earlier versions, `app_session` lacked `window_opacity`. Inserting the singleton row on older databases raised `sqlite3.OperationalError: table app_session has no column named window_opacity`.
   - *Resolution:* Before executing the singleton `INSERT OR IGNORE`, `init_database` inspects `PRAGMA table_info(app_session)`. If missing, it executes:
     ```sql
     ALTER TABLE app_session ADD COLUMN window_opacity INTEGER DEFAULT 100;
     ```

2. **`scratchpads` Time Tracking Columns (`elapsed_seconds`, `archived_at`)**:
   - *Problem:* The stopwatch and audit log system requires persistent tracking of active troubleshooting seconds and archival timestamps.
   - *Resolution:* Inspects `PRAGMA table_info(scratchpads)` and conditionally applies:
     ```sql
     ALTER TABLE scratchpads ADD COLUMN elapsed_seconds INTEGER DEFAULT 0;
     ALTER TABLE scratchpads ADD COLUMN archived_at DATETIME;
     ```

3. **`scratchpad_fts` External Content Rebuild**:
   - *Problem:* Early iterations of the FTS schema indexed a legacy column `content_text`. When updated to `content_html`, calling FTS index rebuild commands resulted in `no such column: T.content_text`.
   - *Resolution:* Inspects `SELECT sql FROM sqlite_master WHERE name = 'scratchpad_fts'`. If `content_text` is detected:
     - Drops existing triggers `scratchpads_ai`, `scratchpads_ad`, `scratchpads_au`.
     - Drops legacy virtual table `scratchpad_fts`.
     - Recreates `scratchpad_fts` referencing `content_html`.
     - Recreates synchronization triggers.
     - Runs `INSERT INTO scratchpad_fts(scratchpad_fts) VALUES('rebuild');`.

4. **Settings Singleton & Defaults**:
   - Populates missing keys into `app_settings` via `INSERT OR IGNORE` (`auto_save_delay_ms=1500`, `jpeg_quality=85`, `ticket_prefix=INC-`, `close_tab_action=prompt`, `window_opacity=100`).

---

## 5. Adding Future Migrations

If new tables or columns are introduced:
1. Add standard DDL to `src/database/schema.sql`.
2. Add safe `PRAGMA table_info` checks and `ALTER TABLE ... ADD COLUMN` statements in `src/database/migrations.py`.
3. Wrap all migration steps inside the atomic transaction block (`with conn:`).
4. Validate with automated migration tests in `tests/test_database.py`.


## Atomic note persistence (data-integrity candidate)

No schema migration is required. `ScratchpadRepository.save_content_with_images`
owns one `BEGIN IMMEDIATE` transaction for the ticket HTML/timestamp, referenced
JPEG upserts and removal of unreferenced images for that ticket. It rejects an
ambient transaction and missing ticket/image references. The connection context
commits once or rolls everything back, including FTS trigger effects. Existing
WAL, foreign keys and busy timeout remain enabled. Independent repository CRUD
methods must not be called inside this unit of work because they commit separately.
Synthetic fault tests cover HTML, image insert, cleanup and commit denial. SQLite
online backup/restore tests check integrity, foreign keys and HTML/BLOB consistency;
no production database is opened, migrated or copied by this task.
