"""SQLite FTS5 history migration, query sanitization, and ranked search backend."""

from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime, timezone
import html
import json
from pathlib import Path
import re
import shutil
import sqlite3
import sys
from typing import Iterable, Sequence
import unicodedata

from src.core.paths import resource_path

# Expose as top-level `history_fts` as well so `from history_fts import ...` resolves seamlessly.
sys.modules.setdefault("history_fts", sys.modules[__name__])

FTS_MIGRATION_VERSION = 3

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
    taxonomy_slugs: tuple[str, ...] = ()
    match_type: str = "exact"


def get_taxonomy_seed_path() -> Path:
    """Resolve taxonomy_seed.json cleanly in both source and frozen PyInstaller modes."""
    bundled = resource_path("src", "database", "taxonomy_seed.json")
    if bundled.is_file():
        return bundled
    return Path(__file__).resolve().parent / "taxonomy_seed.json"


def load_taxonomy_seed(seed_path: Path | None = None) -> dict:
    """Load the editable bilingual 3-axis MSP taxonomy catalog from JSON."""
    path = Path(seed_path) if seed_path is not None else get_taxonomy_seed_path()
    with open(path, "r", encoding="utf-8") as f:
        return json.load(f)


def _get_main_db_file(conn: sqlite3.Connection) -> Path | None:
    try:
        rows = conn.execute("PRAGMA database_list").fetchall()
    except sqlite3.Error:
        return None
    for row in rows:
        name = row[1] if len(row) > 1 else ""
        file_path = row[2] if len(row) > 2 else ""
        if name == "main" and file_path:
            p = Path(file_path)
            if p.is_file() and p.stat().st_size > 0:
                return p
    return None


def _has_preexisting_ticket_data(conn: sqlite3.Connection, schema_kind: str) -> bool:
    table_name = "scratchpads" if schema_kind == "scratchpads" else "ticket_history"
    try:
        row = conn.execute(f"SELECT 1 FROM {table_name} LIMIT 1").fetchone()
        return row is not None
    except sqlite3.Error:
        return False


def _ensure_pre_migration_backup(
    conn: sqlite3.Connection,
    *,
    current_version: int,
    target_version: int,
    schema_kind: str,
) -> Path | None:
    """Create a timestamped `.pre_fts_migration.bak` copy before upgrading non-empty file DBs."""
    db_file = _get_main_db_file(conn)
    if db_file is None:
        return None
    if current_version == 0 and not _has_preexisting_ticket_data(conn, schema_kind):
        return None

    existing = list(
        db_file.parent.glob(f"{db_file.name}.*v{target_version}_*.pre_fts_migration.bak")
    )
    if existing:
        return existing[0]

    ts = datetime.now(timezone.utc).strftime("%Y%m%d_%H%M%S")
    bak_path = db_file.parent / f"{db_file.name}.v{current_version}_to_v{target_version}_{ts}.pre_fts_migration.bak"

    if not conn.in_transaction:
        bak_conn = sqlite3.connect(str(bak_path))
        try:
            conn.backup(bak_conn)
        finally:
            bak_conn.close()
    else:
        shutil.copy2(db_file, bak_path)
    return bak_path


