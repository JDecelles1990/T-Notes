"""Luminous Quick Command Palette modal (Ctrl+K) for T-Notes."""

from __future__ import annotations

from dataclasses import dataclass
from typing import Callable, List, Optional

from PySide6.QtCore import QEvent, QObject, Qt
from PySide6.QtGui import QKeySequence, QShortcut
from PySide6.QtWidgets import (
    QDialog,
    QHBoxLayout,
    QLabel,
    QLineEdit,
    QListWidget,
    QListWidgetItem,
    QPushButton,
    QVBoxLayout,
    QWidget,
)

from src.ui.components.glow_effect import apply_glow_to_buttons, apply_glow_to_inputs
from src.ui.components.panel_transition import animate_dialog_show


@dataclass
class PaletteEntry:
    """Represents one searchable command, note, template, badge, or M365 action."""

    category: str
    label: str
    detail: str
    callback: Callable[[], None]
    keywords: str = ""


class CommandPaletteDialog(QDialog):
    """Fast keyboard-first palette searching tabs, archive, templates, badges, and M365 ops."""

    def __init__(
        self,
        entries: List[PaletteEntry],
        parent: Optional[QWidget] = None,
    ) -> None:
        super().__init__(parent)
        self.setWindowTitle("🔍 Quick Command Palette")
        self.setMinimumSize(620, 440)
        self.setModal(True)

        self._entries = list(entries)
        self._filtered: List[PaletteEntry] = []
        self._shown_once = False

        self._setup_ui()
        self._apply_filter("")

    def _setup_ui(self) -> None:
        self.setObjectName("commandPaletteDialog")
        self.setStyleSheet("""
            #commandPaletteDialog {
                background-color: #0b101d;
                border: 1px solid #38bdf8;
                border-radius: 10px;
            }
        """)

        layout = QVBoxLayout(self)
        layout.setContentsMargins(16, 14, 16, 14)
        layout.setSpacing(10)

        top_row = QHBoxLayout()
        title_lbl = QLabel("🔍 Command Palette")
        title_lbl.setStyleSheet("font-size: 12pt; font-weight: bold; color: #7dd3fc;")
        top_row.addWidget(title_lbl)
        top_row.addStretch()
        self.lbl_count = QLabel("")
        self.lbl_count.setStyleSheet("color: #94a3b8; font-size: 9pt;")
        top_row.addWidget(self.lbl_count)
        layout.addLayout(top_row)

        self.txt_search = QLineEdit()
        self.txt_search.setPlaceholderText(
            "Type to jump to open tabs, archived tickets, templates, badges, layout tools, or M365..."
        )
        self.txt_search.setMinimumHeight(34)
        self.txt_search.textChanged.connect(self._apply_filter)
        self.txt_search.installEventFilter(self)
        layout.addWidget(self.txt_search)

        self.result_list = QListWidget()
        self.result_list.itemDoubleClicked.connect(lambda _: self._execute_selected())
        self.result_list.itemActivated.connect(lambda _: self._execute_selected())
        layout.addWidget(self.result_list, 1)

        bottom = QHBoxLayout()
        hint = QLabel("↑↓ Navigate   •   Enter Run   •   Esc Close")
        hint.setStyleSheet("color: #64748b; font-size: 9pt;")
        bottom.addWidget(hint)
        bottom.addStretch()

        self.btn_run = QPushButton("Run Action")
        self.btn_run.setObjectName("btnPrimary")
        self.btn_run.clicked.connect(self._execute_selected)
        bottom.addWidget(self.btn_run)

        self.btn_close = QPushButton("Close")
        self.btn_close.setObjectName("btnCancel")
        self.btn_close.clicked.connect(self.reject)
        bottom.addWidget(self.btn_close)
        layout.addLayout(bottom)

        QShortcut(QKeySequence("Escape"), self, self.reject)
        apply_glow_to_buttons([self])
        apply_glow_to_inputs([self])
        self.txt_search.setFocus()

    def showEvent(self, event) -> None:
        super().showEvent(event)
        if not self._shown_once:
            self._shown_once = True
            animate_dialog_show(self)
        self.txt_search.setFocus()

    def eventFilter(self, watched: QObject, event: QEvent) -> bool:
        if watched is self.txt_search and event.type() == QEvent.KeyPress:
            key = event.key()  # type: ignore[attr-defined]
            if key == Qt.Key_Down:
                row = self.result_list.currentRow()
                if row + 1 < self.result_list.count() and self._filtered:
                    self.result_list.setCurrentRow(row + 1)
                return True
            if key == Qt.Key_Up:
                row = self.result_list.currentRow()
                if row > 0 and self._filtered:
                    self.result_list.setCurrentRow(row - 1)
                return True
            if key in (Qt.Key_Return, Qt.Key_Enter):
                self._execute_selected()
                return True
        return super().eventFilter(watched, event)

    def _apply_filter(self, query: str) -> None:
        tokens = [t.lower() for t in query.strip().split() if t]
        self.result_list.clear()
        self._filtered = []

        for entry in self._entries:
            haystack = (
                f"{entry.category} {entry.label} {entry.detail} {entry.keywords}"
            ).lower()
            if all(tok in haystack for tok in tokens):
                self._filtered.append(entry)
                display = f"[{entry.category}]  {entry.label}"
                if entry.detail:
                    display += f"  —  {entry.detail}"
                item = QListWidgetItem(display)
                item.setToolTip(entry.detail or entry.label)
                item.setData(Qt.UserRole, len(self._filtered) - 1)
                self.result_list.addItem(item)

        self.lbl_count.setText(f"{len(self._filtered)} match{'es' if len(self._filtered) != 1 else ''}")
        if self._filtered:
            self.result_list.setCurrentRow(0)
            self.btn_run.setEnabled(True)
        else:
            empty = QListWidgetItem("No matching commands, notes, or M365 actions.")
            empty.setFlags(Qt.NoItemFlags)
            self.result_list.addItem(empty)
            self.btn_run.setEnabled(False)

    @property
    def selected_entry(self) -> Optional[PaletteEntry]:
        row = self.result_list.currentRow()
        if 0 <= row < len(self._filtered):
            return self._filtered[row]
        return None

    def _execute_selected(self) -> None:
        entry = self.selected_entry
        if entry is None:
            return
        self.accept()
        entry.callback()
