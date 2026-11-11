"""Unit and integration tests for image resizing in normal and split views."""

from PySide6.QtCore import QEvent, QPoint, QPointF, QRect, Qt
from PySide6.QtGui import QColor, QImage, QKeyEvent, QMouseEvent, QTextDocument, QWheelEvent
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
from src.ui.dialogs.resize_image_dialog import (
    AnnotationItem,
    ImageAnnotationCanvas,
    ResizeImageDialog,
    TextAnnotationDialog,
)
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


def test_image_annotation_canvas_tools_and_history(qapp):
    """Verifies draw, circle, rectangle, text tools, color/stroke customization, and undo/redo/reset."""
    # Create a 200x200 solid white test image
    base_img = QImage(200, 200, QImage.Format_ARGB32_Premultiplied)
    base_img.fill(0xFFFFFFFF)

    canvas = ImageAnnotationCanvas(base_img)
    canvas.resize(400, 400)
    rect = canvas.get_image_display_rect()
    assert rect.isValid()

    # Initial state
    assert not canvas.was_annotated()
    assert not canvas.can_undo()
    assert not canvas.can_redo()

    # Helper function to map image coordinates to canvas viewport
    def to_vp(ix: int, iy: int) -> QPointF:
        scale_x = rect.width() / 200.0
        scale_y = rect.height() / 200.0
        return QPointF(rect.x() + ix * scale_x, rect.y() + iy * scale_y)

    def mouse_ev(ev_type, p: QPointF) -> QMouseEvent:
        return QMouseEvent(ev_type, p, p, Qt.MouseButton.LeftButton, Qt.MouseButton.LeftButton, Qt.KeyboardModifier.NoModifier)

    # 1. Test Freehand Pen drawing
    canvas.set_tool(ImageAnnotationCanvas.TOOL_PEN)
    canvas.set_color(QColor("#ff3b30"))
    canvas.set_stroke_width(4)

    p1 = to_vp(50, 50)
    p2 = to_vp(70, 70)
    canvas.mousePressEvent(mouse_ev(QEvent.Type.MouseButtonPress, p1))
    canvas.mouseMoveEvent(mouse_ev(QEvent.Type.MouseMove, p2))
    canvas.mouseReleaseEvent(mouse_ev(QEvent.Type.MouseButtonRelease, p2))

    assert canvas.was_annotated()
    assert canvas.can_undo()
    annotated_img = canvas.get_annotated_image()
    # Check that pixel at (50, 50) or (70, 70) is no longer pure white
    assert annotated_img.pixelColor(50, 50) != QColor(255, 255, 255)

    # 2. Test Undo
    canvas.undo()
    assert not canvas.was_annotated()
    assert canvas.can_redo()
    assert canvas.get_annotated_image().pixelColor(50, 50) == QColor(255, 255, 255)

    # 3. Test Redo
    canvas.redo()
    assert canvas.was_annotated()
    assert canvas.get_annotated_image().pixelColor(50, 50) != QColor(255, 255, 255)

    # 4. Test Rectangle tool
    canvas.set_tool(ImageAnnotationCanvas.TOOL_RECTANGLE)
    canvas.set_color(QColor("#34c759"))  # Green
    canvas.set_stroke_width(2)

    r_start = to_vp(10, 10)
    r_end = to_vp(60, 60)
    canvas.mousePressEvent(mouse_ev(QEvent.Type.MouseButtonPress, r_start))
    canvas.mouseMoveEvent(mouse_ev(QEvent.Type.MouseMove, r_end))
    canvas.mouseReleaseEvent(mouse_ev(QEvent.Type.MouseButtonRelease, r_end))
    # Border of rectangle should now be colored
    assert canvas.get_annotated_image().pixelColor(10, 10) != QColor(255, 255, 255)

    # 5. Test Circle tool
    canvas.set_tool(ImageAnnotationCanvas.TOOL_CIRCLE)
    canvas.set_color(QColor("#00e5ff"))  # Cyan
    c_start = to_vp(100, 100)
    c_end = to_vp(180, 180)
    canvas.mousePressEvent(mouse_ev(QEvent.Type.MouseButtonPress, c_start))
    canvas.mouseMoveEvent(mouse_ev(QEvent.Type.MouseMove, c_end))
    canvas.mouseReleaseEvent(mouse_ev(QEvent.Type.MouseButtonRelease, c_end))
    assert canvas.was_annotated()

    # 6. Test Text tool (programmatic text placement)
    canvas.set_tool(ImageAnnotationCanvas.TOOL_TEXT)
    canvas.set_color(QColor("#ffcc00"))  # Yellow
    canvas.add_text_at(QPoint(120, 40), "ALERT")
    assert canvas.was_annotated()
    # Glyphs render inside the text bounding box
    assert any(canvas.get_annotated_image().pixelColor(x, y) != QColor(255, 255, 255) for x in range(120, 160) for y in range(40, 70))

    # 7. Test Reset Image back to pristine state
    canvas.reset_image()
    assert not canvas.was_annotated()
    # Image should be back to all white
    assert canvas.get_annotated_image().pixelColor(50, 50) == QColor(255, 255, 255)
    assert canvas.get_annotated_image().pixelColor(10, 10) == QColor(255, 255, 255)

    # Undo reset should restore all annotations
    canvas.undo()
    assert canvas.was_annotated()
    assert canvas.get_annotated_image().pixelColor(50, 50) != QColor(255, 255, 255)


