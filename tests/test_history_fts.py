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


def test_related_history_keyword_extraction_or_query_and_pill_navigation(qapp, tmp_path):
    """Verifies OR query support, hybrid keyword extraction, client boost, and '💡 N Related' pill workflow."""
    from PySide6.QtWidgets import QApplication
    from src.database.history_fts import extract_related_keywords, find_related_history
    from src.repositories.image_repository import ImageRepository
    from src.repositories.session_repository import SessionRepository
    from src.repositories.template_repository import TemplateRepository
    from src.services.session_service import SessionService
    from src.ui.main_window import TechPadMainWindow

    assert sanitize_fts5_query("vpn OR 0x80070005") == '"vpn"* OR "0x80070005"*'
    kw = extract_related_keywords(
        title="FortiClient VPN issue",
        note_text="[2026-11-21 10:00:00] User cannot connect error 0x80070005 after KB5034441",
    )
    assert "FortiClient" in kw and "0x80070005" in kw

    db_mgr = DatabaseManager(tmp_path / "ui_related.db")
    init_database(db_mgr)
    scratch_repo = ScratchpadRepository(db_mgr)
    img_repo = ImageRepository(db_mgr)
    img_svc = ImageService(img_repo)
    sp_svc = ScratchpadService(scratch_repo, img_svc, TemplateRepository(db_mgr))
    sess_svc = SessionService(SessionRepository(db_mgr), sp_svc)

    t_other = sp_svc.create_ticket(
        ticket_number="INC-8100",
        client_name="Fabrikam",
        title="FortiClient 0x80070005 Fix",
        content_html="<p>Cleared credential manager cache for 0x80070005.</p>",
    )
    sp_svc.archive_ticket(t_other["id"])

    t_same = sp_svc.create_ticket(
        ticket_number="INC-8200",
        client_name="Contoso",
        title="VPN Tunnel Reset",
        content_html="<p>Resolved 0x80070005 via miniport reinstall.</p>",
    )
    sp_svc.archive_ticket(t_same["id"])

    conn = db_mgr.get_connection()
    rel_results, rel_total, rel_query = find_related_history(
        conn,
        title="Unable to start tunnel",
        note_text="Getting error 0x80070005 when connecting.",
        client="Contoso",
    )
    assert rel_total == 2
    assert "0x80070005" in rel_query
    # Same-client match receives boost over other clients
    assert rel_results[0].id == t_same["id"]

    win = TechPadMainWindow(sp_svc, img_svc, sess_svc)
    win.show()
    qapp.processEvents()
    try:
        # 1. With no matching subject/body keywords or archived client tickets, pill stays hidden
        assert win.btn_related_history.isVisible() is False

        # 2. Type error code in active ticket & save -> '💡 2 Related' pill becomes visible with tooltip preview
        active_ed = win.tab_widget.get_current_editor()
        assert active_ed is not None
        sp_svc.update_metadata(active_ed.scratchpad_id, ticket_number="INC-9001", client_name="Contoso", title="VPN Tunnel Failed")
        active_ed.setPlainText("Hit 0x80070005 after reboot.")
        win.flush_all_saves()
        qapp.processEvents()

        assert win.btn_related_history.isVisible() is True
        assert win.btn_related_history.text() == "💡 2 Related"
        assert "INC-8200" in win.btn_related_history.toolTip()
        assert "Contoso" in win.btn_related_history.toolTip()

        # 3. Clicking '💡 2 Related' opens History Search pre-filtered (All Clients) + auto-opens Active Ticket pane
        win.btn_related_history.click()
        qapp.processEvents()
        assert win.is_history_search_page is True
        assert win.history_search_page.client_combo.currentData() is None
        assert win.history_search_page.results_list.count() == 2
        assert win.history_search_page.results_list.currentRow() == 0
        assert win.history_search_page.ticket_panel_toggle.isChecked() is True
        assert win.history_search_page.ticket_sidebar.isVisible() is True
    finally:
        win.quit_application()
        QApplication.instance().removeEventFilter(win)
        win.deleteLater()
        db_mgr.close()


