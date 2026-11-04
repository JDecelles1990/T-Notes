"""S001 navigation regressions using isolated DBs and the existing GUI fixture."""

import socket
import subprocess
from pathlib import Path

import pytest
from PySide6.QtCore import QCoreApplication, QEvent, Qt
from PySide6.QtGui import QImage, QKeyEvent, QShortcut, QTextCursor
from PySide6.QtTest import QSignalSpy, QTest
from PySide6.QtWidgets import QApplication, QDialog, QGroupBox, QLineEdit, QMainWindow, QTextEdit

from test_ui_integration import main_window
from src.ui.main_window import TechPadMainWindow
from src.ui.m365.launcher_widget import M365LauncherWidget


def show(window, qapp):
    window.show()
    qapp.processEvents()


def test_default_page_and_accessible_navigation(main_window, qapp):
    show(main_window, qapp)
    stack = main_window.workspace_stack
    original = main_window.workspace_splitter
    editor = main_window._get_active_editor()
    assert stack.count() == 2
    assert stack.widget(0) is original
    assert stack.currentWidget() is original
    button = main_window.toolbar.btn_m365
    assert button.isVisible() and button.isEnabled()
    assert button.text() == "M365 Launcher"
    assert button.accessibleName() and button.toolTip()
    assert button.focusPolicy() == Qt.StrongFocus
    QTest.mouseClick(button, Qt.LeftButton)
    qapp.processEvents()
    assert stack.currentWidget() is main_window.m365_workspace
    assert isinstance(stack.currentWidget(), M365LauncherWidget)
    assert button.text() == "T-Notes"
    assert button.isEnabled() is True
    QTest.mouseClick(main_window.m365_workspace.back_button, Qt.LeftButton)
    qapp.processEvents()
    assert stack.currentWidget() is original
    assert button.text() == "M365 Launcher"
    assert main_window._get_active_editor() is editor


@pytest.mark.parametrize("width", [700, 800, 1100])
def test_toolbar_controls_fit_without_overflow(main_window, qapp, width):
    main_window.resize(width, 750)
    show(main_window, qapp)
    for toolbar in (main_window.toolbar, main_window.toolbar.secondary_toolbar):
        for action in toolbar.actions():
            if not action.isVisible() or action.isSeparator():
                continue
            widget = toolbar.widgetForAction(action)
            assert widget is not None and widget.isVisible(), action.text()
            assert toolbar.rect().contains(widget.geometry()), action.text()
    assert main_window.toolbar.btn_m365.isVisible()


def test_catalog_shell_preserves_notes_boundary_and_placeholders(main_window, qapp):
    show(main_window, qapp)
    main_window.show_m365_workspace()
    widget = main_window.m365_workspace
    assert widget.navigation.count() == 14
    assert widget.navigation.isEnabled()
    names = {group.title() for group in widget.findChildren(QGroupBox)}
    assert {"Company Selection", "Authentication & Tenant Context", "Script Catalog",
            "Parameters", "Execution Workspace", "Parsed Results", "Active Ticket Notes"} <= names
    assert not widget.findChildren(QTextEdit)
    assert not widget.findChildren(QMainWindow)
    assert widget.ticket_sidebar.isVisible()
    QTest.mouseClick(widget.ticket_panel_toggle, Qt.LeftButton)
    assert widget.ticket_sidebar.isHidden()
    QTest.mouseClick(widget.ticket_panel_toggle, Qt.LeftButton)
    assert widget.ticket_sidebar.isVisible()
    widget.workspace_splitter.setSizes([140, 420, 220])
    assert len(widget.workspace_splitter.sizes()) == 3


def test_repeated_switch_preserves_document_cursor_undo_and_instances(main_window, qapp):
    show(main_window, qapp)
    editor = main_window._get_active_editor()
    editor.setFocus()
    editor.textCursor().insertText("S001 synthetic unsaved note")
    editor.textCursor().insertText(" plus undo")
    document = editor.document()
    cursor = editor.textCursor()
    cursor.setPosition(3)
    cursor.setPosition(12, QTextCursor.KeepAnchor)
    editor.setTextCursor(cursor)
    selection = (cursor.position(), cursor.anchor())
    timers = dict(main_window._debounce_timers)
    for _ in range(5):
        assert main_window.show_m365_workspace()
        qapp.processEvents()
        main_window.show_notes_workspace()
        qapp.processEvents()
    assert main_window._get_active_editor() is editor
    assert editor.document() is document
    assert (editor.textCursor().position(), editor.textCursor().anchor()) == selection
    assert "S001 synthetic unsaved note plus undo" in editor.toPlainText()
    assert editor.document().isUndoAvailable()
    assert main_window._debounce_timers == timers
    assert len(main_window.findChildren(QTextEdit)) == 1


