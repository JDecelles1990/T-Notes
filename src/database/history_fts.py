"""SQLite FTS5 history migration, query sanitization, and ranked search backend."""

from __future__ import annotations

from dataclasses import dataclass
import html
import re
import sqlite3
import sys

# Expose as top-level `history_fts` as well so `from history_fts import ...` resolves seamlessly.
sys.modules.setdefault("history_fts", sys.modules[__name__])

FTS_MIGRATION_VERSION = 2

_SNIPPET_START = "\x01"
_SNIPPET_END = "\x02"
_TOKEN_RE = re.compile(r'"([^"]+)"|(\S+)')

# Known HTML elements produced by QTextDocument / T-Notes templates (never strips e.g. <jdoe@contoso.com>).
_HTML_HEAD_STYLE_RE = re.compile(r"<(?:head|style)\b[^>]*>.*?</(?:head|style)>", re.IGNORECASE | re.DOTALL)
_HTML_DOCTYPE_RE = re.compile(r"<!DOCTYPE[^>]*>", re.IGNORECASE)
_ARCHIVE_AUDIT_RE = re.compile(
    r'<div\s+class=["\']ticket-archive-audit["\'].*?</div>\s*</div>',
    re.IGNORECASE | re.DOTALL,
)
_HTML_BLOCK_BREAK_RE = re.compile(
    r"</?(?:p|div|br|hr|li|tr|h[1-6])\b[^>]*>",
    re.IGNORECASE,
)
_KNOWN_HTML_TAG_RE = re.compile(
    r"</?(?:html|head|meta|style|body|p|div|span|br|hr|ul|ol|li|h[1-6]|table|thead|tbody|tr|td|th|img|a|strong|b|em|i|u|s|code|pre|font)\b[^>]*>",
    re.IGNORECASE,
)


@dataclass(frozen=True)
class HistorySearchResult:
    id: int
    ticket_number: str
    client: str
    title: str
    tags: str
    archived_at: str
    snippet_html: str
    rank: float | None = None


def _detect_schema(conn: sqlite3.Connection) -> str:
    """Identifies whether the connection holds T-Notes `scratchpads` or standalone `ticket_history`."""
    tables = {
        row[0]
        for row in conn.execute(
            "SELECT name FROM sqlite_master WHERE type = 'table' AND name IN ('scratchpads', 'ticket_history')"
        ).fetchall()
    }
    if "scratchpads" in tables:
        return "scratchpads"
    if "ticket_history" in tables:
        return "ticket_history"
    raise sqlite3.OperationalError("Neither 'scratchpads' nor 'ticket_history' table exists.")


def _table_exists(conn: sqlite3.Connection, name: str) -> bool:
    row = conn.execute(
        "SELECT 1 FROM sqlite_master WHERE type = 'table' AND name = ?",
        (name,),
    ).fetchone()
    return row is not None


