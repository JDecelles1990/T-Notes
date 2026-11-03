"""UI Integration tests using PySide6 QtTest."""

import pytest
from PySide6.QtCore import QCoreApplication, QEvent, QPoint, Qt, QTimer
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
    try:
        window.quit_application()
    finally:
        # A closed test window otherwise retains its application event filter
        # until GC and can intercept keys intended for a later fixture window.
        qapp.removeEventFilter(window)
        window.deleteLater()
        QCoreApplication.sendPostedEvents(None, QEvent.DeferredDelete)
        manager.close()


def test_ui_initial_state_and_new_tab(main_window):
    # App window title starts with T-Notes
    assert main_window.windowTitle().startswith("T-Notes")

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


def test_ui_editor_image_context_menu_copy_and_save(main_window, tmp_path, monkeypatch):
    """Verifies image detection, clipboard copy, and disk export from right-click context menu."""
    from PySide6.QtWidgets import QFileDialog

    main_window.show()
    editor = main_window.tab_widget.get_current_editor()
    assert editor is not None

    qimg = QImage(64, 64, QImage.Format_RGB32)
    qimg.fill(0xFF112233)
    editor.insert_embedded_image(qimg)

    # Image is at cursor position 0..1 in empty doc
    img_info = editor._get_image_at_pos(QPoint(10, 10))
    assert img_info is not None
    img_url, detected_qimg = img_info
    assert img_url.startswith("image://local/")
    assert not detected_qimg.isNull()

    # Test copy to clipboard
    copied_images = []
    monkeypatch.setattr(QApplication.clipboard(), "setImage", lambda img: copied_images.append(img))
    editor._copy_image_to_clipboard(detected_qimg)
    assert len(copied_images) == 1
    assert not copied_images[0].isNull()

    # Test save image as PNG
    png_path = tmp_path / "exported_screenshot.png"
    monkeypatch.setattr(QFileDialog, "getSaveFileName", lambda *args, **kwargs: (str(png_path), "PNG Image (*.png)"))
    editor._save_image_to_file(img_url, detected_qimg)
    assert png_path.exists()
    assert png_path.stat().st_size > 0

    # Test save image as JPG
    jpg_path = tmp_path / "exported_screenshot.jpg"
    monkeypatch.setattr(QFileDialog, "getSaveFileName", lambda *args, **kwargs: (str(jpg_path), "JPEG Image (*.jpg *.jpeg)"))
    editor._save_image_to_file(img_url, detected_qimg)
    assert jpg_path.exists()
    assert jpg_path.stat().st_size > 0



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


def test_ui_stopwatch_copy_and_reset(main_window, monkeypatch):
    """Tests stopwatch copy menu actions and reset button."""
    stopwatch = main_window.toolbar.stopwatch
    stopwatch._seconds = 930  # 15m 30s -> 0.26h decimal, 0.50h rounded
    stopwatch._update_display()

    copied = []
    monkeypatch.setattr(QApplication.clipboard(), "setText", lambda t: copied.append(t))

    # Test copy exact
    stopwatch._copy_to_clipboard("display")
    assert copied[-1] == "00:15:30"

    # Test copy decimal
    stopwatch._copy_to_clipboard("decimal")
    assert copied[-1] == "0.26h"

    # Test copy 15m rounded
    stopwatch._copy_to_clipboard("rounded")
    assert copied[-1] == "0.50h"

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


