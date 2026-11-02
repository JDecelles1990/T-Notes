"""Main application window for TechPad."""

from pathlib import Path
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
    QStatusBar,
    QVBoxLayout,
    QWidget,
)
from src.core.constants import APP_NAME, APP_VERSION, AUTO_SAVE_DEBOUNCE_MS
from src.core.debouncer import DebounceTimer
from src.services.image_service import ImageService
from src.services.scratchpad_service import ScratchpadService
from src.services.session_service import SessionService
from src.ui.components.editor import TechPadEditor
from src.ui.components.history_drawer import HistoryDrawer
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

        # Pending saves tracking: {scratchpad_id: DebounceTimer}
        self._debounce_timers: dict[int, DebounceTimer] = {}

        self._setup_ui()
        self._setup_shortcuts()
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
        # Central Tab Widget
        self.tab_widget = TechPadTabWidget(self)
        self.tab_widget.new_tab_requested.connect(self.create_new_tab)
        self.tab_widget.tab_edit_requested.connect(self._on_tab_double_clicked)
        self.tab_widget.tab_context_menu_requested.connect(self._on_tab_context_menu)
        self.tab_widget.tab_close_prompted.connect(self._on_tab_close_requested)
        self.tab_widget.tab_reordered.connect(self._on_tabs_reordered)
        self.tab_widget.currentChanged.connect(self._on_current_tab_changed)
        self.setCentralWidget(self.tab_widget)

        # Formatting Toolbar
        self.toolbar = TechPadToolBar(self)
        self.toolbar.image_requested.connect(self._on_insert_image_file)
        self.toolbar.skeleton_selected.connect(self._on_skeleton_selected)
        self.toolbar.export_note_requested.connect(self._on_export_note)
        self.toolbar.opacity_changed.connect(self._on_opacity_changed)
        self.toolbar.settings_requested.connect(self._open_settings_dialog)
        self.addToolBar(Qt.TopToolBarArea, self.toolbar)

        # History / Archive Side Drawer
        self.history_drawer = HistoryDrawer(self.scratchpad_service, self)
        self.history_drawer.restore_requested.connect(self._on_restore_ticket)
        self.history_drawer.delete_requested.connect(self._on_delete_ticket)
        self.addDockWidget(Qt.RightDockWidgetArea, self.history_drawer)

        # Status Bar
        self.status_bar = QStatusBar(self)
        self.setStatusBar(self.status_bar)

        self.lbl_save_status = QLabel("● Saved")
        self.lbl_save_status.setStyleSheet("color: #4ade80; font-weight: bold; padding-left: 8px;")
        self.status_bar.addWidget(self.lbl_save_status)

        self.lbl_active_info = QLabel("")
        self.lbl_active_info.setStyleSheet("color: #9cdcfe; padding-left: 16px;")
        self.status_bar.addWidget(self.lbl_active_info)

        # Toggle history drawer button in status bar
        self.btn_toggle_drawer = QPushButton("📜 History (Ctrl+H)")
        self.btn_toggle_drawer.setObjectName("btnSecondary")
        self.btn_toggle_drawer.setFlat(True)
        self.btn_toggle_drawer.clicked.connect(self._toggle_history_drawer)
        self.status_bar.addPermanentWidget(self.btn_toggle_drawer)

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

        # Create debouncer using configured delay
        delay_ms = int(self.session_service.get_setting("auto_save_delay_ms", str(AUTO_SAVE_DEBOUNCE_MS)))
        debouncer = DebounceTimer(
            delay_ms=delay_ms,
            callback=lambda sid=scratchpad_id: self._execute_save(sid),
            parent=self,
        )
        self._debounce_timers[scratchpad_id] = debouncer
        return editor

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

    def _on_editor_modified(self, scratchpad_id: int) -> None:
        """Triggered whenever typing occurs in an editor."""
        self.set_save_status("Saving...", is_saved=False)
        debouncer = self._debounce_timers.get(scratchpad_id)
        if debouncer:
            debouncer.trigger()

    def _execute_save(self, scratchpad_id: int) -> None:
        """Saves editor content and synchronizes images with SQLite."""
        # Find editor with this scratchpad_id
        for i in range(self.tab_widget.count()):
            editor = self.tab_widget.get_editor_at(i)
            if editor and editor.scratchpad_id == scratchpad_id:
                html = editor.toHtml()
                self.scratchpad_service.save_content(
                    scratchpad_id=scratchpad_id,
                    content_html=html,
                    in_memory_images=editor.in_memory_images,
                )
                # Clear memory image cache after successful DB persistence
                editor.in_memory_images.clear()
                break

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

    def _on_current_tab_changed(self, index: int) -> None:
        """Updates active editor in toolbar and updates status info."""
        # Flush previous tab's debounced save before switching
        self.flush_all_saves()

        editor = self.tab_widget.get_editor_at(index)
        self.toolbar.set_active_editor(editor)

        if editor:
            ticket = self.scratchpad_service.get_ticket(editor.scratchpad_id)
            if ticket:
                t_num = ticket.get("ticket_number", "")
                client = ticket.get("client_name", "")
                title = ticket.get("title", "")
                self.lbl_active_info.setText(f"Active Ticket: #{t_num} | Client: {client or 'N/A'} | Subject: {title or 'N/A'}")
        else:
            self.lbl_active_info.setText("")

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
            # Update tab title
            new_title = TechPadTabWidget.format_title(
                data["ticket_number"],
                data["client_name"],
                data["title"],
            )
            self.tab_widget.setTabText(index, new_title)
            self.tab_widget.setTabToolTip(
                index,
                f"Ticket: {data['ticket_number']}\nClient: {data['client_name']}\nTitle: {data['title']}",
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
        """Persists new tab order after drag and drop."""
        orders = []
        for i in range(self.tab_widget.count()):
            editor = self.tab_widget.get_editor_at(i)
            if editor:
                orders.append((editor.scratchpad_id, i))
        if orders:
            self.scratchpad_service.update_tab_orders(orders)

    def _on_restore_ticket(self, scratchpad_id: int) -> None:
        """Restores an archived ticket as a tab."""
        # Check if already open
        for i in range(self.tab_widget.count()):
            editor = self.tab_widget.get_editor_at(i)
            if editor and editor.scratchpad_id == scratchpad_id:
                self.tab_widget.setCurrentIndex(i)
                return

        ticket = self.scratchpad_service.restore_ticket(scratchpad_id)
        if ticket:
            editor = self._create_editor(ticket["id"], ticket.get("content_html", ""))
            idx = self.tab_widget.add_ticket_tab(ticket, editor)
            self.tab_widget.setCurrentIndex(idx)
            self.history_drawer.refresh_list()

    def _on_delete_ticket(self, scratchpad_id: int) -> None:
        """Permanently deletes a ticket from history."""
        self.scratchpad_service.delete_ticket_permanently(scratchpad_id)
        self.history_drawer.refresh_list()

    def _on_insert_image_file(self) -> None:
        """Prompts for an image file and inserts it into current editor."""
        editor = self.tab_widget.get_current_editor()
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
        """Inserts selected ticket template into active editor."""
        editor = self.tab_widget.get_current_editor()
        if not editor:
            return
        html = self.scratchpad_service.get_skeleton_html(skeleton_name)
        if html:
            editor.textCursor().insertHtml(html)

    def _on_export_note(self) -> None:
        """Copies clean plain text / Markdown note to clipboard for ticketing tool."""
        editor = self.tab_widget.get_current_editor()
        if not editor:
            return

        # Ensure active changes are saved first
        self._execute_save(editor.scratchpad_id)

        clean_text = self.scratchpad_service.export_as_plain_ticket_note(editor.scratchpad_id)
        QApplication.clipboard().setText(clean_text)
        self.status_bar.showMessage("✓ Copied clean note for ticketing system to clipboard!", 3500)

    def _on_tab_context_menu(self, index: int, global_pos: QPoint) -> None:
        """Displays rich context menu on right-clicking a tab or the tab bar."""
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

            # Copy Note for Ticketing Tool
            act_copy = menu.addAction("📤 Copy Note for Ticket Tool")
            act_copy.triggered.connect(lambda: self._copy_tab_note(index))

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

    def _copy_tab_note(self, index: int) -> None:
        """Copies formatted plain text / Markdown note of a specific tab to clipboard."""
        editor = self.tab_widget.get_editor_at(index)
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
        self.history_drawer.setVisible(not self.history_drawer.isVisible())

    def closeEvent(self, event: QCloseEvent) -> None:
        """Synchronously flushes all pending saves and persists workspace session before exit."""
        self.flush_all_saves()

        # Update tab orders
        self._on_tabs_reordered()

        # Determine currently active scratchpad ID
        active_editor = self.tab_widget.get_current_editor()
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
        event.accept()

