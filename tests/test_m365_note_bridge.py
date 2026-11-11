"""Unit tests for M365 PowerShell output bridge to active ticket note."""

import pytest
from PySide6.QtWidgets import QPlainTextEdit, QTextEdit
from src.database.connection import DatabaseManager
from src.database.migrations import init_database
from src.repositories.image_repository import ImageRepository
from src.services.image_service import ImageService
from src.ui.components.editor import TechPadEditor
from src.ui.m365.launcher_widget import M365LauncherWidget


@pytest.fixture
def launcher(tmp_path, qapp):
    db_file = tmp_path / "test_bridge.db"
    db_manager = DatabaseManager(db_file)
    init_database(db_manager)
    img_repo = ImageRepository(db_manager)
    img_service = ImageService(img_repo)

    widget = M365LauncherWidget()
    editor = TechPadEditor(scratchpad_id=1, image_service=img_service)
    editor.setPlainText("Initial ticket notes.\n")
    widget.set_active_ticket(editor, ticket_data={"ticket_number": "INC-1001", "title": "Active Note"})

    yield widget, editor
    db_manager.close()


def test_insert_results_into_ticket_formatted_container(launcher):
    widget, editor = launcher

    # Select an operation from list
    if widget.operation_list.count() > 0:
        widget.operation_list.setCurrentRow(0)

    # Set some synthetic PowerShell results in results_output
    sample_output = "UserPrincipalName: admin@contoso.com\nAccountEnabled: True\nAssignedLicenses: M365 E5"
    widget.results_output.setPlainText(sample_output)

    # Insert into ticket
    success = widget.insert_current_result_into_ticket()
    assert success is True

    # Verify editor content contains formatted container
    html = editor.toHtml()
    assert "M365 Output:" in html
    assert "admin@contoso.com" in html
    assert "AssignedLicenses: M365 E5" in html

    plain = editor.toPlainText()
    assert "admin@contoso.com" in plain
    assert "Initial ticket notes." in plain