def test_step1_pre_migration_backup_rollback_triggers_and_sanitizer_torture(tmp_path):
    """Comprehensive Step 1 data-safety test: backup, rollback, trigger sync, and sanitizer torture cases."""
    from src.database.history_fts import FTS_MIGRATION_VERSION, seed_taxonomy_nodes

    # 1. Pre-migration file DB simulation matching old schema before tags/archived_at/taxonomy existed
    db_file = tmp_path / "legacy_upgrade.db"
    raw_conn = sqlite3.connect(str(db_file))
    raw_conn.executescript(
        """
        PRAGMA foreign_keys = ON;
        CREATE TABLE scratchpads (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            ticket_number TEXT NOT NULL,
            client_name TEXT DEFAULT '',
            title TEXT DEFAULT '',
            content_html TEXT DEFAULT '',
            status TEXT DEFAULT 'active',
            tab_order INTEGER DEFAULT 0,
            elapsed_seconds INTEGER DEFAULT 0,
            created_at DATETIME DEFAULT CURRENT_TIMESTAMP,
            updated_at DATETIME DEFAULT '2026-10-01T09:00:00'
        );
        INSERT INTO scratchpads (ticket_number, client_name, title, content_html, status)
        VALUES ('INC-100', 'Contoso', 'Active ticket', '<p>Still in progress</p>', 'active');
        INSERT INTO scratchpads (ticket_number, client_name, title, content_html, status)
        VALUES ('INC-200', 'Fabrikam', 'Compte bloqué C:\\ProgramData\\App', '<p>Error 0x80070005:denied for &lt;jdoe@fabrikam.com&gt;</p>', 'archived');
        PRAGMA user_version = 0;
        """
    )
    raw_conn.close()

    # 2. Simulated failure mid-migration rolls back cleanly and preserves user_version = 0
    fail_conn = sqlite3.connect(str(db_file))
    try:
        def _boom(_c):
            raise RuntimeError("Simulated mid-migration power loss")

        with pytest.raises(RuntimeError, match="Simulated"):
            migrate_history_fts(fail_conn, _test_hook=_boom)
        assert fail_conn.execute("PRAGMA user_version").fetchone()[0] == 0
    finally:
        fail_conn.close()

    # Backup was created before the attempted upgrade
    backups = list(tmp_path.glob("legacy_upgrade.db.*.pre_fts_migration.bak"))
    assert len(backups) == 1
    assert backups[0].stat().st_size > 0

    # 3. Real migration via DatabaseManager + init_database succeeds atomically & backfills archived ticket
    db_mgr = DatabaseManager(db_file)
    init_database(db_mgr)
    conn = db_mgr.get_connection()
    try:
        assert conn.execute("PRAGMA user_version").fetchone()[0] == FTS_MIGRATION_VERSION
        # Second migration run is a safe no-op and creates no duplicate backups
        assert migrate_history_fts(conn) is False
        assert len(list(tmp_path.glob("legacy_upgrade.db.*.pre_fts_migration.bak"))) == 1

        # Backfill indexed pre-existing archived ticket with French diacritics & HTML escape
        res, total = search_history(conn, "bloque")
        assert total == 1
        assert res[0].ticket_number == "INC-200"

        # 4. Sanitizer torture queries never raise sqlite3.OperationalError
        assert sanitize_fts5_query("AND OR NOT") == '"AND"* "OR"* "NOT"*'
        assert sanitize_fts5_query("--- :::") is None
        for torture in (
            "INC-200",
            r"C:\ProgramData\App\log.txt",
            "0x80070005:denied",
            'AND OR NOT "unclosed quote',
            "--- :::",
            "<jdoe@fabrikam.com>",
        ):
            search_history(conn, torture)

        path_hits, path_total = search_history(conn, r"C:\ProgramData\App")
        assert path_total == 1 and path_hits[0].ticket_number == "INC-200"

        colon_hits, colon_total = search_history(conn, "0x80070005:denied")
        assert colon_total == 1
        assert "&lt;jdoe@fabrikam.com&gt;" in colon_hits[0].snippet_html or "0x80070005" in colon_hits[0].snippet_html

        # 5. Lifecycle trigger sync: restore-to-active hides from archive search, re-archive & delete remove FTS traces
        repo = ScratchpadRepository(db_mgr)
        repo.restore(2, 1)
        _, after_restore = search_history(conn, "bloque")
        assert after_restore == 0

        repo.archive(2)
        _, after_rearchive = search_history(conn, "bloque")
        assert after_rearchive == 1

        # Idempotent re-seeding leaves user assignments intact
        repo.assign_ticket_taxonomy(2, ["domain.identity.entra_mfa", "symptom.auth_signin"])
        seed_taxonomy_nodes(conn)
        assigned = repo.get_ticket_taxonomy(2)
        assert {item["slug"] for item in assigned} == {"domain.identity.entra_mfa", "symptom.auth_signin"}

        # Delete ticket permanently -> FTS index & ticket_taxonomy cascade cleanly
        repo.delete_permanently(2)
        _, after_delete = search_history(conn, "bloque")
        assert after_delete == 0
        assert repo.get_ticket_taxonomy(2) == []
    finally:
        db_mgr.close()


