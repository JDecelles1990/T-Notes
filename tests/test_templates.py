"""Unit and integration tests for custom ticket templates."""

import base64
import pytest
from PySide6.QtCore import QByteArray, QBuffer, QIODevice, QUrl, Qt
from PySide6.QtGui import QColor, QFont, QImage, QTextCursor, QTextDocument
from PySide6.QtWidgets import QApplication, QDialog, QMessageBox

from src.database.connection import DatabaseManager
from src.database.migrations import init_database
from src.repositories.image_repository import ImageRepository
from src.repositories.scratchpad_repository import ScratchpadRepository
from src.repositories.session_repository import SessionRepository
from src.repositories.template_repository import TemplateRepository
from src.services.image_service import ImageService
from src.services.scratchpad_service import ScratchpadService
from src.ui.dialogs.add_template_dialog import AddTemplateDialog, TemplateEditor
from src.ui.components.editor import TechPadEditor
from src.ui.components.toolbar import TechPadToolBar
from src.core.constants import LOCAL_IMAGE_URL_PREFIX


@pytest.fixture
def db_manager(tmp_path):
    """Provides a fresh SQLite database for each test."""
    db_file = tmp_path / "test_templates.db"
    manager = DatabaseManager(db_file)
    init_database(manager)
    yield manager
    manager.close()


@pytest.fixture
def template_repo(db_manager):
    return TemplateRepository(db_manager)


@pytest.fixture
def services(db_manager):
    scratch_repo = ScratchpadRepository(db_manager)
    img_repo = ImageRepository(db_manager)
    img_service = ImageService(img_repo)
    template_repo = TemplateRepository(db_manager)
    scratch_service = ScratchpadService(scratch_repo, img_service, template_repo)
    return scratch_service, img_service, template_repo


def test_template_repository_crud(template_repo):
    """Tests CRUD lifecycle in TemplateRepository."""
    # 1. Create
    tid = template_repo.create("Network Triage", "<p>Check ping and DNS.</p>")
    assert tid > 0

    # 2. Get by ID
    tmpl = template_repo.get_by_id(tid)
    assert tmpl is not None
    assert tmpl["title"] == "Network Triage"
    assert "<p>Check ping and DNS.</p>" in tmpl["content_html"]

    # 3. Get by Title
    tmpl_by_title = template_repo.get_by_title("network triage")  # case-insensitive
    assert tmpl_by_title is not None
    assert tmpl_by_title["id"] == tid

    # 4. Upsert on Conflict
    tid2 = template_repo.create("Network Triage", "<p>Updated check.</p>")
    tmpl_updated = template_repo.get_by_id(tid)
    assert "<p>Updated check.</p>" in tmpl_updated["content_html"]

    # 5. Get All
    template_repo.create("Firewall Rules", "<p>Rules list.</p>")
    all_tmpls = template_repo.get_all()
    assert len(all_tmpls) == 2
    titles = [t["title"] for t in all_tmpls]
    assert "Firewall Rules" in titles
    assert "Network Triage" in titles

    # 6. Delete
    assert template_repo.delete(tid) is True
    assert template_repo.get_by_id(tid) is None
    assert len(template_repo.get_all()) == 1

    # 7. Delete by title
    assert template_repo.delete_by_title("Firewall Rules") is True
    assert len(template_repo.get_all()) == 0


def test_scratchpad_service_custom_templates(services):
    """Tests custom template service validation and retrieval."""
    scratch_service, _, template_repo = services

    # Validation errors
    with pytest.raises(ValueError, match="Template title cannot be empty"):
        scratch_service.add_custom_template("   ", "<p>Some text</p>")

    with pytest.raises(ValueError, match="Template content cannot be empty"):
        scratch_service.add_custom_template("Valid Title", "   ")

    # Add valid template
    tid = scratch_service.add_custom_template("DNS Checklist", "<h3>DNS Checks</h3><p>Nslookup 8.8.8.8</p>")
    assert tid > 0

    # Retrieve via get_custom_templates
    custom_tmpls = scratch_service.get_custom_templates()
    assert len(custom_tmpls) == 1
    assert custom_tmpls[0]["title"] == "DNS Checklist"

    # Retrieve titles
    assert "DNS Checklist" in scratch_service.get_custom_template_titles()

    # get_skeleton_html returns built-in skeletons AND custom templates
    builtin_html = scratch_service.get_skeleton_html("Standard Incident Triage")
    assert "ISSUE DESCRIPTION" in builtin_html

    custom_html = scratch_service.get_skeleton_html("DNS Checklist")
    assert "DNS Checks" in custom_html

    nonexistent_html = scratch_service.get_skeleton_html("Nonexistent")
    assert nonexistent_html == ""

    # Delete via service
    assert scratch_service.delete_custom_template(tid) is True
    assert len(scratch_service.get_custom_templates()) == 0


