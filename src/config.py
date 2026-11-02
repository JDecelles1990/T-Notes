"""Application configuration and filesystem paths."""

from pathlib import Path
import os
import sys

# Base directories
BASE_DIR = Path(__file__).resolve().parent.parent

# User data directory (AppData on Windows or ~/.techpad on Unix)
if sys.platform == "win32":
    APP_DATA_DIR = Path(os.environ.get("LOCALAPPDATA", Path.home() / "AppData" / "Local")) / "TechPad"
else:
    APP_DATA_DIR = Path.home() / ".techpad"

APP_DATA_DIR.mkdir(parents=True, exist_ok=True)

# Database path
DEFAULT_DB_PATH = APP_DATA_DIR / "techpad.db"

# Stylesheet path
STYLES_DIR = BASE_DIR / "assets" / "styles"
DEFAULT_QSS_PATH = STYLES_DIR / "dark_theme.qss"
