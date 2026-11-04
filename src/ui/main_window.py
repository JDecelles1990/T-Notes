"""Main application window for TechPad."""

import ctypes
import json
from pathlib import Path
import sys
from typing import Optional
from PySide6.QtCore import QEvent, QPoint, QSize, Qt, QTimer
from PySide6.QtGui import QAction, QCloseEvent, QFont, QGuiApplication, QKeySequence, QMoveEvent, QResizeEvent, QShortcut, QShowEvent
from PySide6.QtWidgets import (
    QApplication,
    QFileDialog,
    QLabel,
    QMainWindow,
    QMenu,
    QMessageBox,
    QPushButton,
    QSplitter,
    QStackedWidget,
    QStatusBar,
    QSystemTrayIcon,
    QVBoxLayout,
    QWidget,
)
from src.core.constants import APP_NAME, APP_VERSION, AUTO_SAVE_DEBOUNCE_MS
from src.core.debouncer import DebounceTimer
from src.core.global_hotkey import GlobalHotkeyManager
from src.services.image_service import ImageService
from src.services.scratchpad_service import ScratchpadService
from src.services.session_service import SessionService
from src.ui.components.editor import TechPadEditor
from src.ui.components.history_drawer import HistoryDrawer
from src.ui.components.system_tray import TechPadSystemTray, get_or_create_app_icon
from src.ui.components.tab_widget import TechPadTabWidget
from src.ui.components.toolbar import TechPadToolBar
from src.ui.dialogs.edit_ticket_dialog import EditTicketDialog
from src.ui.dialogs.settings_dialog import SettingsDialog
from src.ui.m365.launcher_widget import M365LauncherWidget


class CompactLabel(QLabel):
    """QLabel whose minimumSizeHint width does not constrain narrow parent layouts."""

    def minimumSizeHint(self) -> QSize:
        return QSize(0, super().minimumSizeHint().height())


