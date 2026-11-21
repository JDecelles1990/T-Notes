"""Tests for SQLite FTS5 history migration, sanitizer, ranking, triggers, and repository integration."""

import sqlite3
import pytest

from src.database.history_fts import (
    FTS_MIGRATION_VERSION,
    HistorySearchResult,
    list_history_clients,
    migrate_history_fts,
    sanitize_fts5_query,
    search_history,
)
from src.database.connection import DatabaseManager
from src.database.migrations import init_database
from src.repositories.scratchpad_repository import ScratchpadRepository
from src.services.image_service import ImageService
from src.repositories.image_repository import ImageRepository
from src.services.scratchpad_service import ScratchpadService


@pytest.fixture
def db() -> sqlite3.Connection:
    conn = sqlite3.connect(":memory:")
    conn.execute(
        """
        CREATE TABLE ticket_history (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            ticket_number TEXT NOT NULL,
            client TEXT NOT NULL,
            title TEXT NOT NULL,
            tags TEXT DEFAULT '',
            body TEXT DEFAULT '',
            archived_at TEXT NOT NULL
        )
        """
    )
    # Seed a pre-existing row to verify backfill on migration
    conn.execute(
        """
        INSERT INTO ticket_history (ticket_number, client, title, tags, body, archived_at)
        VALUES (?, ?, ?, ?, ?, ?)
        """,
        (
            "INC-40219",
            "Contoso",
            "Problème réseau VPN",
            "vpn, forticlient",
            "Reset adapter for <jdoe@contoso.com>. Error:0x80070005 resolved.",
            "2026-10-15T14:30:00",
        ),
    )
    conn.commit()
    assert migrate_history_fts(conn) is True
    assert migrate_history_fts(conn) is False  # Idempotent second run
    return conn


def test_sanitizer_edge_cases():
    assert sanitize_fts5_query("") is None
    assert sanitize_fts5_query('   --- ::: "" ') is None
    assert sanitize_fts5_query("INC-40219") == '"INC-40219"*'
    assert sanitize_fts5_query('"blue screen" dell') == '"blue screen" "dell"*'
    assert sanitize_fts5_query('user not "unclosed') == '"user"* "not"* "unclosed"*'


def test_backfill_hyphen_diacritics_and_html_escaping(db: sqlite3.Connection):
    # Hyphenated ticket number
    results, total = search_history(db, "INC-402")
    assert total == 1
    assert results[0].ticket_number == "INC-40219"

    # Diacritic-insensitive search ("reseau" matches "réseau")
    results, total = search_history(db, "reseau")
    assert total == 1

    # Angle brackets in email/body are escaped while <b> highlight stays intact
    results, _ = search_history(db, "0x80070005")
    assert "&lt;jdoe@contoso.com&gt;" in results[0].snippet_html
    assert "<b>0x80070005</b>" in results[0].snippet_html


def test_triggers_sync_insert_update_delete(db: sqlite3.Connection):
    # INSERT trigger
    cur = db.execute(
        """
        INSERT INTO ticket_history (ticket_number, client, title, tags, body, archived_at)
        VALUES ('INC-55001', 'Fabrikam', 'Outlook OST corrupt', 'm365', 'Rebuilt OST profile.', '2026-11-01T09:00:00')
        """
    )
    row_id = cur.lastrowid
    db.commit()

    results, total = search_history(db, "outl ost")
    assert total == 1 and results[0].id == row_id

    # UPDATE trigger
    db.execute(
        "UPDATE ticket_history SET body = 'Migrated to New Outlook cache.' WHERE id = ?",
        (row_id,),
    )
    db.commit()
    assert search_history(db, "rebuilt")[1] == 0
    assert search_history(db, "migrated")[1] == 1

    # DELETE trigger
    db.execute("DELETE FROM ticket_history WHERE id = ?", (row_id,))
    db.commit()
    assert search_history(db, "INC-55001")[1] == 0