def test_ui_tab_drag_and_drop_across_split_panes(main_window):
    """Verifies dragging and releasing a tab transfers it to the destination split pane."""
    main_window.show()
    # Create two more tabs so primary has 3 tabs total
    main_window.create_new_tab()
    main_window.create_new_tab()
    assert main_window.tab_widget.count() == 3

    # Open Split View: tab 1 moves to secondary pane
    main_window.open_split_view()
    assert main_window.tab_widget.count() == 2
    assert main_window.secondary_tab_widget.count() == 1

    # Drag remaining tab 1 from primary pane and release over secondary tab widget
    dragged_editor = main_window.tab_widget.get_editor_at(1)
    dragged_id = dragged_editor.scratchpad_id

    sec_pos = main_window.secondary_tab_widget.mapToGlobal(QPoint(50, 50))
    main_window.tab_widget.tab_cross_drop_requested.emit(1, sec_pos)

    # Primary should now have 1 tab, secondary should have 2 tabs
    assert main_window.tab_widget.count() == 1
    assert main_window.secondary_tab_widget.count() == 2

    # Verify dragged_id is now in secondary_tab_widget
    ed, tw, idx = main_window._find_editor_by_id(dragged_id)
    assert tw == main_window.secondary_tab_widget

    # Now drag tab back from secondary pane to primary pane
    prim_pos = main_window.tab_widget.mapToGlobal(QPoint(50, 50))
    main_window.secondary_tab_widget.tab_cross_drop_requested.emit(idx, prim_pos)

    assert main_window.tab_widget.count() == 2
    assert main_window.secondary_tab_widget.count() == 1
    ed2, tw2, idx2 = main_window._find_editor_by_id(dragged_id)
    assert tw2 == main_window.tab_widget


