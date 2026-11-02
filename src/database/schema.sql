-- TechPad SQLite Schema

PRAGMA journal_mode = WAL;
PRAGMA foreign_keys = ON;

-- Main ticket scratchpad records
CREATE TABLE IF NOT EXISTS scratchpads (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    ticket_number TEXT NOT NULL,
    client_name TEXT DEFAULT '',
    title TEXT DEFAULT '',
    content_html TEXT DEFAULT '',
    status TEXT DEFAULT 'active' CHECK(status IN ('active', 'archived', 'deleted')),
    tab_order INTEGER DEFAULT 0,
    created_at DATETIME DEFAULT CURRENT_TIMESTAMP,
    updated_at DATETIME DEFAULT CURRENT_TIMESTAMP
);

CREATE INDEX IF NOT EXISTS idx_scratchpads_status_order ON scratchpads(status, tab_order);

-- Binary storage for inline and attached images
CREATE TABLE IF NOT EXISTS scratchpad_images (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    scratchpad_id INTEGER NOT NULL,
    image_name TEXT NOT NULL,
    image_data BLOB NOT NULL,
    mime_type TEXT DEFAULT 'image/jpeg',
    created_at DATETIME DEFAULT CURRENT_TIMESTAMP,
    FOREIGN KEY(scratchpad_id) REFERENCES scratchpads(id) ON DELETE CASCADE
);

CREATE UNIQUE INDEX IF NOT EXISTS idx_scratchpad_images_name 
ON scratchpad_images(scratchpad_id, image_name);

-- Application session persistence
CREATE TABLE IF NOT EXISTS app_session (
    id INTEGER PRIMARY KEY CHECK (id = 1),
    active_scratchpad_id INTEGER,
    window_geometry TEXT DEFAULT '',
    history_drawer_open INTEGER DEFAULT 0,
    updated_at DATETIME DEFAULT CURRENT_TIMESTAMP,
    FOREIGN KEY(active_scratchpad_id) REFERENCES scratchpads(id) ON DELETE SET NULL
);

-- Full-Text Search virtual table for instant search across all tickets
CREATE VIRTUAL TABLE IF NOT EXISTS scratchpad_fts USING fts5(
    ticket_number,
    client_name,
    title,
    content_text,
    content='scratchpads',
    content_rowid='id'
);

-- Triggers for FTS5 synchronization
CREATE TRIGGER IF NOT EXISTS scratchpads_ai AFTER INSERT ON scratchpads BEGIN
  INSERT INTO scratchpad_fts(rowid, ticket_number, client_name, title, content_text)
  VALUES (new.id, new.ticket_number, coalesce(new.client_name, ''), coalesce(new.title, ''), coalesce(new.content_html, ''));
END;

CREATE TRIGGER IF NOT EXISTS scratchpads_ad AFTER DELETE ON scratchpads BEGIN
  INSERT INTO scratchpad_fts(scratchpad_fts, rowid, ticket_number, client_name, title, content_text)
  VALUES('delete', old.id, old.ticket_number, coalesce(old.client_name, ''), coalesce(old.title, ''), coalesce(old.content_html, ''));
END;

CREATE TRIGGER IF NOT EXISTS scratchpads_au AFTER UPDATE ON scratchpads BEGIN
  INSERT INTO scratchpad_fts(scratchpad_fts, rowid, ticket_number, client_name, title, content_text)
  VALUES('delete', old.id, old.ticket_number, coalesce(old.client_name, ''), coalesce(old.title, ''), coalesce(old.content_html, ''));
  INSERT INTO scratchpad_fts(rowid, ticket_number, client_name, title, content_text)
  VALUES (new.id, new.ticket_number, coalesce(new.client_name, ''), coalesce(new.title, ''), coalesce(new.content_html, ''));
END;

