"""Unit tests for Windows autostart service, settings integration, and smart restore."""

import sys
from unittest.mock import MagicMock, patch
import pytest

from src.services.autostart_service import AutostartService
from src.ui.dialogs.settings_dialog import SettingsDialog


def test_autostart_service_command():
    service = AutostartService()
    cmd = service.get_launch_command()
    assert "--tray" in cmd
    assert "main.py" in cmd


def test_autostart_service_registry_mock():
    service = AutostartService()

    with patch("src.services.autostart_service._WINREG_AVAILABLE", True), \
         patch("sys.platform", "win32"), \
         patch("src.services.autostart_service.winreg") as mock_winreg:

        mock_key = MagicMock()
        mock_winreg.OpenKey.return_value.__enter__.return_value = mock_key

        # Test enable
        assert service.set_enabled(True) is True
        mock_winreg.SetValueEx.assert_called_once()

        # Test disable
        assert service.set_enabled(False) is True
        mock_winreg.DeleteValue.assert_called_once()

        # Test is_enabled True
        mock_winreg.QueryValueEx.return_value = ("some_cmd", 1)
        assert service.is_enabled() is True

        # Test is_enabled False
        mock_winreg.QueryValueEx.side_effect = FileNotFoundError()
        assert service.is_enabled() is False


def test_settings_dialog_autostart_and_smart_restore(qapp):
    mock_autostart = MagicMock()
    mock_autostart.is_enabled.return_value = True

    settings = {
        "ticket_prefix": "INC-",
        "auto_save_delay_ms": "1500",
        "jpeg_quality": "85",
        "window_opacity": "100",
        "autostart_enabled": "true",
        "smart_restore_enabled": "true",
    }

    dlg = SettingsDialog(
        current_settings=settings,
        autostart_service=mock_autostart,
    )

    assert dlg.chk_autostart.isChecked() is True
    assert dlg.chk_smart_restore.isChecked() is True

    # Change settings
    dlg.chk_autostart.setChecked(False)
    dlg.chk_smart_restore.setChecked(False)

    dlg._on_save_clicked()
    mock_autostart.set_enabled.assert_called_with(False)

    saved = dlg.get_settings()
    assert saved["autostart_enabled"] == "false"
    assert saved["smart_restore_enabled"] == "false"

