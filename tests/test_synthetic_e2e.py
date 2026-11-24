"""End-to-end verification scenarios using 40 realistic bilingual synthetic MSP tickets."""

from __future__ import annotations

from datetime import datetime, timedelta, timezone
import sqlite3
import time

import pytest
from PySide6.QtCore import Qt, QTimer, qInstallMessageHandler
from PySide6.QtGui import QGuiApplication
from PySide6.QtTest import QTest
from PySide6.QtWidgets import QApplication, QStyleOptionViewItem

from src.database.history_fts import (
    assign_ticket_taxonomy,
    get_ticket_taxonomy,
    search_history,
    suggest_taxonomy_for_text,
)
from src.database.semantic_search import (
    EmbeddingIndexWorker,
    FakeEmbeddingProvider,
    OllamaEmbeddingProvider,
    index_pending_embeddings_sync,
    search_history_hybrid,
)
from src.repositories.image_repository import ImageRepository
from src.repositories.scratchpad_repository import ScratchpadRepository
from src.repositories.session_repository import SessionRepository
from src.repositories.template_repository import TemplateRepository
from src.services.image_service import ImageService
from src.services.scratchpad_service import ScratchpadService
from src.services.session_service import SessionService
from src.ui.dialogs.archive_taxonomy_dialog import ArchiveTaxonomyDialog, EditTicketTaxonomyDialog
from src.ui.main_window import TechPadMainWindow
from tests.synthetic_tickets import (
    SYNTHETIC_TICKETS,
    populate_500_ticket_benchmark_db,
    populate_synthetic_database,
)


