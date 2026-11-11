"""Unit tests for BackupService: online SQLite snapshots and ZIP notes export."""

from datetime import datetime, timedelta
import json
import os
from pathlib import Path
import pytest
import sqlite3
import zipfile

from src.database.connection import DatabaseManager
from src.database.migrations import init_database
from src.repositories.image_repository import ImageRepository
from src.repositories.scratchpad_repository import ScratchpadRepository
from src.services.backup_service import BackupService


@pytest.fixture
def backup_env(tmp_path):
    db_file = tmp_path / "test_backup.db"
    backup_dir = tmp_path / "backups"
    db_manager = DatabaseManager(db_file)
    init_database(db_manager)

    scratch_repo = ScratchpadRepository(db_manager)
    img_repo = ImageRepository(db_manager)

    # Populate a ticket with an image
    tid = scratch_repo.create(
        ticket_number="INC-9999",
        client_name="Wayne Enterprises",
        title="Firewall Outage",
        content_html="<h2>Outage Report</h2><p>Server 10.0.0.1 unreachable: <img src='image://local/test_snap.jpg'></p>",
    )
    img_repo.save_image(tid, "test_snap.jpg", b"FAKE_JPEG_IMAGE_BYTES_12345")

    # Add an archived ticket
    arch_id = scratch_repo.create(
        ticket_number="REQ-1002",
        client_name="Acme Corp",
        title="Laptop Provisioning",
        content_html="<p>Laptop shipped.</p>",
    )
    scratch_repo.archive(arch_id)

    service = BackupService(
        db_manager=db_manager,
        scratchpad_repo=scratch_repo,
        image_repo=img_repo,
        backup_dir=backup_dir,
    )
    yield service, db_manager, tmp_path
    db_manager.close()


def test_online_database_snapshot(backup_env):
    service, db_manager, _ = backup_env

    # 1. Create snapshot
    backup_path = service.create_backup_snapshot()
    assert backup_path.exists()
    assert backup_path.name.endswith(".db.bak")

    # 2. Verify snapshot integrity by connecting to it
    conn = sqlite3.connect(str(backup_path))
    conn.row_factory = sqlite3.Row
    row = conn.execute("SELECT ticket_number, client_name FROM scratchpads WHERE id = 1").fetchone()
    conn.close()

    assert row is not None
    assert row["ticket_number"] == "INC-9999"
    assert row["client_name"] == "Wayne Enterprises"


def test_purge_old_backups(backup_env):
    service, _, backup_dir_parent = backup_env

    # Create fresh backup today
    fresh_bak = service.create_backup_snapshot()
    assert fresh_bak.exists()

    # Create an artificially old backup file (10 days old)
    old_file = service.backup_dir / "techpad_2020-01-01.db.bak"
    old_file.write_text("old_backup_data")
    old_time = (datetime.now() - timedelta(days=10)).timestamp()
    os.utime(old_file, (old_time, old_time))

    # Purge with 7-day retention
    purged = service.purge_old_backups(retention_days=7)
    assert purged == 1
    assert not old_file.exists()
    assert fresh_bak.exists()


def test_export_all_notes_to_zip(backup_env):
    service, _, tmp_path = backup_env
    zip_dest = tmp_path / "notes_export.zip"

    exported_zip = service.export_all_notes_to_zip(zip_dest)
    assert exported_zip.exists()

    with zipfile.ZipFile(str(exported_zip), "r") as zf:
        namelist = zf.namelist()

        # Check manifest
        assert "manifest.json" in namelist
        manifest = json.loads(zf.read("manifest.json").decode("utf-8"))
        assert manifest["total_tickets"] == 2
        assert manifest["total_images"] == 1

        # Check tickets folder
        ticket_files = [n for n in namelist if n.startswith("tickets/") and n.endswith(".md")]
        assert len(ticket_files) == 2

        # Read active ticket markdown
        active_md = zf.read(ticket_files[0]).decode("utf-8")
        assert "INC-9999" in active_md or "REQ-1002" in active_md
        assert "---" in active_md  # frontmatter present

        # Check images folder
        assert "images/test_snap.jpg" in namelist
        assert zf.read("images/test_snap.jpg") == b"FAKE_JPEG_IMAGE_BYTES_12345"