def test_pending_image_and_content_save_before_navigation(main_window, qapp):
    show(main_window, qapp)
    editor = main_window._get_active_editor()
    image = QImage(16, 16, QImage.Format_RGB32)
    image.fill(0x112233)
    editor.insert_embedded_image(image)
    editor.textCursor().insertText("Synthetic save boundary")
    names = set(editor.in_memory_images)
    assert names and main_window._debounce_timers[editor.scratchpad_id].is_active()
    assert main_window.show_m365_workspace()
    ticket = main_window.scratchpad_service.get_ticket(editor.scratchpad_id)
    assert "Synthetic save boundary" in ticket["content_html"]
    images = main_window.image_service.repo.get_images_for_scratchpad(editor.scratchpad_id)
    assert set(images) == names
    assert not editor.in_memory_images
    assert all(value.startswith(bytes([255, 216])) for value in images.values())


def test_failed_save_refuses_navigation_and_explicit_retry_retries_stopped_timer(main_window, qapp, monkeypatch):
    show(main_window, qapp)
    editor = main_window._get_active_editor()
    editor.textCursor().insertText("Must survive a synthetic failure")
    original = main_window.scratchpad_service.save_content
    calls = []
    def fail_once(*args, **kwargs):
        calls.append(kwargs["scratchpad_id"])
        if len(calls) == 1:
            raise OSError("Synthetic save failure")
        return original(*args, **kwargs)
    monkeypatch.setattr(main_window.scratchpad_service, "save_content", fail_once)
    assert main_window.show_m365_workspace() is False
    assert not main_window.is_m365_workspace
    assert "Must survive" in editor.toPlainText()
    assert "could not be saved" in main_window.status_bar.currentMessage()
    assert main_window.show_m365_workspace() is True
    assert len(calls) == 2
    assert "Must survive" in main_window.scratchpad_service.get_ticket(editor.scratchpad_id)["content_html"]


@pytest.mark.parametrize("running", [False, True])
def test_workspace_switch_never_reloads_or_changes_stopwatch(main_window, qapp, monkeypatch, running):
    show(main_window, qapp)
    editor = main_window._get_active_editor()
    editor.setFocus()
    qapp.processEvents()
    stopwatch = main_window.toolbar.stopwatch
    stopwatch.start_timer() if running else stopwatch.pause_timer()
    before = (stopwatch.current_scratchpad_id, stopwatch.elapsed_seconds, stopwatch.is_running)
    calls = []
    monkeypatch.setattr(stopwatch, "load_scratchpad", lambda *a, **k: calls.append((a, k)))
    main_window.show_m365_workspace()
    qapp.processEvents()
    main_window.show_notes_workspace()
    qapp.processEvents()
    assert not calls
    assert (stopwatch.current_scratchpad_id, stopwatch.elapsed_seconds, stopwatch.is_running) == before


def test_active_secondary_ticket_split_and_history_state_survive(main_window, qapp):
    show(main_window, qapp)
    main_window.create_new_tab()
    main_window.open_split_view()
    qapp.processEvents()
    editor = main_window.secondary_tab_widget.get_current_editor()
    editor.setFocus()
    qapp.processEvents()
    original = (main_window.tab_widget.currentIndex(), main_window.secondary_tab_widget.currentIndex())
    main_window.history_drawer.show()
    qapp.processEvents()
    sizes = main_window.workspace_splitter.sizes()
    main_window.show_m365_workspace()
    assert main_window.history_drawer.isHidden()
    assert not main_window.btn_toggle_split.isEnabled()
    assert not main_window.btn_toggle_drawer.isEnabled()
    main_window.show_notes_workspace()
    qapp.processEvents()
    assert main_window._get_active_editor() is editor
    assert (main_window.tab_widget.currentIndex(), main_window.secondary_tab_widget.currentIndex()) == original
    assert main_window.secondary_tab_widget.isVisible()
    assert main_window.history_drawer.isVisible()
    assert main_window.workspace_splitter.sizes() == sizes
    main_window.close_split_view()
    assert main_window.secondary_tab_widget.isHidden()
    assert main_window._find_editor_by_id(editor.scratchpad_id)[0] is editor


@pytest.mark.parametrize("key, modifiers", [
    (Qt.Key_W, Qt.ControlModifier), (Qt.Key_F4, Qt.ControlModifier),
    (Qt.Key_T, Qt.ControlModifier), (Qt.Key_Tab, Qt.ControlModifier),
    (Qt.Key_PageDown, Qt.ControlModifier | Qt.ShiftModifier),
    (Qt.Key_1, Qt.ControlModifier), (Qt.Key_Z, Qt.AltModifier),
])
def test_m365_focus_cannot_trigger_hidden_ticket_shortcuts(main_window, qapp, key, modifiers):
    show(main_window, qapp)
    editor = main_window._get_active_editor()
    original = editor.toHtml()
    main_window.show_m365_workspace()
    event = QKeyEvent(QEvent.KeyPress, key, modifiers)
    assert main_window.eventFilter(main_window.m365_workspace.back_button, event) is False
    QTest.keyClick(main_window.m365_workspace.back_button, key, modifiers)
    qapp.processEvents()
    assert main_window.is_m365_workspace
    assert main_window.tab_widget.count() == 1
    assert main_window._get_active_editor() is editor
    assert editor.toHtml() == original
    assert main_window.secondary_tab_widget.isHidden()


