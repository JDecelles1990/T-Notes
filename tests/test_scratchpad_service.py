"""Unit tests for ScratchpadService and SessionService."""

import pytest
from src.database.connection import DatabaseManager
from src.database.migrations import init_database
from src.repositories.image_repository import ImageRepository
from src.repositories.scratchpad_repository import ScratchpadRepository
from src.repositories.session_repository import SessionRepository
from src.services.image_service import ImageService
from src.services.scratchpad_service import ScratchpadService
from src.services.session_service import SessionService


@pytest.fixture
def services(tmp_path):
    db_file = tmp_path / "test_scratchpads.db"
    manager = DatabaseManager(db_file)
    init_database(manager)

    scratch_repo = ScratchpadRepository(manager)
    img_repo = ImageRepository(manager)
    session_repo = SessionRepository(manager)

    img_service = ImageService(img_repo)
    scratch_service = ScratchpadService(scratch_repo, img_service)
    session_service = SessionService(session_repo, scratch_service)

    yield scratch_service, session_service
    manager.close()


def test_create_and_retrieve_ticket(services):
    scratch_service, _ = services

    ticket = scratch_service.create_ticket(
        ticket_number="INC-500",
        client_name="Globex Corp",
        title="Server Migration",
        content_html="<h3>Pre-Checks</h3>",
    )
    assert ticket["id"] > 0
    assert ticket["ticket_number"] == "INC-500"
    assert ticket["client_name"] == "Globex Corp"

    active = scratch_service.get_active_tickets()
    assert len(active) == 1
    assert active[0]["id"] == ticket["id"]


def test_tab_reordering(services):
    scratch_service, _ = services

    t1 = scratch_service.create_ticket("T-1", tab_order=0)
    t2 = scratch_service.create_ticket("T-2", tab_order=1)

    # Swap order
    scratch_service.update_tab_orders([(t1["id"], 1), (t2["id"], 0)])

    active = scratch_service.get_active_tickets()
    assert active[0]["id"] == t2["id"]
    assert active[1]["id"] == t1["id"]


def test_archive_and_restore(services):
    scratch_service, _ = services

    t = scratch_service.create_ticket("T-ArchiveTest")
    sid = t["id"]

    scratch_service.archive_ticket(sid)
    assert len(scratch_service.get_active_tickets()) == 0
    assert len(scratch_service.get_archived_tickets()) == 1

    restored = scratch_service.restore_ticket(sid)
    assert restored["status"] == "active"


def test_archive_ticket_audit_trail_appended(services):
    scratch_service, _ = services

    # Create ticket with initial notes and 900 seconds (15m) of troubleshooting time
    t = scratch_service.create_ticket(
        ticket_number="INC-AUDIT",
        client_name="Initech",
        title="Server Migration",
        content_html="<p>Migrated domain controller to Azure</p>",
        elapsed_seconds=900,
    )
    sid = t["id"]

    # Archive the ticket
    archived = scratch_service.archive_ticket(sid)
    assert archived is not None
    assert archived["status"] == "archived"
    assert archived["archived_at"] is not None

    # Verify audit summary was appended to the ticket content
    content = archived["content_html"]
    assert "Ticket Archive Audit Summary" in content
    assert "Tab Created:" in content
    assert "Tab Archived:" in content
    assert "Total Tab Open Duration:" in content
    assert "Active Troubleshooting Time:" in content
    assert "00:15:00" in content
    assert "0.25h billable" in content

    assert len(scratch_service.get_active_tickets()) == 0
    assert len(scratch_service.get_archived_tickets()) == 1


def test_clean_text_ticket_note_conversion():
    html = """
    <h3>[ISSUE DESCRIPTION]</h3>
    <p>User reported <strong>Outlook crash</strong> on launch.</p>
    <ul>
        <li>Event ID: 1000</li>
        <li>Faulting module: olmapi32.dll</li>
    </ul>
    <pre>Get-Process outlook</pre>
    <img src="image://local/crash_screen.jpg" />
    """
    clean_text = ScratchpadService.convert_html_to_clean_text(html)

    assert "### [ISSUE DESCRIPTION]" in clean_text
    assert "**Outlook crash**" in clean_text
    assert "• Event ID: 1000" in clean_text
    assert "```\nGet-Process outlook\n```" in clean_text
    assert "[Screenshot: crash_screen.jpg]" in clean_text
    # Verify no raw HTML tags remain
    assert "<p>" not in clean_text
    assert "</li>" not in clean_text


def test_clean_text_checklist_conversion():
    html = """
    <p><a href="task://toggle">[ ]</a> Check disk space</p>
    <p><a href="task://toggle">[✔]</a> <span style="text-decoration: line-through; color: #888888;">Reboot server</span></p>
    <p><a href="task://toggle">[x]</a> Notify customer</p>
    """
    clean_text = ScratchpadService.convert_html_to_clean_text(html)
    assert "- [ ] Check disk space" in clean_text
    assert "- [x] Reboot server" in clean_text
    assert "- [x] Notify customer" in clean_text
    assert "task://toggle" not in clean_text
    assert "<a" not in clean_text


def test_session_service_workspace_restore(services):
    scratch_service, session_service = services

    # If DB is empty, restore_workspace creates an initial tab automatically
    active_tickets, focused_id, _, opacity, _ = session_service.restore_workspace()
    assert len(active_tickets) == 1
    assert focused_id == active_tickets[0]["id"]
    assert opacity == 100

    # Persist workspace state with focused tab and opacity
    session_service.persist_workspace(
        active_scratchpad_id=active_tickets[0]["id"],
        window_geometry="aabbcc",
        window_opacity=85,
        history_drawer_open=True,
    )

    # Verify reload returns exact state
    reloaded_tickets, reloaded_id, geom, reloaded_opacity, drawer = session_service.restore_workspace()
    assert reloaded_id == active_tickets[0]["id"]
    assert geom == "aabbcc"
    assert reloaded_opacity == 85
    assert drawer is True

