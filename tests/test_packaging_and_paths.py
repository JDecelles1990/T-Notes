"""Unit and integration tests for PyInstaller packaging helpers, frozen resource paths, and persistence."""

import ast
import sqlite3
import subprocess
import sys

from PySide6.QtGui import QImage, QImageReader, QImageWriter

from src.core.paths import (
    get_app_data_dir,
    get_bundle_root,
    get_legacy_app_data_dir,
    is_frozen,
    migrate_legacy_user_data,
    resource_path,
)
from src.core.powershell_utils import build_powershell_file_command, hidden_subprocess_kwargs
from src.database.connection import DatabaseManager
from src.database.migrations import init_database
from src.repositories.image_repository import ImageRepository
from src.repositories.scratchpad_repository import ScratchpadRepository
from src.services.autostart_service import AutostartService
from src.services.image_service import ImageService
from src.services.m365_preflight_service import M365PreflightService
from src.services.m365_worker_host import discover_pwsh


def test_resource_path_source_and_frozen(tmp_path, monkeypatch):
    """resource_path resolves repo root in source mode and sys._MEIPASS when frozen."""
    assert not is_frozen()
    assert resource_path("assets", "styles", "dark_theme.qss").is_file()
    assert resource_path("scripts", "m365", "_host", "M365WorkerHost.ps1").is_file()
    assert resource_path("scripts", "m365", "_host", "M365SyntheticRunner.ps1").is_file()
    assert resource_path("scripts", "m365", "_host", "M365PreflightProbe.ps1").is_file()

    monkeypatch.setattr(sys, "frozen", True, raising=False)
    monkeypatch.setattr(sys, "_MEIPASS", str(tmp_path), raising=False)

    assert is_frozen()
    assert get_bundle_root() == tmp_path.resolve()
    resolved = resource_path("scripts", "m365", "_host", "M365SyntheticRunner.ps1")
    assert resolved == tmp_path.resolve() / "scripts" / "m365" / "_host" / "M365SyntheticRunner.ps1"


def test_app_data_dir_targets_appdata_tnotes(tmp_path, monkeypatch):
    """Persistent user data resolves to %APPDATA%\\T-Notes on Windows."""
    if sys.platform != "win32":
        return
    monkeypatch.setenv("APPDATA", str(tmp_path))
    assert get_app_data_dir() == tmp_path / "T-Notes"

    local_dir = tmp_path / "Local"
    monkeypatch.setenv("LOCALAPPDATA", str(local_dir))
    assert get_legacy_app_data_dir() == local_dir / "TechPad"


def test_migrate_legacy_user_data_preserves_wal_notes_images_and_backups(tmp_path):
    """Online migration copies legacy TechPad WAL DB + backups to AppData\\T-Notes without deleting legacy."""
    legacy_dir = tmp_path / "legacy_techpad"
    target_dir = tmp_path / "roaming_tnotes"
    legacy_dir.mkdir(parents=True)

    # Seed legacy SQLite database in WAL mode with a scratchpad and embedded JPEG BLOB
    legacy_db = legacy_dir / "techpad.db"
    db = DatabaseManager(legacy_db)
    init_database(db)
    sp_repo = ScratchpadRepository(db)
    img_repo = ImageRepository(db)
    pad_id = sp_repo.create(
        ticket_number="INC-9001",
        client_name="Contoso",
        title="Legacy Migrated Note",
        content_html='<p>Migrated body <img src="image://local/abc.jpg"></p>',
    )
    img_repo.save_image(pad_id, "abc.jpg", b"\xff\xd8\xff\xe0FAKEJPEG")
    db.close()

    # Seed legacy backup snapshot
    legacy_backup = legacy_dir / "backups" / "techpad_2026-11-19.db.bak"
    legacy_backup.parent.mkdir(parents=True)
    legacy_backup.write_bytes(b"backup-data")

    assert migrate_legacy_user_data(target_dir=target_dir, legacy_dir=legacy_dir) is True

    migrated_db = target_dir / "techpad.db"
    assert migrated_db.is_file()
    assert legacy_db.is_file()  # non-destructive

    conn = sqlite3.connect(str(migrated_db))
    try:
        rows = conn.execute("SELECT ticket_number, title FROM scratchpads").fetchall()
        imgs = conn.execute("SELECT image_name, image_data FROM scratchpad_images").fetchall()
    finally:
        conn.close()

    assert rows == [("INC-9001", "Legacy Migrated Note")]
    assert imgs == [("abc.jpg", b"\xff\xd8\xff\xe0FAKEJPEG")]
    assert (target_dir / "backups" / "techpad_2026-11-19.db.bak").read_bytes() == b"backup-data"

    # Second run must be a no-op once target DB exists
    assert migrate_legacy_user_data(target_dir=target_dir, legacy_dir=legacy_dir) is False