def test_scenario_1_fts5_torture_filters_and_snippet_safety(tmp_path):
    """Scenario 1: Pre/post backfill, active isolation, torture queries, combined filters, & HTML safety."""
    ref_now = datetime.now(timezone.utc)
    db_mgr, id_map = populate_synthetic_database(tmp_path / "scenario1.db", now=ref_now)
    conn = db_mgr.get_connection()

    try:
        # 1. Exactly 32 archived tickets searchable via history_fts; 8 active tickets strictly excluded
        _, archived_total = search_history(conn, "", limit=100)
        assert archived_total == 32
        for spec in SYNTHETIC_TICKETS:
            hits, total = search_history(conn, spec.ticket_number)
            if spec.is_archived:
                # Verify FTS5 MATCH directly finds both pre-migration (backfilled) & post-migration rows
                fts_only = conn.execute(
                    "SELECT COUNT(*) FROM history_tickets_fts WHERE history_tickets_fts MATCH ?",
                    (f'"{spec.ticket_number}"',),
                ).fetchone()[0]
                assert fts_only >= 1, f"FTS5 index missing archived {spec.ticket_number}"
                assert total >= 1, f"Archived ticket {spec.ticket_number} missing from FTS5"
                assert any(h.ticket_number == spec.ticket_number for h in hits)
            else:
                assert not any(
                    h.ticket_number == spec.ticket_number for h in hits
                ), f"Active ticket {spec.ticket_number} leaked into history search"

        # 2. Prefix, hyphenated IDs, hex/Entra error codes, Windows path, & quoted phrases
        prefix_hits, prefix_tot = search_history(conn, "Autodisc*")
        assert prefix_tot >= 1 and any(h.ticket_number == "INC-40219" for h in prefix_hits)

        for code_query, expected_num in (
            ("INC-40219", "INC-40219"),
            ("SR-10884", "SR-10884"),
            ("HALO-9921", "HALO-9921"),
            ("0x0000011b", "SR-10884"),
            ("AADSTS50076", "INC-40220"),
            (r"C:\Users\m.tremblay\AppData\Local\Microsoft\Outlook\profile.ost", "INC-40219"),
            ('"shared mailbox"', "INC-40233"),
            ('"compte verrouillé"', "INC-40225"),
        ):
            hits, total = search_history(conn, code_query)
            assert total >= 1, f"Query {code_query!r} returned 0 results"
            assert any(h.ticket_number == expected_num for h in hits), (
                f"Query {code_query!r} missed {expected_num}"
            )

        # 3. French diacritic insensitivity (plain ASCII finds accented archived notes only)
        verrouille_hits, _ = search_history(conn, "verrouille")
        assert [h.ticket_number for h in verrouille_hits] == ["INC-40225"]

        boite_hits, _ = search_history(conn, "boite partagee")
        assert any(h.ticket_number == "INC-40231" for h in boite_hits)

        spouleur_hits, _ = search_history(conn, "spouleur")
        assert any(h.ticket_number == "INC-40226" for h in spouleur_hits)

        # 4. Long ~12,500-char HALO-9921 multi-day escalation searches cleanly
        halo_hits, _ = search_history(conn, "BELL-883412")
        assert len(halo_hits) == 1 and halo_hits[0].ticket_number == "HALO-9921"

        # 5. Torture / malformed queries never raise sqlite3.OperationalError
        torture_queries = [
            "",
            "   ",
            "AND OR NOT",
            '"unclosed quote',
            "***",
            "(((NEAR",
            "C:\\",
            "user@domain.com -- (test) [1]",
            "::: --- ^~!",
            'foo "bar baz AND OR (qux',
        ]
        for q in torture_queries:
            res, tot = search_history(conn, q)
            assert isinstance(res, list) and isinstance(tot, int)

        # 6. Combined filters (Client + Date Window + 3-Axis Taxonomy Slugs)
        cutoff_15d = (ref_now - timedelta(days=15)).strftime("%Y-%m-%d")
        # Assign taxonomy explicitly to INC-40232 (days_ago=11) as a post-upgrade tagged item check,
        # and test Clinique Saint-Laurent post-migration INC-40240 (days_ago=3).
        acier_id = id_map["INC-40232"]
        assign_ticket_taxonomy(
            conn,
            acier_id,
            [
                "domain.security.defender_phishing",
                "symptom.auth_signin",
                "resolution.token_mfa_reset",
            ],
            source="auto",
        )
        filtered_hits, filtered_tot = search_history(
            conn,
            "phishing",
            client="Acier Montérégie",
            date_from=cutoff_15d,
            taxonomy_slugs=[
                "domain.security.defender_phishing",
                "symptom.auth_signin",
                "resolution.token_mfa_reset",
            ],
        )
        assert filtered_tot == 1
        assert [h.ticket_number for h in filtered_hits] == ["INC-40232"]

        # Filtering Clinique Saint-Laurent within last 5 days + teams_sharepoint matches INC-40240 only
        cutoff_5d = (ref_now - timedelta(days=5)).strftime("%Y-%m-%d")
        clinique_hits, clinique_tot = search_history(
            conn,
            "OneDrive",
            client="Clinique Saint-Laurent",
            date_from=cutoff_5d,
            taxonomy_slugs=["domain.m365.teams_sharepoint"],
        )
        assert clinique_tot == 1
        assert clinique_hits[0].ticket_number == "INC-40240"

        # 7. Angle-bracket HTML escaping & match highlight preservation
        err_hits, _ = search_history(conn, "503")
        inc40219_err = next(h for h in err_hits if h.ticket_number == "INC-40219")
        assert "&lt;ErrorCode&gt;<b>503</b>&lt;/ErrorCode&gt;" in inc40219_err.snippet_html

        email_hits, _ = search_history(conn, "gagnon")
        inc40219_email = next(h for h in email_hits if h.ticket_number == "INC-40219")
        assert "&lt;j.<b>gagnon</b>@aciermonteregie.ca&gt;" in inc40219_email.snippet_html
    finally:
        db_mgr.close()


