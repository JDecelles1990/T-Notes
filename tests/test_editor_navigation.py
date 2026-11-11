"""Unit tests for TechPadEditor navigation: horizontal scrolling with Ctrl+Shift+Wheel and zoom in/out with Ctrl+Wheel."""

import pytest
from PySide6.QtCore import QPoint, QPointF, Qt
from PySide6.QtGui import QKeyEvent, QWheelEvent
from PySide6.QtWidgets import QApplication

from src.ui.components.editor import TechPadEditor


def test_techpad_editor_horizontal_scroll_ctrl_shift_wheel(qapp):
    """Verifies that Ctrl+Shift+Mouse Wheel (and Shift+Wheel) scrolls horizontal scrollbar."""
    editor = TechPadEditor(scratchpad_id=1, image_service=None)
    editor.resize(300, 200)

    # Ensure scrollbar has range to scroll
    hbar = editor.horizontalScrollBar()
    hbar.setRange(0, 500)
    hbar.setValue(0)
    assert hbar.maximum() == 500
    assert hbar.value() == 0

    # 1. Roll wheel down (negative delta) with Ctrl+Shift -> Scrolls Right
    ev_down = QWheelEvent(
        QPointF(50, 50),
        QPointF(50, 50),
        QPoint(0, 0),
        QPoint(0, -120),
        Qt.NoButton,
        Qt.ControlModifier | Qt.ShiftModifier,
        Qt.ScrollUpdate,
        False,
    )
    editor.wheelEvent(ev_down)
    assert hbar.value() > 0
    first_scroll = hbar.value()

    # Roll down again -> Scrolls further right
    editor.wheelEvent(ev_down)
    assert hbar.value() > first_scroll
    second_scroll = hbar.value()

    # 2. Roll wheel up (positive delta) with Ctrl+Shift -> Scrolls Left
    ev_up = QWheelEvent(
        QPointF(50, 50),
        QPointF(50, 50),
        QPoint(0, 0),
        QPoint(0, 120),
        Qt.NoButton,
        Qt.ControlModifier | Qt.ShiftModifier,
        Qt.ScrollUpdate,
        False,
    )
    editor.wheelEvent(ev_up)
    assert hbar.value() < second_scroll

    # 3. Test Dedicated Horizontal Wheel / Tilt (dx != 0)
    ev_tilt_right = QWheelEvent(
        QPointF(50, 50),
        QPointF(50, 50),
        QPoint(0, 0),
        QPoint(120, 0),
        Qt.NoButton,
        Qt.ControlModifier | Qt.ShiftModifier,
        Qt.ScrollUpdate,
        False,
    )
    prev_val = hbar.value()
    editor.wheelEvent(ev_tilt_right)
    assert hbar.value() > prev_val

    editor.deleteLater()


def test_techpad_editor_zoom_in_and_out_shift_wheel(qapp):
    """Verifies that Shift+Mouse Wheel (without Ctrl) zooms text in and out, with limits and reset."""
    editor = TechPadEditor(scratchpad_id=1, image_service=None)
    editor.setHtml("<p>Diagnostic Log Content</p>")

    assert editor.get_zoom_level() == 0
    assert editor.get_zoom_percentage() == 100

    # 1. Zoom in with Shift+Wheel Up (delta > 0, without Ctrl)
    ev_zoom_in = QWheelEvent(
        QPointF(50, 50),
        QPointF(50, 50),
        QPoint(0, 0),
        QPoint(0, 120),
        Qt.NoButton,
        Qt.ShiftModifier,
        Qt.ScrollUpdate,
        False,
    )
    editor.wheelEvent(ev_zoom_in)
    assert editor.get_zoom_level() == 1
    assert editor.get_zoom_percentage() == 110

    # Zoom in again
    editor.wheelEvent(ev_zoom_in)
    assert editor.get_zoom_level() == 2
    assert editor.get_zoom_percentage() == 120

    # 2. Zoom out with Shift+Wheel Down (delta < 0, without Ctrl)
    ev_zoom_out = QWheelEvent(
        QPointF(50, 50),
        QPointF(50, 50),
        QPoint(0, 0),
        QPoint(0, -120),
        Qt.NoButton,
        Qt.ShiftModifier,
        Qt.ScrollUpdate,
        False,
    )
    editor.wheelEvent(ev_zoom_out)
    assert editor.get_zoom_level() == 1
    assert editor.get_zoom_percentage() == 110

    editor.wheelEvent(ev_zoom_out)
    assert editor.get_zoom_level() == 0
    assert editor.get_zoom_percentage() == 100

    # 3. Zoom out below baseline
    editor.wheelEvent(ev_zoom_out)
    assert editor.get_zoom_level() == -1
    assert editor.get_zoom_percentage() == 90

    # 4. Reset zoom
    editor.reset_zoom()
    assert editor.get_zoom_level() == 0
    assert editor.get_zoom_percentage() == 100

    editor.deleteLater()


