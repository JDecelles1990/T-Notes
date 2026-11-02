"""Database migration and initialization utilities."""

import sqlite3
from pathlib import Path
from src.database.connection import DatabaseManager


def init_database(db_manager: DatabaseManager) -> None:
    """Initializes the database schema and ensures required singleton rows exist."""
    schema_path = Path(__file__).resolve().parent / "schema.sql"
    with open(schema_path, "r", encoding="utf-8") as f:
        schema_sql = f.read()

    conn = db_manager.get_connection()
    with conn:
        conn.executescript(schema_sql)
        # Ensure session singleton row exists
        conn.execute("""
            INSERT OR IGNORE INTO app_session (id, active_scratchpad_id, window_geometry, history_drawer_open)
            VALUES (1, NULL, '', 0);
        """)