def test_step1_taxonomy_faceted_filtering_and_bilingual_suggestions(tmp_path):
    """Validates 3-axis taxonomy hierarchy, filtering, repository/service integration, and FR/EN alias matching."""
    from src.database.history_fts import get_taxonomy_seed_path
    from src.repositories.image_repository import ImageRepository
    from src.repositories.template_repository import TemplateRepository

    assert get_taxonomy_seed_path().is_file()

    db_mgr = DatabaseManager(tmp_path / "tax_test.db")
    init_database(db_mgr)
    sp_svc = ScratchpadService(
        ScratchpadRepository(db_mgr),
        ImageService(ImageRepository(db_mgr)),
        TemplateRepository(db_mgr),
    )
    try:
        # 1. All 3 axes populated with 2-level max domain hierarchy
        domains = sp_svc.list_taxonomy_nodes(axis="domain")
        symptoms = sp_svc.list_taxonomy_nodes(axis="symptom")
        resolutions = sp_svc.list_taxonomy_nodes(axis="resolution")
        assert len(domains) >= 9
        assert len(symptoms) == 7
        assert len(resolutions) == 8

        # 2. Bilingual FR/EN auto-suggestion accuracy
        fr_sug = sp_svc.suggest_taxonomy_for_text(
            title="Boîte partagée Outlook lente / courriel ne part pas",
            body="Reconstruit le fichier OST et vidé le cache.",
        )
        assert fr_sug["domain"][0]["slug"] == "domain.m365.exchange"
        assert fr_sug["symptom"][0]["slug"] == "symptom.mail_flow_sync"
        assert fr_sug["resolution"][0]["slug"] == "resolution.profile_cache_rebuild"

        print_sug = sp_svc.suggest_taxonomy_for_text(
            title="Imprimante ne répond pas — spouleur bloqué",
            body="Redémarré service spooler et réinstallé pilote.",
        )
        assert print_sug["domain"][0]["slug"] == "domain.hardware.printers_peripherals"
        assert print_sug["resolution"][0]["slug"] == "resolution.service_driver_restart"

        # 3. Assign multi-axis taxonomy & filter search_history across domain + symptom & parent domain
        t1 = sp_svc.create_ticket("INC-9101", "Contoso", "Exchange OST rebuild", "<p>Fixed OST</p>")
        sp_svc.archive_ticket(t1["id"])
        sp_svc.assign_ticket_taxonomy(
            t1["id"],
            ["domain.m365.exchange", "symptom.mail_flow_sync", "resolution.profile_cache_rebuild"],
        )

        t2 = sp_svc.create_ticket("INC-9102", "Contoso", "Entra MFA Loop", "<p>Revoked tokens</p>")
        sp_svc.archive_ticket(t2["id"])
        sp_svc.assign_ticket_taxonomy(
            t2["id"],
            ["domain.identity.entra_mfa", "symptom.auth_signin", "resolution.token_mfa_reset"],
        )

        # Exact multi-axis intersection (domain.m365.exchange + symptom.mail_flow_sync)
        hits, total = sp_svc.search_history(
            "",
            taxonomy_slugs=["domain.m365.exchange", "symptom.mail_flow_sync"],
        )
        assert total == 1
        assert hits[0].id == t1["id"]
        assert "domain.m365.exchange" in hits[0].taxonomy_slugs

        # Parent-level domain slug (domain.m365) matches child leaf tickets too
        parent_hits, parent_total = sp_svc.search_history("", taxonomy_slugs=["domain.m365"])
        assert parent_total == 1
        assert parent_hits[0].id == t1["id"]
    finally:
        db_mgr.close()