def test_hidden_format_actions_disabled_then_restored(main_window, qapp):
    show(main_window, qapp)
    editor = main_window._get_active_editor()
    original = editor.toHtml()
    main_window.toolbar.act_image.setEnabled(False)
    main_window.show_m365_workspace()
    assert not main_window.toolbar.act_checklist.isEnabled()
    main_window.toolbar.act_checklist.trigger()
    QTest.keyClick(main_window.m365_workspace.back_button, Qt.Key_L, Qt.ControlModifier | Qt.AltModifier)
    assert editor.toHtml() == original
    assert all(not shortcut.isEnabled() for shortcut in main_window._notes_shortcuts)
    QTest.keyClick(main_window.m365_workspace.back_button, Qt.Key_Space)
    qapp.processEvents()
    assert not main_window.is_m365_workspace
    assert main_window.toolbar.act_checklist.isEnabled()
    assert not main_window.toolbar.act_image.isEnabled()
    assert all(shortcut.isEnabled() for shortcut in main_window._notes_shortcuts)


def test_hud_from_m365_returns_notes_and_restores_split_history(main_window, qapp):
    show(main_window, qapp)
    main_window.create_new_tab()
    main_window.open_split_view()
    main_window.history_drawer.show()
    qapp.processEvents()
    main_window.show_m365_workspace()
    main_window.toggle_mini_hud_mode()
    assert main_window.is_m365_workspace
    assert main_window.is_mini_hud
    assert main_window.toolbar.isHidden()
    assert main_window.btn_m365.text() == "T-Notes"
    main_window.toggle_mini_hud_mode()
    qapp.processEvents()
    assert not main_window.is_mini_hud
    assert main_window.btn_m365.text() == "T-Notes"
    main_window.show_notes_workspace()
    assert main_window.toolbar.isVisible()
    assert main_window.secondary_tab_widget.isVisible()
    assert main_window.history_drawer.isVisible()
    main_window.toggle_mini_hud_mode()
    assert main_window.show_m365_workspace()
    assert main_window.is_mini_hud
    assert main_window.is_m365_workspace
    assert main_window.btn_m365.text() == "T-Notes"


def test_f8_and_tray_reopen_keep_current_workspace(main_window, qapp, monkeypatch):
    show(main_window, qapp)
    main_window.history_drawer.show()
    main_window.show_m365_workspace()
    main_window.close()
    assert main_window.isHidden() and main_window.tray_icon.isVisible()
    session = main_window.session_service.session_repo.get_session()
    assert session["history_drawer_open"] == 1
    main_window.global_hotkey.activated.emit()
    qapp.processEvents()
    assert main_window.isVisible() and main_window.is_m365_workspace
    assert QApplication.focusWidget() is main_window.m365_workspace.back_button
    monkeypatch.setattr(main_window, "isActiveWindow", lambda: True)
    event = QKeyEvent(QEvent.KeyPress, Qt.Key_F8, Qt.NoModifier)
    assert main_window.eventFilter(main_window.m365_workspace, event)
    assert main_window.isMinimized()


def test_reopen_restores_existing_notes_and_defaults_to_notes(main_window, qapp):
    show(main_window, qapp)
    editor = main_window._get_active_editor()
    editor.textCursor().insertText("Synthetic persisted restart note")
    sid = editor.scratchpad_id
    main_window.show_m365_workspace()
    main_window.quit_application()
    reopened = TechPadMainWindow(main_window.scratchpad_service, main_window.image_service, main_window.session_service)
    try:
        show(reopened, qapp)
        assert not reopened.is_m365_workspace
        assert reopened._get_active_editor().scratchpad_id == sid
        assert "Synthetic persisted restart note" in reopened._get_active_editor().toPlainText()
    finally:
        reopened.quit_application()
        qapp.removeEventFilter(reopened)
        reopened.deleteLater()
        QCoreApplication.sendPostedEvents(None, QEvent.DeferredDelete)


def test_schema_unchanged_and_no_network_or_process_dispatch(main_window, qapp, monkeypatch):
    show(main_window, qapp)
    connection = main_window.scratchpad_service.repo.db.get_connection()
    schema = connection.execute("SELECT type, name, sql FROM sqlite_master ORDER BY type, name").fetchall()
    def forbidden(*args, **kwargs):
        pytest.fail("Workspace navigation must not dispatch a process or network operation")
    monkeypatch.setattr(subprocess, "Popen", forbidden)
    monkeypatch.setattr(subprocess, "run", forbidden)
    monkeypatch.setattr(socket, "create_connection", forbidden)
    for _ in range(3):
        main_window.show_m365_workspace()
        main_window.show_notes_workspace()
    assert connection.execute("SELECT type, name, sql FROM sqlite_master ORDER BY type, name").fetchall() == schema
    assert connection.execute("PRAGMA integrity_check").fetchone()[0] == "ok"
    assert not connection.execute("PRAGMA foreign_key_check").fetchall()


