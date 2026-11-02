# Full-Text Search (FTS5) & Indexing

## 1. Overview
Technicians often need to search across hundreds of archived tickets to locate past solutions, specific error codes (e.g. `0x80070005`), device hostnames, or user accounts.

T-Notes implements an SQLite **FTS5** (Full-Text Search 5) virtual table connected to `scratchpads` via content synchronization triggers. This enables millisecond query execution across ticket numbers, client names, subjects, and note bodies.

---

## 2. Virtual Table Definition

```sql
CREATE VIRTUAL TABLE IF NOT EXISTS scratchpad_fts USING fts5(
    ticket_number,
    client_name,
    title,
    content_text,
    content='scratchpads',
    content_rowid='id'
);
```

- **External Content Table (`content='scratchpads'`):** The FTS table does not duplicate text storage; it indexes data directly from `scratchpads`, keeping the `.db` file compact.
- **Indexed Columns:**
  - `ticket_number`: Ticket identifier.
  - `client_name`: Client / department name.
  - `title`: Subject / short summary.
  - `content_text`: HTML body text.

---

## 3. Automatic Synchronization Triggers

Because `scratchpad_fts` uses external content, three database triggers maintain real-time synchronization on every insert, delete, or update in `scratchpads`:

```sql
-- 1. After Insert: Add new record to FTS index
CREATE TRIGGER IF NOT EXISTS scratchpads_ai AFTER INSERT ON scratchpads BEGIN
  INSERT INTO scratchpad_fts(rowid, ticket_number, client_name, title, content_text)
  VALUES (new.id, new.ticket_number, coalesce(new.client_name, ''), coalesce(new.title, ''), coalesce(new.content_html, ''));
END;

-- 2. After Delete: Remove deleted record from FTS index
CREATE TRIGGER IF NOT EXISTS scratchpads_ad AFTER DELETE ON scratchpads BEGIN
  INSERT INTO scratchpad_fts(scratchpad_fts, rowid, ticket_number, client_name, title, content_text)
  VALUES('delete', old.id, old.ticket_number, coalesce(old.client_name, ''), coalesce(old.title, ''), coalesce(old.content_html, ''));
END;

-- 3. After Update: Remove old token entries and re-index updated text
CREATE TRIGGER IF NOT EXISTS scratchpads_au AFTER UPDATE ON scratchpads BEGIN
  INSERT INTO scratchpad_fts(scratchpad_fts, rowid, ticket_number, client_name, title, content_text)
  VALUES('delete', old.id, old.ticket_number, coalesce(old.client_name, ''), coalesce(old.title, ''), coalesce(old.content_html, ''));
  INSERT INTO scratchpad_fts(rowid, ticket_number, client_name, title, content_text)
  VALUES (new.id, new.ticket_number, coalesce(new.client_name, ''), coalesce(new.title, ''), coalesce(new.content_html, ''));
END;
```

---

## 4. Query Construction & Sanitization

User search input is sanitized and formatted in `ScratchpadRepository.search()`:

### Tokenization & Prefix Matching
To provide real-time suggestions as the technician types in the History Drawer:
1. Special characters and FTS punctuation (quotes, asterisks, parentheses) are stripped or replaced with whitespace to avoid `OperationalError: syntax error`.
2. Each word token is enclosed in quotes and appended with a wildcard prefix operator `*`:
   ```python
   # Example: user types "acme dns"
   sanitized = "".join(ch if ch.isalnum() else " " for ch in clean_query).strip()
   tokens = sanitized.split()
   fts_query = " ".join(f'"{t}"*' for t in tokens)
   # Result: '"acme"* "dns"*'
   ```

### Execution Query
```sql
SELECT s.id, s.ticket_number, s.client_name, s.title, s.content_html, s.status, s.tab_order, s.created_at, s.updated_at
FROM scratchpads s
JOIN scratchpad_fts f ON s.id = f.rowid
WHERE scratchpad_fts MATCH ? AND s.status = ?
ORDER BY s.updated_at DESC
LIMIT 100;
```

### Resilient Fallback
If an unexpected FTS syntax error occurs (e.g. malformed inputs), the repository gracefully catches `sqlite3.OperationalError` and falls back to a standard SQL `LIKE %...%` query across all columns, ensuring the search UI never crashes.

