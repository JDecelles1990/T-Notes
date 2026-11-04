"""Session management service for workspace state restoration, settings, and persistence."""

from typing import Any, Dict, List, Optional, Tuple
from src.repositories.session_repository import SessionRepository
from src.services.scratchpad_service import ScratchpadService


class SessionService:
    """Manages restoring and persisting open tabs, active selection, window state, and settings."""

    def __init__(self, session_repo: SessionRepository, scratchpad_service: ScratchpadService):
        self.session_repo = session_repo
        self.scratchpad_service = scratchpad_service

    def restore_workspace(self) -> Tuple[List[Dict[str, Any]], Optional[int], str, int, bool]:
        """
        Loads the active tabs in saved order, determines the focused scratchpad ID,
        window geometry, window opacity, and history drawer visibility.
        If no active tabs exist, creates a fresh default ticket scratchpad.
        Returns: (active_tickets, focused_scratchpad_id, window_geometry, window_opacity, history_drawer_open)
        """
        session = self.session_repo.get_session() or {}
        active_tickets = self.scratchpad_service.get_active_tickets()

        if not active_tickets:
            # Create an initial ticket so the user has an immediate scratchpad
            prefix = self.get_setting("ticket_prefix", "INC-")
            initial_ticket = self.scratchpad_service.create_ticket(
                ticket_number=f"{prefix}1001",
                client_name="Internal IT",
                title="Daily Scratchpad",
                content_html="<h2>Welcome to T-Notes 🚀</h2><p>Use this tab for troubleshooting notes, CLI logs, and screenshot snips (<strong>Win+Shift+S</strong>).</p>",
            )
            active_tickets = [initial_ticket]

        saved_active_id = session.get("active_scratchpad_id")
        active_ids = {t["id"] for t in active_tickets}

        if saved_active_id not in active_ids:
            focused_id = active_tickets[0]["id"]
        else:
            focused_id = saved_active_id

        window_geometry = session.get("window_geometry", "") or ""
        window_opacity = int(session.get("window_opacity", 100))
        history_drawer_open = bool(session.get("history_drawer_open", 0))

        return active_tickets, focused_id, window_geometry, window_opacity, history_drawer_open

    def persist_workspace(
        self,
        active_scratchpad_id: Optional[int],
        window_geometry: str = "",
        window_opacity: int = 100,
        history_drawer_open: bool = False,
        split_view_active: bool = False,
        split_active_scratchpad_id: Optional[int] = None,
        primary_scratchpad_ids: str = "",
        secondary_scratchpad_ids: str = "",
        split_sizes: str = "",
    ) -> None:
        """Saves current focused scratchpad ID, window geometry, opacity, drawer visibility, and split view state."""
        self.session_repo.save_session(
            active_scratchpad_id=active_scratchpad_id,
            window_geometry=window_geometry,
            window_opacity=window_opacity,
            history_drawer_open=history_drawer_open,
            split_view_active=split_view_active,
            split_active_scratchpad_id=split_active_scratchpad_id,
            primary_scratchpad_ids=primary_scratchpad_ids,
            secondary_scratchpad_ids=secondary_scratchpad_ids,
            split_sizes=split_sizes,
        )

    def get_split_view_session(self) -> Dict[str, Any]:
        """Returns saved split view state, pane allocations, and splitter sizes."""
        session = self.session_repo.get_session() or {}
        return {
            "split_view_active": bool(session.get("split_view_active", 0)),
            "split_active_scratchpad_id": session.get("split_active_scratchpad_id"),
            "primary_scratchpad_ids": session.get("primary_scratchpad_ids", "") or "",
            "secondary_scratchpad_ids": session.get("secondary_scratchpad_ids", "") or "",
            "split_sizes": session.get("split_sizes", "") or "",
        }

    def get_settings(self) -> Dict[str, str]:
        """Returns all configuration settings."""
        return self.session_repo.get_all_settings()

    def get_setting(self, key: str, default: str = "") -> str:
        """Returns a single configuration setting."""
        return self.session_repo.get_setting(key, default)

    def save_settings(self, settings: Dict[str, str]) -> None:
        """Saves updated settings."""
        self.session_repo.set_settings(settings)
