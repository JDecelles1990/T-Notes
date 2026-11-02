"""Custom QTabWidget with right-click context menu, double-click renaming, and slide-reordering."""

from typing import Optional
from PySide6.QtCore import QPoint, Qt, Signal
from PySide6.QtGui import QContextMenuEvent, QMouseEvent
from PySide6.QtWidgets import (
    QTabBar,
    QTabWidget,
    QToolButton,
    QWidget,
)
from src.ui.components.editor import TechPadEditor


class TechPadTabBar(QTabBar):
    """Custom tab bar supporting double clicks, right-click context menus, and slide reorganization."""

    tab_double_clicked = Signal(int)
    tab_context_menu_requested = Signal(int, QPoint)

    def mouseDoubleClickEvent(self, event: QMouseEvent) -> None:
        if event.button() == Qt.LeftButton:
            index = self.tabAt(event.pos())
            if index >= 0:
                self.tab_double_clicked.emit(index)
                event.accept()
                return
        super().mouseDoubleClickEvent(event)

    def contextMenuEvent(self, event: QContextMenuEvent) -> None:
        index = self.tabAt(event.pos())
        self.tab_context_menu_requested.emit(index, event.globalPos())
        event.accept()


class TechPadTabWidget(QTabWidget):
    """Movable, closable tab widget managing ticket scratchpads with context actions."""

    tab_edit_requested = Signal(int)                 # Emits tab_index
    tab_close_prompted = Signal(int)                 # Emits tab_index
    tab_reordered = Signal()                         # Emits when user drags/moves a tab
    new_tab_requested = Signal()                     # Emits when '+' button clicked
    tab_context_menu_requested = Signal(int, QPoint) # Emits (tab_index, global_position)

    def __init__(self, parent: Optional[QWidget] = None):
        super().__init__(parent)

        # 1. Install custom tab bar FIRST before setting movable/closable properties
        self._tab_bar = TechPadTabBar(self)
        self.setTabBar(self._tab_bar)

        # 2. Configure slide-reorganizing, scrollable tabs, and close buttons on both widget and bar
        self.setDocumentMode(True)
        self.setTabsClosable(True)
        self.setMovable(True)
        self.setUsesScrollButtons(True)
        self.setElideMode(Qt.ElideRight)

        self._tab_bar.setMovable(True)
        self._tab_bar.setTabsClosable(True)
        self._tab_bar.setUsesScrollButtons(True)
        self._tab_bar.setElideMode(Qt.ElideRight)
        self._tab_bar.setExpanding(False)

        # Connect signals
        self._tab_bar.tab_double_clicked.connect(self.tab_edit_requested.emit)
        self._tab_bar.tab_context_menu_requested.connect(self.tab_context_menu_requested.emit)
        self._tab_bar.tabMoved.connect(lambda from_idx, to_idx: self.tab_reordered.emit())
        self.tabCloseRequested.connect(self.tab_close_prompted.emit)

        # Persistent '+' corner button
        self.btn_add = QToolButton(self)
        self.btn_add.setText("+")
        self.btn_add.setToolTip("New Ticket Scratchpad (Ctrl+T)")
        self.btn_add.setStyleSheet("""
            QToolButton {
                font-size: 16px;
                font-weight: bold;
                padding: 2px 8px;
                margin-right: 4px;
                background-color: transparent;
                border: none;
                color: #007acc;
            }
            QToolButton:hover {
                background-color: #383838;
                border-radius: 3px;
                color: #ffffff;
            }
        """)
        self.btn_add.clicked.connect(self.new_tab_requested.emit)
        self.setCornerWidget(self.btn_add, Qt.TopRightCorner)

    @staticmethod
    def format_title(ticket_number: str, client_name: str = "", title: str = "") -> str:
        """Formats the title displayed on the tab header."""
        t_num = ticket_number.strip() if ticket_number else "New"
        if not t_num.startswith("#") and not t_num.upper().startswith("INC") and not t_num.upper().startswith("REQ") and not t_num.upper().startswith("T-"):
            t_num = f"#{t_num}"

        secondary = client_name.strip() or title.strip()
        if secondary:
            if len(secondary) > 24:
                secondary = secondary[:21] + "..."
            return f"{t_num} — {secondary}"
        return t_num

    def add_ticket_tab(self, ticket: dict, editor: TechPadEditor) -> int:
        """Adds a new tab and binds ticket metadata."""
        title = self.format_title(
            ticket.get("ticket_number", ""),
            ticket.get("client_name", ""),
            ticket.get("title", ""),
        )
        index = self.addTab(editor, title)
        editor.setProperty("scratchpad_id", ticket.get("id"))
        self.setTabToolTip(index, f"Ticket: {ticket.get('ticket_number')}\nClient: {ticket.get('client_name')}\nTitle: {ticket.get('title')}")
        return index

    def get_editor_at(self, index: int) -> Optional[TechPadEditor]:
        widget = self.widget(index)
        if isinstance(widget, TechPadEditor):
            return widget
        return None

    def get_current_editor(self) -> Optional[TechPadEditor]:
        return self.get_editor_at(self.currentIndex())

    def get_scratchpad_id_at(self, index: int) -> Optional[int]:
        editor = self.get_editor_at(index)
        if editor:
            return editor.scratchpad_id
        return None
