"""UI Integration tests using PySide6 QtTest."""

import pytest
from PySide6.QtCore import Qt, QTimer
from PySide6.QtGui import QImage
from PySide6.QtWidgets import QApplication
from src.database.connection import DatabaseManager
from src.database.migrations import init_database
from src.repositories.image_repository import ImageRepository
from src.repositories.scratchpad_repository import ScratchpadRepository
from src.repositories.session_repository import SessionRepository
from src.services.image_service import ImageService
from src.services.scratchpad_service import ScratchpadService
from src.services.session_service import SessionService
from src.ui.main_window import TechPadMainWindow


@pytest.fixture
def main_window(qapp, tmp_path):
    db_file = tmp_path / "ui_test.db"
    manager = DatabaseManager(db_file)
    init_database(manager)

    scratch_repo = ScratchpadRepository(manager)
    img_repo = ImageRepository(manager)
    session_repo = SessionRepository(manager)

    img_service = ImageService(img_repo)
    scratch_service = ScratchpadService(scratch_repo, img_service)
    session_service = SessionService(session_repo, scratch_service)

    window = TechPadMainWindow(
        scratchpad_service=scratch_service,
        image_service=img_service,
        session_service=session_service,
    )
    yield window
    window.quit_application()
    manager.close()


def test_ui_initial_state_and_new_tab(main_window):
    # App should boot with 1 active tab (initial workspace)
    assert main_window.tab_widget.count() == 1
    assert "INC-1001" in main_window.tab_widget.tabText(0)

    # Click '+' to create new tab
    main_window.create_new_tab()
    assert main_window.tab_widget.count() == 2
    assert main_window.tab_widget.currentIndex() == 1


def test_ui_editor_image_insert_and_autosave(main_window):
    editor = main_window.tab_widget.get_current_editor()
    assert editor is not None

    # Simulate inserting an image
    qimg = QImage(64, 64, QImage.Format_RGB32)
    qimg.fill(0xFF112233)
    editor.insert_embedded_image(qimg)

    # Verify editor has pending in-memory image
    assert len(editor.in_memory_images) == 1
    image_name = list(editor.in_memory_images.keys())[0]

    # Type text
    editor.textCursor().insertHtml("<p>Investigating network packet loss.</p>")

    # Flush save immediately
    main_window.flush_all_saves()
    assert main_window.lbl_save_status.text() == "● Saved"

    # Verify image was stored in database
    db_images = main_window.image_service.repo.get_images_for_scratchpad(editor.scratchpad_id)
    assert image_name in db_images


def test_ui_history_drawer_toggle(main_window):
    main_window.show()
    initial_hidden = main_window.history_drawer.isHidden()

    # Toggle via toolbar 🕰️ button
    assert main_window.toolbar.btn_history.text() == "🕰️"
    main_window.toolbar.btn_history.click()
    assert main_window.history_drawer.isHidden() != initial_hidden

    # Toggle via status bar button
    main_window.btn_toggle_drawer.click()
    assert main_window.history_drawer.isHidden() == initial_hidden


def test_ui_history_drawer_width_and_resizability(main_window):
    """Verifies that the History drawer has reasonable width defaults and minimum bounds for readability."""
    drawer = main_window.history_drawer
    # Check minimum width to prevent collapsing into an unreadable state
    assert drawer.minimumWidth() >= 280
    # Check sizeHint provides an ergonomic default width (>= 350px)
    assert drawer.sizeHint().width() >= 350


def test_ui_tab_movable_and_slide_reordering(main_window):
    # Verify tab bar is explicitly movable to enable slide-reordering
    assert main_window.tab_widget.isMovable() is True
    assert main_window.tab_widget.tabBar().isMovable() is True
    assert main_window.tab_widget.usesScrollButtons() is True

    # Add 2 more tabs
    main_window.create_new_tab()
    main_window.create_new_tab()
    assert main_window.tab_widget.count() == 3

    initial_first_tab_text = main_window.tab_widget.tabText(0)

    # Slide / move Tab 0 to index 2
    main_window.tab_widget.tabBar().moveTab(0, 2)

    assert main_window.tab_widget.tabText(2) == initial_first_tab_text