def _create_taxonomy_tables(conn: sqlite3.Connection, schema_kind: str) -> None:
    ticket_table = "scratchpads" if schema_kind == "scratchpads" else "ticket_history"
    conn.execute(
        """
        CREATE TABLE IF NOT EXISTS taxonomy_nodes (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            slug TEXT NOT NULL UNIQUE,
            axis TEXT NOT NULL CHECK(axis IN ('domain', 'symptom', 'resolution')),
            label TEXT NOT NULL,
            parent_slug TEXT,
            aliases_json TEXT NOT NULL DEFAULT '[]',
            sort_order INTEGER NOT NULL DEFAULT 0,
            is_active INTEGER NOT NULL DEFAULT 1,
            created_at DATETIME DEFAULT CURRENT_TIMESTAMP,
            updated_at DATETIME DEFAULT CURRENT_TIMESTAMP,
            FOREIGN KEY(parent_slug) REFERENCES taxonomy_nodes(slug) ON DELETE SET NULL
        )
        """
    )
    conn.execute(
        "CREATE INDEX IF NOT EXISTS idx_taxonomy_nodes_axis ON taxonomy_nodes(axis, sort_order)"
    )
    conn.execute(
        f"""
        CREATE TABLE IF NOT EXISTS ticket_taxonomy (
            ticket_id INTEGER NOT NULL,
            node_id INTEGER NOT NULL,
            source TEXT NOT NULL DEFAULT 'manual',
            confidence REAL NOT NULL DEFAULT 1.0,
            assigned_at DATETIME DEFAULT CURRENT_TIMESTAMP,
            PRIMARY KEY(ticket_id, node_id),
            FOREIGN KEY(ticket_id) REFERENCES {ticket_table}(id) ON DELETE CASCADE,
            FOREIGN KEY(node_id) REFERENCES taxonomy_nodes(id) ON DELETE CASCADE
        )
        """
    )
    conn.execute(
        "CREATE INDEX IF NOT EXISTS idx_ticket_taxonomy_node ON ticket_taxonomy(node_id, ticket_id)"
    )


def seed_taxonomy_nodes(conn: sqlite3.Connection, seed_path: Path | None = None) -> int:
    """Idempotently upsert taxonomy nodes from taxonomy_seed.json without touching ticket assignments."""
    data = load_taxonomy_seed(seed_path)
    nodes = data.get("nodes", [])
    upserted = 0
    for node in nodes:
        slug = str(node["slug"]).strip()
        axis = str(node["axis"]).strip()
        label = str(node["label"]).strip()
        parent_slug = node.get("parent_slug")
        parent_val = str(parent_slug).strip() if parent_slug else None
        aliases = [str(a).strip() for a in (node.get("aliases") or []) if str(a).strip()]
        sort_order = int(node.get("sort_order", 0))
        aliases_json = json.dumps(aliases, ensure_ascii=False)
        conn.execute(
            """
            INSERT INTO taxonomy_nodes (slug, axis, label, parent_slug, aliases_json, sort_order, is_active)
            VALUES (?, ?, ?, ?, ?, ?, 1)
            ON CONFLICT(slug) DO UPDATE SET
                axis = excluded.axis,
                label = excluded.label,
                parent_slug = excluded.parent_slug,
                aliases_json = excluded.aliases_json,
                sort_order = excluded.sort_order,
                is_active = 1,
                updated_at = CURRENT_TIMESTAMP
            """,
            (slug, axis, label, parent_val, aliases_json, sort_order),
        )
        upserted += 1
    return upserted


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


def migrate_history_fts(
    conn: sqlite3.Connection,
    *,
    seed_path: Path | None = None,
    _test_hook=None,
) -> bool:
    """Create the external-content FTS5 table, taxonomy schema/seeds, triggers, and backfill.

    Note on trigger safety: Neither `scratchpads` nor `ticket_history` defines any nested
    `AFTER UPDATE` triggers performing `UPDATE` statements back onto the same base table,
    preventing external-content FTS5 shadow-table corruption.

    Returns True if the migration ran, False if already at FTS_MIGRATION_VERSION.
    """
    current_version = conn.execute("PRAGMA user_version").fetchone()[0]
    has_fts = _table_exists(conn, "history_tickets_fts")
    has_tax = _table_exists(conn, "taxonomy_nodes") and _table_exists(conn, "ticket_taxonomy")
    if current_version >= FTS_MIGRATION_VERSION and has_fts and has_tax:
        return False

    schema_kind = _detect_schema(conn)
    _ensure_pre_migration_backup(
        conn,
        current_version=current_version,
        target_version=FTS_MIGRATION_VERSION,
        schema_kind=schema_kind,
    )

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
        _create_taxonomy_tables(conn, schema_kind)
        seed_taxonomy_nodes(conn, seed_path=seed_path)
        if _test_hook is not None:
            _test_hook(conn)
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


