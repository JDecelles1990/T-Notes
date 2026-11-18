"""Tests for Neon Aurora visuals, transitions, expanded badges, Tech Tools, and Command Palette."""

import re
import uuid
import pytest
from PySide6.QtCore import QCoreApplication, QEvent, QPoint, Qt
from PySide6.QtTest import QTest
from PySide6.QtWidgets import (
    QApplication,
    QComboBox,
    QDialog,
    QLabel,
    QLineEdit,
    QPushButton,
    QSpinBox,
    QVBoxLayout,
    QWidget,
)

from src.core.constants import LOG_BADGES
from src.database.connection import DatabaseManager
from src.database.migrations import init_database
from src.repositories.image_repository import ImageRepository
from src.repositories.scratchpad_repository import ScratchpadRepository
from src.repositories.session_repository import SessionRepository
from src.services.image_service import ImageService
from src.services.scratchpad_service import ScratchpadService
from src.services.session_service import SessionService
from src.services.tech_tools_service import TechToolsService
from src.ui.components import panel_transition
from src.ui.components.editor import TechPadEditor
from src.ui.components.glow_effect import (
    AuroraAccentBar,
    InputGlowAnimator,
    apply_glow_to_buttons,
    apply_glow_to_inputs,
    install_input_glow,
    pulse_widget_glow,
)
from src.ui.components.panel_transition import (
    SlideFadeBarTransition,
    WidgetFadeTransition,
    animate_bar_show,
    animate_dialog_show,
)
from src.ui.dialogs.command_palette_dialog import CommandPaletteDialog, PaletteEntry
from src.ui.dialogs.quick_tools_dialog import QuickToolsDialog
from src.ui.main_window import TechPadMainWindow


@pytest.fixture
def main_window(qapp, tmp_path):
    db_file = tmp_path / "visual_enhancements_test.db"
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
    try:
        window.quit_application()
    finally:
        qapp.removeEventFilter(window)
        window.deleteLater()
        QCoreApplication.sendPostedEvents(None, QEvent.DeferredDelete)
        manager.close()


def test_input_glow_animator_hover_focus_and_skip_internal_children(qapp):
    host = QWidget()
    layout = QVBoxLayout(host)
    btn_focus = QPushButton("FocusSink", host)
    line = QLineEdit(host)
    spin = QSpinBox(host)
    combo = QComboBox(host)
    combo.setEditable(True)
    layout.addWidget(btn_focus)
    layout.addWidget(line)
    layout.addWidget(spin)
    layout.addWidget(combo)
    host.show()
    btn_focus.setFocus()
    QTest.qWait(40)

    count = apply_glow_to_inputs([host])
    assert count == 3

    # Internal child line edits inside spinbox & editable combobox must not get duplicate allocators
    assert getattr(spin.lineEdit(), "_input_glow_animator", None) is None
    assert getattr(combo.lineEdit(), "_input_glow_animator", None) is None

    anim: InputGlowAnimator = getattr(line, "_input_glow_animator")
    assert anim is install_input_glow(line)  # Idempotent
    assert anim.level == 0.0
    assert anim.is_glowing is False

    # Hover activates glow when unfocused
    QApplication.sendEvent(line, QEvent(QEvent.Enter))
    QTest.qWait(220)
    assert anim.is_hovered is True
    assert anim.is_glowing is True
    assert line.graphicsEffect().isEnabled() is True

    # Leave returns to idle when unfocused
    QApplication.sendEvent(line, QEvent(QEvent.Leave))
    QTest.qWait(280)
    assert anim.is_hovered is False
    assert anim.is_glowing is False
    assert line.graphicsEffect().isEnabled() is False

    # Focus keeps glow active even after mouse leaves, and clearing focus fades back to idle
    line.setFocus()
    QTest.qWait(220)
    assert anim.is_focused is True
    assert anim.is_glowing is True
    btn_focus.setFocus()
    QTest.qWait(280)
    assert anim.is_focused is False
    assert anim.is_glowing is False

    host.close()
    host.deleteLater()


def test_aurora_accent_bar_and_pulse_widget_glow(qapp):
    parent = QWidget()
    parent.resize(420, 60)
    btn = QPushButton("Glowing Btn", parent)
    lbl = QLabel("● Saved", parent)
    apply_glow_to_buttons([parent])

    bar = AuroraAccentBar(height=2).attach_to(parent, edge="bottom")
    parent.show()
    QTest.qWait(80)

    assert bar.geometry().y() == parent.height() - 2
    assert bar.geometry().width() == parent.width()
    bar.repaint()
    assert bar.phase >= 0.0

    # Pulse label glow works safely
    pulse_widget_glow(lbl, "#22c55e", duration_ms=140)
    assert lbl.graphicsEffect() is not None
    assert lbl.graphicsEffect().isEnabled() is True
    QTest.qWait(200)
    assert lbl.graphicsEffect().isEnabled() is False

    # Pulse on a glow-animated button safely no-ops without overwriting button's GlowAnimator effect
    original_effect = btn.graphicsEffect()
    pulse_widget_glow(btn, "#38bdf8", duration_ms=140)
    assert btn.graphicsEffect() is original_effect

    parent.close()
    parent.deleteLater()