class TechPadMainWindow(QMainWindow):
    """Main window integrating tabs, rich-text editor, toolbar, auto-save, and history drawer."""

    def __init__(
        self,
        scratchpad_service: ScratchpadService,
        image_service: ImageService,
        session_service: SessionService,
        parent: Optional[QWidget] = None,
    ):
        super().__init__(parent)
        self.scratchpad_service = scratchpad_service
        self.image_service = image_service
        self.session_service = session_service

        self.setWindowTitle(f"{APP_NAME} v{APP_VERSION} — Technician Scratchpad")
        self.resize(1100, 750)
        self.setMinimumSize(660, 400)

        # Pending saves tracking: {scratchpad_id: DebounceTimer}
        self._debounce_timers: dict[int, DebounceTimer] = {}
        self._force_quit: bool = False
        self._shutdown_accepted = False
        self._note_revisions: dict[int, int] = {}
        self._first_minimize_to_tray: bool = True
        self._notes_visibility = {}
        self._notes_enabled = {}
        self._workspace_restore_ticket = None
        self._dirty_scratchpad_ids: set[int] = set()
        self._workspace_switching = False
        self._user_history_drawer_open: bool = False
        self._history_auto_collapsed: bool = False
        self._user_split_view_active: bool = False
        self._split_auto_single_pane: bool = False
        self._compact_active_pane: int = 0
        self._saved_splitter_sizes: list[int] = []
        self._logical_active_scratchpad_id = None
        self._restoring_workspace: bool = False

        self.setWindowIcon(get_or_create_app_icon())

        self._setup_ui()
        self._setup_shortcuts()
        self._setup_tray_and_hotkey()
        self._restore_workspace()

        # Install application-level event filter for reliable global shortcut interception
        if app := QApplication.instance():
            app.installEventFilter(self)

    def eventFilter(self, watched, event) -> bool:
        """Application-level event filter intercepting tab shortcuts across all widgets.

        Ensures browser-style tab shortcuts (including Ctrl+Shift+PageUp/PageDown)
        work reliably regardless of which child widget has focus, and handles
        hardware keyboard modifiers (such as Qt.KeypadModifier on Windows).
        """
        if event.type() == QEvent.KeyPress:
            if QApplication.activeModalWidget() is not None:
                return super().eventFilter(watched, event)

            mods = event.modifiers()
            has_ctrl = bool(mods & Qt.ControlModifier)
            has_shift = bool(mods & Qt.ShiftModifier)
            has_alt = bool(mods & Qt.AltModifier)
            key = event.key()

            # F8 toggle window visibility (minimize if active, pop if minimized/inactive)
            if key == Qt.Key_F8 and not has_ctrl and not has_alt and not has_shift:
                self.toggle_window_visibility()
                return True

            # Alt+T remains global; it returns to Notes before entering HUD.
            if key == Qt.Key_T and has_alt and not has_ctrl and not has_shift:
                self.toggle_mini_hud_mode()
                return True

            if self.is_m365_workspace:
                return super().eventFilter(watched, event)

            if key == Qt.Key_F5 and not has_ctrl and not has_alt and not has_shift:
                if hasattr(self, "toolbar"):
                    self.toolbar._insert_timestamp()
                return True

            if key == Qt.Key_Z and has_alt and has_shift and not has_ctrl:
                self.switch_compact_split_pane()
                return True

            if key == Qt.Key_Z and has_alt and not has_ctrl and not has_shift:
                self._toggle_split_view()
                return True

            if has_ctrl and not has_alt:
                # 1. Tab Reordering (Slide Left / Right): Ctrl + Shift + PageDown / PageUp
                if has_shift:
                    if key == Qt.Key_PageDown:
                        self._move_active_tab_relative(+1)
                        return True
                    elif key == Qt.Key_PageUp:
                        self._move_active_tab_relative(-1)
                        return True
                    elif key in (Qt.Key_Backtab, Qt.Key_Tab):
                        self._switch_tab_relative(-1)
                        return True
                    elif key == Qt.Key_T:
                        self._restore_last_closed_tab()
                        return True

                # 2. Tab Navigation & Management: Ctrl + PageDown / PageUp / Tab / W / T / 1..9
                else:
                    if key == Qt.Key_PageDown:
                        self._switch_tab_relative(+1)
                        return True
                    elif key == Qt.Key_PageUp:
                        self._switch_tab_relative(-1)
                        return True
                    elif key == Qt.Key_Tab:
                        self._switch_tab_relative(+1)
                        return True
                    elif key in (Qt.Key_W, Qt.Key_F4):
                        self._close_current_tab()
                        return True
                    elif key == Qt.Key_T:
                        self.create_new_tab()
                        return True
                    elif Qt.Key_1 <= key <= Qt.Key_8:
                        self._select_tab_index(key - Qt.Key_1)
                        return True
                    elif key == Qt.Key_9:
                        self._select_tab_index(self.tab_widget.count() - 1)
                        return True

        return super().eventFilter(watched, event)

    def _setup_ui(self) -> None:
        # Central Horizontal Splitter with Primary & Secondary Tab Panes
        self.workspace_splitter = QSplitter(Qt.Horizontal, self)
        self.workspace_splitter.setChildrenCollapsible(False)
        self.workspace_splitter.splitterMoved.connect(lambda pos, idx: self._save_session_state())

        # Secondary Tab Widget (Left Pane — Split View Sidebar)
        self.secondary_tab_widget = TechPadTabWidget(self)
        self.secondary_tab_widget.tabBar().tabBarClicked.connect(
            lambda idx: self._on_tab_header_clicked(self.secondary_tab_widget, idx)
        )
        self.secondary_tab_widget.new_tab_requested.connect(self._create_new_secondary_tab)
        self.secondary_tab_widget.tab_edit_requested.connect(self._on_secondary_tab_double_clicked)
        self.secondary_tab_widget.tab_context_menu_requested.connect(self._on_secondary_tab_context_menu)
        self.secondary_tab_widget.tab_close_prompted.connect(self._on_secondary_tab_close_requested)
        self.secondary_tab_widget.tab_reordered.connect(self._on_tabs_reordered)
        self.secondary_tab_widget.currentChanged.connect(self._on_secondary_tab_changed)
        self.secondary_tab_widget.tab_cross_drop_requested.connect(
            lambda idx, gpos: self._handle_tab_cross_drop(self.secondary_tab_widget, idx, gpos)
        )
        self.secondary_tab_widget.tab_cross_drag_moved.connect(
            lambda idx, gpos: self._handle_tab_cross_drag_move(self.secondary_tab_widget, idx, gpos)
        )
        self.secondary_tab_widget.hide()
        self.workspace_splitter.addWidget(self.secondary_tab_widget)

        # Primary Tab Widget (Right Pane — Main Window)
        self.tab_widget = TechPadTabWidget(self)
        self.tab_widget.tabBar().tabBarClicked.connect(
            lambda idx: self._on_tab_header_clicked(self.tab_widget, idx)
        )
        self.tab_widget.new_tab_requested.connect(self.create_new_tab)
        self.tab_widget.tab_edit_requested.connect(self._on_tab_double_clicked)
        self.tab_widget.tab_context_menu_requested.connect(self._on_tab_context_menu)
        self.tab_widget.tab_close_prompted.connect(self._on_tab_close_requested)
        self.tab_widget.tab_reordered.connect(self._on_tabs_reordered)
        self.tab_widget.currentChanged.connect(self._on_current_tab_changed)
        self.tab_widget.tab_cross_drop_requested.connect(
            lambda idx, gpos: self._handle_tab_cross_drop(self.tab_widget, idx, gpos)
        )
        self.tab_widget.tab_cross_drag_moved.connect(
            lambda idx, gpos: self._handle_tab_cross_drag_move(self.tab_widget, idx, gpos)
        )
        self.workspace_splitter.addWidget(self.tab_widget)

        self.workspace_stack = QStackedWidget(self)
        self.workspace_stack.addWidget(self.workspace_splitter)
        self.m365_workspace = M365LauncherWidget(self.workspace_stack)
        self.workspace_stack.addWidget(self.m365_workspace)
        self.setMinimumSize(660, 400)
        self.workspace_stack.setCurrentWidget(self.workspace_splitter)
        self._update_module_status_bar_buttons(is_m365=False)
        self.m365_workspace.back_requested.connect(self.switch_workspace)
        self.setCentralWidget(self.workspace_stack)

        # Formatting & System Toolbars (Two-Row Header)
        self.toolbar = TechPadToolBar(self)
        self.toolbar.image_requested.connect(self._on_insert_image_file)
        self.toolbar.skeleton_selected.connect(self._on_skeleton_selected)
        self.toolbar.checklist_requested.connect(self._on_insert_checklist)
        self.toolbar.copy_formatted_requested.connect(self._on_copy_formatted_note)
        self.toolbar.export_note_requested.connect(self._on_export_note)
        self.toolbar.split_view_requested.connect(self._toggle_split_view)
        self.toolbar.mini_hud_requested.connect(self.toggle_mini_hud_mode)
        self.toolbar.opacity_changed.connect(self._on_opacity_changed)
        self.toolbar.history_requested.connect(self._toggle_history_drawer)
        self.toolbar.settings_requested.connect(self._open_settings_dialog)
        self.toolbar.m365_requested.connect(self.switch_workspace)
        self.toolbar.stopwatch.time_updated.connect(self._on_stopwatch_time_updated)

        # Row 1: Formatting Actions
        self.addToolBar(Qt.TopToolBarArea, self.toolbar)
        # Line break between toolbar rows
        self.addToolBarBreak(Qt.TopToolBarArea)
        # Row 2: Ticket Workflow, Stopwatch, Opacity & Preferences
        self.addToolBar(Qt.TopToolBarArea, self.toolbar.secondary_toolbar)

        # History / Archive Side Drawer
        self.history_drawer = HistoryDrawer(self.scratchpad_service, self)
        self.history_drawer.restore_requested.connect(self._on_restore_ticket)
        self.history_drawer.split_restore_requested.connect(self._on_history_split_restore)
        self.history_drawer.delete_requested.connect(self._on_delete_ticket)
        self.addDockWidget(Qt.RightDockWidgetArea, self.history_drawer)
        self.resizeDocks([self.history_drawer], [380], Qt.Horizontal)

        # Status Bar
        self.status_bar = QStatusBar(self)
        self.setStatusBar(self.status_bar)
        self.toolbar.stopwatch.status_message_requested.connect(self.status_bar.showMessage)

        # 1. Toggle Always-on-Top Mini-HUD button in status bar (down-left corner for 1-click restore in HUD mode)
        self.btn_status_hud = QPushButton("📌 HUD (Alt+T)")
        self.btn_status_hud.setObjectName("btnSecondary")
        self.btn_status_hud.setFlat(True)
        self.btn_status_hud.setToolTip("Toggle Always-on-Top Mini-HUD Mode (Alt+T)")
        self.btn_status_hud.clicked.connect(self.toggle_mini_hud_mode)
        self.status_bar.addWidget(self.btn_status_hud)

        # 2. M365 Launcher button in status bar (2nd place from left, between HUD and Split)
        self.btn_m365 = QPushButton("M365 Launcher")
        self.btn_m365.setObjectName("btnSecondary")
        self.btn_m365.setFlat(True)
        self.btn_m365.setToolTip("Open the M365 Launcher workspace in this window (Alt+F8)")
        self.btn_m365.setAccessibleName("M365 Launcher")
        self.btn_m365.setFocusPolicy(Qt.StrongFocus)
        self.btn_m365.clicked.connect(self.switch_workspace)
        self.status_bar.addWidget(self.btn_m365)
        self.toolbar.btn_m365 = self.btn_m365

        # 3. Toggle split view button in status bar (on the right side of M365 Launcher button, left side of bottom bar)
        self.btn_toggle_split = QPushButton("◫ Split (Alt+Z)")
        self.btn_toggle_split.setObjectName("btnSecondary")
        self.btn_toggle_split.setFlat(True)
        self.btn_toggle_split.setToolTip("Toggle side-by-side split view mode (Alt+Z)")
        self.btn_toggle_split.clicked.connect(self._toggle_split_view)
        self.status_bar.addWidget(self.btn_toggle_split)

        self.btn_switch_split_pane = QPushButton("⇋ Switch Pane (Alt+Shift+Z)")
        self.btn_switch_split_pane.setObjectName("btnSecondary")
        self.btn_switch_split_pane.setFlat(True)
        self.btn_switch_split_pane.setToolTip("Switch between primary and secondary split panes in compact mode (Alt+Shift+Z)")
        self.btn_switch_split_pane.clicked.connect(self.switch_compact_split_pane)
        self.btn_switch_split_pane.setVisible(False)
        self.status_bar.addWidget(self.btn_switch_split_pane)

        # 4. Toggle history drawer button in status bar (on the right side of the Split button, left side of bottom bar)
        self.btn_toggle_drawer = QPushButton("🕰️ History (Ctrl+H)")
        self.btn_toggle_drawer.setObjectName("btnSecondary")
        self.btn_toggle_drawer.setFlat(True)
        self.btn_toggle_drawer.setToolTip("Toggle History and Archival drawer (Ctrl+H)")
        self.btn_toggle_drawer.clicked.connect(self._toggle_history_drawer)
        self.status_bar.addWidget(self.btn_toggle_drawer)

        # 5. M365 Launcher module sidebar buttons: Categories & Active Ticket (replacing Split & History in M365 mode)
        self.btn_m365_categories = QPushButton("☰ Categories")
        self.btn_m365_categories.setObjectName("btnSecondary")
        self.btn_m365_categories.setFlat(True)
        self.btn_m365_categories.setCheckable(True)
        self.btn_m365_categories.setChecked(self.m365_workspace.nav_toggle.isChecked())
        self.btn_m365_categories.setToolTip("Show or hide the category navigation sidebar")
        self.btn_m365_categories.setAccessibleName("Toggle category navigation panel")
        self.btn_m365_categories.setFocusPolicy(Qt.StrongFocus)
        self.btn_m365_categories.clicked.connect(self._toggle_m365_categories)
        self.btn_m365_categories.setVisible(False)
        self.status_bar.addWidget(self.btn_m365_categories)

        self.btn_m365_active_ticket = QPushButton("Active Ticket")
        self.btn_m365_active_ticket.setObjectName("btnSecondary")
        self.btn_m365_active_ticket.setFlat(True)
        self.btn_m365_active_ticket.setCheckable(True)
        self.btn_m365_active_ticket.setChecked(self.m365_workspace.ticket_panel_toggle.isChecked())
        self.btn_m365_active_ticket.setToolTip("Show or hide the active ticket sidebar")
        self.btn_m365_active_ticket.setAccessibleName("Toggle active ticket panel")
        self.btn_m365_active_ticket.setFocusPolicy(Qt.StrongFocus)
        self.btn_m365_active_ticket.clicked.connect(self._toggle_m365_active_ticket)
        self.btn_m365_active_ticket.setVisible(False)
        self.status_bar.addWidget(self.btn_m365_active_ticket)

        # Bidirectional synchronization with M365LauncherWidget toggles
        self.m365_workspace.nav_toggle.toggled.connect(self.btn_m365_categories.setChecked)
        self.m365_workspace.ticket_panel_toggle.toggled.connect(self.btn_m365_active_ticket.setChecked)
        self.m365_workspace.btn_categories = self.btn_m365_categories
        self.m365_workspace.btn_active_ticket = self.btn_m365_active_ticket

        # Ensure HUD, M365 Launcher / T-Notes, and module-specific buttons remain visible on the left even during status messages
        self.status_bar.messageChanged.connect(self._keep_status_buttons_visible)

        # 6. Save status indicator and active ticket details
        self.lbl_save_status = QLabel("● Saved")
        self.lbl_save_status.setStyleSheet("color: #4ade80; font-weight: bold; padding-left: 8px;")
        self.status_bar.addWidget(self.lbl_save_status)

        self.lbl_active_info = CompactLabel("")
        self.lbl_active_info.setStyleSheet("color: #9cdcfe; padding-left: 16px;")
        self.status_bar.addWidget(self.lbl_active_info)

    def _toggle_m365_categories(self) -> None:
        """Toggles the M365 category navigation sidebar."""
        if hasattr(self, "m365_workspace") and hasattr(self.m365_workspace, "nav_toggle"):
            self.m365_workspace.nav_toggle.setChecked(self.btn_m365_categories.isChecked())

    def _toggle_m365_active_ticket(self) -> None:
        """Toggles the M365 active ticket sidebar."""
        if hasattr(self, "m365_workspace") and hasattr(self.m365_workspace, "ticket_panel_toggle"):
            self.m365_workspace.ticket_panel_toggle.setChecked(self.btn_m365_active_ticket.isChecked())

    def _update_module_status_bar_buttons(self, is_m365: Optional[bool] = None) -> None:
        """Updates visibility of module-specific buttons on the bottom status bar."""
        if is_m365 is None:
            is_m365 = self.is_m365_workspace
        if is_m365:
            if hasattr(self, "btn_toggle_split"):
                self.btn_toggle_split.setVisible(False)
            if hasattr(self, "btn_switch_split_pane"):
                self.btn_switch_split_pane.setVisible(False)
            if hasattr(self, "btn_toggle_drawer"):
                self.btn_toggle_drawer.setVisible(False)
            if hasattr(self, "btn_m365_categories"):
                self.btn_m365_categories.setVisible(True)
            if hasattr(self, "btn_m365_active_ticket"):
                self.btn_m365_active_ticket.setVisible(True)
        else:
            if hasattr(self, "btn_toggle_split"):
                self.btn_toggle_split.setVisible(True)
            if hasattr(self, "btn_switch_split_pane"):
                self.btn_switch_split_pane.setVisible(getattr(self, "_split_auto_single_pane", False))
            if hasattr(self, "btn_toggle_drawer"):
                self.btn_toggle_drawer.setVisible(True)
            if hasattr(self, "btn_m365_categories"):
                self.btn_m365_categories.setVisible(False)
            if hasattr(self, "btn_m365_active_ticket"):
                self.btn_m365_active_ticket.setVisible(False)

    def _keep_status_buttons_visible(self, _msg: str = "") -> None:
        """Keeps HUD, M365 Launcher / T-Notes, and module-specific buttons visible on the left even during temporary status messages."""
        if hasattr(self, "btn_status_hud"):
            self.btn_status_hud.setVisible(True)
        if hasattr(self, "btn_m365"):
            self.btn_m365.setVisible(True)
        self._update_module_status_bar_buttons()

    def _setup_shortcuts(self) -> None:
        """Configures application-wide shortcuts for saving, drawer toggle, and settings.

        Note: Browser-style tab shortcuts (Ctrl+T, Ctrl+W, Ctrl+PgUp/PgDown,
        Ctrl+Shift+PgUp/PgDown, Ctrl+1..9) are intercepted centrally in eventFilter()
        to guarantee reliable dispatch across all focused child widgets and
        hardware modifier states.
        """
        self._notes_shortcuts = [
            QShortcut(QKeySequence("Ctrl+S"), self, self.flush_all_saves, context=Qt.ApplicationShortcut),
            QShortcut(QKeySequence("Ctrl+H"), self, self._toggle_history_drawer, context=Qt.ApplicationShortcut),
            QShortcut(QKeySequence("Ctrl+,"), self, self._open_settings_dialog, context=Qt.ApplicationShortcut),
            QShortcut(QKeySequence("Alt+Z"), self, self._toggle_split_view, context=Qt.ApplicationShortcut),
            QShortcut(QKeySequence("Alt+Shift+Z"), self, self.switch_compact_split_pane, context=Qt.ApplicationShortcut),
        ]
        QShortcut(QKeySequence("Alt+T"), self, self.toggle_mini_hud_mode, context=Qt.ApplicationShortcut)
        QShortcut(QKeySequence("F8"), self, self.toggle_window_visibility, context=Qt.ApplicationShortcut)
        # One Qt shortcut owns Alt+F8; do not also handle it in eventFilter.
        self.workspace_shortcut = QShortcut(
            QKeySequence("Alt+F8"), self, self.switch_workspace
        )
        self.workspace_shortcut.setContext(Qt.ApplicationShortcut)
        self.workspace_shortcut.setAutoRepeat(False)

    @property
    def is_m365_workspace(self) -> bool:
        return self.workspace_stack.currentWidget() is self.m365_workspace

    @property
    def history_auto_collapsed(self) -> bool:
        """Returns True if the History drawer was automatically collapsed by responsive layout."""
        return getattr(self, "_history_auto_collapsed", False)

    @history_auto_collapsed.setter
    def history_auto_collapsed(self, val: bool) -> None:
        self._history_auto_collapsed = bool(val)

    @property
    def split_auto_single_pane(self) -> bool:
        """Returns True if Split View is temporarily displaying a single pane due to narrow width."""
        return getattr(self, "_split_auto_single_pane", False)

    @property
    def is_split_view_active(self) -> bool:
        """Returns True if Split View is currently active and open."""
        return getattr(self, "_user_split_view_active", False) and (
            self.secondary_tab_widget.isVisible()
            or getattr(self, "_split_auto_single_pane", False)
            or (getattr(self, "is_mini_hud", False) and getattr(self, "_saved_split_active", False))
            or (getattr(self, "is_m365_workspace", False) and getattr(self, "_notes_split_active", False))
        )

    def switch_workspace(self) -> bool:
        """Shared button/Alt+F8 route; refuse modal, shutdown or reentrant input."""
        if (
            QApplication.activeModalWidget() is not None
            or self._force_quit
            or self._workspace_switching
            or not self.isVisible()
            or self.isMinimized()
        ):
            return False
        self._workspace_switching = True
        try:
            if self.is_m365_workspace:
                self.show_notes_workspace()
                return True
            return self.show_m365_workspace()
        finally:
            self._workspace_switching = False

    def _activate_and_focus(self, target_widget: Optional[QWidget] = None) -> None:
        """Activate the window and direct keyboard focus to the target widget."""
        if not self.isVisible() or self.isMinimized():
            return
        self.raise_()
        self.activateWindow()
        if sys.platform == "win32":
            try:
                import ctypes
                ctypes.windll.user32.SetForegroundWindow(int(self.winId()))
            except Exception:
                pass
        if target_widget is not None:
            target_widget.setFocus()

    def show_m365_workspace(self) -> bool:
        """Flush notes, then select the existing M365 page without rebuilding notes."""
        if self.is_m365_workspace:
            return True
        pending = {sid for sid, timer in self._debounce_timers.items() if timer.is_active()}
        pending.update(self._dirty_scratchpad_ids)
        try:
            # Call the existing saver directly: exceptions raised inside a Qt
            # signal callback do not propagate through DebounceTimer.flush().
            for sid in sorted(pending):
                if timer := self._debounce_timers.get(sid):
                    timer.cancel()
                self._execute_save(sid)
        except Exception:
            # Dirty IDs survive failed autosaves and stopped timers, allowing
            # an explicit navigation retry without treating an idle timer as saved.
            self.status_bar.showMessage("Notes could not be saved. Stay in T-Notes and retry.", 6000)
            return False
        editor = self._get_active_editor()
        self._workspace_restore_ticket = editor.scratchpad_id if editor else None
        self._notes_split_active = getattr(self, "_saved_split_active", False) if self.is_mini_hud else self.is_split_view_active
        for widget in (self.toolbar, self.toolbar.secondary_toolbar, self.history_drawer):
            self._notes_visibility[widget] = not widget.isHidden()
            widget.hide()
        self._notes_visibility[self.secondary_tab_widget] = (
            getattr(self, "_saved_split_visible", False) if self.is_mini_hud else (self._user_split_view_active and not self.secondary_tab_widget.isHidden())
        )
        if not self.history_auto_collapsed:
            self._user_history_drawer_open = self._notes_visibility[self.history_drawer]
        actions = set(self.toolbar.findChildren(QAction) + self.toolbar.secondary_toolbar.findChildren(QAction))
        for control in (*actions, *self._notes_shortcuts, self.btn_toggle_split, self.btn_toggle_drawer):
            self._notes_enabled[control] = control.isEnabled()
            control.setEnabled(False)

        # Transform M365 Launcher button into T-Notes button on bottom bar
        self.btn_m365.setText("T-Notes")
        self.btn_m365.setToolTip("Return to T-Notes workspace (Alt+F8)")
        self.btn_m365.setAccessibleName("T-Notes")
        self.btn_m365.setEnabled(True)
        self.btn_m365.setVisible(True)
        self._update_module_status_bar_buttons()

        if self.is_mini_hud:
            if hasattr(self, "tab_widget"):
                self.tab_widget.set_hud_nav_arrows_visible(False)
            self.setWindowTitle(f"📌 [HUD] {APP_NAME} — M365 Launcher")
            if hasattr(self, "btn_status_hud"):
                self.btn_status_hud.setText("📌 Normal (Alt+T)")
                self.btn_status_hud.setVisible(True)
        else:
            self.setMinimumSize(640, 380)
            if hasattr(self, "btn_status_hud"):
                self.btn_status_hud.setText("📌 HUD (Alt+T)")
                self.btn_status_hud.setVisible(True)

        self.workspace_stack.setCurrentWidget(self.m365_workspace)
        self._update_module_status_bar_buttons(is_m365=True)
        self._activate_and_focus(self.m365_workspace.back_button)
        return True

    def show_notes_workspace(self) -> None:
        """Restore the same Notes page and its pre-navigation controls."""
        if not self.is_m365_workspace:
            return

        # Transform T-Notes button back into M365 Launcher button on bottom bar
        self.btn_m365.setText("M365 Launcher")
        self.btn_m365.setToolTip("Open the M365 Launcher workspace in this window (Alt+F8)")
        self.btn_m365.setAccessibleName("M365 Launcher")
        self.btn_m365.setEnabled(True)
        self.btn_m365.setVisible(True)
        self._update_module_status_bar_buttons()

        if self.is_mini_hud:
            self.setMinimumSize(340, 200)
            if hasattr(self, "tab_widget"):
                self.tab_widget.set_hud_nav_arrows_visible(True)
            editor = self._get_active_editor()
            t_label = ""
            if editor:
                ticket = self.scratchpad_service.get_ticket(editor.scratchpad_id)
                if ticket:
                    t_num = ticket.get("ticket_number", "")
                    client = ticket.get("client_name", "")
                    t_label = f" — #{t_num}" + (f" ({client})" if client else "")
            self.setWindowTitle(f"📌 [HUD] {APP_NAME}{t_label}")
            if hasattr(self, "btn_status_hud"):
                self.btn_status_hud.setText("📌 Normal (Alt+T)")
                self.btn_status_hud.setVisible(True)
        else:
            self.setMinimumSize(660, 400)
            self.setWindowTitle(f"{APP_NAME} v{APP_VERSION} — Technician Scratchpad")
            if hasattr(self, "btn_status_hud"):
                self.btn_status_hud.setText("📌 HUD (Alt+T)")
                self.btn_status_hud.setVisible(True)

        self.workspace_stack.setCurrentWidget(self.workspace_splitter)
        self._update_module_status_bar_buttons(is_m365=False)
        split_was_visible = self._notes_visibility.get(self.secondary_tab_widget, False)
        if not self.is_mini_hud:
            for widget, visible in self._notes_visibility.items():
                widget.setVisible(visible)
            if split_was_visible:
                self._user_split_view_active = True
                if hasattr(self, "toolbar") and hasattr(self.toolbar, "btn_split"):
                    self.toolbar.btn_split.setChecked(True)
                if hasattr(self, "btn_toggle_split"):
                    self.btn_toggle_split.setText("◫ Single (Alt+Z)")
                if self.width() >= 750:
                    self.secondary_tab_widget.show()
                    self.tab_widget.show()
        else:
            self._saved_split_active = getattr(self, "_notes_split_active", False)
            self._saved_split_visible = split_was_visible
        for control, enabled in self._notes_enabled.items():
            control.setEnabled(enabled)
        self._notes_visibility.clear()
        self._notes_enabled.clear()
        if not self.is_mini_hud:
            self._clamp_geometry_to_screen()
            self._check_responsive_layout(self.width())
        self._activate_and_focus(self._get_active_editor())

    def _setup_tray_and_hotkey(self) -> None:
        """Configures the system tray icon and system-wide F8 global hotkey."""
        # System Tray Icon
        self.tray_icon = TechPadSystemTray(self)
        self.tray_icon.toggle_requested.connect(self.toggle_window_visibility)
        self.tray_icon.new_tab_requested.connect(self._create_new_tab_and_show)
        self.tray_icon.hud_requested.connect(self.toggle_mini_hud_mode)
        self.tray_icon.quit_requested.connect(self.quit_application)
        self.tray_icon.show()

        # Global System-Wide F8 Hotkey (managed via Win32 RegisterHotKey)
        self.global_hotkey = GlobalHotkeyManager(parent=self)
        self.global_hotkey.activated.connect(self.toggle_window_visibility)
        self.global_hotkey.register()

    def toggle_window_visibility(self) -> None:
        """Toggles window visibility: pops to front if minimized/hidden/inactive, or minimizes if active."""
        is_active = self.isVisible() and not self.isMinimized() and self.isActiveWindow()

        if is_active:
            # App is open on screen and active in foreground -> minimize it
            self.showMinimized()
        else:
            # App is minimized, hidden in tray, or behind other windows -> make it pop!
            self.showNormal()
            self.raise_()
            self.activateWindow()
            if sys.platform == "win32":
                try:
                    user32 = ctypes.windll.user32
                    hwnd = int(self.winId())
                    user32.ShowWindow(hwnd, 9)  # 9 = SW_RESTORE
                    user32.SetForegroundWindow(hwnd)
                except Exception:
                    pass
            if self.is_m365_workspace:
                self._activate_and_focus(self.m365_workspace.back_button)
            elif editor := self._get_active_editor():
                editor.setFocus()

    def _create_new_tab_and_show(self) -> None:
        """Restores window from tray and creates a new ticket tab."""
        self.showNormal()
        self.raise_()
        self.activateWindow()
        self.show_notes_workspace()
        self.create_new_tab()

    def quit_application(self) -> None:
        """Performs full synchronous flush, unregisters hotkeys, and cleanly exits the application."""
        self._force_quit = True
        self._shutdown_accepted = False
        self.close()  # closeEvent owns persistence and all teardown.
        if self._shutdown_accepted:
            if app := QApplication.instance():
                app.quit()

    def _save_session_state(self) -> None:
        """Persists workspace session state including tab orders, split view, and window layout."""
        if getattr(self, "_restoring_workspace", False):
            return

        # 1. Tab IDs in order for primary and secondary panes
        primary_ids = []
        for i in range(self.tab_widget.count()):
            ed = self.tab_widget.get_editor_at(i)
            if ed:
                primary_ids.append(ed.scratchpad_id)

        secondary_ids = []
        for i in range(self.secondary_tab_widget.count()):
            ed = self.secondary_tab_widget.get_editor_at(i)
            if ed:
                secondary_ids.append(ed.scratchpad_id)

        # 2. Active tickets in each pane
        prim_cur = self.tab_widget.get_current_editor()
        prim_active_id = prim_cur.scratchpad_id if prim_cur else None

        sec_cur = self.secondary_tab_widget.get_current_editor()
        sec_active_id = sec_cur.scratchpad_id if sec_cur else None

        # Overall active scratchpad
        if self.is_m365_workspace and getattr(self, "_workspace_restore_ticket", None):
            focused_id = self._workspace_restore_ticket
        elif getattr(self, "_logical_active_scratchpad_id", None):
            focused_id = self._logical_active_scratchpad_id
        elif self.secondary_tab_widget.isVisible() and self.secondary_tab_widget.hasFocus() and sec_active_id:
            focused_id = sec_active_id
        else:
            focused_id = prim_active_id or sec_active_id

        # 3. Split view active state
        if self.is_mini_hud:
            split_active = getattr(self, "_saved_split_active", False) and (len(secondary_ids) > 0)
        else:
            split_active = self.is_split_view_active and (len(secondary_ids) > 0)

        # 4. Split sizes
        sizes = self.workspace_splitter.sizes() if hasattr(self, "workspace_splitter") else []
        split_sizes_str = json.dumps(sizes) if sizes else ""

        # 5. Window geometry and opacity
        geometry_hex = self.saveGeometry().toHex().data().decode("utf-8") if hasattr(self, "saveGeometry") else ""
        opacity_val = int(round(self.windowOpacity() * 100)) if hasattr(self, "windowOpacity") else 100

        # 6. Drawer open state
        if self.is_m365_workspace:
            drawer_open = self._user_history_drawer_open if self.history_auto_collapsed else self._notes_visibility.get(self.history_drawer, False)
        else:
            drawer_open = self._user_history_drawer_open if self.history_auto_collapsed else (self.history_drawer.isVisible() if hasattr(self, "history_drawer") else False)

        self.session_service.persist_workspace(
            active_scratchpad_id=focused_id,
            window_geometry=geometry_hex,
            window_opacity=opacity_val,
            history_drawer_open=drawer_open,
            split_view_active=split_active,
            split_active_scratchpad_id=sec_active_id,
            primary_scratchpad_ids=json.dumps(primary_ids),
            secondary_scratchpad_ids=json.dumps(secondary_ids),
            split_sizes=split_sizes_str,
        )

    def _restore_workspace(self) -> None:
        """Restores tabs and focused tab from SQLite session, supporting single-pane and Split View."""
        self._restoring_workspace = True
        try:
            active_tickets, focused_id, window_geometry, window_opacity, drawer_open = self.session_service.restore_workspace()

            if window_geometry:
                try:
                    self.restoreGeometry(bytes.fromhex(window_geometry))
                except Exception:
                    pass

            # Apply saved opacity (60% to 100%)
            opacity_clamped = max(60, min(100, window_opacity))
            self.setWindowOpacity(opacity_clamped / 100.0)
            self.toolbar.set_opacity_value(opacity_clamped)

            self._user_history_drawer_open = bool(drawer_open)
            if self.width() < 850 and drawer_open:
                self._history_auto_collapsed = True
                self.history_drawer.setVisible(False)
            else:
                self._history_auto_collapsed = False
                self.history_drawer.setVisible(bool(drawer_open))

            split_info = self.session_service.get_split_view_session()
            split_active = split_info.get("split_view_active", False)
            split_active_id = split_info.get("split_active_scratchpad_id")
            primary_ids_raw = split_info.get("primary_scratchpad_ids", "")
            secondary_ids_raw = split_info.get("secondary_scratchpad_ids", "")
            split_sizes_raw = split_info.get("split_sizes", "")

            try:
                primary_ids = json.loads(primary_ids_raw) if primary_ids_raw else []
            except Exception:
                primary_ids = []

            try:
                secondary_ids = json.loads(secondary_ids_raw) if secondary_ids_raw else []
            except Exception:
                secondary_ids = []

            ticket_map = {t["id"]: t for t in active_tickets}

            sec_tickets = []
            if secondary_ids:
                sec_tickets = [ticket_map[sid] for sid in secondary_ids if sid in ticket_map]

            sec_id_set = {t["id"] for t in sec_tickets}

            prim_tickets = []
            if primary_ids:
                prim_tickets = [ticket_map[sid] for sid in primary_ids if sid in ticket_map and sid not in sec_id_set]

            accounted = {t["id"] for t in prim_tickets} | sec_id_set
            for t in active_tickets:
                if t["id"] not in accounted:
                    prim_tickets.append(t)

            if not prim_tickets and sec_tickets:
                prim_tickets.append(sec_tickets.pop(0))

            # Populate primary tab widget
            prim_focus_idx = 0
            for i, ticket in enumerate(prim_tickets):
                editor = self._create_editor(ticket["id"], ticket.get("content_html", ""))
                idx = self.tab_widget.add_ticket_tab(ticket, editor)
                if ticket["id"] == focused_id:
                    prim_focus_idx = idx

            if self.tab_widget.count() > 0:
                self.tab_widget.setCurrentIndex(prim_focus_idx)

            if split_active and sec_tickets:
                self._user_split_view_active = True
                self.toolbar.btn_split.setChecked(True)
                self.btn_toggle_split.setText("◫ Single (Alt+Z)")

                sec_focus_idx = 0
                for i, ticket in enumerate(sec_tickets):
                    editor = self._create_editor(ticket["id"], ticket.get("content_html", ""))
                    idx = self.secondary_tab_widget.add_ticket_tab(ticket, editor)
                    if ticket["id"] == split_active_id:
                        sec_focus_idx = idx

                if self.secondary_tab_widget.count() > 0:
                    self.secondary_tab_widget.setCurrentIndex(sec_focus_idx)

                # Parse and apply splitter sizes
                split_sizes = []
                if split_sizes_raw:
                    try:
                        split_sizes = json.loads(split_sizes_raw)
                    except Exception:
                        split_sizes = []

                if self.width() < 750:
                    self._split_auto_single_pane = True
                    if focused_id in {t["id"] for t in sec_tickets}:
                        self._compact_active_pane = 1
                        self.tab_widget.hide()
                        self.secondary_tab_widget.show()
                        self.btn_switch_split_pane.setText("⇋ Pane 2/2 (Alt+Shift+Z)")
                    else:
                        self._compact_active_pane = 0
                        self.secondary_tab_widget.hide()
                        self.tab_widget.show()
                        self.btn_switch_split_pane.setText("⇋ Pane 1/2 (Alt+Shift+Z)")
                    self.btn_switch_split_pane.setVisible(True)
                else:
                    self._split_auto_single_pane = False
                    self.tab_widget.show()
                    self.secondary_tab_widget.show()
                    self.btn_switch_split_pane.setVisible(False)
                    if split_sizes and len(split_sizes) == 2 and sum(split_sizes) > 0:
                        self.workspace_splitter.setSizes(split_sizes)
                    else:
                        total_w = self.workspace_splitter.width() or self.width() or 1000
                        half = max(200, total_w // 2)
                        self.workspace_splitter.setSizes([half, half])

                if focused_id in {t["id"] for t in sec_tickets}:
                    sec_ed = self.secondary_tab_widget.get_current_editor()
                    if sec_ed:
                        self._on_editor_focused(sec_ed.scratchpad_id)
                else:
                    prim_ed = self.tab_widget.get_current_editor()
                    if prim_ed:
                        self._on_editor_focused(prim_ed.scratchpad_id)
            else:
                self._user_split_view_active = False
                self._split_auto_single_pane = False
                self.toolbar.btn_split.setChecked(False)
                self.btn_toggle_split.setText("◫ Split (Alt+Z)")
                self.btn_switch_split_pane.setVisible(False)
                self.tab_widget.show()
                self.secondary_tab_widget.hide()
                self._on_current_tab_changed(self.tab_widget.currentIndex())

            if focused_id:
                self._logical_active_scratchpad_id = focused_id
        finally:
            self._restoring_workspace = False

    def _create_editor(self, scratchpad_id: int, initial_html: str) -> TechPadEditor:
        """Instantiates and configures a TechPadEditor for a ticket."""
        editor = TechPadEditor(scratchpad_id, self.image_service, self)
        editor.load_content(initial_html)
        editor.content_modified.connect(self._on_editor_modified)
        editor.currentCharFormatChanged.connect(self.toolbar.update_format_states)
        editor.move_tab_requested.connect(self._move_active_tab_relative)
        editor.switch_tab_requested.connect(self._switch_tab_relative)
        editor.checklist_stats_changed.connect(self._on_checklist_stats_changed)
        editor.editor_focused.connect(self._on_editor_focused)

        # Create debouncer using configured delay
        delay_ms = int(self.session_service.get_setting("auto_save_delay_ms", str(AUTO_SAVE_DEBOUNCE_MS)))
        debouncer = DebounceTimer(
            delay_ms=delay_ms,
            callback=lambda sid=scratchpad_id: self._execute_save(sid),
            parent=self,
        )
        self._debounce_timers[scratchpad_id] = debouncer
        return editor

    def _on_tab_header_clicked(self, tw: TechPadTabWidget, idx: int) -> None:
        """Focuses the clicked tab's editor and sets it as the Active Ticket note."""
        if 0 <= idx < tw.count():
            editor = tw.get_editor_at(idx)
            if editor:
                editor.setFocus()
                self._on_editor_focused(editor.scratchpad_id)

    def _get_active_editor(self) -> Optional[TechPadEditor]:
        """Returns the currently active editor where the cursor is placed across primary and secondary panes."""
        # 1. First check if a TechPadEditor (or its viewport) has keyboard focus right now
        focus_w = QApplication.focusWidget()
        if isinstance(focus_w, TechPadEditor):
            self._logical_active_scratchpad_id = focus_w.scratchpad_id
            return focus_w
        if focus_w and isinstance(focus_w.parent(), TechPadEditor):
            self._logical_active_scratchpad_id = focus_w.parent().scratchpad_id
            return focus_w.parent()

        # 2. Check which visible pane's editor currently has focus or cursor focus
        sec_ed = self.secondary_tab_widget.get_current_editor() if self.secondary_tab_widget.isVisible() else None
        prim_ed = self.tab_widget.get_current_editor()

        if sec_ed and (sec_ed.hasFocus() or (sec_ed.viewport() and sec_ed.viewport().hasFocus())):
            self._logical_active_scratchpad_id = sec_ed.scratchpad_id
            return sec_ed
        if prim_ed and (prim_ed.hasFocus() or (prim_ed.viewport() and prim_ed.viewport().hasFocus())):
            self._logical_active_scratchpad_id = prim_ed.scratchpad_id
            return prim_ed

        # 3. Check tracked logical active scratchpad ID
        if getattr(self, "_logical_active_scratchpad_id", None):
            ed, tw, idx = self._find_editor_by_id(self._logical_active_scratchpad_id)
            if ed and ed.isVisible():
                return ed

        # 4. Check toolbar's current editor reference
        if hasattr(self, "toolbar") and self.toolbar._current_editor:
            if self.toolbar._current_editor.isVisible():
                return self.toolbar._current_editor

        # 5. Default fallback
        return prim_ed or sec_ed

    def _find_editor_by_id(self, scratchpad_id: int):
        """Finds editor, its parent tab widget, and index by scratchpad ID."""
        for tw in (self.tab_widget, self.secondary_tab_widget):
            for i in range(tw.count()):
                ed = tw.get_editor_at(i)
                if ed and ed.scratchpad_id == scratchpad_id:
                    return ed, tw, i
        return None, None, -1

    def create_new_tab(self) -> None:
        """Creates a new ticket scratchpad and opens it in a new tab."""
        prefix = self.session_service.get_setting("ticket_prefix", "INC-")
        active = self.scratchpad_service.get_active_tickets()
        ticket = self.scratchpad_service.create_ticket(ticket_number=f"{prefix}{len(active) + 101}")
        editor = self._create_editor(ticket["id"], "")
        idx = self.tab_widget.add_ticket_tab(ticket, editor)
        self.tab_widget.setCurrentIndex(idx)
        editor.setFocus()
        self.set_save_status("Saved", is_saved=True)
        self._on_tabs_reordered()

    def _create_new_secondary_tab(self) -> None:
        """Creates a new ticket scratchpad and opens it in the secondary (split) tab pane."""
        prefix = self.session_service.get_setting("ticket_prefix", "INC-")
        active = self.scratchpad_service.get_active_tickets()
        ticket = self.scratchpad_service.create_ticket(ticket_number=f"{prefix}{len(active) + 101}")
        editor = self._create_editor(ticket["id"], "")
        idx = self.secondary_tab_widget.add_ticket_tab(ticket, editor)
        self.secondary_tab_widget.setCurrentIndex(idx)
        editor.setFocus()
        self.set_save_status("Saved", is_saved=True)
        self._on_tabs_reordered()

    def _on_editor_modified(self, scratchpad_id: int) -> None:
        """Triggered whenever typing occurs in an editor."""
        self._dirty_scratchpad_ids.add(scratchpad_id)
        self._note_revisions[scratchpad_id] = self._note_revisions.get(scratchpad_id, 0) + 1
        self.set_save_status("Saving...", is_saved=False)
        debouncer = self._debounce_timers.get(scratchpad_id)
        if debouncer:
            debouncer.trigger()

    def _execute_save(self, scratchpad_id: int) -> None:
        """Saves editor content and synchronizes images with SQLite across primary and secondary panes."""
        editor, tw, idx = self._find_editor_by_id(scratchpad_id)
        try:
            if editor is None:
                if scratchpad_id in self._dirty_scratchpad_ids:
                    raise RuntimeError("Dirty ticket editor unavailable; recover editor and Retry (Ctrl+S)")
                return
            if timer := self._debounce_timers.get(scratchpad_id):
                timer.cancel()
            revision = self._note_revisions.get(scratchpad_id, 0)
            receipt = self.scratchpad_service.save_content(
                scratchpad_id=scratchpad_id,
                content_html=editor.toHtml(),
                in_memory_images=dict(editor.in_memory_images),
                expected_revision=revision,
            )
            if (receipt.status != "saved" or receipt.ticket_id != scratchpad_id
                    or receipt.attempted_revision != revision or receipt.persisted_revision != revision
                    or self._note_revisions.get(scratchpad_id, 0) != revision):
                raise RuntimeError("Save did not acknowledge current editor revision")
        except Exception:
            self._dirty_scratchpad_ids.add(scratchpad_id)
            self.set_save_status("Save Failed", is_saved=False)
            self.status_bar.showMessage("Save Failed — unsaved changes retained. Retry with Ctrl+S.", 10000)
            raise
        editor.in_memory_images.clear()
        self._dirty_scratchpad_ids.discard(scratchpad_id)

        # Check if any other saves are pending or dirty
        any_dirty = bool(self._dirty_scratchpad_ids)
        any_timer_active = any(d.is_active() for d in self._debounce_timers.values())
        if not any_dirty and not any_timer_active:
            self.set_save_status("Saved", is_saved=True)
        elif any_dirty and not any_timer_active:
            self.set_save_status("Save Failed", is_saved=False)

    def flush_all_saves(self) -> bool:
        """Forces all debounced saves and dirty tickets to execute immediately."""
        pending = {sid for sid, timer in self._debounce_timers.items() if timer.is_active()}
        pending.update(self._dirty_scratchpad_ids)
        all_ok = True
        for sid in sorted(pending):
            if timer := self._debounce_timers.get(sid):
                timer.cancel()
            try:
                self._execute_save(sid)
            except Exception:
                all_ok = False
        if self._dirty_scratchpad_ids or not all_ok:
            self.set_save_status("Save Failed", is_saved=False)
            return False
        self.set_save_status("Saved", is_saved=True)
        return True

    def set_save_status(self, text: str, is_saved: bool = True) -> None:
        """Updates the status bar indicator."""
        if is_saved and self._dirty_scratchpad_ids:
            is_saved = False
            text = "Saving..." if any(t.is_active() for t in self._debounce_timers.values()) else "Save Failed"
        if is_saved:
            self.lbl_save_status.setText("● Saved")
            self.lbl_save_status.setStyleSheet("color: #4ade80; font-weight: bold; padding-left: 8px;")
        else:
            if "fail" in text.lower():
                self.lbl_save_status.setText(f"● {text}")
                self.lbl_save_status.setStyleSheet("color: #ef4444; font-weight: bold; padding-left: 8px;")
            else:
                self.lbl_save_status.setText("↻ Saving...")
                self.lbl_save_status.setStyleSheet("color: #facc15; font-weight: bold; padding-left: 8px;")

    def _on_stopwatch_time_updated(self, scratchpad_id: int, elapsed_seconds: int) -> None:
        """Persists stopwatch elapsed seconds and updates the active tab's running minutes display."""
        self.scratchpad_service.update_elapsed_time(scratchpad_id, elapsed_seconds)

        # Update tab title with running minutes tag (e.g. '#4092 (14m) — ACME')
        editor, tw, idx = self._find_editor_by_id(scratchpad_id)
        if editor and tw:
            ticket = self.scratchpad_service.get_ticket(scratchpad_id)
            if ticket:
                tw.update_tab_title(
                    index=idx,
                    ticket_number=ticket.get("ticket_number", ""),
                    client_name=ticket.get("client_name", ""),
                    title=ticket.get("title", ""),
                    elapsed_seconds=elapsed_seconds,
                )

    def _on_checklist_stats_changed(self, scratchpad_id: int, completed: int, total: int) -> None:
        """Updates the tab badge and tooltip whenever checklist items are added, removed, or toggled."""
        editor, tw, idx = self._find_editor_by_id(scratchpad_id)
        if editor and tw:
            ticket = self.scratchpad_service.get_ticket(scratchpad_id)
            if ticket:
                elapsed = ticket.get("elapsed_seconds", 0) or 0
                if self.toolbar.stopwatch.current_scratchpad_id == scratchpad_id:
                    elapsed = self.toolbar.stopwatch.elapsed_seconds
                tw.update_tab_title(
                    index=idx,
                    ticket_number=ticket.get("ticket_number", ""),
                    client_name=ticket.get("client_name", ""),
                    title=ticket.get("title", ""),
                    elapsed_seconds=elapsed,
                    checklist_progress=(completed, total),
                )

    def _on_editor_focused(self, scratchpad_id: int) -> None:
        """Updates active editor in toolbar, synchronizes stopwatch, and updates status info when focus enters editor."""
        editor, tw, idx = self._find_editor_by_id(scratchpad_id)
        if not editor:
            return

        if self.is_m365_workspace or self._workspace_switching:
            return
        self._logical_active_scratchpad_id = scratchpad_id
        self.toolbar.set_active_editor(editor)
        restore_ticket = self._workspace_restore_ticket
        self._workspace_restore_ticket = None
        if restore_ticket == scratchpad_id and self.toolbar.stopwatch.current_scratchpad_id == scratchpad_id:
            return
        ticket = self.scratchpad_service.get_ticket(scratchpad_id)
        if ticket:
            t_num = ticket.get("ticket_number", "")
            client = ticket.get("client_name", "")
            title = ticket.get("title", "")
            self.lbl_active_info.setText(f"Active Ticket: #{t_num} | Client: {client or 'N/A'} | Subject: {title or 'N/A'}")
            elapsed = ticket.get("elapsed_seconds", 0) or 0
            self.toolbar.stopwatch.load_scratchpad(
                scratchpad_id=scratchpad_id,
                elapsed_seconds=elapsed,
                auto_start=True,
            )

    def _on_current_tab_changed(self, index: int) -> None:
        """Updates active editor in toolbar and synchronizes stopwatch on primary tab change."""
        self.flush_all_saves()
        if not getattr(self, "_restoring_workspace", False):
            self._save_session_state()
        editor = self.tab_widget.get_editor_at(index)
        if editor:
            self._on_editor_focused(editor.scratchpad_id)
        else:
            self.toolbar.set_active_editor(None)
            self.lbl_active_info.setText("")
            self.toolbar.stopwatch.pause_timer()

        if getattr(self, "is_mini_hud", False):
            t_label = ""
            if editor:
                ticket = self.scratchpad_service.get_ticket(editor.scratchpad_id)
                if ticket:
                    t_num = ticket.get("ticket_number", "")
                    client = ticket.get("client_name", "")
                    t_label = f" — #{t_num}" + (f" ({client})" if client else "")
            self.setWindowTitle(f"📌 [HUD] {APP_NAME}{t_label}")

    def _on_tab_double_clicked(self, index: int) -> None:
        """Opens modal dialog to edit ticket metadata."""
        editor = self.tab_widget.get_editor_at(index)
        if not editor:
            return

        ticket = self.scratchpad_service.get_ticket(editor.scratchpad_id) or {}
        dlg = EditTicketDialog(
            ticket_number=ticket.get("ticket_number", ""),
            client_name=ticket.get("client_name", ""),
            title=ticket.get("title", ""),
            parent=self,
        )
        if dlg.exec():
            data = dlg.get_data()
            self.scratchpad_service.update_metadata(
                scratchpad_id=editor.scratchpad_id,
                ticket_number=data["ticket_number"],
                client_name=data["client_name"],
                title=data["title"],
            )

            # Preserve elapsed seconds in updated tab title
            elapsed = 0
            if self.toolbar.stopwatch.current_scratchpad_id == editor.scratchpad_id:
                elapsed = self.toolbar.stopwatch.elapsed_seconds
            else:
                elapsed = ticket.get("elapsed_seconds", 0) or 0

            # Update tab title (preserving checklist badge and progress)
            self.tab_widget.update_tab_title(
                index=index,
                ticket_number=data["ticket_number"],
                client_name=data["client_name"],
                title=data["title"],
                elapsed_seconds=elapsed,
            )
            self._on_current_tab_changed(index)

    def _close_current_tab(self) -> None:
        idx = self.tab_widget.currentIndex()
        if idx >= 0:
            self._on_tab_close_requested(idx)

    def _on_tab_close_requested(self, index: int) -> None:
        """Handles tab closure by checking user preference (prompt vs direct archive)."""
        editor = self.tab_widget.get_editor_at(index)
        if not editor:
            return

        close_pref = self.session_service.get_setting("close_tab_action", "prompt")
        if close_pref == "archive":
            self._archive_tab(index)
            return

        ticket = self.scratchpad_service.get_ticket(editor.scratchpad_id) or {}
        t_label = f"#{ticket.get('ticket_number', '')} {ticket.get('client_name', '')}"

        msg_box = QMessageBox(self)
        msg_box.setWindowTitle("Close Ticket Scratchpad")
        msg_box.setText(f"How would you like to handle ticket {t_label}?")
        btn_archive = msg_box.addButton("Archive to History", QMessageBox.AcceptRole)
        btn_delete = msg_box.addButton("Delete Permanently", QMessageBox.DestructiveRole)
        btn_cancel = msg_box.addButton("Cancel", QMessageBox.RejectRole)
        msg_box.setDefaultButton(btn_archive)

        msg_box.exec()
        clicked = msg_box.clickedButton()

        if clicked == btn_archive:
            self._archive_tab(index)
        elif clicked == btn_delete:
            self.scratchpad_service.delete_ticket_permanently(editor.scratchpad_id)
            self._remove_tab(index, editor.scratchpad_id)
            self.history_drawer.refresh_list()

    def _switch_tab_relative(self, delta: int) -> None:
        """Switches active tab to next or previous (Ctrl+Tab / Ctrl+PageDown)."""
        active_editor = self._get_active_editor()
        tw = self.tab_widget
        if active_editor:
            _, found_tw, _ = self._find_editor_by_id(active_editor.scratchpad_id)
            if found_tw:
                tw = found_tw
        elif self.secondary_tab_widget.isVisible() and self.secondary_tab_widget.hasFocus():
            tw = self.secondary_tab_widget

        count = tw.count()
        if count > 1:
            new_idx = (tw.currentIndex() + delta) % count
            tw.setCurrentIndex(new_idx)
            editor = tw.get_current_editor()
            if editor:
                editor.setFocus()

    def _move_active_tab_relative(self, delta: int) -> None:
        """Slides / moves the active tab left or right (Ctrl+Shift+PageDown / PageUp)."""
        active_editor = self._get_active_editor()
        tw = self.tab_widget
        if active_editor:
            _, found_tw, _ = self._find_editor_by_id(active_editor.scratchpad_id)
            if found_tw:
                tw = found_tw
        elif self.secondary_tab_widget.isVisible() and self.secondary_tab_widget.hasFocus():
            tw = self.secondary_tab_widget

        current = tw.currentIndex()
        target = current + delta
        if 0 <= target < tw.count():
            tw.tabBar().moveTab(current, target)
            tw.setCurrentIndex(target)
            editor = tw.get_current_editor()
            if editor:
                editor.setFocus()
            self._on_tabs_reordered()

    def _select_tab_index(self, index: int) -> None:
        """Selects a tab by direct index (Ctrl+1..Ctrl+9)."""
        if 0 <= index < self.tab_widget.count():
            self.tab_widget.setCurrentIndex(index)
            editor = self.tab_widget.get_current_editor()
            if editor:
                editor.setFocus()

    def _restore_last_closed_tab(self) -> None:
        """Restores the most recently archived ticket (Ctrl+Shift+T)."""
        archived = self.scratchpad_service.get_archived_tickets(limit=1)
        if archived:
            self._on_restore_ticket(archived[0]["id"])
            self.status_bar.showMessage(f"✓ Restored ticket #{archived[0].get('ticket_number')}", 3000)
        else:
            self.status_bar.showMessage("No archived tickets available to restore", 2500)

    def _on_opacity_changed(self, value: int) -> None:
        """Updates window opacity in real time from slider (60% to 100%)."""
        clamped = max(60, min(100, value))
        self.setWindowOpacity(clamped / 100.0)

    def _open_settings_dialog(self) -> None:
        """Opens preferences dialog and applies updated settings."""
        current_settings = self.session_service.get_settings()
        dlg = SettingsDialog(current_settings, self)
        if dlg.exec():
            new_settings = dlg.get_settings()
            self.session_service.save_settings(new_settings)
            if "window_opacity" in new_settings:
                val = int(new_settings["window_opacity"])
                self.setWindowOpacity(val / 100.0)
                self.toolbar.set_opacity_value(val)
            if "auto_save_delay_ms" in new_settings:
                new_delay = int(new_settings["auto_save_delay_ms"])
                for debouncer in self._debounce_timers.values():
                    debouncer.delay_ms = new_delay
            self.status_bar.showMessage("✓ Preferences saved", 3000)

    def _remove_tab(self, index: int, scratchpad_id: int) -> None:
        if self.toolbar.stopwatch.current_scratchpad_id == scratchpad_id:
            self.toolbar.stopwatch.pause_timer()

        if scratchpad_id in self._debounce_timers:
            self._debounce_timers[scratchpad_id].cancel()
            del self._debounce_timers[scratchpad_id]

        self.tab_widget.removeTab(index)

        # Update remaining tab orders
        self._on_tabs_reordered()

        # If all tabs are closed, create a fresh scratchpad
        if self.tab_widget.count() == 0:
            self.create_new_tab()

    def _on_tabs_reordered(self) -> None:
        """Persists new tab order after drag and drop across primary and secondary panes."""
        orders = []
        order_idx = 0
        for tw in (self.tab_widget, self.secondary_tab_widget):
            for i in range(tw.count()):
                editor = tw.get_editor_at(i)
                if editor:
                    orders.append((editor.scratchpad_id, order_idx))
                    order_idx += 1
        if orders:
            self.scratchpad_service.update_tab_orders(orders)
        self._save_session_state()

    def _on_restore_ticket(self, scratchpad_id: int) -> None:
        """Restores an archived ticket as an active tab in the primary pane."""
        # Check if already open in primary or secondary
        ed, tw, idx = self._find_editor_by_id(scratchpad_id)
        if tw and idx >= 0:
            tw.setCurrentIndex(idx)
            if ed:
                ed.setFocus()
            return

        ticket = self.scratchpad_service.restore_ticket(scratchpad_id)
        if ticket:
            editor = self._create_editor(ticket["id"], ticket.get("content_html", ""))
            idx = self.tab_widget.add_ticket_tab(ticket, editor)
            self.tab_widget.setCurrentIndex(idx)
            editor.setFocus()
            self._on_tabs_reordered()
            self.history_drawer.refresh_list()

    def _on_history_split_restore(self, scratchpad_id: int) -> None:
        """Restores an archived ticket directly into the secondary pane in Split View."""
        self.open_split_view(target_scratchpad_id=scratchpad_id)
        self.history_drawer.refresh_list()

    def _on_delete_ticket(self, scratchpad_id: int) -> None:
        """Permanently deletes a ticket from history."""
        self.scratchpad_service.delete_ticket_permanently(scratchpad_id)
        self.history_drawer.refresh_list()

    def _on_insert_image_file(self) -> None:
        """Prompts for an image file and inserts it into current focused editor."""
        editor = self._get_active_editor()
        if not editor:
            return

        file_path, _ = QFileDialog.getOpenFileName(
            self,
            "Select Screenshot or Image",
            "",
            "Images (*.png *.jpg *.jpeg *.bmp *.webp *.gif)",
        )
        if file_path:
            with open(file_path, "rb") as f:
                data = f.read()
            editor.insert_embedded_image(data)

    def _on_skeleton_selected(self, skeleton_name: str) -> None:
        """Inserts selected ticket template into active focused editor."""
        editor = self._get_active_editor()
        if not editor:
            return
        html = self.scratchpad_service.get_skeleton_html(skeleton_name)
        if html:
            editor.textCursor().insertHtml(html)

    def _on_insert_checklist(self) -> None:
        """Inserts an interactive checklist item in the active focused editor."""
        editor = self._get_active_editor()
        if editor:
            editor.insert_checklist_item()

    def _on_copy_formatted_note(self) -> None:
        """Copies the entire active note with rich formatting, colors, and embedded images to clipboard."""
        editor = self._get_active_editor()
        if not editor:
            return

        self._execute_save(editor.scratchpad_id)
        editor.copy_formatted_note()
        ticket = self.scratchpad_service.get_ticket(editor.scratchpad_id) or {}
        t_label = f"#{ticket.get('ticket_number', '')}".strip()
        msg = f"✓ Copied formatted note ({t_label}) with rich text & images to clipboard!" if t_label != "#" else "✓ Copied formatted note with rich text & images to clipboard!"
        self.status_bar.showMessage(msg, 3500)

    def _on_export_note(self) -> None:
        """Copies clean plain text / Markdown note from active editor to clipboard for ticketing tool."""
        editor = self._get_active_editor()
        if not editor:
            return

        # Ensure active changes are saved first
        self._execute_save(editor.scratchpad_id)

        clean_text = self.scratchpad_service.export_as_plain_ticket_note(editor.scratchpad_id)
        QApplication.clipboard().setText(clean_text)
        ticket = self.scratchpad_service.get_ticket(editor.scratchpad_id) or {}
        t_label = f"#{ticket.get('ticket_number', '')}".strip()
        msg = f"✓ Copied clean note ({t_label}) for ticketing system to clipboard!" if t_label != "#" else "✓ Copied clean note for ticketing system to clipboard!"
        self.status_bar.showMessage(msg, 3500)

    def _on_tab_context_menu(self, index: int, global_pos: QPoint) -> None:
        """Displays rich context menu on right-clicking a tab or the primary tab bar."""
        menu = QMenu(self)

        if index >= 0:
            editor = self.tab_widget.get_editor_at(index)
            ticket = self.scratchpad_service.get_ticket(editor.scratchpad_id) if editor else None
            t_num = ticket.get("ticket_number", "") if ticket else ""

            # Rename / Edit Ticket Metadata
            act_rename = menu.addAction(f"✏️ Rename Ticket #{t_num}...")
            act_rename.triggered.connect(lambda: self._on_tab_double_clicked(index))

            # Duplicate Note
            act_duplicate = menu.addAction("📋 Duplicate Ticket Note")
            act_duplicate.triggered.connect(lambda: self._duplicate_tab(index))

            # Copy Formatted Note (Rich Text & Images)
            act_copy_rich = menu.addAction("📋 Copy Formatted Note (Rich Text & Images)")
            act_copy_rich.triggered.connect(lambda: self._copy_tab_formatted_note_from(self.tab_widget, index))

            # Copy Clean Note for Ticketing Tool
            act_copy = menu.addAction("📤 Copy Clean Note for Ticket Tool")
            act_copy.triggered.connect(lambda: self._copy_tab_note(index))

            menu.addSeparator()

            # Split view toggle / move action
            if self.secondary_tab_widget.isVisible():
                act_move = menu.addAction("◫ Move to Split Sidebar (Left Pane)")
                act_move.triggered.connect(lambda: self._move_tab_between_panes(self.tab_widget, self.secondary_tab_widget, index))
            else:
                act_split = menu.addAction("◫ Open in Split Sidebar (Alt+Z)")
                act_split.triggered.connect(lambda: self._open_tab_in_split_view(index))

            menu.addSeparator()

            # Archive Ticket
            act_archive = menu.addAction("📦 Archive to History")
            act_archive.triggered.connect(lambda: self._archive_tab(index))

            # Close Tab
            act_close = menu.addAction("✕ Close Tab")
            act_close.triggered.connect(lambda: self._on_tab_close_requested(index))

            if self.tab_widget.count() > 1:
                act_close_others = menu.addAction("Close Other Tabs")
                act_close_others.triggered.connect(lambda: self._close_other_tabs(index))

            menu.addSeparator()

        # Always offer quick tab creation
        act_new = menu.addAction("➕ New Ticket Tab (Ctrl+T)")
        act_new.triggered.connect(self.create_new_tab)

        menu.exec(global_pos)

    def _open_tab_in_split_view(self, index: int) -> None:
        """Opens the specified primary tab in the secondary pane of split view."""
        editor = self.tab_widget.get_editor_at(index)
        if not editor:
            return
        self.open_split_view(target_scratchpad_id=editor.scratchpad_id)

    def _on_secondary_tab_context_menu(self, index: int, global_pos: QPoint) -> None:
        """Displays context menu for tabs in secondary (split) pane."""
        menu = QMenu(self)

        if index >= 0:
            editor = self.secondary_tab_widget.get_editor_at(index)
            ticket = self.scratchpad_service.get_ticket(editor.scratchpad_id) if editor else None
            t_num = ticket.get("ticket_number", "") if ticket else ""

            act_rename = menu.addAction(f"✏️ Rename Ticket #{t_num}...")
            act_rename.triggered.connect(lambda: self._on_secondary_tab_double_clicked(index))

            act_move = menu.addAction("◫ Move to Main Window (Right Pane)")
            act_move.triggered.connect(lambda: self._move_tab_between_panes(self.secondary_tab_widget, self.tab_widget, index))

            # Copy Formatted Note (Rich Text & Images)
            act_copy_rich = menu.addAction("📋 Copy Formatted Note (Rich Text & Images)")
            act_copy_rich.triggered.connect(lambda: self._copy_tab_formatted_note_from(self.secondary_tab_widget, index))

            act_copy = menu.addAction("📤 Copy Clean Note for Ticket Tool")
            act_copy.triggered.connect(lambda: self._copy_tab_note_from(self.secondary_tab_widget, index))

            menu.addSeparator()

            act_archive = menu.addAction("📦 Archive to History")
            act_archive.triggered.connect(lambda: self._archive_secondary_tab(index))

            act_close = menu.addAction("✕ Close Tab")
            act_close.triggered.connect(lambda: self._on_secondary_tab_close_requested(index))

            menu.addSeparator()

        act_new = menu.addAction("➕ New Ticket Tab")
        act_new.triggered.connect(self._create_new_secondary_tab)

        act_close_split = menu.addAction("◫ Close Split Sidebar (Alt+Z)")
        act_close_split.triggered.connect(self.close_split_view)

        menu.exec(global_pos)

    def _on_secondary_tab_double_clicked(self, index: int) -> None:
        """Opens modal dialog to edit ticket metadata in secondary pane."""
        editor = self.secondary_tab_widget.get_editor_at(index)
        if not editor:
            return

        ticket = self.scratchpad_service.get_ticket(editor.scratchpad_id) or {}
        dlg = EditTicketDialog(
            ticket_number=ticket.get("ticket_number", ""),
            client_name=ticket.get("client_name", ""),
            title=ticket.get("title", ""),
            parent=self,
        )
        if dlg.exec():
            data = dlg.get_data()
            self.scratchpad_service.update_metadata(
                scratchpad_id=editor.scratchpad_id,
                ticket_number=data["ticket_number"],
                client_name=data["client_name"],
                title=data["title"],
            )

            elapsed = 0
            if self.toolbar.stopwatch.current_scratchpad_id == editor.scratchpad_id:
                elapsed = self.toolbar.stopwatch.elapsed_seconds
            else:
                elapsed = ticket.get("elapsed_seconds", 0) or 0

            self.secondary_tab_widget.update_tab_title(
                index=index,
                ticket_number=data["ticket_number"],
                client_name=data["client_name"],
                title=data["title"],
                elapsed_seconds=elapsed,
            )
            self._on_secondary_tab_changed(index)

    def _on_secondary_tab_changed(self, index: int) -> None:
        """Updates active editor in toolbar and synchronizes stopwatch on secondary tab change."""
        self.flush_all_saves()
        if not getattr(self, "_restoring_workspace", False):
            self._save_session_state()
        editor = self.secondary_tab_widget.get_editor_at(index)
        if editor:
            self._on_editor_focused(editor.scratchpad_id)

    def _on_secondary_tab_close_requested(self, index: int) -> None:
        """Handles closing a tab from the secondary pane."""
        editor = self.secondary_tab_widget.get_editor_at(index)
        if not editor:
            return

        close_pref = self.session_service.get_setting("close_tab_action", "prompt")
        if close_pref == "archive":
            self._archive_secondary_tab(index)
            return

        ticket = self.scratchpad_service.get_ticket(editor.scratchpad_id) or {}
        t_label = f"#{ticket.get('ticket_number', '')} {ticket.get('client_name', '')}"

        msg_box = QMessageBox(self)
        msg_box.setWindowTitle("Close Ticket Scratchpad")
        msg_box.setText(f"How would you like to handle ticket {t_label}?")
        btn_archive = msg_box.addButton("Archive to History", QMessageBox.AcceptRole)
        btn_delete = msg_box.addButton("Delete Permanently", QMessageBox.DestructiveRole)
        btn_cancel = msg_box.addButton("Cancel", QMessageBox.RejectRole)
        msg_box.setDefaultButton(btn_archive)

        msg_box.exec()
        clicked = msg_box.clickedButton()

        if clicked == btn_archive:
            self._archive_secondary_tab(index)
        elif clicked == btn_delete:
            self.scratchpad_service.delete_ticket_permanently(editor.scratchpad_id)
            self._remove_secondary_tab(index, editor.scratchpad_id)
            self.history_drawer.refresh_list()

    def _archive_secondary_tab(self, index: int) -> None:
        """Archives a secondary tab directly without extra prompt."""
        editor = self.secondary_tab_widget.get_editor_at(index)
        if not editor:
            return
        if not self._save_before_archive(editor.scratchpad_id):
            return
        self._remove_secondary_tab(index, editor.scratchpad_id)
        self.history_drawer.refresh_list()
        self.status_bar.showMessage("✓ Ticket archived to History Drawer", 3000)

    def _remove_secondary_tab(self, index: int, scratchpad_id: int) -> None:
        """Removes a tab from the secondary pane and collapses split view if empty."""
        if self.toolbar.stopwatch.current_scratchpad_id == scratchpad_id:
            self.toolbar.stopwatch.pause_timer()

        if scratchpad_id in self._debounce_timers:
            self._debounce_timers[scratchpad_id].cancel()
            del self._debounce_timers[scratchpad_id]

        self.secondary_tab_widget.removeTab(index)
        self._on_tabs_reordered()

        if self.secondary_tab_widget.count() == 0:
            self.close_split_view()

    def _move_tab_between_panes(
        self,
        from_tw: TechPadTabWidget,
        to_tw: TechPadTabWidget,
        index: int,
        target_index: Optional[int] = None,
    ) -> None:
        """Moves a tab from one pane to another without losing state or content."""
        if index < 0 or index >= from_tw.count():
            return
        editor = from_tw.get_editor_at(index)
        if not editor:
            return
        sid = editor.scratchpad_id
        ticket = self.scratchpad_service.get_ticket(sid) or {"id": sid}
        if self.toolbar.stopwatch.current_scratchpad_id == sid:
            ticket["elapsed_seconds"] = self.toolbar.stopwatch.elapsed_seconds

        from_tw.removeTab(index)
        if target_index is not None and 0 <= target_index <= to_tw.count():
            new_idx = to_tw.insert_ticket_tab(target_index, ticket, editor)
        else:
            new_idx = to_tw.add_ticket_tab(ticket, editor)

        to_tw.setCurrentIndex(new_idx)
        editor.setFocus()
        self._on_editor_focused(sid)
        self._on_tabs_reordered()

        # If primary became empty, create a new tab; if secondary became empty, close split view
        if from_tw == self.tab_widget and self.tab_widget.count() == 0:
            self.create_new_tab()
        elif from_tw == self.secondary_tab_widget and self.secondary_tab_widget.count() == 0:
            self.close_split_view()

    def _handle_tab_cross_drag_move(self, from_tw: TechPadTabWidget, source_idx: int, global_pos: QPoint) -> None:
        """Auto-scrolls the destination tab bar when hovering near its edges during cross-pane drag exchange."""
        if not self.secondary_tab_widget.isVisible():
            return

        to_tw = self.tab_widget if from_tw == self.secondary_tab_widget else self.secondary_tab_widget
        to_bar = to_tw.tabBar()

        pos_in_tw = to_tw.mapFromGlobal(global_pos)
        # Check if cursor is roughly within the destination tab bar / header row height
        if -25 <= pos_in_tw.y() <= 45:
            scroll_margin = 85
            if -25 <= pos_in_tw.x() <= scroll_margin:
                to_bar._start_auto_scroll(-1, is_cross_drag=True)
            elif to_tw.width() - scroll_margin <= pos_in_tw.x() <= to_tw.width() + 25:
                to_bar._start_auto_scroll(1, is_cross_drag=True)
            else:
                to_bar._stop_auto_scroll()
        else:
            to_bar._stop_auto_scroll()

    def _handle_tab_cross_drop(self, from_tw: TechPadTabWidget, source_idx: int, global_pos: QPoint) -> None:
        """Handles dropping a dragged tab into the other split view pane or triggering split view."""
        self.tab_widget.tabBar()._stop_auto_scroll()
        self.secondary_tab_widget.tabBar()._stop_auto_scroll()
        if source_idx < 0 or source_idx >= from_tw.count():
            return

        # 1. First resolve destination pane geometrically using global coordinates
        to_tw = None
        if self.secondary_tab_widget.isVisible():
            sec_tl = self.secondary_tab_widget.mapToGlobal(QPoint(0, 0))
            if (
                sec_tl.x() - 10 <= global_pos.x() <= sec_tl.x() + self.secondary_tab_widget.width() + 5
                and sec_tl.y() - 25 <= global_pos.y() <= sec_tl.y() + self.secondary_tab_widget.height() + 25
            ):
                to_tw = self.secondary_tab_widget

        if to_tw is None and self.tab_widget.isVisible():
            tab_tl = self.tab_widget.mapToGlobal(QPoint(0, 0))
            if (
                tab_tl.x() - 5 <= global_pos.x() <= tab_tl.x() + self.tab_widget.width() + 10
                and tab_tl.y() - 25 <= global_pos.y() <= tab_tl.y() + self.tab_widget.height() + 25
            ):
                to_tw = self.tab_widget

        # 2. Fallback to widgetAt parent hierarchy check
        if to_tw is None:
            target_widget = QApplication.widgetAt(global_pos)
            curr = target_widget
            while curr:
                if curr == self.tab_widget:
                    to_tw = self.tab_widget
                    break
                elif curr == self.secondary_tab_widget:
                    to_tw = self.secondary_tab_widget
                    break
                curr = curr.parent()

        # If Split View is not open, check if user dragged tab to the workspace splitter area to open Split View
        if not self.secondary_tab_widget.isVisible():
            splitter_global = self.workspace_splitter.mapToGlobal(QPoint(0, 0))
            splitter_rect = self.workspace_splitter.rect()
            if (
                splitter_global.x() <= global_pos.x() <= splitter_global.x() + splitter_rect.width()
                and splitter_global.y() <= global_pos.y() <= splitter_global.y() + splitter_rect.height()
            ):
                editor = from_tw.get_editor_at(source_idx)
                if editor:
                    self.open_split_view(target_scratchpad_id=editor.scratchpad_id)
            return

        # If dropped over the other tab widget pane:
        if to_tw and to_tw != from_tw:
            target_index = self._calculate_tab_insert_index(to_tw, global_pos)
            self._move_tab_between_panes(from_tw, to_tw, source_idx, target_index=target_index)

    def _calculate_tab_insert_index(self, target_tw: TechPadTabWidget, global_pos: QPoint) -> int:
        """Determines the target insert index in the destination tab widget based on drop coordinates."""
        bar = target_tw.tabBar()
        pos_in_bar = bar.mapFromGlobal(global_pos)
        pos_in_tw = target_tw.mapFromGlobal(global_pos)

        # Check if cursor is roughly within tab bar vertical bounds (+/- 35px)
        if -25 <= pos_in_bar.y() <= bar.height() + 35 or -25 <= pos_in_tw.y() <= 45:
            idx = bar.tabAt(pos_in_bar)
            if idx >= 0:
                rect = bar.tabRect(idx)
                if pos_in_bar.x() > rect.center().x():
                    return idx + 1
                return idx
            for i in range(target_tw.count()):
                r = bar.tabRect(i)
                if r.left() <= pos_in_bar.x() <= r.right():
                    if pos_in_bar.x() > r.center().x():
                        return i + 1
                    return i
            # If to the left of all tabs in the bar or over left arrow
            if pos_in_bar.x() <= 0 or pos_in_tw.x() <= 40:
                return 0
            # If to the right of all tabs in the bar
            if pos_in_bar.x() > 0 or pos_in_tw.x() >= target_tw.width() - 40:
                return target_tw.count()

        # Dropped into the editor area: insert as active tab at the end
        return target_tw.count()

    def _toggle_split_view(self) -> None:
        """Toggles side-by-side split view mode."""
        if self.is_split_view_active:
            self.close_split_view()
        else:
            self.open_split_view()

    def open_split_view(self, target_scratchpad_id: Optional[int] = None) -> None:
        """Enables split view mode and restores the Split sidebar."""
        self.flush_all_saves()
        self._user_split_view_active = True

        if self.secondary_tab_widget.count() > 0:
            if target_scratchpad_id is not None:
                for i in range(self.secondary_tab_widget.count()):
                    ed = self.secondary_tab_widget.get_editor_at(i)
                    if ed and ed.scratchpad_id == target_scratchpad_id:
                        self.secondary_tab_widget.setCurrentIndex(i)
                        break
                else:
                    for i in range(self.tab_widget.count()):
                        ed = self.tab_widget.get_editor_at(i)
                        if ed and ed.scratchpad_id == target_scratchpad_id:
                            self._move_tab_between_panes(self.tab_widget, self.secondary_tab_widget, i)
                            break
        else:
            if target_scratchpad_id is not None:
                moved = False
                for i in range(self.tab_widget.count()):
                    ed = self.tab_widget.get_editor_at(i)
                    if ed and ed.scratchpad_id == target_scratchpad_id:
                        self._move_tab_between_panes(self.tab_widget, self.secondary_tab_widget, i)
                        moved = True
                        break
                if not moved:
                    ticket = self.scratchpad_service.get_ticket(target_scratchpad_id)
                    if ticket:
                        if ticket.get("status") == "archived":
                            ticket = self.scratchpad_service.restore_ticket(target_scratchpad_id)
                        editor = self._create_editor(ticket["id"], ticket.get("content_html", ""))
                        self.secondary_tab_widget.add_ticket_tab(ticket, editor)
            elif self.tab_widget.count() > 1:
                curr_idx = self.tab_widget.currentIndex()
                move_idx = curr_idx + 1 if curr_idx + 1 < self.tab_widget.count() else curr_idx - 1
                self._move_tab_between_panes(self.tab_widget, self.secondary_tab_widget, move_idx)
            else:
                self._create_new_secondary_tab()

        if self.width() < 750:
            self._split_auto_single_pane = True
            self._compact_active_pane = 0
            self.secondary_tab_widget.show()
            self.tab_widget.hide()
            if hasattr(self, "btn_switch_split_pane"):
                self.btn_switch_split_pane.setVisible(True)
                self.btn_switch_split_pane.setText("⇋ Pane 1/2 (Alt+Shift+Z)")
        else:
            self._split_auto_single_pane = False
            self.secondary_tab_widget.show()
            self.tab_widget.show()
            if hasattr(self, "btn_switch_split_pane"):
                self.btn_switch_split_pane.setVisible(False)
            total_w = self.workspace_splitter.width() or self.width() or 1000
            saved_sizes = getattr(self, "_saved_splitter_sizes", None)
            if saved_sizes and len(saved_sizes) == 2 and sum(saved_sizes) > 0:
                self.workspace_splitter.setSizes(saved_sizes)
            else:
                sidebar_w = min(400, max(250, total_w // 3))
                self.workspace_splitter.setSizes([sidebar_w, total_w - sidebar_w])

        self.toolbar.btn_split.setChecked(True)
        self.btn_toggle_split.setText("◫ Single (Alt+Z)")

        sec_editor = self.secondary_tab_widget.get_current_editor()
        if sec_editor:
            sec_editor.setFocus()
            self._on_editor_focused(sec_editor.scratchpad_id)

        self._on_tabs_reordered()

    def close_split_view(self) -> None:
        """Hides secondary (split) pane without moving or evicting its tabs."""
        self.flush_all_saves()
        self._user_split_view_active = False
        self._split_auto_single_pane = False
        self._compact_active_pane = 0
        if hasattr(self, "btn_switch_split_pane"):
            self.btn_switch_split_pane.setVisible(False)

        # Do NOT move or consolidate secondary tabs into primary tab widget!
        # Secondary tabs remain safely in secondary_tab_widget so their placement is preserved.
        self.secondary_tab_widget.hide()
        self.tab_widget.show()

        if hasattr(self, "toolbar") and hasattr(self.toolbar, "btn_split"):
            self.toolbar.btn_split.setChecked(False)
        if hasattr(self, "btn_toggle_split"):
            self.btn_toggle_split.setText("◫ Split (Alt+Z)")

        prim_editor = self.tab_widget.get_current_editor()
        if prim_editor:
            prim_editor.setFocus()
            self._on_editor_focused(prim_editor.scratchpad_id)

        self._save_session_state()

    @property
    def is_mini_hud(self) -> bool:
        """Returns True if the application is currently in Always-on-Top Mini-HUD mode."""
        return getattr(self, "_is_mini_hud", False)

    def toggle_mini_hud_mode(self) -> None:
        """Toggles between normal workspace and Always-on-Top Mini-HUD mode."""
        if self.is_mini_hud:
            self._disable_mini_hud()
        else:
            self._enable_mini_hud()

    def _enable_mini_hud(self) -> None:
        """Enables Always-on-Top Mini-HUD mode: compact floating HUD pinned to top."""
        self.flush_all_saves()

        # 1. Preserve normal workspace state
        self._saved_normal_geometry = self.saveGeometry()
        self._saved_row1_visible = self.toolbar.isVisible()
        self._saved_drawer_visible = self.history_drawer.isVisible()
        self._saved_split_visible = self.secondary_tab_widget.isVisible()

        self._is_mini_hud = True

        # 2. Hide bulky UI elements to maximize note space
        self.toolbar.hide()
        if self._saved_drawer_visible:
            self.history_drawer.hide()

        # 3. Ensure an editor pane remains visible in Mini-HUD
        if self.is_m365_workspace:
            self._saved_split_active = getattr(self, "_notes_split_active", False)
            self._saved_split_visible = self._notes_visibility.get(self.secondary_tab_widget, False)
        else:
            self._saved_split_active = self.is_split_view_active
            self._saved_split_visible = self.secondary_tab_widget.isVisible()
        self._saved_compact_pane = getattr(self, "_compact_active_pane", 0)
        self.secondary_tab_widget.hide()
        self.tab_widget.show()
        hud_editor = self.tab_widget.get_current_editor()

        # 4. Ensure left-side status bar buttons (HUD, M365 Launcher / T-Notes, Split, History) remain visible at same left emplacement
        if hasattr(self, "btn_status_hud"):
            self.btn_status_hud.setText("📌 Normal (Alt+T)")
            self.btn_status_hud.setVisible(True)
        if hasattr(self, "btn_m365"):
            if self.is_m365_workspace:
                self.btn_m365.setText("T-Notes")
                self.btn_m365.setToolTip("Return to T-Notes workspace (Alt+F8)")
                self.btn_m365.setAccessibleName("T-Notes")
            else:
                self.btn_m365.setText("M365 Launcher")
                self.btn_m365.setToolTip("Open the M365 Launcher workspace in this window (Alt+F8)")
                self.btn_m365.setAccessibleName("M365 Launcher")
            self.btn_m365.setEnabled(True)
            self.btn_m365.setVisible(True)
        self._update_module_status_bar_buttons()

        # 5. Show HUD tab navigation arrows on tabs bar if in Notes workspace
        if hasattr(self, "tab_widget"):
            self.tab_widget.set_hud_nav_arrows_visible(not self.is_m365_workspace)

        # 6. Enable Always-on-Top and position as right sidebar with longer height
        self.setMinimumSize(340, 200)
        self.setWindowFlag(Qt.WindowStaysOnTopHint, True)
        self.show()

        screen = self.screen() or QGuiApplication.primaryScreen()
        if screen:
            avail = screen.availableGeometry()
            frame = self.frameGeometry()
            geo = self.geometry()
            extra_h = max(0, frame.height() - geo.height())
            title_h = max(0, geo.y() - frame.y())
            if title_h == 0 and extra_h > 0:
                title_h = extra_h

            sidebar_width = min(440, avail.width())
            sidebar_height = max(200, avail.height() - extra_h)
            sidebar_x = avail.x() + avail.width() - sidebar_width
            sidebar_y = avail.y() + title_h
            self.setMaximumHeight(avail.height() - extra_h)
            self.setGeometry(sidebar_x, sidebar_y, sidebar_width, sidebar_height)
        else:
            self.resize(440, 700)

        # 7. Update HUD window title with active ticket info or M365
        if self.is_m365_workspace:
            self.setWindowTitle(f"📌 [HUD] {APP_NAME} — M365 Launcher")
        else:
            t_label = ""
            if hud_editor:
                ticket = self.scratchpad_service.get_ticket(hud_editor.scratchpad_id)
                if ticket:
                    t_num = ticket.get("ticket_number", "")
                    client = ticket.get("client_name", "")
                    t_label = f" — #{t_num}" + (f" ({client})" if client else "")
            self.setWindowTitle(f"📌 [HUD] {APP_NAME}{t_label}")

        # 8. Update UI controls & status bar feedback
        self.toolbar.set_mini_hud_state(True)
        if hasattr(self, "btn_status_hud"):
            self.btn_status_hud.setText("📌 Normal (Alt+T)")
            self.btn_status_hud.show()
        self.status_bar.showMessage("📌 Mini-HUD Mode Active (Always-on-Top) — Press Alt+T to restore", 3500)

        self.show()
        if self.is_m365_workspace:
            self._activate_and_focus(self.m365_workspace.back_button)
        else:
            self._activate_and_focus(hud_editor)

    def _disable_mini_hud(self) -> None:
        """Disables Mini-HUD mode and restores standard full workspace geometry."""
        self.flush_all_saves()

        self._is_mini_hud = False

        # 1. Disable Always-on-Top and restore workspace-specific minimum size
        self.setWindowFlag(Qt.WindowStaysOnTopHint, False)
        self.setMaximumHeight(16777215)
        if self.is_m365_workspace:
            self.setMinimumSize(640, 380)
        else:
            self.setMinimumSize(660, 400)

        # 2. Restore previous window geometry within available screen bounds
        if getattr(self, "_saved_normal_geometry", None):
            self.restoreGeometry(self._saved_normal_geometry)
            self._clamp_geometry_to_screen()

        # 3. Restore visibility of toolbar, drawer, and split view
        if not self.is_m365_workspace:
            if getattr(self, "_saved_row1_visible", True):
                self.toolbar.show()
            if getattr(self, "_saved_row2_visible", True):
                self.toolbar.secondary_toolbar.show()
            if getattr(self, "_saved_drawer_visible", False):
                if not self.history_auto_collapsed:
                    self.history_drawer.show()

        # Ensure left-side status bar buttons remain visible in normal mode
        if hasattr(self, "btn_status_hud"):
            self.btn_status_hud.setText("📌 HUD (Alt+T)")
            self.btn_status_hud.setVisible(True)
        if hasattr(self, "btn_m365"):
            if self.is_m365_workspace:
                self.btn_m365.setText("T-Notes")
                self.btn_m365.setToolTip("Return to T-Notes workspace (Alt+F8)")
                self.btn_m365.setAccessibleName("T-Notes")
            else:
                self.btn_m365.setText("M365 Launcher")
                self.btn_m365.setToolTip("Open the M365 Launcher workspace in this window (Alt+F8)")
                self.btn_m365.setAccessibleName("M365 Launcher")
            self.btn_m365.setEnabled(True)
            self.btn_m365.setVisible(True)
        self._update_module_status_bar_buttons()

        # Hide HUD tab navigation arrows on tabs bar
        if hasattr(self, "tab_widget"):
            self.tab_widget.set_hud_nav_arrows_visible(False)

        if not self.is_m365_workspace:
            # Restore Split View
            if getattr(self, "_saved_split_active", False) or getattr(self, "_saved_split_visible", False):
                self._user_split_view_active = True
                if self.width() < 750:
                    self._split_auto_single_pane = True
                    if getattr(self, "_saved_compact_pane", 0) == 1:
                        self.tab_widget.hide()
                        self.secondary_tab_widget.show()
                        self._compact_active_pane = 1
                    else:
                        self.secondary_tab_widget.hide()
                        self.tab_widget.show()
                        self._compact_active_pane = 0
                    if hasattr(self, "btn_switch_split_pane"):
                        self.btn_switch_split_pane.setVisible(True)
                        self.btn_switch_split_pane.setText(f"⇋ Pane {self._compact_active_pane + 1}/2 (Alt+Shift+Z)")
                else:
                    self._split_auto_single_pane = False
                    self.tab_widget.show()
                    self.secondary_tab_widget.show()
                    if hasattr(self, "btn_switch_split_pane"):
                        self.btn_switch_split_pane.setVisible(False)
            else:
                self._user_split_view_active = False
                self._split_auto_single_pane = False
                self.tab_widget.show()
                self.secondary_tab_widget.hide()
                if hasattr(self, "btn_switch_split_pane"):
                    self.btn_switch_split_pane.setVisible(False)
            self._check_responsive_layout(self.width())

        # 4. Restore window title and UI controls
        if not self.is_m365_workspace:
            self.setWindowTitle(f"{APP_NAME} v{APP_VERSION} — Technician Scratchpad")
        else:
            self.setWindowTitle(f"{APP_NAME} v{APP_VERSION} — M365 Launcher")
        self.toolbar.set_mini_hud_state(False)
        if hasattr(self, "btn_status_hud"):
            self.btn_status_hud.setText("📌 HUD (Alt+T)")
            self.btn_status_hud.show()
        self.status_bar.showMessage("✓ Restored Normal Workspace", 3000)

        self.show()
        self._activate_and_focus(self._get_active_editor())

    def _duplicate_tab(self, index: int) -> None:
        """Duplicates a ticket scratchpad and its embedded images."""
        editor = self.tab_widget.get_editor_at(index)
        if not editor:
            return

        self._execute_save(editor.scratchpad_id)
        ticket = self.scratchpad_service.get_ticket(editor.scratchpad_id) or {}
        new_ticket = self.scratchpad_service.create_ticket(
            ticket_number=f"{ticket.get('ticket_number', 'T-100')}-COPY",
            client_name=ticket.get("client_name", ""),
            title=f"Copy of {ticket.get('title', '')}" if ticket.get("title") else "Copied Ticket",
            content_html=editor.toHtml(),
        )

        # Duplicate associated image BLOBs
        images = self.image_service.repo.get_images_for_scratchpad(editor.scratchpad_id)
        for img_name, img_data in images.items():
            self.image_service.repo.save_image(new_ticket["id"], img_name, img_data)

        new_editor = self._create_editor(new_ticket["id"], new_ticket.get("content_html", ""))
        idx = self.tab_widget.add_ticket_tab(new_ticket, new_editor)
        self.tab_widget.setCurrentIndex(idx)
        self._on_tabs_reordered()
        self.status_bar.showMessage(f"✓ Duplicated ticket as #{new_ticket['ticket_number']}", 3000)

    def _save_before_archive(self, scratchpad_id: int) -> bool:
        """Archive only after the live snapshot commits, including idle dirty tickets."""
        try:
            self._execute_save(scratchpad_id)
            if scratchpad_id in self._dirty_scratchpad_ids:
                raise RuntimeError("Ticket remains dirty")
            self.scratchpad_service.archive_ticket(scratchpad_id)
        except Exception:
            self.set_save_status("Save Failed", is_saved=False)
            self.status_bar.showMessage("Save Failed — archive cancelled; note retained. Retry with Ctrl+S, then Archive.", 10000)
            return False
        return True

    def _archive_tab(self, index: int) -> None:
        """Archives a tab directly without extra prompt."""
        editor = self.tab_widget.get_editor_at(index)
        if not editor:
            return
        if not self._save_before_archive(editor.scratchpad_id):
            return
        self._remove_tab(index, editor.scratchpad_id)
        self.history_drawer.refresh_list()
        self.status_bar.showMessage("✓ Ticket archived to History Drawer", 3000)

    def _copy_tab_formatted_note_from(self, tab_widget: TechPadTabWidget, index: int) -> None:
        """Copies the entire note of a specific tab with rich formatting, colors, and embedded images."""
        editor = tab_widget.get_editor_at(index)
        if not editor:
            return
        self._execute_save(editor.scratchpad_id)
        editor.copy_formatted_note()
        self.status_bar.showMessage("✓ Copied formatted note (rich text & images) to clipboard!", 3500)

    def _copy_tab_note(self, index: int) -> None:
        """Copies formatted plain text / Markdown note of a primary tab to clipboard."""
        self._copy_tab_note_from(self.tab_widget, index)

    def _copy_tab_note_from(self, tab_widget: TechPadTabWidget, index: int) -> None:
        """Copies formatted plain text / Markdown note of a specific tab to clipboard."""
        editor = tab_widget.get_editor_at(index)
        if not editor:
            return
        self._execute_save(editor.scratchpad_id)
        clean_text = self.scratchpad_service.export_as_plain_ticket_note(editor.scratchpad_id)
        QApplication.clipboard().setText(clean_text)
        self.status_bar.showMessage("✓ Copied note to clipboard!", 3500)

    def _close_other_tabs(self, keep_index: int) -> None:
        """Closes and archives all open tabs except the selected one."""
        keep_editor = self.tab_widget.get_editor_at(keep_index)
        if not keep_editor:
            return
        keep_id = keep_editor.scratchpad_id

        for i in range(self.tab_widget.count() - 1, -1, -1):
            editor = self.tab_widget.get_editor_at(i)
            if editor and editor.scratchpad_id != keep_id:
                if not self._save_before_archive(editor.scratchpad_id):
                    self.history_drawer.refresh_list()
                    return
                self._remove_tab(i, editor.scratchpad_id)

        self.history_drawer.refresh_list()
        self.status_bar.showMessage("✓ Closed and archived other tabs", 3000)

    def _toggle_history_drawer(self) -> None:
        if self.history_drawer.isVisible():
            self._user_history_drawer_open = False
            self.history_auto_collapsed = False
            self.history_drawer.hide()
        else:
            self._user_history_drawer_open = True
            self.history_auto_collapsed = False
            self.history_drawer.show()
            if self.history_drawer.width() < 320:
                self.resizeDocks([self.history_drawer], [380], Qt.Horizontal)

    def closeEvent(self, event: QCloseEvent) -> None:
        """Minimizes to system tray if tray icon is active, preserving saves and session state."""
        self._shutdown_accepted = False
        try:
            self.toolbar.stopwatch.save_current_state()
            save_ok = self.flush_all_saves()
        except Exception:
            save_ok = False
        if not save_ok or self._dirty_scratchpad_ids:
            self.status_bar.showMessage("Error: Notes could not be saved. Application remains open to prevent data loss.", 6000)
            self.set_save_status("Save Failed", is_saved=False)
            self._force_quit = False
            event.ignore()
            self.show_notes_workspace()
            self.showNormal()
            self._activate_and_focus(self._get_active_editor())
            self.status_bar.showMessage("Save Failed — application remains open. Retry with Ctrl+S, then Quit.", 10000)
            return

        try:
            if self._force_quit or not (getattr(self, "tray_icon", None) and self.tray_icon.isVisible()):
                self.toolbar.stopwatch.pause_timer()
            # Update tab orders and persist full session state across all panes
            self._on_tabs_reordered()

        except Exception:
            self._force_quit = False
            self.set_save_status("Save Failed", is_saved=False)
            event.ignore()
            self.show_notes_workspace()
            self.showNormal()
            self._activate_and_focus(self._get_active_editor())
            self.status_bar.showMessage("Save Failed — session could not be saved. Retry Ctrl+S, then Quit.", 10000)
            return

        # If system tray is active and not forcing quit, minimize to tray
        if getattr(self, "tray_icon", None) and self.tray_icon.isVisible() and not getattr(self, "_force_quit", False):
            event.ignore()
            self.hide()
            if getattr(self, "_first_minimize_to_tray", True):
                self._first_minimize_to_tray = False
                self.tray_icon.showMessage(
                    f"{APP_NAME} Running in Background",
                    f"{APP_NAME} minimized to system tray.\nPress F8 anytime to show or hide.",
                    QSystemTrayIcon.Information,
                    2500,
                )
        else:
            if hasattr(self, "global_hotkey") and self.global_hotkey:
                self.global_hotkey.unregister()
            if getattr(self, "tray_icon", None):
                self.tray_icon.hide()
            self._shutdown_accepted = True
            event.accept()

    def showEvent(self, event: QShowEvent) -> None:
        super().showEvent(event)
        self._clamp_geometry_to_screen()
        self._check_responsive_layout(self.width())

    def resizeEvent(self, event: QResizeEvent) -> None:
        super().resizeEvent(event)
        if self.is_mini_hud:
            self._clamp_hud_geometry()
        self._check_responsive_layout(self.width())

    def moveEvent(self, event: QMoveEvent) -> None:
        super().moveEvent(event)
        if self.is_mini_hud:
            self._clamp_hud_geometry()

    def _clamp_hud_geometry(self) -> None:
        """Clamps HUD window geometry so the title bar is on-screen and the bottom bar never overlaps the taskbar."""
        if not self.is_mini_hud:
            return
        screen = self.screen() or QGuiApplication.primaryScreen()
        if not screen:
            return
        avail = screen.availableGeometry()
        frame = self.frameGeometry()
        geo = self.geometry()

        title_h = max(0, geo.y() - frame.y())
        extra_h = max(0, frame.height() - geo.height())
        bottom_border = max(0, frame.bottom() - geo.bottom())

        max_client_h = max(self.minimumHeight(), avail.height() - extra_h)
        if self.maximumHeight() != max_client_h:
            self.setMaximumHeight(max_client_h)

        # Ensure title bar is on-screen within available work area
        new_y = max(avail.y() + title_h, geo.y())

        # If window frame bottom extends into or behind the taskbar (avail.bottom()):
        frame_bottom = new_y - title_h + geo.height() + extra_h - 1
        if frame_bottom > avail.bottom():
            allowed_h = max(self.minimumHeight(), avail.bottom() - new_y - bottom_border + 1)
            if new_y + allowed_h + bottom_border - 1 > avail.bottom():
                new_y = max(avail.y() + title_h, avail.bottom() - allowed_h - bottom_border + 1)
            new_h = allowed_h
        else:
            new_h = geo.height()

        if (geo.x(), new_y, geo.width(), new_h) != (geo.x(), geo.y(), geo.width(), geo.height()):
            self.setGeometry(geo.x(), new_y, geo.width(), new_h)
    def switch_compact_split_pane(self) -> None:
        """Toggles displayed pane in compact single-pane Split View mode."""
        if not self.is_split_view_active or not self.split_auto_single_pane:
            return
        if self._compact_active_pane == 0:
            self._compact_active_pane = 1
            self.tab_widget.hide()
            self.secondary_tab_widget.show()
            ed = self.secondary_tab_widget.get_current_editor()
            if ed:
                ed.setFocus()
                self._on_editor_focused(ed.scratchpad_id)
        else:
            self._compact_active_pane = 0
            self.secondary_tab_widget.hide()
            self.tab_widget.show()
            ed = self.tab_widget.get_current_editor()
            if ed:
                ed.setFocus()
                self._on_editor_focused(ed.scratchpad_id)
        self.btn_switch_split_pane.setText(f"⇋ Pane {self._compact_active_pane + 1}/2 (Alt+Shift+Z)")

    def _clamp_geometry_to_screen(self) -> None:
        """Clamps the window geometry to fit within the active screen's available geometry."""
        screen = self.screen() or QGuiApplication.primaryScreen()
        if not screen:
            return
        avail = screen.availableGeometry()
        geo = self.geometry()
        new_w = min(geo.width(), avail.width())
        new_h = min(geo.height(), avail.height())
        max_x = avail.x() + avail.width() - new_w
        max_y = avail.y() + avail.height() - new_h
        new_x = max(avail.x(), min(geo.x(), max_x))
        new_y = max(avail.y(), min(geo.y(), max_y))
        if (new_x, new_y, new_w, new_h) != (geo.x(), geo.y(), geo.width(), geo.height()):
            self.setGeometry(new_x, new_y, new_w, new_h)

    def _check_responsive_layout(self, current_width: int) -> None:
        """Coordinates responsive toolbar, history drawer, and split view layout."""
        if self.is_m365_workspace:
            return
        if hasattr(self, "toolbar"):
            self.toolbar.check_responsive_mode(current_width)
        self._check_responsive_history(current_width)
        self._check_responsive_split(current_width)

    def _check_responsive_history(self, current_width: int) -> None:
        """Temporarily collapses History drawer on narrow viewports to prioritize editor."""
        if self.is_m365_workspace:
            return
        if current_width < 850:
            if self._user_history_drawer_open and not self.history_auto_collapsed:
                self.history_auto_collapsed = True
                self.history_drawer.hide()
        elif current_width >= 900:
            if self.history_auto_collapsed:
                self.history_auto_collapsed = False
                if self._user_history_drawer_open and not self.is_m365_workspace:
                    self.history_drawer.show()

    def _check_responsive_split(self, current_width: int) -> None:
        """Switches between side-by-side and compact single-pane Split View."""
        if not self.is_split_view_active:
            if hasattr(self, "btn_switch_split_pane"):
                self.btn_switch_split_pane.setVisible(False)
            return
        if current_width < 750 and not self.split_auto_single_pane:
            self._saved_splitter_sizes = self.workspace_splitter.sizes()
            self._split_auto_single_pane = True
            ed = self._get_active_editor()
            if ed and self.secondary_tab_widget.indexOf(ed) != -1:
                self._compact_active_pane = 1
                self.tab_widget.hide()
                self.secondary_tab_widget.show()
            else:
                self._compact_active_pane = 0
                self.secondary_tab_widget.hide()
                self.tab_widget.show()
            self.btn_switch_split_pane.setVisible(True)
            self.btn_switch_split_pane.setText(f"⇋ Pane {self._compact_active_pane + 1}/2 (Alt+Shift+Z)")
        elif current_width >= 780 and self.split_auto_single_pane:
            self._split_auto_single_pane = False
            self.tab_widget.show()
            self.secondary_tab_widget.show()
            self.btn_switch_split_pane.setVisible(False)
            if getattr(self, "_saved_splitter_sizes", None):
                self.workspace_splitter.setSizes(self._saved_splitter_sizes)
            else:
                half = max(200, self.workspace_splitter.width() // 2)
                self.workspace_splitter.setSizes([half, half])


