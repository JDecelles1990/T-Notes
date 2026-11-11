"""Floating in-editor search and replace bar for TechPad note editors."""

from typing import List, Optional, Tuple
from PySide6.QtCore import QEvent, QPoint, QRect, Qt, Signal
from PySide6.QtGui import QColor, QFont, QKeySequence, QTextCharFormat, QTextCursor, QTextDocument
from PySide6.QtWidgets import (
    QFrame,
    QHBoxLayout,
    QLabel,
    QLineEdit,
    QPushButton,
    QTextEdit,
    QToolButton,
    QVBoxLayout,
    QWidget,
)
from src.ui.components.glow_effect import apply_glow_to_buttons


class FindReplaceBar(QFrame):
    """
    Floating VS Code-style top-right search & replace bar docked over TechPadEditor.
    Supports search-as-you-type, match highlighting, next/prev navigation,
    case matching, and single/all replacement.
    """

    def __init__(self, editor: QTextEdit, parent: Optional[QWidget] = None):
        super().__init__(parent or editor)
        self.editor = editor
        self._matches: List[Tuple[int, int]] = []
        self._current_match_index: int = -1
        self._case_sensitive: bool = False

        self.setObjectName("findReplaceBar")
        self.setFrameShape(QFrame.StyledPanel)
        self.setStyleSheet("""
            #findReplaceBar {
                background-color: #252526;
                border: 1px solid #3c3c3c;
                border-radius: 6px;
            }
            QLineEdit {
                background-color: #1e1e1e;
                color: #ffffff;
                border: 1px solid #3c3c3c;
                border-radius: 3px;
                padding: 4px 6px;
                font-size: 11px;
                selection-background-color: #264f78;
            }
            QLineEdit:focus {
                border: 1px solid #007acc;
            }
            QToolButton, QPushButton {
                background-color: #2d2d2d;
                border: 1px solid #3c3c3c;
                border-radius: 3px;
                color: #cccccc;
                font-size: 11px;
                padding: 3px 6px;
            }
            QToolButton:hover, QPushButton:hover {
                background-color: #383838;
                border-color: #007acc;
                color: #ffffff;
            }
            QToolButton:checked {
                background-color: #0e639c;
                border-color: #1177bb;
                color: #ffffff;
            }
            QLabel {
                color: #858585;
                font-size: 11px;
            }
        """)

        self._setup_ui()
        self.hide()

    def _setup_ui(self) -> None:
        self.main_layout = QVBoxLayout(self)
        self.main_layout.setContentsMargins(6, 6, 6, 6)
        self.main_layout.setSpacing(4)

        # Row 1: Find Row
        find_row = QHBoxLayout()
        find_row.setSpacing(4)

        self.btn_toggle_replace = QToolButton()
        self.btn_toggle_replace.setText("▶")
        self.btn_toggle_replace.setToolTip("Toggle Replace (Ctrl+H)")
        self.btn_toggle_replace.setFixedSize(20, 22)
        self.btn_toggle_replace.clicked.connect(self.toggle_replace_mode)
        find_row.addWidget(self.btn_toggle_replace)

        self.txt_find = QLineEdit()
        self.txt_find.setPlaceholderText("Find...")
        self.txt_find.setMinimumWidth(160)
        self.txt_find.textChanged.connect(self._on_find_text_changed)
        find_row.addWidget(self.txt_find)

        self.lbl_matches = QLabel("No results")
        self.lbl_matches.setMinimumWidth(65)
        self.lbl_matches.setAlignment(Qt.AlignCenter)
        find_row.addWidget(self.lbl_matches)

        self.btn_case = QToolButton()
        self.btn_case.setText("Aa")
        self.btn_case.setCheckable(True)
        self.btn_case.setToolTip("Match Case (Alt+C)")
        self.btn_case.setFixedSize(26, 22)
        self.btn_case.toggled.connect(self._on_case_toggled)
        find_row.addWidget(self.btn_case)

        self.btn_prev = QToolButton()
        self.btn_prev.setText("▲")
        self.btn_prev.setToolTip("Previous Match (Shift+Enter)")
        self.btn_prev.setFixedSize(22, 22)
        self.btn_prev.clicked.connect(self.find_prev)
        find_row.addWidget(self.btn_prev)

        self.btn_next = QToolButton()
        self.btn_next.setText("▼")
        self.btn_next.setToolTip("Next Match (Enter)")
        self.btn_next.setFixedSize(22, 22)
        self.btn_next.clicked.connect(self.find_next)
        find_row.addWidget(self.btn_next)

        self.btn_close = QToolButton()
        self.btn_close.setText("✕")
        self.btn_close.setToolTip("Close (Esc)")
        self.btn_close.setFixedSize(20, 22)
        self.btn_close.clicked.connect(self.hide_bar)
        find_row.addWidget(self.btn_close)

        self.main_layout.addLayout(find_row)

        # Row 2: Replace Row (hidden by default)
        self.replace_container = QWidget()
        replace_row = QHBoxLayout(self.replace_container)
        replace_row.setContentsMargins(0, 0, 0, 0)
        replace_row.setSpacing(4)

        spacer_dummy = QWidget()
        spacer_dummy.setFixedSize(20, 22)
        replace_row.addWidget(spacer_dummy)

        self.txt_replace = QLineEdit()
        self.txt_replace.setPlaceholderText("Replace...")
        self.txt_replace.setMinimumWidth(160)
        replace_row.addWidget(self.txt_replace)

        self.btn_replace = QToolButton()
        self.btn_replace.setText("Replace")
        self.btn_replace.setToolTip("Replace Selected Match")
        self.btn_replace.clicked.connect(self.replace_current)
        replace_row.addWidget(self.btn_replace)

        self.btn_replace_all = QToolButton()
        self.btn_replace_all.setText("Replace All")
        self.btn_replace_all.setToolTip("Replace All Matches")
        self.btn_replace_all.clicked.connect(self.replace_all)
        replace_row.addWidget(self.btn_replace_all)

        self.replace_container.setVisible(False)
        self.main_layout.addWidget(self.replace_container)

        apply_glow_to_buttons([self])

    def show_bar(self, replace_mode: bool = False, initial_query: str = "") -> None:
        """Opens the find/replace bar, prefilling query if provided."""
        if initial_query:
            self.txt_find.setText(initial_query)
            self.txt_find.selectAll()

        self.set_replace_mode(replace_mode)
        self.show()
        self.raise_()
        self.reposition()
        self.txt_find.setFocus()
        self._on_find_text_changed(self.txt_find.text())

    def hide_bar(self) -> None:
        """Hides the bar, clears extra selections, and restores focus to editor."""
        self.hide()
        self._clear_highlights()
        self.editor.setFocus()

    def set_replace_mode(self, enabled: bool) -> None:
        """Shows or hides the replace row."""
        self.replace_container.setVisible(enabled)
        self.btn_toggle_replace.setText("▼" if enabled else "▶")
        self.adjustSize()
        self.reposition()

    def toggle_replace_mode(self) -> None:
        """Toggles between Find and Replace modes."""
        new_state = not self.replace_container.isVisible()
        self.set_replace_mode(new_state)
        if new_state:
            self.txt_replace.setFocus()

    def reposition(self) -> None:
        """Positions the floating bar in the top-right corner of the editor viewport."""
        if not self.editor:
            return
        w = self.sizeHint().width()
        margin = 18
        x = max(10, self.editor.width() - w - margin)
        y = 8
        self.move(QPoint(x, y))

    def _on_case_toggled(self, checked: bool) -> None:
        self._case_sensitive = checked
        self._on_find_text_changed(self.txt_find.text())

    def _on_find_text_changed(self, text: str) -> None:
        """Re-scans document for matches and applies visual highlighting."""
        query = text
        if not query:
            self._matches = []
            self._current_match_index = -1
            self.lbl_matches.setText("No results")
            self.lbl_matches.setStyleSheet("color: #858585;")
            self._clear_highlights()
            return

        doc = self.editor.document()
        plain_text = doc.toPlainText()

        self._matches = []
        start_idx = 0
        q_len = len(query)

        if not self._case_sensitive:
            plain_lower = plain_text.lower()
            query_lower = query.lower()
            while True:
                pos = plain_lower.find(query_lower, start_idx)
                if pos == -1:
                    break
                self._matches.append((pos, pos + q_len))
                start_idx = pos + q_len
        else:
            while True:
                pos = plain_text.find(query, start_idx)
                if pos == -1:
                    break
                self._matches.append((pos, pos + q_len))
                start_idx = pos + q_len

        total = len(self._matches)
        if total == 0:
            self._current_match_index = -1
            self.lbl_matches.setText("0 of 0")
            self.lbl_matches.setStyleSheet("color: #f87171;")
            self._clear_highlights()
        else:
            # Pick closest match forward from current editor cursor position
            cursor_pos = self.editor.textCursor().position()
            found_idx = 0
            for i, (start, _) in enumerate(self._matches):
                if start >= cursor_pos:
                    found_idx = i
                    break
            self._current_match_index = found_idx
            self._update_selection_and_counter()

    def find_next(self) -> None:
        """Jumps to next match in document."""
        if not self._matches:
            return
        self._current_match_index = (self._current_match_index + 1) % len(self._matches)
        self._update_selection_and_counter()

    def find_prev(self) -> None:
        """Jumps to previous match in document."""
        if not self._matches:
            return
        self._current_match_index = (self._current_match_index - 1 + len(self._matches)) % len(self._matches)
        self._update_selection_and_counter()

    def _update_selection_and_counter(self) -> None:
        """Applies highlight formatting to matches and moves cursor to current match."""
        total = len(self._matches)
        if total == 0 or self._current_match_index < 0:
            self.lbl_matches.setText("0 of 0")
            self.lbl_matches.setStyleSheet("color: #f87171;")
            self._clear_highlights()
            return

        self.lbl_matches.setText(f"{self._current_match_index + 1} of {total}")
        self.lbl_matches.setStyleSheet("color: #4ade80;")

        # Prepare extra selections
        extra_selections = []

        other_fmt = QTextCharFormat()
        other_fmt.setBackground(QColor(100, 75, 0, 160))

        curr_fmt = QTextCharFormat()
        curr_fmt.setBackground(QColor(0, 122, 204, 220))
        curr_fmt.setForeground(QColor(255, 255, 255))

        for i, (start, end) in enumerate(self._matches):
            sel = QTextEdit.ExtraSelection()
            cursor = self.editor.textCursor()
            cursor.setPosition(start)
            cursor.setPosition(end, QTextCursor.KeepAnchor)
            sel.cursor = cursor
            sel.format = curr_fmt if i == self._current_match_index else other_fmt
            extra_selections.append(sel)

        self.editor.setExtraSelections(extra_selections)

        # Move editor cursor and scroll into view
        active_start, active_end = self._matches[self._current_match_index]
        active_cursor = self.editor.textCursor()
        active_cursor.setPosition(active_start)
        active_cursor.setPosition(active_end, QTextCursor.KeepAnchor)
        self.editor.setTextCursor(active_cursor)
        self.editor.ensureCursorVisible()

    def _clear_highlights(self) -> None:
        self.editor.setExtraSelections([])

    def replace_current(self) -> None:
        """Replaces the active match with replacement text and moves to next match."""
        if not self._matches or self._current_match_index < 0:
            return

        replacement = self.txt_replace.text()
        start, end = self._matches[self._current_match_index]

        cursor = self.editor.textCursor()
        cursor.setPosition(start)
        cursor.setPosition(end, QTextCursor.KeepAnchor)
        cursor.insertText(replacement)

        # Re-run search to update match indices
        self._on_find_text_changed(self.txt_find.text())

    def replace_all(self) -> None:
        """Replaces all matches across document atomically."""
        if not self._matches:
            return

        replacement = self.txt_replace.text()
        cursor = self.editor.textCursor()
        cursor.beginEditBlock()

        # Iterate in reverse order so positions don't shift
        for start, end in reversed(self._matches):
            cursor.setPosition(start)
            cursor.setPosition(end, QTextCursor.KeepAnchor)
            cursor.insertText(replacement)

        cursor.endEditBlock()
        self._on_find_text_changed(self.txt_find.text())

    def keyPressEvent(self, event) -> None:
        if event.key() == Qt.Key_Escape:
            self.hide_bar()
            event.accept()
            return
        elif event.key() in (Qt.Key_Return, Qt.Key_Enter):
            if self.txt_find.hasFocus():
                if event.modifiers() & Qt.ShiftModifier:
                    self.find_prev()
                else:
                    self.find_next()
                event.accept()
                return
            elif self.txt_replace.hasFocus():
                self.replace_current()
                event.accept()
                return
        super().keyPressEvent(event)

