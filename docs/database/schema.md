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

## 4. Migration Strategy

Database migrations are defined and managed in `src/database/migrations.py`.
- On application boot, `init_database(db_manager)` executes `src/database/schema.sql` idempotently using `CREATE TABLE IF NOT EXISTS`.
- If new tables or columns are introduced in future versions:
  1. Add new DDL statements to `src/database/schema.sql`.
  2. Implement idempotent `ALTER TABLE ... ADD COLUMN ...` checks in `src/database/migrations.py`.
  3. Ensure all automated tests in `tests/test_database.py` pass.

