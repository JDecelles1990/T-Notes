"""Repository for scratchpad CRUD and full-text search operations."""

from datetime import datetime, timezone
from typing import Any, Dict, List, Optional, Tuple
from src.database.connection import DatabaseManager


def _get_utc_now_str() -> str:
    return datetime.now(timezone.utc).strftime("%Y-%m-%d %H:%M:%S")


class ScratchpadRepository:
    """Manages database transactions for the scratchpads table."""

    def __init__(self, db_manager: DatabaseManager):
        self.db = db_manager

    def create(
        self,
        ticket_number: str,
        client_name: str = "",
        title: str = "",
        content_html: str = "",
        status: str = "active",
        tab_order: int = 0,
    ) -> int:
        """Inserts a new scratchpad and returns its generated ID."""
        conn = self.db.get_connection()
        now = _get_utc_now_str()
        with conn:
            cursor = conn.execute(
                """
                INSERT INTO scratchpads (ticket_number, client_name, title, content_html, status, tab_order, created_at, updated_at)
                VALUES (?, ?, ?, ?, ?, ?, ?, ?)
                """,
                (ticket_number.strip(), client_name.strip(), title.strip(), content_html, status, tab_order, now, now),
            )
            return cursor.lastrowid

    def get_by_id(self, scratchpad_id: int) -> Optional[Dict[str, Any]]:
        """Retrieves a single scratchpad by ID."""
        conn = self.db.get_connection()
        row = conn.execute(
            """
            SELECT id, ticket_number, client_name, title, content_html, status, tab_order, created_at, updated_at
            FROM scratchpads
            WHERE id = ?
            """,
            (scratchpad_id,),
        ).fetchone()
        return dict(row) if row else None

    def get_active(self) -> List[Dict[str, Any]]:
        """Returns all active scratchpads ordered by tab_order ASC."""
        conn = self.db.get_connection()
        rows = conn.execute(
            """
            SELECT id, ticket_number, client_name, title, content_html, status, tab_order, created_at, updated_at
            FROM scratchpads
            WHERE status = 'active'
            ORDER BY tab_order ASC, id ASC
            """
        ).fetchall()
        return [dict(r) for r in rows]

    def get_archived(self, limit: int = 100, offset: int = 0) -> List[Dict[str, Any]]:
        """Returns archived scratchpads ordered by updated_at DESC."""
        conn = self.db.get_connection()
        rows = conn.execute(
            """
            SELECT id, ticket_number, client_name, title, content_html, status, tab_order, created_at, updated_at
            FROM scratchpads
            WHERE status = 'archived'
            ORDER BY updated_at DESC
            LIMIT ? OFFSET ?
            """,
            (limit, offset),
        ).fetchall()
        return [dict(r) for r in rows]

    def update_content(self, scratchpad_id: int, content_html: str) -> None:
        """Updates the HTML content and updated_at timestamp."""
        conn = self.db.get_connection()
        now = _get_utc_now_str()
        with conn:
            conn.execute(
                """
                UPDATE scratchpads
                SET content_html = ?, updated_at = ?
                WHERE id = ?
                """,
                (content_html, now, scratchpad_id),
            )

    def update_metadata(self, scratchpad_id: int, ticket_number: str, client_name: str, title: str) -> None:
        """Updates the ticket number, client, and summary title."""
        conn = self.db.get_connection()
        now = _get_utc_now_str()
        with conn:
            conn.execute(
                """
                UPDATE scratchpads
                SET ticket_number = ?, client_name = ?, title = ?, updated_at = ?
                WHERE id = ?
                """,
                (ticket_number.strip(), client_name.strip(), title.strip(), now, scratchpad_id),
            )

    def update_tab_orders(self, orders: List[Tuple[int, int]]) -> None:
        """Batch updates tab_order for a list of (scratchpad_id, order_index) tuples."""
        conn = self.db.get_connection()
        with conn:
            conn.executemany(
                """
                UPDATE scratchpads
                SET tab_order = ?
                WHERE id = ?
                """,
                [(order, sid) for sid, order in orders],
            )

    def archive(self, scratchpad_id: int) -> None:
        """Marks a scratchpad as archived."""
        conn = self.db.get_connection()
        now = _get_utc_now_str()
        with conn:
            conn.execute(
                """
                UPDATE scratchpads
                SET status = 'archived', updated_at = ?
                WHERE id = ?
                """,
                (now, scratchpad_id),
            )

    def restore(self, scratchpad_id: int, next_tab_order: int) -> None:
        """Restores an archived scratchpad back to active status."""
        conn = self.db.get_connection()
        now = _get_utc_now_str()
        with conn:
            conn.execute(
                """
                UPDATE scratchpads
                SET status = 'active', tab_order = ?, updated_at = ?
                WHERE id = ?
                """,
                (next_tab_order, now, scratchpad_id),
            )

    def delete_permanently(self, scratchpad_id: int) -> None:
        """Permanently deletes a scratchpad and its associated images (cascades)."""
        conn = self.db.get_connection()
        with conn:
            conn.execute(
                "DELETE FROM scratchpads WHERE id = ?",
                (scratchpad_id,),
            )

    def search(self, query: str, status: Optional[str] = None) -> List[Dict[str, Any]]:
        """
        Performs full-text search using FTS5 with prefix matching.
        Falls back to LIKE queries if FTS encounters syntax issues.
        """
        clean_query = query.strip()
        if not clean_query:
            return self.get_archived() if status == "archived" else self.get_active()

        conn = self.db.get_connection()
        # Format query for FTS5 prefix matching
        # Replace non-alphanumeric chars with spaces to prevent FTS syntax errors
        sanitized = "".join(ch if ch.isalnum() else " " for ch in clean_query).strip()
        if not sanitized:
            return []

        tokens = sanitized.split()
        fts_query = " ".join(f'"{t}"*' for t in tokens)

        try:
            if status:
                sql = """
                    SELECT s.id, s.ticket_number, s.client_name, s.title, s.content_html, s.status, s.tab_order, s.created_at, s.updated_at
                    FROM scratchpads s
                    JOIN scratchpad_fts f ON s.id = f.rowid
                    WHERE scratchpad_fts MATCH ? AND s.status = ?
                    ORDER BY s.updated_at DESC
                    LIMIT 100
                """
                rows = conn.execute(sql, (fts_query, status)).fetchall()
            else:
                sql = """
                    SELECT s.id, s.ticket_number, s.client_name, s.title, s.content_html, s.status, s.tab_order, s.created_at, s.updated_at
                    FROM scratchpads s
                    JOIN scratchpad_fts f ON s.id = f.rowid
                    WHERE scratchpad_fts MATCH ?
                    ORDER BY s.updated_at DESC
                    LIMIT 100
                """
                rows = conn.execute(sql, (fts_query,)).fetchall()
            return [dict(r) for r in rows]
        except sqlite3.OperationalError:
            # Fallback to standard LIKE matching
            pattern = f"%{clean_query}%"
            if status:
                sql = """
                    SELECT id, ticket_number, client_name, title, content_html, status, tab_order, created_at, updated_at
                    FROM scratchpads
                    WHERE status = ? AND (ticket_number LIKE ? OR client_name LIKE ? OR title LIKE ? OR content_html LIKE ?)
                    ORDER BY updated_at DESC
                    LIMIT 100
                """
                rows = conn.execute(sql, (status, pattern, pattern, pattern, pattern)).fetchall()
            else:
                sql = """
                    SELECT id, ticket_number, client_name, title, content_html, status, tab_order, created_at, updated_at
                    FROM scratchpads
                    WHERE ticket_number LIKE ? OR client_name LIKE ? OR title LIKE ? OR content_html LIKE ?
                    ORDER BY updated_at DESC
                    LIMIT 100
                """
                rows = conn.execute(sql, (pattern, pattern, pattern, pattern)).fetchall()
            return [dict(r) for r in rows]