def test_techpad_editor_ctrl_wheel_fast_vertical_scroll(qapp):
    """Verifies that Ctrl+Mouse Wheel scrolls vertically faster (page step) without altering zoom level."""
    editor = TechPadEditor(scratchpad_id=1, image_service=None)
    editor.resize(300, 200)

    # Populate with tall content
    editor.setHtml("<p>" + "<br>".join(f"Line {i}: test incident details" for i in range(120)) + "</p>")

    vbar = editor.verticalScrollBar()
    vbar.setRange(0, 2000)
    vbar.setValue(0)
    assert vbar.maximum() == 2000
    assert vbar.value() == 0
    assert editor.get_zoom_level() == 0

    # 1. Roll wheel down with Ctrl -> Fast vertical scroll
    ev_ctrl_down = QWheelEvent(
        QPointF(50, 50),
        QPointF(50, 50),
        QPoint(0, 0),
        QPoint(0, -120),
        Qt.NoButton,
        Qt.ControlModifier,
        Qt.ScrollUpdate,
        False,
    )
    editor.wheelEvent(ev_ctrl_down)
    # Must scroll vertical scrollbar significantly (page step)
    assert vbar.value() > 0
    # Zoom level must remain 0 (not modified by Ctrl+Wheel!)
    assert editor.get_zoom_level() == 0

    down_pos = vbar.value()

    # 2. Roll wheel up with Ctrl -> Fast vertical scroll back up
    ev_ctrl_up = QWheelEvent(
        QPointF(50, 50),
        QPointF(50, 50),
        QPoint(0, 0),
        QPoint(0, 120),
        Qt.NoButton,
        Qt.ControlModifier,
        Qt.ScrollUpdate,
        False,
    )
    editor.wheelEvent(ev_ctrl_up)
    assert vbar.value() < down_pos
    assert editor.get_zoom_level() == 0

    editor.deleteLater()


def test_techpad_editor_keyboard_zoom_shortcuts(qapp):
    """Verifies keyboard shortcuts: Ctrl++ / Ctrl+= (Zoom In), Ctrl+- (Zoom Out), Ctrl+0 (Reset Zoom)."""
    editor = TechPadEditor(scratchpad_id=1, image_service=None)
    editor.setHtml("<p>Keyboard Zoom Test</p>")

    assert editor.get_zoom_level() == 0

    # 1. Ctrl+= (Standard Plus key without shift)
    key_equal = QKeyEvent(QKeyEvent.KeyPress, Qt.Key_Equal, Qt.ControlModifier)
    editor.keyPressEvent(key_equal)
    assert editor.get_zoom_level() == 1

    # 2. Ctrl++ (Plus key)
    key_plus = QKeyEvent(QKeyEvent.KeyPress, Qt.Key_Plus, Qt.ControlModifier)
    editor.keyPressEvent(key_plus)
    assert editor.get_zoom_level() == 2

    # 3. Ctrl+- (Minus key)
    key_minus = QKeyEvent(QKeyEvent.KeyPress, Qt.Key_Minus, Qt.ControlModifier)
    editor.keyPressEvent(key_minus)
    assert editor.get_zoom_level() == 1

    # 4. Ctrl+0 (Reset Zoom)
    key_zero = QKeyEvent(QKeyEvent.KeyPress, Qt.Key_0, Qt.ControlModifier)
    editor.keyPressEvent(key_zero)
    assert editor.get_zoom_level() == 0

    # 5. Clamping at limits
    for _ in range(50):
        editor.zoom_in()
    assert editor.get_zoom_level() == TechPadEditor.MAX_ZOOM_LEVEL

    for _ in range(60):
        editor.zoom_out()
    assert editor.get_zoom_level() == TechPadEditor.MIN_ZOOM_LEVEL

    editor.reset_zoom()
    assert editor.get_zoom_level() == 0

    editor.deleteLater()


def test_techpad_editor_context_menu_reset_zoom(qapp, monkeypatch):
    """Verifies that the context menu includes Reset Zoom when zoomed in or out."""
    from PySide6.QtWidgets import QMenu

    editor = TechPadEditor(scratchpad_id=1, image_service=None)
    editor.setHtml("<p>Context Menu Zoom Test</p>")
    monkeypatch.setattr(editor, "createStandardContextMenu", lambda: QMenu(editor))

    # When zoom is 100% (level 0), no Reset Zoom action
    menu_normal = editor.create_custom_context_menu(QPoint(10, 10))
    action_texts = [a.text() for a in menu_normal.actions()]
    assert not any("Reset Zoom" in text for text in action_texts)

    # When zoomed in to 120% (level 2), Reset Zoom action is present
    editor.zoom_in(2)
    menu_zoomed = editor.create_custom_context_menu(QPoint(10, 10))
    action_texts_zoomed = [a.text() for a in menu_zoomed.actions()]
    assert any("Reset Zoom" in text and "120%" in text for text in action_texts_zoomed)

    # When zoomed out to 90% (level -1), Reset Zoom action is present
    editor.zoom_out(3)
    menu_zoomed_out = editor.create_custom_context_menu(QPoint(10, 10))
    action_texts_zoomed_out = [a.text() for a in menu_zoomed_out.actions()]
    assert any("Reset Zoom" in text and "90%" in text for text in action_texts_zoomed_out)

    editor.deleteLater()