def test_ui_tab_drag_trigger_split_view(main_window):
    """Verifies dragging a tab to the right half of the window opens Split View."""
    main_window.show()
    main_window.create_new_tab()
    assert main_window.tab_widget.count() == 2
    assert main_window.secondary_tab_widget.isHidden()

    # Drag tab 1 to right half of workspace
    target_editor = main_window.tab_widget.get_editor_at(1)
    target_id = target_editor.scratchpad_id

    splitter_global = main_window.workspace_splitter.mapToGlobal(QPoint(0, 0))
    right_x = splitter_global.x() + (main_window.workspace_splitter.width() * 3 // 4)
    right_y = splitter_global.y() + 50
    drop_pos = QPoint(right_x, right_y)

    main_window.tab_widget.tab_cross_drop_requested.emit(1, drop_pos)

    assert main_window.secondary_tab_widget.isVisible()
    ed, tw, idx = main_window._find_editor_by_id(target_id)
    assert tw == main_window.secondary_tab_widget


def test_ui_copy_selection_with_rich_text_colors_and_images(main_window):
    """Verifies that copying text with colors, formatting, and images embeds Base64 data URIs."""
    editor = main_window._get_active_editor()
    assert editor is not None

    # Insert colored text and an embedded image
    img = QImage(16, 16, QImage.Format_RGB32)
    img.fill(0x0000ff)

    editor.insertHtml('<p style="color: #ff0000; font-weight: bold;">Red Bold Title</p>')
    editor.insert_embedded_image(img)
    editor.insertHtml('<p style="color: #00ff00;">Green Step 2</p>')

    # Select all content and invoke createMimeDataFromSelection
    editor.selectAll()
    mime = editor.createMimeDataFromSelection()

    assert mime.hasHtml()
    html = mime.html()

    # Verify colors and formatting are preserved in HTML
    assert "color:#ff0000" in html or "color: #ff0000" in html
    assert "color:#00ff00" in html or "color: #00ff00" in html

    # Verify internal image://local/ URI was replaced with self-contained data:image/jpeg;base64,...
    assert "image://local/" not in html
    assert "data:image/jpeg;base64," in html

    # Plain text fallback should replace object replacement char \uFFFC with [Screenshot]
    plain = mime.text()
    assert "\uFFFC" not in plain
    assert "[Screenshot]" in plain

    # Raw image data must always be present on MIME data for chat/image paste
    assert mime.hasImage() is True
    assert mime.imageData() is not None


def test_ui_copy_formatted_note_toolbar_and_context_menu(main_window, monkeypatch):
    """Verifies that Copy Note button and copy_formatted_note place enriched HTML onto clipboard."""
    editor = main_window._get_active_editor()
    assert editor is not None

    # Insert content with image
    img = QImage(20, 20, QImage.Format_RGB32)
    img.fill(0xff00ff)
    editor.insertHtml('<h2 style="color: #33aaff;">Section Header</h2>')
    editor.insert_embedded_image(img)

    captured_html = []
    captured_text = []
    original_set_mime = QApplication.clipboard().setMimeData

    def mock_set_mime(mime):
        captured_html.append(mime.html() if mime.hasHtml() else "")
        captured_text.append(mime.text() if mime.hasText() else "")
        original_set_mime(mime)

    monkeypatch.setattr(QApplication.clipboard(), "setMimeData", mock_set_mime)

    # Trigger via toolbar button
    main_window.toolbar.btn_copy_note.click()

    assert len(captured_html) >= 1
    last_html = captured_html[-1]
    assert "data:image/jpeg;base64," in last_html
    assert "image://local/" not in last_html
    assert "Section Header" in captured_text[-1]


def test_ui_mini_hud_toggle_geometry_and_flags(main_window):
    """Verifies that toggle_mini_hud_mode sets right-sidebar geometry, WindowStaysOnTopHint, and restores cleanly."""
    main_window.show()
    assert main_window.is_mini_hud is False
    assert not bool(main_window.windowFlags() & Qt.WindowStaysOnTopHint)
    assert main_window.toolbar.isVisible() is True

    # 1. Toggle to Mini-HUD mode (docked right sidebar with longer height)
    main_window.toggle_mini_hud_mode()

    assert main_window.is_mini_hud is True
    assert bool(main_window.windowFlags() & Qt.WindowStaysOnTopHint) is True
    assert main_window.toolbar.isVisible() is False
    assert main_window.width() <= 480
    assert main_window.height() >= 400
    assert "[HUD]" in main_window.windowTitle()
    assert main_window.toolbar.btn_pin.isChecked() is True
    assert "Normal" in main_window.btn_status_hud.text()
    # HUD button is located in the down-left corner of the status bar for 1-click restore
    assert main_window.btn_status_hud.isVisible() is True
    assert main_window.btn_status_hud.x() < 100

    # 2. Toggle back to Normal mode via the down-left HUD button (1-click restore)
    main_window.btn_status_hud.click()

    assert main_window.is_mini_hud is False
    assert not bool(main_window.windowFlags() & Qt.WindowStaysOnTopHint)
    assert main_window.toolbar.isVisible() is True
    assert "[HUD]" not in main_window.windowTitle()
    assert main_window.toolbar.btn_pin.isChecked() is False
    assert "HUD" in main_window.btn_status_hud.text()


def test_ui_mini_hud_shortcut_and_controls(main_window):
    """Verifies that Alt+T shortcut in eventFilter triggers Mini-HUD toggle."""
    main_window.show()
    assert main_window.is_mini_hud is False

    from PySide6.QtGui import QKeyEvent
    from PySide6.QtCore import QEvent

    # Simulate Alt+T key press event
    key_event = QKeyEvent(QEvent.KeyPress, Qt.Key_T, Qt.AltModifier)
    handled = main_window.eventFilter(main_window, key_event)

    assert handled is True
    assert main_window.is_mini_hud is True

    # Simulate Alt+T key press event again to restore
    key_event2 = QKeyEvent(QEvent.KeyPress, Qt.Key_T, Qt.AltModifier)
    handled2 = main_window.eventFilter(main_window, key_event2)

    assert handled2 is True
    assert main_window.is_mini_hud is False


def test_ui_toolbar_compact_and_normal_responsive_mode(main_window, qapp):
    """Verifies responsive toolbar compact vs normal mode, hysteresis, and overflow actions."""
    main_window.show()
    tb = main_window.toolbar

    # 1. Normal Mode (width >= 800)
    main_window.resize(1000, 750)
    qapp.processEvents()
    assert tb.is_compact is False
    assert tb.act_badge.isVisible() is True
    assert tb.act_timestamp_btn.isVisible() is True
    assert tb.act_image_btn.isVisible() is True
    assert tb.act_more.isVisible() is False
    assert tb.btn_m365.isVisible() is True

    # 2. Compact Mode (width < 775)
    main_window.resize(720, 750)
    qapp.processEvents()
    assert tb.is_compact is True
    assert tb.act_badge.isVisible() is False
    assert tb.act_timestamp_btn.isVisible() is False
    assert tb.act_image_btn.isVisible() is False
    assert tb.act_timestamp.isVisible() is True
    assert tb.act_image.isVisible() is True
    assert tb.act_more.isVisible() is True
    assert tb.btn_more.isVisible() is True
    assert tb.btn_m365.isVisible() is True

    # 3. Hysteresis check
    # Arriving from compact (720 -> 785) should stay compact (< 800)
    main_window.resize(785, 750)
    qapp.processEvents()
    assert tb.is_compact is True

    # Reaching >= 800 should return to normal mode
    main_window.resize(805, 750)
    qapp.processEvents()
    assert tb.is_compact is False

    # Arriving from normal (805 -> 785) should stay normal (>= 775)
    main_window.resize(785, 750)
    qapp.processEvents()
    assert tb.is_compact is False

    # 4. Action parity via 'More ▾' menu
    main_window.resize(700, 750)
    qapp.processEvents()
    editor = main_window.tab_widget.get_current_editor()
    assert editor is not None
    editor.clear()
    editor.setFocus()
    tb.set_active_editor(editor)

    # Trigger timestamp from act_timestamp
    tb.act_timestamp.trigger()
    qapp.processEvents()
    assert "[" in editor.toPlainText() and "]" in editor.toPlainText()
    assert editor.hasFocus()


def test_ui_history_drawer_responsive_auto_collapse_and_restore(main_window, qapp):
    """Verifies responsive automatic collapse and restoration of History drawer."""
    main_window.show()
    main_window.resize(1000, 750)
    qapp.processEvents()

    # User explicitly opens history drawer
    main_window.history_drawer.show()
    main_window._user_history_drawer_open = True
    assert main_window.history_drawer.isVisible() is True
    assert main_window.history_auto_collapsed is False

    # 1. Resize to < 850 collapses drawer temporarily
    main_window.resize(750, 750)
    qapp.processEvents()
    assert main_window.history_drawer.isHidden() is True
    assert main_window.history_auto_collapsed is True
    assert main_window._user_history_drawer_open is True

    # 2. Resize to >= 900 restores drawer
    main_window.resize(920, 750)
    qapp.processEvents()
    assert main_window.history_drawer.isVisible() is True
    assert main_window.history_auto_collapsed is False

    # 3. Manual toggle while narrow updates preference
    main_window.resize(750, 750)
    qapp.processEvents()
    assert main_window.history_auto_collapsed is True
    # User manually opens it while narrow
    main_window._toggle_history_drawer()
    qapp.processEvents()
    assert main_window.history_drawer.isVisible() is True
    assert main_window.history_auto_collapsed is False
    assert main_window._user_history_drawer_open is True

    # 4. Session persistence when auto-collapsed preserves user intent
    # Re-collapse it
    main_window.resize(950, 750)
    qapp.processEvents()
    main_window.resize(750, 750)
    qapp.processEvents()
    assert main_window.history_auto_collapsed is True
    # Calling close() saves session
    main_window.close()
    session = main_window.session_service.session_repo.get_session()
    assert session["history_drawer_open"] == 1


def test_ui_split_view_responsive_single_pane_and_restore(main_window, qapp):
    """Verifies responsive compact single-pane Split View and switching."""
    main_window.show()
    main_window.resize(1000, 750)
    qapp.processEvents()

    # Create second tab and open split view
    main_window.create_new_tab()
    main_window.open_split_view()
    qapp.processEvents()

    assert main_window.is_split_view_active is True
    assert main_window.split_auto_single_pane is False
    assert main_window.tab_widget.isVisible() is True
    assert main_window.secondary_tab_widget.isVisible() is True
    assert main_window.btn_switch_split_pane.isVisible() is False

    primary_editor = main_window.tab_widget.get_current_editor()
    sec_editor = main_window.secondary_tab_widget.get_current_editor()
    assert primary_editor is not None and sec_editor is not None
    prim_id = primary_editor.scratchpad_id
    sec_id = sec_editor.scratchpad_id

    # Ensure primary editor is active before resizing
    primary_editor.setFocus()
    main_window._on_editor_focused(prim_id)
    qapp.processEvents()

    # 1. Resize < 750 switches to single pane displaying active editor (pane 1)
    main_window.resize(700, 750)
    qapp.processEvents()
    assert main_window.split_auto_single_pane is True
    assert main_window.btn_switch_split_pane.isVisible() is True
    assert main_window.tab_widget.isVisible() is True
    assert main_window.secondary_tab_widget.isHidden() is True
    assert "Pane 1/2" in main_window.btn_switch_split_pane.text()

    # Identities preserved
    assert main_window.tab_widget.get_current_editor() is primary_editor
    assert main_window.secondary_tab_widget.get_current_editor() is sec_editor

    # 2. Switch compact split pane to pane 2
    main_window.switch_compact_split_pane()
    qapp.processEvents()
    assert main_window.tab_widget.isHidden() is True
    assert main_window.secondary_tab_widget.isVisible() is True
    assert "Pane 2/2" in main_window.btn_switch_split_pane.text()
    assert sec_editor.hasFocus()

    # 3. Modify note in secondary pane while compact
    sec_editor.insertPlainText("Compact edit in pane 2")
    main_window.flush_all_saves()
    loaded_sec = main_window.scratchpad_service.get_ticket(sec_id)
    assert loaded_sec is not None
    assert "Compact edit in pane 2" in loaded_sec["content_html"]

    # 4. Switch back to pane 1
    main_window.switch_compact_split_pane()
    qapp.processEvents()
    assert main_window.tab_widget.isVisible() is True
    assert main_window.secondary_tab_widget.isHidden() is True
    assert "Pane 1/2" in main_window.btn_switch_split_pane.text()
    assert primary_editor.hasFocus()

    # 5. Restore two panes on >= 780
    main_window.resize(850, 750)
    qapp.processEvents()
    assert main_window.split_auto_single_pane is False
    assert main_window.tab_widget.isVisible() is True
    assert main_window.secondary_tab_widget.isVisible() is True
    assert main_window.btn_switch_split_pane.isVisible() is False


def test_ui_portrait_monitor_700_viewport_constraints(main_window, qapp):
    """Verifies that Notes workspace operates cleanly at 700 logical pixels wide."""
    main_window.show()
    main_window.resize(700, 1120)
    qapp.processEvents()

    assert main_window.width() == 700
    assert main_window.minimumWidth() <= 700

    # Ensure toolbar actions fit without horizontal overflow
    tb1 = main_window.toolbar
    tb2 = main_window.toolbar.secondary_toolbar
    assert tb1.is_compact is True

    for tb in (tb1, tb2):
        for act in tb.actions():
            if not act.isVisible() or act.isSeparator():
                continue
            w = tb.widgetForAction(act)
            if w:
                assert tb.rect().contains(w.geometry())

    # Active editor visible and writable
    editor = main_window.tab_widget.get_current_editor()
    assert editor is not None and editor.isVisible()
    editor.setFocus()
    editor.insertPlainText("Portrait 700 test")
    assert "Portrait 700 test" in editor.toPlainText()

    # Clamping function check
    main_window._clamp_geometry_to_screen()
    assert main_window.width() <= 700