def test_editor_insert_template_html(qapp, services):
    """Tests inserting template HTML with embedded Base64 image into TechPadEditor."""
    scratch_service, img_service, _ = services
    editor = TechPadEditor(scratchpad_id=1, image_service=img_service)
    editor.setPlainText("Ticket context: ")

    # Generate small 10x10 synthetic blue image as Base64 JPEG
    qimg = QImage(10, 10, QImage.Format_RGB32)
    qimg.fill(QColor("blue"))
    ba = QByteArray()
    buf = QBuffer(ba)
    buf.open(QIODevice.WriteOnly)
    qimg.save(buf, "JPEG", 85)
    b64_str = base64.b64encode(bytes(ba.data())).decode("ascii")

    template_html = f'<h3>Template Title</h3><p>Diagnostics: <img src="data:image/jpeg;base64,{b64_str}"></p>'

    # Move cursor to end and insert
    cursor = editor.textCursor()
    cursor.movePosition(QTextCursor.MoveOperation.End)
    editor.setTextCursor(cursor)

    editor.insert_template_html(template_html)

    # Verify editor contents
    plain = editor.toPlainText()
    assert "Ticket context:" in plain
    assert "Template Title" in plain
    assert "Diagnostics:" in plain

    # Verify image was unpacked and registered
    assert len(editor.in_memory_images) == 1
    image_name = list(editor.in_memory_images.keys())[0]
    assert image_name.endswith(".jpg")

    # Verify image resource exists in QTextDocument
    res_url = f"{LOCAL_IMAGE_URL_PREFIX}{image_name}"
    res = editor.document().resource(QTextDocument.ImageResource, QUrl(res_url))
    assert res is not None and not res.isNull()


def test_add_template_dialog(qapp, services, monkeypatch):
    """Tests AddTemplateDialog controls, formatting buttons, and self-contained HTML export."""
    monkeypatch.setattr(QMessageBox, "warning", lambda *args, **kwargs: None)
    _, img_service, _ = services
    dialog = AddTemplateDialog(image_service=img_service, initial_title="My Template")

    # Title line edit
    assert dialog.txt_title.text() == "My Template"

    # Test empty validation
    dialog.txt_title.setText("")
    dialog._on_save_clicked()
    assert dialog.result() != QDialog.Accepted

    dialog.txt_title.setText("Valid Template")
    dialog.editor.setPlainText("")
    dialog._on_save_clicked()
    assert dialog.result() != QDialog.Accepted

    # Apply text and formatting
    dialog.editor.setPlainText("Hello Template World")
    cursor = dialog.editor.textCursor()
    cursor.select(QTextCursor.SelectionType.Document)
    dialog.editor.setTextCursor(cursor)

    # Bold toggle
    dialog.btn_bold.setChecked(True)
    dialog._toggle_bold()
    fmt = dialog.editor.currentCharFormat()
    assert fmt.fontWeight() == QFont.Bold

    # Italic toggle
    dialog.btn_italic.setChecked(True)
    dialog._toggle_italic()
    fmt = dialog.editor.currentCharFormat()
    assert fmt.fontItalic() is True

    # Underline toggle
    dialog.btn_underline.setChecked(True)
    dialog._toggle_underline()
    fmt = dialog.editor.currentCharFormat()
    assert fmt.fontUnderline() is True

    # Strikethrough toggle
    dialog.btn_strike.setChecked(True)
    dialog._toggle_strikethrough()
    fmt = dialog.editor.currentCharFormat()
    assert fmt.fontStrikeOut() is True

    # Deselect and move cursor to end before inserting image
    cursor = dialog.editor.textCursor()
    cursor.movePosition(QTextCursor.MoveOperation.End)
    dialog.editor.setTextCursor(cursor)

    # Insert Image directly
    test_img = QImage(16, 16, QImage.Format_RGB32)
    test_img.fill(QColor("green"))
    dialog.editor.insert_image(test_img)
    assert len(dialog.editor.in_memory_images) == 1

    # Check export data
    title, content_html = dialog.get_template_data()
    assert title == "Valid Template"
    assert "Hello Template World" in content_html
    assert "data:image/jpeg;base64," in content_html

    # Test save accepts
    dialog._on_save_clicked()
    assert dialog.result() == QDialog.Accepted


