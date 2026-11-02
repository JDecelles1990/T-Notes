"""Stopwatch toolbar widget for real-time ticket time tracking and MSP billing exports."""

from typing import Optional
from PySide6.QtCore import Qt, QTimer, Signal
from PySide6.QtWidgets import (
    QApplication,
    QHBoxLayout,
    QLabel,
    QMenu,
    QPushButton,
    QToolTip,
    QWidget,
)
from src.services.stopwatch_service import StopwatchService


class TicketStopwatchWidget(QWidget):
    """Compact stopwatch widget embedded in the toolbar for tracking billable ticket time."""

    time_updated = Signal(int, int)              # (scratchpad_id, elapsed_seconds)
    psa_export_requested = Signal()              # Emitted when user clicks 'Copy Note for Ticket Tool'
    status_message_requested = Signal(str, int)  # Emitted to display info on the main status bar

    def __init__(self, idle_threshold_seconds: int = 300, parent: Optional[QWidget] = None):
        super().__init__(parent)
        self._current_id: Optional[int] = None
        self._seconds: int = 0
        self._is_running: bool = False
        self._auto_paused: bool = False
        self._idle_threshold_seconds: int = idle_threshold_seconds

        # 1-second pulse timer
        self._timer = QTimer(self)
        self._timer.setInterval(1000)
        self._timer.timeout.connect(self._on_tick)

        self._build_ui()

    def _build_ui(self) -> None:
        layout = QHBoxLayout(self)
        layout.setContentsMargins(4, 1, 4, 1)
        layout.setSpacing(4)

        # Timer Display
        self.lbl_time = QLabel("⏱️ 00:00:00")
        self.lbl_time.setStyleSheet(
            "font-family: Consolas, 'Courier New', monospace; font-size: 13px; "
            "font-weight: bold; color: #58a6ff; padding: 2px 4px; "
            "background-color: #21262d; border: 1px solid #30363d; border-radius: 4px;"
        )
        self.lbl_time.setToolTip("Active ticket troubleshooting stopwatch")

        # Play / Pause Toggle Button
        self.btn_toggle = QPushButton("▶️")
        self.btn_toggle.setFixedSize(30, 24)
        self.btn_toggle.setToolTip("Start / Pause Stopwatch")
        self.btn_toggle.setStyleSheet("""
            QPushButton {
                background-color: #21262d;
                border: 1px solid #30363d;
                border-radius: 4px;
                font-size: 11px;
            }
            QPushButton:hover {
                background-color: #30363d;
                border-color: #58a6ff;
            }
        """)
        self.btn_toggle.clicked.connect(self.toggle_timer)

        # Reset Button
        self.btn_reset = QPushButton("🔄")
        self.btn_reset.setFixedSize(30, 24)
        self.btn_reset.setToolTip("Reset Timer to 00:00:00")
        self.btn_reset.setStyleSheet("""
            QPushButton {
                background-color: #21262d;
                border: 1px solid #30363d;
                border-radius: 4px;
                font-size: 11px;
            }
            QPushButton:hover {
                background-color: #30363d;
                border-color: #f85149;
            }
        """)
        self.btn_reset.clicked.connect(self.reset_timer)

        # PSA Copy Menu Button
        self.btn_copy = QPushButton("📋 Time")
        self.btn_copy.setFixedHeight(24)
        self.btn_copy.setToolTip("Copy billable time format to clipboard")
        self.btn_copy.setStyleSheet("""
            QPushButton {
                background-color: #21262d;
                border: 1px solid #30363d;
                border-radius: 4px;
                padding: 2px 8px;
                color: #e6edf3;
                font-weight: 500;
            }
            QPushButton:hover {
                background-color: #30363d;
                border-color: #58a6ff;
            }
        """)
        self._menu_copy = QMenu(self)
        self._menu_copy.addAction("📋 Copy Exact (HH:MM:SS)", lambda: self._copy_to_clipboard("display"))
        self._menu_copy.addAction("⏱️ Copy Decimal (e.g. 0.25h)", lambda: self._copy_to_clipboard("decimal"))
        self._menu_copy.addAction("⏲️ Copy 15m Rounded Block", lambda: self._copy_to_clipboard("rounded"))
        self._menu_copy.addSeparator()
        self._menu_copy.addAction("📤 Copy Note for Ticket Tool", self.psa_export_requested.emit)
        self.btn_copy.setMenu(self._menu_copy)

        layout.addWidget(self.lbl_time)
        layout.addWidget(self.btn_toggle)
        layout.addWidget(self.btn_reset)
        layout.addWidget(self.btn_copy)

    @property
    def current_scratchpad_id(self) -> Optional[int]:
        return self._current_id

    @property
    def elapsed_seconds(self) -> int:
        return self._seconds

    @property
    def is_running(self) -> bool:
        return self._is_running

    def load_scratchpad(self, scratchpad_id: int, elapsed_seconds: int = 0, auto_start: bool = True) -> None:
        """Loads a tab's timer state. Automatically resumes if auto_start is True."""
        self.save_current_state()
        self._current_id = scratchpad_id
        self._seconds = max(0, elapsed_seconds)
        self._auto_paused = False
        self._update_display()

        if auto_start:
            self.start_timer()
        else:
            self.pause_timer()

    def _on_tick(self) -> None:
        # Check for workstation lock or 5m+ idle inactivity
        if StopwatchService.should_auto_pause(self._idle_threshold_seconds):
            self.pause_timer()
            self._auto_paused = True
            self.lbl_time.setToolTip("⏱️ Auto-paused due to 5m inactivity or lock. Click ▶️ to resume.")
            self.status_message_requested.emit(
                "⏱️ Stopwatch auto-paused due to 5 minutes of inactivity or system lock.", 4000
            )
            return

        self._seconds += 1
        self._update_display()
        if self._current_id is not None:
            self.time_updated.emit(self._current_id, self._seconds)

    def _update_display(self) -> None:
        formatted = StopwatchService.format_time(self._seconds)
        self.lbl_time.setText(f"⏱️ {formatted.display}")
        if not self._auto_paused:
            self.lbl_time.setToolTip(
                f"Elapsed: {formatted.display} | Decimal: {formatted.decimal_hours} | 15m Block: {formatted.rounded_15m}"
            )

    def toggle_timer(self) -> None:
        if self._is_running:
            self.pause_timer()
        else:
            self._auto_paused = False
            self.start_timer()

    def start_timer(self) -> None:
        if not self._is_running:
            self._is_running = True
            self._auto_paused = False
            self.btn_toggle.setText("⏸️")
            self.btn_toggle.setToolTip("Pause Stopwatch")
            self._timer.start()

    def pause_timer(self) -> None:
        if self._is_running:
            self._is_running = False
            self.btn_toggle.setText("▶️")
            self.btn_toggle.setToolTip("Start Stopwatch")
            self._timer.stop()
            self.save_current_state()

    def reset_timer(self) -> None:
        self.pause_timer()
        self._seconds = 0
        self._update_display()
        self.save_current_state()

    def save_current_state(self) -> None:
        """Emits final elapsed seconds so services/repositories persist immediately."""
        if self._current_id is not None:
            self.time_updated.emit(self._current_id, self._seconds)

    def _copy_to_clipboard(self, mode: str) -> None:
        formatted = StopwatchService.format_time(self._seconds)
        text = {
            "display": formatted.display,
            "decimal": formatted.decimal_hours,
            "rounded": formatted.rounded_15m,
        }.get(mode, formatted.display)

        QApplication.clipboard().setText(text)
        global_pos = self.btn_copy.mapToGlobal(self.btn_copy.rect().center())
        QToolTip.showText(global_pos, f"Copied: {text}", self.btn_copy, self.btn_copy.rect(), 2500)
        self.status_message_requested.emit(f"✓ Copied time ({text}) to clipboard", 2500)
