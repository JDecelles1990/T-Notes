"""Unit tests for SQLite database connection, schema, migrations, and FTS5 indexing."""

import pytest
from src.database.connection import DatabaseManager
from src.database.migrations import init_database
from src.repositories.scratchpad_repository import ScratchpadRepository
from src.repositories.image_repository import ImageRepository
from src.repositories.session_repository import SessionRepository


@pytest.fixture
def db_manager(tmp_path):
    """Provides a fresh database manager with initialized schema for each test."""
    db_file = tmp_path / "test_techpad.db"
    manager = DatabaseManager(db_file)
    init_database(manager)
    yield manager
    manager.close()


def test_database_initialization_and_pragmas(db_manager):
    conn = db_manager.get_connection()
    # Check WAL mode
    journal_mode = conn.execute("PRAGMA journal_mode;").fetchone()[0]
    assert journal_mode.lower() == "wal"

    # Check Foreign keys enabled
    foreign_keys = conn.execute("PRAGMA foreign_keys;").fetchone()[0]
    assert foreign_keys == 1

    # Check tables exist
    tables = [
        row[0]
        for row in conn.execute(
            "SELECT name FROM sqlite_master WHERE type='table';"
        ).fetchall()
    ]
    assert "scratchpads" in tables
    assert "scratchpad_images" in tables
    assert "app_session" in tables
    assert "scratchpad_fts" in tables


def test_scratchpad_crud(db_manager):
    repo = ScratchpadRepository(db_manager)

    # Create
    sid = repo.create(
        ticket_number="INC-1001",
        client_name="Acme Corp",
        title="VPN Gateway Down",
        content_html="<p>Investigating tunnel drop.</p>",
    )
    assert sid > 0

    # Read
    ticket = repo.get_by_id(sid)
    assert ticket is not None
    assert ticket["ticket_number"] == "INC-1001"
    assert ticket["client_name"] == "Acme Corp"
    assert ticket["status"] == "active"

    # Update metadata
    repo.update_metadata(sid, ticket_number="INC-1001", client_name="Acme Corp", title="Resolved VPN")
    updated = repo.get_by_id(sid)
    assert updated["title"] == "Resolved VPN"

    # Update content
    repo.update_content(sid, "<p>Rebooted firewall tunnel.</p>")
    assert repo.get_by_id(sid)["content_html"] == "<p>Rebooted firewall tunnel.</p>"

    # Archive
    repo.archive(sid)
    assert repo.get_by_id(sid)["status"] == "archived"
    assert len(repo.get_active()) == 0
    assert len(repo.get_archived()) == 1

    # Restore
    repo.restore(sid, next_tab_order=0)
    assert repo.get_by_id(sid)["status"] == "active"
    assert len(repo.get_active()) == 1


def test_cascade_deletion_of_images(db_manager):
    scratch_repo = ScratchpadRepository(db_manager)
    img_repo = ImageRepository(db_manager)

    sid = scratch_repo.create(ticket_number="INC-2002")
    img_repo.save_image(sid, "test_snip.jpg", b"fake_jpeg_binary_data")

    assert img_repo.get_image(sid, "test_snip.jpg") == b"fake_jpeg_binary_data"

    # Permanently delete scratchpad
    scratch_repo.delete_permanently(sid)

    # Verify scratchpad is gone
    assert scratch_repo.get_by_id(sid) is None

    # Verify images were cascade-deleted
    assert img_repo.get_image(sid, "test_snip.jpg") is None


def test_fts5_search(db_manager):
    repo = ScratchpadRepository(db_manager)

    sid1 = repo.create(ticket_number="INC-3001", client_name="Contoso", title="DNS Failure", content_html="Domain controller nslookup timed out")
    sid2 = repo.create(ticket_number="INC-3002", client_name="Fabrikam", title="Printer Issue", content_html="Paper jam in tray 2")

    # Search by keyword in title
    results = repo.search("DNS")
    assert len(results) == 1
    assert results[0]["id"] == sid1

    # Search by client name
    results = repo.search("Fabrikam")
    assert len(results) == 1
    assert results[0]["id"] == sid2

    # Search by word in body
    results = repo.search("nslookup")
    assert len(results) == 1
    assert results[0]["id"] == sid1


