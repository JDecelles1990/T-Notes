"""Repository for custom user ticket templates."""

from typing import Any, Dict, List, Optional
from src.database.connection import DatabaseManager


class TemplateRepository:
    """Manages SQLite persistence for user-defined ticket templates."""

    def __init__(self, db_manager: DatabaseManager):
        self.db = db_manager

    def create(self, title: str, content_html: str) -> int:
        """
        Creates or updates a custom template record with atomic SQLite transaction.
        Returns the template ID.
        """
        conn = self.db.get_connection()
        with conn:
            cursor = conn.execute(
                """
                INSERT INTO custom_templates (title, content_html, updated_at)
                VALUES (?, ?, CURRENT_TIMESTAMP)
                ON CONFLICT(title) DO UPDATE SET
                    content_html = excluded.content_html,
                    updated_at = CURRENT_TIMESTAMP
                """,
                (title.strip(), content_html),
            )
            return cursor.lastrowid

    def get_by_id(self, template_id: int) -> Optional[Dict[str, Any]]:
        """Retrieves a single template by its database ID."""
        conn = self.db.get_connection()
        row = conn.execute(
            """
            SELECT id, title, content_html, created_at, updated_at
            FROM custom_templates
            WHERE id = ?
            """,
            (template_id,),
        ).fetchone()
        return dict(row) if row else None

    def get_by_title(self, title: str) -> Optional[Dict[str, Any]]:
        """Retrieves a single template by its title (case-insensitive lookup)."""
        conn = self.db.get_connection()
        row = conn.execute(
            """
            SELECT id, title, content_html, created_at, updated_at
            FROM custom_templates
            WHERE title = ? COLLATE NOCASE
            """,
            (title.strip(),),
        ).fetchone()
        return dict(row) if row else None

    def get_all(self) -> List[Dict[str, Any]]:
        """Returns all custom templates sorted alphabetically by title."""
        conn = self.db.get_connection()
        rows = conn.execute(
            """
            SELECT id, title, content_html, created_at, updated_at
            FROM custom_templates
            ORDER BY title COLLATE NOCASE ASC
            """
        ).fetchall()
        return [dict(row) for row in rows]

    def update(self, template_id: int, title: str, content_html: str) -> bool:
        """Updates an existing template's title and content."""
        conn = self.db.get_connection()
        with conn:
            cursor = conn.execute(
                """
                UPDATE custom_templates
                SET title = ?, content_html = ?, updated_at = CURRENT_TIMESTAMP
                WHERE id = ?
                """,
                (title.strip(), content_html, template_id),
            )
            return cursor.rowcount > 0

    def delete(self, template_id: int) -> bool:
        """Deletes a template by ID."""
        conn = self.db.get_connection()
        with conn:
            cursor = conn.execute(
                "DELETE FROM custom_templates WHERE id = ?",
                (template_id,),
            )
            return cursor.rowcount > 0

    def delete_by_title(self, title: str) -> bool:
        """Deletes a template by title."""
        conn = self.db.get_connection()
        with conn:
            cursor = conn.execute(
                "DELETE FROM custom_templates WHERE title = ? COLLATE NOCASE",
                (title.strip(),),
            )
            return cursor.rowcount > 0