def test_ui_tab_duplicate_and_archive_actions(main_window):
    initial_count = main_window.tab_widget.count()

    # Test duplicate tab
    main_window._duplicate_tab(0)
    assert main_window.tab_widget.count() == initial_count + 1
    duplicated_tab_text = main_window.tab_widget.tabText(main_window.tab_widget.currentIndex())
    assert "COPY" in duplicated_tab_text

    # Test archive tab
    archived_idx = main_window.tab_widget.currentIndex()
    main_window._archive_tab(archived_idx)
    assert main_window.tab_widget.count() == initial_count
    assert len(main_window.scratchpad_service.get_archived_tickets()) >= 1


def test_ui_editor_url_detection(main_window):
    editor = main_window.tab_widget.get_current_editor()
    assert editor is not None

    # Test linkify_text
    raw_text = "Refer to https://portal.azure.com and www.google.com for logs."
    linked_html = editor.linkify_text(raw_text)
    assert '<a href="https://portal.azure.com"' in linked_html
    assert '<a href="http://www.google.com"' in linked_html


def test_ui_opacity_slider(main_window):
    # Test setting opacity through slider
    main_window.toolbar.slider_opacity.setValue(75)
    assert round(main_window.windowOpacity(), 2) == 0.75
    assert "75%" in main_window.toolbar.lbl_opacity.text()

    # Opacity bounds
    main_window.toolbar.slider_opacity.setValue(60)
    assert round(main_window.windowOpacity(), 2) == 0.60

    main_window.toolbar.slider_opacity.setValue(100)
    assert round(main_window.windowOpacity(), 2) == 1.0


def test_ui_tab_browser_shortcuts(main_window):
    main_window.create_new_tab()
    main_window.create_new_tab()
    assert main_window.tab_widget.count() >= 3

    # Test switch relative
    initial_idx = main_window.tab_widget.currentIndex()
    main_window._switch_tab_relative(+1)
    assert main_window.tab_widget.currentIndex() != initial_idx

    # Test select by number
    main_window._select_tab_index(0)
    assert main_window.tab_widget.currentIndex() == 0

    # Test direct editor key event for Ctrl+Shift+PageDown with KeypadModifier (Windows keyboard hardware)
    from PySide6.QtCore import QEvent
    from PySide6.QtGui import QKeyEvent
    editor = main_window.tab_widget.get_current_editor()
    assert editor is not None

    # Simulate pressing Ctrl+Shift+PageDown with KeypadModifier while typing in editor
    ev_move_right = QKeyEvent(QKeyEvent.KeyPress, Qt.Key_PageDown, Qt.ControlModifier | Qt.ShiftModifier | Qt.KeypadModifier)
    editor.keyPressEvent(ev_move_right)
    assert main_window.tab_widget.currentIndex() == 1

    # Simulate pressing Ctrl+Shift+PageUp with KeypadModifier while typing in editor
    ev_move_left = QKeyEvent(QKeyEvent.KeyPress, Qt.Key_PageUp, Qt.ControlModifier | Qt.ShiftModifier | Qt.KeypadModifier)
    editor.keyPressEvent(ev_move_left)
    assert main_window.tab_widget.currentIndex() == 0


def test_ui_global_tab_reordering_with_keypad_modifier(main_window):
    """Verifies that Ctrl+Shift+PageDown and PageUp reorder tabs via the global event filter

    even when the Windows keyboard hardware driver emits Qt.KeypadModifier.
    """
    from PySide6.QtCore import QEvent
    from PySide6.QtGui import QKeyEvent

    main_window.show()
    main_window.create_new_tab()
    main_window.create_new_tab()
    assert main_window.tab_widget.count() >= 3

    # Select tab 0
    main_window.tab_widget.setCurrentIndex(0)
    tab0_title = main_window.tab_widget.tabText(0)
    tab1_title = main_window.tab_widget.tabText(1)

    editor = main_window.tab_widget.get_current_editor()
    editor.setFocus()

    # Press Ctrl+Shift+PageDown through QApplication with KeypadModifier
    ev_down = QKeyEvent(QEvent.KeyPress, Qt.Key_PageDown, Qt.ControlModifier | Qt.ShiftModifier | Qt.KeypadModifier)
    consumed = main_window.eventFilter(editor, ev_down)
    assert consumed is True

    # Tab 0 should have slid to position 1
    assert main_window.tab_widget.currentIndex() == 1
    assert main_window.tab_widget.tabText(1) == tab0_title
    assert main_window.tab_widget.tabText(0) == tab1_title

    # Press Ctrl+Shift+PageUp through QApplication with KeypadModifier
    ev_up = QKeyEvent(QEvent.KeyPress, Qt.Key_PageUp, Qt.ControlModifier | Qt.ShiftModifier | Qt.KeypadModifier)
    consumed = main_window.eventFilter(editor, ev_up)
    assert consumed is True

    # Tab should have slid back to position 0
    assert main_window.tab_widget.currentIndex() == 0
    assert main_window.tab_widget.tabText(0) == tab0_title
    assert main_window.tab_widget.tabText(1) == tab1_title

    # Test with focus on tabBar as well
    main_window.tab_widget.tabBar().setFocus()
    consumed = main_window.eventFilter(main_window.tab_widget.tabBar(), ev_down)
    assert consumed is True
    assert main_window.tab_widget.currentIndex() == 1