def test_previous_failed_autosave_with_idle_timer_is_retried_before_navigation(main_window, qapp, monkeypatch):
    show(main_window, qapp)
    editor = main_window._get_active_editor()
    editor.textCursor().insertText("Earlier failed autosave")
    timer = main_window._debounce_timers[editor.scratchpad_id]
    timer.cancel()
    original = main_window.scratchpad_service.save_content
    def fail(*args, **kwargs):
        raise OSError("Synthetic prior autosave failure")
    monkeypatch.setattr(main_window.scratchpad_service, "save_content", fail)
    with pytest.raises(OSError):
        main_window._execute_save(editor.scratchpad_id)
    assert not timer.is_active()
    monkeypatch.setattr(main_window.scratchpad_service, "save_content", original)
    assert main_window.show_m365_workspace()
    assert "Earlier failed autosave" in main_window.scratchpad_service.get_ticket(editor.scratchpad_id)["content_html"]


def test_failed_image_save_keeps_original_cache_and_editor(main_window, qapp, monkeypatch):
    show(main_window, qapp)
    editor = main_window._get_active_editor()
    image = QImage(8, 8, QImage.Format_RGB32)
    image.fill(0x334455)
    editor.insert_embedded_image(image)
    cache = dict(editor.in_memory_images)
    def fail(*args, **kwargs):
        raise OSError("Synthetic image persistence failure")
    monkeypatch.setattr(main_window.scratchpad_service, "save_content", fail)
    assert not main_window.show_m365_workspace()
    assert main_window._get_active_editor() is editor
    assert editor.in_memory_images == cache
    monkeypatch.undo()


def test_themed_navigation_row_fits_minimum_width(main_window, qapp):
    previous = qapp.styleSheet()
    qapp.setStyleSheet((Path(__file__).parents[1] / "assets/styles/dark_theme.qss").read_text())
    try:
        main_window.resize(800, 750)
        show(main_window, qapp)
        toolbar = main_window.toolbar
        for action in toolbar.actions():
            if action.isVisible() and not action.isSeparator():
                widget = toolbar.widgetForAction(action)
                assert widget.isVisible() and toolbar.rect().contains(widget.geometry())
        assert toolbar.btn_m365.isVisible()
    finally:
        qapp.setStyleSheet(previous)


def press_alt_f8(target, qapp):
    QTest.keyClick(target, Qt.Key_F8, Qt.AltModifier)
    qapp.processEvents()


@pytest.mark.parametrize("running", [False, True])
def test_alt_f8_preserves_split_ticket_pending_notes_and_timer(main_window, qapp, running):
    show(main_window, qapp)
    main_window.create_new_tab()
    main_window.open_split_view()
    qapp.processEvents()
    editor = main_window.secondary_tab_widget.get_current_editor()
    editor.setFocus()
    qapp.processEvents()
    editor.textCursor().insertText("Synthetic Alt+F8 pending note")
    stopwatch = main_window.toolbar.stopwatch
    stopwatch.start_timer() if running else stopwatch.pause_timer()
    timer_state = (stopwatch.current_scratchpad_id, stopwatch.elapsed_seconds, stopwatch.is_running)
    identity = (main_window.workspace_splitter, main_window.m365_workspace, editor.document())
    selection = (main_window.tab_widget.currentIndex(), main_window.secondary_tab_widget.currentIndex())
    sizes = main_window.workspace_splitter.sizes()
    press_alt_f8(editor, qapp)
    assert main_window.is_m365_workspace
    assert "Synthetic Alt+F8 pending note" in main_window.scratchpad_service.get_ticket(editor.scratchpad_id)["content_html"]
    press_alt_f8(main_window.m365_workspace.back_button, qapp)
    assert not main_window.is_m365_workspace
    assert main_window._get_active_editor() is editor
    assert (main_window.workspace_splitter, main_window.m365_workspace, editor.document()) == identity
    assert (main_window.tab_widget.currentIndex(), main_window.secondary_tab_widget.currentIndex()) == selection
    assert main_window.secondary_tab_widget.isVisible()
    assert main_window.workspace_splitter.sizes() == sizes
    assert (stopwatch.current_scratchpad_id, stopwatch.elapsed_seconds, stopwatch.is_running) == timer_state


def test_alt_f8_dispatches_once_per_press_and_reuses_widgets(main_window, qapp):
    show(main_window, qapp)
    editor = main_window._get_active_editor()
    document = editor.document()
    pages = [main_window.workspace_stack.widget(i) for i in range(2)]
    spy = QSignalSpy(main_window.workspace_shortcut.activated)
    assert spy.isValid()
    for press in range(1, 9):
        target = main_window.m365_workspace.back_button if main_window.is_m365_workspace else editor
        press_alt_f8(target, qapp)
        assert spy.count() == press
        assert main_window.is_m365_workspace is bool(press % 2)
        assert [main_window.workspace_stack.widget(i) for i in range(2)] == pages
        assert editor.document() is document
        assert len(main_window.findChildren(QTextEdit)) == 1