def test_scenario_2_bilingual_auto_tagging_accuracy_audit(tmp_path):
    """Scenario 2: Audit EN vs FR-CA auto-suggestion accuracy across all 40 synthetic tickets."""
    db_mgr, _ = populate_synthetic_database(tmp_path / "scenario2.db")
    conn = db_mgr.get_connection()

    try:
        stats = {
            lang: {axis: {"hits": 0, "total": 0, "misses": []} for axis in ("domain", "symptom", "resolution")}
            for lang in ("EN", "FR")
        }

        for spec in SYNTHETIC_TICKETS:
            sug = suggest_taxonomy_for_text(
                title=spec.title,
                body=spec.body_text,
                conn=conn,
                max_per_axis=2,
            )

            if not spec.has_technical_cues:
                # Minimal empty-body ticket (INC-40250) must stay quiet without false positives
                total_suggestions = sum(len(v) for v in sug.values())
                assert total_suggestions <= 1, f"Unexpected noisy suggestions on minimal ticket: {sug}"
                continue

            for axis, expected_slug in (
                ("domain", spec.expected_domain),
                ("symptom", spec.expected_symptom),
                ("resolution", spec.expected_resolution),
            ):
                assert expected_slug is not None
                candidates = sug.get(axis, [])
                if axis == "domain":
                    picked = next(
                        (c["slug"] for c in candidates if c.get("parent_slug") is not None),
                        candidates[0]["slug"] if candidates else None,
                    )
                else:
                    picked = candidates[0]["slug"] if candidates else None

                bucket = stats[spec.language][axis]
                bucket["total"] += 1
                if picked == expected_slug:
                    bucket["hits"] += 1
                else:
                    bucket["misses"].append((spec.ticket_number, expected_slug, picked))

        print("\n=== Auto-Tagging Accuracy Audit (39 Technical Tickets: EN vs FR-CA) ===")
        for axis in ("domain", "symptom", "resolution"):
            en_b = stats["EN"][axis]
            fr_b = stats["FR"][axis]
            ov_hits = en_b["hits"] + fr_b["hits"]
            ov_tot = en_b["total"] + fr_b["total"]
            en_pct = (en_b["hits"] / en_b["total"]) * 100.0
            fr_pct = (fr_b["hits"] / fr_b["total"]) * 100.0
            ov_pct = (ov_hits / ov_tot) * 100.0
            print(
                f"  {axis.capitalize():<10} | "
                f"EN: {en_b['hits']}/{en_b['total']} ({en_pct:.1f}%) | "
                f"FR-CA: {fr_b['hits']}/{fr_b['total']} ({fr_pct:.1f}%) | "
                f"Overall: {ov_hits}/{ov_tot} ({ov_pct:.1f}%)"
            )
            if en_b["misses"] or fr_b["misses"]:
                print(f"    Misses -> EN: {en_b['misses']} | FR: {fr_b['misses']}")

            assert en_pct >= 80.0, f"EN {axis} accuracy below 80%: {en_pct:.1f}% ({en_b['misses']})"
            assert fr_pct >= 80.0, f"FR {axis} accuracy below 80%: {fr_pct:.1f}% ({fr_b['misses']})"
            assert ov_pct >= 80.0, f"Overall {axis} accuracy below 80%: {ov_pct:.1f}%"
    finally:
        db_mgr.close()


