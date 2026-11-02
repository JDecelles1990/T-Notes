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
    window.close()
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
    main_window._toggle_history_drawer()
    assert main_window.history_drawer.isHidden() != initial_hidden
    main_window._toggle_history_drawer()
    assert main_window.history_drawer.isHidden() == initial_hidden


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

    # Test move relative
    main_window._move_active_tab_relative(+1)
    assert main_window.tab_widget.currentIndex() == 1