def test_alt_f8_works_from_m365_form_focus_without_editing_hidden_notes(main_window, qapp):
    show(main_window, qapp)
    editor = main_window._get_active_editor()
    before = editor.toHtml()
    QTest.mouseClick(main_window.toolbar.btn_m365, Qt.LeftButton)
    field = QLineEdit(main_window.m365_workspace)
    main_window.m365_workspace.layout().addWidget(field)
    field.setText("Synthetic unsubmitted parameter")
    field.setFocus()
    qapp.processEvents()
    assert QApplication.focusWidget() is field
    press_alt_f8(field, qapp)
    assert not main_window.is_m365_workspace
    assert field.text() == "Synthetic unsubmitted parameter"
    assert editor.toHtml() == before
    assert main_window.tab_widget.count() == 1


@pytest.mark.parametrize("m365", [False, True])
def test_alt_f8_and_shared_navigation_are_suppressed_by_modal(main_window, qapp, m365):
    show(main_window, qapp)
    if m365:
        main_window.show_m365_workspace()
    dialog = QDialog(main_window)
    dialog.setWindowModality(Qt.ApplicationModal)
    try:
        dialog.show()
        qapp.processEvents()
        assert QApplication.activeModalWidget() is dialog
        press_alt_f8(dialog, qapp)
        assert main_window.is_m365_workspace is m365
        assert main_window.switch_workspace() is False
        assert main_window.is_m365_workspace is m365
    finally:
        dialog.close()
        dialog.deleteLater()
        QCoreApplication.sendPostedEvents(None, QEvent.DeferredDelete)


@pytest.mark.parametrize("running", [False, True])
def test_alt_f8_safely_leaves_hud_and_preserves_normal_state(main_window, qapp, running):
    show(main_window, qapp)
    main_window.create_new_tab()
    main_window.open_split_view()
    main_window.history_drawer.show()
    qapp.processEvents()
    normal_geometry = main_window.geometry()
    main_window.toggle_mini_hud_mode()
    # HUD hides the secondary pane and recreates the native window flags. Send
    # input to its visible focused editor, not a cached pre-HUD hidden widget.
    main_window.activateWindow()
    assert QTest.qWaitForWindowActive(main_window, 1000)
    editor = main_window.tab_widget.get_current_editor()
    editor.setFocus()
    qapp.processEvents()
    assert editor.isVisible() and QApplication.focusWidget() is editor
    saved_geometry = bytes(main_window._saved_normal_geometry)
    stopwatch = main_window.toolbar.stopwatch
    stopwatch.start_timer() if running else stopwatch.pause_timer()
    state = (stopwatch.current_scratchpad_id, stopwatch.elapsed_seconds, stopwatch.is_running)
    press_alt_f8(editor, qapp)
    assert main_window.is_m365_workspace and main_window.is_mini_hud
    assert bool(main_window.windowFlags() & Qt.WindowStaysOnTopHint)
    assert main_window.btn_m365.text() == "T-Notes"
    assert main_window.btn_m365.isEnabled() is True
    assert bytes(main_window._saved_normal_geometry) == saved_geometry
    assert QTest.qWaitForWindowActive(main_window, 1000)
    assert QApplication.focusWidget() is main_window.m365_workspace.back_button
    press_alt_f8(main_window.m365_workspace.back_button, qapp)
    assert not main_window.is_m365_workspace and main_window.is_mini_hud
    assert main_window.btn_m365.text() == "M365 Launcher"
    assert (stopwatch.current_scratchpad_id, stopwatch.elapsed_seconds, stopwatch.is_running) == state
    # Exiting HUD restores normal mode and all controls
    main_window.toggle_mini_hud_mode()
    assert not main_window.is_mini_hud
    assert main_window.toolbar.isVisible()
    assert main_window.secondary_tab_widget.isVisible()
    assert main_window.history_drawer.isVisible()
    assert main_window.geometry() == normal_geometry


@pytest.mark.parametrize("source", ["shortcut", "button"])
def test_alt_f8_and_button_use_the_same_save_failure_guard(main_window, qapp, monkeypatch, source):
    show(main_window, qapp)
    editor = main_window._get_active_editor()
    editor.textCursor().insertText("Synthetic guarded navigation")
    original = main_window.scratchpad_service.save_content
    def fail(*args, **kwargs):
        raise OSError("Synthetic navigation failure")
    monkeypatch.setattr(main_window.scratchpad_service, "save_content", fail)
    if source == "shortcut":
        press_alt_f8(editor, qapp)
    else:
        QTest.mouseClick(main_window.toolbar.btn_m365, Qt.LeftButton)
    assert not main_window.is_m365_workspace
    assert not main_window._workspace_switching
    assert "Synthetic guarded navigation" in editor.toPlainText()
    monkeypatch.setattr(main_window.scratchpad_service, "save_content", original)
    press_alt_f8(editor, qapp)
    assert main_window.is_m365_workspace


