"""Unit and integration tests for the global Neon Aurora hover tooltip overlay."""

from PySide6.QtCore import QEvent, QPoint, QPointF, QRect, Qt
from PySide6.QtGui import QAction, QColor, QGuiApplication, QHelpEvent, QKeyEvent, QMouseEvent, QPixmap
from PySide6.QtTest import QTest
from PySide6.QtWidgets import (
    QApplication,
    QListWidget,
    QListWidgetItem,
    QPushButton,
    QTabBar,
    QTextEdit,
    QToolButton,
    QWidget,
)

from src.ui.components import panel_transition
from src.ui.components.aurora_tooltip import (
    AURORA_BORDER_PALETTE,
    AURORA_TEXT_PALETTE,
    GLOW_MARGIN,
    MAX_CONTENT_WIDTH,
    PAD_X,
    AuroraToolTipManager,
    AuroraToolTipWidget,
    get_aurora_tooltip_manager,
    hide_aurora_tooltip,
    install_aurora_tooltips,
    normalize_tooltip_text,
    show_aurora_tooltip,
)


def _send_tooltip_event(widget: QWidget, local_pos: QPoint | None = None) -> QHelpEvent:
    pos = local_pos if local_pos is not None else widget.rect().center()
    global_pos = widget.mapToGlobal(pos)
    ev = QHelpEvent(QEvent.ToolTip, pos, global_pos)
    QApplication.sendEvent(widget, ev)
    return ev


def test_install_aurora_tooltips_is_idempotent(qapp):
    """install_aurora_tooltips installs once and returns the existing manager on repeat calls."""
    mgr1 = install_aurora_tooltips(qapp)
    mgr2 = install_aurora_tooltips(qapp)
    assert isinstance(mgr1, AuroraToolTipManager)
    assert mgr1 is mgr2
    assert get_aurora_tooltip_manager(qapp) is mgr1


def test_button_tooltip_intercepted_without_modifying_button(qapp):
    """Hovering a QPushButton or QToolButton renders the Aurora tooltip while leaving buttons untouched."""
    mgr = install_aurora_tooltips(qapp)
    assert mgr is not None
    tip_widget = mgr.tooltip_widget

    host = QWidget()
    host.resize(360, 140)
    btn = QPushButton("Bold", host)
    btn.setGeometry(20, 20, 120, 36)
    btn.setStyleSheet("QPushButton { color: #e2e8f0; }")
    btn.setToolTip("Bold (Ctrl+B)")

    tbtn = QToolButton(host)
    tbtn.setGeometry(160, 20, 120, 36)
    act = QAction("Insert Checkbox", host)
    act.setToolTip("Insert Interactive Task Checkbox (Ctrl+Shift+C)")
    tbtn.setDefaultAction(act)

    # Snapshot button state before hover
    btn_ss_before = btn.styleSheet()
    btn_fx_before = btn.graphicsEffect()
    btn_font_before = btn.font().toString()
    tbtn_ss_before = tbtn.styleSheet()
    tbtn_fx_before = tbtn.graphicsEffect()

    host.show()
    qapp.processEvents()
    try:
        ev = _send_tooltip_event(btn)
        assert ev.isAccepted()
        assert tip_widget.isVisible()
        assert tip_widget.text == "Bold (Ctrl+B)"
        assert mgr.active_owner is btn

        # Verify custom rendering paints vivid non-transparent rainbow & neon pixels
        pix = tip_widget.grab()
        assert isinstance(pix, QPixmap)
        assert not pix.isNull()
        img = pix.toImage()
        colorful_pixels = 0
        for y in range(0, img.height(), 2):
            for x in range(0, img.width(), 2):
                c = img.pixelColor(x, y)
                if c.alpha() > 40 and c.saturation() > 110 and c.value() > 120:
                    colorful_pixels += 1
        assert colorful_pixels > 40

        # Verify QToolButton defaultAction tooltip resolves cleanly
        ev2 = _send_tooltip_event(tbtn)
        assert ev2.isAccepted()
        assert tip_widget.isVisible()
        assert tip_widget.text == "Insert Interactive Task Checkbox (Ctrl+Shift+C)"

        # Verify buttons were NOT modified in any way
        assert btn.styleSheet() == btn_ss_before
        assert btn.graphicsEffect() is btn_fx_before
        assert btn.font().toString() == btn_font_before
        assert tbtn.styleSheet() == tbtn_ss_before
        assert tbtn.graphicsEffect() is tbtn_fx_before
    finally:
        hide_aurora_tooltip(immediate=True)
        host.close()
        host.deleteLater()