def test_resize_image_dialog_with_annotation_controls(qapp):
    """Verifies that ResizeImageDialog integrates markup toolbar, tool selection, swatches, and dimensions."""
    img = QImage(300, 200, QImage.Format_ARGB32_Premultiplied)
    img.fill(0xFFFFFFFF)

    dlg = ResizeImageDialog(
        current_width=300,
        current_height=200,
        original_width=300,
        original_height=200,
        image=img,
    )

    try:
        assert dlg.canvas is not None
        assert not dlg.was_image_annotated()

        # Tool buttons switch tool on canvas
        dlg.btn_tool_circle.click()
        assert dlg.canvas._active_tool == ImageAnnotationCanvas.TOOL_CIRCLE

        dlg.btn_tool_rect.click()
        assert dlg.canvas._active_tool == ImageAnnotationCanvas.TOOL_RECTANGLE

        dlg.btn_tool_pen.click()
        assert dlg.canvas._active_tool == ImageAnnotationCanvas.TOOL_PEN

        dlg.btn_tool_text.click()
        assert dlg.canvas._active_tool == ImageAnnotationCanvas.TOOL_TEXT

        # Stroke width buttons
        dlg.btn_stroke_thin.click()
        assert dlg.canvas._stroke_width == 2

        dlg.btn_stroke_thick.click()
        assert dlg.canvas._stroke_width == 8

        # Annotate via canvas helper
        dlg.canvas.add_text_at(QPoint(50, 50), "NOTE")
        assert dlg.was_image_annotated()
        annotated = dlg.get_annotated_image()
        assert annotated is not None and not annotated.isNull()

        # Undo via dialog button
        dlg.btn_undo.click()
        assert not dlg.was_image_annotated()

        # Redo via dialog button
        dlg.btn_redo.click()
        assert dlg.was_image_annotated()

        # Reset via dialog button
        dlg.btn_reset.click()
        assert not dlg.was_image_annotated()

    finally:
        dlg.deleteLater()


def test_editor_double_click_opens_resize_dialog_and_applies_markup(qapp, services):
    """Verifies that double-clicking an image in TechPadEditor opens the dialog and applies markup and dimensions."""
    scratch_service, img_service, session_service = services
    main_window = TechPadMainWindow(scratch_service, img_service, session_service)

    try:
        editor = main_window.tab_widget.get_current_editor()
        assert editor is not None

        # Insert a 400x200 test image
        img = QImage(400, 200, QImage.Format_RGB32)
        img.fill(0xFF336699)
        editor.insert_embedded_image(img)

        info = editor._get_image_info_at_doc_pos(0)
        assert info is not None
        raw_name = info["name"].replace("image://local/", "").split("/")[-1]

        # Prepare a marked-up QImage
        annotated_img = QImage(400, 200, QImage.Format_RGB32)
        annotated_img.fill(0xFFFF0000)  # Red filled

        class MockAnnotateDialog:
            def __init__(self, *args, **kwargs):
                pass
            def exec(self):
                return QDialog.Accepted
            def was_image_annotated(self):
                return True
            def get_annotated_image(self):
                return annotated_img
            def get_dimensions(self):
                return (350, 175)

        import src.ui.components.editor as editor_mod
        orig_dlg = editor_mod.ResizeImageDialog
        editor_mod.ResizeImageDialog = MockAnnotateDialog
        try:
            editor._open_resize_dialog(info)

            # Check that in_memory_images contains updated JPEG bytes
            assert raw_name in editor.in_memory_images
            assert len(editor.in_memory_images[raw_name]) > 0

            # Check dimensions updated to (350, 175)
            info_after = editor._get_image_info_at_doc_pos(0)
            assert info_after["current_width"] == 350
            assert info_after["current_height"] == 175

            # Check QTextDocument resource was updated with annotated image
            res = editor.document().resource(QTextDocument.ImageResource, info["name"])
            assert isinstance(res, QImage) and not res.isNull()
            assert res.pixelColor(10, 10) == QColor(255, 0, 0)
        finally:
            editor_mod.ResizeImageDialog = orig_dlg

    finally:
        try:
            main_window.quit_application()
        except Exception:
            pass
        qapp.removeEventFilter(main_window)
        main_window.deleteLater()