def test_workspace_navigation_blocks_reentrancy_and_shutdown(main_window, qapp, monkeypatch):
    show(main_window, qapp)
    editor = main_window._get_active_editor()
    editor.textCursor().insertText("Synthetic reentrant save")
    original = main_window.scratchpad_service.save_content
    attempts = []
    def save(*args, **kwargs):
        attempts.append(main_window.switch_workspace())
        return original(*args, **kwargs)
    monkeypatch.setattr(main_window.scratchpad_service, "save_content", save)
    press_alt_f8(editor, qapp)
    assert attempts == [False]
    assert main_window.is_m365_workspace and not main_window._workspace_switching
    monkeypatch.setattr(main_window, "_force_quit", True)
    assert main_window.switch_workspace() is False
    assert main_window.is_m365_workspace


def test_alt_f8_is_one_nonrepeating_application_shortcut_only(main_window, qapp, monkeypatch):
    from src.core.global_hotkey import GlobalHotkeyManager
    show(main_window, qapp)
    keys = [shortcut.key().toString() for shortcut in main_window.findChildren(QShortcut)]
    assert keys.count("Alt+F8") == 1
    assert main_window.workspace_shortcut.context() == Qt.ApplicationShortcut
    assert not main_window.workspace_shortcut.autoRepeat()
    managers = main_window.findChildren(GlobalHotkeyManager)
    assert len(managers) == 1 and managers[0].key_code == 0x77
    def forbidden(*args, **kwargs):
        pytest.fail("Alt+F8 must not register a system-wide hotkey")
    monkeypatch.setattr(GlobalHotkeyManager, "register", forbidden)
    press_alt_f8(main_window._get_active_editor(), qapp)
    press_alt_f8(main_window.m365_workspace.back_button, qapp)
    assert not main_window.is_m365_workspace


def test_existing_alt_t_alt_z_and_f8_after_alt_f8(main_window, qapp, monkeypatch):
    show(main_window, qapp)
    editor = main_window._get_active_editor()
    press_alt_f8(editor, qapp)
    press_alt_f8(main_window.m365_workspace.back_button, qapp)
    main_window.create_new_tab()
    editor = main_window._get_active_editor()
    QTest.keyClick(editor, Qt.Key_Z, Qt.AltModifier)
    qapp.processEvents()
    assert main_window.secondary_tab_widget.isVisible()
    QTest.keyClick(main_window._get_active_editor(), Qt.Key_T, Qt.AltModifier)
    qapp.processEvents()
    assert main_window.is_mini_hud
    QTest.keyClick(main_window._get_active_editor(), Qt.Key_T, Qt.AltModifier)
    qapp.processEvents()
    assert not main_window.is_mini_hud
    assert main_window.secondary_tab_widget.isVisible()
    monkeypatch.setattr(main_window, "isActiveWindow", lambda: True)
    QTest.keyClick(main_window._get_active_editor(), Qt.Key_F8)
    assert main_window.isMinimized()
    main_window.global_hotkey.activated.emit()
    qapp.processEvents()
    assert main_window.isVisible() and not main_window.isMinimized()


def test_both_visible_navigation_buttons_use_shared_guard(main_window, qapp, monkeypatch):
    show(main_window, qapp)
    monkeypatch.setattr(main_window, "_workspace_switching", True)
    QTest.mouseClick(main_window.toolbar.btn_m365, Qt.LeftButton)
    assert not main_window.is_m365_workspace
    monkeypatch.setattr(main_window, "_workspace_switching", False)
    QTest.mouseClick(main_window.toolbar.btn_m365, Qt.LeftButton)
    assert main_window.is_m365_workspace
    monkeypatch.setattr(main_window, "_workspace_switching", True)
    QTest.mouseClick(main_window.m365_workspace.back_button, Qt.LeftButton)
    assert main_window.is_m365_workspace
    monkeypatch.setattr(main_window, "_workspace_switching", False)
    QTest.mouseClick(main_window.m365_workspace.back_button, Qt.LeftButton)
    assert not main_window.is_m365_workspace



def test_m365_responsive_at_compact_and_high_dpi_viewports(main_window, qapp):
    show(main_window, qapp)
    main_window.show_m365_workspace()
    qapp.processEvents()
    launcher = main_window.m365_workspace

    # Viewports: 1280x720@150% (853x480), 1280x720@125% (1024x576), 1600x900@150% (1066x600), minimum (640x380)
    for tw, th in [(853, 480), (1024, 576), (1066, 600), (640, 380)]:
        main_window.resize(tw, th)
        qapp.processEvents()
        assert main_window.height() <= th, f"Window height {main_window.height()} exceeded target {th}"
        assert main_window.width() <= tw, f"Window width {main_window.width()} exceeded target {tw}"
        assert launcher.back_button.isVisible()
        assert launcher.scroll_area.isVisible()
        groups = {g.title() for g in launcher.findChildren(QGroupBox)}
        assert {"Company Selection", "Authentication & Tenant Context", "Script Catalog",
                "Parameters", "Execution Workspace", "Parsed Results"} <= groups