def test_step2_taxonomy_filters_delegate_badges_and_preview_header(qapp, tmp_path):
    """Validates Step 2 3-axis taxonomy dropdown filtering, delegate card badges, and preview metadata header."""
    from PySide6.QtCore import Qt
    from PySide6.QtWidgets import QStyleOptionViewItem
    from src.repositories.image_repository import ImageRepository
    from src.repositories.template_repository import TemplateRepository
    from src.ui.components.history_search_page import HistorySearchPage

    db_mgr = DatabaseManager(tmp_path / "step2_tax_ui.db")
    init_database(db_mgr)
    sp_svc = ScratchpadService(
        ScratchpadRepository(db_mgr),
        ImageService(ImageRepository(db_mgr)),
        TemplateRepository(db_mgr),
    )

    t1 = sp_svc.create_ticket(
        ticket_number="INC-9301",
        client_name="Contoso",
        title="Exchange shared mailbox OST failure",
        content_html="<p>Rebuilt Outlook OST cache cleanly.</p>",
    )
    sp_svc.archive_ticket(t1["id"])
    sp_svc.assign_ticket_taxonomy(
        t1["id"],
        ["domain.m365.exchange", "symptom.mail_flow_sync", "resolution.profile_cache_rebuild"],
    )

    t2 = sp_svc.create_ticket(
        ticket_number="INC-9302",
        client_name="Fabrikam",
        title="Entra MFA token loop",
        content_html="<p>Revoked Entra MFA sessions and re-registered.</p>",
    )
    sp_svc.archive_ticket(t2["id"])
    sp_svc.assign_ticket_taxonomy(
        t2["id"],
        ["domain.identity.entra_mfa", "symptom.auth_signin", "resolution.token_mfa_reset"],
    )

    page = HistorySearchPage(get_conn=db_mgr.get_connection)
    page.resize(1100, 680)
    page.show()
    qapp.processEvents()
    try:
        page.refresh_and_focus()
        assert page.results_list.count() == 2
        assert page.domain_combo.findData("domain.m365.exchange") > 0
        assert page.domain_combo.findData("domain.m365") > 0
        assert page.symptom_combo.findData("symptom.mail_flow_sync") > 0
        assert page.resolution_combo.findData("resolution.profile_cache_rebuild") > 0

        # Filter by parent domain slug -> matches child leaf domain.m365.exchange
        page.domain_combo.setCurrentIndex(page.domain_combo.findData("domain.m365"))
        qapp.processEvents()
        assert page.results_list.count() == 1
        assert page.count_label.text() == "1 match"

        # Preview header shows assigned taxonomy labels
        assert "M365 › Exchange" in page.meta_label.text()
        assert "Mail Flow / Sync" in page.meta_label.text()
        assert "Profile / Cache Rebuild" in page.meta_label.text()

        # Custom delegate card includes human-readable taxonomy badges
        delegate = page.results_list.itemDelegate()
        res = page.results_list.item(0).data(Qt.ItemDataRole.UserRole + 1)
        opt = QStyleOptionViewItem()
        opt.rect.setWidth(360)
        doc_html = delegate._build_document(opt, res).toHtml()
        assert "M365 › Exchange" in doc_html

        # Cross-axis combination with mismatched symptom returns 0 matches
        page.symptom_combo.setCurrentIndex(page.symptom_combo.findData("symptom.auth_signin"))
        qapp.processEvents()
        assert page.results_list.count() == 0
        assert page.count_label.text() == "0 matches"

        # Switching symptom & resolution to match Exchange ticket brings it back
        page.symptom_combo.setCurrentIndex(page.symptom_combo.findData("symptom.mail_flow_sync"))
        page.resolution_combo.setCurrentIndex(page.resolution_combo.findData("resolution.profile_cache_rebuild"))
        qapp.processEvents()
        assert page.results_list.count() == 1
        assert "INC-9301" in page.meta_label.text()
    finally:
        page.close()
        page.deleteLater()
        db_mgr.close()


def test_step2_main_window_history_coexistence_and_shortcuts(qapp, tmp_path):
    """Verifies top 🕰️ coexistence, Ctrl+Shift+F shortcut, and graceful drawer hide/restore."""
    from PySide6.QtWidgets import QApplication
    from src.repositories.image_repository import ImageRepository
    from src.repositories.session_repository import SessionRepository
    from src.repositories.template_repository import TemplateRepository
    from src.services.session_service import SessionService
    from src.ui.main_window import TechPadMainWindow

    db_mgr = DatabaseManager(tmp_path / "step2_coexist.db")
    init_database(db_mgr)
    scratch_repo = ScratchpadRepository(db_mgr)
    img_repo = ImageRepository(db_mgr)
    img_svc = ImageService(img_repo)
    sp_svc = ScratchpadService(scratch_repo, img_svc, TemplateRepository(db_mgr))
    sess_svc = SessionService(SessionRepository(db_mgr), sp_svc)

    arch = sp_svc.create_ticket(
        ticket_number="INC-9401",
        client_name="Contoso",
        title="Problème réseau Wi-Fi",
        content_html="<p>Réseau restauré via réinitialisation DHCP.</p>",
    )
    sp_svc.archive_ticket(arch["id"])

    win = TechPadMainWindow(sp_svc, img_svc, sess_svc)
    win.show()
    qapp.processEvents()
    try:
        # 1. Open right History drawer via top 🕰️ button -> stays in Active Workspace
        if win.history_drawer.isHidden():
            win.toolbar.btn_history.click()
            qapp.processEvents()
        assert win.history_drawer.isVisible() is True
        assert win.is_history_search_page is False

        # 2. Trigger Ctrl+Shift+F slot -> opens HistorySearchPage, focuses search_input, hides drawer
        win.history_search_shortcut.activated.emit()
        qapp.processEvents()
        assert win.is_history_search_page is True
        assert win.history_drawer.isHidden() is True
        assert win.bottom_history_btn.isChecked() is True
        assert win.history_search_page.search_input.hasFocus() is True

        # 3. Clicking top 🕰️ while HistorySearchPage is open & drawer had been open:
        # closes HistorySearchPage and toggles drawer closed (never two history views side-by-side)
        win.toolbar.btn_history.click()
        qapp.processEvents()
        assert win.is_history_search_page is False
        assert win.history_drawer.isHidden() is True

        # 4. When drawer is hidden and HistorySearchPage is open, clicking top 🕰️ closes search page & opens drawer
        win.bottom_history_btn.click()
        qapp.processEvents()
        assert win.is_history_search_page is True
        win.toolbar.btn_history.click()
        qapp.processEvents()
        assert win.is_history_search_page is False
        assert win.history_drawer.isVisible() is True
    finally:
        win.quit_application()
        QApplication.instance().removeEventFilter(win)
        win.deleteLater()
        db_mgr.close()


