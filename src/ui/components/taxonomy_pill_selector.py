"""Reusable wrapping FlowLayout and dark-theme 3-axis taxonomy pill selector widget."""

from __future__ import annotations

import sqlite3
import sys
from typing import Callable, Iterable, Sequence

from PySide6.QtCore import QPoint, QRect, QSize, Qt, Signal
from PySide6.QtWidgets import (
    QHBoxLayout,
    QLabel,
    QLayout,
    QLayoutItem,
    QPushButton,
    QSizePolicy,
    QVBoxLayout,
    QWidget,
)

from src.database.history_fts import (
    assign_ticket_taxonomy,
    get_ticket_taxonomy,
    list_taxonomy_nodes,
    load_taxonomy_seed,
)

# Expose as top-level `taxonomy_pill_selector` as well so direct imports work identically.
sys.modules.setdefault("taxonomy_pill_selector", sys.modules[__name__])

_AXIS_TITLES: tuple[tuple[str, str], ...] = (
    ("domain", "Domain"),
    ("symptom", "Symptom"),
    ("resolution", "Resolution"),
)


def persist_taxonomy_assignments(
    conn: sqlite3.Connection,
    ticket_id: int,
    assignments: Sequence[dict[str, object]],
    *,
    replace_existing: bool = True,
) -> list[dict[str, object]]:
    """Atomically persist manual/auto taxonomy assignments with per-tag provenance via Step 1 APIs."""
    normalized: list[tuple[str, str, float]] = []
    seen: set[str] = set()
    for entry in assignments:
        slug = str(entry.get("slug", "")).strip()
        if not slug or slug in seen:
            continue
        seen.add(slug)
        raw_source = str(entry.get("source", "manual")).strip().lower()
        source = raw_source if raw_source in ("auto", "manual", "legacy") else "manual"
        confidence = max(0.0, min(1.0, float(entry.get("confidence", 1.0))))
        normalized.append((slug, source, confidence))

    in_tx = bool(conn.in_transaction)
    if not in_tx:
        conn.execute("BEGIN")
    try:
        if replace_existing:
            assign_ticket_taxonomy(conn, ticket_id, [], replace_existing=True)

        for slug, source, confidence in normalized:
            assign_ticket_taxonomy(
                conn,
                ticket_id,
                [slug],
                source=source,
                confidence=confidence,
                replace_existing=False,
            )

        if not in_tx:
            conn.commit()
    except Exception:
        if not in_tx and conn.in_transaction:
            conn.rollback()
        raise

    return get_ticket_taxonomy(conn, ticket_id)


class FlowLayout(QLayout):
    """Standard Qt wrapping layout that flows pill widgets across rows without horizontal scroll."""

    def __init__(
        self,
        parent: QWidget | None = None,
        margin: int = 0,
        h_spacing: int = 6,
        v_spacing: int = 6,
    ) -> None:
        super().__init__(parent)
        self._item_list: list[QLayoutItem] = []
        self._h_space = h_spacing
        self._v_space = v_spacing
        self.setContentsMargins(margin, margin, margin, margin)

    def __del__(self) -> None:
        while self._item_list:
            self.takeAt(0)

    def addItem(self, item: QLayoutItem) -> None:
        self._item_list.append(item)

    def horizontalSpacing(self) -> int:
        return self._h_space

    def verticalSpacing(self) -> int:
        return self._v_space

    def count(self) -> int:
        return len(self._item_list)

    def itemAt(self, index: int) -> QLayoutItem | None:
        if 0 <= index < len(self._item_list):
            return self._item_list[index]
        return None

    def takeAt(self, index: int) -> QLayoutItem | None:
        if 0 <= index < len(self._item_list):
            return self._item_list.pop(index)
        return None

    def expandingDirections(self) -> Qt.Orientation:
        return Qt.Orientation(0)

    def hasHeightForWidth(self) -> bool:
        return True

    def heightForWidth(self, width: int) -> int:
        return self._do_layout(QRect(0, 0, width, 0), test_only=True)

    def setGeometry(self, rect: QRect) -> None:
        super().setGeometry(rect)
        self._do_layout(rect, test_only=False)

    def sizeHint(self) -> QSize:
        return self.minimumSize()

    def minimumSize(self) -> QSize:
        size = QSize()
        for item in self._item_list:
            size = size.expandedTo(item.minimumSize())
        margins = self.contentsMargins()
        size += QSize(margins.left() + margins.right(), margins.top() + margins.bottom())
        return size

    def _do_layout(self, rect: QRect, *, test_only: bool) -> int:
        left, top, right, bottom = self.getContentsMargins()
        effective = rect.adjusted(left, top, -right, -bottom)
        x = effective.x()
        y = effective.y()
        line_height = 0

        for item in self._item_list:
            hint = item.sizeHint()
            next_x = x + hint.width() + self._h_space
            if next_x - self._h_space > effective.right() and line_height > 0:
                x = effective.x()
                y = y + line_height + self._v_space
                next_x = x + hint.width() + self._h_space
                line_height = 0

            if not test_only:
                item.setGeometry(QRect(QPoint(x, y), hint))

            x = next_x
            line_height = max(line_height, hint.height())

        return y + line_height - rect.y() + bottom