def test_m365_collapsible_navigation_and_ticket_sidebar(main_window, qapp):
    show(main_window, qapp)
    main_window.show_m365_workspace()
    qapp.processEvents()
    launcher = main_window.m365_workspace

    # Category navigation collapse & expand
    assert launcher.navigation.isVisible()
    QTest.mouseClick(launcher.nav_toggle, Qt.LeftButton)
    qapp.processEvents()
    assert launcher.navigation.isHidden()
    QTest.mouseClick(launcher.nav_toggle, Qt.LeftButton)
    qapp.processEvents()
    assert launcher.navigation.isVisible()

    # Ticket sidebar collapse & expand
    assert launcher.ticket_sidebar.isVisible()
    QTest.mouseClick(launcher.ticket_panel_toggle, Qt.LeftButton)
    qapp.processEvents()
    assert launcher.ticket_sidebar.isHidden()

    # Panel state preservation across workspace switch
    main_window.switch_workspace() # return to notes
    qapp.processEvents()
    main_window.switch_workspace() # return to M365
    qapp.processEvents()
    assert launcher.ticket_sidebar.isHidden() # stays collapsed
    QTest.mouseClick(launcher.ticket_panel_toggle, Qt.LeftButton)
    qapp.processEvents()
    assert launcher.ticket_sidebar.isVisible()


def test_m365_responsive_column_arrangement_retains_widgets(main_window, qapp):
    show(main_window, qapp)
    main_window.show_m365_workspace()
    qapp.processEvents()
    launcher = main_window.m365_workspace

    groups_init = [id(g) for g in launcher._content_groups]
    # Squeeze to single-column threshold (<500px center viewport)
    main_window.resize(640, 400)
    qapp.processEvents()
    assert launcher._current_columns == 1
    groups_1col = [id(g) for g in launcher._content_groups]
    assert groups_init == groups_1col # Identical widget instances preserved

    # Expand to 2-column mode
    main_window.resize(1100, 750)
    qapp.processEvents()
    assert launcher._current_columns == 2
    groups_2col = [id(g) for g in launcher._content_groups]
    assert groups_init == groups_2col # Identical widget instances preserved


def test_workspace_specific_minimum_sizes(main_window, qapp):
    from PySide6.QtCore import QSize
    show(main_window, qapp)
    # Notes workspace minimum size
    assert main_window.minimumSize() == QSize(660, 400)

    # M365 workspace minimum size
    main_window.show_m365_workspace()
    qapp.processEvents()
    assert main_window.minimumSize() == QSize(640, 380)

    # Mini-HUD minimum size
    main_window.toggle_mini_hud_mode()
    qapp.processEvents()
    assert main_window.minimumSize() == QSize(340, 200)

    # Normal M365 restored when exiting HUD while in M365
    main_window.toggle_mini_hud_mode()
    qapp.processEvents()
    assert main_window.minimumSize() == QSize(640, 380)

    # Returning to Notes workspace restores Notes minimum size
    main_window.show_notes_workspace()
    qapp.processEvents()
    assert main_window.minimumSize() == QSize(660, 400)


def test_no_qfont_setpointsize_warnings(main_window, qapp):
    warnings = []
    def warn_handler(msg_type, context, msg):
        if "setPointSize" in msg:
            warnings.append(msg)
    from PySide6.QtCore import qInstallMessageHandler
    qInstallMessageHandler(warn_handler)

    show(main_window, qapp)
    main_window.resize(853, 480)
    qapp.processEvents()
    main_window.switch_workspace()
    qapp.processEvents()
    main_window.switch_workspace()
    qapp.processEvents()
    assert len(warnings) == 0, f"Unexpected QFont warnings caught: {warnings}"

# =========================================================================
# Independent Codex Sol High Review Regressions
# =========================================================================


def test_regression_more_menu_mouse_commands_remain_visible(main_window, qapp):
    show(main_window, qapp)
    main_window.resize(700, 750)
    qapp.processEvents()
    tb = main_window.toolbar
    tb.menu_more.popup(tb.btn_more.mapToGlobal(tb.btn_more.rect().bottomLeft()))
    qapp.processEvents()
    try:
        assert tb.act_timestamp.isVisible() and tb.act_image.isVisible()
    finally:
        tb.menu_more.hide()


def test_regression_compact_f5_works_from_editor(main_window, qapp):
    show(main_window, qapp)
    main_window.resize(700, 750)
    qapp.processEvents()
    ed = main_window.tab_widget.get_current_editor()
    ed.setFocus()
    main_window.activateWindow()
    assert QTest.qWaitForWindowActive(main_window, 1000)
    before = ed.toPlainText()
    QTest.keyClick(ed, Qt.Key_F5)
    qapp.processEvents()
    assert ed.toPlainText() != before