_FTS_BOOLEAN_WORDS = frozenset({"AND", "OR", "NOT"})


def sanitize_fts5_query(raw_query: str, *, match_any: bool = False) -> str | None:
    """Convert raw user input into a safe FTS5 MATCH expression.

    - Preserves closed double-quoted phrases ("blue screen").
    - Quotes individual tokens so hyphens (`INC-40219`), Windows paths (`C:\\Users\\...`),
      colons (`0x80070005:denied`), stray quotes, and boolean keywords (`AND`, `OR`, `NOT`)
      never trigger FTS5 syntax errors.
    - Preserves explicit `OR` only when joining two non-boolean search terms (or when
      `match_any=True`), so `sanitize_fts5_query("AND OR NOT")` safely quotes all three.
    - Appends `*` to unquoted tokens for as-you-type prefix matching.
    - Returns None when no searchable alphanumeric tokens remain.
    """
    if not raw_query or not raw_query.strip():
        return None

    raw_items = _TOKEN_RE.findall(raw_query)
    n = len(raw_items)
    parts: list[str] = []
    pending_or = False

    def _has_following_term(idx: int) -> bool:
        for p2, t2 in raw_items[idx + 1:]:
            if p2:
                return any(ch.isalnum() for ch in p2.strip())
            c2 = t2.strip('"')
            if c2 in _FTS_BOOLEAN_WORDS:
                return False
            if any(ch.isalnum() for ch in c2):
                return True
        return False

    last_was_non_bool = False
    for idx, (phrase, token) in enumerate(raw_items):
        if phrase:
            cleaned = phrase.strip()
            if any(ch.isalnum() for ch in cleaned):
                if (pending_or or match_any) and parts:
                    parts.append("OR")
                pending_or = False
                escaped = cleaned.replace('"', '""')
                parts.append(f'"{escaped}"')
                last_was_non_bool = True
        elif token:
            if not match_any and token == "OR" and parts and last_was_non_bool and _has_following_term(idx):
                pending_or = True
                last_was_non_bool = False
                continue
            cleaned = token.strip('"')
            if any(ch.isalnum() for ch in cleaned):
                if (pending_or or match_any) and parts:
                    parts.append("OR")
                pending_or = False
                escaped = cleaned.replace('"', '""')
                parts.append(f'"{escaped}"*')
                last_was_non_bool = token not in _FTS_BOOLEAN_WORDS

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


def _fetch_taxonomy_map(conn: sqlite3.Connection, ticket_ids: Sequence[int]) -> dict[int, tuple[str, ...]]:
    if not ticket_ids or not _table_exists(conn, "ticket_taxonomy"):
        return {}
    placeholders = ",".join("?" for _ in ticket_ids)
    rows = conn.execute(
        f"""
        SELECT tt.ticket_id, tn.slug
        FROM ticket_taxonomy tt
        JOIN taxonomy_nodes tn ON tn.id = tt.node_id
        WHERE tt.ticket_id IN ({placeholders})
        ORDER BY tn.axis ASC, tn.sort_order ASC, tn.slug ASC
        """,
        list(ticket_ids),
    ).fetchall()
    mapping: dict[int, list[str]] = {}
    for tid, slug in rows:
        mapping.setdefault(int(tid), []).append(str(slug))
    return {tid: tuple(slugs) for tid, slugs in mapping.items()}