def test_autostart_command_uses_frozen_executable(tmp_path, monkeypatch):
    """Frozen AutostartService registers the standalone T-Notes.exe path directly."""
    fake_exe = tmp_path / "T-Notes.exe"
    fake_exe.write_bytes(b"")
    monkeypatch.setattr(sys, "frozen", True, raising=False)
    monkeypatch.setattr(sys, "executable", str(fake_exe))

    cmd = AutostartService().get_launch_command()
    assert cmd == f'"{fake_exe.resolve()}" --tray'
    assert "main.py" not in cmd


def test_powershell_file_command_and_hidden_kwargs():
    """Bundled PowerShell invocations pass -NoProfile -ExecutionPolicy Bypass -File and hide console windows."""
    cmd = build_powershell_file_command("pwsh.exe", "C:/bundle/scripts/m365/_host/M365WorkerHost.ps1")
    assert cmd == [
        "pwsh.exe",
        "-NoLogo",
        "-NoProfile",
        "-NonInteractive",
        "-ExecutionPolicy",
        "Bypass",
        "-File",
        "C:/bundle/scripts/m365/_host/M365WorkerHost.ps1",
    ]
    kwargs = hidden_subprocess_kwargs()
    if sys.platform == "win32":
        assert kwargs["creationflags"] == getattr(subprocess, "CREATE_NO_WINDOW", 0)
        si = kwargs["startupinfo"]
        assert si.wShowWindow == getattr(subprocess, "SW_HIDE", 0)


def test_preflight_probe_script_executes_cleanly():
    """M365PreflightProbe.ps1 runs via -ExecutionPolicy Bypass -File when pwsh is available."""
    pwsh = discover_pwsh()
    if pwsh is None:
        return
    result = M365PreflightService._run_pwsh_probe(pwsh, ("Microsoft.Graph.Authentication",))
    assert result["pwsh_found"] is True
    assert isinstance(result["version"], str)
    assert result["edition"] == "Core"
    assert "Microsoft.Graph.Authentication" in result["modules"]


def test_qt_image_formats_include_jpeg_and_png(qapp, tmp_path):
    """PySide6 image plugins support JPEG and PNG so inline screenshots save and render cleanly."""
    readers = {bytes(fmt).decode("ascii").lower() for fmt in QImageReader.supportedImageFormats()}
    writers = {bytes(fmt).decode("ascii").lower() for fmt in QImageWriter.supportedImageFormats()}
    assert "jpeg" in readers and "png" in readers
    assert "jpeg" in writers and "png" in writers

    db = DatabaseManager(tmp_path / "img_test.db")
    init_database(db)
    svc = ImageService(ImageRepository(db))
    img = QImage(32, 24, QImage.Format_ARGB32)
    img.fill(0xFF11AAFF)
    name, url, jpeg_bytes, loaded = svc.create_embedded_image(img)
    assert name.endswith(".jpg")
    assert url.startswith("image://local/")
    assert len(jpeg_bytes) > 0
    assert not loaded.isNull()
    db.close()


def test_pyinstaller_spec_is_valid_ast_and_references_existing_inputs():
    """T-Notes.spec parses cleanly and points at valid entry script and asset folders."""
    spec_path = resource_path("T-Notes.spec")
    assert spec_path.is_file()
    ast.parse(spec_path.read_text(encoding="utf-8"))
    for rel in (
        "src/main.py",
        "src/database/schema.sql",
        "src/database/taxonomy_seed.json",
        "assets/styles/dark_theme.qss",
        "assets/icons/app_icon.png",
        "assets/m365",
        "docs/contracts/m365/schemas",
        "prototypes/m365_official_engine/protocol.ps1",
        "scripts/m365/_host/M365WorkerHost.ps1",
        "scripts/m365/_host/M365SyntheticRunner.ps1",
        "scripts/m365/_host/M365PreflightProbe.ps1",
    ):
        assert resource_path(rel).exists(), f"Missing spec input: {rel}"