def test_step2_debounce_clipboard_and_controller_refresh(qapp, tmp_path, monkeypatch):
    """Validates 180 ms debounced FTS5 lookup, diacritic highlight, clipboard copy, and restore/clone refresh."""
    from PySide6.QtGui import QGuiApplication
    from PySide6.QtTest import QTest
    from PySide6.QtWidgets import QApplication
    from src.repositories.image_repository import ImageRepository
    from src.repositories.session_repository import SessionRepository
    from src.repositories.template_repository import TemplateRepository
    from src.services.session_service import SessionService
    from src.ui.main_window import TechPadMainWindow

    copied: list[str] = []
    monkeypatch.setattr(QGuiApplication.clipboard(), "setText", copied.append)

    db_mgr = DatabaseManager(tmp_path / "step2_debounce.db")
    init_database(db_mgr)
    scratch_repo = ScratchpadRepository(db_mgr)
    img_repo = ImageRepository(db_mgr)
    img_svc = ImageService(img_repo)
    sp_svc = ScratchpadService(scratch_repo, img_svc, TemplateRepository(db_mgr))
    sess_svc = SessionService(SessionRepository(db_mgr), sp_svc)

    t1 = sp_svc.create_ticket(
        ticket_number="INC-9501",
        client_name="Contoso",
        title="Panne réseau VPN",
        content_html="<p>Le réseau interne a été rétabli.</p>",
    )
    sp_svc.archive_ticket(t1["id"])
    t2 = sp_svc.create_ticket(
        ticket_number="INC-9502",
        client_name="Fabrikam",
        title="Printer Spooler Queue",
        content_html="<p>Cleared spooler queue.</p>",
    )
    sp_svc.archive_ticket(t2["id"])

    win = TechPadMainWindow(sp_svc, img_svc, sess_svc)
    win.show()
    qapp.processEvents()
    try:
        win.bottom_history_btn.click()
        qapp.processEvents()
        page = win.history_search_page
        assert page._debounce.interval() == 180
        assert page.results_list.count() == 2

        # Typing starts debounce timer; waiting slightly past 180 ms executes FTS5 search & highlights 'réseau'
        page.search_input.setText("reseau")
        assert page._debounce.isActive() is True
        QTest.qWait(240)
        qapp.processEvents()

        assert page.results_list.count() == 1
        assert page.count_label.text() == "1 match"
        assert len(page.preview_edit.extraSelections()) >= 1

        # Copy Body / Copy All populate clipboard
        page.copy_body_btn.click()
        assert "rétabli" in copied[-1]
        page.copy_all_btn.click()
        assert "INC-9501" in copied[-1]

        # Restore removes archived ticket from HistorySearchPage results & refreshes count
        page.restore_btn.click()
        qapp.processEvents()
        assert win.is_history_search_page is False
        assert win.tab_widget.get_current_editor().scratchpad_id == t1["id"]

        win.bottom_history_btn.click()
        qapp.processEvents()
        assert page.results_list.count() == 0  # 'reseau' archived ticket was restored to active

        page.search_input.clear()
        page._run_fresh_search()
        assert page.results_list.count() == 1  # Only INC-9502 remains archived

        # Clone keeps archived ticket in History and creates a new active tab
        tabs_before = win.tab_widget.count()
        page.clone_btn.click()
        qapp.processEvents()
        assert win.is_history_search_page is False
        assert win.tab_widget.count() == tabs_before + 1
        assert win.tab_widget.get_current_editor().scratchpad_id not in (t1["id"], t2["id"])
    finally:
        win.quit_application()
        QApplication.instance().removeEventFilter(win)
        win.deleteLater()
        db_mgr.close()