def _pill_stylesheet(state: str) -> str:
    """Return dark-theme QSS styling for unselected, manual, and auto-suggested pill states."""
    if state == "auto":
        return (
            "QPushButton {"
            "  background: qlineargradient(x1:0, y1:0, x2:1, y2:0, stop:0 rgba(124,58,237,0.42), stop:1 rgba(14,165,233,0.34));"
            "  color: #f5f3ff;"
            "  border: 1px solid #a78bfa;"
            "  border-radius: 12px;"
            "  padding: 4px 10px;"
            "  font-size: 11px;"
            "  font-weight: 600;"
            "}"
            "QPushButton:hover { border-color: #c4b5fd; color: #ffffff; }"
        )
    if state == "manual":
        return (
            "QPushButton {"
            "  background: qlineargradient(x1:0, y1:0, x2:1, y2:0, stop:0 #0284c7, stop:1 #2563eb);"
            "  color: #ffffff;"
            "  border: 1px solid #38bdf8;"
            "  border-radius: 12px;"
            "  padding: 4px 10px;"
            "  font-size: 11px;"
            "  font-weight: 600;"
            "}"
            "QPushButton:hover { border-color: #7dd3fc; background: #0ea5e9; }"
        )
    return (
        "QPushButton {"
        "  background-color: rgba(15, 23, 42, 0.72);"
        "  color: #cbd5e1;"
        "  border: 1px solid rgba(71, 85, 105, 0.60);"
        "  border-radius: 12px;"
        "  padding: 4px 10px;"
        "  font-size: 11px;"
        "  font-weight: 500;"
        "}"
        "QPushButton:hover {"
        "  border: 1px solid rgba(56, 189, 248, 0.75);"
        "  color: #f8fafc;"
        "  background-color: rgba(30, 41, 59, 0.85);"
        "}"
    )