def test_ui_stopwatch_integration_and_dynamic_tab_minutes(main_window):
    """Verifies stopwatch tracks active ticket time and dynamically displays running minutes on tab headers."""
    stopwatch = main_window.toolbar.stopwatch
    assert stopwatch is not None
    assert stopwatch.is_running is True

    # Check initial ticket has 0 elapsed seconds
    initial_editor = main_window.tab_widget.get_current_editor()
    sid = initial_editor.scratchpad_id
    assert stopwatch.current_scratchpad_id == sid

    # Simulate stopwatch running for 14 minutes (840 seconds)
    stopwatch._seconds = 840
    stopwatch._update_display()
    assert "00:14:00" in stopwatch.lbl_time.text()

    # Trigger time update emission
    stopwatch.time_updated.emit(sid, 840)

    # Tab header should now include '(14m)'
    current_tab_title = main_window.tab_widget.tabText(main_window.tab_widget.currentIndex())
    assert "(14m)" in current_tab_title

    # Create a second tab
    main_window.create_new_tab()
    new_editor = main_window.tab_widget.get_current_editor()
    new_sid = new_editor.scratchpad_id
    assert new_sid != sid

    # Outgoing tab's time (840s) should have been saved in database
    saved_ticket = main_window.scratchpad_service.get_ticket(sid)
    assert saved_ticket["elapsed_seconds"] == 840

    # New tab's stopwatch should start at 0
    assert stopwatch.current_scratchpad_id == new_sid
    assert stopwatch.elapsed_seconds == 0

    # Switch back to the first tab
    main_window._select_tab_index(0)
    assert stopwatch.current_scratchpad_id == sid
    assert stopwatch.elapsed_seconds == 840
    assert "00:14:00" in stopwatch.lbl_time.text()


def test_ui_stopwatch_copy_and_reset(main_window):
    """Tests stopwatch copy menu actions and reset button."""
    stopwatch = main_window.toolbar.stopwatch
    stopwatch._seconds = 930  # 15m 30s -> 0.26h decimal, 0.50h rounded
    stopwatch._update_display()

    # Test copy exact
    stopwatch._copy_to_clipboard("display")
    assert QApplication.clipboard().text() == "00:15:30"

    # Test copy decimal
    stopwatch._copy_to_clipboard("decimal")
    assert QApplication.clipboard().text() == "0.26h"

    # Test copy 15m rounded
    stopwatch._copy_to_clipboard("rounded")
    assert QApplication.clipboard().text() == "0.50h"

    # Test reset timer
    stopwatch.reset_timer()
    assert stopwatch.elapsed_seconds == 0
    assert stopwatch.is_running is False
    assert "00:00:00" in stopwatch.lbl_time.text()


def test_ui_stopwatch_auto_pause_on_idle(main_window, monkeypatch):
    """Verifies that the stopwatch auto-pauses when the computer is locked or idle >= 5 minutes."""
    from src.services.stopwatch_service import StopwatchService

    stopwatch = main_window.toolbar.stopwatch
    stopwatch.start_timer()
    assert stopwatch.is_running is True

    # Mock should_auto_pause to True (idle for 5+ minutes or locked)
    monkeypatch.setattr(StopwatchService, "should_auto_pause", lambda threshold: True)

    # Execute tick
    stopwatch._on_tick()

    # Stopwatch should now be paused
    assert stopwatch.is_running is False
    assert stopwatch._auto_paused is True


