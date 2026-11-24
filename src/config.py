"""Application configuration and filesystem paths."""

import os
from pathlib import Path
import sys

from src.core.paths import (
    get_app_data_dir,
    get_bundle_root,
    get_legacy_app_data_dir,
    is_frozen,
    migrate_legacy_user_data,
    resource_path,
)

# Bundle / repository root (_MEIPASS when frozen, repository root in source mode)
BASE_DIR = get_bundle_root()

# Persistent writable user data directory (%APPDATA%\T-Notes on Windows)
APP_DATA_DIR = get_app_data_dir()
try:
    APP_DATA_DIR.mkdir(parents=True, exist_ok=True)
except OSError:
    pass

# Database path (always outside _MEIPASS so notes & tabs survive app updates;
# optional TNOTES_DB_PATH override enables launching an isolated visual sandbox).
_ENV_DB_PATH = os.environ.get("TNOTES_DB_PATH", "").strip()
DEFAULT_DB_PATH = (
    Path(_ENV_DB_PATH).expanduser().resolve()
    if _ENV_DB_PATH
    else (APP_DATA_DIR / "techpad.db")
)

# Read-only bundled UI asset paths
STYLES_DIR = resource_path("assets", "styles")
DEFAULT_QSS_PATH = resource_path("assets", "styles", "dark_theme.qss")
DEFAULT_ICON_PATH = resource_path("assets", "icons", "app_icon.png")

# Default ticket plain-text export directory (writable in both source and frozen modes)
DEFAULT_EXPORT_DIR = (APP_DATA_DIR / "exports") if is_frozen() else (BASE_DIR / "T-Notes")
try:
    DEFAULT_EXPORT_DIR.mkdir(parents=True, exist_ok=True)
except OSError:
    pass


