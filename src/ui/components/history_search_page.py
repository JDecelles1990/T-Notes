"""Full-page master-detail History Search workspace backed by SQLite FTS5."""

from __future__ import annotations

from datetime import datetime, timedelta
import html
import re
import sqlite3
import sys
from typing import Callable
import unicodedata

from PySide6.QtCore import QEvent, QRectF, QSize, Qt, QTimer, Signal
from PySide6.QtGui import (
    QAbstractTextDocumentLayout,
    QColor,
    QFont,
    QGuiApplication,
    QKeySequence,
    QShortcut,
    QTextCharFormat,
    QTextCursor,
    QTextDocument,
)
from PySide6.QtWidgets import (
    QApplication,
    QColorDialog,
    QComboBox,
    QFileDialog,
    QFrame,
    QGroupBox,
    QHBoxLayout,
    QLabel,
    QLineEdit,
    QListWidget,
    QListWidgetItem,
    QMenu,
    QPlainTextEdit,
    QPushButton,
    QSplitter,
    QStyle,
    QStyledItemDelegate,
    QStyleOptionViewItem,
    QTextEdit,
    QToolButton,
    QVBoxLayout,
    QWidget,
)

from src.core.constants import LOG_BADGES, TICKET_SKELETONS
from src.database.history_fts import (
    HistorySearchResult,
    get_history_ticket,
    get_ticket_taxonomy,
    list_history_clients,
    list_taxonomy_nodes,
    search_history,
)
from src.ui.components.editor import TechPadEditor
from src.ui.components.panel_transition import PanelWidthTransition
from src.ui.m365.launcher_widget import HoverToolButton

# Expose as top-level `history_search_page` as well so direct imports work identically.
sys.modules.setdefault("history_search_page", sys.modules[__name__])

_RESULT_ROLE = Qt.ItemDataRole.UserRole + 1
_QUERY_TOKEN_RE = re.compile(r'"([^"]+)"|(\S+)')


def _extract_highlight_terms(raw_query: str) -> list[str]:
    """Pull searchable terms out of the query string for preview highlighting."""
    terms: list[str] = []
    for phrase, token in _QUERY_TOKEN_RE.findall(raw_query or ""):
        if not phrase and token == "OR":
            continue
        candidate = (phrase or token).strip('"').strip()
        if any(ch.isalnum() for ch in candidate):
            terms.append(candidate)
    return terms


def _strip_accents_with_map(text: str) -> tuple[str, list[int]]:
    """Return (lowercased_ascii_folded_text, index_map) for accent-insensitive offset mapping."""
    norm_chars: list[str] = []
    idx_map: list[int] = []
    for orig_idx, ch in enumerate(text):
        decomposed = unicodedata.normalize("NFKD", ch)
        for part in decomposed:
            if unicodedata.category(part) != "Mn":
                norm_chars.append(part.lower())
                idx_map.append(orig_idx)
    return "".join(norm_chars), idx_map


class HistoryItemDelegate(QStyledItemDelegate):
    """Renders compact multi-line rich-text result cards with taxonomy badges and FTS5 snippets."""

    _PADDING_X = 10
    _PADDING_Y = 7

    def __init__(
        self,
        parent: QWidget | None = None,
        label_lookup: Callable[[str], str] | None = None,
    ) -> None:
        super().__init__(parent)
        self._label_lookup = label_lookup

    def _build_document(self, option: QStyleOptionViewItem, result: HistorySearchResult) -> QTextDocument:
        doc = QTextDocument()
        doc.setDefaultFont(option.font)
        doc.setDocumentMargin(0)

        date_short = (result.archived_at or "")[:10]
        client_part = f" · {html.escape(result.client)}" if result.client else ""
        header_meta = f"{html.escape(result.ticket_number)}{client_part}"
        title_safe = html.escape(result.title or "(Untitled)")
        snippet_safe = result.snippet_html or ""

        tax_badges_html = ""
        if getattr(result, "taxonomy_slugs", ()):
            pills = []
            for slug in result.taxonomy_slugs:
                lbl = html.escape(self._label_lookup(slug) if self._label_lookup else slug)
                pills.append(
                    f"<span style='background-color:rgba(56,189,248,0.14); color:#7dd3fc; "
                    f"padding:1px 5px; border-radius:3px; font-size:10px;'>{lbl}</span>"
                )
            tax_badges_html = f"<div style='margin-top:3px;'>{' &nbsp;'.join(pills)}</div>"

        muted_color = option.palette.placeholderText().color().name()
        text_color = (
            option.palette.highlightedText().color().name()
            if option.state & QStyle.StateFlag.State_Selected
            else option.palette.text().color().name()
        )

        card_html = (
            f"<div style='color:{text_color};'>"
            f"<table width='100%' cellspacing='0' cellpadding='0'><tr>"
            f"<td style='font-size:11px; color:{muted_color};'><b>{header_meta}</b></td>"
            f"<td align='right' style='font-size:11px; color:{muted_color};'>{html.escape(date_short)}</td>"
            f"</tr></table>"
            f"<div style='font-size:13px; margin-top:2px;'><b>{title_safe}</b></div>"
            f"{tax_badges_html}"
            f"<div style='font-size:12px; color:{muted_color}; margin-top:2px;'>{snippet_safe}</div>"
            f"</div>"
        )
        doc.setHtml(card_html)
        avail_width = max(option.rect.width() - (self._PADDING_X * 2), 200)
        doc.setTextWidth(avail_width)
        return doc

    def paint(self, painter, option: QStyleOptionViewItem, index) -> None:
        result: HistorySearchResult | None = index.data(_RESULT_ROLE)
        if result is None:
            super().paint(painter, option, index)
            return

        painter.save()
        opt = QStyleOptionViewItem(option)
        self.initStyleOption(opt, index)
        opt.text = ""

        style = opt.widget.style() if opt.widget else None
        if style:
            style.drawControl(QStyle.ControlElement.CE_ItemViewItem, opt, painter, opt.widget)

        doc = self._build_document(opt, result)
        painter.translate(opt.rect.left() + self._PADDING_X, opt.rect.top() + self._PADDING_Y)
        clip = QRectF(0, 0, opt.rect.width() - self._PADDING_X * 2, opt.rect.height() - self._PADDING_Y * 2)

        ctx = QAbstractTextDocumentLayout.PaintContext()
        ctx.palette = opt.palette
        ctx.clip = clip
        doc.documentLayout().draw(painter, ctx)

        painter.restore()
        painter.save()
        divider = opt.palette.mid().color()
        divider.setAlpha(60)
        painter.setPen(divider)
        painter.drawLine(opt.rect.bottomLeft(), opt.rect.bottomRight())
        painter.restore()

    def sizeHint(self, option: QStyleOptionViewItem, index) -> QSize:
        result: HistorySearchResult | None = index.data(_RESULT_ROLE)
        if result is None:
            return super().sizeHint(option, index)
        doc = self._build_document(option, result)
        height = int(doc.size().height()) + (self._PADDING_Y * 2) + 2
        return QSize(option.rect.width(), max(height, 64))