def test_scratchpads_migration_ranking_filters_and_service_wrapper(tmp_path):
    """Validates PRAGMA user_version=2, archived-only filtering, BM25 ranking, date/client filters, and HTML cleaning."""
    db_mgr = DatabaseManager(tmp_path / "tnotes_hist.db")
    init_database(db_mgr)
    conn = db_mgr.get_connection()

    try:
        assert conn.execute("PRAGMA user_version").fetchone()[0] == FTS_MIGRATION_VERSION
        # Idempotent second call must return False
        assert migrate_history_fts(conn) is False

        repo = ScratchpadRepository(db_mgr)
        svc = ScratchpadService(repo, ImageService(ImageRepository(db_mgr)))

        # Active ticket must NEVER appear in search_history results
        active_id = repo.create(
            ticket_number="INC-99999",
            client_name="Contoso",
            title="Active Outlook OST issue",
            content_html="<p>Active ticket troubleshooting outlook ost</p>",
            status="active",
        )
        assert active_id > 0

        # Ticket A: older archived ticket where "outlook" is in body only
        id_body = repo.create(
            ticket_number="INC-10001",
            client_name="Contoso",
            title="Workstation cleanup",
            content_html="<html><head><style>p{color:#fff;}</style></head><body><p>Cleared Outlook cache for &lt;user@contoso.com&gt; and &lt;admin@contoso.com&gt;.</p></body></html>",
            status="active",
        )
        repo.archive(id_body, archived_at="2026-11-01 10:00:00")

        # Ticket B: newer archived ticket where "outlook" is in title (higher bm25 weight = 4.0)
        id_title = repo.create(
            ticket_number="INC-10002",
            client_name="Fabrikam",
            title="Outlook OST corruption",
            content_html="<p>Rebuilt profile for <bob@fabrikam.com>.</p>",
            status="active",
        )
        repo.archive(id_title, archived_at="2026-11-10 15:30:00")

        # 1. Archived-only filter & relevance sorting (title weight > body weight)
        results, total = svc.search_history("outlook")
        assert total == 2
        assert all(isinstance(r, HistorySearchResult) for r in results)
        assert [r.id for r in results] == [id_title, id_body]
        assert results[0].rank is not None and results[0].rank <= results[1].rank
        assert "&lt;bob@fabrikam.com&gt;" in results[0].snippet_html or "<b>Outlook</b>" in results[0].snippet_html

        # 2. Client filter
        contoso_res, contoso_total = svc.search_history("outlook", client="Contoso")
        assert contoso_total == 1
        assert contoso_res[0].id == id_body
        assert "<style>" not in contoso_res[0].snippet_html

        # 3. Date range filter (YYYY-MM-DD inclusive upper bound)
        date_res, date_total = svc.search_history("", date_from="2026-11-05", date_to="2026-11-10")
        assert date_total == 1
        assert date_res[0].id == id_title

        # 4. Empty query strips Qt HTML header boilerplate instead of leaking <head><style>
        empty_res, empty_total = svc.search_history("")
        assert empty_total == 2
        assert [r.id for r in empty_res] == [id_title, id_body]
        assert "<style>" not in empty_res[1].snippet_html
        assert "Cleared Outlook cache" in empty_res[1].snippet_html

        # 5. Pagination limit & offset
        page1, p_total = svc.search_history("", limit=1, offset=0)
        page2, _ = svc.search_history("", limit=1, offset=1)
        assert p_total == 2
        assert [page1[0].id, page2[0].id] == [id_title, id_body]

        # 6. Distinct client list only includes archived clients
        assert svc.list_archived_clients() == ["Contoso", "Fabrikam"]
    finally:
        db_mgr.close()


