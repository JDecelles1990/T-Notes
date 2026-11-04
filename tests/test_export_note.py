"""Unit and integration tests for Active Ticket plain-text file export."""

from datetime import datetime
from pathlib import Path
import pytest
from PySide6.QtCore import Qt
from PySide6.QtGui import QImage, QTextCursor
from PySide6.QtWidgets import QApplication

from src.config import BASE_DIR, DEFAULT_EXPORT_DIR
from src.database.connection import DatabaseManager
from src.database.migrations import init_database
from src.repositories.image_repository import ImageRepository
from src.repositories.scratchpad_repository import ScratchpadRepository
from src.repositories.session_repository import SessionRepository
from src.repositories.template_repository import TemplateRepository
from src.services.image_service import ImageService
from src.services.scratchpad_service import ScratchpadService
from src.services.session_service import SessionService
from src.ui.components.editor import TechPadEditor
from src.ui.components.toolbar import TechPadToolBar
from src.ui.main_window import TechPadMainWindow


@pytest.fixture
def db_manager(tmp_path):
    db_file = tmp_path / "test_export.db"
    manager = DatabaseManager(db_file)
    init_database(manager)
    yield manager
    manager.close()


@pytest.fixture
def services(db_manager):
    scratch_repo = ScratchpadRepository(db_manager)
    img_repo = ImageRepository(db_manager)
    img_service = ImageService(img_repo)
    template_repo = TemplateRepository(db_manager)
    scratch_service = ScratchpadService(scratch_repo, img_service, template_repo)
    session_repo = SessionRepository(db_manager)
    session_service = SessionService(session_repo, scratch_service)
    return scratch_service, img_service, session_service


def test_sanitize_filename_part():
    """Tests filename sanitization for Windows and cross-platform filesystems."""
    assert ScratchpadService.sanitize_filename_part("INC-1001") == "INC-1001"
    assert ScratchpadService.sanitize_filename_part("Acme Corp") == "Acme_Corp"
    assert ScratchpadService.sanitize_filename_part("Test / Path: With * Ill?egal <Chars>|#") == "Test_Path_With_Illegal_Chars"
    assert ScratchpadService.sanitize_filename_part("   ___leading and trailing___   ") == "leading_and_trailing"
    assert ScratchpadService.sanitize_filename_part("") == ""


def test_generate_export_filename_same_hour_overwrites():
    """Tests that filenames match in the same hour and differ across hours, with client if exists."""
    # 1. Ticket with Client
    ticket_with_client = {
        "ticket_number": "INC-4092",
        "client_name": "Cyberdyne Systems",
        "title": "T-800 Firmware Malfunction",
    }

    t1 = datetime(2026, 11, 4, 14, 5)   # 14:05
    t2 = datetime(2026, 11, 4, 14, 55)  # 14:55
    t3 = datetime(2026, 11, 4, 15, 0)   # 15:00

    fn1 = ScratchpadService.generate_export_filename(ticket_with_client, now=t1)
    fn2 = ScratchpadService.generate_export_filename(ticket_with_client, now=t2)
    fn3 = ScratchpadService.generate_export_filename(ticket_with_client, now=t3)

    assert fn1 == "INC-4092_Cyberdyne_Systems_2026-11-04_14h.txt"
    # Same hour yields identical filename for automatic overwrite
    assert fn1 == fn2
    # Different hour yields distinct filename
    assert fn1 != fn3
    assert fn3 == "INC-4092_Cyberdyne_Systems_2026-11-04_15h.txt"

    # 2. Ticket without Client (client omitted from filename)
    ticket_no_client = {
        "ticket_number": "INC-1002",
        "client_name": "",
        "title": "Quick triage",
    }
    fn_no_client = ScratchpadService.generate_export_filename(ticket_no_client, now=t1)
    assert fn_no_client == "INC-1002_2026-11-04_14h.txt"