def test_migration_adds_window_opacity_to_legacy_db(tmp_path):
    """Simulates an existing database from before window_opacity was introduced."""
    db_file = tmp_path / "legacy_techpad.db"
    manager = DatabaseManager(db_file)
    conn = manager.get_connection()

    # Create old table without window_opacity column
    with conn:
        conn.execute("""
            CREATE TABLE app_session (
                id INTEGER PRIMARY KEY CHECK (id = 1),
                active_scratchpad_id INTEGER,
                window_geometry TEXT DEFAULT '',
                history_drawer_open INTEGER DEFAULT 0,
                updated_at DATETIME DEFAULT CURRENT_TIMESTAMP
            );
        """)
        conn.execute("INSERT INTO app_session (id, active_scratchpad_id) VALUES (1, NULL);")

    # Now run init_database and verify it cleanly migrates without throwing OperationalError
    init_database(manager)

    # Verify column exists and is queryable
    row = conn.execute("SELECT window_opacity FROM app_session WHERE id = 1;").fetchone()
    assert row[0] == 100
    manager.close()


def test_migration_adds_elapsed_seconds_to_legacy_db(tmp_path):
    """Simulates an existing database from before elapsed_seconds was introduced on scratchpads."""
    db_file = tmp_path / "legacy_scratchpads.db"
    manager = DatabaseManager(db_file)
    conn = manager.get_connection()

    # Create old scratchpads table without elapsed_seconds column
    with conn:
        conn.execute("""
            CREATE TABLE scratchpads (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                ticket_number TEXT NOT NULL,
                client_name TEXT DEFAULT '',
                title TEXT DEFAULT '',
                content_html TEXT DEFAULT '',
                status TEXT DEFAULT 'active',
                tab_order INTEGER DEFAULT 0,
                created_at DATETIME DEFAULT CURRENT_TIMESTAMP,
                updated_at DATETIME DEFAULT CURRENT_TIMESTAMP
            );
        """)
        conn.execute("INSERT INTO scratchpads (ticket_number) VALUES ('INC-OLD-1');")

    # Run init_database which should migrate the table
    init_database(manager)

    repo = ScratchpadRepository(manager)
    ticket = repo.get_by_id(1)
    assert ticket is not None
    assert ticket.get("elapsed_seconds") == 0

    # Test updating elapsed time
    repo.update_elapsed_time(1, 450)
    ticket = repo.get_by_id(1)
    assert ticket["elapsed_seconds"] == 450
    manager.close()


def test_migration_upgrades_legacy_fts_with_content_text(tmp_path):
    """Simulates an existing database from when scratchpad_fts had the old content_text column."""
    db_file = tmp_path / "legacy_fts_db.db"
    manager = DatabaseManager(db_file)
    conn = manager.get_connection()

    with conn:
        conn.execute("""
            CREATE TABLE scratchpads (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                ticket_number TEXT NOT NULL,
                client_name TEXT DEFAULT '',
                title TEXT DEFAULT '',
                content_html TEXT DEFAULT '',
                status TEXT DEFAULT 'active',
                tab_order INTEGER DEFAULT 0,
                created_at DATETIME DEFAULT CURRENT_TIMESTAMP,
                updated_at DATETIME DEFAULT CURRENT_TIMESTAMP
            );
        """)
        conn.execute("INSERT INTO scratchpads (ticket_number, title, content_html) VALUES ('INC-999', 'Old FTS', 'Network outage');")

        # Create old FTS virtual table with 'content_text'
        conn.execute("""
            CREATE VIRTUAL TABLE scratchpad_fts USING fts5(
                ticket_number,
                client_name,
                title,
                content_text,
                content='scratchpads',
                content_rowid='id'
            );
        """)

    # Running init_database should detect the legacy content_text column and migrate cleanly
    init_database(manager)

    # Verify FTS virtual table was migrated to content_html
    sql_row = conn.execute("SELECT sql FROM sqlite_master WHERE name = 'scratchpad_fts';").fetchone()
    assert "content_html" in sql_row[0]
    assert "content_text" not in sql_row[0]

    # Verify search works across the migrated database
    repo = ScratchpadRepository(manager)
    results = repo.search("outage")
    assert len(results) == 1
    assert results[0]["ticket_number"] == "INC-999"

    manager.close()


