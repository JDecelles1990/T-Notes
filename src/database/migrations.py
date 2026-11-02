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

        # 1. Migration: Ensure window_opacity column exists on older databases BEFORE inserting
        pragma_cols = [r[1] for r in conn.execute("PRAGMA table_info(app_session);").fetchall()]
        if "window_opacity" not in pragma_cols:
            conn.execute("ALTER TABLE app_session ADD COLUMN window_opacity INTEGER DEFAULT 100;")

        # 2. Migration: Ensure elapsed_seconds and archived_at columns exist on scratchpads
        scratchpad_cols = [r[1] for r in conn.execute("PRAGMA table_info(scratchpads);").fetchall()]
        if "elapsed_seconds" not in scratchpad_cols:
            conn.execute("ALTER TABLE scratchpads ADD COLUMN elapsed_seconds INTEGER DEFAULT 0;")
        if "archived_at" not in scratchpad_cols:
            conn.execute("ALTER TABLE scratchpads ADD COLUMN archived_at DATETIME;")

        # 3. Ensure session singleton row exists
        conn.execute("""
            INSERT OR IGNORE INTO app_session (id, active_scratchpad_id, window_geometry, window_opacity, history_drawer_open)
            VALUES (1, NULL, '', 100, 0);
        """)

        # 4. Populate default settings in app_settings table
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

        # 5. Synchronize FTS5 index with scratchpads table
        conn.execute("INSERT INTO scratchpad_fts(scratchpad_fts) VALUES('rebuild');")
