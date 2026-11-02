"""Database migration and initialization utilities."""

import sqlite3
from pathlib import Path
from src.database.connection import DatabaseManager


def init_database(db_manager: DatabaseManager) -> None:
    """Initializes the database schema, runs migrations, and ensures required rows exist."""
    schema_path = Path(__file__).resolve().parent / "schema.sql"
    with open(schema_path, "r", encoding="utf-8") as f:
        schema_sql = f.read()

    conn = db_manager.get_connection()
    with conn:
        conn.executescript(schema_sql)

        # Ensure session singleton row exists
        conn.execute("""
            INSERT OR IGNORE INTO app_session (id, active_scratchpad_id, window_geometry, window_opacity, history_drawer_open)
            VALUES (1, NULL, '', 100, 0);
        """)

        # Migration: Ensure window_opacity column exists on older databases
        pragma_cols = [r[1] for r in conn.execute("PRAGMA table_info(app_session);").fetchall()]
        if "window_opacity" not in pragma_cols:
            conn.execute("ALTER TABLE app_session ADD COLUMN window_opacity INTEGER DEFAULT 100;")

        # Populate default settings in app_settings table
        default_settings = [
            ("auto_save_delay_ms", "1500"),
            ("jpeg_quality", "85"),
            ("ticket_prefix", "INC-"),
            ("close_tab_action", "prompt"),
            ("window_opacity", "100"),
        ]
        for key, val in default_settings:
            conn.execute(
                "INSERT OR IGNORE INTO app_settings (key, value) VALUES (?, ?);",
                (key, val),
            )