def test_regression_failed_navigation_then_explicit_save_retries_text_and_image(main_window, qapp, monkeypatch):
    show(main_window, qapp)
    ed = main_window.tab_widget.get_current_editor()
    sid = ed.scratchpad_id
    image = QImage(8, 8, QImage.Format_RGB32)
    image.fill(0x123456)
    ed.insert_embedded_image(image)
    ed.insertPlainText("regression failed transition draft")
    names = set(ed.in_memory_images)
    original = main_window.scratchpad_service.save_content
    def fail(**kw):
        raise OSError("Synthetic persistence failure")
    monkeypatch.setattr(main_window.scratchpad_service, "save_content", fail)
    assert not main_window.show_m365_workspace()
    assert sid in main_window._dirty_scratchpad_ids and ed.in_memory_images
    assert not main_window._debounce_timers[sid].is_active()
    monkeypatch.setattr(main_window.scratchpad_service, "save_content", original)
    main_window.flush_all_saves()
    saved = main_window.scratchpad_service.get_ticket(sid)["content_html"]
    images = main_window.image_service.repo.get_images_for_scratchpad(sid)
    assert "regression failed transition draft" in saved and set(images) == names


def test_regression_failed_navigation_then_quit_persists_draft(main_window, qapp, monkeypatch):
    show(main_window, qapp)
    ed = main_window.tab_widget.get_current_editor()
    sid = ed.scratchpad_id
    ed.insertPlainText("regression draft before quit")
    original = main_window.scratchpad_service.save_content
    def fail(**kw):
        raise OSError("Synthetic persistence failure")
    monkeypatch.setattr(main_window.scratchpad_service, "save_content", fail)
    assert not main_window.show_m365_workspace()
    monkeypatch.setattr(main_window.scratchpad_service, "save_content", original)
    main_window.quit_application()
    saved = main_window.scratchpad_service.get_ticket(sid)["content_html"]
    assert "regression draft before quit" in saved


def test_regression_hidden_pane_real_debounce_saves_correct_ticket_images(main_window, qapp):
    show(main_window, qapp)
    main_window.create_new_tab()
    main_window.open_split_view()
    qapp.processEvents()
    primary = main_window.tab_widget.get_current_editor()
    secondary = main_window.secondary_tab_widget.get_current_editor()
    originals = [(ed, ed.document()) for ed in (primary, secondary)]
    for ed, text, color in [(primary, "regression primary draft", 0x123456), (secondary, "regression secondary draft", 0x654321)]:
        image = QImage(8, 8, QImage.Format_RGB32)
        image.fill(color)
        ed.insert_embedded_image(image)
        ed.insertPlainText(text)
    secondary.setFocus()
    main_window._on_editor_focused(secondary.scratchpad_id)
    main_window.resize(700, 750)
    qapp.processEvents()
    assert primary.isHidden() or not primary.isVisible()
    QTest.qWait(1700)
    for ed, text in [(primary, "regression primary draft"), (secondary, "regression secondary draft")]:
        saved = main_window.scratchpad_service.get_ticket(ed.scratchpad_id)["content_html"]
        assert text in saved
        assert len(main_window.image_service.repo.get_images_for_scratchpad(ed.scratchpad_id)) == 1
    assert all(ed.document() is doc for ed, doc in originals)


def test_regression_m365_resize_keeps_notes_history_hidden(main_window, qapp):
    show(main_window, qapp)
    if not main_window.history_drawer.isVisible():
        main_window._toggle_history_drawer()
    assert main_window.history_drawer.isVisible()
    assert main_window.switch_workspace()
    assert main_window.history_drawer.isHidden()
    main_window.resize(700, 750)
    qapp.processEvents()
    main_window.resize(1000, 750)
    qapp.processEvents()
    assert main_window.is_m365_workspace and not main_window.history_drawer.isVisible()


def test_regression_compact_secondary_to_hud_keeps_an_editor_visible(main_window, qapp):
    show(main_window, qapp)
    main_window.resize(700, 750)
    main_window.create_new_tab()
    main_window.open_split_view()
    qapp.processEvents()
    assert not main_window.tab_widget.isVisible() and main_window.secondary_tab_widget.isVisible()
    main_window.toggle_mini_hud_mode()
    qapp.processEvents()
    assert main_window.tab_widget.isVisible() or main_window.secondary_tab_widget.isVisible()


def test_regression_close_from_m365_preserves_secondary_active_ticket(main_window, qapp):
    show(main_window, qapp)
    main_window.create_new_tab()
    main_window.open_split_view()
    qapp.processEvents()
    ed = main_window.secondary_tab_widget.get_current_editor()
    ed.setFocus()
    main_window._on_editor_focused(ed.scratchpad_id)
    assert main_window._get_active_editor() is ed
    assert main_window.switch_workspace()
    main_window.close()
    session = main_window.session_service.session_repo.get_session()
    assert session["active_scratchpad_id"] == ed.scratchpad_id

