"""Shared pytest fixtures."""

import pytest
from PySide6.QtWidgets import QApplication


@pytest.fixture(scope="session")
def qapp():
    """Provides a single shared QApplication instance for all UI tests."""
    app = QApplication.instance()
    if app is None:
        app = QApplication([])
    return app



@pytest.fixture(autouse=True)
def _disable_panel_transitions(monkeypatch):
    """Keep side-pane show/hide synchronous in tests (transition tests opt back in)."""
    from src.ui.components import panel_transition

    monkeypatch.setattr(panel_transition, "TRANSITIONS_ENABLED", False)