def search_history(
    conn: sqlite3.Connection,
    query: str = "",
    *,
    client: str | None = None,
    boost_client: str | None = None,
    date_from: str | None = None,
    date_to: str | None = None,
    taxonomy_slugs: Sequence[str] | str | None = None,
    match_any: bool = False,
    sort_by: str = "relevance",
    limit: int = 100,
    offset: int = 0,
) -> tuple[list[HistorySearchResult], int]:
    """Search archived tickets with optional client, date-range, and 3-axis taxonomy filters.

    Returns ``(results, total_matching_count)``.
    """
    schema_kind = _detect_schema(conn)
    fts_expr = sanitize_fts5_query(query, match_any=match_any)

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

    if isinstance(taxonomy_slugs, str):
        slug_list = [s.strip() for s in taxonomy_slugs.split(",") if s.strip()]
    else:
        slug_list = [str(s).strip() for s in (taxonomy_slugs or ()) if str(s).strip()]

    for slug in slug_list:
        filters.append(
            """
            EXISTS (
                SELECT 1
                FROM ticket_taxonomy tt
                JOIN taxonomy_nodes tn ON tn.id = tt.node_id
                WHERE tt.ticket_id = h.id AND (tn.slug = ? OR tn.parent_slug = ?)
            )
            """
        )
        filter_params.extend([slug, slug])

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

        tax_map = _fetch_taxonomy_map(conn, [int(r[0]) for r in rows])
        results = [
            HistorySearchResult(
                id=row[0],
                ticket_number=row[1] or "",
                client=row[2] or "",
                title=row[3] or "",
                tags=row[4] or "",
                archived_at=row[5] or "",
                snippet_html=_format_empty_preview(row[6] or ""),
                taxonomy_slugs=tax_map.get(int(row[0]), ()),
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
    boost_clean = (boost_client or "").strip()
    if sort_by == "date":
        rank_select = "bm25(history_tickets_fts, 10.0, 5.0, 4.0, 2.0, 1.0) AS rank"
        order_sql = "ORDER BY archived_ts DESC, h.id DESC"
        select_params: list[object] = [_SNIPPET_START, _SNIPPET_END, *match_params, limit, offset]
    elif boost_clean:
        rank_select = (
            "(bm25(history_tickets_fts, 10.0, 5.0, 4.0, 2.0, 1.0) "
            f"- CASE WHEN lower({client_col}) = lower(?) THEN 15.0 ELSE 0.0 END) AS rank"
        )
        order_sql = "ORDER BY rank ASC, archived_ts DESC, h.id DESC"
        select_params = [_SNIPPET_START, _SNIPPET_END, boost_clean, *match_params, limit, offset]
    else:
        rank_select = "bm25(history_tickets_fts, 10.0, 5.0, 4.0, 2.0, 1.0) AS rank"
        order_sql = "ORDER BY rank ASC, archived_ts DESC, h.id DESC"
        select_params = [_SNIPPET_START, _SNIPPET_END, *match_params, limit, offset]

    # Weights match the 5 FTS5 columns: ticket_number, client, title, tags, body/content_html
    rows = conn.execute(
        f"""
        SELECT
            {select_cols},
            snippet(history_tickets_fts, -1, ?, ?, ' ... ', 18) AS raw_snippet,
            {rank_select}
        FROM history_tickets_fts
        JOIN {table_name} AS h ON h.id = history_tickets_fts.rowid
        {where_sql}
        {order_sql}
        LIMIT ? OFFSET ?
        """,
        select_params,
    ).fetchall()

    tax_map = _fetch_taxonomy_map(conn, [int(row[0]) for row in rows])
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
            taxonomy_slugs=tax_map.get(int(row[0]), ()),
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


_RELATED_TOKEN_RE = re.compile(r"[A-Za-z0-9À-ÿ][A-Za-z0-9À-ÿ._:-]*[A-Za-z0-9À-ÿ]|[A-Za-z0-9À-ÿ]+")
_RELATED_TIMESTAMP_RE = re.compile(r"\[\d{4}-\d{2}-\d{2}(?:\s+\d{2}:\d{2}(?::\d{2})?)?(?:\s*UTC)?\]")
_RELATED_STOPWORDS: frozenset[str] = frozenset({
    "the", "and", "for", "with", "from", "that", "this", "into", "onto", "when", "while",
    "where", "what", "which", "who", "how", "why", "not", "cant", "cannot", "unable",
    "working", "worked", "after", "before", "have", "has", "had", "been", "was", "were",
    "are", "is", "use", "tab", "will", "would", "could", "should", "may", "might", "can",
    "please", "check", "checked", "trying", "tried", "need", "needs", "issue", "problem",
    "ticket", "client", "subject", "caller", "status", "action", "taken", "steps",
    "description", "diagnostics", "troubleshooting", "root", "cause", "resolution", "notes",
    "note", "summary", "user", "users", "account", "daily", "scratchpad", "general",
    "welcome", "t-notes", "logs", "snips", "win", "shift", "untitled", "billet", "sujet",
    "probleme", "problème", "diagnostic", "solution", "pour", "avec", "dans", "sans",
    "sur", "sous", "par", "pas", "plus", "une", "des", "les", "est", "sont", "qui",
    "que", "quoi", "fait", "faire", "ete", "été", "depuis", "avant", "apres", "après",
    "utilisateur", "compte", "pass", "fail", "warn", "info", "screenshot",
})


def _extract_tokens_from_source(raw: str) -> list[str]:
    cleaned = _RELATED_TIMESTAMP_RE.sub(" ", _strip_known_html(raw or ""))
    tokens: list[str] = []
    for raw_tok in _RELATED_TOKEN_RE.findall(cleaned):
        tok = raw_tok.strip("._:-")
        if len(tok) < 2 or not any(ch.isalnum() for ch in tok):
            continue
        low = tok.lower()
        if low in _RELATED_STOPWORDS or low == "or":
            continue
        is_tech = any(ch.isdigit() or ch in "._:-" for ch in tok)
        if not is_tech and len(tok) < 3 and not tok.isupper():
            continue
        if tok.isdigit() and len(tok) < 3:
            continue
        tokens.append(tok)
    return tokens


def extract_related_keywords(title: str = "", note_text: str = "", max_terms: int = 5) -> list[str]:
    """Extract distinctive technical terms and error codes from subject + live note text."""
    title_tokens = _extract_tokens_from_source(title)
    note_tokens = _extract_tokens_from_source(note_text)

    # Prioritize Subject keywords, then technical codes/alphanumerics from live notes, then general note words
    prioritized: list[str] = []
    note_tech = [t for t in note_tokens if any(ch.isdigit() or ch in "._:-" for ch in t) or t.isupper()]
    note_other = [t for t in note_tokens if t not in note_tech]

    seen: set[str] = set()
    for tok in [*title_tokens, *note_tech, *note_other]:
        key = tok.lower()
        if key in seen:
            continue
        seen.add(key)
        prioritized.append(tok)
        if len(prioritized) >= max(1, int(max_terms)):
            break
    return prioritized


def find_related_history(
    conn: sqlite3.Connection,
    *,
    title: str = "",
    note_text: str = "",
    client: str = "",
    limit: int = 5,
) -> tuple[list[HistorySearchResult], int, str]:
    """Find archived tickets related by hybrid Subject + note keywords with optional client boost.

    Returns ``(results, total_matches, search_query_used)``.
    """
    client_clean = (client or "").strip()
    keywords = extract_related_keywords(title=title, note_text=note_text)
    if keywords:
        query_str = " OR ".join(keywords)
        results, total = search_history(
            conn,
            query_str,
            boost_client=client_clean or None,
            sort_by="relevance",
            limit=limit,
        )
        if total > 0:
            return results, total, query_str

    if client_clean:
        results, total = search_history(
            conn,
            "",
            client=client_clean,
            sort_by="date",
            limit=limit,
        )
        if total > 0:
            return results, total, ""

    return [], 0, ""


# =============================================================================
# 3-Axis Technical Troubleshooting Taxonomy & Bilingual Alias Matcher
# =============================================================================


def _fold_ascii_lower(text: str) -> str:
    """Return NFKD accent-stripped lowercase text so FR/EN aliases match regardless of accents."""
    if not text:
        return ""
    decomposed = unicodedata.normalize("NFKD", text)
    folded = "".join(ch for ch in decomposed if unicodedata.category(ch) != "Mn")
    return folded.lower()


def list_taxonomy_nodes(
    conn: sqlite3.Connection,
    *,
    axis: str | None = None,
    active_only: bool = True,
) -> list[dict[str, object]]:
    """Return taxonomy nodes ordered by axis and sort_order."""
    if not _table_exists(conn, "taxonomy_nodes"):
        return []
    clauses: list[str] = []
    params: list[object] = []
    if axis:
        clauses.append("axis = ?")
        params.append(axis)
    if active_only:
        clauses.append("is_active = 1")
    where_sql = f"WHERE {' AND '.join(clauses)}" if clauses else ""
    rows = conn.execute(
        f"""
        SELECT id, slug, axis, label, parent_slug, aliases_json, sort_order, is_active
        FROM taxonomy_nodes
        {where_sql}
        ORDER BY axis ASC, sort_order ASC, id ASC
        """,
        params,
    ).fetchall()
    nodes: list[dict[str, object]] = []
    for row in rows:
        try:
            aliases = json.loads(row[5] or "[]")
        except json.JSONDecodeError:
            aliases = []
        nodes.append(
            {
                "id": int(row[0]),
                "slug": row[1],
                "axis": row[2],
                "label": row[3],
                "parent_slug": row[4],
                "aliases": aliases,
                "sort_order": int(row[6]),
                "is_active": bool(row[7]),
            }
        )
    return nodes


def assign_ticket_taxonomy(
    conn: sqlite3.Connection,
    ticket_id: int,
    slugs: Iterable[str],
    *,
    source: str = "manual",
    confidence: float = 1.0,
    replace_existing: bool = False,
) -> list[dict[str, object]]:
    """Assign one or more taxonomy node slugs to a ticket cleanly within a transaction."""
    normalized = []
    seen: set[str] = set()
    for raw_slug in slugs:
        s = str(raw_slug).strip()
        if s and s not in seen:
            seen.add(s)
            normalized.append(s)

    in_tx = bool(conn.in_transaction)
    if not in_tx:
        conn.execute("BEGIN")
    try:
        if replace_existing:
            conn.execute("DELETE FROM ticket_taxonomy WHERE ticket_id = ?", (ticket_id,))

        if normalized:
            placeholders = ",".join("?" for _ in normalized)
            rows = conn.execute(
                f"SELECT id, slug FROM taxonomy_nodes WHERE slug IN ({placeholders})",
                normalized,
            ).fetchall()
            slug_to_id = {str(r[1]): int(r[0]) for r in rows}
            missing = [s for s in normalized if s not in slug_to_id]
            if missing:
                raise ValueError(f"Unknown taxonomy slug(s): {', '.join(missing)}")

            conf_clamped = max(0.0, min(1.0, float(confidence)))
            for slug in normalized:
                conn.execute(
                    """
                    INSERT INTO ticket_taxonomy (ticket_id, node_id, source, confidence)
                    VALUES (?, ?, ?, ?)
                    ON CONFLICT(ticket_id, node_id) DO UPDATE SET
                        source = excluded.source,
                        confidence = excluded.confidence,
                        assigned_at = CURRENT_TIMESTAMP
                    """,
                    (ticket_id, slug_to_id[slug], source, conf_clamped),
                )
        if not in_tx:
            conn.commit()
    except Exception:
        if not in_tx and conn.in_transaction:
            conn.rollback()
        raise

    return get_ticket_taxonomy(conn, ticket_id)


def get_ticket_taxonomy(conn: sqlite3.Connection, ticket_id: int) -> list[dict[str, object]]:
    """Return all taxonomy nodes assigned to a ticket ordered by axis and sort order."""
    if not _table_exists(conn, "ticket_taxonomy"):
        return []
    rows = conn.execute(
        """
        SELECT tn.id, tn.slug, tn.axis, tn.label, tn.parent_slug, tt.source, tt.confidence, tt.assigned_at
        FROM ticket_taxonomy tt
        JOIN taxonomy_nodes tn ON tn.id = tt.node_id
        WHERE tt.ticket_id = ?
        ORDER BY tn.axis ASC, tn.sort_order ASC, tn.slug ASC
        """,
        (ticket_id,),
    ).fetchall()
    return [
        {
            "id": int(r[0]),
            "slug": r[1],
            "axis": r[2],
            "label": r[3],
            "parent_slug": r[4],
            "source": r[5],
            "confidence": float(r[6]),
            "assigned_at": r[7],
        }
        for r in rows
    ]


def suggest_taxonomy_for_text(
    title: str = "",
    body: str = "",
    *,
    conn: sqlite3.Connection | None = None,
    seed_path: Path | None = None,
    max_per_axis: int = 2,
) -> dict[str, list[dict[str, object]]]:
    """Suggest top taxonomy nodes per axis (`domain`, `symptom`, `resolution`) via bilingual aliases."""
    suggestions: dict[str, list[dict[str, object]]] = {
        "domain": [],
        "symptom": [],
        "resolution": [],
    }
    if conn is not None and _table_exists(conn, "taxonomy_nodes"):
        nodes = list_taxonomy_nodes(conn, active_only=True)
    else:
        nodes = load_taxonomy_seed(seed_path).get("nodes", [])

    folded_title = _fold_ascii_lower(_strip_known_html(title or ""))
    folded_body = _fold_ascii_lower(_strip_known_html(body or ""))
    # Replace punctuation separators with spaces for clean boundary checks, preserving full string too
    norm_title = re.sub(r"[^a-z0-9]+", " ", folded_title).strip()
    norm_body = re.sub(r"[^a-z0-9]+", " ", folded_body).strip()
    if not norm_title and not norm_body:
        return suggestions

    title_words = set(norm_title.split())
    body_words = set(norm_body.split())

    for node in nodes:
        axis = str(node.get("axis", ""))
        if axis not in suggestions:
            continue
        # Skip coarse top-level domain parents when leaf subcategories exist with higher specificity,
        # unless no leaf matches (leaf nodes have parent_slug set or non-empty aliases).
        aliases = [str(a) for a in (node.get("aliases") or []) if str(a).strip()]
        if not aliases:
            continue

        score = 0.0
        matched_aliases: list[str] = []
        for raw_alias in aliases:
            alias_norm = re.sub(r"[^a-z0-9]+", " ", _fold_ascii_lower(raw_alias)).strip()
            if not alias_norm:
                continue
            alias_words = alias_norm.split()
            word_bonus = 1.4 if len(alias_words) > 1 else 1.0

            hit_title = (
                alias_norm in title_words
                if len(alias_words) == 1
                else f" {alias_norm} " in f" {norm_title} "
            )
            hit_body = (
                alias_norm in body_words
                if len(alias_words) == 1
                else f" {alias_norm} " in f" {norm_body} "
            )
            if hit_title:
                score += 3.0 * word_bonus
                matched_aliases.append(raw_alias)
            elif hit_body:
                score += 1.5 * word_bonus
                matched_aliases.append(raw_alias)

        if score > 0.0:
            # Prefer specific 2nd-level domain nodes over top-level container nodes when both match
            if axis == "domain" and node.get("parent_slug"):
                score += 0.5
            suggestions[axis].append(
                {
                    "slug": str(node["slug"]),
                    "axis": axis,
                    "label": str(node["label"]),
                    "parent_slug": node.get("parent_slug"),
                    "score": round(score, 2),
                    "confidence": round(min(0.99, 0.45 + 0.15 * len(matched_aliases)), 2),
                    "matched_aliases": matched_aliases,
                }
            )

    for axis_key, items in suggestions.items():
        items.sort(key=lambda item: (-float(item["score"]), -len(item["matched_aliases"]), str(item["slug"])))
        suggestions[axis_key] = items[: max(1, int(max_per_axis))]

    return suggestions
