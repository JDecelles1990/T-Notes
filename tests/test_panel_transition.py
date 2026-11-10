"""Tests for slide transitions on side panes (Split, History, Categories, Active Ticket)."""

import pytest
from PySide6.QtCore import QCoreApplication, QEvent
from PySide6.QtTest import QTest
from PySide6.QtWidgets import QSplitter, QTextEdit

from src.database.connection import DatabaseManager
from src.database.migrations import init_database
from src.repositories.image_repository import ImageRepository
from src.repositories.scratchpad_repository import ScratchpadRepository
from src.repositories.session_repository import SessionRepository
from src.services.image_service import ImageService
from src.services.scratchpad_service import ScratchpadService
from src.services.session_service import SessionService
from src.ui.components import panel_transition
from src.ui.components.panel_transition import PanelWidthTransition
from src.ui.main_window import TechPadMainWindow


@pytest.fixture
def main_window(qapp, tmp_path):
    manager = DatabaseManager(tmp_path / "transition_test.db")
    init_database(manager)
    img_service = ImageService(ImageRepository(manager))
    scratch_service = ScratchpadService(ScratchpadRepository(manager), img_service)
    session_service = SessionService(SessionRepository(manager), scratch_service)
    window = TechPadMainWindow(scratch_service, img_service, session_service)
    yield window
    try:
        window.quit_application()
    finally:
        qapp.removeEventFilter(window)
        window.deleteLater()
        QCoreApplication.sendPostedEvents(None, QEvent.DeferredDelete)
        manager.close()

def _enable(monkeypatch):
    monkeypatch.setattr(panel_transition, "TRANSITIONS_ENABLED", True)


def _splitter(qapp):
    splitter = QSplitter()
    side, main = QTextEdit(), QTextEdit()
    side.setMinimumWidth(80)
    side.setMaximumWidth(400)
    splitter.addWidget(side)
    splitter.addWidget(main)
    splitter.resize(900, 300)
    splitter.setSizes([250, 650])
    splitter.show()
    qapp.processEvents()
    return splitter, side


def test_collapse_and_expand_animate_then_settle(qapp, monkeypatch):
    _enable(monkeypatch)
    splitter, side = _splitter(qapp)
    tr = PanelWidthTransition(side, default_width=250)
    assert tr.is_open

    tr.hide_panel()
    QTest.qWait(80)
    assert tr.running and side.isVisible()  # still sliding, not yet hidden
    assert tr.is_open is False
    QTest.qWait(450)
    assert side.isHidden() and not tr.running
    assert (side.minimumWidth(), side.maximumWidth()) == (80, 400)  # limits restored

    tr.show_panel()
    QTest.qWait(80)
    assert side.isVisible() and tr.running
    QTest.qWait(450)
    assert not tr.running and side.isVisible()
    assert 200 <= side.width() <= 400
    assert (side.minimumWidth(), side.maximumWidth()) == (80, 400)
    splitter.close()


def test_toggle_mid_animation_reverses_cleanly(qapp, monkeypatch):
    _enable(monkeypatch)
    splitter, side = _splitter(qapp)
    tr = PanelWidthTransition(side, default_width=250)
    tr.hide_panel()
    QTest.qWait(90)
    tr.show_panel()
    QTest.qWait(500)
    assert side.isVisible() and not tr.running
    assert (side.minimumWidth(), side.maximumWidth()) == (80, 400)
    splitter.close()


def test_disabled_transitions_are_immediate(qapp, monkeypatch):
    splitter, side = _splitter(qapp)  # autouse fixture leaves transitions disabled
    tr = PanelWidthTransition(side)
    tr.hide_panel()
    assert side.isHidden() and not tr.running
    tr.show_panel()
    assert side.isVisible() and not tr.running
    splitter.close()


def test_hidden_parent_never_animates(qapp, monkeypatch):
    _enable(monkeypatch)
    splitter = QSplitter()
    side = QTextEdit()
    splitter.addWidget(side)
    tr = PanelWidthTransition(side)
    assert tr.animation_allowed() is False
    tr.show_panel()
    assert not side.isHidden() and not tr.running


def test_split_sidebar_slides_open_and_closed(main_window, qapp, monkeypatch):
    main_window.resize(1100, 700)
    main_window.show()
    main_window.create_new_tab()
    qapp.processEvents()
    _enable(monkeypatch)

    main_window.open_split_view()
    assert main_window._split_transition.running
    QTest.qWait(500)
    assert main_window.secondary_tab_widget.isVisible()
    assert main_window.secondary_tab_widget.width() >= 200
    assert main_window.is_split_view_active is True

    main_window.close_split_view()
    assert main_window.secondary_tab_widget.isVisible()  # sliding closed
    assert main_window.is_split_view_active is False
    QTest.qWait(500)
    assert main_window.secondary_tab_widget.isHidden()
    assert main_window.secondary_tab_widget.count() == 1  # tab preserved
    assert all(s >= 100 for s in main_window._saved_splitter_sizes)

    main_window.open_split_view()
    QTest.qWait(500)
    assert main_window.secondary_tab_widget.isVisible()
    assert main_window.secondary_tab_widget.width() >= 200


def test_history_drawer_slides_open_and_closed(main_window, qapp, monkeypatch):
    main_window.resize(1200, 700)
    main_window.show()
    qapp.processEvents()
    _enable(monkeypatch)

    main_window._toggle_history_drawer()
    assert main_window._history_transition.running
    QTest.qWait(500)
    assert main_window.history_drawer.isVisible()
    assert main_window.history_drawer.width() >= 200
    assert main_window.history_drawer.maximumWidth() > 5000  # limits restored

    main_window._toggle_history_drawer()
    assert main_window.history_drawer.isVisible()  # sliding closed
    QTest.qWait(500)
    assert main_window.history_drawer.isHidden()
    assert main_window._user_history_drawer_open is False


def test_m365_category_and_ticket_panes_slide(main_window, qapp, monkeypatch):
    main_window.resize(1200, 750)
    main_window.show()
    qapp.processEvents()
    assert main_window.switch_workspace() is True
    qapp.processEvents()
    ws = main_window.m365_workspace
    _enable(monkeypatch)

    ws.nav_toggle.setChecked(False)
    assert ws._nav_transition.running and ws.navigation.isVisible()
    QTest.qWait(500)
    assert ws.navigation.isHidden()
    ws.nav_toggle.setChecked(True)
    QTest.qWait(500)
    assert ws.navigation.isVisible() and ws.navigation.width() >= 110
    assert (ws.navigation.minimumWidth(), ws.navigation.maximumWidth()) == (110, 180)

    ws.ticket_panel_toggle.setChecked(False)
    assert ws._ticket_transition.running and ws.ticket_sidebar.isVisible()
    QTest.qWait(500)
    assert ws.ticket_sidebar.isHidden()
    ws.ticket_panel_toggle.setChecked(True)
    QTest.qWait(500)
    assert ws.ticket_sidebar.isVisible() and ws.ticket_sidebar.width() >= 220

