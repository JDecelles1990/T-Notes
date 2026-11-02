"""Unit tests for StopwatchService formatting and idle detection."""

import pytest
from src.services.stopwatch_service import FormattedTime, StopwatchService


def test_stopwatch_format_zero_seconds():
    result = StopwatchService.format_time(0)
    assert result.display == "00:00:00"
    assert result.decimal_hours == "0.00h"
    assert result.rounded_15m == "0.00h"


def test_stopwatch_format_sub_minute_billing_minimum():
    # MSP standard: Any work under 15m rounds up to the minimum 15m (0.25h) block
    result = StopwatchService.format_time(45)
    assert result.display == "00:00:45"
    assert result.decimal_hours == "0.01h"
    assert result.rounded_15m == "0.25h"


def test_stopwatch_format_14_minutes():
    # 14 minutes 32 seconds = 872 seconds
    result = StopwatchService.format_time(872)
    assert result.display == "00:14:32"
    assert result.decimal_hours == "0.24h"
    assert result.rounded_15m == "0.25h"


def test_stopwatch_format_15_minutes_exact():
    # Exactly 15 minutes = 900 seconds
    result = StopwatchService.format_time(900)
    assert result.display == "00:15:00"
    assert result.decimal_hours == "0.25h"
    assert result.rounded_15m == "0.25h"


def test_stopwatch_format_15_minutes_plus_one_second():
    # 15 minutes 1 second = 901 seconds -> rounds up to next 15m block (0.50h)
    result = StopwatchService.format_time(901)
    assert result.display == "00:15:01"
    assert result.decimal_hours == "0.25h"
    assert result.rounded_15m == "0.50h"


def test_stopwatch_format_multi_hour():
    # 2 hours, 18 minutes, 40 seconds = 8320 seconds
    result = StopwatchService.format_time(8320)
    assert result.display == "02:18:40"
    assert result.decimal_hours == "2.31h"
    assert result.rounded_15m == "2.50h"


def test_stopwatch_format_tab_tag():
    assert StopwatchService.format_tab_tag(0) == ""
    assert StopwatchService.format_tab_tag(45) == " (0m)"
    assert StopwatchService.format_tab_tag(60) == " (1m)"
    assert StopwatchService.format_tab_tag(840) == " (14m)"


def test_stopwatch_system_detection_safe_execution():
    # Ensure system API calls execute safely without throwing exceptions
    locked = StopwatchService.is_workstation_locked()
    assert isinstance(locked, bool)

    idle = StopwatchService.get_system_idle_seconds()
    assert isinstance(idle, float)
    assert idle >= 0.0


def test_stopwatch_should_auto_pause_threshold(monkeypatch):
    # Mock idle time to 301 seconds (exceeding 300s threshold)
    monkeypatch.setattr(StopwatchService, "is_workstation_locked", lambda: False)
    monkeypatch.setattr(StopwatchService, "get_system_idle_seconds", lambda: 301.0)
    assert StopwatchService.should_auto_pause(idle_threshold_seconds=300) is True

    # Mock idle time to 120 seconds (under threshold)
    monkeypatch.setattr(StopwatchService, "get_system_idle_seconds", lambda: 120.0)
    assert StopwatchService.should_auto_pause(idle_threshold_seconds=300) is False

    # Mock workstation locked
    monkeypatch.setattr(StopwatchService, "is_workstation_locked", lambda: True)
    assert StopwatchService.should_auto_pause(idle_threshold_seconds=300) is True