def test_image_editor_zoom_and_pan(qapp):
    """Verifies image zoom in, zoom out, reset, and Ctrl+Wheel / toolbar zoom controls."""
    img = QImage(200, 200, QImage.Format_ARGB32_Premultiplied)
    img.fill(0xFFFFFFFF)

    canvas = ImageAnnotationCanvas(img)
    canvas.resize(400, 400)

    # Initial zoom is 1.0 (100%)
    assert canvas.get_zoom_factor() == 1.0

    # Zoom in
    canvas.zoom_in()
    assert canvas.get_zoom_factor() == 1.25

    # Zoom in again
    canvas.zoom_in()
    assert round(canvas.get_zoom_factor(), 3) == 1.562

    # Zoom out
    canvas.zoom_out()
    assert canvas.get_zoom_factor() == 1.25

    # Reset zoom
    canvas.reset_zoom()
    assert canvas.get_zoom_factor() == 1.0

    # Ctrl+Mouse Wheel Zoom In
    wheel_in = QWheelEvent(
        QPointF(200, 200),
        QPointF(200, 200),
        QPoint(0, 0),
        QPoint(0, 120),
        Qt.NoButton,
        Qt.ControlModifier,
        Qt.ScrollUpdate,
        False,
    )
    canvas.wheelEvent(wheel_in)
    assert canvas.get_zoom_factor() == 1.25

    # Ctrl+Mouse Wheel Zoom Out
    wheel_out = QWheelEvent(
        QPointF(200, 200),
        QPointF(200, 200),
        QPoint(0, 0),
        QPoint(0, -120),
        Qt.NoButton,
        Qt.ControlModifier,
        Qt.ScrollUpdate,
        False,
    )
    canvas.wheelEvent(wheel_out)
    assert canvas.get_zoom_factor() == 1.0

    # Test dialog zoom toolbar integration
    dlg = ResizeImageDialog(
        current_width=200,
        current_height=200,
        original_width=200,
        original_height=200,
        image=img,
    )
    try:
        assert dlg.lbl_zoom_val.text() == "100%"
        dlg.btn_zoom_in.click()
        assert dlg.canvas.get_zoom_factor() == 1.25
        assert dlg.lbl_zoom_val.text() == "125%"

        dlg.btn_zoom_out.click()
        assert dlg.canvas.get_zoom_factor() == 1.0
        assert dlg.lbl_zoom_val.text() == "100%"

        dlg.btn_zoom_reset.click()
        assert dlg.canvas.get_zoom_factor() == 1.0
    finally:
        dlg.deleteLater()


