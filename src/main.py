"""Main application entry point for TechPad."""

import os
from pathlib import Path
import sys

# When frozen via PyInstaller, stay beside the executable (never chdir into _MEIPASS).
# When running from source (including Windows Startup from System32), add repo root to sys.path.
if getattr(sys, "frozen", False):
    try:
        os.chdir(Path(sys.executable).resolve().parent)
    except OSError:
        pass
else:
    _PROJECT_ROOT = Path(__file__).resolve().parent.parent
    if str(_PROJECT_ROOT) not in sys.path:
        sys.path.insert(0, str(_PROJECT_ROOT))
    try:
        os.chdir(_PROJECT_ROOT)
    except OSError:
        pass

from PySide6.QtCore import QCoreApplication, Qt
from PySide6.QtGui import QFont, QIcon
from PySide6.QtWidgets import QApplication
from src.config import (
    DEFAULT_DB_PATH,
    DEFAULT_QSS_PATH,
    is_frozen,
    migrate_legacy_user_data,
    resource_path,
)
from src.core.constants import APP_NAME
from src.database.connection import DatabaseManager
from src.database.migrations import init_database
from src.repositories.image_repository import ImageRepository
from src.repositories.scratchpad_repository import ScratchpadRepository
from src.repositories.session_repository import SessionRepository
from src.repositories.template_repository import TemplateRepository
from src.services.autostart_service import AutostartService
from src.services.backup_service import BackupService
from src.services.image_service import ImageService
from src.services.scratchpad_service import ScratchpadService
from src.services.session_service import SessionService
from src.ui.components.aurora_tooltip import install_aurora_tooltips
from src.ui.components.system_tray import get_or_create_app_icon
from src.ui.main_window import TechPadMainWindow


