"""Unit tests for in-note search and replace floating bar."""

import pytest
from PySide6.QtCore import Qt
from PySide6.QtGui import QKeyEvent, QTextCursor
from src.database.connection import DatabaseManager
from src.database.migrations import init_database
from src.repositories.image_repository import ImageRepository
from src.services.image_service import ImageService
from src.ui.components.editor import TechPadEditor


@pytest.fixture
def editor(tmp_path, qapp):
    db_file = tmp_path / "test_find_replace.db"
    db_manager = DatabaseManager(db_file)
    init_database(db_manager)
    img_repo = ImageRepository(db_manager)
    img_service = ImageService(img_repo)
    ed = TechPadEditor(scratchpad_id=1, image_service=img_service)
    ed.show()
    yield ed
    db_manager.close()


def test_find_matches_case_insensitive(editor):
    editor.setPlainText("Host server-01 is healthy. Backup Server-02 is standby.")
    bar = editor.find_replace_bar

    bar.show_bar(replace_mode=False)
    assert not bar.isHidden()

    bar.txt_find.setText("server")
    assert bar.lbl_matches.text() == "1 of 2"
    assert len(bar._matches) == 2

    bar.find_next()
    assert bar.lbl_matches.text() == "2 of 2"

    bar.find_next()
    assert bar.lbl_matches.text() == "1 of 2"

    bar.find_prev()
    assert bar.lbl_matches.text() == "2 of 2"


def test_find_matches_case_sensitive(editor):
    editor.setPlainText("Host server-01 is healthy. Backup Server-02 is standby.")
    bar = editor.find_replace_bar
    bar.show_bar(replace_mode=False)

    bar.btn_case.setChecked(True)
    bar.txt_find.setText("server")
    assert bar.lbl_matches.text() == "1 of 1"

    bar.txt_find.setText("Server")
    assert bar.lbl_matches.text() == "1 of 1"

    bar.txt_find.setText("SERVER")
    assert bar.lbl_matches.text() == "0 of 0"


def test_replace_current(editor):
    editor.setPlainText("Configuring eth0 and eth0 gateway.")
    bar = editor.find_replace_bar
    bar.show_bar(replace_mode=True)

    bar.txt_find.setText("eth0")
    bar.txt_replace.setText("ens192")
    assert bar.lbl_matches.text() == "1 of 2"

    bar.replace_current()
    text = editor.toPlainText()
    assert text.startswith("Configuring ens192 and eth0 gateway.")
    assert bar.lbl_matches.text() == "1 of 1"


def test_replace_all(editor):
    editor.setPlainText("IP 192.168.1.10 and 192.168.1.20 and 192.168.1.30")
    bar = editor.find_replace_bar
    bar.show_bar(replace_mode=True)

    bar.txt_find.setText("192.168.1")
    bar.txt_replace.setText("10.0.0")
    assert len(bar._matches) == 3

    bar.replace_all()
    text = editor.toPlainText()
    assert text == "IP 10.0.0.10 and 10.0.0.20 and 10.0.0.30"
    assert bar.lbl_matches.text() == "0 of 0"


def test_shortcuts_and_prefill(editor):
    text = "Diagnostic error code ERR_404 reported."
    editor.setPlainText(text)
    bar = editor.find_replace_bar

    # Select ERR_404
    pos = text.find("ERR_404")
    cursor = editor.textCursor()
    cursor.setPosition(pos)
    cursor.setPosition(pos + len("ERR_404"), QTextCursor.KeepAnchor)
    editor.setTextCursor(cursor)
    assert editor.textCursor().selectedText() == "ERR_404"

    # Trigger show_find_replace
    editor.show_find_replace(replace_mode=False)
    assert not bar.isHidden()
    assert bar.txt_find.text() == "ERR_404"
    assert bar.lbl_matches.text() == "1 of 1"

    # Esc key hides bar
    esc_event = QKeyEvent(QKeyEvent.KeyPress, Qt.Key_Escape, Qt.NoModifier)
    bar.keyPressEvent(esc_event)
    assert bar.isHidden()


def test_ctrl_h_opens_replace_mode(editor):
    bar = editor.find_replace_bar
    assert bar.isHidden()

    # Press Ctrl+H in editor
    ctrl_h = QKeyEvent(QKeyEvent.KeyPress, Qt.Key_H, Qt.ControlModifier)
    editor.keyPressEvent(ctrl_h)
    assert not bar.isHidden()
    assert bar.replace_container.isVisible()