def test_image_editor_window_title_and_maximize(qapp):
    """Verifies that the dialog is named 'Image Editor', pops up maximized by default, and toggles restore/maximize."""
    img = QImage(200, 100, QImage.Format_ARGB32_Premultiplied)
    img.fill(0xFF445566)

    dlg = ResizeImageDialog(
        current_width=200,
        current_height=100,
        original_width=200,
        original_height=100,
        image=img,
    )
    try:
        # Verify Window Title is 'Image Editor'
        assert dlg.windowTitle() == "Image Editor"

        # Verify Window Flags include MinMaxButtonsHint for OS title bar double-click maximize
        flags = dlg.windowFlags()
        assert bool(flags & Qt.WindowMinMaxButtonsHint)

        # Dialog pops up maximized at full screen by default
        assert dlg.isMaximized() or bool(dlg.windowState() & Qt.WindowMaximized)
        assert dlg.btn_maximize.text() == "❐ Restore"

        # Test toggle restore back to normal size
        dlg._toggle_maximize()
        assert not dlg.isMaximized()
        assert dlg.btn_maximize.text() == "⛶ Maximize"

        # Test toggle back to full screen
        dlg._toggle_maximize()
        assert dlg.isMaximized() or bool(dlg.windowState() & Qt.WindowMaximized)
        assert dlg.btn_maximize.text() == "❐ Restore"
    finally:
        dlg.deleteLater()


def test_text_annotation_rectangle_and_size_like_paint(qapp):
    """Verifies Paint-style text placement inside a bounding rectangle with custom font size and optional border."""
    img = QImage(400, 300, QImage.Format_ARGB32_Premultiplied)
    img.fill(0xFFFFFFFF)

    canvas = ImageAnnotationCanvas(img)
    canvas.resize(400, 300)

    # 1. Custom font size selection
    canvas.set_font_size(24)
    assert canvas.get_font_size() == 24

    # 2. Add text within explicit bounding rectangle with callout border
    target_box = QRect(40, 40, 220, 80)
    canvas.add_text_in_rect(target_box, "SERVER ERROR\nCHECK IIS", font_size=24, draw_border=True)
    assert canvas.was_annotated()

    # Pixels inside target rectangle must be colored (border and text)
    annotated = canvas.get_annotated_image()
    assert any(annotated.pixelColor(x, y) != QColor(255, 255, 255) for x in range(40, 260) for y in range(40, 120))

    # 3. Test TextAnnotationDialog
    text_dlg = TextAnnotationDialog(target_box, font_size=20, color=QColor("#ff3b30"))
    try:
        assert text_dlg.windowTitle() == "Add Text to Image"
        assert text_dlg.get_font_size() == 20
        text_dlg.spin_size.setValue(32)
        assert text_dlg.get_font_size() == 32

        assert not text_dlg.should_draw_border()
        text_dlg.chk_border.setChecked(True)
        assert text_dlg.should_draw_border()

        text_dlg.text_edit.setPlainText("Test callout content")
        assert text_dlg.get_text() == "Test callout content"
    finally:
        text_dlg.deleteLater()