def test_tab_bar_item_view_and_scroll_area_tooltip_resolution(qapp):
    """Resolves per-tab tooltips, QListWidget item ToolTipRole, and QTextEdit viewport tooltips."""
    mgr = install_aurora_tooltips(qapp)
    assert mgr is not None
    tip_widget = mgr.tooltip_widget

    host = QWidget()
    host.resize(520, 420)

    tab_bar = QTabBar(host)
    tab_bar.setGeometry(10, 10, 480, 34)
    i0 = tab_bar.addTab("INC-1001")
    i1 = tab_bar.addTab("INC-1002")
    tab_bar.setTabToolTip(i0, "INC-1001 — VPN Outage\nChecklist: 2/5 completed")
    tab_bar.setTabToolTip(i1, "INC-1002 — Exchange Mailbox Audit")

    list_widget = QListWidget(host)
    list_widget.setGeometry(10, 60, 480, 120)
    item = QListWidgetItem("Archive Ticket #42")
    item.setToolTip("Archived 2026-11-19 • Click to restore")
    list_widget.addItem(item)

    editor = QTextEdit(host)
    editor.setGeometry(10, 200, 480, 160)
    editor.setToolTip("Open link: https://portal.azure.com")

    host.show()
    qapp.processEvents()
    try:
        # 1. QTabBar tab 0 and tab 1
        r0 = tab_bar.tabRect(i0)
        r1 = tab_bar.tabRect(i1)
        _send_tooltip_event(tab_bar, r0.center())
        assert tip_widget.isVisible()
        assert "VPN Outage" in tip_widget.text

        _send_tooltip_event(tab_bar, r1.center())
        assert tip_widget.isVisible()
        assert "Exchange Mailbox Audit" in tip_widget.text

        # Moving mouse to another tab dismisses the stale tooltip cleanly
        move_ev = QMouseEvent(
            QEvent.MouseMove,
            QPointF(r0.center()),
            QPointF(tab_bar.mapToGlobal(r0.center())),
            Qt.NoButton,
            Qt.NoButton,
            Qt.NoModifier,
        )
        QApplication.sendEvent(tab_bar, move_ev)
        assert not tip_widget.isVisible()

        # 2. QListWidget item viewport ToolTipRole
        item_rect = list_widget.visualItemRect(item)
        _send_tooltip_event(list_widget.viewport(), item_rect.center())
        assert tip_widget.isVisible()
        assert tip_widget.text == "Archived 2026-11-19 • Click to restore"

        # 3. QTextEdit scroll-area viewport resolves parent toolTip()
        _send_tooltip_event(editor.viewport(), editor.viewport().rect().center())
        assert tip_widget.isVisible()
        assert tip_widget.text == "Open link: https://portal.azure.com"
    finally:
        hide_aurora_tooltip(immediate=True)
        host.close()
        host.deleteLater()


def test_rich_text_normalization_and_multiline_wrapping(qapp):
    """Normalizes basic HTML tags into lines and wraps long tooltips within max card width."""
    assert normalize_tooltip_text("<b>Hello</b><br/>Line 2 &amp; <i>more</i>") == "Hello\nLine 2 & more"
    assert normalize_tooltip_text("   \n  ") == ""

    widget = AuroraToolTipWidget()
    try:
        long_text = (
            "Hover tooltip description that is intentionally much longer than the maximum "
            "single-line width so the layout wraps cleanly across multiple glowing rainbow lines."
        )
        shown = widget.show_tooltip(QPoint(120, 120), long_text)
        assert shown is True
        assert widget.width() <= MAX_CONTENT_WIDTH + PAD_X * 2 + GLOW_MARGIN * 2 + 4
        assert widget.height() > 54
    finally:
        widget.hide_tooltip(immediate=True)
        widget.close()
        widget.deleteLater()