def migrate_history_fts(conn: sqlite3.Connection) -> bool:
    """Create the external-content FTS5 table, attach sync triggers, and backfill existing rows.

    Returns True if the migration ran, False if already applied.
    """
    current_version = conn.execute("PRAGMA user_version").fetchone()[0]
    if current_version >= FTS_MIGRATION_VERSION and _table_exists(conn, "history_tickets_fts"):
        return False

    schema_kind = _detect_schema(conn)
    in_tx = bool(conn.in_transaction)
    prev_isolation = conn.isolation_level
    if not in_tx:
        conn.isolation_level = None

    try:
        if in_tx:
            conn.execute("SAVEPOINT history_fts_migration")
        else:
            conn.execute("BEGIN IMMEDIATE")

        if schema_kind == "scratchpads":
            cols = {row[1] for row in conn.execute("PRAGMA table_info(scratchpads)").fetchall()}
            if "tags" not in cols:
                conn.execute("ALTER TABLE scratchpads ADD COLUMN tags TEXT DEFAULT ''")
            if "archived_at" not in cols:
                conn.execute("ALTER TABLE scratchpads ADD COLUMN archived_at DATETIME")

            conn.execute(
                """
                UPDATE scratchpads
                SET archived_at = COALESCE(NULLIF(updated_at, ''), NULLIF(created_at, ''), CURRENT_TIMESTAMP)
                WHERE status = 'archived' AND (archived_at IS NULL OR archived_at = '')
                """
            )

            conn.execute("DROP TRIGGER IF EXISTS history_tickets_ai")
            conn.execute("DROP TRIGGER IF EXISTS history_tickets_ad")
            conn.execute("DROP TRIGGER IF EXISTS history_tickets_au")
            conn.execute("DROP TABLE IF EXISTS history_tickets_fts")

            conn.execute(
                """
                CREATE VIRTUAL TABLE IF NOT EXISTS history_tickets_fts USING fts5(
                    ticket_number,
                    client_name,
                    title,
                    tags,
                    content_html,
                    content='scratchpads',
                    content_rowid='id',
                    tokenize='unicode61 remove_diacritics 2',
                    prefix='2 3'
                )
                """
            )

            conn.execute(
                """
                CREATE TRIGGER IF NOT EXISTS history_tickets_ai
                AFTER INSERT ON scratchpads BEGIN
                    INSERT INTO history_tickets_fts(
                        rowid, ticket_number, client_name, title, tags, content_html
                    ) VALUES (
                        new.id,
                        new.ticket_number,
                        coalesce(new.client_name, ''),
                        coalesce(new.title, ''),
                        coalesce(new.tags, ''),
                        coalesce(new.content_html, '')
                    );
                END
                """
            )

            conn.execute(
                """
                CREATE TRIGGER IF NOT EXISTS history_tickets_ad
                AFTER DELETE ON scratchpads BEGIN
                    INSERT INTO history_tickets_fts(
                        history_tickets_fts, rowid, ticket_number, client_name, title, tags, content_html
                    ) VALUES (
                        'delete',
                        old.id,
                        old.ticket_number,
                        coalesce(old.client_name, ''),
                        coalesce(old.title, ''),
                        coalesce(old.tags, ''),
                        coalesce(old.content_html, '')
                    );
                END
                """
            )

            conn.execute(
                """
                CREATE TRIGGER IF NOT EXISTS history_tickets_au
                AFTER UPDATE ON scratchpads BEGIN
                    INSERT INTO history_tickets_fts(
                        history_tickets_fts, rowid, ticket_number, client_name, title, tags, content_html
                    ) VALUES (
                        'delete',
                        old.id,
                        old.ticket_number,
                        coalesce(old.client_name, ''),
                        coalesce(old.title, ''),
                        coalesce(old.tags, ''),
                        coalesce(old.content_html, '')
                    );
                    INSERT INTO history_tickets_fts(
                        rowid, ticket_number, client_name, title, tags, content_html
                    ) VALUES (
                        new.id,
                        new.ticket_number,
                        coalesce(new.client_name, ''),
                        coalesce(new.title, ''),
                        coalesce(new.tags, ''),
                        coalesce(new.content_html, '')
                    );
                END
                """
            )
        else:
            conn.execute(
                """
                CREATE VIRTUAL TABLE IF NOT EXISTS history_tickets_fts USING fts5(
                    ticket_number,
                    client,
                    title,
                    tags,
                    body,
                    content='ticket_history',
                    content_rowid='id',
                    tokenize='unicode61 remove_diacritics 2',
                    prefix='2 3'
                )
                """
            )

            conn.execute(
                """
                CREATE TRIGGER IF NOT EXISTS history_tickets_ai
                AFTER INSERT ON ticket_history BEGIN
                    INSERT INTO history_tickets_fts(
                        rowid, ticket_number, client, title, tags, body
                    ) VALUES (
                        new.id, new.ticket_number, new.client, new.title, new.tags, new.body
                    );
                END
                """
            )

            conn.execute(
                """
                CREATE TRIGGER IF NOT EXISTS history_tickets_ad
                AFTER DELETE ON ticket_history BEGIN
                    INSERT INTO history_tickets_fts(
                        history_tickets_fts, rowid, ticket_number, client, title, tags, body
                    ) VALUES (
                        'delete', old.id, old.ticket_number, old.client, old.title, old.tags, old.body
                    );
                END
                """
            )

            conn.execute(
                """
                CREATE TRIGGER IF NOT EXISTS history_tickets_au
                AFTER UPDATE ON ticket_history BEGIN
                    INSERT INTO history_tickets_fts(
                        history_tickets_fts, rowid, ticket_number, client, title, tags, body
                    ) VALUES (
                        'delete', old.id, old.ticket_number, old.client, old.title, old.tags, old.body
                    );
                    INSERT INTO history_tickets_fts(
                        rowid, ticket_number, client, title, tags, body
                    ) VALUES (
                        new.id, new.ticket_number, new.client, new.title, new.tags, new.body
                    );
                END
                """
            )

        conn.execute("INSERT INTO history_tickets_fts(history_tickets_fts) VALUES('rebuild')")
        conn.execute(f"PRAGMA user_version = {FTS_MIGRATION_VERSION}")

        if in_tx:
            conn.execute("RELEASE SAVEPOINT history_fts_migration")
        else:
            conn.execute("COMMIT")
        return True
    except Exception:
        if in_tx:
            try:
                conn.execute("ROLLBACK TO SAVEPOINT history_fts_migration")
                conn.execute("RELEASE SAVEPOINT history_fts_migration")
            except sqlite3.Error:
                pass
        elif conn.in_transaction:
            conn.execute("ROLLBACK")
        raise
    finally:
        if not in_tx:
            conn.isolation_level = prev_isolation