def test_image_editor_move_shapes_and_text(qapp):
    """Verifies that drawn shapes (rectangles, circles, pen) and text can be selected, moved via drag or arrow keys, deleted, and undone."""
    img = QImage(600, 400, QImage.Format_ARGB32_Premultiplied)
    img.fill(0xFFFFFFFF)

    canvas = ImageAnnotationCanvas(img)
    canvas.resize(600, 400)

    # 1. Add a rectangle item
    rect_item = AnnotationItem(
        AnnotationItem.TYPE_RECTANGLE,
        QColor("#ff3b30"),
        stroke_width=4,
        rect=QRect(50, 50, 100, 80),
    )
    canvas.get_items().append(rect_item)

    # 2. Add a text item
    canvas.add_text_in_rect(QRect(200, 150, 150, 60), "INITIAL TEXT", font_size=18, draw_border=True)
    assert len(canvas.get_items()) == 2
    text_item = canvas.get_items()[-1]
    assert text_item.item_type == AnnotationItem.TYPE_TEXT
    assert text_item.text == "INITIAL TEXT"

    # 3. Switch to Select tool
    canvas.set_tool(ImageAnnotationCanvas.TOOL_SELECT)
    assert canvas._active_tool == ImageAnnotationCanvas.TOOL_SELECT

    # 4. Select the rectangle by clicking inside it
    hit = canvas.select_item_at(QPoint(80, 80))
    assert hit is rect_item
    assert canvas.get_selected_item() is rect_item

    # 5. Move the rectangle with move_selected_item (+30, +20)
    canvas.move_selected_item(30, 20)
    assert rect_item.rect == QRect(80, 70, 100, 80)

    # Verify Undo restores rectangle to (50, 50)
    canvas.undo()
    rect_after_undo = canvas.get_items()[0]
    assert rect_after_undo.rect == QRect(50, 50, 100, 80)

    # Verify Redo moves it forward again to (80, 70)
    canvas.redo()
    selected = canvas.get_items()[0]
    assert selected.rect == QRect(80, 70, 100, 80)

    # 6. Select text item by clicking inside it
    hit_text = canvas.select_item_at(QPoint(250, 170))
    assert hit_text is not None
    assert hit_text.item_type == AnnotationItem.TYPE_TEXT
    assert canvas.get_selected_item() == hit_text
    orig_text_rect = QRect(hit_text.rect)

    # 7. Nudge text with Arrow keys (keyboard navigation)
    # Right arrow: +1px
    key_right = QKeyEvent(QEvent.KeyPress, Qt.Key_Right, Qt.NoModifier)
    canvas.keyPressEvent(key_right)
    assert canvas.get_selected_item().rect.x() == orig_text_rect.x() + 1

    # Shift + Down arrow: +10px
    key_shift_down = QKeyEvent(QEvent.KeyPress, Qt.Key_Down, Qt.ShiftModifier)
    canvas.keyPressEvent(key_shift_down)
    assert canvas.get_selected_item().rect.y() == orig_text_rect.y() + 10

    # 8. Test mouse drag move simulation in canvas
    disp_rect = canvas.get_image_display_rect()
    curr_rect = canvas.get_selected_item().rect
    img_pt = QPoint(curr_rect.center())
    vp_x = int(disp_rect.x() + img_pt.x() * (disp_rect.width() / img.width()))
    vp_y = int(disp_rect.y() + img_pt.y() * (disp_rect.height() / img.height()))

    press_ev = QMouseEvent(QEvent.MouseButtonPress, QPointF(vp_x, vp_y), QPointF(vp_x, vp_y), Qt.LeftButton, Qt.LeftButton, Qt.NoModifier)
    canvas.mousePressEvent(press_ev)
    assert canvas._is_moving_item is True

    # Drag horizontally in viewport
    move_ev = QMouseEvent(QEvent.MouseMove, QPointF(vp_x + 20, vp_y), QPointF(vp_x + 20, vp_y), Qt.LeftButton, Qt.LeftButton, Qt.NoModifier)
    canvas.mouseMoveEvent(move_ev)

    release_ev = QMouseEvent(QEvent.MouseButtonRelease, QPointF(vp_x + 20, vp_y), QPointF(vp_x + 20, vp_y), Qt.LeftButton, Qt.NoButton, Qt.NoModifier)
    canvas.mouseReleaseEvent(release_ev)
    assert canvas._is_moving_item is False

    # 9. Delete selected text item
    key_del = QKeyEvent(QEvent.KeyPress, Qt.Key_Delete, Qt.NoModifier)
    canvas.keyPressEvent(key_del)
    assert len(canvas.get_items()) == 1
    assert canvas.get_selected_item() is None

    # Undo restores the deleted item
    canvas.undo()
    assert len(canvas.get_items()) == 2
    assert canvas.get_items()[-1].item_type == AnnotationItem.TYPE_TEXT

    # 10. Test Dialog tool shortcuts and toolbar buttons
    dlg = ResizeImageDialog(
        current_width=600,
        current_height=400,
        original_width=600,
        original_height=400,
        image=img,
    )
    try:
        assert dlg.canvas._active_tool == ImageAnnotationCanvas.TOOL_PEN
        dlg.btn_tool_select.click()
        assert dlg.canvas._active_tool == ImageAnnotationCanvas.TOOL_SELECT
        dlg.btn_tool_rect.click()
        assert dlg.canvas._active_tool == ImageAnnotationCanvas.TOOL_RECTANGLE
    finally:
        dlg.deleteLater()


