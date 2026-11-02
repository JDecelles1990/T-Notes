"""System tray integration for TechPad background execution and quick launching."""

from pathlib import Path
from typing import Optional
from PySide6.QtCore import Qt, Signal
from PySide6.QtGui import QAction, QColor, QFont, QIcon, QPainter, QPixmap
from PySide6.QtWidgets import QMenu, QSystemTrayIcon, QWidget
from src.core.constants import APP_NAME, APP_VERSION


def get_or_create_app_icon() -> QIcon:
    """Returns the application icon, creating assets/icons/app_icon.png if missing."""
    icon_path = Path(__file__).resolve().parent.parent.parent.parent / "assets" / "icons" / "app_icon.png"
    if icon_path.exists():
        return QIcon(str(icon_path))

    # Generate fallback crisp high-DPI icon in memory
    pm = QPixmap(64, 64)
    pm.fill(Qt.transparent)
    p = QPainter(pm)
    p.setRenderHint(QPainter.Antialiasing)
    p.setBrush(QColor("#007acc"))
    p.setPen(Qt.NoPen)
    p.drawRoundedRect(4, 4, 56, 56, 12, 12)
    p.setPen(QColor("#ffffff"))
    font = QFont("Segoe UI", 28, QFont.Bold)
    p.setFont(font)
    p.drawText(pm.rect(), Qt.AlignCenter, "T")
    p.end()

    try:
        icon_path.parent.mkdir(parents=True, exist_ok=True)
        pm.save(str(icon_path))
    except Exception:
        pass

    return QIcon(pm)


class TechPadSystemTray(QSystemTrayIcon):
    """System tray icon with context menu for background execution and quick actions."""

    show_requested = Signal()
    toggle_requested = Signal()
    new_tab_requested = Signal()
    quit_requested = Signal()

    def __init__(self, parent: Optional[QWidget] = None):
        super().__init__(get_or_create_app_icon(), parent)
        self.setToolTip(f"{APP_NAME} v{APP_VERSION} (Press F8 to toggle)")
        self._build_menu()
        self.activated.connect(self._on_activated)

    def _build_menu(self) -> None:
        menu = QMenu()

        self.act_toggle = menu.addAction(f"Show / Hide {APP_NAME} (F8)")
        self.act_toggle.triggered.connect(self.toggle_requested.emit)

        self.act_new = menu.addAction("➕ New Ticket Tab (Ctrl+T)")
        self.act_new.triggered.connect(self.new_tab_requested.emit)

        menu.addSeparator()

        self.act_quit = menu.addAction(f"✕ Quit {APP_NAME}")
        self.act_quit.triggered.connect(self.quit_requested.emit)

        self.setContextMenu(menu)

    def _on_activated(self, reason: QSystemTrayIcon.ActivationReason) -> None:
        """Toggles window visibility upon left-click or double-click."""
        if reason in (QSystemTrayIcon.Trigger, QSystemTrayIcon.DoubleClick):
            self.toggle_requested.emit()