def test_history_search_page_filters_highlighting_keyboard_and_copy(qapp, db: sqlite3.Connection, monkeypatch):
    """Validates HistorySearchPage filtering, accent-insensitive preview highlights, keyboard nav, and copy actions."""
    from PySide6.QtCore import Qt
    from PySide6.QtGui import QGuiApplication
    from PySide6.QtTest import QTest
    from src.ui.components.history_search_page import HistorySearchPage

    copied_texts: list[str] = []
    monkeypatch.setattr(QGuiApplication.clipboard(), "setText", copied_texts.append)

    # Add a second row so client dropdown and date filter have multiple entries
    db.execute(
        """
        INSERT INTO ticket_history (ticket_number, client, title, tags, body, archived_at)
        VALUES ('INC-55001', 'Fabrikam', 'Outlook OST', 'm365', 'Rebuilt OST profile.', '2026-11-18T11:00:00')
        """
    )
    db.commit()

    page = HistorySearchPage(get_conn=lambda: db)
    page.resize(1000, 620)
    page.show()
    qapp.processEvents()
    try:
        page.refresh_and_focus()
        assert page.results_list.count() == 2
        assert page.count_label.text() == "2 matches"
        assert page.client_combo.count() == 3  # All Clients, Contoso, Fabrikam

        # Search without diacritics matches "réseau" inside title/body and highlights match
        page.search_input.setText("reseau")
        page._run_fresh_search()
        assert page.results_list.count() == 1
        assert "INC-40219" in page.meta_label.text()
        assert page.copy_all_btn.isEnabled()

        # Copy Body & Copy All
        page.copy_body_btn.click()
        assert len(copied_texts) == 1
        assert "Error:0x80070005" in copied_texts[-1]
        page.copy_all_btn.click()
        assert len(copied_texts) == 2
        clip_all = copied_texts[-1]
        assert "Ticket: INC-40219" in clip_all
        assert "Client: Contoso" in clip_all

        # Highlighting works even when accent-stripped term matches accented text in body
        page._highlight_preview_matches("Panne réseau détectée", "reseau")
        assert len(page.preview_edit.extraSelections()) == 1

        # Down arrow moves focus from search_input into results_list
        page.search_input.setFocus()
        qapp.processEvents()
        QTest.keyClick(page.search_input, Qt.Key.Key_Down)
        assert page.results_list.hasFocus()
        assert page.results_list.currentRow() == 0

        # Escape clears non-empty focused search box first, second Esc emits back_requested
        back_emitted = []
        page.back_requested.connect(lambda: back_emitted.append(True))
        page.search_input.setFocus()
        qapp.processEvents()
        page._handle_escape()
        assert page.search_input.text() == ""
        assert back_emitted == []
        page._handle_escape()
        assert back_emitted == [True]
    finally:
        page.close()
        page.deleteLater()