def test_animation_timer_runs_only_while_visible_and_advances_phase(qapp):
    """The shimmer timer advances rainbow phase while visible and stops immediately on hide."""
    widget = AuroraToolTipWidget()
    try:
        assert not widget.is_animating_effects
        widget.show_tooltip(QPoint(140, 140), "Flowing Rainbow Test")
        assert widget.isVisible()
        assert widget.is_animating_effects

        initial_phase = widget.phase
        widget._on_anim_tick()
        assert widget.phase != initial_phase
        assert not widget.grab().isNull()

        widget.hide_tooltip(immediate=True)
        assert not widget.isVisible()
        assert not widget.is_animating_effects
    finally:
        widget.close()
        widget.deleteLater()


def test_dismissal_on_leave_click_key_and_empty_tooltip(qapp):
    """Tooltips dismiss cleanly on Leave, MouseButtonPress, KeyPress, and empty tooltip events."""
    mgr = install_aurora_tooltips(qapp)
    assert mgr is not None
    tip_widget = mgr.tooltip_widget

    btn = QPushButton("Action")
    btn.resize(140, 36)
    btn.setToolTip("Dismissal verification")
    btn.show()
    qapp.processEvents()
    try:
        # 1. Leave dismisses
        _send_tooltip_event(btn)
        assert tip_widget.isVisible()
        QApplication.sendEvent(btn, QEvent(QEvent.Leave))
        assert not tip_widget.isVisible()

        # 2. MouseButtonPress dismisses
        _send_tooltip_event(btn)
        assert tip_widget.isVisible()
        press = QMouseEvent(
            QEvent.MouseButtonPress,
            QPointF(10, 10),
            QPointF(btn.mapToGlobal(QPoint(10, 10))),
            Qt.LeftButton,
            Qt.LeftButton,
            Qt.NoModifier,
        )
        QApplication.sendEvent(btn, press)
        assert not tip_widget.isVisible()

        # 3. KeyPress dismisses
        _send_tooltip_event(btn)
        assert tip_widget.isVisible()
        key = QKeyEvent(QEvent.KeyPress, Qt.Key_Escape, Qt.NoModifier)
        QApplication.sendEvent(btn, key)
        assert not tip_widget.isVisible()

        # 4. Empty tooltip on active owner dismisses
        _send_tooltip_event(btn)
        assert tip_widget.isVisible()
        btn.setToolTip("")
        _send_tooltip_event(btn)
        assert not tip_widget.isVisible()
    finally:
        hide_aurora_tooltip(immediate=True)
        btn.close()
        btn.deleteLater()


def test_smooth_appear_and_disappear_transitions_when_enabled(qapp):
    """When TRANSITIONS_ENABLED is True, tooltips animate appear/disappear opacity and stop timers after hide."""
    orig = panel_transition.TRANSITIONS_ENABLED
    panel_transition.TRANSITIONS_ENABLED = True
    widget = AuroraToolTipWidget()
    try:
        widget.show_tooltip(QPoint(200, 200), "Smooth Transition Tooltip")
        assert widget.isVisible()
        assert widget.is_transitioning
        assert widget.is_animating_effects
        assert not widget.is_hiding

        # Allow appear transition (175ms) to finish
        QTest.qWait(240)
        qapp.processEvents()
        assert widget.isVisible()
        assert not widget.is_transitioning
        assert widget.windowOpacity() >= 0.99

        # Trigger smooth disappear transition (135ms)
        widget.hide_tooltip()
        assert widget.isVisible()
        assert widget.is_hiding
        assert widget.is_transitioning

        # Mid-flight reversal: showing new text cancels hide cleanly
        widget.show_tooltip(QPoint(220, 210), "Reversed Back In")
        assert not widget.is_hiding
        QTest.qWait(240)
        qapp.processEvents()
        assert widget.isVisible()
        assert widget.windowOpacity() >= 0.99

        # Complete smooth disappear
        widget.hide_tooltip()
        QTest.qWait(210)
        qapp.processEvents()
        assert not widget.isVisible()
        assert not widget.is_animating_effects
    finally:
        panel_transition.TRANSITIONS_ENABLED = orig
        widget.hide_tooltip(immediate=True)
        widget.close()
        widget.deleteLater()