def sanitize_fts5_query(raw_query: str) -> str | None:
    """Convert raw user input into a safe FTS5 MATCH expression.

    - Preserves closed double-quoted phrases ("blue screen").
    - Quotes individual tokens so hyphens, colons, paths, and AND/OR/NOT are literal.
    - Appends '*' to unquoted tokens for as-you-type prefix matching.
    - Returns None when no searchable alphanumeric tokens remain.
    """
    if not raw_query or not raw_query.strip():
        return None

    parts: list[str] = []
    for phrase, token in _TOKEN_RE.findall(raw_query):
        if phrase:
            cleaned = phrase.strip()
            if any(ch.isalnum() for ch in cleaned):
                escaped = cleaned.replace('"', '""')
                parts.append(f'"{escaped}"')
        elif token:
            cleaned = token.strip('"')
            if any(ch.isalnum() for ch in cleaned):
                escaped = cleaned.replace('"', '""')
                parts.append(f'"{escaped}"*')

    return " ".join(parts) if parts else None


def _strip_known_html(raw_text: str) -> str:
    """Strips QTextDocument/ticket HTML markup while preserving sentinel markers and angle-bracket literals."""
    if not raw_text:
        return ""
    if not _KNOWN_HTML_TAG_RE.search(raw_text) and not _HTML_DOCTYPE_RE.search(raw_text):
        return raw_text

    cleaned = _ARCHIVE_AUDIT_RE.sub(" ", raw_text)
    cleaned = _HTML_HEAD_STYLE_RE.sub(" ", cleaned)
    cleaned = _HTML_DOCTYPE_RE.sub(" ", cleaned)
    cleaned = _HTML_BLOCK_BREAK_RE.sub(" ", cleaned)
    cleaned = _KNOWN_HTML_TAG_RE.sub("", cleaned)
    cleaned = html.unescape(cleaned)
    cleaned = cleaned.replace("\xa0", " ")
    return re.sub(r"\s+", " ", cleaned).strip()