def test_export_ticket_to_file(tmp_path, services):
    """Tests file export with pure plain text, no images, and overwrite within same hour."""
    scratch_service, img_service, _ = services

    # Create ticket in repo
    ticket = scratch_service.create_ticket(
        ticket_number="INC-2020",
        client_name="Wayne Enterprises",
        title="Batcave Network Drop",
        content_html="<p><b>Issue:</b> Switch offline.<br>Ping 10.0.0.1 failed.</p>",
    )
    sid = ticket["id"]

    t1 = datetime(2026, 11, 4, 10, 15)
    file_path1, fn1 = scratch_service.export_ticket_to_file(
        scratchpad_id=sid,
        text_content="Issue: Switch offline.\nPing 10.0.0.1 failed.",
        export_dir=tmp_path,
        now=t1,
    )

    assert file_path1.exists()
    assert file_path1.parent.name == "2026-11-04_10h"
    assert file_path1.parent.parent == tmp_path
    assert fn1 == "INC-2020_Wayne_Enterprises_2026-11-04_10h.txt"
    content = file_path1.read_text(encoding="utf-8")
    assert "Issue: Switch offline." in content
    assert "Ping 10.0.0.1 failed." in content
    assert "<p>" not in content
    assert "<b>" not in content

    # Trigger second export within same hour with updated notes
    t2 = datetime(2026, 11, 4, 10, 45)
    file_path2, fn2 = scratch_service.export_ticket_to_file(
        scratchpad_id=sid,
        text_content="Issue: Switch offline.\nPing 10.0.0.1 failed.\nResolved by rebooting router.",
        export_dir=tmp_path,
        now=t2,
    )

    # Must overwrite the exact same file
    assert file_path1 == file_path2
    assert len(list((tmp_path / "2026-11-04_10h").glob("*.txt"))) == 1
    content2 = file_path2.read_text(encoding="utf-8")
    assert "Resolved by rebooting router." in content2


def test_toolbar_export_file_signal(qapp):
    """Tests that toolbar Copy Note dropdown contains Export Note action and emits signal."""
    toolbar = TechPadToolBar()
    copy_menu = toolbar.btn_copy_note.menu()
    assert copy_menu is not None

    actions = copy_menu.actions()
    action_texts = [a.text() for a in actions]
    assert any("Export Note" in t for t in action_texts)

    emitted = []
    toolbar.export_file_requested.connect(lambda: emitted.append(True))

    for act in actions:
        if "Export Note" in act.text():
            act.trigger()

    assert emitted == [True]


def test_main_window_export_active_ticket(qapp, services, tmp_path, monkeypatch):
    """Tests full UI workflow: clicking Export Note exports active ticket from primary or split pane."""
    scratch_service, img_service, session_service = services

    # Mock default export dir to tmp_path
    monkeypatch.setattr("src.services.scratchpad_service.DEFAULT_EXPORT_DIR", tmp_path)

    main_window = TechPadMainWindow(
        scratchpad_service=scratch_service,
        image_service=img_service,
        session_service=session_service,
    )

    main_window.show()
    try:
            # 1. Primary pane active ticket
        editor = main_window._get_active_editor()
        assert editor is not None
        editor.setPlainText("Diagnostic steps executed:\n1. Checked DHCP\n2. Tested gateway")
    
        # Insert a dummy image to verify it gets stripped from export
        test_img = QImage(8, 8, QImage.Format_RGB32)
        editor.insert_embedded_image(test_img)
        assert "\uFFFC" in editor.toPlainText()
    
        # Trigger Export Note action
        main_window._on_export_active_ticket_file()
    
        # Verify file was written to tmp_path
        exported_files = list(tmp_path.rglob("*.txt"))
        assert len(exported_files) == 1
        assert exported_files[0].parent.name == datetime.now().strftime("%Y-%m-%d_%Hh")
        assert exported_files[0].parent.parent == tmp_path
        exported_content = exported_files[0].read_text(encoding="utf-8")
    
        # Content has text and no image placeholder
        assert "Diagnostic steps executed:" in exported_content
        assert "1. Checked DHCP" in exported_content
        assert "\uFFFC" not in exported_content
        assert "<img" not in exported_content
        assert "Exported note" in main_window.status_bar.currentMessage()
    
        # 2. Split View secondary pane active ticket export
        main_window._toggle_split_view()
        assert not main_window.secondary_tab_widget.isHidden()
        sec_editor = main_window.secondary_tab_widget.get_current_editor()
        assert sec_editor is not None
        sec_editor.setPlainText("Secondary Pane Ticket Notes:\nFirewall rule updated.")
        sec_editor.setFocus()
    
        # Verify active editor resolved to secondary editor
        assert main_window._get_active_editor() is sec_editor
    
        # Trigger export on the active Split view ticket
        main_window._on_export_active_ticket_file()
    
        exported_files_after = list(tmp_path.rglob("*.txt"))
        assert len(exported_files_after) == 2
        sec_content = [f.read_text(encoding="utf-8") for f in exported_files_after if "Secondary Pane Ticket Notes" in f.read_text(encoding="utf-8")]
        assert len(sec_content) == 1
        assert "Firewall rule updated." in sec_content[0]
    finally:
        try:
            main_window.quit_application()
        except Exception:
            pass
        qapp.removeEventFilter(main_window)
        main_window.deleteLater()
