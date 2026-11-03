"""Synthetic regression coverage for archive, shutdown and atomic note saves."""

import sqlite3
from unittest.mock import Mock

import pytest
from PySide6.QtGui import QCloseEvent, QImage
from PySide6.QtWidgets import QMessageBox

from test_ui_integration import main_window
from test_scratchpad_service import services


def fail(*args, **kwargs):
    raise OSError("synthetic persistence failure")


@pytest.mark.parametrize("route", ["primary", "secondary", "prompt_primary", "prompt_secondary", "others"])
def test_failed_idle_save_blocks_every_archive_route(main_window, monkeypatch, route):
    w = main_window
    if route == "others":
        w.create_new_tab()
    editor = w.tab_widget.get_current_editor()
    sid = editor.scratchpad_id
    if "secondary" in route:
        w._move_tab_between_panes(w.tab_widget, w.secondary_tab_widget, w.tab_widget.currentIndex())
    editor.textCursor().insertText("UNSAVED synthetic archive draft")
    image = QImage(4, 4, QImage.Format_RGB32)
    image.fill(0x123456)
    editor.insert_embedded_image(image)
    before_html = editor.toHtml()
    before_images = dict(editor.in_memory_images)
    before_undo = editor.document().isUndoAvailable()
    original = w.scratchpad_service.save_content
    monkeypatch.setattr(w.scratchpad_service, "save_content", fail)
    assert not w.flush_all_saves()
    assert not w._debounce_timers[sid].is_active()
    if route.startswith("prompt"):
        monkeypatch.setattr(QMessageBox, "exec", lambda self: 0)
        monkeypatch.setattr(QMessageBox, "clickedButton", lambda self: self.buttons()[0])
    action = {
        "primary": lambda: w._archive_tab(w.tab_widget.indexOf(editor)),
        "secondary": lambda: w._archive_secondary_tab(w.secondary_tab_widget.indexOf(editor)),
        "prompt_primary": lambda: w._on_tab_close_requested(w.tab_widget.indexOf(editor)),
        "prompt_secondary": lambda: w._on_secondary_tab_close_requested(w.secondary_tab_widget.indexOf(editor)),
        "others": lambda: w._close_other_tabs(0),
    }[route]
    action()
    assert w.scratchpad_service.get_ticket(sid)["status"] == "active"
    assert w._find_editor_by_id(sid)[0] is editor
    assert sid in w._dirty_scratchpad_ids
    assert editor.toHtml() == before_html
    assert editor.in_memory_images == before_images
    assert editor.document().isUndoAvailable() == before_undo
    assert "Save Failed" in w.lbl_save_status.text()
    monkeypatch.setattr(w.scratchpad_service, "save_content", original)
    action()  # Explicit retry without another edit.
    assert w.scratchpad_service.get_ticket(sid)["status"] == "archived"
    w.scratchpad_service.restore_ticket(sid)
    assert "UNSAVED synthetic archive draft" in w.scratchpad_service.get_ticket(sid)["content_html"]
    assert w.image_service.repo.get_images_for_scratchpad(sid)


@pytest.mark.parametrize("hidden", [False, True])
@pytest.mark.parametrize("entry", ["quit", "close"])
def test_failed_shutdown_retains_recovery_controls(main_window, monkeypatch, hidden, entry):
    w = main_window
    editor = w.tab_widget.get_current_editor()
    editor.textCursor().insertText("Synthetic shutdown draft")
    w.global_hotkey = Mock()
    w.tray_icon = Mock()
    w.tray_icon.isVisible.return_value = True
    w.show()
    if hidden:
        w.hide()
    original = w.scratchpad_service.save_content
    monkeypatch.setattr(w.scratchpad_service, "save_content", fail)
    if entry == "quit":
        w.quit_application()
    else:
        event = QCloseEvent()
        w.closeEvent(event)
        assert not event.isAccepted()
    assert w.isVisible()
    w.global_hotkey.unregister.assert_not_called()
    w.tray_icon.hide.assert_not_called()
    assert not w._force_quit
    assert editor.scratchpad_id in w._dirty_scratchpad_ids
    monkeypatch.setattr(w.scratchpad_service, "save_content", original)
    assert w.flush_all_saves()


def test_dirty_missing_editor_is_not_acknowledged(main_window):
    w = main_window
    w._dirty_scratchpad_ids.add(987654)
    with pytest.raises(Exception, match="[Ee]ditor"):
        w._execute_save(987654)
    assert not w.flush_all_saves()
    w._dirty_scratchpad_ids.remove(987654)


