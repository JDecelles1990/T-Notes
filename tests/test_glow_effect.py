"""Tests for colorful hover/click glow animations on T-Notes buttons."""

from PySide6.QtCore import QEvent, QPoint, Qt
from PySide6.QtGui import QMouseEvent
from PySide6.QtTest import QTest
from PySide6.QtWidgets import QPushButton, QToolButton

from src.ui.components.glow_effect import (
    GLOW_PALETTE,
    HOVER_LEVEL,
    PRESS_LEVEL,
    GlowAnimator,
    apply_glow_to_buttons,
    install_glow,
)


def _mouse(etype, button=Qt.LeftButton):
    pos = QPoint(5, 5)
    return QMouseEvent(etype, pos, pos, button, button, Qt.NoModifier)


def test_idle_button_has_no_active_glow(qapp):
    btn = QPushButton("Idle")
    anim = install_glow(btn, GLOW_PALETTE[0])
    assert isinstance(anim, GlowAnimator)
    assert anim.level == 0.0
    assert anim.is_glowing is False


def test_install_is_idempotent(qapp):
    btn = QPushButton("Once")
    assert install_glow(btn) is install_glow(btn)


def test_hover_fades_in_and_out(qapp):
    btn = QPushButton("Hover")
    anim = install_glow(btn, GLOW_PALETTE[2])

    anim.eventFilter(btn, QEvent(QEvent.Enter))
    QTest.qWait(300)
    assert abs(anim.level - HOVER_LEVEL) < 0.01
    assert anim.is_glowing is True
    assert anim.effect.blurRadius() > 10

    anim.eventFilter(btn, QEvent(QEvent.Leave))
    QTest.qWait(300)
    assert anim.level == 0.0
    assert anim.is_glowing is False


def test_click_flares_brighter_than_hover_then_settles(qapp):
    btn = QPushButton("Click")
    btn.show()
    anim = install_glow(btn, GLOW_PALETTE[4])

    anim.eventFilter(btn, QEvent(QEvent.Enter))
    QTest.qWait(300)
    hover_blur = anim.effect.blurRadius()

    anim.eventFilter(btn, _mouse(QEvent.MouseButtonPress))
    QTest.qWait(200)
    assert abs(anim.level - PRESS_LEVEL) < 0.01
    assert anim.effect.blurRadius() > hover_blur

    anim.eventFilter(btn, QEvent(QEvent.Leave))
    anim.eventFilter(btn, _mouse(QEvent.MouseButtonRelease))
    QTest.qWait(300)
    assert anim.level == 0.0
    assert anim.is_glowing is False
    btn.close()


def test_disabled_button_never_glows(qapp):
    btn = QPushButton("Off")
    btn.setEnabled(False)
    anim = install_glow(btn)
    anim.eventFilter(btn, QEvent(QEvent.Enter))
    anim.eventFilter(btn, _mouse(QEvent.MouseButtonPress))
    QTest.qWait(150)
    assert anim.level == 0.0
    assert anim.is_glowing is False


def test_hide_resets_glow(qapp):
    btn = QPushButton("Hide")
    anim = install_glow(btn)
    anim.eventFilter(btn, QEvent(QEvent.Enter))
    QTest.qWait(250)
    assert anim.is_glowing is True
    anim.eventFilter(btn, QEvent(QEvent.Hide))
    assert anim.level == 0.0
    assert anim.is_glowing is False


def test_apply_glow_to_buttons_decorates_push_and_tool_buttons(qapp):
    from PySide6.QtWidgets import QWidget, QVBoxLayout, QCheckBox

    root = QWidget()
    lay = QVBoxLayout(root)
    b1, b2, chk = QPushButton("a"), QToolButton(), QCheckBox("c")
    for w in (b1, b2, chk):
        lay.addWidget(w)

    assert apply_glow_to_buttons([root, None]) == 2
    assert apply_glow_to_buttons([root]) == 0  # already decorated
    assert getattr(chk, "_glow_animator", None) is None
    assert b1._glow_animator._base.name() != b2._glow_animator._base.name()


def _tab_widget(qapp):
    from PySide6.QtWidgets import QWidget
    from src.ui.components.tab_widget import TechPadTabWidget

    tw = TechPadTabWidget()
    for name in ("one", "two", "three"):
        tw.addTab(QWidget(), name)
    tw.resize(500, 200)
    tw.show()
    qapp.processEvents()
    return tw


def test_tab_hover_glow_fades_in_and_out(qapp):
    tw = _tab_widget(qapp)
    bar = tw.tabBar()
    assert bar.glow_level(1) == 0.0

    bar._set_glow_hover(1)
    QTest.qWait(400)
    assert abs(bar.glow_level(1) - 1.0) < 0.05
    assert bar.glow_level(0) == 0.0
    assert not bar.grab().isNull()  # glow paints without error

    bar._set_glow_hover(-1)
    QTest.qWait(600)
    assert bar.glow_level(1) == 0.0
    assert not bar._glow_timer.isActive()
    tw.close()


def test_tab_click_glow_flares_then_settles(qapp):
    tw = _tab_widget(qapp)
    bar = tw.tabBar()
    bar._set_glow_hover(2)
    QTest.qWait(300)
    hover_level = bar.glow_level(2)

    bar._set_glow_press(2)
    QTest.qWait(500)
    assert bar.glow_level(2) > hover_level + 0.4
    assert not bar.grab().isNull()

    bar._set_glow_press(-1)
    QTest.qWait(500)
    assert abs(bar.glow_level(2) - 1.0) < 0.05

    bar.leaveEvent(QEvent(QEvent.Leave))
    QTest.qWait(700)
    assert bar.glow_level(2) == 0.0
    tw.close()


def test_tab_glow_resets_when_tabs_change(qapp):
    from PySide6.QtWidgets import QWidget

    tw = _tab_widget(qapp)
    bar = tw.tabBar()
    bar._set_glow_hover(0)
    QTest.qWait(200)
    assert bar.glow_level(0) > 0
    tw.addTab(QWidget(), "four")
    assert bar.glow_level(0) == 0.0
    tw.close()
