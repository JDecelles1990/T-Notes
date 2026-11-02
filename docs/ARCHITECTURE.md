# ARCHITECTURE.md — System Design & Specifications

## 1. Relational Schema (SQLite)

```sql
PRAGMA journal_mode = WAL;
PRAGMA foreign_keys = ON;

-- Active and archived scratchpad tickets
CREATE TABLE IF NOT EXISTS scratchpads (
    id TEXT PRIMARY KEY,               -- UUID string
    ticket_number TEXT NOT NULL,       -- e.g. "4821" or "INC-1092"
    client_name TEXT DEFAULT '',
    title TEXT DEFAULT '',
    content_html TEXT DEFAULT '',
    status TEXT CHECK(status IN ('active', 'archived')) DEFAULT 'active',
    tab_order INTEGER DEFAULT 0,
    created_at DATETIME DEFAULT CURRENT_TIMESTAMP,
    updated_at DATETIME DEFAULT CURRENT_TIMESTAMP
);

-- Compressed JPEG BLOB storage for ticket screenshots
CREATE TABLE IF NOT EXISTS scratchpad_images (
    id TEXT PRIMARY KEY,               -- UUID string matching internal URI
    scratchpad_id TEXT NOT NULL,
    image_data BLOB NOT NULL,          -- Compressed JPEG binary
    created_at DATETIME DEFAULT CURRENT_TIMESTAMP,
    FOREIGN KEY(scratchpad_id) REFERENCES scratchpads(id) ON DELETE CASCADE
);

-- Application session state for workspace restoration
CREATE TABLE IF NOT EXISTS app_session (
    key TEXT PRIMARY KEY,
    value TEXT NOT NULL
);

-- Full-Text Search virtual table
CREATE VIRTUAL TABLE IF NOT EXISTS scratchpad_fts USING fts5(
    ticket_number,
    client_name,
    title,
    content_plain,
    content='scratchpads',
    content_rowid='rowid'
);