def test_step3_archive_taxonomy_dialog_en_and_fr_autosuggest_provenance_and_filters(qapp, tmp_path):
    """Validates EN/FR-CA auto-suggestions, auto vs manual provenance, Enter confirm, and HistorySearchPage filtering."""
    from PySide6.QtCore import Qt, QTimer
    from PySide6.QtTest import QTest
    from PySide6.QtWidgets import QApplication
    from src.database.history_fts import get_ticket_taxonomy
    from src.repositories.image_repository import ImageRepository
    from src.repositories.session_repository import SessionRepository
    from src.repositories.template_repository import TemplateRepository
    from src.services.session_service import SessionService
    from src.ui.dialogs.archive_taxonomy_dialog import ArchiveTaxonomyDialog
    from src.ui.main_window import TechPadMainWindow

    db_mgr = DatabaseManager(tmp_path / "step3_en_fr.db")
    init_database(db_mgr)
    conn = db_mgr.get_connection()
    scratch_repo = ScratchpadRepository(db_mgr)
    img_repo = ImageRepository(db_mgr)
    img_svc = ImageService(img_repo)
    sp_svc = ScratchpadService(scratch_repo, img_svc, TemplateRepository(db_mgr))
    sess_svc = SessionService(SessionRepository(db_mgr), sp_svc)

    # 1. English auto-suggestion accuracy
    en_dlg = ArchiveTaxonomyDialog(
        ticket_number="INC-9601",
        client_name="Contoso",
        title="Outlook OST corrupt, rebuilt user profile",
        body_text="Cleared cache and recreated Outlook profile.",
        conn=conn,
    )
    try:
        en_assignments = {a["slug"]: a["source"] for a in en_dlg.pill_selector.selected_assignments()}
        assert en_assignments.get("domain.m365.exchange") == "auto"
        assert en_assignments.get("symptom.mail_flow_sync") == "auto"
        assert en_assignments.get("resolution.profile_cache_rebuild") == "auto"
        exch_btn = en_dlg.pill_selector.pill_buttons["domain.m365.exchange"]
        assert exch_btn.property("pillState") == "auto"
        assert "✦" in exch_btn.text()
        assert "Auto-suggested" in exch_btn.toolTip()
    finally:
        en_dlg.close()
        en_dlg.deleteLater()

    # 2. French-Canadian diacritic-insensitive auto-suggestion + manual pill click provenance
    fr_dlg = ArchiveTaxonomyDialog(
        ticket_number="INC-9602",
        client_name="Desjardins",
        title="Imprimante réseau bloquée, redémarrage du spooler",
        body_text="",
        conn=conn,
    )
    try:
        fr_assignments = {a["slug"]: a["source"] for a in fr_dlg.pill_selector.selected_assignments()}
        assert fr_assignments.get("domain.hardware.printers_peripherals") == "auto"
        assert fr_assignments.get("symptom.hardware_print") == "auto"

        # Clicking an unselected pill marks it manual while untouched suggestions stay auto
        manual_btn = fr_dlg.pill_selector.pill_buttons["resolution.service_driver_restart"]
        manual_btn.click()
        assert manual_btn.property("pillState") == "manual"

        # Toggling an auto pill off then on switches it cleanly to manual
        print_btn = fr_dlg.pill_selector.pill_buttons["symptom.hardware_print"]
        print_btn.click()
        assert print_btn.isChecked() is False
        print_btn.click()
        assert print_btn.isChecked() is True
        assert print_btn.property("pillState") == "manual"

        mixed = {a["slug"]: a["source"] for a in fr_dlg.selected_assignments()}
        # Simulate user pressing Enter on Archive Ticket button
        fr_dlg._on_archive_with_tags()
        mixed = {a["slug"]: a["source"] for a in fr_dlg.selected_assignments()}
        assert mixed["domain.hardware.printers_peripherals"] == "auto"
        assert mixed["symptom.hardware_print"] == "manual"
        assert mixed["resolution.service_driver_restart"] == "manual"
    finally:
        fr_dlg.close()
        fr_dlg.deleteLater()

    # 3. Full MainWindow single-keystroke Enter archive flow & immediate Step 2 search visibility
    win = TechPadMainWindow(sp_svc, img_svc, sess_svc)
    win.show()
    qapp.processEvents()
    try:
        ed = win.tab_widget.get_current_editor()
        sid = ed.scratchpad_id
        sp_svc.update_metadata(
            sid,
            ticket_number="INC-9610",
            client_name="Contoso",
            title="Outlook OST corrupt, rebuilt user profile",
        )
        ed.setPlainText("Rebuilt OST file and verified mail flow.")
        idx = win.tab_widget.indexOf(ed)

        def _confirm_with_manual_and_enter():
            modal = QApplication.activeModalWidget()
            assert isinstance(modal, ArchiveTaxonomyDialog)
            modal.pill_selector.pill_buttons["resolution.permissions_updated"].click()
            QTest.keyClick(modal, Qt.Key.Key_Return)

        QTimer.singleShot(30, _confirm_with_manual_and_enter)
        assert win._archive_tab(idx) is True
        qapp.processEvents()

        saved_ticket = sp_svc.get_ticket(sid)
        assert saved_ticket["status"] == "archived"
        saved_tax = {row["slug"]: row["source"] for row in get_ticket_taxonomy(conn, sid)}
        assert saved_tax["domain.m365.exchange"] == "auto"
        assert saved_tax["resolution.permissions_updated"] == "manual"

        # Immediately searchable via Step 2 taxonomy filter dropdowns in HistorySearchPage
        win.bottom_history_btn.click()
        qapp.processEvents()
        page = win.history_search_page
        dom_idx = page.domain_combo.findData("domain.m365.exchange")
        assert dom_idx > 0
        page.domain_combo.setCurrentIndex(dom_idx)
        qapp.processEvents()
        assert page.results_list.count() == 1
        assert "INC-9610" in page.meta_label.text()
    finally:
        win.quit_application()
        QApplication.instance().removeEventFilter(win)
        win.deleteLater()
        db_mgr.close()