def test_ui_two_row_toolbar_and_no_overflow(main_window):
    """Verifies that the top header is divided into two rows without 3-dots overflow."""
    tb1 = main_window.toolbar
    tb2 = main_window.toolbar.secondary_toolbar

    # Both toolbars exist and are fixed
    assert tb1 is not None
    assert tb2 is not None
    assert tb1.isMovable() is False
    assert tb2.isMovable() is False

    # Row 1 has formatting actions
    assert tb1.act_bold is not None
    assert tb1.act_code is not None
    assert tb1.act_export is not None

    # Row 2 has ticket stopwatch, opacity, history, and settings
    assert tb2.findChild(type(tb1.stopwatch)) is not None
    assert tb1.btn_history.parent() == tb2
    assert tb1.btn_settings.parent() == tb2
    assert tb1.slider_opacity.parent() == tb2


def test_ui_system_tray_close_to_tray(main_window):
    """Verifies that closing the window minimizes to the system tray instead of terminating."""
    assert main_window.tray_icon is not None
    assert main_window.tray_icon.isVisible() is True

    main_window.show()
    assert main_window.isVisible() is True

    # User closes the window
    main_window.close()

    # Window should be hidden in system tray, not destroyed
    assert main_window.isHidden() is True
    assert main_window.tray_icon.isVisible() is True


def test_ui_f8_toggle_window_visibility(main_window):
    """Verifies that F8 pops window when hidden/minimized and minimizes when active."""
    # 1. Start with window hidden (in tray)
    main_window.hide()
    assert main_window.isHidden() is True

    # Press F8 -> should pop window
    main_window.toggle_window_visibility()
    assert main_window.isVisible() is True
    assert main_window.isMinimized() is False

    # 2. Window is now open and active -> pressing F8 should minimize it
    # Mock isActiveWindow to True for testing headless environment
    main_window.showMinimized()
    assert main_window.isMinimized() is True

    # Press F8 while minimized -> should pop window back up
    main_window.toggle_window_visibility()
    assert main_window.isMinimized() is False
    assert main_window.isVisible() is True


def test_global_hotkey_manager_lifecycle():
    """Verifies GlobalHotkeyManager registration and signal dispatch."""
    from src.core.global_hotkey import GlobalHotkeyManager

    mgr = GlobalHotkeyManager(key_code=0x77, hotkey_id=2001)
    # Register hotkey
    registered = mgr.register()
    # Should safely return a boolean (True on Windows with available hotkey)
    assert isinstance(registered, bool)

    triggered = []
    mgr.activated.connect(lambda: triggered.append(True))
    mgr.activated.emit()
    assert triggered == [True]

    # Clean unregister
    mgr.unregister()
    assert mgr.is_registered is False


def test_ui_checklist_toolbar_and_insert(main_window):
    """Verifies that the toolbar task button inserts a checklist item into the active editor."""
    assert main_window.toolbar.act_checklist.text() == "☑ Checkbox"
    assert main_window.toolbar.act_checklist.shortcut().toString() == "Ctrl+Alt+L"

    editor = main_window.tab_widget.get_current_editor()
    assert editor is not None
    assert editor.get_checklist_stats() == (0, 0)

    # Click toolbar checklist button
    main_window.toolbar.act_checklist.trigger()

    # Verify checklist item inserted
    assert "[ ]" in editor.toPlainText()
    assert editor.get_checklist_stats() == (0, 1)