def _run_smoke_self_test(
    db_manager: DatabaseManager,
    scratchpad_service: ScratchpadService,
    image_service: ImageService,
    report_path: str | None = None,
) -> int:
    """Opt-in frozen end-to-end verification gated strictly on TNOTES_DB_PATH."""
    import json
    from PySide6.QtGui import QImage, QImageReader, QImageWriter, QTextDocument
    from src.core.paths import get_bundle_root
    from src.database.history_fts import (
        get_taxonomy_seed_path,
        get_ticket_taxonomy,
        list_taxonomy_nodes,
        search_history,
    )
    from src.database.semantic_search import OllamaEmbeddingProvider, search_history_hybrid
    from src.ui.components.taxonomy_pill_selector import persist_taxonomy_assignments
    from src.ui.dialogs.archive_taxonomy_dialog import ArchiveTaxonomyDialog

    conn = db_manager.get_connection()
    seed_path = get_taxonomy_seed_path()
    qss_exists = DEFAULT_QSS_PATH.is_file()
    nodes = list_taxonomy_nodes(conn, active_only=True)
    if not seed_path.is_file() or len(nodes) < 25:
        raise RuntimeError(f"Bundled taxonomy_seed.json missing or incomplete ({len(nodes)} nodes)")

    readers = sorted(bytes(f).decode("ascii").lower() for f in QImageReader.supportedImageFormats())
    writers = sorted(bytes(f).decode("ascii").lower() for f in QImageWriter.supportedImageFormats())
    if "jpeg" not in readers or "jpeg" not in writers or "png" not in readers:
        raise RuntimeError(f"Missing Qt JPEG/PNG plugins: readers={readers}, writers={writers}")

    # 1. Create note, compress & store JPEG screenshot, and register QTextDocument resource
    ticket = scratchpad_service.create_ticket(
        ticket_number="SMOKE-1001",
        client_name="Clinique Saint-Laurent",
        title="Boîte partagée Outlook OST corrompue — profil reconstruit",
        content_html="<p>Initial frozen smoke check note.</p>",
    )
    tid = int(ticket["id"])

    img = QImage(48, 32, QImage.Format_ARGB32)
    img.fill(0xFF1E90FF)
    img_name, img_url, jpeg_bytes, loaded_qimg = image_service.create_embedded_image(img)
    if not jpeg_bytes or loaded_qimg.isNull():
        raise RuntimeError("JPEG compression or Qt JPEG decode failed in frozen runtime")

    html_body = (
        f'<p>Rebuilt Outlook OST for &lt;tech@cliniquesl.ca&gt;.</p>'
        f'<p><img src="{img_url}" /></p>'
    )
    scratchpad_service.save_content(
        scratchpad_id=tid,
        content_html=html_body,
        in_memory_images={img_name: jpeg_bytes},
    )
    doc = QTextDocument()
    image_service.load_scratchpad_images_into_document(tid, doc)
    stored_imgs = image_service.repo.get_images_for_scratchpad(tid)
    if img_name not in stored_imgs or len(stored_imgs[img_name]) == 0:
        raise RuntimeError("Compressed JPEG BLOB was not persisted to scratchpad_images")

    # 2. Archive ticket & tag with ArchiveTaxonomyDialog auto-suggested pills
    dlg = ArchiveTaxonomyDialog(
        ticket_number="SMOKE-1001",
        client_name="Clinique Saint-Laurent",
        title=ticket["title"],
        body_text="Rebuilt Outlook OST cache and verified shared mailbox sync.",
        conn=conn,
    )
    try:
        dlg._on_archive_with_tags()
        assignments = dlg.selected_assignments()
    finally:
        dlg.close()
        dlg.deleteLater()

    if not assignments:
        raise RuntimeError("ArchiveTaxonomyDialog produced 0 auto-suggested taxonomy pills")

    scratchpad_service.archive_ticket(tid)
    persist_taxonomy_assignments(conn, tid, assignments, replace_existing=True)
    saved_tax = get_ticket_taxonomy(conn, tid)
    saved_slugs = [str(r["slug"]) for r in saved_tax]
    if "domain.m365.exchange" not in saved_slugs:
        raise RuntimeError(f"Expected domain.m365.exchange tag, got {saved_slugs}")

    # 3. FTS5 diacritic-insensitive + taxonomy-filtered search
    hits, total = search_history(
        conn,
        "boite partagee",
        client="Clinique Saint-Laurent",
        taxonomy_slugs=["domain.m365.exchange"],
    )
    if total != 1 or hits[0].ticket_number != "SMOKE-1001":
        raise RuntimeError(f"FTS5 history search failed: total={total}, hits={hits}")

    # 4. Graceful offline Ollama fallback check
    offline_provider = OllamaEmbeddingProvider(
        base_url="http://127.0.0.1:59999",
        model_id="bge-m3",
        availability_timeout=0.1,
        embed_timeout=0.1,
    )
    ollama_available = offline_provider.is_available()
    hyb_hits, hyb_total = search_history_hybrid(
        conn,
        "SMOKE-1001",
        mode="smart",
        provider=offline_provider,
    )
    if ollama_available or hyb_total < 1 or hyb_hits[0].ticket_number != "SMOKE-1001":
        raise RuntimeError("Offline Ollama fallback check failed")

    report = {
        "status": "ok",
        "is_frozen": is_frozen(),
        "executable": str(Path(sys.executable).resolve()),
        "bundle_root": str(get_bundle_root()),
        "db_path": str(db_manager.db_path),
        "user_version": int(conn.execute("PRAGMA user_version").fetchone()[0]),
        "journal_mode": str(conn.execute("PRAGMA journal_mode").fetchone()[0]),
        "qss_exists": qss_exists,
        "taxonomy_seed_path": str(seed_path),
        "taxonomy_node_count": len(nodes),
        "jpeg_bytes": len(jpeg_bytes),
        "assigned_taxonomy_slugs": saved_slugs,
        "fts5_hits": total,
        "fts5_snippet_html": hits[0].snippet_html,
        "offline_ollama_fallback_ok": (not ollama_available) and hyb_total >= 1,
    }
    if report_path:
        rp = Path(report_path)
        rp.parent.mkdir(parents=True, exist_ok=True)
        rp.write_text(json.dumps(report, indent=2, ensure_ascii=False), encoding="utf-8")
    return 0


