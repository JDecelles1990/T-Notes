"""Unit and integration tests for image resizing in normal and split views."""

from PySide6.QtCore import QPoint, QRect, Qt
from PySide6.QtGui import QImage, QKeyEvent
from PySide6.QtWidgets import QApplication, QDialog
import pytest

from src.database.connection import DatabaseManager
from src.database.migrations import init_database
from src.repositories.image_repository import ImageRepository
from src.repositories.scratchpad_repository import ScratchpadRepository
from src.repositories.session_repository import SessionRepository
from src.repositories.template_repository import TemplateRepository
from src.services.image_service import ImageService
from src.services.scratchpad_service import ScratchpadService
from src.services.session_service import SessionService
from src.ui.dialogs.resize_image_dialog import ResizeImageDialog
from src.ui.main_window import TechPadMainWindow


@pytest.fixture
def db_manager(tmp_path):
    db_file = tmp_path / "test_resize.db"
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


def test_resize_image_dialog_aspect_ratio_and_presets(qapp):
    """Verifies proportional adjustments, presets, and aspect ratio locking in ResizeImageDialog."""
    dlg = ResizeImageDialog(
        current_width=800,
        current_height=400,
        original_width=800,
        original_height=400,
        max_pane_width=350,
    )
    assert dlg.get_dimensions() == (800, 400)

    # 1. 50% Preset (800x400 -> 400x200)
    dlg._apply_preset_percentage(0.50)
    assert dlg.get_dimensions() == (400, 200)

    # 2. 25% Preset (800x400 -> 200x100)
    dlg._apply_preset_percentage(0.25)
    assert dlg.get_dimensions() == (200, 100)

    # 3. 100% Preset restores original dimensions
    dlg._apply_preset_percentage(1.0)
    assert dlg.get_dimensions() == (800, 400)

    # 4. Fit to pane width (capped at max_pane_width = 350, proportional height = 175)
    dlg._apply_preset_fit_pane()
    assert dlg.get_dimensions() == (350, 175)

    # 5. Proportional change via Width spinbox
    dlg.spin_width.setValue(600)
    assert dlg.spin_height.value() == 300

    # 6. Proportional change via Height spinbox
    dlg.spin_height.setValue(150)
    assert dlg.spin_width.value() == 300

    # 7. Unlocked aspect ratio allows independent width/height
    dlg.chk_lock_aspect.setChecked(False)
    dlg.spin_width.setValue(500)
    assert dlg.spin_height.value() == 150  # Height remains unchanged


def test_editor_image_resize_in_normal_view(qapp, services):
    """Verifies image resizing in normal view: API resize, quick presets, dialog, and HTML persistence."""
    scratch_service, img_service, session_service = services
    main_window = TechPadMainWindow(scratch_service, img_service, session_service)

    try:
        editor = main_window.tab_widget.get_current_editor()
        assert editor is not None

        # Insert a 400x200 test image
        img = QImage(400, 200, QImage.Format_RGB32)
        img.fill(0xFF224466)
        editor.insert_embedded_image(img)

        # 1. Image detection
        info = editor._get_image_info_at_doc_pos(0)
        assert info is not None
        assert info["original_width"] == 400
        assert info["original_height"] == 200

        # 2. Resize via public API to 300x150
        editor.resize_image_at(0, 300, 150)
        info2 = editor._get_image_info_at_doc_pos(0)
        assert info2["current_width"] == 300
        assert info2["current_height"] == 150
        html = editor.toHtml()
        assert 'width="300"' in html
        assert 'height="150"' in html

        # 3. Quick Resize to 50% (of original 400x200 -> 200x100)
        editor._quick_resize_image(info, 0.50)
        info3 = editor._get_image_info_at_doc_pos(0)
        assert info3["current_width"] == 200
        assert info3["current_height"] == 100
        assert 'width="200"' in editor.toHtml()

        # 4. Quick Resize Fit to Pane
        editor._quick_resize_image(info, "fit")
        info_fit = editor._get_image_info_at_doc_pos(0)
        assert info_fit["current_width"] <= editor.viewport().width()

        # 5. Dialog resize with accepted mock
        class MockDialog:
            def __init__(self, *args, **kwargs):
                pass
            def exec(self):
                return QDialog.Accepted
            def get_dimensions(self):
                return (260, 130)

        import src.ui.components.editor as editor_mod
        orig_dlg = editor_mod.ResizeImageDialog
        editor_mod.ResizeImageDialog = MockDialog
        try:
            editor._open_resize_dialog(info)
            info_dlg = editor._get_image_info_at_doc_pos(0)
            assert info_dlg["current_width"] == 260
            assert info_dlg["current_height"] == 130
        finally:
            editor_mod.ResizeImageDialog = orig_dlg
    finally:
        try:
            main_window.quit_application()
        except Exception:
            pass
        qapp.removeEventFilter(main_window)
        main_window.deleteLater()


def test_editor_image_resize_in_split_view(qapp, services):
    """Verifies that images in the Split View secondary pane can be resized and fit the sidebar."""
    scratch_service, img_service, session_service = services
    main_window = TechPadMainWindow(scratch_service, img_service, session_service)

    try:
        # Open side-by-side split view
        main_window.open_split_view()
        assert not main_window.secondary_tab_widget.isHidden()

        sec_editor = main_window.secondary_tab_widget.get_current_editor()
        assert sec_editor is not None

        # Insert a 600x300 image in split view pane
        img = QImage(600, 300, QImage.Format_RGB32)
        img.fill(0xFFAABBCC)
        sec_editor.insert_embedded_image(img)

        # Verify image exists in secondary pane
        info = sec_editor._get_image_info_at_doc_pos(0)
        assert info is not None
        assert info["original_width"] == 600
        assert info["original_height"] == 300

        # Resize to 50% (300x150)
        sec_editor._quick_resize_image(info, 0.50)
        info_50 = sec_editor._get_image_info_at_doc_pos(0)
        assert info_50["current_width"] == 300
        assert info_50["current_height"] == 150
        assert 'width="300"' in sec_editor.toHtml()

        # Fit to pane width in Split View
        sec_editor._quick_resize_image(info, "fit")
        info_fit = sec_editor._get_image_info_at_doc_pos(0)
        # In split view, available width is constrained to secondary pane
        assert info_fit["current_width"] <= max(50, sec_editor.viewport().width())

        # Test image selection and Delete key removal
        sec_editor._selected_image_pos = 0
        del_event = QKeyEvent(QKeyEvent.KeyPress, Qt.Key_Delete, Qt.NoModifier)
        sec_editor.keyPressEvent(del_event)
        # Image character removed
        assert sec_editor._get_image_info_at_doc_pos(0) is None
        assert sec_editor._selected_image_pos is None
    finally:
        try:
            main_window.quit_application()
        except Exception:
            pass
        qapp.removeEventFilter(main_window)
        main_window.deleteLater()

