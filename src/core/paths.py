"""Frozen-safe resource resolution and persistent writable user-data directories."""

from __future__ import annotations

import os
from pathlib import Path
import shutil
import sqlite3
import sys


def is_frozen() -> bool:
    """Returns True when running inside a PyInstaller bundle."""
    return bool(getattr(sys, "frozen", False) and hasattr(sys, "_MEIPASS"))


def get_bundle_root() -> Path:
    """Returns the read-only bundle directory (_MEIPASS when frozen, repo root in source mode)."""
    if is_frozen():
        return Path(sys._MEIPASS).resolve()
    return Path(__file__).resolve().parents[2]


def resource_path(*parts: str | os.PathLike[str]) -> Path:
    """Resolves an application resource path inside the active bundle or source root."""
    root = get_bundle_root()
    return root.joinpath(*parts) if parts else root


def get_app_data_dir() -> Path:
    """Returns the writable persistent user data directory (%APPDATA%\\T-Notes on Windows)."""
    if sys.platform == "win32":
        base = os.environ.get("APPDATA") or str(Path.home() / "AppData" / "Roaming")
        return Path(base) / "T-Notes"
    return Path.home() / ".t-notes"


def get_legacy_app_data_dir() -> Path:
    """Returns the pre-packaging user data directory (%LOCALAPPDATA%\\TechPad on Windows)."""
    if sys.platform == "win32":
        base = os.environ.get("LOCALAPPDATA") or str(Path.home() / "AppData" / "Local")
        return Path(base) / "TechPad"
    return Path.home() / ".techpad"


def migrate_legacy_user_data(
    target_dir: Path | None = None,
    legacy_dir: Path | None = None,
) -> bool:
    """Non-destructively migrates legacy TechPad SQLite data and backups into T-Notes AppData.

    Uses SQLite's online backup API so WAL journals are cleanly checkpointed into
    ``target_dir / "techpad.db"`` without modifying or removing the legacy files.
    Returns ``True`` if a migration was performed, or ``False`` otherwise.
    """
    dst_dir = Path(target_dir) if target_dir is not None else get_app_data_dir()
    src_dir = Path(legacy_dir) if legacy_dir is not None else get_legacy_app_data_dir()
    dst_dir.mkdir(parents=True, exist_ok=True)

    target_db = dst_dir / "techpad.db"
    legacy_db = src_dir / "techpad.db"

    try:
        same_dir = dst_dir.resolve() == src_dir.resolve()
    except OSError:
        same_dir = dst_dir == src_dir

    if same_dir or target_db.exists() or not legacy_db.is_file():
        return False

    tmp_target_db = dst_dir / "techpad.db.migrating"
    src_conn: sqlite3.Connection | None = None
    dst_conn: sqlite3.Connection | None = None
    try:
        src_conn = sqlite3.connect(str(legacy_db), timeout=5.0)
        dst_conn = sqlite3.connect(str(tmp_target_db))
        src_conn.backup(dst_conn)
    finally:
        if dst_conn is not None:
            dst_conn.close()
        if src_conn is not None:
            src_conn.close()

    tmp_target_db.replace(target_db)

    legacy_backups = src_dir / "backups"
    target_backups = dst_dir / "backups"
    if legacy_backups.is_dir():
        for src_item in legacy_backups.rglob("*"):
            if not src_item.is_file():
                continue
            rel = src_item.relative_to(legacy_backups)
            dst_item = target_backups / rel
            if dst_item.exists():
                continue
            try:
                dst_item.parent.mkdir(parents=True, exist_ok=True)
                shutil.copy2(src_item, dst_item)
            except OSError:
                pass

    return True