def test_main_window_bottom_history_button_and_restore_clone(qapp, tmp_path):
    """Top 🕰️ button still toggles HistoryDrawer while bottom History button & Ctrl+Shift+F toggle HistorySearchPage."""
    from PySide6.QtWidgets import QApplication
    from src.repositories.image_repository import ImageRepository
    from src.repositories.session_repository import SessionRepository
    from src.repositories.template_repository import TemplateRepository
    from src.services.session_service import SessionService
    from src.ui.main_window import TechPadMainWindow

    db_mgr = DatabaseManager(tmp_path / "ui_hist.db")
    init_database(db_mgr)
    scratch_repo = ScratchpadRepository(db_mgr)
    img_repo = ImageRepository(db_mgr)
    img_svc = ImageService(img_repo)
    sp_svc = ScratchpadService(scratch_repo, img_svc, TemplateRepository(db_mgr))
    sess_svc = SessionService(SessionRepository(db_mgr), sp_svc)

    # Create an archived ticket with an embedded image so clone carries images too
    arch = sp_svc.create_ticket(
        ticket_number="INC-7001",
        client_name="Northwind",
        title="MFA Prompt Loop",
        content_html='<p>Cleared token cache and <img src="image://local/snap.jpg"> fixed.</p>',
    )
    img_repo.save_image(arch["id"], "snap.jpg", b"\xff\xd8\xff\xe0CLONEIMG")
    sp_svc.archive_ticket(arch["id"])

    win = TechPadMainWindow(sp_svc, img_svc, sess_svc)
    win.show()
    qapp.processEvents()
    try:
        # 1. Notes bottom bar shows Split and hides History Active Ticket button initially
        assert win.btn_toggle_split.isVisible() is True
        assert win.btn_history_active_ticket.isVisible() is False

        # 2. Top 🕰️ button still toggles right-side HistoryDrawer intact
        was_hidden = win.history_drawer.isHidden()
        win.toolbar.btn_history.click()
        assert win.history_drawer.isHidden() != was_hidden
        if win.history_drawer.isHidden():
            win.toolbar.btn_history.click()
        assert win.history_drawer.isVisible()

        # 3. Bottom History button switches main_stack to HistorySearchPage, transforms to 'T-Notes', swaps Split -> Active Ticket, & tucks drawer
        assert win.bottom_history_btn.text() == "🕰️ History"
        win.bottom_history_btn.click()
        qapp.processEvents()
        assert win.is_history_search_page is True
        assert win.bottom_history_btn.isChecked() is True
        assert win.bottom_history_btn.text() == "T-Notes"
        assert win.btn_toggle_split.isVisible() is False
        assert win.btn_history_active_ticket.isVisible() is True
        assert win.btn_history_active_ticket.text() == "Active Ticket"
        assert win.history_search_page.ticket_sidebar.isHidden() is True
        assert win.history_drawer.isHidden() is True
        assert win.history_search_page.results_list.count() == 1
        assert "MFA Prompt Loop" in win.history_search_page.meta_label.text()

        # 4. Clicking bottom Active Ticket opens the live shared Active Ticket right pane
        active_ed = win.tab_widget.get_current_editor()
        assert active_ed is not None
        win.btn_history_active_ticket.click()
        qapp.processEvents()
        assert win.btn_history_active_ticket.isChecked() is True
        assert win.history_search_page.ticket_sidebar.isVisible() is True
        assert win.history_search_page.ticket_editor is not None
        assert win.history_search_page.ticket_editor.document() is active_ed.document()
        win.history_search_page.ticket_editor.textCursor().insertText("Live sidebar edit from History")
        assert "Live sidebar edit from History" in active_ed.toPlainText()

        # Clicking bottom Active Ticket again closes the right pane cleanly
        win.btn_history_active_ticket.click()
        qapp.processEvents()
        assert win.btn_history_active_ticket.isChecked() is False
        assert win.history_search_page.ticket_sidebar.isHidden() is True

        # 5. Clicking bottom T-Notes (History) button again returns to workspace, restores '🕰️ History', swaps Active Ticket -> Split, & restores drawer
        win.bottom_history_btn.click()
        qapp.processEvents()
        assert win.is_history_search_page is False
        assert win.bottom_history_btn.isChecked() is False
        assert win.bottom_history_btn.text() == "🕰️ History"
        assert win.btn_toggle_split.isVisible() is True
        assert win.btn_history_active_ticket.isVisible() is False
        assert win.history_drawer.isVisible() is True

        # 4. Clone to New creates a fresh active ticket (preserving image) & closes search page
        win.open_history_search_page()
        assert win.is_history_search_page is True
        tabs_before = win.tab_widget.count()
        win.clone_ticket_from_history(arch["id"])
        qapp.processEvents()
        assert win.is_history_search_page is False
        assert win.tab_widget.count() == tabs_before + 1
        cloned_ed = win.tab_widget.get_current_editor()
        assert cloned_ed is not None
        assert cloned_ed.scratchpad_id != arch["id"]
        assert img_repo.get_image(cloned_ed.scratchpad_id, "snap.jpg") == b"\xff\xd8\xff\xe0CLONEIMG"

        # 5. Restore to Active re-opens original archived ticket
        win.open_history_search_page()
        tabs_mid = win.tab_widget.count()
        win.restore_ticket_from_history(arch["id"])
        qapp.processEvents()
        assert win.is_history_search_page is False
        assert win.tab_widget.count() == tabs_mid + 1
        assert win.tab_widget.get_current_editor().scratchpad_id == arch["id"]
    finally:
        win.quit_application()
        QApplication.instance().removeEventFilter(win)
        win.deleteLater()
        db_mgr.close()


