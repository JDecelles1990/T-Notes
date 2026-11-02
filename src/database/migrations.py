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

        # 3. Migration: Migrate legacy scratchpad_fts if it was created with old 'content_text' column
        fts_row = conn.execute("SELECT sql FROM sqlite_master WHERE name = 'scratchpad_fts';").fetchone()
        if fts_row and "content_text" in fts_row[0]:
            conn.execute("DROP TRIGGER IF EXISTS scratchpads_ai;")
            conn.execute("DROP TRIGGER IF EXISTS scratchpads_ad;")
            conn.execute("DROP TRIGGER IF EXISTS scratchpads_au;")
            conn.execute("DROP TABLE IF EXISTS scratchpad_fts;")
            conn.execute("""
                CREATE VIRTUAL TABLE scratchpad_fts USING fts5(
                    ticket_number,
                    client_name,
                    title,
                    content_html,
                    content='scratchpads',
                    content_rowid='id'
                );
            """)
            conn.execute("""
                CREATE TRIGGER scratchpads_ai AFTER INSERT ON scratchpads BEGIN
                  INSERT INTO scratchpad_fts(rowid, ticket_number, client_name, title, content_html)
                  VALUES (new.id, new.ticket_number, coalesce(new.client_name, ''), coalesce(new.title, ''), coalesce(new.content_html, ''));
                END;
            """)
            conn.execute("""
                CREATE TRIGGER scratchpads_ad AFTER DELETE ON scratchpads BEGIN
                  INSERT INTO scratchpad_fts(scratchpad_fts, rowid, ticket_number, client_name, title, content_html)
                  VALUES('delete', old.id, old.ticket_number, coalesce(old.client_name, ''), coalesce(old.title, ''), coalesce(old.content_html, ''));
                END;
            """)
            conn.execute("""
                CREATE TRIGGER scratchpads_au AFTER UPDATE ON scratchpads BEGIN
                  INSERT INTO scratchpad_fts(scratchpad_fts, rowid, ticket_number, client_name, title, content_html)
                  VALUES('delete', old.id, old.ticket_number, coalesce(old.client_name, ''), coalesce(old.title, ''), coalesce(old.content_html, ''));
                  INSERT INTO scratchpad_fts(rowid, ticket_number, client_name, title, content_html)
                  VALUES (new.id, new.ticket_number, coalesce(new.client_name, ''), coalesce(new.title, ''), coalesce(new.content_html, ''));
                END;
            """)

        # 4. Ensure session singleton row exists
        conn.execute("""
            INSERT OR IGNORE INTO app_session (id, active_scratchpad_id, window_geometry, window_opacity, history_drawer_open)
            VALUES (1, NULL, '', 100, 0);
        """)

        # 5. Populate default settings in app_settings table
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

        # 6. Synchronize FTS5 index with scratchpads table
        try:
            conn.execute("INSERT INTO scratchpad_fts(scratchpad_fts) VALUES('rebuild');")
        except sqlite3.OperationalError:
            pass