def test_screen_bounds_clamping_and_disabled_widget_rule(qapp):
    """Clamps tooltip strictly inside screen availableGeometry and respects disabled widget tooltip rules."""
    mgr = install_aurora_tooltips(qapp)
    assert mgr is not None
    tip_widget = mgr.tooltip_widget

    screen = QGuiApplication.primaryScreen()
    avail = screen.availableGeometry() if screen is not None else QRect(0, 0, 1920, 1080)

    # Bottom-right edge should flip/clamp inside screen
    edge_pos = QPoint(avail.right() - 2, avail.bottom() - 2)
    tip_widget.show_tooltip(edge_pos, "Bottom-right edge clamped tooltip")
    try:
        geo = tip_widget.frameGeometry()
        assert geo.left() >= avail.left()
        assert geo.top() >= avail.top()
        assert geo.right() <= avail.right()
        assert geo.bottom() <= avail.bottom()
    finally:
        hide_aurora_tooltip(immediate=True)

    # Disabled widget should suppress tooltip unless WA_AlwaysShowToolTips is set
    btn = QPushButton("Disabled")
    btn.resize(120, 34)
    btn.setToolTip("Disabled hint")
    btn.setEnabled(False)
    btn.show()
    qapp.processEvents()
    try:
        _send_tooltip_event(btn)
        assert not tip_widget.isVisible()

        btn.setAttribute(Qt.WA_AlwaysShowToolTips, True)
        _send_tooltip_event(btn)
        assert tip_widget.isVisible()
        assert tip_widget.text == "Disabled hint"
    finally:
        hide_aurora_tooltip(immediate=True)
        btn.close()
        btn.deleteLater()


def test_live_manual_sticky_tooltip_for_editor_resize(qapp):
    """Sticky programmatic tooltips (used for live image drag-resize) survive MouseMove until hidden."""
    mgr = install_aurora_tooltips(qapp)
    assert mgr is not None
    tip_widget = mgr.tooltip_widget

    owner = QWidget()
    owner.resize(200, 120)
    owner.show()
    qapp.processEvents()
    try:
        shown = show_aurora_tooltip(QPoint(180, 180), "420 × 240 px (Hold Shift to unconstrain)", owner=owner, sticky=True)
        assert shown is True
        assert tip_widget.isVisible()
        assert "420 × 240 px" in tip_widget.text

        move_ev = QMouseEvent(
            QEvent.MouseMove,
            QPointF(50, 50),
            QPointF(owner.mapToGlobal(QPoint(50, 50))),
            Qt.LeftButton,
            Qt.LeftButton,
            Qt.NoModifier,
        )
        QApplication.sendEvent(owner, move_ev)
        assert tip_widget.isVisible()

        hide_aurora_tooltip(immediate=True)
        assert not tip_widget.isVisible()
    finally:
        hide_aurora_tooltip(immediate=True)
        owner.close()
        owner.deleteLater()


def test_palettes_have_seamless_wrap():
    """Text and border palettes wrap seamlessly from stop 0.0 to 1.0."""
    assert AURORA_TEXT_PALETTE[0][0] == 0.0
    assert AURORA_TEXT_PALETTE[-1][0] == 1.0
    assert QColor(AURORA_TEXT_PALETTE[0][1]) == QColor(AURORA_TEXT_PALETTE[-1][1])

    assert AURORA_BORDER_PALETTE[0][0] == 0.0
    assert AURORA_BORDER_PALETTE[-1][0] == 1.0
    assert QColor(AURORA_BORDER_PALETTE[0][1]) == QColor(AURORA_BORDER_PALETTE[-1][1])