def test_toolbar_template_menu(qapp):
    """Tests toolbar template dropdown menu population and action triggers."""
    toolbar = TechPadToolBar()

    # Rebuild with custom templates
    custom = [
        {"id": 1, "title": "Custom Template 1", "content_html": "<p>1</p>"},
        {"id": 2, "title": "Custom Template 2", "content_html": "<p>2</p>"},
    ]
    toolbar.update_templates_menu(custom)

    menu = toolbar.btn_skeleton.menu()
    assert menu is not None
    actions = menu.actions()

    action_texts = [a.text() for a in actions]
    assert "Standard Incident Triage" in action_texts
    assert "Custom Template 1" in action_texts
    assert "Custom Template 2" in action_texts
    assert "🔳 Add a new template" in action_texts

    # Test signal emissions
    selected_names = []
    toolbar.skeleton_selected.connect(selected_names.append)

    add_requested = []
    toolbar.add_template_requested.connect(lambda: add_requested.append(True))

    for act in actions:
        if act.text() == "Custom Template 1":
            act.trigger()
        elif act.text() == "🔳 Add a new template":
            act.trigger()

    assert selected_names == ["Custom Template 1"]
    assert add_requested == [True]


from src.services.session_service import SessionService
from src.ui.main_window import TechPadMainWindow
from unittest.mock import MagicMock


def test_main_window_add_template_and_insert_at_cursor(qapp, services, monkeypatch):
    """Tests the full user flow: opening the add template dialog, saving, and inserting at cursor."""
    scratch_service, img_service, template_repo = services
    session_repo = SessionRepository(template_repo.db)
    session_service = SessionService(session_repo, scratch_service)

    main_window = TechPadMainWindow(
        scratchpad_service=scratch_service,
        image_service=img_service,
        session_service=session_service,
    )
    try:
            # Ensure an active editor exists
        editor = main_window._get_active_editor()
        assert editor is not None
        editor.setPlainText("Prefix text: ")
        cursor = editor.textCursor()
        cursor.movePosition(QTextCursor.MoveOperation.End)
        editor.setTextCursor(cursor)
    
        # Mock AddTemplateDialog to simulate user entering title and template
        def mock_dialog_exec(dialog_self):
            dialog_self.txt_title.setText("Server Onboarding")
            dialog_self.editor.setHtml("<p><strong>Server:</strong> Host-01</p>")
            return QDialog.Accepted
    
        monkeypatch.setattr(AddTemplateDialog, "exec", mock_dialog_exec)
    
        # User clicks "🔳 Add a new template"
        main_window._on_add_new_template()
    
        # 1. Verify template was saved to database
        saved_templates = scratch_service.get_custom_templates()
        assert len(saved_templates) == 1
        assert saved_templates[0]["title"] == "Server Onboarding"
    
        # 2. Verify toolbar menu has the new template
        menu = main_window.toolbar.btn_skeleton.menu()
        action_texts = [a.text() for a in menu.actions()]
        assert "Server Onboarding" in action_texts
        assert "🔳 Add a new template" in action_texts
    
        # 3. User clicks the template from the menu -> inserts at cursor
        main_window._on_skeleton_selected("Server Onboarding")
    
        # 4. Verify text was inserted at cursor
        full_text = editor.toPlainText()
        assert "Prefix text: " in full_text
        assert "Server: Host-01" in full_text
    
        # 5. Test inserting in middle of text
        editor.setPlainText("Start Middle End")
        # Move cursor between 'Start ' and 'Middle'
        cursor = editor.textCursor()
        cursor.setPosition(6)
        editor.setTextCursor(cursor)
    
        main_window._on_skeleton_selected("Server Onboarding")
        text_after = editor.toPlainText()
        assert text_after.startswith("Start ")
        assert "Server: Host-01" in text_after
        assert text_after.endswith("Middle End")
    finally:
        try:
            main_window.quit_application()
        except Exception:
            pass


