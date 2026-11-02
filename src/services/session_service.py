"""Session management service for workspace state restoration and persistence."""

from typing import Any, Dict, List, Optional, Tuple
from src.repositories.session_repository import SessionRepository
from src.services.scratchpad_service import ScratchpadService


class SessionService:
    """Manages restoring and persisting open tabs, active selection, and window state."""

    def __init__(self, session_repo: SessionRepository, scratchpad_service: ScratchpadService):
        self.session_repo = session_repo
        self.scratchpad_service = scratchpad_service

    def restore_workspace(self) -> Tuple[List[Dict[str, Any]], Optional[int], str, bool]:
        """
        Loads the active tabs in saved order, determines the focused scratchpad ID,
        window geometry, and history drawer visibility.
        If no active tabs exist, creates a fresh default ticket scratchpad.
        Returns: (active_tickets, focused_scratchpad_id, window_geometry, history_drawer_open)
        """
        session = self.session_repo.get_session() or {}
        active_tickets = self.scratchpad_service.get_active_tickets()

        if not active_tickets:
            # Create an initial ticket so the user has an immediate scratchpad
            initial_ticket = self.scratchpad_service.create_ticket(
                ticket_number="INC-1001",
                client_name="Internal IT",
                title="Daily Scratchpad",
                content_html="<h2>Welcome to TechPad 🚀</h2><p>Use this tab for troubleshooting notes, CLI logs, and screenshot snips (<strong>Win+Shift+S</strong>).</p>",
            )
            active_tickets = [initial_ticket]

        saved_active_id = session.get("active_scratchpad_id")
        active_ids = {t["id"] for t in active_tickets}

        if saved_active_id not in active_ids:
            # Default to the first active tab
            focused_id = active_tickets[0]["id"]
        else:
            focused_id = saved_active_id

        window_geometry = session.get("window_geometry", "") or ""
        history_drawer_open = bool(session.get("history_drawer_open", 0))

        return active_tickets, focused_id, window_geometry, history_drawer_open

    def persist_workspace(
        self,
        active_scratchpad_id: Optional[int],
        window_geometry: str = "",
        history_drawer_open: bool = False,
    ) -> None:
        """Saves current focused scratchpad ID, window geometry, and drawer visibility."""
        self.session_repo.save_session(
            active_scratchpad_id=active_scratchpad_id,
            window_geometry=window_geometry,
            history_drawer_open=history_drawer_open,
        )