def test_image_editor_edge_move_and_rotation(qapp):
    """Verifies that forms and text can be moved by clicking and dragging their bounding box edges, and can be rotated."""
    img = QImage(600, 400, QImage.Format_ARGB32_Premultiplied)
    img.fill(0xFFFFFFFF)

    canvas = ImageAnnotationCanvas(img)
    canvas.resize(600, 400)

    # 1. Add a rectangle form at (100, 100, 200, 100)
    rect_item = AnnotationItem(
        AnnotationItem.TYPE_RECTANGLE,
        QColor("#ff3b30"),
        stroke_width=4,
        rect=QRect(100, 100, 200, 100),
    )
    canvas.get_items().append(rect_item)
    canvas._selected_item = rect_item
    canvas.set_tool(ImageAnnotationCanvas.TOOL_SELECT)

    disp_rect = canvas.get_image_display_rect()
    scale_x = disp_rect.width() / img.width()
    scale_y = disp_rect.height() / img.height()

    # 2. Test Edge Hit Testing:
    # Top Edge:
    top_edge_vp = QPoint(
        int(disp_rect.x() + 200 * scale_x),
        int(disp_rect.y() + 100 * scale_y - 4),
    )
    handle, it = canvas.get_selection_handle_at(top_edge_vp)
    assert it is rect_item
    assert handle == ImageAnnotationCanvas.HANDLE_EDGE_TOP

    # Drag Top Edge to move item:
    press_ev = QMouseEvent(QEvent.MouseButtonPress, QPointF(top_edge_vp), QPointF(top_edge_vp), Qt.LeftButton, Qt.LeftButton, Qt.NoModifier)
    canvas.mousePressEvent(press_ev)
    assert canvas._action_mode == ImageAnnotationCanvas.ACTION_MOVE

    move_ev = QMouseEvent(QEvent.MouseMove, QPointF(top_edge_vp.x() + 25, top_edge_vp.y() + 15), QPointF(top_edge_vp.x() + 25, top_edge_vp.y() + 15), Qt.LeftButton, Qt.LeftButton, Qt.NoModifier)
    canvas.mouseMoveEvent(move_ev)

    release_ev = QMouseEvent(QEvent.MouseButtonRelease, QPointF(top_edge_vp.x() + 25, top_edge_vp.y() + 15), QPointF(top_edge_vp.x() + 25, top_edge_vp.y() + 15), Qt.LeftButton, Qt.NoButton, Qt.NoModifier)
    canvas.mouseReleaseEvent(release_ev)
    assert canvas._action_mode == ImageAnnotationCanvas.ACTION_NONE

    # Item moved from (100, 100)
    assert rect_item.rect.x() > 100
    assert rect_item.rect.y() > 100

    # 3. Test Rotation Handle Hit Testing & Dragging:
    # Rotation handle is 24px above the top edge
    b_rect = rect_item.get_bounding_rect()
    rot_handle_vp = QPoint(
        int(disp_rect.x() + b_rect.center().x() * scale_x),
        int(disp_rect.y() + b_rect.top() * scale_y - 24),
    )
    handle_rot, it_rot = canvas.get_selection_handle_at(rot_handle_vp)
    assert it_rot is rect_item
    assert handle_rot == ImageAnnotationCanvas.HANDLE_ROTATE

    # Drag rotation handle to rotate:
    rot_press = QMouseEvent(QEvent.MouseButtonPress, QPointF(rot_handle_vp), QPointF(rot_handle_vp), Qt.LeftButton, Qt.LeftButton, Qt.NoModifier)
    canvas.mousePressEvent(rot_press)
    assert canvas._action_mode == ImageAnnotationCanvas.ACTION_ROTATE
    assert canvas._is_rotating is True

    # Drag 90 degrees to the right
    center_vp_x = int(disp_rect.x() + b_rect.center().x() * scale_x)
    center_vp_y = int(disp_rect.y() + b_rect.center().y() * scale_y)
    rot_move = QMouseEvent(QEvent.MouseMove, QPointF(center_vp_x + 50, center_vp_y), QPointF(center_vp_x + 50, center_vp_y), Qt.LeftButton, Qt.LeftButton, Qt.NoModifier)
    canvas.mouseMoveEvent(rot_move)
    assert canvas._selected_item.rotation != 0.0

    rot_release = QMouseEvent(QEvent.MouseButtonRelease, QPointF(center_vp_x + 50, center_vp_y), QPointF(center_vp_x + 50, center_vp_y), Qt.LeftButton, Qt.NoButton, Qt.NoModifier)
    canvas.mouseReleaseEvent(rot_release)
    assert canvas._action_mode == ImageAnnotationCanvas.ACTION_NONE
    assert canvas._is_rotating is False

    # 4. Test rotate_selected_item (90 degrees):
    prev_rot = rect_item.rotation
    canvas.rotate_selected_item(90.0)
    assert round(rect_item.rotation) == round((prev_rot + 90.0) % 360.0)

    # Undo restores rotation
    canvas.undo()
    assert round(canvas.get_items()[0].rotation) == round(prev_rot)

    # 5. Test Keyboard Rotation Shortcuts: [ and ]
    key_bracket_right = QKeyEvent(QEvent.KeyPress, Qt.Key_BracketRight, Qt.NoModifier)
    canvas.keyPressEvent(key_bracket_right)
    assert round(canvas.get_selected_item().rotation) == round((prev_rot + 15.0) % 360.0)

    key_bracket_left = QKeyEvent(QEvent.KeyPress, Qt.Key_BracketLeft, Qt.NoModifier)
    canvas.keyPressEvent(key_bracket_left)
    assert round(canvas.get_selected_item().rotation) == round(prev_rot)

    # 6. Test Text Box Edge Move and Rotation:
    canvas.add_text_in_rect(QRect(50, 50, 160, 60), "ROTATING TEXT", font_size=18, draw_border=True)
    text_item = canvas.get_selected_item()
    assert text_item.item_type == AnnotationItem.TYPE_TEXT
    assert text_item.text == "ROTATING TEXT"
    assert canvas._active_tool == ImageAnnotationCanvas.TOOL_SELECT

    # Rotate text 45 degrees
    text_item.rotate(45.0)
    assert text_item.rotation == 45.0
    annotated = canvas.get_annotated_image()
    assert not annotated.isNull()

    # 7. Test Dialog Rotate 90 Button and Shortcut (Ctrl+R):
    dlg = ResizeImageDialog(
        current_width=600,
        current_height=400,
        original_width=600,
        original_height=400,
        image=img,
    )
    try:
        dlg.canvas.add_text_in_rect(QRect(100, 100, 120, 50), "TEST", font_size=16)
        dlg.btn_rotate_90.click()
        assert dlg.canvas.get_selected_item().rotation == 90.0
        dlg.btn_rotate_90.click()
        assert dlg.canvas.get_selected_item().rotation == 180.0
    finally:
        dlg.deleteLater()