def test_transitions_sync_fallback_and_animated_cleanup(qapp):
    pane = QWidget()
    pane.resize(240, 120)
    pane.show()

    # 1. With transitions disabled (default test fixture)
    assert panel_transition.TRANSITIONS_ENABLED is False
    fade = WidgetFadeTransition(pane, duration_ms=80)
    fade.fade_in()
    assert fade.is_running is False
    assert pane.graphicsEffect() is None

    bar = QWidget(pane)
    bar.resize(120, 28)
    bar.show()
    animate_bar_show(bar, QPoint(20, 24), duration_ms=80)
    assert bar.pos() == QPoint(20, 24)
    assert bar.graphicsEffect() is None

    dlg = QDialog()
    animate_dialog_show(dlg, duration_ms=80)
    assert dlg.windowOpacity() == pytest.approx(1.0)

    # 2. With transitions enabled -> fades and clears QGraphicsOpacityEffect cleanly afterward
    prev = panel_transition.TRANSITIONS_ENABLED
    try:
        panel_transition.TRANSITIONS_ENABLED = True
        fade.fade_in(start_opacity=0.2)
        assert fade.is_running is True
        assert pane.graphicsEffect() is not None
        QTest.qWait(140)
        assert fade.is_running is False
        assert pane.graphicsEffect() is None

        slide = SlideFadeBarTransition(bar, duration_ms=80)
        slide.show_animated(QPoint(30, 40))
        QTest.qWait(140)
        assert bar.pos() == QPoint(30, 40)
        assert bar.graphicsEffect() is None

        dlg.show()
        animate_dialog_show(dlg, duration_ms=80)
        QTest.qWait(140)
        assert dlg.windowOpacity() == pytest.approx(1.0)
    finally:
        panel_transition.TRANSITIONS_ENABLED = prev

    dlg.close()
    dlg.deleteLater()
    pane.close()
    pane.deleteLater()


def test_expanded_log_badges_and_toolbar_insertion(main_window):
    expected = {"PASS", "FAIL", "WARN", "INFO", "RESOLVED", "BLOCKED", "WAITING", "P1", "VIP"}
    assert expected.issubset(set(LOG_BADGES.keys()))

    editor = main_window.tab_widget.get_current_editor()
    assert editor is not None
    main_window.toolbar.set_active_editor(editor)

    for key in ("RESOLVED", "BLOCKED", "WAITING", "P1", "VIP"):
        main_window.toolbar._insert_badge(key)

    plain = editor.toPlainText()
    assert "RESOLVED" in plain
    assert "BLOCKED" in plain
    assert "WAITING" in plain
    assert "P1" in plain
    assert "VIP" in plain


def test_tech_tools_service_extraction_and_generators():
    sample = """
    User alice.smith@alpine.example (UPN: bob_99@contoso.onmicrosoft.com, dup Alice.Smith@alpine.example)
    Object IDs: 40000000-0000-4000-8000-000000000001 and 40000000-0000-4000-8000-000000000001
    Hosts: 10.20.30.40, invalid 999.888.1.1, gateway 192.168.1.1
    Ticket INC-4092 related to SR10203 and CHG-8812
    Docs: https://learn.microsoft.com/en-us/entra/, http://portal.azure.com/
    """
    entities = TechToolsService.extract_entities(sample)
    assert entities["emails"] == ["alice.smith@alpine.example", "bob_99@contoso.onmicrosoft.com"]
    assert entities["guids"] == ["40000000-0000-4000-8000-000000000001"]
    assert entities["ips"] == ["10.20.30.40", "192.168.1.1"]
    assert entities["tickets"] == ["INC-4092", "SR10203", "CHG-8812"]
    assert entities["urls"] == [
        "https://learn.microsoft.com/en-us/entra/",
        "http://portal.azure.com/",
    ]

    uid = TechToolsService.generate_uuid()
    parsed = uuid.UUID(uid)
    assert parsed.version == 4

    pw = TechToolsService.generate_temp_password(18)
    assert len(pw) == 18
    assert any(c.islower() for c in pw)
    assert any(c.isupper() for c in pw)
    assert any(c.isdigit() for c in pw)
    assert any(c in "@#$%!&*?" for c in pw)

    ts = TechToolsService.format_iso_timestamp()
    assert re.match(r"^\d{4}-\d{2}-\d{2}T\d{2}:\d{2}:\d{2}Z$", ts["utc"])
    assert "UTC:" in ts["combined"] and "Local:" in ts["combined"]


def test_quick_tools_dialog_and_send_to_m365(qapp):
    inserted = []
    routed = []

    dlg = QuickToolsDialog(
        note_text="Target user jane.doe@contoso.com oid 11111111-2222-4333-8444-555555555555 on 10.0.0.5",
        on_insert_text=inserted.append,
        on_send_to_m365=lambda upn, guid: routed.append((upn, guid)),
    )
    dlg.show()

    assert dlg.entity_list.count() >= 3
    dlg.txt_filter.setText("jane.doe")
    assert dlg.entity_list.count() == 1

    dlg.btn_insert_entity.click()
    assert inserted == ["jane.doe@contoso.com"]

    dlg.btn_send_m365.click()
    assert routed == [("jane.doe@contoso.com", "11111111-2222-4333-8444-555555555555")]

    dlg.close()
    dlg.deleteLater()


