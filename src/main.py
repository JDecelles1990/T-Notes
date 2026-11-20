"""Main application entry point for TechPad."""

import os
from pathlib import Path
import sys

# When frozen via PyInstaller, stay beside the executable (never chdir into _MEIPASS).
# When running from source (including Windows Startup from System32), add repo root to sys.path.
if getattr(sys, "frozen", False):
    try:
        os.chdir(Path(sys.executable).resolve().parent)
    except OSError:
        pass
else:
    _PROJECT_ROOT = Path(__file__).resolve().parent.parent
    if str(_PROJECT_ROOT) not in sys.path:
        sys.path.insert(0, str(_PROJECT_ROOT))
    try:
        os.chdir(_PROJECT_ROOT)
    except OSError:
        pass

from PySide6.QtCore import QCoreApplication, Qt
from PySide6.QtGui import QFont, QIcon
from PySide6.QtWidgets import QApplication
from src.config import (
    DEFAULT_DB_PATH,
    DEFAULT_QSS_PATH,
    is_frozen,
    migrate_legacy_user_data,
    resource_path,
)
from src.core.constants import APP_NAME
from src.database.connection import DatabaseManager
from src.database.migrations import init_database
from src.repositories.image_repository import ImageRepository
from src.repositories.scratchpad_repository import ScratchpadRepository
from src.repositories.session_repository import SessionRepository
from src.repositories.template_repository import TemplateRepository
from src.services.autostart_service import AutostartService
from src.services.backup_service import BackupService
from src.services.image_service import ImageService
from src.services.scratchpad_service import ScratchpadService
from src.services.session_service import SessionService
from src.ui.components.aurora_tooltip import install_aurora_tooltips
from src.ui.components.system_tray import get_or_create_app_icon
from src.ui.main_window import TechPadMainWindow


def main() -> int:
    """Initializes services, loads stylesheet, and executes the PySide6 application."""
    # Enable High DPI scaling
    os.environ["QT_AUTO_SCREEN_SCALE_FACTOR"] = "1"

    # Ensure Qt discovers bundled imageformat plugins (qjpeg, qico, etc.) when frozen
    if is_frozen():
        qt_plugins = resource_path("PySide6", "plugins")
        if qt_plugins.is_dir():
            QCoreApplication.addLibraryPath(str(qt_plugins))

    app = QApplication(sys.argv)
    app.setQuitOnLastWindowClosed(False)
    app.setApplicationName(APP_NAME)
    app.setOrganizationName("MSP Tools")
    app.setWindowIcon(get_or_create_app_icon())

    # Set default clean system font
    font = QFont("Segoe UI", 10)
    app.setFont(font)

    # Apply Dark Theme QSS
    if DEFAULT_QSS_PATH.exists():
        with open(DEFAULT_QSS_PATH, "r", encoding="utf-8") as f:
            app.setStyleSheet(f.read())

    # Install global Neon Aurora hover tooltips (does not modify any buttons)
    install_aurora_tooltips(app)

    # Migrate legacy TechPad SQLite data & backups into %APPDATA%\T-Notes if needed
    try:
        migrate_legacy_user_data()
    except Exception as e:
        print(f"Warning: Legacy user data migration skipped: {e}", file=sys.stderr)

    # Initialize Database & Run Migrations
    db_manager = DatabaseManager(DEFAULT_DB_PATH)
    init_database(db_manager)

    # Initialize Repositories (Data Access Layer)
    scratchpad_repo = ScratchpadRepository(db_manager)
    image_repo = ImageRepository(db_manager)
    session_repo = SessionRepository(db_manager)
    template_repo = TemplateRepository(db_manager)

    # Initialize Services (Business Logic Layer)
    image_service = ImageService(image_repo)
    scratchpad_service = ScratchpadService(scratchpad_repo, image_service, template_repo)
    session_service = SessionService(session_repo, scratchpad_service)
    autostart_service = AutostartService()
    backup_service = BackupService(db_manager, scratchpad_repo, image_repo)

    # Ensure Windows Startup registry entry matches user preference (enabled by default)
    autostart_pref = session_service.get_setting("autostart_enabled", "true").lower() == "true"
    if autostart_pref:
        try:
            autostart_service.set_enabled(True)
        except Exception as e:
            print(f"Warning: Windows startup could not be registered: {e}", file=sys.stderr)

    # Automatic Daily Database Snapshot (rolling 7-day retention)
    try:
        backup_service.maybe_run_daily_backup(retention_days=7)
    except Exception as e:
        print(f"Warning: Daily backup could not be created: {e}", file=sys.stderr)

    # Launch Main Window (Presentation Layer)
    window = TechPadMainWindow(
        scratchpad_service=scratchpad_service,
        image_service=image_service,
        session_service=session_service,
        autostart_service=autostart_service,
        backup_service=backup_service,
    )

    # Evaluate Startup Mode (--tray flag and Smart Restore)
    is_tray_flag = "--tray" in sys.argv
    smart_restore = session_service.get_setting("smart_restore_enabled", "true").lower() == "true"
    last_state = session_service.get_setting("last_window_state", "visible")

    if is_tray_flag:
        if smart_restore and last_state == "visible":
            window.show()
        else:
            window.hide()
            if getattr(window, "tray_icon", None) and hasattr(window.tray_icon, "show_message"):
                window.tray_icon.show_message(
                    f"{APP_NAME} Active",
                    f"{APP_NAME} is running in the background. Press F8 to open.",
                    timeout=3500,
                )
    else:
        window.show()

    return app.exec()


if __name__ == "__main__":
    sys.exit(main())