def main() -> int:
    """Initializes services, loads stylesheet, and executes the PySide6 application."""
    is_smoke_self_test = "--smoke-self-test" in sys.argv
    smoke_report_path: str | None = None
    if "--smoke-report" in sys.argv:
        idx = sys.argv.index("--smoke-report")
        if idx + 1 < len(sys.argv):
            smoke_report_path = sys.argv[idx + 1]

    if is_smoke_self_test and not os.environ.get("TNOTES_DB_PATH", "").strip():
        print("Refusing --smoke-self-test without TNOTES_DB_PATH set.", file=sys.stderr)
        return 2

    # Enable High DPI scaling
    os.environ["QT_AUTO_SCREEN_SCALE_FACTOR"] = "1"

    # Ensure Qt discovers bundled imageformat plugins (qjpeg, qico, etc.) when frozen
    if is_frozen():
        qt_plugins = resource_path("PySide6", "plugins")
        if qt_plugins.is_dir():
            QCoreApplication.addLibraryPath(str(qt_plugins))

    app = QApplication(sys.argv)
    app.setQuitOnLastWindowClosed(False)
    app.setApplicationName(APP_NAME)
    app.setOrganizationName("MSP Tools")
    app.setWindowIcon(get_or_create_app_icon())

    # Set default clean system font
    font = QFont("Segoe UI", 10)
    app.setFont(font)

    # Apply Dark Theme QSS
    if DEFAULT_QSS_PATH.exists():
        with open(DEFAULT_QSS_PATH, "r", encoding="utf-8") as f:
            app.setStyleSheet(f.read())

    # Install global Neon Aurora hover tooltips (does not modify any buttons)
    install_aurora_tooltips(app)

    _sandbox_db_override = bool(os.environ.get("TNOTES_DB_PATH", "").strip())

    # Migrate legacy TechPad SQLite data & backups into %APPDATA%\T-Notes if needed
    if not _sandbox_db_override:
        try:
            migrate_legacy_user_data()
        except Exception as e:
            print(f"Warning: Legacy user data migration skipped: {e}", file=sys.stderr)

    # Initialize Database & Run Migrations
    db_manager = DatabaseManager(DEFAULT_DB_PATH)
    init_database(db_manager)

    # Initialize Repositories (Data Access Layer)
    scratchpad_repo = ScratchpadRepository(db_manager)
    image_repo = ImageRepository(db_manager)
    session_repo = SessionRepository(db_manager)
    template_repo = TemplateRepository(db_manager)

    # Initialize Services (Business Logic Layer)
    image_service = ImageService(image_repo)
    scratchpad_service = ScratchpadService(scratchpad_repo, image_service, template_repo)
    session_service = SessionService(session_repo, scratchpad_service)
    autostart_service = AutostartService()
    backup_service = BackupService(db_manager, scratchpad_repo, image_repo)

    # Ensure Windows Startup registry entry matches user preference (enabled by default)
    autostart_pref = session_service.get_setting("autostart_enabled", "true").lower() == "true"
    if autostart_pref and not _sandbox_db_override:
        try:
            autostart_service.set_enabled(True)
        except Exception as e:
            print(f"Warning: Windows startup could not be registered: {e}", file=sys.stderr)

    # Automatic Daily Database Snapshot (rolling 7-day retention)
    if not _sandbox_db_override:
        try:
            backup_service.maybe_run_daily_backup(retention_days=7)
        except Exception as e:
            print(f"Warning: Daily backup could not be created: {e}", file=sys.stderr)

    if is_smoke_self_test:
        try:
            return _run_smoke_self_test(
                db_manager=db_manager,
                scratchpad_service=scratchpad_service,
                image_service=image_service,
                report_path=smoke_report_path,
            )
        finally:
            db_manager.close()

    # Launch Main Window (Presentation Layer)
    window = TechPadMainWindow(
        scratchpad_service=scratchpad_service,
        image_service=image_service,
        session_service=session_service,
        autostart_service=autostart_service,
        backup_service=backup_service,
    )

    # Evaluate Startup Mode (--tray flag and Smart Restore)
    is_tray_flag = "--tray" in sys.argv
    smart_restore = session_service.get_setting("smart_restore_enabled", "true").lower() == "true"
    last_state = session_service.get_setting("last_window_state", "visible")

    if is_tray_flag:
        if smart_restore and last_state == "visible":
            window.show()
        else:
            window.hide()
            if getattr(window, "tray_icon", None) and hasattr(window.tray_icon, "show_message"):
                window.tray_icon.show_message(
                    f"{APP_NAME} Active",
                    f"{APP_NAME} is running in the background. Press F8 to open.",
                    timeout=3500,
                )
    else:
        window.show()

    return app.exec()


if __name__ == "__main__":
    sys.exit(main())