def test_scenario_3_headless_ui_workflow_archive_edit_restore_clone(qapp, tmp_path, monkeypatch):
    """Scenario 3: Full PySide6 MainWindow workflow on 40-ticket synthetic DB under offscreen Qt."""
    copied_texts: list[str] = []
    monkeypatch.setattr(QGuiApplication.clipboard(), "setText", copied_texts.append)

    db_mgr, id_map = populate_synthetic_database(tmp_path / "scenario3_ui.db")
    conn = db_mgr.get_connection()

    scratch_repo = ScratchpadRepository(db_mgr)
    img_svc = ImageService(ImageRepository(db_mgr))
    sp_svc = ScratchpadService(scratch_repo, img_svc, TemplateRepository(db_mgr))
    sess_svc = SessionService(SessionRepository(db_mgr), sp_svc)

    win = TechPadMainWindow(sp_svc, img_svc, sess_svc)
    win.show()
    qapp.processEvents()

    try:
        assert win.tab_widget.count() == 8

        # 1. Coexistence: Top 🕰️ opens right History drawer without switching away from active tabs
        if win.history_drawer.isHidden():
            win.toolbar.btn_history.click()
            qapp.processEvents()
        assert win.history_drawer.isVisible() is True
        assert win.is_history_search_page is False

        # 2. Bottom History button switches central main_stack to HistorySearchPage & hides drawer
        win.bottom_history_btn.click()
        qapp.processEvents()
        assert win.is_history_search_page is True
        assert win.main_stack.currentWidget() is win.history_search_page
        assert win.history_drawer.isHidden() is True
        assert win.history_search_page.results_list.count() == 32

        # Return to active workspace for archiving flows
        win.history_search_page.back_btn.click()
        qapp.processEvents()
        assert win.is_history_search_page is False

        # 3. Archive EN active ticket INC-40301 via immediate Enter -> source='auto' provenance
        en_id = id_map["INC-40301"]
        en_ed, tw_en, en_idx = win._find_editor_by_id(en_id)
        assert en_ed is not None and tw_en is win.tab_widget

        QTimer.singleShot(30, lambda: QTest.keyClick(QApplication.activeModalWidget(), Qt.Key.Key_Return))
        assert win._archive_tab(en_idx, prompt_taxonomy=True) is True
        qapp.processEvents()

        assert sp_svc.get_ticket(en_id)["status"] == "archived"
        en_tax = {r["slug"]: r["source"] for r in get_ticket_taxonomy(conn, en_id)}
        assert en_tax["domain.m365.exchange"] == "auto"
        assert en_tax["symptom.mail_flow_sync"] == "auto"
        assert en_tax["resolution.profile_cache_rebuild"] == "auto"

        # 4. Archive FR active ticket INC-40302, toggle manual pill, confirm -> mixed auto + manual provenance
        fr_id = id_map["INC-40302"]
        fr_ed, tw_fr, fr_idx = win._find_editor_by_id(fr_id)
        assert fr_ed is not None and tw_fr is win.tab_widget

        def _toggle_manual_and_accept():
            modal = QApplication.activeModalWidget()
            assert isinstance(modal, ArchiveTaxonomyDialog)
            modal.pill_selector.pill_buttons["resolution.escalated_vendor"].click()
            QTest.keyClick(modal, Qt.Key.Key_Return)

        QTimer.singleShot(30, _toggle_manual_and_accept)
        assert win._archive_tab(fr_idx, prompt_taxonomy=True) is True
        qapp.processEvents()

        fr_tax = {r["slug"]: r["source"] for r in get_ticket_taxonomy(conn, fr_id)}
        assert fr_tax["domain.hardware.printers_peripherals"] == "auto"
        assert fr_tax["symptom.hardware_print"] == "auto"
        assert fr_tax["resolution.escalated_vendor"] == "manual"

        # 5. Esc cancel on active ticket INC-40303 leaves ticket active & excluded from FTS5
        esc_id = id_map["INC-40303"]
        esc_ed, _, esc_idx = win._find_editor_by_id(esc_id)
        assert esc_ed is not None

        QTimer.singleShot(30, lambda: QTest.keyClick(QApplication.activeModalWidget(), Qt.Key.Key_Escape))
        assert win._archive_tab(esc_idx, prompt_taxonomy=True) is False
        qapp.processEvents()
        assert sp_svc.get_ticket(esc_id)["status"] == "active"
        assert get_ticket_taxonomy(conn, esc_id) == []
        _, esc_fts_total = search_history(conn, "INC-40303")
        assert esc_fts_total == 0

        # 6. HistorySearchPage: Search, preview highlight, Copy Body & Copy All
        win.bottom_history_btn.click()
        qapp.processEvents()
        page = win.history_search_page

        page.search_input.setText("0x0000011b")
        QTest.qWait(230)
        qapp.processEvents()
        assert page.results_list.count() >= 2
        page.results_list.setCurrentRow(0)
        qapp.processEvents()
        assert len(page.preview_edit.extraSelections()) >= 1

        page.copy_body_btn.click()
        assert "0x0000011b" in copied_texts[-1]
        page.copy_all_btn.click()
        assert "Ticket:" in copied_texts[-1] and "Archived:" in copied_texts[-1]

        # 7. Retroactive Edit Tags on untagged pre-migration ticket INC-40219 -> live card refresh
        page.search_input.setText("INC-40219")
        QTest.qWait(230)
        qapp.processEvents()
        assert page.results_list.count() == 1
        page.results_list.setCurrentRow(0)
        qapp.processEvents()

        def _edit_tags_suggest_and_save():
            modal = QApplication.activeModalWidget()
            assert isinstance(modal, EditTicketTaxonomyDialog)
            modal.suggest_btn.click()
            modal.pill_selector.pill_buttons["symptom.permissions_access"].click()
            modal.save_btn.click()

        QTimer.singleShot(30, _edit_tags_suggest_and_save)
        assert page._open_edit_tags_dialog() is True
        qapp.processEvents()

        inc40219_tax = {r["slug"]: r["source"] for r in get_ticket_taxonomy(conn, id_map["INC-40219"])}
        assert inc40219_tax["domain.m365.exchange"] == "auto"
        assert inc40219_tax["symptom.permissions_access"] == "manual"

        delegate = page.results_list.itemDelegate()
        res0 = page.results_list.item(0).data(Qt.ItemDataRole.UserRole + 1)
        opt = QStyleOptionViewItem()
        opt.rect.setWidth(360)
        card_html = delegate._build_document(opt, res0).toHtml()
        assert "M365 › Exchange" in card_html
        assert "Permissions / Access" in page.meta_label.text()

        # 8. Restore INC-40220 to active -> opens active tab and leaves ZERO FTS ghost records
        restore_id = id_map["INC-40220"]
        page.search_input.setText("INC-40220")
        QTest.qWait(230)
        qapp.processEvents()
        assert page.results_list.count() == 1
        page.results_list.setCurrentRow(0)
        qapp.processEvents()
        page.restore_btn.click()
        qapp.processEvents()

        assert win.is_history_search_page is False
        assert win.tab_widget.get_current_editor().scratchpad_id == restore_id
        assert sp_svc.get_ticket(restore_id)["status"] == "active"
        assert search_history(conn, "INC-40220")[1] == 0

        # 9. Clone INC-40233 to new ticket -> creates new active tab while INC-40233 stays archived
        clone_src_id = id_map["INC-40233"]
        win.bottom_history_btn.click()
        qapp.processEvents()
        page.search_input.setText("INC-40233")
        QTest.qWait(230)
        qapp.processEvents()
        assert page.results_list.count() == 1
        page.results_list.setCurrentRow(0)
        qapp.processEvents()

        tabs_before_clone = win.tab_widget.count()
        page.clone_btn.click()
        qapp.processEvents()

        assert win.is_history_search_page is False
        assert win.tab_widget.count() == tabs_before_clone + 1
        cloned_ed = win.tab_widget.get_current_editor()
        assert cloned_ed is not None and cloned_ed.scratchpad_id != clone_src_id
        assert sp_svc.get_ticket(clone_src_id)["status"] == "archived"
        assert search_history(conn, "INC-40233")[1] == 1
    finally:
        win.quit_application()
        QApplication.instance().removeEventFilter(win)
        win.deleteLater()
        qapp.processEvents()
        db_mgr.close()