class TaxonomyPillSelector(QWidget):
    """Compact dark-mode pill selector grouped by Domain, Symptom, and Resolution with provenance tracking."""

    selection_changed = Signal()

    def __init__(
        self,
        nodes: Sequence[dict[str, object]] | None = None,
        *,
        conn: sqlite3.Connection | None = None,
        parent: QWidget | None = None,
    ) -> None:
        super().__init__(parent)
        self._nodes = self._resolve_nodes(nodes=nodes, conn=conn)
        self._nodes_by_slug: dict[str, dict[str, object]] = {
            str(n["slug"]): dict(n) for n in self._nodes if n.get("slug")
        }
        self._provenance: dict[str, str] = {}
        self._confidence: dict[str, float] = {}
        self.pill_buttons: dict[str, QPushButton] = {}
        self._axis_layouts: dict[str, FlowLayout] = {}

        self._build_ui()

    @staticmethod
    def _resolve_nodes(
        *,
        nodes: Sequence[dict[str, object]] | None,
        conn: sqlite3.Connection | None,
    ) -> list[dict[str, object]]:
        if nodes is not None:
            return [dict(n) for n in nodes]
        if conn is not None:
            try:
                loaded = list_taxonomy_nodes(conn, active_only=True)
                if loaded:
                    return loaded
            except sqlite3.Error:
                pass
        return [dict(n) for n in load_taxonomy_seed().get("nodes", [])]

    def _build_ui(self) -> None:
        root = QVBoxLayout(self)
        root.setContentsMargins(0, 0, 0, 0)
        root.setSpacing(8)

        # Header row: legend + Clear All action
        header_row = QHBoxLayout()
        header_row.setContentsMargins(0, 0, 0, 0)
        header_row.setSpacing(8)

        legend = QLabel("✦ Auto-suggested · Click any pill to toggle manual tags")
        legend.setStyleSheet("color: #94a3b8; font-size: 11px;")
        header_row.addWidget(legend)
        header_row.addStretch(1)

        self.clear_all_btn = QPushButton("Clear All")
        self.clear_all_btn.setFlat(True)
        self.clear_all_btn.setCursor(Qt.CursorShape.PointingHandCursor)
        self.clear_all_btn.setAutoDefault(False)
        self.clear_all_btn.setStyleSheet(
            "QPushButton { color: #7dd3fc; border: none; background: transparent; padding: 2px 6px; font-size: 11px; }"
            "QPushButton:hover { color: #bae6fd; text-decoration: underline; }"
        )
        self.clear_all_btn.clicked.connect(self.clear_all)
        header_row.addWidget(self.clear_all_btn)
        root.addLayout(header_row)

        parent_domain_slugs = {
            str(n["parent_slug"])
            for n in self._nodes
            if n.get("axis") == "domain" and n.get("parent_slug")
        }

        for axis_key, axis_title in _AXIS_TITLES:
            axis_label = QLabel(axis_title)
            axis_label.setStyleSheet(
                "color: #7dd3fc; font-weight: 700; font-size: 11px; margin-top: 2px;"
            )
            root.addWidget(axis_label)

            container = QWidget(self)
            flow = FlowLayout(container, margin=0, h_spacing=6, v_spacing=6)
            container.setLayout(flow)
            container.setSizePolicy(QSizePolicy.Policy.Expanding, QSizePolicy.Policy.Preferred)
            self._axis_layouts[axis_key] = flow

            for node in self._nodes:
                if node.get("axis") != axis_key:
                    continue
                slug = str(node["slug"])
                if axis_key == "domain" and slug in parent_domain_slugs:
                    continue
                self._create_pill_button(slug, str(node["label"]), flow, container)

            root.addWidget(container)

    def _create_pill_button(
        self,
        slug: str,
        label: str,
        flow: FlowLayout,
        parent_widget: QWidget,
    ) -> QPushButton:
        if slug in self.pill_buttons:
            return self.pill_buttons[slug]
        btn = QPushButton(label, parent_widget)
        btn.setCheckable(True)
        btn.setAutoDefault(False)
        btn.setCursor(Qt.CursorShape.PointingHandCursor)
        btn.setSizePolicy(QSizePolicy.Policy.Fixed, QSizePolicy.Policy.Fixed)
        btn.clicked.connect(lambda checked=False, s=slug: self._on_pill_clicked(s, checked))
        self.pill_buttons[slug] = btn
        flow.addWidget(btn)
        self._sync_button_appearance(slug)
        return btn

    def _ensure_pill_button(self, slug: str) -> QPushButton | None:
        if slug in self.pill_buttons:
            return self.pill_buttons[slug]
        node = self._nodes_by_slug.get(slug)
        if node is None:
            return None
        axis = str(node.get("axis", ""))
        flow = self._axis_layouts.get(axis)
        if flow is None:
            return None
        parent_widget = flow.parentWidget() or self
        return self._create_pill_button(slug, str(node.get("label", slug)), flow, parent_widget)

    def _sync_button_appearance(self, slug: str) -> None:
        btn = self.pill_buttons.get(slug)
        if btn is None:
            return
        node = self._nodes_by_slug.get(slug, {})
        base_label = str(node.get("label", slug))
        if not btn.isChecked():
            state = "unselected"
            btn.setText(base_label)
            btn.setToolTip(base_label)
        elif self._provenance.get(slug) == "auto":
            state = "auto"
            btn.setText(f"✦ {base_label}")
            btn.setToolTip(f"{base_label} (Auto-suggested)")
        else:
            state = "manual"
            btn.setText(base_label)
            btn.setToolTip(f"{base_label} (Manual)")
        btn.setProperty("pillState", state)
        btn.setStyleSheet(_pill_stylesheet(state))

    def _on_pill_clicked(self, slug: str, checked: bool) -> None:
        if checked:
            self._provenance[slug] = "manual"
            self._confidence[slug] = 1.0
        else:
            self._provenance.pop(slug, None)
            self._confidence.pop(slug, None)
        self._sync_button_appearance(slug)
        self.selection_changed.emit()

    def set_pill_state(
        self,
        slug: str,
        checked: bool,
        *,
        source: str = "manual",
        confidence: float = 1.0,
    ) -> bool:
        """Programmatically set a pill checked/unchecked with explicit provenance."""
        btn = self._ensure_pill_button(slug)
        if btn is None:
            return False
        btn.blockSignals(True)
        btn.setChecked(bool(checked))
        btn.blockSignals(False)
        if checked:
            self._provenance[slug] = "auto" if source == "auto" else "manual"
            self._confidence[slug] = max(0.0, min(1.0, float(confidence)))
        else:
            self._provenance.pop(slug, None)
            self._confidence.pop(slug, None)
        self._sync_button_appearance(slug)
        self.selection_changed.emit()
        return True

    def clear_all(self) -> None:
        """Uncheck all pills and reset provenance state."""
        self._provenance.clear()
        self._confidence.clear()
        for slug, btn in self.pill_buttons.items():
            btn.blockSignals(True)
            btn.setChecked(False)
            btn.blockSignals(False)
            self._sync_button_appearance(slug)
        self.selection_changed.emit()

    def set_auto_suggestions(
        self,
        suggestions: dict[str, Sequence[dict[str, object]]],
        *,
        clear_existing: bool = True,
        max_per_axis: int | None = None,
    ) -> None:
        """Pre-select suggested tags as source='auto' (preserving existing manual pills when clear_existing=False)."""
        if clear_existing:
            self.clear_all()

        for axis_key, _ in _AXIS_TITLES:
            axis_items = suggestions.get(axis_key) or ()
            applied = 0
            for item in axis_items:
                slug = str(item.get("slug", "")).strip()
                if not slug or slug not in self.pill_buttons:
                    continue
                if max_per_axis is not None and applied >= max_per_axis:
                    break
                btn = self.pill_buttons[slug]
                if not clear_existing and btn.isChecked() and self._provenance.get(slug) == "manual":
                    applied += 1
                    continue
                conf = float(item.get("confidence", 0.7))
                btn.blockSignals(True)
                btn.setChecked(True)
                btn.blockSignals(False)
                self._provenance[slug] = "auto"
                self._confidence[slug] = max(0.0, min(1.0, conf))
                self._sync_button_appearance(slug)
                applied += 1
        self.selection_changed.emit()

    def set_saved_tags(self, saved_tags: Iterable[dict[str, object] | str]) -> None:
        """Pre-select saved tags from SQLite (preserving 'auto' vs 'manual' provenance)."""
        self.clear_all()
        for entry in saved_tags:
            if isinstance(entry, str):
                slug = entry.strip()
                source = "manual"
                confidence = 1.0
            else:
                slug = str(entry.get("slug", "")).strip()
                raw_source = str(entry.get("source", "manual")).strip().lower()
                source = "auto" if raw_source == "auto" else "manual"
                confidence = float(entry.get("confidence", 1.0))
            if not slug:
                continue
            btn = self._ensure_pill_button(slug)
            if btn is None:
                continue
            btn.blockSignals(True)
            btn.setChecked(True)
            btn.blockSignals(False)
            self._provenance[slug] = source
            self._confidence[slug] = max(0.0, min(1.0, confidence))
            self._sync_button_appearance(slug)
        self.selection_changed.emit()

    def selected_slugs(self) -> list[str]:
        """Return currently checked taxonomy slugs."""
        return [slug for slug, btn in self.pill_buttons.items() if btn.isChecked()]

    def selected_assignments(self) -> list[dict[str, object]]:
        """Return checked tags paired with provenance ('auto' or 'manual') and confidence."""
        return [
            {
                "slug": slug,
                "source": self._provenance.get(slug, "manual"),
                "confidence": self._confidence.get(slug, 1.0),
            }
            for slug in self.selected_slugs()
        ]


def __getattr__(name: str):
    if name in ("ArchiveTaxonomyDialog", "EditTicketTaxonomyDialog"):
        from src.ui.dialogs import archive_taxonomy_dialog as _dlg_mod

        return getattr(_dlg_mod, name)
    raise AttributeError(f"module {__name__!r} has no attribute {name!r}")