class HistorySearchPage(QWidget):
    """Full-page master-detail search workspace for archived T-Notes tickets."""

    back_requested = Signal()
    restore_requested = Signal(int)
    clone_requested = Signal(int)
    note_modified = Signal(int)
    save_requested = Signal(int)
    send_default_email_requested = Signal()
    status_message_requested = Signal(str, int)

    _PAGE_SIZE = 100

    def __init__(
        self,
        get_conn: Callable[[], sqlite3.Connection],
        parent: QWidget | None = None,
    ) -> None:
        super().__init__(parent)
        self._get_conn = get_conn
        self._loaded_count = 0
        self._total_count = 0
        self._current_ticket: dict[str, str | int] | None = None
        self.scratchpad_service = None
        self.image_service = None
        self._stopwatch = None
        self._active_editor: TechPadEditor | None = None
        self._current_ticket_number = ""
        self.ticket_editor: TechPadEditor | None = None
        self._taxonomy_labels: dict[str, str] = {}

        self._debounce = QTimer(self)
        self._debounce.setSingleShot(True)
        self._debounce.setInterval(180)
        self._debounce.timeout.connect(self._run_fresh_search)

        self._build_ui()
        self._wire_signals()

    def _build_ui(self) -> None:
        root = QVBoxLayout(self)
        root.setContentsMargins(12, 10, 12, 10)
        root.setSpacing(8)

        # --- Top Filter Bar ---
        filter_bar = QHBoxLayout()
        filter_bar.setSpacing(8)

        self.back_btn = QPushButton("← Active Tickets")
        self.back_btn.setToolTip("Return to active workspace (Esc)")

        self.search_input = QLineEdit()
        self.search_input.setPlaceholderText(
            'Search archived tickets (e.g. INC-40219, vpn, "blue screen")...'
        )
        self.search_input.setClearButtonEnabled(True)
        self.search_input.installEventFilter(self)

        self.client_combo = QComboBox()
        self.client_combo.setMinimumWidth(120)
        self.client_combo.addItem("All Clients", None)
        self.client_combo.setToolTip("Filter archived tickets by Client / Company")

        self.date_combo = QComboBox()
        self.date_combo.addItem("All Time", None)
        self.date_combo.addItem("Last 7 Days", 7)
        self.date_combo.addItem("Last 30 Days", 30)
        self.date_combo.addItem("Last 90 Days", 90)
        self.date_combo.setToolTip("Filter by archive date window")

        self.domain_combo = QComboBox()
        self.domain_combo.addItem("All Domains", None)
        self.domain_combo.setToolTip("Filter by Technical Domain")

        self.symptom_combo = QComboBox()
        self.symptom_combo.addItem("All Symptoms", None)
        self.symptom_combo.setToolTip("Filter by Symptom")

        self.resolution_combo = QComboBox()
        self.resolution_combo.addItem("All Resolutions", None)
        self.resolution_combo.setToolTip("Filter by Resolution")

        for combo in (self.client_combo, self.domain_combo, self.symptom_combo, self.resolution_combo):
            combo.setSizeAdjustPolicy(QComboBox.SizeAdjustPolicy.AdjustToMinimumContentsLengthWithIcon)
            combo.setMinimumContentsLength(11)
            combo.setMaximumWidth(175)

        self.sort_combo = QComboBox()
        self.sort_combo.addItem("Relevance", "relevance")
        self.sort_combo.addItem("Newest Archived", "date")
        self.sort_combo.setToolTip("Sort results by BM25 relevance or newest archive date")

        self.count_label = QLabel("")
        self.count_label.setMinimumWidth(90)
        self.count_label.setAlignment(Qt.AlignmentFlag.AlignRight | Qt.AlignmentFlag.AlignVCenter)

        filter_bar.addWidget(self.back_btn)
        filter_bar.addWidget(self.search_input, stretch=1)
        filter_bar.addWidget(self.client_combo)
        filter_bar.addWidget(self.date_combo)
        filter_bar.addWidget(self.domain_combo)
        filter_bar.addWidget(self.symptom_combo)
        filter_bar.addWidget(self.resolution_combo)
        filter_bar.addWidget(self.sort_combo)
        filter_bar.addWidget(self.count_label)
        root.addLayout(filter_bar)

        # --- Master-Detail Splitter ---
        self.splitter = QSplitter(Qt.Orientation.Horizontal)
        self.splitter.setChildrenCollapsible(False)

        # Left Pane: Results List + Load More
        left_pane = QWidget()
        left_layout = QVBoxLayout(left_pane)
        left_layout.setContentsMargins(0, 0, 0, 0)
        left_layout.setSpacing(6)

        self.results_list = QListWidget()
        self.results_list.setItemDelegate(
            HistoryItemDelegate(
                self.results_list,
                label_lookup=lambda slug: self._taxonomy_labels.get(slug, slug),
            )
        )
        self.results_list.setUniformItemSizes(False)
        self.results_list.setHorizontalScrollBarPolicy(Qt.ScrollBarPolicy.ScrollBarAlwaysOff)
        self.results_list.setSpacing(0)

        self.load_more_btn = QPushButton("Load More")
        self.load_more_btn.setVisible(False)

        left_layout.addWidget(self.results_list, stretch=1)
        left_layout.addWidget(self.load_more_btn)

        # Right Pane: Preview Header + Action Strip + Highlighted Body
        right_pane = QWidget()
        right_layout = QVBoxLayout(right_pane)
        right_layout.setContentsMargins(8, 0, 0, 0)
        right_layout.setSpacing(8)

        self.meta_label = QLabel("Select an archived ticket to inspect its notes.")
        self.meta_label.setWordWrap(True)

        action_bar = QHBoxLayout()
        action_bar.setSpacing(6)
        self.copy_all_btn = QPushButton("Copy All")
        self.copy_all_btn.setToolTip("Copy ticket header and full note body to clipboard")
        self.copy_body_btn = QPushButton("Copy Body")
        self.copy_body_btn.setToolTip("Copy ticket note body only to clipboard")
        self.restore_btn = QPushButton("Restore to Active")
        self.restore_btn.setToolTip("Re-open this archived ticket as an active workspace tab")
        self.clone_btn = QPushButton("Clone to New")
        self.clone_btn.setToolTip("Create a fresh active ticket pre-filled from this archived note")
        self.feedback_label = QLabel("")

        for btn in (self.copy_all_btn, self.copy_body_btn, self.restore_btn, self.clone_btn):
            btn.setEnabled(False)
            action_bar.addWidget(btn)
        action_bar.addStretch(1)
        action_bar.addWidget(self.feedback_label)

        divider = QFrame()
        divider.setFrameShape(QFrame.Shape.HLine)
        divider.setFrameShadow(QFrame.Shadow.Sunken)

        self.preview_edit = QPlainTextEdit()
        self.preview_edit.setReadOnly(True)
        self.preview_edit.setPlaceholderText("Ticket notes preview...")

        right_layout.addWidget(self.meta_label)
        right_layout.addLayout(action_bar)
        right_layout.addWidget(divider)
        right_layout.addWidget(self.preview_edit, stretch=1)

        self.splitter.addWidget(left_pane)
        self.splitter.addWidget(right_pane)

        # Hidden toggle button kept synchronized with bottom status-bar "Active Ticket" button
        self.ticket_panel_toggle = QToolButton(self)
        self.ticket_panel_toggle.setText("Active Ticket")
        self.ticket_panel_toggle.setToolTip("Show or hide the Active Ticket right pane")
        self.ticket_panel_toggle.setAccessibleName("Toggle active ticket panel in History")
        self.ticket_panel_toggle.setFocusPolicy(Qt.StrongFocus)
        self.ticket_panel_toggle.setCheckable(True)
        self.ticket_panel_toggle.setChecked(False)
        self.ticket_panel_toggle.setVisible(False)

        # Far-Right Pane: Active Ticket Sidebar (shared QTextDocument with live ticket)
        self.ticket_sidebar = QGroupBox("Active Ticket Notes", self.splitter)
        self.ticket_sidebar.setMinimumWidth(240)
        self._sidebar_layout = QVBoxLayout(self.ticket_sidebar)
        self._sidebar_layout.setContentsMargins(6, 10, 6, 6)
        self._sidebar_layout.setSpacing(4)

        self.ticket_header_card = QWidget(self.ticket_sidebar)
        self.ticket_header_card.setObjectName("ticketHeaderCard")
        self.ticket_header_card.setStyleSheet("""
            QWidget#ticketHeaderCard {
                background-color: rgba(18, 27, 46, 0.68);
                border: 1px solid rgba(56, 189, 248, 0.28);
                border-radius: 4px;
            }
        """)
        header_card_layout = QVBoxLayout(self.ticket_header_card)
        header_card_layout.setContentsMargins(6, 6, 6, 6)
        header_card_layout.setSpacing(4)

        id_client_row = QHBoxLayout()
        id_client_row.setContentsMargins(0, 0, 0, 0)
        id_client_row.setSpacing(4)

        self.lbl_ticket_id = QLabel("#INC-000", self.ticket_header_card)
        self.lbl_ticket_id.setStyleSheet(
            "font-weight: bold; font-size: 11px; color: #58a6ff; "
            "background-color: #161b22; border: 1px solid #30363d; "
            "border-radius: 3px; padding: 1px 5px;"
        )
        id_client_row.addWidget(self.lbl_ticket_id)

        self.lbl_ticket_client = QLabel("Client: N/A", self.ticket_header_card)
        self.lbl_ticket_client.setStyleSheet("color: #8b949e; font-size: 11px;")
        id_client_row.addWidget(self.lbl_ticket_client)
        id_client_row.addStretch(1)

        corner_btn_style = """
            QToolButton {
                background-color: #161b22; border: 1px solid #30363d; border-radius: 3px;
                color: #c9d1d9; font-family: 'Segoe UI Symbol', 'Segoe UI Emoji', Consolas, sans-serif;
                font-size: 11px; font-weight: bold; padding: 1px 2px;
            }
            QToolButton:hover { background-color: #30363d; border-color: #58a6ff; color: #ffffff; }
            QToolButton:pressed { background-color: #1f6feb; color: #ffffff; }
            QToolButton::menu-indicator { image: none; width: 0px; }
        """

        self.btn_template = QToolButton(self.ticket_header_card)
        self.btn_template.setText("🗒️")
        self.btn_template.setFixedSize(26, 22)
        self.btn_template.setPopupMode(QToolButton.InstantPopup)
        self.btn_template.setToolTip("Insert Structured Ticket Template (Ctrl+Alt+S)")
        self.btn_template.setStyleSheet(corner_btn_style)
        template_menu = QMenu(self.btn_template)
        for name in TICKET_SKELETONS.keys():
            act = template_menu.addAction(name)
            act.triggered.connect(lambda checked=False, n=name: self._insert_template(n))
        self.btn_template.setMenu(template_menu)
        id_client_row.addWidget(self.btn_template)

        self.btn_copy_note = QToolButton(self.ticket_header_card)
        self.btn_copy_note.setText("📋")
        self.btn_copy_note.setFixedSize(26, 22)
        self.btn_copy_note.setPopupMode(QToolButton.MenuButtonPopup)
        self.btn_copy_note.setToolTip("Copy Note: Click to copy rich note (Ctrl+Shift+C), or open menu for clean PSA export (Ctrl+Alt+N)")
        self.btn_copy_note.setStyleSheet(corner_btn_style)
        copy_menu = QMenu(self.btn_copy_note)
        act_copy_rich = copy_menu.addAction("📋 Copy Formatted Note (Rich Text & Images)")
        act_copy_rich.triggered.connect(self._copy_formatted_note)
        act_copy_clean = copy_menu.addAction("📤 Copy Clean Note for Ticket Tool")
        act_copy_clean.triggered.connect(self._copy_clean_note)
        act_export_file = copy_menu.addAction("💾 Export Note (T-Notes Folder)")
        act_export_file.triggered.connect(self._export_active_ticket_file)
        copy_menu.addSeparator()
        act_send_email = copy_menu.addAction("📧 Send Active Ticket to Default Email")
        act_send_email.triggered.connect(self.send_default_email_requested.emit)
        self.btn_copy_note.setMenu(copy_menu)
        self.btn_copy_note.clicked.connect(self._copy_formatted_note)
        id_client_row.addWidget(self.btn_copy_note)

        self.btn_more = HoverToolButton(self.ticket_header_card)
        self.btn_more.setText("...")
        self.btn_more.setFixedSize(26, 22)
        self.btn_more.setPopupMode(QToolButton.InstantPopup)
        self.btn_more.setToolTip("Text Features & Formatting (Click or Hover)")
        self.btn_more.setStyleSheet(corner_btn_style)
        self.menu_text_features = QMenu(self.btn_more)
        self.btn_more.setMenu(self.menu_text_features)
        id_client_row.addWidget(self.btn_more)

        self.act_bold = self.menu_text_features.addAction("B  Bold (Ctrl+B)")
        self.act_bold.setCheckable(True)
        self.act_bold.triggered.connect(self._toggle_bold)

        self.act_italic = self.menu_text_features.addAction("I   Italic (Ctrl+I)")
        self.act_italic.setCheckable(True)
        self.act_italic.triggered.connect(self._toggle_italic)

        self.act_underline = self.menu_text_features.addAction("U  Underline (Ctrl+U)")
        self.act_underline.setCheckable(True)
        self.act_underline.triggered.connect(self._toggle_underline)

        self.menu_text_features.addSeparator()

        self.act_color = self.menu_text_features.addAction("🎨 Text Color... (Ctrl+Alt+X)")
        self.act_color.triggered.connect(self._pick_text_color)

        self.act_highlight = self.menu_text_features.addAction("🖍️ Highlight Color... (Ctrl+Alt+H)")
        self.act_highlight.triggered.connect(self._pick_highlight_color)

        self.act_code = self.menu_text_features.addAction("</> Monospace Code Block (Ctrl+Alt+C)")
        self.act_code.triggered.connect(self._insert_code_block)

        self.menu_text_features.addSeparator()

        self.menu_badge = QMenu("🏷️ Log Badges", self.menu_text_features)
        for tag_key, info in LOG_BADGES.items():
            b_act = self.menu_badge.addAction(info["label"])
            b_act.triggered.connect(lambda checked=False, k=tag_key: self._insert_badge(k))
        self.menu_text_features.addMenu(self.menu_badge)

        self.menu_text_features.addSeparator()

        self.act_checklist = self.menu_text_features.addAction("☑ Checkbox (Ctrl+Alt+L)")
        self.act_checklist.triggered.connect(self._insert_checklist)

        self.act_timestamp = self.menu_text_features.addAction("🕒 Current Timestamp (F5)")
        self.act_timestamp.triggered.connect(self._insert_timestamp)

        self.act_image = self.menu_text_features.addAction("🖼️ Insert Image File... (Ctrl+Alt+I)")
        self.act_image.triggered.connect(self._insert_image)

        header_card_layout.addLayout(id_client_row)

        self.lbl_ticket_subject = QLabel("Subject: N/A", self.ticket_header_card)
        self.lbl_ticket_subject.setStyleSheet("color: #c9d1d9; font-size: 11px;")
        self.lbl_ticket_subject.setWordWrap(True)
        header_card_layout.addWidget(self.lbl_ticket_subject)

        stopwatch_row = QHBoxLayout()
        stopwatch_row.setContentsMargins(0, 0, 0, 0)
        stopwatch_row.setSpacing(4)

        self.lbl_sidebar_stopwatch = QLabel("⏱️ 00:00:00", self.ticket_header_card)
        self.lbl_sidebar_stopwatch.setStyleSheet(
            "font-family: Consolas, 'Courier New', monospace; font-size: 12px; "
            "font-weight: bold; color: #58a6ff; padding: 2px 4px; "
            "background-color: #161b22; border: 1px solid #30363d; border-radius: 3px;"
        )
        self.lbl_sidebar_stopwatch.setToolTip("Active ticket troubleshooting stopwatch")
        stopwatch_row.addWidget(self.lbl_sidebar_stopwatch, 1)

        self.btn_sidebar_stopwatch_toggle = QToolButton(self.ticket_header_card)
        self.btn_sidebar_stopwatch_toggle.setText("▶")
        self.btn_sidebar_stopwatch_toggle.setFixedSize(26, 22)
        self.btn_sidebar_stopwatch_toggle.setToolTip("Start / Pause Stopwatch")
        self.btn_sidebar_stopwatch_toggle.setStyleSheet("""
            QToolButton {
                background-color: #161b22; border: 1px solid #30363d; border-radius: 3px;
                font-family: 'Segoe UI Symbol', 'Segoe UI Emoji', sans-serif;
                font-size: 11px; color: #58a6ff; font-weight: bold;
            }
            QToolButton:hover { background-color: #30363d; border-color: #58a6ff; color: #79c0ff; }
        """)
        self.btn_sidebar_stopwatch_toggle.clicked.connect(self._toggle_stopwatch)
        stopwatch_row.addWidget(self.btn_sidebar_stopwatch_toggle)

        self.btn_sidebar_stopwatch_reset = QToolButton(self.ticket_header_card)
        self.btn_sidebar_stopwatch_reset.setText("↺")
        self.btn_sidebar_stopwatch_reset.setFixedSize(26, 22)
        self.btn_sidebar_stopwatch_reset.setToolTip("Reset Timer to 00:00:00")
        self.btn_sidebar_stopwatch_reset.setStyleSheet("""
            QToolButton {
                background-color: #161b22; border: 1px solid #30363d; border-radius: 3px;
                font-family: 'Segoe UI Symbol', 'Segoe UI Emoji', sans-serif;
                font-size: 12px; color: #8b949e; font-weight: bold;
            }
            QToolButton:hover { background-color: #30363d; border-color: #f85149; color: #f85149; }
        """)
        self.btn_sidebar_stopwatch_reset.clicked.connect(self._reset_stopwatch)
        stopwatch_row.addWidget(self.btn_sidebar_stopwatch_reset)

        header_card_layout.addLayout(stopwatch_row)
        self._sidebar_layout.addWidget(self.ticket_header_card)

        self._ticket_transition = PanelWidthTransition(self.ticket_sidebar, default_width=300)
        self.ticket_sidebar.hide()

        self.splitter.addWidget(self.ticket_sidebar)
        self.splitter.setStretchFactor(0, 0)
        self.splitter.setStretchFactor(1, 1)
        self.splitter.setStretchFactor(2, 0)
        self.splitter.setSizes([360, 560, 300])
        root.addWidget(self.splitter, stretch=1)

        esc_shortcut = QShortcut(QKeySequence(Qt.Key.Key_Escape), self)
        esc_shortcut.setContext(Qt.ShortcutContext.WidgetWithChildrenShortcut)
        esc_shortcut.activated.connect(self._handle_escape)

    def _wire_signals(self) -> None:
        self.back_btn.clicked.connect(self.back_requested.emit)
        self.search_input.textChanged.connect(lambda _: self._debounce.start())
        self.search_input.returnPressed.connect(self._run_fresh_search)
        self.client_combo.currentIndexChanged.connect(self._run_fresh_search)
        self.date_combo.currentIndexChanged.connect(self._run_fresh_search)
        self.domain_combo.currentIndexChanged.connect(self._run_fresh_search)
        self.symptom_combo.currentIndexChanged.connect(self._run_fresh_search)
        self.resolution_combo.currentIndexChanged.connect(self._run_fresh_search)
        self.sort_combo.currentIndexChanged.connect(self._run_fresh_search)
        self.load_more_btn.clicked.connect(self._load_next_page)
        self.results_list.currentItemChanged.connect(self._on_result_selected)

        self.copy_all_btn.clicked.connect(self._copy_all)
        self.copy_body_btn.clicked.connect(self._copy_body)
        self.restore_btn.clicked.connect(self._emit_restore)
        self.clone_btn.clicked.connect(self._emit_clone)
        self.ticket_panel_toggle.toggled.connect(self._on_ticket_panel_toggled)

    def eventFilter(self, watched, event) -> bool:
        if watched is self.search_input and event.type() == QEvent.Type.KeyPress:
            if event.key() == Qt.Key.Key_Down and self.results_list.count() > 0:
                self.results_list.setFocus()
                if self.results_list.currentRow() < 0:
                    self.results_list.setCurrentRow(0)
                return True
        return super().eventFilter(watched, event)

    # --- Public entry point when navigating to this page ---

    def refresh_and_focus(self) -> None:
        """Reload client and taxonomy dropdowns, run current query, and focus the search bar."""
        self._reload_clients()
        self._reload_taxonomy_filters()
        self._run_fresh_search()
        self.search_input.setFocus()
        self.search_input.selectAll()

    def open_with_related_query(
        self,
        query: str,
        client: str | None = None,
        open_active_ticket_pane: bool = True,
    ) -> None:
        """Populate filters for related past tickets, select the best match, and optionally open Active Ticket."""
        self._reload_clients()
        self._reload_taxonomy_filters()
        clean_query = (query or "").strip()

        for combo in (self.domain_combo, self.symptom_combo, self.resolution_combo):
            combo.blockSignals(True)
            combo.setCurrentIndex(0)
            combo.blockSignals(False)

        self.client_combo.blockSignals(True)
        if not clean_query and client:
            client_idx = self.client_combo.findData(client)
            self.client_combo.setCurrentIndex(client_idx if client_idx >= 0 else 0)
        else:
            self.client_combo.setCurrentIndex(0)
        self.client_combo.blockSignals(False)

        self.sort_combo.blockSignals(True)
        sort_idx = self.sort_combo.findData("relevance" if clean_query else "date")
        if sort_idx >= 0:
            self.sort_combo.setCurrentIndex(sort_idx)
        self.sort_combo.blockSignals(False)

        self.search_input.blockSignals(True)
        self.search_input.setText(clean_query)
        self.search_input.blockSignals(False)

        self._run_fresh_search()
        if open_active_ticket_pane:
            self.ticket_panel_toggle.setChecked(True)
        if self.results_list.count() > 0:
            self.results_list.setFocus()
        else:
            self.search_input.setFocus()

    def _reload_clients(self) -> None:
        previous_client = self.client_combo.currentData()
        clients = list_history_clients(self._get_conn())

        self.client_combo.blockSignals(True)
        self.client_combo.clear()
        self.client_combo.addItem("All Clients", None)
        for client_name in clients:
            self.client_combo.addItem(client_name, client_name)

        restore_idx = self.client_combo.findData(previous_client)
        self.client_combo.setCurrentIndex(restore_idx if restore_idx >= 0 else 0)
        self.client_combo.blockSignals(False)

    def _reload_taxonomy_filters(self) -> None:
        try:
            nodes = list_taxonomy_nodes(self._get_conn(), active_only=True)
        except sqlite3.Error:
            nodes = []
        self._taxonomy_labels = {str(n["slug"]): str(n["label"]) for n in nodes}

        combos = (
            (self.domain_combo, "All Domains", "domain"),
            (self.symptom_combo, "All Symptoms", "symptom"),
            (self.resolution_combo, "All Resolutions", "resolution"),
        )
        for combo, default_label, axis in combos:
            previous = combo.currentData()
            combo.blockSignals(True)
            combo.clear()
            combo.addItem(default_label, None)
            for node in nodes:
                if node.get("axis") != axis:
                    continue
                label = str(node["label"])
                slug = str(node["slug"])
                combo.addItem(label, slug)
                idx = combo.count() - 1
                combo.setItemData(idx, label, Qt.ItemDataRole.ToolTipRole)
            restore_idx = combo.findData(previous)
            combo.setCurrentIndex(restore_idx if restore_idx >= 0 else 0)
            combo.blockSignals(False)

    def _selected_taxonomy_slugs(self) -> list[str]:
        return [
            slug
            for slug in (
                self.domain_combo.currentData(),
                self.symptom_combo.currentData(),
                self.resolution_combo.currentData(),
            )
            if slug
        ]

    # --- Search & Pagination ---

    def _compute_date_from(self) -> str | None:
        days = self.date_combo.currentData()
        if not days:
            return None
        return (datetime.now() - timedelta(days=int(days))).strftime("%Y-%m-%d")

    def _run_fresh_search(self) -> None:
        self._debounce.stop()
        self._loaded_count = 0
        self.results_list.clear()
        self._clear_preview()
        self._load_next_page()

        if self.results_list.count() > 0:
            self.results_list.setCurrentRow(0)

    def _load_next_page(self) -> None:
        conn = self._get_conn()
        results, total = search_history(
            conn,
            query=self.search_input.text(),
            client=self.client_combo.currentData(),
            date_from=self._compute_date_from(),
            taxonomy_slugs=self._selected_taxonomy_slugs() or None,
            sort_by=self.sort_combo.currentData() or "relevance",
            limit=self._PAGE_SIZE,
            offset=self._loaded_count,
        )

        self._total_count = total
        for res in results:
            item = QListWidgetItem()
            item.setData(_RESULT_ROLE, res)
            self.results_list.addItem(item)

        self._loaded_count += len(results)
        self._update_counters()

    def _update_counters(self) -> None:
        if self._total_count == 0:
            self.count_label.setText("0 matches")
        elif self._loaded_count < self._total_count:
            self.count_label.setText(f"{self._loaded_count} of {self._total_count}")
        else:
            suffix = "match" if self._total_count == 1 else "matches"
            self.count_label.setText(f"{self._total_count} {suffix}")

        remaining = self._total_count - self._loaded_count
        self.load_more_btn.setVisible(remaining > 0)
        if remaining > 0:
            self.load_more_btn.setText(f"Load More ({remaining} remaining)")

    # --- Preview & Accent-Insensitive Match Highlighting ---

    def _on_result_selected(
        self, current: QListWidgetItem | None, _previous: QListWidgetItem | None
    ) -> None:
        if current is None:
            self._clear_preview()
            return

        res: HistorySearchResult | None = current.data(_RESULT_ROLE)
        if res is None:
            self._clear_preview()
            return

        ticket = get_history_ticket(self._get_conn(), res.id)
        if ticket is None:
            self._clear_preview()
            return

        self._current_ticket = ticket

        try:
            tax_nodes = get_ticket_taxonomy(self._get_conn(), res.id)
        except sqlite3.Error:
            tax_nodes = []
        tax_part = (
            "<br>Taxonomy: "
            + " · ".join(f"<b>{html.escape(str(n['label']))}</b>" for n in tax_nodes)
            if tax_nodes
            else ""
        )

        tags_part = f" · Tags: {html.escape(str(self._current_ticket['tags']))}" if self._current_ticket["tags"] else ""
        self.meta_label.setText(
            f"<b>{html.escape(str(self._current_ticket['ticket_number']))}</b> — "
            f"{html.escape(str(self._current_ticket['title']))}<br>"
            f"Client: {html.escape(str(self._current_ticket['client']))} · "
            f"Archived: {html.escape(str(self._current_ticket['archived_at'])[:16])}{tags_part}{tax_part}"
        )

        body_text = str(self._current_ticket["body"])
        self.preview_edit.setPlainText(body_text)
        self._highlight_preview_matches(body_text, self.search_input.text())

        for btn in (self.copy_all_btn, self.copy_body_btn, self.restore_btn, self.clone_btn):
            btn.setEnabled(True)

    def _highlight_preview_matches(self, text: str, raw_query: str) -> None:
        terms = _extract_highlight_terms(raw_query)
        if not text or not terms:
            self.preview_edit.setExtraSelections([])
            return

        norm_text, idx_map = _strip_accents_with_map(text)
        norm_terms = [_strip_accents_with_map(t)[0] for t in terms]
        norm_terms = [t for t in norm_terms if t]
        if not norm_terms:
            self.preview_edit.setExtraSelections([])
            return

        pattern = re.compile("|".join(re.escape(t) for t in norm_terms))

        highlight_fmt = QTextCharFormat()
        highlight_fmt.setBackground(QColor(245, 194, 17, 95))
        highlight_fmt.setForeground(self.preview_edit.palette().text())

        selections: list[QTextEdit.ExtraSelection] = []
        first_match_pos: int | None = None

        for match in pattern.finditer(norm_text):
            orig_start = idx_map[match.start()]
            orig_end = idx_map[match.end() - 1] + 1
            while orig_end < len(text) and unicodedata.category(text[orig_end]) == "Mn":
                orig_end += 1

            cursor = self.preview_edit.textCursor()
            cursor.setPosition(orig_start)
            cursor.setPosition(orig_end, QTextCursor.MoveMode.KeepAnchor)

            sel = QTextEdit.ExtraSelection()
            sel.cursor = cursor
            sel.format = highlight_fmt
            selections.append(sel)

            if first_match_pos is None:
                first_match_pos = orig_start

        self.preview_edit.setExtraSelections(selections)

        if first_match_pos is not None:
            cursor = self.preview_edit.textCursor()
            cursor.setPosition(first_match_pos)
            self.preview_edit.setTextCursor(cursor)
            self.preview_edit.centerCursor()

    def _clear_preview(self) -> None:
        self._current_ticket = None
        self.meta_label.setText("Select an archived ticket to inspect its notes.")
        self.preview_edit.clear()
        self.preview_edit.setExtraSelections([])
        for btn in (self.copy_all_btn, self.copy_body_btn, self.restore_btn, self.clone_btn):
            btn.setEnabled(False)

    # --- Actions ---

    def _flash_feedback(self, message: str) -> None:
        self.feedback_label.setText(message)
        QTimer.singleShot(1800, lambda: self.feedback_label.setText(""))

    def _copy_all(self) -> None:
        if not self._current_ticket:
            return
        t = self._current_ticket
        text = (
            f"Ticket: {t['ticket_number']}\n"
            f"Client: {t['client']}\n"
            f"Title: {t['title']}\n"
            f"Archived: {t['archived_at']}\n\n"
            f"{t['body']}"
        )
        QGuiApplication.clipboard().setText(text)
        self._flash_feedback("Copied full ticket")

    def _copy_body(self) -> None:
        if not self._current_ticket:
            return
        QGuiApplication.clipboard().setText(str(self._current_ticket["body"]))
        self._flash_feedback("Copied body")

    def _emit_restore(self) -> None:
        if self._current_ticket:
            self.restore_requested.emit(int(self._current_ticket["id"]))

    def _emit_clone(self) -> None:
        if self._current_ticket:
            self.clone_requested.emit(int(self._current_ticket["id"]))

    def _handle_escape(self) -> None:
        if self.search_input.hasFocus() and self.search_input.text():
            self.search_input.clear()
        else:
            self.back_requested.emit()

    # --- Active Ticket Right Sidebar (Zero-Lag Shared Document) ---

    def _ensure_ticket_editor(self) -> TechPadEditor:
        """Lazily instantiates ticket_editor when History Search or its Active Ticket pane is opened."""
        if self.ticket_editor is None:
            self.ticket_editor = TechPadEditor(
                scratchpad_id=0,
                image_service=self.image_service,
                parent=self.ticket_sidebar,
            )
            self.ticket_editor.setPlaceholderText("Ticket notes...")
            self.ticket_editor.currentCharFormatChanged.connect(self._update_format_states)
            self.ticket_editor.content_modified.connect(self._on_editor_content_modified)
            self._sidebar_layout.addWidget(self.ticket_editor, 1)
        return self.ticket_editor

    def _ensure_sidebar_splitter_width(self) -> None:
        sizes = self.splitter.sizes()
        if len(sizes) == 3 and sizes[2] < 240:
            total = max(900, sum(sizes))
            side_w = min(320, max(240, total // 3))
            rem = max(200, total - side_w)
            left_w = max(240, int(rem * 0.42))
            self.splitter.setSizes([left_w, max(200, rem - left_w), side_w])

    def _on_ticket_panel_toggled(self, visible: bool) -> None:
        """Slides the Active Ticket right pane open/closed."""
        if visible:
            self._ensure_ticket_editor()
            self._ticket_transition.show_panel(
                target_width=300,
                on_finished=self._ensure_sidebar_splitter_width,
            )
            self._ensure_sidebar_splitter_width()
        else:
            self._ticket_transition.hide_panel()

    def set_active_ticket(
        self,
        editor: TechPadEditor | None,
        ticket_data: dict | None = None,
        scratchpad_service=None,
        image_service=None,
        stopwatch=None,
    ) -> None:
        """Binds the active ticket's shared QTextDocument and stopwatch into the right sidebar."""
        if scratchpad_service is not None:
            self.scratchpad_service = scratchpad_service
        if image_service is not None:
            self.image_service = image_service

        ticket_editor = self._ensure_ticket_editor()
        if image_service is not None:
            ticket_editor.image_service = image_service

        if self._stopwatch is not None:
            try:
                self._stopwatch.time_updated.disconnect(self._on_stopwatch_tick)
            except (RuntimeError, TypeError):
                pass
        self._stopwatch = stopwatch
        if self._stopwatch is not None:
            self._stopwatch.time_updated.connect(self._on_stopwatch_tick)
            self._update_stopwatch_ui()

        self._active_editor = editor
        if editor is None:
            self.lbl_ticket_id.setText("No Ticket")
            self.lbl_ticket_client.setText("Client: N/A")
            self.lbl_ticket_subject.setText("Open a ticket in T-Notes to view and edit notes.")
            self.btn_template.setEnabled(False)
            self.btn_copy_note.setEnabled(False)
            self.btn_more.setEnabled(False)
            ticket_editor.setEnabled(False)
            ticket_editor.setPlainText("")
            return

        self.btn_template.setEnabled(True)
        self.btn_copy_note.setEnabled(True)
        self.btn_more.setEnabled(True)
        ticket_editor.setEnabled(True)
        ticket_editor.scratchpad_id = editor.scratchpad_id
        ticket_editor.in_memory_images = editor.in_memory_images
        ticket_editor.setDocument(editor.document())

        ticket = ticket_data or (self.scratchpad_service.get_ticket(editor.scratchpad_id) if self.scratchpad_service else None) or {}
        t_num = ticket.get("ticket_number", "")
        self._current_ticket_number = t_num
        client = ticket.get("client_name", "") or "N/A"
        title = ticket.get("title", "") or "N/A"

        self.lbl_ticket_id.setText(f"#{t_num}" if t_num else "Ticket")
        self.lbl_ticket_client.setText(f"Client: {client}")
        self.lbl_ticket_subject.setText(f"Subject: {title}")

    def _on_stopwatch_tick(self, _sid: int, _elapsed_seconds: int) -> None:
        self._update_stopwatch_ui()

    def _update_stopwatch_ui(self) -> None:
        if self._stopwatch:
            self.lbl_sidebar_stopwatch.setText(self._stopwatch.lbl_time.text())
            self.btn_sidebar_stopwatch_toggle.setText(self._stopwatch.btn_toggle.text())

    def _toggle_stopwatch(self) -> None:
        if self._stopwatch:
            self._stopwatch.toggle_timer()
            self._update_stopwatch_ui()

    def _reset_stopwatch(self) -> None:
        if self._stopwatch:
            self._stopwatch.reset_timer()
            self._update_stopwatch_ui()

    def _on_editor_content_modified(self, scratchpad_id: int) -> None:
        self.note_modified.emit(scratchpad_id)

    def _update_format_states(self, fmt: QTextCharFormat) -> None:
        self.act_bold.setChecked(fmt.fontWeight() == QFont.Bold)
        self.act_italic.setChecked(fmt.fontItalic())
        self.act_underline.setChecked(fmt.fontUnderline())

    @staticmethod
    def _apply_char_format(ed: TechPadEditor, cursor: QTextCursor, fmt: QTextCharFormat) -> None:
        if cursor.hasSelection():
            cursor.mergeCharFormat(fmt)
            ed.setTextCursor(cursor)
        ed.mergeCurrentCharFormat(fmt)
        ed.setFocus()

    def _toggle_bold(self) -> None:
        ed = self._ensure_ticket_editor()
        cursor = ed.textCursor()
        fmt = QTextCharFormat()
        fmt.setFontWeight(QFont.Bold if self.act_bold.isChecked() else QFont.Normal)
        self._apply_char_format(ed, cursor, fmt)

    def _toggle_italic(self) -> None:
        ed = self._ensure_ticket_editor()
        cursor = ed.textCursor()
        fmt = QTextCharFormat()
        fmt.setFontItalic(self.act_italic.isChecked())
        self._apply_char_format(ed, cursor, fmt)

    def _toggle_underline(self) -> None:
        ed = self._ensure_ticket_editor()
        cursor = ed.textCursor()
        fmt = QTextCharFormat()
        fmt.setFontUnderline(self.act_underline.isChecked())
        self._apply_char_format(ed, cursor, fmt)

    def _pick_text_color(self) -> None:
        ed = self._ensure_ticket_editor()
        cursor = ed.textCursor()
        color = QColorDialog.getColor(Qt.white, self, "Select Text Color")
        if color.isValid():
            fmt = QTextCharFormat()
            fmt.setForeground(color)
            self._apply_char_format(ed, cursor, fmt)
        else:
            ed.setFocus()

    def _pick_highlight_color(self) -> None:
        ed = self._ensure_ticket_editor()
        cursor = ed.textCursor()
        color = QColorDialog.getColor(QColor("#264f78"), self, "Select Highlight Color")
        if color.isValid():
            fmt = QTextCharFormat()
            fmt.setBackground(color)
            self._apply_char_format(ed, cursor, fmt)
        else:
            ed.setFocus()

    def _insert_code_block(self) -> None:
        ed = self._ensure_ticket_editor()
        cursor = ed.textCursor()
        selected = cursor.selectedText()
        content = selected if selected else "# CLI / PowerShell Output"
        snippet = (
            '<div style="background-color: #252526; border: 1px solid #3c3c3c; '
            'border-radius: 4px; padding: 6px; font-family: Consolas, monospace; color: #9cdcfe;">'
            f'<code>{content}</code></div><br>'
        )
        cursor.insertHtml(snippet)
        ed.setFocus()

    def _insert_badge(self, tag_key: str) -> None:
        ed = self._ensure_ticket_editor()
        info = LOG_BADGES.get(tag_key)
        if not info:
            return
        badge_html = (
            f'&nbsp;<span style="background-color: {info["bg_color"]}; color: {info["text_color"]}; '
            f'border: 1px solid {info["border_color"]}; border-radius: 3px; padding: 2px 6px; '
            f'font-weight: bold; font-size: 11px;">{info["label"]}</span>&nbsp;'
        )
        ed.textCursor().insertHtml(badge_html)
        ed.setFocus()

    def _insert_checklist(self) -> None:
        ed = self._ensure_ticket_editor()
        ed.insert_checklist_item()
        ed.setFocus()

    def _insert_timestamp(self) -> None:
        ed = self._ensure_ticket_editor()
        now_str = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
        ed.textCursor().insertHtml(f"<strong>[{now_str}]</strong> ")
        ed.setFocus()

    def _insert_image(self) -> None:
        ed = self._ensure_ticket_editor()
        file_path, _ = QFileDialog.getOpenFileName(
            self,
            "Select Screenshot or Image",
            "",
            "Images (*.png *.jpg *.jpeg *.bmp *.webp *.gif)",
        )
        if file_path:
            with open(file_path, "rb") as f:
                data = f.read()
            ed.insert_embedded_image(data)
        ed.setFocus()

    def _insert_template(self, skeleton_name: str) -> None:
        ed = self._ensure_ticket_editor()
        if self.scratchpad_service:
            snippet = self.scratchpad_service.get_skeleton_html(skeleton_name)
        else:
            snippet = TICKET_SKELETONS.get(skeleton_name, "")
        if snippet:
            if hasattr(ed, "insert_template_html"):
                ed.insert_template_html(snippet)
            else:
                ed.textCursor().insertHtml(snippet)
        ed.setFocus()

    def update_templates_menu(self, custom_templates: list | None = None) -> None:
        """Updates the Active Ticket sidebar template menu with built-in and custom templates."""
        if not hasattr(self, "btn_template"):
            return
        template_menu = QMenu(self.btn_template)
        for name in TICKET_SKELETONS.keys():
            act = template_menu.addAction(name)
            act.triggered.connect(lambda checked=False, n=name: self._insert_template(n))
        if custom_templates:
            template_menu.addSeparator()
            for item in custom_templates:
                title = item.get("title", "") if isinstance(item, dict) else str(item)
                if title:
                    act = template_menu.addAction(title)
                    act.triggered.connect(lambda checked=False, t=title: self._insert_template(t))
        self.btn_template.setMenu(template_menu)

    def _copy_formatted_note(self) -> None:
        ed = self._ensure_ticket_editor()
        if self._active_editor:
            self.save_requested.emit(ed.scratchpad_id)
            ed.copy_formatted_note()
            t_label = f"#{self._current_ticket_number}".strip() if self._current_ticket_number else ""
            msg = f"✓ Copied formatted note ({t_label}) with rich text & images to clipboard!" if t_label else "✓ Copied formatted note with rich text & images to clipboard!"
            self.status_message_requested.emit(msg, 3500)

    def _copy_clean_note(self) -> None:
        ed = self._ensure_ticket_editor()
        if self._active_editor:
            self.save_requested.emit(ed.scratchpad_id)
            if self.scratchpad_service:
                clean_text = self.scratchpad_service.export_as_plain_ticket_note(ed.scratchpad_id)
            else:
                clean_text = ed.toPlainText()
            QApplication.clipboard().setText(clean_text)
            t_label = f"#{self._current_ticket_number}".strip() if self._current_ticket_number else ""
            msg = f"✓ Copied clean note ({t_label}) for ticketing system to clipboard!" if t_label else "✓ Copied clean note for ticketing system to clipboard!"
            self.status_message_requested.emit(msg, 3500)

    def _export_active_ticket_file(self) -> None:
        ed = self._ensure_ticket_editor()
        if self._active_editor:
            self.save_requested.emit(ed.scratchpad_id)
            clean_text = ed.toPlainText().replace("\uFFFC", "")
            clean_text = re.sub(r"\n{3,}", "\n\n", clean_text).strip()
            if self.scratchpad_service:
                try:
                    file_path, filename = self.scratchpad_service.export_ticket_to_file(
                        scratchpad_id=ed.scratchpad_id,
                        text_content=clean_text,
                    )
                    t_label = f"#{self._current_ticket_number}".strip() if self._current_ticket_number else ""
                    rel_path = f"{file_path.parent.name}/{filename}"
                    msg = f"✓ Exported note ({t_label}) to T-Notes/{rel_path}" if t_label else f"✓ Exported note to T-Notes/{rel_path}"
                    self.status_message_requested.emit(msg, 4000)
                except Exception as e:
                    self.status_message_requested.emit(f"Export Failed: {e}", 4000)