def test_scratchpad_service_update_and_get_template(services):
    """Tests updating and fetching custom templates in ScratchpadService."""
    scratch_service, _, _ = services

    tid1 = scratch_service.add_custom_template("Initial Template", "<p>Initial content</p>")
    tid2 = scratch_service.add_custom_template("Second Template", "<p>Second content</p>")

    # Fetch by ID
    tmpl = scratch_service.get_custom_template(tid1)
    assert tmpl is not None
    assert tmpl["title"] == "Initial Template"

    # Update template 1
    assert scratch_service.update_custom_template(tid1, "Updated Template", "<p>Updated content</p>") is True
    updated = scratch_service.get_custom_template(tid1)
    assert updated["title"] == "Updated Template"
    assert "<p>Updated content</p>" in updated["content_html"]

    # Validation errors on update
    with pytest.raises(ValueError, match="Template title cannot be empty"):
        scratch_service.update_custom_template(tid1, "   ", "<p>Valid content</p>")

    with pytest.raises(ValueError, match="Template content cannot be empty"):
        scratch_service.update_custom_template(tid1, "Valid Title", "   ")

    # Conflict with existing title
    with pytest.raises(ValueError, match="already exists"):
        scratch_service.update_custom_template(tid1, "Second Template", "<p>Conflict</p>")


def test_add_template_dialog_modify_and_delete_flow(qapp, services, monkeypatch):
    """Tests AddTemplateDialog dropdown switching, modification, deletion, and glowing buttons."""
    monkeypatch.setattr(QMessageBox, "warning", lambda *args, **kwargs: None)
    monkeypatch.setattr(QMessageBox, "information", lambda *args, **kwargs: None)

    scratch_service, img_service, _ = services
    tid = scratch_service.add_custom_template("VPN Setup", "<p>Connect to VPN gateway.</p>")

    dialog = AddTemplateDialog(
        image_service=img_service,
        scratchpad_service=scratch_service,
    )

    # Initially at index 0 (Create New)
    assert dialog.combo_templates.currentIndex() == 0
    assert dialog.get_action_mode() == "create"
    assert dialog.btn_delete.isHidden() is True
    assert dialog.btn_save.text() == "Save Template"

    # Switch to "VPN Setup" (index 1)
    assert dialog.combo_templates.count() >= 2
    dialog.combo_templates.setCurrentIndex(1)

    assert dialog.get_action_mode() == "update"
    assert dialog.get_target_template_id() == tid
    assert dialog.txt_title.text() == "VPN Setup"
    assert "Connect to VPN gateway" in dialog.editor.toPlainText()
    assert dialog.btn_delete.isHidden() is False
    assert dialog.btn_save.text() == "Update Template"

    # Modify the template
    dialog.txt_title.setText("VPN Setup 2.0")
    dialog.editor.setPlainText("Connect to WireGuard VPN.")
    dialog._on_save_clicked()
    assert dialog.result() == QDialog.Accepted
    assert dialog.was_saved_internally() is True
    assert dialog.was_modified() is True

    # Verify update in service
    updated = scratch_service.get_custom_template(tid)
    assert updated["title"] == "VPN Setup 2.0"
    assert "Connect to WireGuard VPN" in updated["content_html"]

    # Re-open dialog to test delete flow
    dialog2 = AddTemplateDialog(
        image_service=img_service,
        scratchpad_service=scratch_service,
        initial_template_id=tid,
    )
    assert dialog2.combo_templates.currentData() == tid
    assert dialog2.btn_delete.isHidden() is False

    # Test delete cancelled
    monkeypatch.setattr(QMessageBox, "question", lambda *args, **kwargs: QMessageBox.StandardButton.No)
    dialog2._on_delete_clicked()
    assert scratch_service.get_custom_template(tid) is not None

    # Test delete confirmed
    monkeypatch.setattr(QMessageBox, "question", lambda *args, **kwargs: QMessageBox.StandardButton.Yes)
    dialog2._on_delete_clicked()

    # Template must now be gone
    assert scratch_service.get_custom_template(tid) is None
    assert dialog2.was_modified() is True
    assert dialog2.combo_templates.currentIndex() == 0
    assert dialog2.btn_delete.isHidden() is True
    assert dialog2.txt_title.text() == ""