def test_image_editor_line_tool_and_shift_snap(qapp):
    """Verifies the Line tool, straight line snapping when holding Shift, moving, rotating, and dialog toolbar integration."""
    # 1. Test snap_to_straight_line helper (0°, 45°, 90°, etc.)
    p1 = QPoint(100, 100)

    # Near horizontal (dx=100, dy=4 -> snapped angle 0°)
    snap_h = ImageAnnotationCanvas.snap_to_straight_line(p1, QPoint(200, 104))
    assert snap_h.y() == 100
    assert snap_h.x() == 200

    # Near vertical (dx=3, dy=100 -> snapped angle 90°)
    snap_v = ImageAnnotationCanvas.snap_to_straight_line(p1, QPoint(103, 200))
    assert snap_v.x() == 100
    assert snap_v.y() == 200

    # Near 45° diagonal (dx=102, dy=98 -> snapped angle 45°)
    snap_d = ImageAnnotationCanvas.snap_to_straight_line(p1, QPoint(202, 198))
    # Distance is approx 141.4 -> dx and dy should be equal
    assert snap_d.x() - p1.x() == snap_d.y() - p1.y()

    # 2. Test Canvas Line Drawing without Shift (free angle)
    img = QImage(600, 400, QImage.Format_ARGB32_Premultiplied)
    img.fill(0xFFFFFFFF)

    canvas = ImageAnnotationCanvas(img)
    canvas.resize(600, 400)
    canvas.set_tool(ImageAnnotationCanvas.TOOL_LINE)
    assert canvas._active_tool == ImageAnnotationCanvas.TOOL_LINE

    disp_rect = canvas.get_image_display_rect()
    scale_x = disp_rect.width() / img.width()
    scale_y = disp_rect.height() / img.height()

    vp_p1 = QPoint(int(disp_rect.x() + 50 * scale_x), int(disp_rect.y() + 50 * scale_y))
    vp_p2 = QPoint(int(disp_rect.x() + 150 * scale_x), int(disp_rect.y() + 90 * scale_y))

    # Mouse press at (50, 50)
    press_ev = QMouseEvent(QEvent.MouseButtonPress, QPointF(vp_p1), QPointF(vp_p1), Qt.LeftButton, Qt.LeftButton, Qt.NoModifier)
    canvas.mousePressEvent(press_ev)
    assert canvas._is_drawing is True

    # Mouse move to (150, 90)
    move_ev = QMouseEvent(QEvent.MouseMove, QPointF(vp_p2), QPointF(vp_p2), Qt.LeftButton, Qt.LeftButton, Qt.NoModifier)
    canvas.mouseMoveEvent(move_ev)

    # Mouse release at (150, 90)
    rel_ev = QMouseEvent(QEvent.MouseButtonRelease, QPointF(vp_p2), QPointF(vp_p2), Qt.LeftButton, Qt.NoButton, Qt.NoModifier)
    canvas.mouseReleaseEvent(rel_ev)

    assert len(canvas.get_items()) == 1
    free_line = canvas.get_items()[0]
    assert free_line.item_type == AnnotationItem.TYPE_LINE
    assert len(free_line.points) == 2
    assert free_line.points[0] == QPoint(50, 50)
    assert free_line.points[1] == QPoint(150, 90)
    # Drawing a line switches back to Select tool automatically
    assert canvas._active_tool == ImageAnnotationCanvas.TOOL_SELECT
    assert canvas.get_selected_item() is free_line

    # 3. Test Canvas Line Drawing WITH Shift (straight horizontal line snap)
    canvas.set_tool(ImageAnnotationCanvas.TOOL_LINE)
    vp_p3 = QPoint(int(disp_rect.x() + 50 * scale_x), int(disp_rect.y() + 200 * scale_x))
    vp_p4 = QPoint(int(disp_rect.x() + 250 * scale_x), int(disp_rect.y() + 208 * scale_x))

    press_ev_shift = QMouseEvent(QEvent.MouseButtonPress, QPointF(vp_p3), QPointF(vp_p3), Qt.LeftButton, Qt.LeftButton, Qt.ShiftModifier)
    canvas.mousePressEvent(press_ev_shift)

    move_ev_shift = QMouseEvent(QEvent.MouseMove, QPointF(vp_p4), QPointF(vp_p4), Qt.LeftButton, Qt.LeftButton, Qt.ShiftModifier)
    canvas.mouseMoveEvent(move_ev_shift)

    rel_ev_shift = QMouseEvent(QEvent.MouseButtonRelease, QPointF(vp_p4), QPointF(vp_p4), Qt.LeftButton, Qt.NoButton, Qt.ShiftModifier)
    canvas.mouseReleaseEvent(rel_ev_shift)

    assert len(canvas.get_items()) == 2
    straight_line = canvas.get_items()[1]
    assert straight_line.item_type == AnnotationItem.TYPE_LINE
    # Because Shift was held and dy was very small (8px vs 200px), it snapped to perfectly straight horizontal line
    assert straight_line.points[0].y() == straight_line.points[1].y()

    # 4. Test Move and Rotate on Line Item
    canvas.select_item_at(straight_line.points[0])
    assert canvas.get_selected_item() is straight_line

    orig_p0 = QPoint(straight_line.points[0])
    orig_p1 = QPoint(straight_line.points[1])
    canvas.move_selected_item(15, 25)
    assert straight_line.points[0] == QPoint(orig_p0.x() + 15, orig_p0.y() + 25)
    assert straight_line.points[1] == QPoint(orig_p1.x() + 15, orig_p1.y() + 25)

    # Undo restores straight line position
    canvas.undo()
    restored_line = canvas.get_items()[1]
    assert restored_line.points[0] == orig_p0
    assert restored_line.points[1] == orig_p1

    # Rotate straight line 90 degrees
    canvas.select_item_at(restored_line.points[0])
    canvas.rotate_selected_item(90.0)
    assert canvas.get_selected_item().rotation == 90.0

    # 5. Test Dialog Toolbar Line button and shortcut
    dlg = ResizeImageDialog(
        current_width=600,
        current_height=400,
        original_width=600,
        original_height=400,
        image=img,
    )
    try:
        assert hasattr(dlg, "btn_tool_line")
        assert dlg.btn_tool_line.text() == "📏 Line"
        dlg.btn_tool_line.click()
        assert dlg.canvas._active_tool == ImageAnnotationCanvas.TOOL_LINE

        # Verify tool changed signal syncs toolbar button
        dlg.canvas.set_tool(ImageAnnotationCanvas.TOOL_LINE)
        assert dlg.btn_tool_line.isChecked()
    finally:
        dlg.deleteLater()