def test_scenario_4_hybrid_semantic_wal_qthread_and_offline_fallback(qapp, tmp_path):
    """Scenario 4: WAL QThread indexing, hash skip, cross-lingual RRF, filters, fallback, shutdown."""
    qt_warnings: list[str] = []
    prev_handler = qInstallMessageHandler(lambda _t, _c, msg: qt_warnings.append(msg))

    db_file = tmp_path / "scenario4_semantic.db"
    db_mgr, id_map = populate_synthetic_database(db_file)
    conn = db_mgr.get_connection()

    try:
        assert conn.execute("PRAGMA journal_mode").fetchone()[0].lower() == "wal"

        # 1. QThread background worker indexes all 32 archived tickets cleanly
        provider = FakeEmbeddingProvider(dim=64)
        worker1 = EmbeddingIndexWorker(db_file, provider, batch_size=8)
        fin1: list[tuple[int, str]] = []
        worker1.indexing_finished.connect(lambda c, s: fin1.append((c, s)))
        worker1.start()
        assert worker1.wait(6000) is True
        qapp.processEvents()
        assert fin1 and fin1[-1][0] == 32
        assert conn.execute("SELECT COUNT(*) FROM ticket_embeddings").fetchone()[0] == 32

        # 2. Second QThread pass skips all unchanged content hashes (0 re-embedded)
        calls_before = len(provider.calls)
        worker2 = EmbeddingIndexWorker(db_file, provider, batch_size=8)
        fin2: list[tuple[int, str]] = []
        worker2.indexing_finished.connect(lambda c, s: fin2.append((c, s)))
        worker2.start()
        assert worker2.wait(6000) is True
        qapp.processEvents()
        assert fin2 == [(0, "Up to date")]
        assert len(provider.calls) == calls_before

        # 3. Updating 1 archived ticket re-embeds exactly 1 ticket
        edited_id = id_map["INC-40238"]
        ScratchpadRepository(db_mgr).update_content(
            edited_id,
            "<p>Expanded Meraki DHCP scope and updated VLAN 10 DNS forwarders.</p>",
        )
        worker3 = EmbeddingIndexWorker(db_file, provider, batch_size=8)
        fin3: list[tuple[int, str]] = []
        worker3.indexing_finished.connect(lambda c, s: fin3.append((c, s)))
        worker3.start()
        assert worker3.wait(6000) is True
        qapp.processEvents()
        assert fin3 and fin3[-1][0] == 1

        # 4. Hybrid RRF: exact ticket ID ranks #1, and cross-lingual zero-overlap query surfaces FR ticket INC-40231
        exact_hits, exact_tot = search_history_hybrid(conn, "INC-40219", mode="smart", provider=provider)
        assert exact_tot >= 1 and exact_hits[0].ticket_number == "INC-40219"

        # FTS5 alone has zero overlap between "shared inbox missing new emails" and French INC-40231
        assert search_history(conn, "shared inbox missing new emails")[1] == 0
        sem_hits, sem_tot = search_history_hybrid(
            conn,
            "shared inbox missing new emails",
            mode="smart",
            provider=provider,
            min_similarity=0.25,
        )
        assert sem_tot >= 1
        inc40231_hit = next((h for h in sem_hits if h.ticket_number == "INC-40231"), None)
        assert inc40231_hit is not None
        assert inc40231_hit.match_type == "semantic"

        # 5. Active client/date/taxonomy filters strictly constrain semantic candidates
        wrong_client_hits, wrong_client_tot = search_history_hybrid(
            conn,
            "shared inbox missing new emails",
            mode="smart",
            provider=provider,
            client="NorthStar Logistics",
            min_similarity=0.25,
        )
        assert all(h.client == "NorthStar Logistics" for h in wrong_client_hits)
        assert not any(h.ticket_number == "INC-40231" for h in wrong_client_hits)
        assert wrong_client_tot == len(wrong_client_hits)

        # 6. UI test with unreachable Ollama port (graceful fallback) & clean window close
        scratch_repo = ScratchpadRepository(db_mgr)
        img_svc = ImageService(ImageRepository(db_mgr))
        sp_svc = ScratchpadService(scratch_repo, img_svc, TemplateRepository(db_mgr))
        sess_svc = SessionService(SessionRepository(db_mgr), sp_svc)

        win = TechPadMainWindow(sp_svc, img_svc, sess_svc)
        page = win.history_search_page
        win.show()
        win.bottom_history_btn.click()
        qapp.processEvents()

        # Point OllamaEmbeddingProvider at closed local port; Smart mode still returns exact FTS results cleanly
        unreachable_ollama = OllamaEmbeddingProvider(
            base_url="http://127.0.0.1:59999",
            model_id="fake-bge-m3",
            availability_timeout=0.1,
            embed_timeout=0.1,
        )
        page.set_embedding_provider(unreachable_ollama)
        page.mode_combo.setCurrentIndex(page.mode_combo.findData("smart"))
        page.search_input.setText("0x0000011b")
        QTest.qWait(260)
        qapp.processEvents()
        assert page.results_list.count() >= 2

        # Kick off background indexer on live provider then immediately quit -> zero QThread warnings
        page.set_embedding_provider(FakeEmbeddingProvider(model_id="shutdown-test-model", dim=64))
        page.start_background_indexing(force=True)
        win.quit_application()
        QApplication.instance().removeEventFilter(win)
        win.deleteLater()
        qapp.processEvents()

        assert not any("Destroyed while thread is still running" in m for m in qt_warnings)
    finally:
        qInstallMessageHandler(prev_handler)
        db_mgr.close()