def _format_body_plain_text(raw_body: str) -> str:
    """Converts Qt rich-text HTML into readable multi-line plain text while preserving non-HTML angle brackets."""
    if not raw_body:
        return ""
    if not _KNOWN_HTML_TAG_RE.search(raw_body) and not _HTML_DOCTYPE_RE.search(raw_body):
        return raw_body

    cleaned = _HTML_HEAD_STYLE_RE.sub("", raw_body)
    cleaned = _HTML_DOCTYPE_RE.sub("", cleaned)
    cleaned = re.sub(r"<br\s*/?>", "\n", cleaned, flags=re.IGNORECASE)
    cleaned = re.sub(r"</(?:p|div|li|h[1-6]|tr)\s*>", "\n", cleaned, flags=re.IGNORECASE)
    cleaned = _KNOWN_HTML_TAG_RE.sub("", cleaned)
    cleaned = html.unescape(cleaned).replace("\xa0", " ")
    lines = [line.rstrip() for line in cleaned.splitlines()]
    text = "\n".join(lines).strip()
    return re.sub(r"\n{3,}", "\n\n", text)


def _format_snippet_html(raw_snippet: str) -> str:
    cleaned = _strip_known_html(raw_snippet or "")
    escaped = html.escape(cleaned)
    return escaped.replace(_SNIPPET_START, "<b>").replace(_SNIPPET_END, "</b>")


def _format_empty_preview(raw_body: str, max_len: int = 140) -> str:
    cleaned = _strip_known_html(raw_body or "")
    if not cleaned:
        return ""
    return html.escape(cleaned[:max_len])


def search_history(
    conn: sqlite3.Connection,
    query: str = "",
    *,
    client: str | None = None,
    date_from: str | None = None,
    date_to: str | None = None,
    sort_by: str = "relevance",
    limit: int = 100,
    offset: int = 0,
) -> tuple[list[HistorySearchResult], int]:
    """Search archived tickets with optional client and date-range filters.

    Returns ``(results, total_matching_count)``.
    """
    schema_kind = _detect_schema(conn)
    fts_expr = sanitize_fts5_query(query)

    if schema_kind == "scratchpads":
        table_name = "scratchpads"
        client_col = "h.client_name"
        archived_expr = "COALESCE(NULLIF(h.archived_at, ''), h.updated_at, '')"
        select_cols = (
            "h.id, h.ticket_number, COALESCE(h.client_name, ''), "
            "COALESCE(h.title, ''), COALESCE(h.tags, ''), "
            f"{archived_expr} AS archived_ts"
        )
        body_col = "COALESCE(h.content_html, '')"
        base_filters = ["h.status = 'archived'"]
    else:
        table_name = "ticket_history"
        client_col = "h.client"
        archived_expr = "h.archived_at"
        select_cols = (
            "h.id, h.ticket_number, COALESCE(h.client, ''), "
            "COALESCE(h.title, ''), COALESCE(h.tags, ''), "
            "COALESCE(h.archived_at, '') AS archived_ts"
        )
        body_col = "COALESCE(h.body, '')"
        base_filters = []

    filters: list[str] = list(base_filters)
    filter_params: list[object] = []

    if client:
        filters.append(f"{client_col} = ?")
        filter_params.append(client)
    if date_from:
        filters.append(f"{archived_expr} >= ?")
        filter_params.append(date_from)
    if date_to:
        upper = f"{date_to}\uffff" if len(date_to) == 10 else date_to
        filters.append(f"{archived_expr} <= ?")
        filter_params.append(upper)

    # Empty (or punctuation-only) query: browse newest archived directly
    if fts_expr is None:
        where_sql = f"WHERE {' AND '.join(filters)}" if filters else ""
        total = conn.execute(
            f"SELECT COUNT(*) FROM {table_name} AS h {where_sql}",
            filter_params,
        ).fetchone()[0]

        rows = conn.execute(
            f"""
            SELECT
                {select_cols},
                {body_col} AS preview_src
            FROM {table_name} AS h
            {where_sql}
            ORDER BY archived_ts DESC, h.id DESC
            LIMIT ? OFFSET ?
            """,
            [*filter_params, limit, offset],
        ).fetchall()

        results = [
            HistorySearchResult(
                id=row[0],
                ticket_number=row[1] or "",
                client=row[2] or "",
                title=row[3] or "",
                tags=row[4] or "",
                archived_at=row[5] or "",
                snippet_html=_format_empty_preview(row[6] or ""),
            )
            for row in rows
        ]
        return results, total

    # Full-text query path
    where_clauses = ["history_tickets_fts MATCH ?", *filters]
    where_sql = "WHERE " + " AND ".join(where_clauses)
    match_params: list[object] = [fts_expr, *filter_params]

    total = conn.execute(
        f"""
        SELECT COUNT(*)
        FROM history_tickets_fts
        JOIN {table_name} AS h ON h.id = history_tickets_fts.rowid
        {where_sql}
        """,
        match_params,
    ).fetchone()[0]

    # SQLite bm25() returns negative scores: more negative = better match, so ASC ranks best first.
    order_sql = (
        "ORDER BY archived_ts DESC, h.id DESC"
        if sort_by == "date"
        else "ORDER BY rank ASC, archived_ts DESC, h.id DESC"
    )

    # Weights match the 5 FTS5 columns: ticket_number, client, title, tags, body/content_html
    rows = conn.execute(
        f"""
        SELECT
            {select_cols},
            snippet(history_tickets_fts, -1, ?, ?, ' ... ', 18) AS raw_snippet,
            bm25(history_tickets_fts, 10.0, 5.0, 4.0, 2.0, 1.0) AS rank
        FROM history_tickets_fts
        JOIN {table_name} AS h ON h.id = history_tickets_fts.rowid
        {where_sql}
        {order_sql}
        LIMIT ? OFFSET ?
        """,
        [_SNIPPET_START, _SNIPPET_END, *match_params, limit, offset],
    ).fetchall()

    results = [
        HistorySearchResult(
            id=row[0],
            ticket_number=row[1] or "",
            client=row[2] or "",
            title=row[3] or "",
            tags=row[4] or "",
            archived_at=row[5] or "",
            snippet_html=_format_snippet_html(row[6]),
            rank=row[7],
        )
        for row in rows
    ]
    return results, total