def test_history_active_ticket_text_color_and_highlight_on_selection(qapp, tmp_path, monkeypatch):
    """Highlighting text in History's Active Ticket pane and changing text/highlight color applies to selection."""
    from PySide6.QtGui import QColor, QTextCursor
    from PySide6.QtWidgets import QApplication, QColorDialog
    from src.repositories.image_repository import ImageRepository
    from src.repositories.session_repository import SessionRepository
    from src.repositories.template_repository import TemplateRepository
    from src.services.session_service import SessionService
    from src.ui.main_window import TechPadMainWindow

    db_mgr = DatabaseManager(tmp_path / "ui_hist_color.db")
    init_database(db_mgr)
    scratch_repo = ScratchpadRepository(db_mgr)
    img_repo = ImageRepository(db_mgr)
    img_svc = ImageService(img_repo)
    sp_svc = ScratchpadService(scratch_repo, img_svc, TemplateRepository(db_mgr))
    sess_svc = SessionService(SessionRepository(db_mgr), sp_svc)

    win = TechPadMainWindow(sp_svc, img_svc, sess_svc)
    win.show()
    qapp.processEvents()
    try:
        active_ed = win.tab_widget.get_current_editor()
        assert active_ed is not None
        active_ed.setPlainText("Alpha Beta Gamma")

        # Enter History module and open the Active Ticket right pane
        win.bottom_history_btn.click()
        qapp.processEvents()
        win.btn_history_active_ticket.click()
        qapp.processEvents()

        hist_ed = win.history_search_page.ticket_editor
        assert hist_ed is not None
        assert win.toolbar._current_editor is hist_ed

        # 1. Select "Beta" in History Active Ticket pane and change text & highlight color via top toolbar
        cursor = hist_ed.textCursor()
        cursor.setPosition(6)
        cursor.setPosition(10, QTextCursor.KeepAnchor)
        hist_ed.setTextCursor(cursor)
        assert hist_ed.textCursor().selectedText() == "Beta"

        monkeypatch.setattr(QColorDialog, "getColor", staticmethod(lambda *args, **kwargs: QColor("#ef4444")))
        win.toolbar.act_color.trigger()
        qapp.processEvents()

        monkeypatch.setattr(QColorDialog, "getColor", staticmethod(lambda *args, **kwargs: QColor("#facc15")))
        win.toolbar.act_highlight.trigger()
        qapp.processEvents()

        check_cur = QTextCursor(active_ed.document())
        check_cur.setPosition(8)
        fmt = check_cur.charFormat()
        assert fmt.foreground().color().name() == "#ef4444"
        assert fmt.background().color().name() == "#facc15"

        # 2. Select "Gamma" and change colors via History Active Ticket sidebar '...' menu actions
        cursor2 = hist_ed.textCursor()
        cursor2.setPosition(11)
        cursor2.setPosition(16, QTextCursor.KeepAnchor)
        hist_ed.setTextCursor(cursor2)
        assert hist_ed.textCursor().selectedText() == "Gamma"

        monkeypatch.setattr(QColorDialog, "getColor", staticmethod(lambda *args, **kwargs: QColor("#38bdf8")))
        win.history_search_page.act_color.trigger()
        qapp.processEvents()

        monkeypatch.setattr(QColorDialog, "getColor", staticmethod(lambda *args, **kwargs: QColor("#1e293b")))
        win.history_search_page.act_highlight.trigger()
        qapp.processEvents()

        check_cur2 = QTextCursor(active_ed.document())
        check_cur2.setPosition(13)
        fmt2 = check_cur2.charFormat()
        assert fmt2.foreground().color().name() == "#38bdf8"
        assert fmt2.background().color().name() == "#1e293b"

        # 3. Returning to active workspace rebinds toolbar back to tab editor
        win.close_history_search_page()
        qapp.processEvents()
        assert win.toolbar._current_editor is active_ed
    finally:
        win.quit_application()
        QApplication.instance().removeEventFilter(win)
        win.deleteLater()
        db_mgr.close()
