"""Main application entry point for TechPad."""

import os
import sys
from PySide6.QtCore import Qt
from PySide6.QtGui import QFont, QIcon
from PySide6.QtWidgets import QApplication
from src.config import DEFAULT_DB_PATH, DEFAULT_QSS_PATH
from src.database.connection import DatabaseManager
from src.database.migrations import init_database
from src.repositories.image_repository import ImageRepository
from src.repositories.scratchpad_repository import ScratchpadRepository
from src.repositories.session_repository import SessionRepository
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
    app.setApplicationName("TechPad")
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

    # Initialize Services (Business Logic Layer)
    image_service = ImageService(image_repo)
    scratchpad_service = ScratchpadService(scratchpad_repo, image_service)
    session_service = SessionService(session_repo, scratchpad_service)

    # Launch Main Window (Presentation Layer)
    window = TechPadMainWindow(
        scratchpad_service=scratchpad_service,
        image_service=image_service,
        session_service=session_service,
    )
    window.show()

    return app.exec()


if __name__ == "__main__":
    sys.exit(main())