def list_history_clients(conn: sqlite3.Connection) -> list[str]:
    """Returns distinct non-empty client names across archived tickets sorted alphabetically."""
    schema_kind = _detect_schema(conn)
    if schema_kind == "scratchpads":
        rows = conn.execute(
            """
            SELECT DISTINCT client_name
            FROM scratchpads
            WHERE status = 'archived' AND trim(coalesce(client_name, '')) <> ''
            ORDER BY client_name COLLATE NOCASE ASC
            """
        ).fetchall()
    else:
        rows = conn.execute(
            """
            SELECT DISTINCT client
            FROM ticket_history
            WHERE trim(coalesce(client, '')) <> ''
            ORDER BY client COLLATE NOCASE ASC
            """
        ).fetchall()
    return [row[0] for row in rows]


def get_history_ticket(conn: sqlite3.Connection, ticket_id: int) -> dict[str, str | int] | None:
    """Returns full normalized ticket fields for the preview pane in HistorySearchPage."""
    schema_kind = _detect_schema(conn)
    if schema_kind == "scratchpads":
        row = conn.execute(
            """
            SELECT
                id,
                ticket_number,
                COALESCE(client_name, ''),
                COALESCE(title, ''),
                COALESCE(tags, ''),
                COALESCE(content_html, ''),
                COALESCE(NULLIF(archived_at, ''), updated_at, '')
            FROM scratchpads
            WHERE id = ?
            """,
            (ticket_id,),
        ).fetchone()
    else:
        row = conn.execute(
            """
            SELECT
                id,
                ticket_number,
                COALESCE(client, ''),
                COALESCE(title, ''),
                COALESCE(tags, ''),
                COALESCE(body, ''),
                COALESCE(archived_at, '')
            FROM ticket_history
            WHERE id = ?
            """,
            (ticket_id,),
        ).fetchone()

    if row is None:
        return None
    return {
        "id": row[0],
        "ticket_number": row[1] or "",
        "client": row[2] or "",
        "title": row[3] or "",
        "tags": row[4] or "",
        "body": _format_body_plain_text(row[5] or ""),
        "archived_at": row[6] or "",
    }
