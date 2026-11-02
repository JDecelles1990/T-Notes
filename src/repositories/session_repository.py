"""Repository for persisting active workspace and session state."""

from datetime import datetime, timezone
from typing import Any, Dict, Optional
from src.database.connection import DatabaseManager


def _get_utc_now_str() -> str:
    return datetime.now(timezone.utc).strftime("%Y-%m-%d %H:%M:%S")


class SessionRepository:
    """Manages application session persistence."""

    def __init__(self, db_manager: DatabaseManager):
        self.db = db_manager

    def save_session(
        self,
        active_scratchpad_id: Optional[int],
        window_geometry: str = "",
        history_drawer_open: bool = False,
    ) -> None:
        """Saves current active tab, window geometry, and drawer state."""
        conn = self.db.get_connection()
        now = _get_utc_now_str()
        with conn:
            conn.execute(
                """
                INSERT INTO app_session (id, active_scratchpad_id, window_geometry, history_drawer_open, updated_at)
                VALUES (1, ?, ?, ?, ?)
                ON CONFLICT(id) DO UPDATE SET
                    active_scratchpad_id = excluded.active_scratchpad_id,
                    window_geometry = excluded.window_geometry,
                    history_drawer_open = excluded.history_drawer_open,
                    updated_at = excluded.updated_at
                """,
                (active_scratchpad_id, window_geometry, 1 if history_drawer_open else 0, now),
            )

    def get_session(self) -> Optional[Dict[str, Any]]:
        """Retrieves saved session data."""
        conn = self.db.get_connection()
        row = conn.execute(
            """
            SELECT id, active_scratchpad_id, window_geometry, history_drawer_open, updated_at
            FROM app_session
            WHERE id = 1
            """
        ).fetchone()
        return dict(row) if row else None
