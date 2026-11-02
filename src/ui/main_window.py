"""Main application window for TechPad."""

import ctypes
from pathlib import Path
import sys
from typing import Optional
from PySide6.QtCore import QEvent, QPoint, Qt, QTimer
from PySide6.QtGui import QAction, QCloseEvent, QFont, QKeySequence, QShortcut
from PySide6.QtWidgets import (
    QApplication,
    QFileDialog,
    QLabel,
    QMainWindow,
    QMenu,
    QMessageBox,
    QPushButton,
    QSplitter,
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
        self.setMinimumSize(800, 500)

        # Pending saves tracking: {scratchpad_id: DebounceTimer}
        self._debounce_timers: dict[int, DebounceTimer] = {}
        self._force_quit: bool = False
        self._first_minimize_to_tray: bool = True

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

            # Alt+Z toggle split view
            if key == Qt.Key_Z and has_alt and not has_ctrl and not has_shift:
                self._toggle_split_view()
                return True

            # Alt+T toggle Always-on-Top Mini-HUD mode
            if key == Qt.Key_T and has_alt and not has_ctrl and not has_shift:
                self.toggle_mini_hud_mode()
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

        # Primary Tab Widget (Left Pane)
        self.tab_widget = TechPadTabWidget(self)
        self.tab_widget.new_tab_requested.connect(self.create_new_tab)
        self.tab_widget.tab_edit_requested.connect(self._on_tab_double_clicked)
        self.tab_widget.tab_context_menu_requested.connect(self._on_tab_context_menu)
        self.tab_widget.tab_close_prompted.connect(self._on_tab_close_requested)
        self.tab_widget.tab_reordered.connect(self._on_tabs_reordered)
        self.tab_widget.currentChanged.connect(self._on_current_tab_changed)
        self.tab_widget.tab_cross_drop_requested.connect(
            lambda idx, gpos: self._handle_tab_cross_drop(self.tab_widget, idx, gpos)
        )
        self.workspace_splitter.addWidget(self.tab_widget)

        # Secondary Tab Widget (Right Pane — Split View)
        self.secondary_tab_widget = TechPadTabWidget(self)
        self.secondary_tab_widget.new_tab_requested.connect(self._create_new_secondary_tab)
        self.secondary_tab_widget.tab_edit_requested.connect(self._on_secondary_tab_double_clicked)
        self.secondary_tab_widget.tab_context_menu_requested.connect(self._on_secondary_tab_context_menu)
        self.secondary_tab_widget.tab_close_prompted.connect(self._on_secondary_tab_close_requested)
        self.secondary_tab_widget.tab_reordered.connect(self._on_tabs_reordered)
        self.secondary_tab_widget.currentChanged.connect(self._on_secondary_tab_changed)
        self.secondary_tab_widget.tab_cross_drop_requested.connect(
            lambda idx, gpos: self._handle_tab_cross_drop(self.secondary_tab_widget, idx, gpos)
        )
        self.secondary_tab_widget.hide()
        self.workspace_splitter.addWidget(self.secondary_tab_widget)

        self.setCentralWidget(self.workspace_splitter)

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

        self.lbl_save_status = QLabel("● Saved")
        self.lbl_save_status.setStyleSheet("color: #4ade80; font-weight: bold; padding-left: 8px;")
        self.status_bar.addWidget(self.lbl_save_status)

        self.lbl_active_info = QLabel("")
        self.lbl_active_info.setStyleSheet("color: #9cdcfe; padding-left: 16px;")
        self.status_bar.addWidget(self.lbl_active_info)

        # Toggle split view button in status bar
        self.btn_toggle_split = QPushButton("◫ Split (Alt+Z)")
        self.btn_toggle_split.setObjectName("btnSecondary")
        self.btn_toggle_split.setFlat(True)
        self.btn_toggle_split.clicked.connect(self._toggle_split_view)
        self.status_bar.addPermanentWidget(self.btn_toggle_split)

        # Toggle history drawer button in status bar
        self.btn_toggle_drawer = QPushButton("🕰️ History (Ctrl+H)")
        self.btn_toggle_drawer.setObjectName("btnSecondary")
        self.btn_toggle_drawer.setFlat(True)
        self.btn_toggle_drawer.clicked.connect(self._toggle_history_drawer)
        self.status_bar.addPermanentWidget(self.btn_toggle_drawer)

        # Toggle Always-on-Top Mini-HUD button in status bar
        self.btn_status_hud = QPushButton("📌 HUD (Alt+T)")
        self.btn_status_hud.setObjectName("btnSecondary")
        self.btn_status_hud.setFlat(True)
        self.btn_status_hud.setToolTip("Toggle Always-on-Top Mini-HUD Mode (Alt+T)")
        self.btn_status_hud.clicked.connect(self.toggle_mini_hud_mode)
        self.status_bar.addPermanentWidget(self.btn_status_hud)

    def _setup_shortcuts(self) -> None:
        """Configures application-wide shortcuts for saving, drawer toggle, and settings.

        Note: Browser-style tab shortcuts (Ctrl+T, Ctrl+W, Ctrl+PgUp/PgDown,
        Ctrl+Shift+PgUp/PgDown, Ctrl+1..9) are intercepted centrally in eventFilter()
        to guarantee reliable dispatch across all focused child widgets and
        hardware modifier states.
        """
        QShortcut(QKeySequence("Ctrl+S"), self, self.flush_all_saves, context=Qt.ApplicationShortcut)
        QShortcut(QKeySequence("Ctrl+H"), self, self._toggle_history_drawer, context=Qt.ApplicationShortcut)
        QShortcut(QKeySequence("Ctrl+,"), self, self._open_settings_dialog, context=Qt.ApplicationShortcut)
        QShortcut(QKeySequence("Alt+Z"), self, self._toggle_split_view, context=Qt.ApplicationShortcut)
        QShortcut(QKeySequence("Alt+T"), self, self.toggle_mini_hud_mode, context=Qt.ApplicationShortcut)
        QShortcut(QKeySequence("F8"), self, self.toggle_window_visibility, context=Qt.ApplicationShortcut)

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
            if editor := self._get_active_editor():
                editor.setFocus()

    def _create_new_tab_and_show(self) -> None:
        """Restores window from tray and creates a new ticket tab."""
        self.showNormal()
        self.raise_()
        self.activateWindow()
        self.create_new_tab()

    def quit_application(self) -> None:
        """Performs full synchronous flush, unregisters hotkeys, and cleanly exits the application."""
        self._force_quit = True
        if hasattr(self, "global_hotkey") and self.global_hotkey:
            self.global_hotkey.unregister()
        if hasattr(self, "tray_icon") and self.tray_icon:
            self.tray_icon.hide()
        self.close()
        if app := QApplication.instance():
            app.quit()

    def _restore_workspace(self) -> None:
        """Restores tabs and focused tab from SQLite session."""
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

        self.history_drawer.setVisible(drawer_open)

        focused_index = 0
        for i, ticket in enumerate(active_tickets):
            editor = self._create_editor(ticket["id"], ticket.get("content_html", ""))
            idx = self.tab_widget.add_ticket_tab(ticket, editor)
            if ticket["id"] == focused_id:
                focused_index = idx

        self.tab_widget.setCurrentIndex(focused_index)
        self._on_current_tab_changed(focused_index)

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

    def _get_active_editor(self) -> Optional[TechPadEditor]:
        """Returns the currently active editor across primary and secondary panes."""
        if hasattr(self, "toolbar") and self.toolbar._current_editor:
            for tw in (self.tab_widget, self.secondary_tab_widget):
                for i in range(tw.count()):
                    if tw.get_editor_at(i) == self.toolbar._current_editor:
                        return self.toolbar._current_editor
        if self.secondary_tab_widget.isVisible() and self.secondary_tab_widget.hasFocus():
            if sec_ed := self.secondary_tab_widget.get_current_editor():
                return sec_ed
        return self.tab_widget.get_current_editor()

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

    def _on_editor_modified(self, scratchpad_id: int) -> None:
        """Triggered whenever typing occurs in an editor."""
        self.set_save_status("Saving...", is_saved=False)
        debouncer = self._debounce_timers.get(scratchpad_id)
        if debouncer:
            debouncer.trigger()

    def _execute_save(self, scratchpad_id: int) -> None:
        """Saves editor content and synchronizes images with SQLite across primary and secondary panes."""
        editor, tw, idx = self._find_editor_by_id(scratchpad_id)
        if editor:
            html = editor.toHtml()
            self.scratchpad_service.save_content(
                scratchpad_id=scratchpad_id,
                content_html=html,
                in_memory_images=editor.in_memory_images,
            )
            # Clear memory image cache after successful DB persistence
            editor.in_memory_images.clear()

        # Check if any other saves are pending
        any_pending = any(d.is_active() for d in self._debounce_timers.values())
        if not any_pending:
            self.set_save_status("Saved", is_saved=True)

    def flush_all_saves(self) -> None:
        """Forces all debounced saves to execute immediately."""
        for debouncer in self._debounce_timers.values():
            debouncer.flush()
        self.set_save_status("Saved", is_saved=True)

    def set_save_status(self, text: str, is_saved: bool = True) -> None:
        """Updates the status bar indicator."""
        if is_saved:
            self.lbl_save_status.setText("● Saved")
            self.lbl_save_status.setStyleSheet("color: #4ade80; font-weight: bold; padding-left: 8px;")
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

        self.toolbar.set_active_editor(editor)
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
        editor = self.tab_widget.get_editor_at(index)
        if editor:
            self._on_editor_focused(editor.scratchpad_id)
        else:
            self.toolbar.set_active_editor(None)
            self.lbl_active_info.setText("")
            self.toolbar.stopwatch.pause_timer()

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

        # Flush any pending save on this tab first
        debouncer = self._debounce_timers.get(editor.scratchpad_id)
        if debouncer:
            debouncer.flush()

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
            self.scratchpad_service.archive_ticket(editor.scratchpad_id)
            self._remove_tab(index, editor.scratchpad_id)
            self.history_drawer.refresh_list()
        elif clicked == btn_delete:
            self.scratchpad_service.delete_ticket_permanently(editor.scratchpad_id)
            self._remove_tab(index, editor.scratchpad_id)
            self.history_drawer.refresh_list()

    def _switch_tab_relative(self, delta: int) -> None:
        """Switches active tab to next or previous (Ctrl+Tab / Ctrl+PageDown)."""
        count = self.tab_widget.count()
        if count > 1:
            new_idx = (self.tab_widget.currentIndex() + delta) % count
            self.tab_widget.setCurrentIndex(new_idx)
            editor = self.tab_widget.get_current_editor()
            if editor:
                editor.setFocus()

    def _move_active_tab_relative(self, delta: int) -> None:
        """Slides / moves the active tab left or right (Ctrl+Shift+PageDown / PageUp)."""
        current = self.tab_widget.currentIndex()
        target = current + delta
        if 0 <= target < self.tab_widget.count():
            self.tab_widget.tabBar().moveTab(current, target)
            self.tab_widget.setCurrentIndex(target)
            editor = self.tab_widget.get_current_editor()
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
        self.status_bar.showMessage("✓ Copied formatted note (rich text & images) to clipboard!", 3500)

    def _on_export_note(self) -> None:
        """Copies clean plain text / Markdown note from active editor to clipboard for ticketing tool."""
        editor = self._get_active_editor()
        if not editor:
            return

        # Ensure active changes are saved first
        self._execute_save(editor.scratchpad_id)

        clean_text = self.scratchpad_service.export_as_plain_ticket_note(editor.scratchpad_id)
        QApplication.clipboard().setText(clean_text)
        self.status_bar.showMessage("✓ Copied clean note for ticketing system to clipboard!", 3500)

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
                act_move = menu.addAction("◫ Move to Right Pane")
                act_move.triggered.connect(lambda: self._move_tab_between_panes(self.tab_widget, self.secondary_tab_widget, index))
            else:
                act_split = menu.addAction("◫ Open in Side-by-Side Split (Alt+Z)")
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

            act_move = menu.addAction("◫ Move to Left Pane")
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

        act_close_split = menu.addAction("◫ Close Split View (Alt+Z)")
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

        debouncer = self._debounce_timers.get(editor.scratchpad_id)
        if debouncer:
            debouncer.flush()

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
            self.scratchpad_service.archive_ticket(editor.scratchpad_id)
            self._remove_secondary_tab(index, editor.scratchpad_id)
            self.history_drawer.refresh_list()
        elif clicked == btn_delete:
            self.scratchpad_service.delete_ticket_permanently(editor.scratchpad_id)
            self._remove_secondary_tab(index, editor.scratchpad_id)
            self.history_drawer.refresh_list()

    def _archive_secondary_tab(self, index: int) -> None:
        """Archives a secondary tab directly without extra prompt."""
        editor = self.secondary_tab_widget.get_editor_at(index)
        if not editor:
            return
        debouncer = self._debounce_timers.get(editor.scratchpad_id)
        if debouncer:
            debouncer.flush()
        self.scratchpad_service.archive_ticket(editor.scratchpad_id)
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

    def _handle_tab_cross_drop(self, from_tw: TechPadTabWidget, source_idx: int, global_pos: QPoint) -> None:
        """Handles dropping a dragged tab into the other split view pane or triggering split view."""
        if source_idx < 0 or source_idx >= from_tw.count():
            return

        target_widget = QApplication.widgetAt(global_pos)
        if not target_widget:
            return

        # Find which tab widget is under the drop point
        to_tw = None
        curr = target_widget
        while curr:
            if curr == self.tab_widget:
                to_tw = self.tab_widget
                break
            elif curr == self.secondary_tab_widget:
                to_tw = self.secondary_tab_widget
                break
            curr = curr.parent()

        # If Split View is not open, check if user dragged tab to the right half of the workspace splitter
        if not self.secondary_tab_widget.isVisible():
            splitter_global = self.workspace_splitter.mapToGlobal(QPoint(0, 0))
            splitter_rect = self.workspace_splitter.rect()
            right_half_x = splitter_global.x() + (splitter_rect.width() // 2)
            if (
                splitter_global.x() <= global_pos.x() <= splitter_global.x() + splitter_rect.width()
                and splitter_global.y() <= global_pos.y() <= splitter_global.y() + splitter_rect.height()
                and global_pos.x() >= right_half_x
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

        # Check if cursor is roughly within tab bar vertical bounds (+/- 30px)
        if -15 <= pos_in_bar.y() <= bar.height() + 30:
            idx = bar.tabAt(pos_in_bar)
            if idx >= 0:
                rect = bar.tabRect(idx)
                if pos_in_bar.x() > rect.center().x():
                    return idx + 1
                return idx
            # If to the right of all tabs in the bar
            if pos_in_bar.x() > 0:
                return target_tw.count()

        # Dropped into the editor area: insert as active tab at the end
        return target_tw.count()

    def _toggle_split_view(self) -> None:
        """Toggles side-by-side split view mode."""
        if self.secondary_tab_widget.isVisible():
            self.close_split_view()
        else:
            self.open_split_view()

    def open_split_view(self, target_scratchpad_id: Optional[int] = None) -> None:
        """Enables split view mode and populates the secondary pane."""
        self.flush_all_saves()

        if self.secondary_tab_widget.isVisible():
            if target_scratchpad_id is not None:
                # Find if target is in primary pane
                for i in range(self.tab_widget.count()):
                    ed = self.tab_widget.get_editor_at(i)
                    if ed and ed.scratchpad_id == target_scratchpad_id:
                        self._move_tab_between_panes(self.tab_widget, self.secondary_tab_widget, i)
                        break
            return

        # Prepare secondary pane content
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
        elif self.secondary_tab_widget.count() == 0:
            if self.tab_widget.count() > 1:
                curr_idx = self.tab_widget.currentIndex()
                move_idx = curr_idx + 1 if curr_idx + 1 < self.tab_widget.count() else curr_idx - 1
                self._move_tab_between_panes(self.tab_widget, self.secondary_tab_widget, move_idx)
            else:
                self._create_new_secondary_tab()

        self.secondary_tab_widget.show()
        total_w = self.workspace_splitter.width() or self.width() or 1000
        half = max(200, total_w // 2)
        self.workspace_splitter.setSizes([half, half])

        self.toolbar.btn_split.setChecked(True)
        self.btn_toggle_split.setText("◫ Single (Alt+Z)")

        sec_editor = self.secondary_tab_widget.get_current_editor()
        if sec_editor:
            sec_editor.setFocus()
            self._on_editor_focused(sec_editor.scratchpad_id)

        self._on_tabs_reordered()

    def close_split_view(self) -> None:
        """Consolidates secondary tabs into primary tab widget and hides secondary pane."""
        self.flush_all_saves()

        while self.secondary_tab_widget.count() > 0:
            editor = self.secondary_tab_widget.get_editor_at(0)
            if editor:
                sid = editor.scratchpad_id
                ticket = self.scratchpad_service.get_ticket(sid) or {"id": sid}
                self.secondary_tab_widget.removeTab(0)
                self.tab_widget.add_ticket_tab(ticket, editor)
            else:
                self.secondary_tab_widget.removeTab(0)

        self.secondary_tab_widget.hide()
        self.toolbar.btn_split.setChecked(False)
        self.btn_toggle_split.setText("◫ Split (Alt+Z)")

        prim_editor = self.tab_widget.get_current_editor()
        if prim_editor:
            prim_editor.setFocus()
            self._on_editor_focused(prim_editor.scratchpad_id)

        self._on_tabs_reordered()

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
        if self._saved_split_visible:
            self.secondary_tab_widget.hide()

        # 3. Enable Always-on-Top and relax minimum size constraints
        self.setMinimumSize(340, 200)
        self.setWindowFlag(Qt.WindowStaysOnTopHint, True)
        self.resize(440, 280)

        # 4. Update HUD window title with active ticket info
        editor = self._get_active_editor()
        t_label = ""
        if editor:
            ticket = self.scratchpad_service.get_ticket(editor.scratchpad_id)
            if ticket:
                t_num = ticket.get("ticket_number", "")
                client = ticket.get("client_name", "")
                t_label = f" — #{t_num}" + (f" ({client})" if client else "")
        self.setWindowTitle(f"📌 [HUD] {APP_NAME}{t_label}")

        # 5. Update UI controls & status bar feedback
        self.toolbar.set_mini_hud_state(True)
        if hasattr(self, "btn_status_hud"):
            self.btn_status_hud.setText("📌 Normal (Alt+T)")
        self.status_bar.showMessage("📌 Mini-HUD Mode Active (Always-on-Top) — Press Alt+T to restore", 3500)

        self.show()

    def _disable_mini_hud(self) -> None:
        """Disables Mini-HUD mode and restores standard full workspace geometry."""
        self.flush_all_saves()

        self._is_mini_hud = False

        # 1. Disable Always-on-Top and restore standard minimum size
        self.setWindowFlag(Qt.WindowStaysOnTopHint, False)
        self.setMinimumSize(800, 500)

        # 2. Restore previous window geometry
        if getattr(self, "_saved_normal_geometry", None):
            self.restoreGeometry(self._saved_normal_geometry)

        # 3. Restore visibility of toolbar, drawer, and split view
        if getattr(self, "_saved_row1_visible", True):
            self.toolbar.show()
        if getattr(self, "_saved_drawer_visible", False):
            self.history_drawer.show()
        if getattr(self, "_saved_split_visible", False):
            self.secondary_tab_widget.show()

        # 4. Restore window title and UI controls
        self.setWindowTitle(f"{APP_NAME} v{APP_VERSION} — Technician Scratchpad")
        self.toolbar.set_mini_hud_state(False)
        if hasattr(self, "btn_status_hud"):
            self.btn_status_hud.setText("📌 HUD (Alt+T)")
        self.status_bar.showMessage("✓ Restored Normal Workspace", 3000)

        self.show()

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
        self.status_bar.showMessage(f"✓ Duplicated ticket as #{new_ticket['ticket_number']}", 3000)

    def _archive_tab(self, index: int) -> None:
        """Archives a tab directly without extra prompt."""
        editor = self.tab_widget.get_editor_at(index)
        if not editor:
            return
        debouncer = self._debounce_timers.get(editor.scratchpad_id)
        if debouncer:
            debouncer.flush()
        self.scratchpad_service.archive_ticket(editor.scratchpad_id)
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
                debouncer = self._debounce_timers.get(editor.scratchpad_id)
                if debouncer:
                    debouncer.flush()
                self.scratchpad_service.archive_ticket(editor.scratchpad_id)
                self._remove_tab(i, editor.scratchpad_id)

        self.history_drawer.refresh_list()
        self.status_bar.showMessage("✓ Closed and archived other tabs", 3000)

    def _toggle_history_drawer(self) -> None:
        is_visible = not self.history_drawer.isVisible()
        self.history_drawer.setVisible(is_visible)
        if is_visible and self.history_drawer.width() < 320:
            self.resizeDocks([self.history_drawer], [380], Qt.Horizontal)

    def closeEvent(self, event: QCloseEvent) -> None:
        """Minimizes to system tray if tray icon is active, preserving saves and session state."""
        self.toolbar.stopwatch.save_current_state()
        self.flush_all_saves()

        # Update tab orders across all panes
        self._on_tabs_reordered()

        # Determine currently active scratchpad ID
        active_editor = self._get_active_editor()
        active_id = active_editor.scratchpad_id if active_editor else None

        # Save session with window geometry and opacity
        geometry_hex = self.saveGeometry().toHex().data().decode("utf-8")
        opacity_val = int(round(self.windowOpacity() * 100))
        self.session_service.persist_workspace(
            active_scratchpad_id=active_id,
            window_geometry=geometry_hex,
            window_opacity=opacity_val,
            history_drawer_open=self.history_drawer.isVisible(),
        )

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
            self.toolbar.stopwatch.pause_timer()
            if hasattr(self, "global_hotkey") and self.global_hotkey:
                self.global_hotkey.unregister()
            event.accept()