def test_add_template_dialog_new_template_button_reset(qapp, services):
    """Tests that clicking '➕ New Template' resets modify mode back to create mode."""
    scratch_service, img_service, _ = services
    tid = scratch_service.add_custom_template("Printer Setup", "<p>IP: 192.168.1.50</p>")

    dialog = AddTemplateDialog(
        image_service=img_service,
        scratchpad_service=scratch_service,
        initial_template_id=tid,
    )

    assert dialog.get_action_mode() == "update"
    assert dialog.btn_delete.isHidden() is False

    # Click New Template button
    dialog.btn_new_template.click()

    assert dialog.combo_templates.currentIndex() == 0
    assert dialog.get_action_mode() == "create"
    assert dialog.get_target_template_id() is None
    assert dialog.btn_delete.isHidden() is True
    assert dialog.txt_title.text() == ""
    assert dialog.editor.toPlainText().strip() == ""


def test_main_window_modify_and_delete_template(qapp, services, monkeypatch):
    """Tests modifying and deleting a template through TechPadMainWindow, verifying menu updates."""
    monkeypatch.setattr(QMessageBox, "warning", lambda *args, **kwargs: None)
    monkeypatch.setattr(QMessageBox, "information", lambda *args, **kwargs: None)

    scratch_service, img_service, template_repo = services
    session_repo = SessionRepository(template_repo.db)
    session_service = SessionService(session_repo, scratch_service)

    main_window = TechPadMainWindow(
        scratchpad_service=scratch_service,
        image_service=img_service,
        session_service=session_service,
    )
    try:
        # Pre-populate custom template
        tid = scratch_service.add_custom_template("Old Template", "<p>Old Content</p>")
        main_window._refresh_template_menus()

        # Check menu has old template
        menu = main_window.toolbar.btn_skeleton.menu()
        action_texts = [a.text() for a in menu.actions()]
        assert "Old Template" in action_texts

        # Simulate user modifying template in dialog
        def mock_modify_exec(dialog_self):
            dialog_self.combo_templates.setCurrentIndex(1)
            dialog_self.txt_title.setText("Renamed Template")
            dialog_self.editor.setHtml("<p>New Content</p>")
            dialog_self._on_save_clicked()
            return QDialog.Accepted

        monkeypatch.setattr(AddTemplateDialog, "exec", mock_modify_exec)
        main_window._on_add_new_template()

        # Check template modified in DB and menu
        tmpl = scratch_service.get_custom_template(tid)
        assert tmpl["title"] == "Renamed Template"

        menu = main_window.toolbar.btn_skeleton.menu()
        action_texts = [a.text() for a in menu.actions()]
        assert "Renamed Template" in action_texts
        assert "Old Template" not in action_texts

        # Simulate user opening dialog and deleting the template
        monkeypatch.setattr(QMessageBox, "question", lambda *args, **kwargs: QMessageBox.StandardButton.Yes)

        def mock_delete_exec(dialog_self):
            dialog_self.combo_templates.setCurrentIndex(1)
            dialog_self._on_delete_clicked()
            return QDialog.Rejected  # User closed dialog after deleting

        monkeypatch.setattr(AddTemplateDialog, "exec", mock_delete_exec)
        main_window._on_add_new_template()

        # Check template deleted in DB and removed from menu
        assert scratch_service.get_custom_template(tid) is None
        menu = main_window.toolbar.btn_skeleton.menu()
        action_texts = [a.text() for a in menu.actions()]
        assert "Renamed Template" not in action_texts
    finally:
        try:
            main_window.quit_application()
        except Exception:
            pass