def test_step3_archive_without_tags_cancel_escape_and_bulk_archive(qapp, tmp_path):
    """Validates Archive Without Tags, Esc cancel leaving active ticket untouched, and non-modal bulk archive."""
    from PySide6.QtCore import Qt, QTimer
    from PySide6.QtTest import QTest
    from PySide6.QtWidgets import QApplication
    from src.database.history_fts import get_ticket_taxonomy
    from src.repositories.image_repository import ImageRepository
    from src.repositories.session_repository import SessionRepository
    from src.repositories.template_repository import TemplateRepository
    from src.services.session_service import SessionService
    from src.ui.dialogs.archive_taxonomy_dialog import ArchiveTaxonomyDialog
    from src.ui.main_window import TechPadMainWindow

    db_mgr = DatabaseManager(tmp_path / "step3_flows.db")
    init_database(db_mgr)
    conn = db_mgr.get_connection()
    scratch_repo = ScratchpadRepository(db_mgr)
    img_repo = ImageRepository(db_mgr)
    img_svc = ImageService(img_repo)
    sp_svc = ScratchpadService(scratch_repo, img_svc, TemplateRepository(db_mgr))
    sess_svc = SessionService(SessionRepository(db_mgr), sp_svc)

    win = TechPadMainWindow(sp_svc, img_svc, sess_svc)
    win.show()
    qapp.processEvents()
    try:
        # 1. Pressing Esc on ArchiveTaxonomyDialog cancels cleanly and keeps ticket active & untouched
        ed1 = win.tab_widget.get_current_editor()
        sid1 = ed1.scratchpad_id
        sp_svc.update_metadata(sid1, ticket_number="INC-9701", client_name="Contoso", title="Outlook OST issue")
        ed1.setPlainText("Still actively troubleshooting.")
        tabs_before = win.tab_widget.count()

        QTimer.singleShot(30, lambda: QTest.keyClick(QApplication.activeModalWidget(), Qt.Key.Key_Escape))
        assert win._archive_tab(win.tab_widget.indexOf(ed1)) is False
        qapp.processEvents()
        assert sp_svc.get_ticket(sid1)["status"] == "active"
        assert win.tab_widget.count() == tabs_before
        assert get_ticket_taxonomy(conn, sid1) == []

        # 2. Moving a ticket to secondary split pane and clicking "Archive Without Tags" stores 0 tags
        win.create_new_tab()
        ed2 = win.tab_widget.get_current_editor()
        sid2 = ed2.scratchpad_id
        sp_svc.update_metadata(sid2, ticket_number="INC-9702", client_name="Fabrikam", title="Entra MFA prompt loop")
        ed2.setPlainText("Reset MFA tokens.")
        win.open_split_view(target_scratchpad_id=sid2)
        qapp.processEvents()

        def _click_untagged():
            modal = QApplication.activeModalWidget()
            assert isinstance(modal, ArchiveTaxonomyDialog)
            modal.archive_untagged_btn.click()

        QTimer.singleShot(30, _click_untagged)
        assert win._archive_secondary_tab(0) is True
        qapp.processEvents()
        assert sp_svc.get_ticket(sid2)["status"] == "archived"
        assert get_ticket_taxonomy(conn, sid2) == []

        # 3. Bulk archiving via _close_other_tabs skips modal dialogs and silently auto-tags archived tickets
        win.create_new_tab()
        ed_keep = win.tab_widget.get_current_editor()
        keep_idx = win.tab_widget.indexOf(ed_keep)

        win._close_other_tabs(keep_idx)
        qapp.processEvents()
        assert sp_svc.get_ticket(sid1)["status"] == "archived"
        auto_tax = get_ticket_taxonomy(conn, sid1)
        assert any(row["slug"] == "domain.m365.exchange" and row["source"] == "auto" for row in auto_tax)
    finally:
        win.quit_application()
        QApplication.instance().removeEventFilter(win)
        win.deleteLater()
        db_mgr.close()