@pytest.mark.parametrize("stage", ["html", "insert", "cleanup", "commit"])
def test_html_image_failure_rolls_back_and_retry_restores(services, monkeypatch, tmp_path, stage):
    service, _ = services
    sid = service.create_ticket("SYNTHETIC-ATOMIC", content_html="old")["id"]
    other = service.create_ticket("SYNTHETIC-OTHER", content_html="other")["id"]
    conn = service.repo.db.get_connection()
    service.image_service.repo.save_image(sid, "old.jpg", b"old-jpeg")
    service.image_service.repo.save_image(other, "other.jpg", b"other-jpeg")
    html = '<p>new</p><img src="image://local/new.jpg">'
    images = {"new.jpg": b"synthetic-jpeg"}
    if stage != "commit":
        sql = {"html": "BEFORE UPDATE OF content_html ON scratchpads", "insert": "BEFORE INSERT ON scratchpad_images", "cleanup": "BEFORE DELETE ON scratchpad_images"}[stage]
        conn.execute(f"CREATE TEMP TRIGGER fail_save {sql} BEGIN SELECT RAISE(ABORT, 'synthetic failure'); END")
    else:
        conn.set_authorizer(lambda action, arg, *rest: sqlite3.SQLITE_DENY if action == sqlite3.SQLITE_TRANSACTION and arg == "COMMIT" else sqlite3.SQLITE_OK)
    with pytest.raises(Exception):
        service.save_content(sid, html, images)
    conn.set_authorizer(None)
    assert service.get_ticket(sid)["content_html"] == "old"
    assert service.image_service.repo.get_images_for_scratchpad(sid) == {"old.jpg": b"old-jpeg"}
    assert images == {"new.jpg": b"synthetic-jpeg"}
    if stage != "commit":
        conn.execute("DROP TRIGGER fail_save")
    receipt = service.save_content(sid, html, images)
    assert receipt.status == "saved" and receipt.ticket_id == sid
    assert service.get_ticket(sid)["content_html"] == html
    assert service.image_service.repo.get_images_for_scratchpad(sid) == images
    assert service.image_service.repo.get_images_for_scratchpad(other) == {"other.jpg": b"other-jpeg"}
    # SQLite online backup includes a consistent WAL snapshot, never a raw file copy.
    backup = sqlite3.connect(tmp_path / "synthetic-backup.sqlite")
    conn.backup(backup)
    restored = sqlite3.connect(tmp_path / "synthetic-restored.sqlite")
    backup.backup(restored)
    assert restored.execute("PRAGMA integrity_check").fetchone()[0] == "ok"
    assert restored.execute("PRAGMA foreign_key_check").fetchall() == []
    assert restored.execute("SELECT content_html FROM scratchpads WHERE id=?", (sid,)).fetchone()[0] == html
    assert restored.execute("SELECT image_data FROM scratchpad_images WHERE scratchpad_id=?", (sid,)).fetchone()[0] == images["new.jpg"]
    backup.close()
    restored.close()


def test_missing_referenced_image_rejects_save(services):
    service, _ = services
    sid = service.create_ticket("SYNTHETIC-MISSING", content_html="old")["id"]
    with pytest.raises(ValueError, match="image"):
        service.save_content(sid, '<img src="image://local/missing.jpg">', {})
    assert service.get_ticket(sid)["content_html"] == "old"


def test_save_receipt_does_not_clear_a_newer_edit(main_window, monkeypatch):
    w = main_window
    editor = w.tab_widget.get_current_editor()
    sid = editor.scratchpad_id
    editor.textCursor().insertText("first snapshot")
    original = w.scratchpad_service.save_content
    def save_then_edit(*args, **kwargs):
        receipt = original(*args, **kwargs)
        editor.textCursor().insertText(" newer edit")
        return receipt
    monkeypatch.setattr(w.scratchpad_service, "save_content", save_then_edit)
    assert not w.flush_all_saves()
    assert sid in w._dirty_scratchpad_ids
    monkeypatch.setattr(w.scratchpad_service, "save_content", original)
    assert w.flush_all_saves()
    assert "newer edit" in w.scratchpad_service.get_ticket(sid)["content_html"]


@pytest.mark.parametrize("stage", ["stopwatch", "pause", "session", "order"])
def test_hidden_shutdown_metadata_failure_preserves_controls(main_window, monkeypatch, stage):
    w = main_window
    w.global_hotkey = Mock()
    w.tray_icon = Mock()
    w.tray_icon.isVisible.return_value = True
    target, name = {
        "stopwatch": (w.toolbar.stopwatch, "save_current_state"),
        "pause": (w.toolbar.stopwatch, "pause_timer"),
        "session": (w.session_service, "persist_workspace"),
        "order": (w, "_on_tabs_reordered"),
    }[stage]
    with monkeypatch.context() as patch:
        patch.setattr(target, name, fail)
        w.hide()
        w.quit_application()
        assert w.isVisible() and not w._force_quit
        w.global_hotkey.unregister.assert_not_called()
        w.tray_icon.hide.assert_not_called()


def test_failed_quit_then_retry_only_exits_after_success(main_window, monkeypatch, qapp):
    w = main_window
    editor = w.tab_widget.get_current_editor()
    editor.textCursor().insertText("Synthetic retry quit")
    w.global_hotkey = Mock()
    w.tray_icon = Mock()
    w.tray_icon.isVisible.return_value = True
    quit_calls = Mock()
    monkeypatch.setattr(qapp, "quit", quit_calls)
    with monkeypatch.context() as patch:
        patch.setattr(w.scratchpad_service, "save_content", fail)
        w.quit_application()
        quit_calls.assert_not_called()
    w.quit_application()
    quit_calls.assert_called_once()
    w.global_hotkey.unregister.assert_called_once()
    w.tray_icon.hide.assert_called_once()


def test_new_ticket_does_not_mask_other_failed_note(main_window, monkeypatch):
    w = main_window
    editor = w.tab_widget.get_current_editor()
    editor.textCursor().insertText("older dirty note")
    with monkeypatch.context() as patch:
        patch.setattr(w.scratchpad_service, "save_content", fail)
        assert not w.flush_all_saves()
        w.create_new_tab()
        assert editor.scratchpad_id in w._dirty_scratchpad_ids
        assert "Saved" not in w.lbl_save_status.text()
