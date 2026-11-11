"""Main application entry point for TechPad."""

import os
import sys
from PySide6.QtCore import Qt
from PySide6.QtGui import QFont, QIcon
from PySide6.QtWidgets import QApplication
from src.config import DEFAULT_DB_PATH, DEFAULT_QSS_PATH
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
from src.ui.components.system_tray import get_or_create_app_icon
from src.ui.main_window import TechPadMainWindow


def main() -> int:
    """Initializes services, loads stylesheet, and executes the PySide6 application."""
    # Enable High DPI scaling
    os.environ["QT_AUTO_SCREEN_SCALE_FACTOR"] = "1"

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
