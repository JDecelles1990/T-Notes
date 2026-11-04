"""Custom QTabWidget with right-click context menu, double-click renaming, and slide-reordering."""

from typing import Optional
from PySide6.QtCore import QPoint, QRect, Qt, Signal, QTimer
from PySide6.QtGui import QColor, QContextMenuEvent, QMouseEvent, QPainter, QPixmap
from PySide6.QtWidgets import (
    QApplication,
    QHBoxLayout,
    QLabel,
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


class TabDragPreview(QLabel):
    """Floating semi-transparent ghost preview of the dragged tab providing visual drag animation."""

    def __init__(self, tab_bar: "TechPadTabBar", tab_idx: int):
        super().__init__(None)
        self.setWindowFlags(
            Qt.ToolTip | Qt.FramelessWindowHint | Qt.WindowTransparentForInput | Qt.NoDropShadowWindowHint
        )
        self.setAttribute(Qt.WA_ShowWithoutActivating)
        self.setAttribute(Qt.WA_TranslucentBackground)
        self.setWindowOpacity(0.85)

        rect = tab_bar.tabRect(tab_idx)
        raw_pix = tab_bar.grab(rect)
        if raw_pix.isNull() or raw_pix.width() <= 0:
            raw_pix = QPixmap(max(rect.width(), 80), max(rect.height(), 24))
            raw_pix.fill(QColor(40, 40, 40))

        styled_pix = QPixmap(raw_pix.size())
        styled_pix.fill(Qt.transparent)
        p = QPainter(styled_pix)
        p.setRenderHint(QPainter.Antialiasing, True)
        p.drawPixmap(0, 0, raw_pix)
        p.setPen(QColor("#007acc"))
        p.setBrush(Qt.NoBrush)
        p.drawRect(0, 0, raw_pix.width() - 1, raw_pix.height() - 1)
        p.end()

        self.setPixmap(styled_pix)
        self.resize(styled_pix.size())


class TechPadTabBar(QTabBar):
    """Custom tab bar supporting double clicks, right-click context menus, auto-scrolling, and slide reorganization."""

    tab_double_clicked = Signal(int)
    tab_context_menu_requested = Signal(int, QPoint)
    tab_cross_drop_requested = Signal(int, QPoint)  # Emits (source_tab_index, global_position)
    tab_cross_drag_moved = Signal(int, QPoint)      # Emits (source_tab_index, global_position) during cross-pane drag

    def __init__(self, parent: Optional[QWidget] = None):
        super().__init__(parent)
        self._drag_tab_idx: Optional[int] = None
        self._drag_start_pos: Optional[QPoint] = None
        self._is_dragging: bool = False
        self._is_dragging_out: bool = False
        self._had_drag: bool = False
        self._last_mouse_pos: Optional[QPoint] = None
        self._drag_preview: Optional[TabDragPreview] = None

        # Auto-scrolling timer when dragging tabs near left/right edges (smooth, human-controllable speed)
        self._auto_scroll_timer = QTimer(self)
        self._auto_scroll_timer.setInterval(220)
        self._auto_scroll_timer.timeout.connect(self._on_auto_scroll)
        self._scroll_direction: int = 0

    def _scroll_left_btn(self) -> Optional[QToolButton]:
        return self.findChild(QToolButton, "ScrollLeftButton")

    def _scroll_right_btn(self) -> Optional[QToolButton]:
        return self.findChild(QToolButton, "ScrollRightButton")

    def _start_auto_scroll(self, direction: int) -> None:
        self._scroll_direction = direction
        if not self._auto_scroll_timer.isActive():
            self._auto_scroll_timer.start()

    def _stop_auto_scroll(self) -> None:
        self._scroll_direction = 0
        if self._auto_scroll_timer.isActive():
            self._auto_scroll_timer.stop()

    def _on_auto_scroll(self) -> None:
        if not self._is_dragging or self._drag_tab_idx is None:
            self._stop_auto_scroll()
            return

        if self._scroll_direction < 0:
            btn = self._scroll_left_btn()
            if btn and btn.isEnabled():
                btn.click()
                self._check_reorder_at(self._last_mouse_pos)
            else:
                self._stop_auto_scroll()
        elif self._scroll_direction > 0:
            btn = self._scroll_right_btn()
            if btn and btn.isEnabled():
                btn.click()
                self._check_reorder_at(self._last_mouse_pos)
            else:
                self._stop_auto_scroll()

    def _check_reorder_at(self, pos: Optional[QPoint]) -> None:
        """Dynamically reorders the dragged tab to the left or right of the hovered tab or edge."""
        if pos is None or self._drag_tab_idx is None or self.count() <= 1:
            return

        cur_idx = self._drag_tab_idx

        # If hovering at or past the left edge of visible tabs
        if pos.x() <= 15:
            for i in range(cur_idx):
                rect = self.tabRect(i)
                if rect.right() > 0:
                    self.moveTab(cur_idx, i)
                    self._drag_tab_idx = i
                    self.setCurrentIndex(i)
                    break
            return

        # If hovering at or past the right edge of visible tabs
        if pos.x() >= self.width() - 15:
            for i in range(self.count() - 1, cur_idx, -1):
                rect = self.tabRect(i)
                if rect.left() < self.width():
                    self.moveTab(cur_idx, i)
                    self._drag_tab_idx = i
                    self.setCurrentIndex(i)
                    break
            return

        target_idx = self.tabAt(pos)
        if target_idx < 0:
            for i in range(self.count()):
                r = self.tabRect(i)
                if r.left() <= pos.x() <= r.right():
                    target_idx = i
                    break

        if target_idx >= 0 and target_idx != cur_idx:
            rect = self.tabRect(target_idx)
            dest_idx = cur_idx
            if target_idx > cur_idx:
                # Dragging right: past midpoint places tab to right (target_idx), before midpoint places to left (target_idx - 1)
                dest_idx = target_idx if pos.x() >= rect.center().x() else target_idx - 1
            elif target_idx < cur_idx:
                # Dragging left: before midpoint places tab to left (target_idx), past midpoint places to right (target_idx + 1)
                dest_idx = target_idx if pos.x() <= rect.center().x() else target_idx + 1

            if dest_idx != cur_idx and 0 <= dest_idx < self.count():
                self.moveTab(cur_idx, dest_idx)
                self._drag_tab_idx = dest_idx
                self.setCurrentIndex(dest_idx)

    def _destroy_drag_preview(self) -> None:
        """Hides and safely destroys the floating drag preview widget."""
        if self._drag_preview is not None:
            self._drag_preview.hide()
            self._drag_preview.deleteLater()
            self._drag_preview = None

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

            # 3. Active drag placeholder animation when tab is picked up and moving
            if self._is_dragging and i == self._drag_tab_idx:
                painter.fillRect(rect.adjusted(1, 2, -1, 0), QColor(10, 10, 10, 160))
                painter.setPen(QColor("#007acc"))
                painter.drawRect(rect.adjusted(1, 2, -2, -1))

    def mousePressEvent(self, event: QMouseEvent) -> None:
        if event.button() == Qt.LeftButton:
            idx = self.tabAt(event.position().toPoint())
            self._drag_tab_idx = idx if idx >= 0 else None
            self._drag_start_pos = event.position().toPoint()
            self._is_dragging = False
            self._is_dragging_out = False
            self._had_drag = False
            self._last_mouse_pos = event.position().toPoint()
            self._destroy_drag_preview()
        super().mousePressEvent(event)

    def mouseMoveEvent(self, event: QMouseEvent) -> None:
        if self._drag_tab_idx is not None and (event.buttons() & Qt.LeftButton) and self._drag_start_pos:
            pos = event.position().toPoint()
            self._last_mouse_pos = pos
            dist = (pos - self._drag_start_pos).manhattanLength()
            if dist >= QApplication.startDragDistance():
                self._had_drag = True
                self._is_dragging = True
                if self._drag_preview is None and 0 <= self._drag_tab_idx < self.count():
                    self._drag_preview = TabDragPreview(self, self._drag_tab_idx)
                    self._drag_preview.show()
                self.update()

            if self._is_dragging:
                gpos = event.globalPosition().toPoint()
                if self._drag_preview:
                    self._drag_preview.move(
                        gpos.x() - self._drag_preview.width() // 2,
                        gpos.y() - self._drag_preview.height() // 2,
                    )

                # Vertical drag-out condition: pulling tab down into editor (or above bar) detaches for cross-pane transfer
                is_vertical_drag_out = pos.y() < -20 or pos.y() > self.height() + 25

                if self._is_dragging_out:
                    # Once detached, stay in cross-pane drag-out mode unless dragged back into source tab bar bounds
                    if not is_vertical_drag_out and self.rect().contains(pos):
                        self._is_dragging_out = False
                        QApplication.restoreOverrideCursor()
                    else:
                        self.tab_cross_drag_moved.emit(self._drag_tab_idx, gpos)
                        return
                elif is_vertical_drag_out:
                    # Detach for cross-pane tab exchange
                    self._stop_auto_scroll()
                    self._is_dragging_out = True
                    QApplication.setOverrideCursor(Qt.DragMoveCursor)
                    self.tab_cross_drag_moved.emit(self._drag_tab_idx, gpos)
                    return

                # Intra-bar reordering and scrolling: horizontal dragging along the tab bar scrolls and reorders tabs
                scroll_margin = 35
                if pos.x() <= scroll_margin:
                    self._start_auto_scroll(-1)
                elif pos.x() >= self.width() - scroll_margin:
                    self._start_auto_scroll(1)
                else:
                    self._stop_auto_scroll()

                self._check_reorder_at(pos)
                return

        super().mouseMoveEvent(event)

    def mouseReleaseEvent(self, event: QMouseEvent) -> None:
        self._stop_auto_scroll()
        self._destroy_drag_preview()
        win = self.window()
        if win and hasattr(win, "secondary_tab_widget") and hasattr(win, "tab_widget"):
            win.secondary_tab_widget.tabBar()._stop_auto_scroll()
            win.tab_widget.tabBar()._stop_auto_scroll()
        if self._is_dragging_out:
            self._is_dragging_out = False
            QApplication.restoreOverrideCursor()
            source_idx = self._drag_tab_idx
            self._drag_tab_idx = None
            self._is_dragging = False
            self._had_drag = False
            self.update()
            gpos = event.globalPosition().toPoint()
            super().mouseReleaseEvent(event)
            if source_idx is not None:
                self.tab_cross_drop_requested.emit(source_idx, gpos)
            return

        had_drag = getattr(self, "_had_drag", False)
        if self._is_dragging:
            pos = event.position().toPoint()
            self._check_reorder_at(pos)
            if self._drag_tab_idx is not None:
                self.setCurrentIndex(self._drag_tab_idx)

        self._drag_tab_idx = None
        self._is_dragging = False
        self._had_drag = False
        self.update()
        super().mouseReleaseEvent(event)
        if had_drag and self.parent():
            if hasattr(self.parent(), "tab_reordered"):
                self.parent().tab_reordered.emit()

    def keyPressEvent(self, event) -> None:
        if event.key() == Qt.Key_Escape:
            self._stop_auto_scroll()
            self._destroy_drag_preview()
            win = self.window()
            if win and hasattr(win, "secondary_tab_widget") and hasattr(win, "tab_widget"):
                win.secondary_tab_widget.tabBar()._stop_auto_scroll()
                win.tab_widget.tabBar()._stop_auto_scroll()
            if self._is_dragging_out:
                self._is_dragging_out = False
                QApplication.restoreOverrideCursor()
            self._drag_tab_idx = None
            self._is_dragging = False
            self._had_drag = False
            self.update()
            event.accept()
            return
        super().keyPressEvent(event)

    def mouseDoubleClickEvent(self, event: QMouseEvent) -> None:
        if event.button() == Qt.LeftButton:
            index = self.tabAt(event.position().toPoint())
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
    tab_cross_drop_requested = Signal(int, QPoint)   # Emits (source_tab_index, global_position)
    tab_cross_drag_moved = Signal(int, QPoint)       # Emits (source_tab_index, global_position) during cross drag

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
        self._tab_bar.tab_cross_drop_requested.connect(self.tab_cross_drop_requested.emit)
        self._tab_bar.tab_cross_drag_moved.connect(self.tab_cross_drag_moved.emit)
        self._tab_bar.tabMoved.connect(lambda from_idx, to_idx: self.tab_reordered.emit())
        self.tabCloseRequested.connect(self.tab_close_prompted.emit)

        # Left corner: Previous tab navigation button (for HUD mode)
        self.btn_prev = QToolButton(self)
        self.btn_prev.setText("◀")
        self.btn_prev.setToolTip("Previous Ticket Tab (Ctrl+PgUp)")
        self.btn_prev.setObjectName("btnTabPrev")
        self.btn_prev.setStyleSheet("""
            QToolButton {
                font-size: 11px;
                font-weight: bold;
                padding: 2px 6px;
                background-color: transparent;
                border: none;
                color: #9cdcfe;
            }
            QToolButton:hover {
                background-color: #383838;
                border-radius: 3px;
                color: #ffffff;
            }
            QToolButton:disabled {
                color: #555555;
                background-color: transparent;
            }
        """)
        self.btn_prev.clicked.connect(self._navigate_previous_tab)
        self.btn_prev.setVisible(False)
        self.setCornerWidget(self.btn_prev, Qt.TopLeftCorner)

        # Right corner container: Next tab navigation button (for HUD mode) + '+' button
        self.right_corner_widget = QWidget(self)
        right_layout = QHBoxLayout(self.right_corner_widget)
        right_layout.setContentsMargins(0, 0, 0, 0)
        right_layout.setSpacing(2)

        self.btn_next = QToolButton(self.right_corner_widget)
        self.btn_next.setText("▶")
        self.btn_next.setToolTip("Next Ticket Tab (Ctrl+PgDown)")
        self.btn_next.setObjectName("btnTabNext")
        self.btn_next.setStyleSheet("""
            QToolButton {
                font-size: 11px;
                font-weight: bold;
                padding: 2px 6px;
                background-color: transparent;
                border: none;
                color: #9cdcfe;
            }
            QToolButton:hover {
                background-color: #383838;
                border-radius: 3px;
                color: #ffffff;
            }
            QToolButton:disabled {
                color: #555555;
                background-color: transparent;
            }
        """)
        self.btn_next.clicked.connect(self._navigate_next_tab)
        self.btn_next.setVisible(False)
        right_layout.addWidget(self.btn_next)

        # Persistent '+' corner button
        self.btn_add = QToolButton(self.right_corner_widget)
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
        right_layout.addWidget(self.btn_add)

        self.setCornerWidget(self.right_corner_widget, Qt.TopRightCorner)

        self.currentChanged.connect(lambda _: self._update_nav_arrows_state())

    def tabInserted(self, index: int) -> None:
        super().tabInserted(index)
        self._update_nav_arrows_state()

    def tabRemoved(self, index: int) -> None:
        super().tabRemoved(index)
        self._update_nav_arrows_state()

    def set_hud_nav_arrows_visible(self, visible: bool) -> None:
        """Shows or hides the left and right tab navigation arrows for HUD mode."""
        self.btn_prev.setVisible(visible)
        self.btn_next.setVisible(visible)
        self._update_nav_arrows_state()

    def _update_nav_arrows_state(self) -> None:
        """Updates enabled status of the navigation arrows based on tab count."""
        can_navigate = self.count() > 1
        if hasattr(self, "btn_prev"):
            self.btn_prev.setEnabled(can_navigate)
        if hasattr(self, "btn_next"):
            self.btn_next.setEnabled(can_navigate)

    def _navigate_previous_tab(self) -> None:
        """Navigates to the previous ticket tab."""
        count = self.count()
        if count > 1:
            idx = (self.currentIndex() - 1) % count
            self.setCurrentIndex(idx)
            editor = self.get_current_editor()
            if editor:
                editor.setFocus()

    def _navigate_next_tab(self) -> None:
        """Navigates to the next ticket tab."""
        count = self.count()
        if count > 1:
            idx = (self.currentIndex() + 1) % count
            self.setCurrentIndex(idx)
            editor = self.get_current_editor()
            if editor:
                editor.setFocus()

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

    def insert_ticket_tab(self, index: int, ticket: dict, editor: TechPadEditor) -> int:
        """Inserts a tab at a specific index and binds ticket metadata."""
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
        idx = self.insertTab(index, editor, title)
        editor.setProperty("scratchpad_id", sp_id)

        # Rich tooltip
        tooltip = f"Ticket: {ticket.get('ticket_number')}\nClient: {ticket.get('client_name') or 'N/A'}\nTitle: {ticket.get('title') or 'N/A'}"
        if checklist_progress and checklist_progress[1] > 0:
            pct = int(round((checklist_progress[0] / checklist_progress[1]) * 100))
            tooltip += f"\nTasks: {checklist_progress[0]}/{checklist_progress[1]} completed ({pct}%)"
        if elapsed > 0:
            tooltip += f"\nTroubleshooting Time: {elapsed // 60}m"
        self.setTabToolTip(idx, tooltip)
        return idx

    def add_ticket_tab(self, ticket: dict, editor: TechPadEditor) -> int:
        """Adds a new tab at the end and binds ticket metadata."""
        return self.insert_ticket_tab(self.count(), ticket, editor)

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