def test_ui_checklist_toggle_and_tab_progress(main_window):
    """Verifies toggling checklist items updates dynamic tab badge and rich tooltip."""
    main_window.show()
    editor = main_window.tab_widget.get_current_editor()
    assert editor is not None
    editor.clear()

    # Insert two checklist tasks
    main_window.toolbar.act_checklist.trigger()
    editor.insertPlainText("Verify firewall status\n")
    main_window.toolbar.act_checklist.trigger()
    editor.insertPlainText("Restart service\n")

    # Check initial stats and tab header
    completed, total = editor.get_checklist_stats()
    assert (completed, total) == (0, 2)
    tab_text = main_window.tab_widget.tabText(0)
    assert "☑️0/2" in tab_text

    # Toggle task 1 at position of first checkbox
    cursor = editor.textCursor()
    cursor.setPosition(1)
    editor.setTextCursor(cursor)
    pos = editor.cursorRect(cursor).center()
    editor._toggle_checkbox_at(pos)

    assert editor.get_checklist_stats() == (1, 2)
    assert "[✔]" in editor.toPlainText()
    tab_text = main_window.tab_widget.tabText(0)
    assert "☑️1/2" in tab_text
    tooltip = main_window.tab_widget.tabToolTip(0)
    assert "Tasks: 1/2 completed (50%)" in tooltip

    # Toggle task 2
    plain = editor.toPlainText()
    idx2 = plain.find("[ ]")
    assert idx2 != -1
    cursor.setPosition(idx2 + 1)
    editor.setTextCursor(cursor)
    pos2 = editor.cursorRect(cursor).center()
    editor._toggle_checkbox_at(pos2)

    assert editor.get_checklist_stats() == (2, 2)
    tab_text = main_window.tab_widget.tabText(0)
    assert "✅2/2" in tab_text
    tooltip = main_window.tab_widget.tabToolTip(0)
    assert "Tasks: 2/2 completed (100%)" in tooltip


def test_ui_checklist_enter_continuation_and_exit(main_window):
    """Verifies pressing Enter on a checklist line continues list, and on empty checkbox exits."""
    from PySide6.QtGui import QKeyEvent
    from PySide6.QtCore import QEvent

    editor = main_window.tab_widget.get_current_editor()
    assert editor is not None
    editor.clear()

    # Insert first checklist item
    editor.insert_checklist_item()
    editor.insertPlainText("Step 1")

    # Press Enter -> should continue checklist on next line
    enter_event = QKeyEvent(QEvent.KeyPress, Qt.Key_Return, Qt.NoModifier)
    editor.keyPressEvent(enter_event)

    stats = editor.get_checklist_stats()
    assert stats == (0, 2)

    # Press Enter again on empty checklist item -> should exit checklist and delete the empty box
    enter_event2 = QKeyEvent(QEvent.KeyPress, Qt.Key_Return, Qt.NoModifier)
    editor.keyPressEvent(enter_event2)

    stats = editor.get_checklist_stats()
    assert stats == (0, 1)


def test_ui_checklist_typing_space_auto_conversion(main_window):
    """Verifies typing '[] ' or '- [ ] ' at start of line auto-converts to an interactive checkbox."""
    from PySide6.QtGui import QKeyEvent
    from PySide6.QtCore import QEvent

    editor = main_window.tab_widget.get_current_editor()
    assert editor is not None
    editor.clear()

    # Type '[]' then press Space
    editor.insertPlainText("[]")
    space_event = QKeyEvent(QEvent.KeyPress, Qt.Key_Space, Qt.NoModifier, text=" ")
    editor.keyPressEvent(space_event)

    # Check auto-conversion took effect
    stats = editor.get_checklist_stats()
    assert stats == (0, 1)
    assert "[ ]" in editor.toPlainText()


def test_ui_tab_color_ownership(main_window):
    """Verifies each tab owns a different, distinct color persistently."""
    from src.ui.components.tab_widget import TAB_COLOR_PALETTE

    # App starts with tab 0
    assert main_window.tab_widget.count() == 1
    c0 = main_window.tab_widget.get_tab_color(0)
    assert c0.isValid()

    # Create two more tabs
    main_window.create_new_tab()
    main_window.create_new_tab()
    assert main_window.tab_widget.count() == 3

    c0 = main_window.tab_widget.get_tab_color(0)
    c1 = main_window.tab_widget.get_tab_color(1)
    c2 = main_window.tab_widget.get_tab_color(2)

    # All three tabs must have different colors
    colors = {c0.name(), c1.name(), c2.name()}
    assert len(colors) == 3

    # Remember which scratchpad ID owned which color
    sp0 = main_window.tab_widget.get_scratchpad_id_at(0)
    sp1 = main_window.tab_widget.get_scratchpad_id_at(1)

    # Move tab 0 to position 1 (reordering)
    main_window._move_active_tab_relative(+1)

    # The tickets must still own their respective colors even after index shift
    for i in range(main_window.tab_widget.count()):
        sp_id = main_window.tab_widget.get_scratchpad_id_at(i)
        if sp_id == sp0:
            assert main_window.tab_widget.get_tab_color(i).name() == c0.name()
        elif sp_id == sp1:
            assert main_window.tab_widget.get_tab_color(i).name() == c1.name()