def test_step3_retroactive_edit_tags_in_history_search_page(qapp, tmp_path):
    """Validates HistorySearchPage Edit Tags button, ✦ Suggest Tags, manual edits, card refresh, and scroll preservation."""
    from PySide6.QtCore import Qt, QTimer
    from PySide6.QtWidgets import QApplication, QStyleOptionViewItem
    from src.database.history_fts import get_ticket_taxonomy
    from src.repositories.image_repository import ImageRepository
    from src.repositories.template_repository import TemplateRepository
    from src.ui.components.history_search_page import HistorySearchPage
    from src.ui.dialogs.archive_taxonomy_dialog import EditTicketTaxonomyDialog

    db_mgr = DatabaseManager(tmp_path / "step3_edit_tags.db")
    init_database(db_mgr)
    conn = db_mgr.get_connection()
    sp_svc = ScratchpadService(
        ScratchpadRepository(db_mgr),
        ImageService(ImageRepository(db_mgr)),
        TemplateRepository(db_mgr),
    )

    target_id = sp_svc.create_ticket(
        ticket_number="INC-9801",
        client_name="Northwind",
        title="Imprimante réseau bloquée",
        content_html="<p>Redémarré service spooler et réinstallé pilote.</p>",
    )["id"]
    sp_svc.archive_ticket(target_id)

    # Seed extra archived tickets so scroll bar is populated cleanly
    for idx in range(15):
        tid = sp_svc.create_ticket(
            ticket_number=f"INC-98{idx + 10}",
            client_name="Contoso",
            title=f"Sample archived ticket {idx}",
            content_html="<p>Routine ticket notes.</p>",
        )["id"]
        sp_svc.archive_ticket(tid)

    page = HistorySearchPage(get_conn=db_mgr.get_connection)
    page.resize(980, 420)
    page.show()
    qapp.processEvents()
    try:
        page.refresh_and_focus()
        assert page.edit_tags_btn.isEnabled() is True

        # Select target untagged ticket near the bottom of the list to verify scroll preservation
        target_row = next(
            r
            for r in range(page.results_list.count())
            if page.results_list.item(r).data(Qt.ItemDataRole.UserRole + 1).id == target_id
        )
        page.results_list.setCurrentRow(target_row)
        qapp.processEvents()
        page.results_list.verticalScrollBar().setValue(120)
        qapp.processEvents()
        saved_scroll = page.results_list.verticalScrollBar().value()

        def _suggest_toggle_and_save():
            modal = QApplication.activeModalWidget()
            assert isinstance(modal, EditTicketTaxonomyDialog)
            modal.suggest_btn.click()
            # Manual pill toggled in addition to ✦ auto-suggestions
            modal.pill_selector.pill_buttons["symptom.connectivity"].click()
            modal.save_btn.click()

        QTimer.singleShot(30, _suggest_toggle_and_save)
        assert page._open_edit_tags_dialog() is True
        qapp.processEvents()

        # Verify SQLite provenance persisted
        saved_tax = {row["slug"]: row["source"] for row in get_ticket_taxonomy(conn, target_id)}
        assert saved_tax["domain.hardware.printers_peripherals"] == "auto"
        assert saved_tax["resolution.service_driver_restart"] == "auto"
        assert saved_tax["symptom.connectivity"] == "manual"

        # Verify right-pane header, left-pane card badges, current row, and scroll position all updated/preserved
        assert "Hardware › Printers / Peripherals" in page.meta_label.text()
        assert "Connectivity" in page.meta_label.text()
        delegate = page.results_list.itemDelegate()
        res = page.results_list.item(target_row).data(Qt.ItemDataRole.UserRole + 1)
        opt = QStyleOptionViewItem()
        opt.rect.setWidth(360)
        card_html = delegate._build_document(opt, res).toHtml()
        assert "Hardware › Printers / Peripherals" in card_html
        assert page.results_list.currentRow() == target_row
        assert page.results_list.verticalScrollBar().value() == saved_scroll
    finally:
        page.close()
        page.deleteLater()
        db_mgr.close()