def test_command_palette_filtering_and_execution(qapp):
    triggered = []
    entries = [
        PaletteEntry("Open Tab", "#101 — Contoso", "VPN issue", lambda: triggered.append("tab"), "vpn"),
        PaletteEntry("Badge", "Insert Badge ✅ RESOLVED", "Triage pill", lambda: triggered.append("badge")),
        PaletteEntry("Action", "Toggle Split View", "Alt+Z", lambda: triggered.append("split")),
    ]
    dlg = CommandPaletteDialog(entries)
    dlg.show()

    dlg.txt_search.setText("resolved")
    assert len(dlg._filtered) == 1
    assert dlg.selected_entry.label.endswith("RESOLVED")

    QTest.keyClick(dlg.txt_search, Qt.Key_Return)
    assert triggered == ["badge"]

    dlg.deleteLater()


def test_main_window_telemetry_and_m365_entity_routing(main_window):
    main_window.show()
    editor: TechPadEditor = main_window.tab_widget.get_current_editor()
    assert editor is not None

    editor.setPlainText("Hello world VPN diagnostic\n[ ] Check DNS")
    main_window._update_telemetry(editor)
    telemetry_text = main_window.lbl_telemetry.text()
    assert "8w" in telemetry_text
    assert "2L" in telemetry_text
    assert "0/1" in telemetry_text

    # Build Command Palette entries without raw SQL and ensure all core groups exist
    entries = main_window._build_command_palette_entries()
    categories = {e.category for e in entries}
    assert {"Open Tab", "Action", "Badge", "Template"}.issubset(categories)

    # Test routing extracted entity to M365 workspace
    main_window._send_extracted_entity_to_m365(
        upn="tech.target@alpine.example",
        object_id="aaaaaaaa-bbbb-4ccc-8ddd-eeeeeeeeeeee",
    )
    assert main_window.is_m365_workspace is True
    assert main_window.m365_workspace.company_panel.target_upn.text() == "tech.target@alpine.example"
    assert (
        main_window.m365_workspace.company_panel.target_object_id.text()
        == "aaaaaaaa-bbbb-4ccc-8ddd-eeeeeeeeeeee"
    )


def test_tnotes_toolbars_visible_in_normal_and_hud_and_after_m365_transitions(main_window, qapp):
    """Verifies both top T-Notes toolbars stay visible in Normal & HUD mode across all M365 transitions."""
    main_window.show()
    qapp.processEvents()

    # Initial Normal mode in T-Notes
    assert main_window.is_m365_workspace is False
    assert main_window.toolbar.isVisible() is True
    assert main_window.toolbar.secondary_toolbar.isVisible() is True
    assert main_window.contextMenuPolicy() == Qt.NoContextMenu
    assert main_window.toolbar.toggleViewAction().isEnabled() is False
    assert main_window.toolbar.secondary_toolbar.toggleViewAction().isEnabled() is False

    # Enter Mini-HUD in T-Notes -> both toolbars must remain visible
    main_window.toggle_mini_hud_mode()
    qapp.processEvents()
    assert main_window.is_mini_hud is True
    assert main_window.toolbar.isVisible() is True
    assert main_window.toolbar.secondary_toolbar.isVisible() is True

    # Path A: HUD in T-Notes -> switch to M365 (hidden) -> exit HUD in M365 -> back to T-Notes Normal
    assert main_window.show_m365_workspace() is True
    qapp.processEvents()
    assert main_window.toolbar.isHidden() is True
    assert main_window.toolbar.secondary_toolbar.isHidden() is True
    main_window.toggle_mini_hud_mode()  # Exit HUD while still in M365
    qapp.processEvents()
    main_window.show_notes_workspace()  # Return to T-Notes Normal mode
    qapp.processEvents()
    assert main_window.is_mini_hud is False
    assert main_window.toolbar.isVisible() is True
    assert main_window.toolbar.secondary_toolbar.isVisible() is True

    # Path B: Normal -> M365 -> enter HUD in M365 -> switch to T-Notes in HUD -> exit HUD
    assert main_window.show_m365_workspace() is True
    qapp.processEvents()
    main_window.toggle_mini_hud_mode()  # Enter HUD while in M365
    qapp.processEvents()
    assert main_window.toolbar.isHidden() is True
    main_window.show_notes_workspace()  # Return to T-Notes while still in HUD mode
    qapp.processEvents()
    assert main_window.is_mini_hud is True
    assert main_window.toolbar.isVisible() is True
    assert main_window.toolbar.secondary_toolbar.isVisible() is True

    main_window.toggle_mini_hud_mode()  # Exit HUD back to T-Notes Normal mode
    qapp.processEvents()
    assert main_window.is_mini_hud is False
    assert main_window.toolbar.isVisible() is True
    assert main_window.toolbar.secondary_toolbar.isVisible() is True