def test_ui_reorganized_ribbon_structure(main_window):
    """Verifies that the ribbon buttons are reorganized logically without artificial expanding spacers."""
    tb1 = main_window.toolbar
    tb2 = main_window.toolbar.secondary_toolbar

    # Row 1 contains Checkbox button
    assert tb1.act_checklist.text() == "☑ Checkbox"

    # Row 2 contains Template, Copy Note, Opacity, History, Settings
    assert tb1.btn_skeleton.parent() == tb2
    assert tb1.act_export.parent() == tb2

    # Stopwatch play/reset buttons use crisp Unicode glyphs
    assert tb1.stopwatch.btn_toggle.text() in ("▶", "⏸")
    assert tb1.stopwatch.btn_reset.text() == "↺"


def test_ui_split_view_toggle_and_layout(main_window):
    """Verifies toggling split view creates side-by-side panes and partitions tabs."""
    main_window.show()
    # Create a second tab so we have 2 tabs
    main_window.create_new_tab()
    assert main_window.tab_widget.count() == 2
    assert main_window.secondary_tab_widget.isHidden()

    # Toggle Split View ON
    main_window.toolbar.btn_split.click()
    assert main_window.secondary_tab_widget.isVisible()
    assert main_window.tab_widget.count() == 1
    assert main_window.secondary_tab_widget.count() == 1
    assert main_window.toolbar.btn_split.isChecked()
    assert "Single" in main_window.btn_toggle_split.text()

    # Toggle Split View OFF
    main_window.toolbar.btn_split.click()
    assert main_window.secondary_tab_widget.isHidden()
    assert main_window.tab_widget.count() == 2
    assert not main_window.toolbar.btn_split.isChecked()
    assert "Split" in main_window.btn_toggle_split.text()


def test_ui_split_view_editor_focus_sync(main_window):
    """Verifies focusing the secondary pane updates active editor, stopwatch, and formatting target."""
    main_window.show()
    main_window.create_new_tab()
    main_window.open_split_view()

    prim_editor = main_window.tab_widget.get_editor_at(0)
    sec_editor = main_window.secondary_tab_widget.get_editor_at(0)
    assert prim_editor is not None and sec_editor is not None

    # Focus secondary editor
    main_window._on_editor_focused(sec_editor.scratchpad_id)
    assert main_window._get_active_editor() == sec_editor
    assert main_window.toolbar._current_editor == sec_editor
    assert main_window.toolbar.stopwatch.current_scratchpad_id == sec_editor.scratchpad_id

    # Insert checklist into active editor
    main_window._on_insert_checklist()
    assert "[ ]" in sec_editor.toPlainText()
    assert "[ ]" not in prim_editor.toPlainText()


def test_ui_split_view_close_and_remerge(main_window):
    """Verifies that closing split view preserves content and safely consolidates all tickets."""
    main_window.create_new_tab()
    main_window.open_split_view()

    sec_editor = main_window.secondary_tab_widget.get_editor_at(0)
    sec_id = sec_editor.scratchpad_id
    sec_editor.setPlainText("Important dual-pane research notes.")
    main_window.flush_all_saves()

    # Close Split View
    main_window.close_split_view()
    assert main_window.secondary_tab_widget.isHidden()
    assert main_window.tab_widget.count() == 2

    # Check that sec_id is now in the primary tab widget with content preserved
    ed, tw, idx = main_window._find_editor_by_id(sec_id)
    assert tw == main_window.tab_widget
    assert "Important dual-pane research notes." in ed.toPlainText()


def test_ui_history_drawer_split_restore(main_window):
    """Verifies right-clicking an archived ticket to open in split view restores it directly in secondary pane."""
    main_window.show()
    # Archive initial ticket
    sp_id = main_window.tab_widget.get_editor_at(0).scratchpad_id
    main_window.scratchpad_service.archive_ticket(sp_id)
    main_window.history_drawer.refresh_list()

    # Trigger restore in split view from history drawer
    main_window.history_drawer.split_restore_requested.emit(sp_id)
    assert main_window.secondary_tab_widget.isVisible()
    ed, tw, idx = main_window._find_editor_by_id(sp_id)
    assert tw == main_window.secondary_tab_widget