def test_scenario_5_500_ticket_benchmark(tmp_path):
    """Scenario 5: 500-ticket FTS5 + taxonomy + 384-dim cosine/RRF performance (<100 ms per query)."""
    db_mgr = populate_500_ticket_benchmark_db(tmp_path / "bench_500.db", target_archived_count=500)
    conn = db_mgr.get_connection()

    try:
        provider = FakeEmbeddingProvider(model_id="bench-384", dim=384)
        indexed, _ = index_pending_embeddings_sync(conn, provider, batch_size=50)
        assert indexed == 500

        # Precompute normalized query vectors once (benchmarking SQLite/vector/RRF search cost itself,
        # excluding external LLM latency).
        fts_queries = ["0x0000011b", "FortiClient VPN", "boite partagee", "AADSTS50076", "node-250"]
        hybrid_queries = [
            ("FortiClient tunnel disconnect", provider.embed_texts(["FortiClient tunnel disconnect"])[0]),
            ("shared inbox not updating", provider.embed_texts(["shared inbox not updating"])[0]),
            ("printer spooler queue stuck", provider.embed_texts(["printer spooler queue stuck"])[0]),
            ("compte verrouille entra mfa", provider.embed_texts(["compte verrouille entra mfa"])[0]),
        ]

        # Warmup once
        search_history(conn, "Outlook", limit=100)
        search_history_hybrid(
            conn,
            "Outlook",
            mode="smart",
            model_id="bench-384",
            query_vector=hybrid_queries[0][1],
            limit=100,
        )

        # 1. Pure FTS5 search + snippets
        fts_ms: list[float] = []
        for q in fts_queries:
            t0 = time.perf_counter()
            hits, total = search_history(conn, q, limit=100)
            elapsed = (time.perf_counter() - t0) * 1000.0
            fts_ms.append(elapsed)
            assert total >= 1 and len(hits) >= 1

        # 2. Combined FTS5 + 3-axis taxonomy + client filter
        tax_ms: list[float] = []
        combo_cases = [
            ("Outlook", "Acier Montérégie", ["domain.m365.exchange", "symptom.mail_flow_sync", "resolution.profile_cache_rebuild"]),
            ("VPN", "Apex Manufacturing", ["domain.network.vpn_dns_wifi", "symptom.connectivity"]),
            ("imprimante", "Boulangerie Lavoie", ["domain.hardware.printers_peripherals", "symptom.hardware_print"]),
        ]
        for q, client_name, slugs in combo_cases:
            t0 = time.perf_counter()
            hits, total = search_history(
                conn,
                q,
                client=client_name,
                taxonomy_slugs=slugs,
                limit=100,
            )
            elapsed = (time.perf_counter() - t0) * 1000.0
            tax_ms.append(elapsed)
            assert total >= 1 and all(h.client == client_name for h in hits)

        # 3. Full 500-vector 384-dim cosine similarity scan + Hybrid RRF merge
        rrf_ms: list[float] = []
        for q, q_vec in hybrid_queries:
            t0 = time.perf_counter()
            hits, total = search_history_hybrid(
                conn,
                q,
                mode="smart",
                model_id="bench-384",
                query_vector=q_vec,
                limit=100,
            )
            elapsed = (time.perf_counter() - t0) * 1000.0
            rrf_ms.append(elapsed)
            assert total >= 1 and len(hits) >= 1

        fts_avg, fts_max = sum(fts_ms) / len(fts_ms), max(fts_ms)
        tax_avg, tax_max = sum(tax_ms) / len(tax_ms), max(tax_ms)
        rrf_avg, rrf_max = sum(rrf_ms) / len(rrf_ms), max(rrf_ms)

        print("\n=== 500-Ticket Performance Benchmark (384-dim float32 BLOBs) ===")
        print(f"  FTS5 + Snippets          : avg {fts_avg:.2f} ms | max {fts_max:.2f} ms")
        print(f"  FTS5 + Taxonomy + Client : avg {tax_avg:.2f} ms | max {tax_max:.2f} ms")
        print(f"  Hybrid 500-Vec + RRF     : avg {rrf_avg:.2f} ms | max {rrf_max:.2f} ms")

        assert fts_max < 100.0, f"FTS5 query exceeded 100ms budget: {fts_max:.2f} ms"
        assert tax_max < 100.0, f"Taxonomy filter query exceeded 100ms budget: {tax_max:.2f} ms"
        assert rrf_max < 100.0, f"500-vector Hybrid RRF exceeded 100ms budget: {rrf_max:.2f} ms"
    finally:
        db_mgr.close()
