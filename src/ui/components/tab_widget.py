"""Custom QTabWidget with right-click context menu, double-click renaming, and slide-reordering."""

from typing import Optional
from PySide6.QtCore import QPoint, QRect, Qt, Signal
from PySide6.QtGui import QColor, QContextMenuEvent, QMouseEvent, QPainter
from PySide6.QtWidgets import (
    QTabBar,
    QTabWidget,
    QToolButton,
    QWidget,
)
from src.ui.components.editor import TechPadEditor

TAB_COLOR_PALETTE = [
    "#38bdf8",  # Sky Blue
    "#34d399",  # Emerald Green
    "#a855f7",  # Purple
    "#fbbf24",  # Amber / Gold
    "#f43f5e",  # Rose / Coral
    "#06b6d4",  # Cyan
    "#fb923c",  # Orange
    "#818cf8",  # Indigo
    "#a3e635",  # Lime
    "#ec4899",  # Pink
    "#2dd4bf",  # Teal
    "#c084fc",  # Lavender
]


class TechPadTabBar(QTabBar):
    """Custom tab bar supporting double clicks, right-click context menus, and slide reorganization."""

    tab_double_clicked = Signal(int)
    tab_context_menu_requested = Signal(int, QPoint)

    def paintEvent(self, event) -> None:
        """Paints standard tab layout, then overlays each tab's distinctive owned color."""
        super().paintEvent(event)
        parent_widget = self.parent()
        if not isinstance(parent_widget, TechPadTabWidget):
            return

        painter = QPainter(self)
        painter.setRenderHint(QPainter.Antialiasing, True)

        for i in range(self.count()):
            rect = self.tabRect(i)
            color = parent_widget.get_tab_color(i)
            is_selected = (i == self.currentIndex())

            # 1. Subtle background ambient tint with tab's own color
            tint_alpha = 32 if is_selected else 14
            tint = QColor(color.red(), color.green(), color.blue(), tint_alpha)
            painter.fillRect(rect.adjusted(1, 2, -1, 0), tint)

            # 2. Distinct top accent stripe (3px if selected, 2px if unselected)
            stripe_height = 3 if is_selected else 2
            stripe_rect = QRect(rect.x() + 1, rect.y(), rect.width() - 2, stripe_height)
            painter.fillRect(stripe_rect, color)

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
        self._tab_checklist_progress: dict[int, tuple[int, int]] = {}
        self._tab_colors: dict[int, str] = {}

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
    def format_title(
        ticket_number: str,
        client_name: str = "",
        title: str = "",
        elapsed_seconds: int = 0,
        checklist_progress: Optional[tuple[int, int]] = None,
    ) -> str:
        """Formats the title displayed on the tab header (e.g. '#4092 (14m) ☑️2/5 — ACME')."""
        t_num = ticket_number.strip() if ticket_number else "New"
        if not t_num.startswith("#") and not t_num.upper().startswith("INC") and not t_num.upper().startswith("REQ") and not t_num.upper().startswith("T-"):
            t_num = f"#{t_num}"

        time_tag = f" ({elapsed_seconds // 60}m)" if elapsed_seconds > 0 else ""

        progress_tag = ""
        if checklist_progress and checklist_progress[1] > 0:
            completed, total = checklist_progress
            if completed == total:
                progress_tag = f" ✅{completed}/{total}"
            else:
                progress_tag = f" ☑️{completed}/{total}"

        t_display = f"{t_num}{time_tag}{progress_tag}"

        secondary = client_name.strip() or title.strip()
        if secondary:
            if len(secondary) > 24:
                secondary = secondary[:21] + "..."
            return f"{t_display} — {secondary}"
        return t_display

    def add_ticket_tab(self, ticket: dict, editor: TechPadEditor) -> int:
        """Adds a new tab and binds ticket metadata."""
        elapsed = ticket.get("elapsed_seconds", 0) or 0
        sp_id = ticket.get("id")
        if sp_id is not None and sp_id not in self._tab_colors:
            self._tab_colors[sp_id] = TAB_COLOR_PALETTE[(sp_id - 1) % len(TAB_COLOR_PALETTE)]

        checklist_progress = None
        if editor:
            c, tot = editor.get_checklist_stats()
            if tot > 0:
                checklist_progress = (c, tot)
                if sp_id is not None:
                    self._tab_checklist_progress[sp_id] = checklist_progress

        title = self.format_title(
            ticket.get("ticket_number", ""),
            ticket.get("client_name", ""),
            ticket.get("title", ""),
            elapsed_seconds=elapsed,
            checklist_progress=checklist_progress,
        )
        index = self.addTab(editor, title)
        editor.setProperty("scratchpad_id", sp_id)

        # Rich tooltip
        tooltip = f"Ticket: {ticket.get('ticket_number')}\nClient: {ticket.get('client_name') or 'N/A'}\nTitle: {ticket.get('title') or 'N/A'}"
        if checklist_progress and checklist_progress[1] > 0:
            pct = int(round((checklist_progress[0] / checklist_progress[1]) * 100))
            tooltip += f"\nTasks: {checklist_progress[0]}/{checklist_progress[1]} completed ({pct}%)"
        if elapsed > 0:
            tooltip += f"\nTroubleshooting Time: {elapsed // 60}m"
        self.setTabToolTip(index, tooltip)
        return index

    def update_tab_title(
        self,
        index: int,
        ticket_number: str,
        client_name: str = "",
        title: str = "",
        elapsed_seconds: int = 0,
        checklist_progress: Optional[tuple[int, int]] = None,
    ) -> None:
        """Updates tab header title with ticket metadata, elapsed minutes, and task progress."""
        if 0 <= index < self.count():
            sp_id = self.get_scratchpad_id_at(index)
            if checklist_progress is not None and sp_id is not None:
                self._tab_checklist_progress[sp_id] = checklist_progress
            elif sp_id is not None and checklist_progress is None:
                checklist_progress = self._tab_checklist_progress.get(sp_id)

            new_title = self.format_title(
                ticket_number,
                client_name,
                title,
                elapsed_seconds=elapsed_seconds,
                checklist_progress=checklist_progress,
            )
            if self.tabText(index) != new_title:
                self.setTabText(index, new_title)

            # Update rich tooltip
            tooltip = f"Ticket: {ticket_number}\nClient: {client_name or 'N/A'}\nTitle: {title or 'N/A'}"
            if checklist_progress and checklist_progress[1] > 0:
                pct = int(round((checklist_progress[0] / checklist_progress[1]) * 100))
                tooltip += f"\nTasks: {checklist_progress[0]}/{checklist_progress[1]} completed ({pct}%)"
            if elapsed_seconds > 0:
                tooltip += f"\nTroubleshooting Time: {elapsed_seconds // 60}m"
            self.setTabToolTip(index, tooltip)

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

    def get_tab_color(self, index: int) -> QColor:
        """Returns the distinctive owned color for the tab at the given index."""
        sp_id = self.get_scratchpad_id_at(index)
        if sp_id is not None and sp_id in self._tab_colors:
            return QColor(self._tab_colors[sp_id])
        if sp_id is not None:
            c = TAB_COLOR_PALETTE[(sp_id - 1) % len(TAB_COLOR_PALETTE)]
            self._tab_colors[sp_id] = c
            return QColor(c)
        return QColor(TAB_COLOR_PALETTE[index % len(TAB_COLOR_PALETTE)])

    def set_tab_color(self, scratchpad_id: int, hex_color: str) -> None:
        """Explicitly sets or overrides the owned color for a scratchpad."""
        self._tab_colors[scratchpad_id] = hex_color
        self._tab_bar.update()
