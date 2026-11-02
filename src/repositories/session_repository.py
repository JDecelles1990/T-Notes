"""Repository for persisting active workspace, settings, and session state."""

from datetime import datetime, timezone
from typing import Any, Dict, Optional
from src.database.connection import DatabaseManager


def _get_utc_now_str() -> str:
    return datetime.now(timezone.utc).strftime("%Y-%m-%d %H:%M:%S")


class SessionRepository:
    """Manages application session persistence and user preferences."""

    def __init__(self, db_manager: DatabaseManager):
        self.db = db_manager

    def save_session(
        self,
        active_scratchpad_id: Optional[int],
        window_geometry: str = "",
        window_opacity: int = 100,
        history_drawer_open: bool = False,
    ) -> None:
        """Saves current active tab, window geometry, opacity, and drawer state."""
        conn = self.db.get_connection()
        now = _get_utc_now_str()
        with conn:
            conn.execute(
                """
                INSERT INTO app_session (id, active_scratchpad_id, window_geometry, window_opacity, history_drawer_open, updated_at)
                VALUES (1, ?, ?, ?, ?, ?)
                ON CONFLICT(id) DO UPDATE SET
                    active_scratchpad_id = excluded.active_scratchpad_id,
                    window_geometry = excluded.window_geometry,
                    window_opacity = excluded.window_opacity,
                    history_drawer_open = excluded.history_drawer_open,
                    updated_at = excluded.updated_at
                """,
                (active_scratchpad_id, window_geometry, window_opacity, 1 if history_drawer_open else 0, now),
            )

    def get_session(self) -> Optional[Dict[str, Any]]:
        """Retrieves saved session data."""
        conn = self.db.get_connection()
        row = conn.execute(
            """
            SELECT id, active_scratchpad_id, window_geometry, window_opacity, history_drawer_open, updated_at
            FROM app_session
            WHERE id = 1
            """
        ).fetchone()
        return dict(row) if row else None

    def get_all_settings(self) -> Dict[str, str]:
        """Retrieves all key-value settings from app_settings."""
        conn = self.db.get_connection()
        rows = conn.execute("SELECT key, value FROM app_settings").fetchall()
        return {r["key"]: r["value"] for r in rows}

    def get_setting(self, key: str, default: str = "") -> str:
        """Retrieves a single setting by key."""
        conn = self.db.get_connection()
        row = conn.execute("SELECT value FROM app_settings WHERE key = ?", (key,)).fetchone()
        return row["value"] if row else default

    def set_setting(self, key: str, value: str) -> None:
        """Saves or updates a setting."""
        conn = self.db.get_connection()
        with conn:
            conn.execute(
                """
                INSERT INTO app_settings (key, value) VALUES (?, ?)
                ON CONFLICT(key) DO UPDATE SET value = excluded.value
                """,
                (key, str(value)),
            )

    def set_settings(self, settings_dict: Dict[str, str]) -> None:
        """Batch saves multiple settings."""
        conn = self.db.get_connection()
        with conn:
            conn.executemany(
                """
                INSERT INTO app_settings (key, value) VALUES (?, ?)
                ON CONFLICT(key) DO UPDATE SET value = excluded.value
                """,
                [(k, str(v)) for k, v in settings_dict.items()],
            )
