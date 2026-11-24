"""Keyboard-first dialogs for one-click archive taxonomy tagging and retroactive tag editing."""

from __future__ import annotations

import sqlite3
import sys
from typing import Sequence

from PySide6.QtCore import Qt
from PySide6.QtWidgets import (
    QDialog,
    QFrame,
    QHBoxLayout,
    QLabel,
    QPushButton,
    QVBoxLayout,
    QWidget,
)

from src.database.history_fts import (
    get_ticket_taxonomy,
    list_taxonomy_nodes,
    suggest_taxonomy_for_text,
)
from src.ui.components.taxonomy_pill_selector import (
    TaxonomyPillSelector,
    persist_taxonomy_assignments,
)

sys.modules.setdefault("archive_taxonomy_dialog", sys.modules[__name__])


def _format_ticket_summary(ticket_number: str, client_name: str, title: str) -> str:
    parts: list[str] = []
    num = (ticket_number or "").strip()
    client = (client_name or "").strip()
    subj = (title or "").strip()
    if num:
        parts.append(num if num.startswith("#") else f"#{num}")
    if client:
        parts.append(client)
    if subj:
        parts.append(subj)
    return " · ".join(parts) if parts else "Active Ticket"


class ArchiveTaxonomyDialog(QDialog):
    """Fast keyboard-first modal intercepting single-ticket archive with auto-suggested EN/FR pills."""

    OUTCOME_CANCEL = 0
    OUTCOME_ARCHIVE_WITH_TAGS = 1
    OUTCOME_ARCHIVE_WITHOUT_TAGS = 2

    def __init__(
        self,
        *,
        ticket_number: str = "",
        client_name: str = "",
        title: str = "",
        body_text: str = "",
        conn: sqlite3.Connection | None = None,
        nodes: Sequence[dict[str, object]] | None = None,
        suggestions: dict[str, list[dict[str, object]]] | None = None,
        parent: QWidget | None = None,
    ) -> None:
        super().__init__(parent)
        self._conn = conn
        self._title_text = title or ""
        self._body_text = body_text or ""
        self.outcome = self.OUTCOME_CANCEL

        self.setWindowTitle("Archive Ticket — Categorize & Tag")
        self.setModal(True)
        self.setMinimumWidth(640)

        root = QVBoxLayout(self)
        root.setContentsMargins(16, 14, 16, 14)
        root.setSpacing(10)

        self.summary_label = QLabel(_format_ticket_summary(ticket_number, client_name, title), self)
        self.summary_label.setWordWrap(True)
        self.summary_label.setStyleSheet(
            "font-weight: 700; font-size: 13px; color: #f8fafc; "
            "background-color: rgba(18, 27, 46, 0.72); "
            "border: 1px solid rgba(56, 189, 248, 0.28); "
            "border-radius: 6px; padding: 7px 10px;"
        )
        root.addWidget(self.summary_label)

        resolved_nodes = list(nodes) if nodes is not None else None
        if resolved_nodes is None and conn is not None:
            resolved_nodes = list_taxonomy_nodes(conn, active_only=True) or None

        self.pill_selector = TaxonomyPillSelector(nodes=resolved_nodes, conn=conn, parent=self)
        auto_sug = (
            suggestions
            if suggestions is not None
            else suggest_taxonomy_for_text(title=self._title_text, body=self._body_text, conn=conn, max_per_axis=2)
        )
        self.pill_selector.set_auto_suggestions(auto_sug, clear_existing=True, max_per_axis=1)
        root.addWidget(self.pill_selector)

        divider = QFrame(self)
        divider.setFrameShape(QFrame.Shape.HLine)
        divider.setStyleSheet("color: rgba(56, 189, 248, 0.22);")
        root.addWidget(divider)

        btn_row = QHBoxLayout()
        btn_row.setSpacing(8)

        self.cancel_btn = QPushButton("Cancel", self)
        self.cancel_btn.setObjectName("btnCancel")
        self.cancel_btn.setAutoDefault(False)
        self.cancel_btn.setToolTip("Cancel archiving and keep ticket active (Esc)")
        self.cancel_btn.clicked.connect(self._on_cancel)

        self.archive_untagged_btn = QPushButton("Archive Without Tags", self)
        self.archive_untagged_btn.setAutoDefault(False)
        self.archive_untagged_btn.setToolTip("Archive ticket immediately with zero taxonomy tags assigned")
        self.archive_untagged_btn.clicked.connect(self._on_archive_without_tags)

        self.archive_btn = QPushButton("Archive Ticket", self)
        self.archive_btn.setObjectName("btnPrimary")
        self.archive_btn.setDefault(True)
        self.archive_btn.setAutoDefault(True)
        self.archive_btn.setToolTip("Confirm selected tags and move ticket to History (Enter)")
        self.archive_btn.clicked.connect(self._on_archive_with_tags)

        btn_row.addWidget(self.cancel_btn)
        btn_row.addStretch(1)
        btn_row.addWidget(self.archive_untagged_btn)
        btn_row.addWidget(self.archive_btn)
        root.addLayout(btn_row)

        self.archive_btn.setFocus()

    def _on_archive_with_tags(self) -> None:
        self.outcome = self.OUTCOME_ARCHIVE_WITH_TAGS
        self.accept()

    def _on_archive_without_tags(self) -> None:
        self.outcome = self.OUTCOME_ARCHIVE_WITHOUT_TAGS
        self.accept()

    def _on_cancel(self) -> None:
        self.outcome = self.OUTCOME_CANCEL
        self.reject()

    def reject(self) -> None:
        self.outcome = self.OUTCOME_CANCEL
        super().reject()

    def selected_slugs(self) -> list[str]:
        if self.outcome != self.OUTCOME_ARCHIVE_WITH_TAGS:
            return []
        return self.pill_selector.selected_slugs()

    def selected_assignments(self) -> list[dict[str, object]]:
        if self.outcome != self.OUTCOME_ARCHIVE_WITH_TAGS:
            return []
        return self.pill_selector.selected_assignments()


class EditTicketTaxonomyDialog(QDialog):
    """Modal dialog for retroactively viewing, suggesting, and editing tags on an archived ticket."""

    def __init__(
        self,
        *,
        ticket_id: int,
        ticket_number: str = "",
        client_name: str = "",
        title: str = "",
        body_text: str = "",
        conn: sqlite3.Connection | None = None,
        nodes: Sequence[dict[str, object]] | None = None,
        saved_tags: Sequence[dict[str, object] | str] | None = None,
        parent: QWidget | None = None,
    ) -> None:
        super().__init__(parent)
        self._ticket_id = int(ticket_id)
        self._conn = conn
        self._title_text = title or ""
        self._body_text = body_text or ""

        self.setWindowTitle("Edit Ticket Taxonomy Tags")
        self.setModal(True)
        self.setMinimumWidth(640)

        root = QVBoxLayout(self)
        root.setContentsMargins(16, 14, 16, 14)
        root.setSpacing(10)

        header_bar = QHBoxLayout()
        header_bar.setSpacing(8)
        self.summary_label = QLabel(_format_ticket_summary(ticket_number, client_name, title), self)
        self.summary_label.setWordWrap(True)
        self.summary_label.setStyleSheet(
            "font-weight: 700; font-size: 13px; color: #f8fafc; "
            "background-color: rgba(18, 27, 46, 0.72); "
            "border: 1px solid rgba(56, 189, 248, 0.28); "
            "border-radius: 6px; padding: 7px 10px;"
        )
        header_bar.addWidget(self.summary_label, stretch=1)

        self.suggest_btn = QPushButton("✦ Suggest Tags", self)
        self.suggest_btn.setAutoDefault(False)
        self.suggest_btn.setToolTip("Auto-suggest matching EN/FR Domain, Symptom & Resolution tags from note text")
        self.suggest_btn.clicked.connect(self._on_suggest_clicked)
        header_bar.addWidget(self.suggest_btn)
        root.addLayout(header_bar)

        resolved_nodes = list(nodes) if nodes is not None else None
        if resolved_nodes is None and conn is not None:
            resolved_nodes = list_taxonomy_nodes(conn, active_only=True) or None

        self.pill_selector = TaxonomyPillSelector(nodes=resolved_nodes, conn=conn, parent=self)
        initial_tags = (
            list(saved_tags)
            if saved_tags is not None
            else (get_ticket_taxonomy(conn, self._ticket_id) if conn is not None else [])
        )
        self.pill_selector.set_saved_tags(initial_tags)
        root.addWidget(self.pill_selector)

        divider = QFrame(self)
        divider.setFrameShape(QFrame.Shape.HLine)
        divider.setStyleSheet("color: rgba(56, 189, 248, 0.22);")
        root.addWidget(divider)

        btn_row = QHBoxLayout()
        btn_row.setSpacing(8)

        self.cancel_btn = QPushButton("Cancel", self)
        self.cancel_btn.setObjectName("btnCancel")
        self.cancel_btn.setAutoDefault(False)
        self.cancel_btn.clicked.connect(self.reject)

        self.save_btn = QPushButton("Save Tags", self)
        self.save_btn.setObjectName("btnPrimary")
        self.save_btn.setDefault(True)
        self.save_btn.setAutoDefault(True)
        self.save_btn.clicked.connect(self.accept)

        btn_row.addWidget(self.cancel_btn)
        btn_row.addStretch(1)
        btn_row.addWidget(self.save_btn)
        root.addLayout(btn_row)

        self.save_btn.setFocus()

    def _on_suggest_clicked(self) -> None:
        suggestions = suggest_taxonomy_for_text(
            title=self._title_text,
            body=self._body_text,
            conn=self._conn,
            max_per_axis=2,
        )
        self.pill_selector.set_auto_suggestions(suggestions, clear_existing=False, max_per_axis=1)

    def selected_slugs(self) -> list[str]:
        return self.pill_selector.selected_slugs()

    def selected_assignments(self) -> list[dict[str, object]]:
        return self.pill_selector.selected_assignments()


__all__ = [
    "ArchiveTaxonomyDialog",
    "EditTicketTaxonomyDialog",
    "persist_taxonomy_assignments",
]
