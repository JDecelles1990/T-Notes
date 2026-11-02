"""Business logic service for scratchpad operations and note formatting."""

import re
from typing import Any, Dict, List, Optional, Tuple
from src.core.constants import STATUS_ACTIVE, STATUS_ARCHIVED, TICKET_SKELETONS
from src.repositories.image_repository import ImageRepository
from src.repositories.scratchpad_repository import ScratchpadRepository
from src.services.image_service import ImageService


class ScratchpadService:
    """Orchestrates scratchpad creation, persistence, image synchronization, and note export."""

    def __init__(
        self,
        scratchpad_repo: ScratchpadRepository,
        image_service: ImageService,
    ):
        self.repo = scratchpad_repo
        self.image_service = image_service

    def create_ticket(
        self,
        ticket_number: str = "",
        client_name: str = "",
        title: str = "",
        content_html: str = "",
        tab_order: Optional[int] = None,
    ) -> Dict[str, Any]:
        """Creates a new active ticket scratchpad."""
        active = self.repo.get_active()
        if tab_order is None:
            tab_order = len(active)

        if not ticket_number.strip():
            # Generate next default ticket number
            ticket_number = f"T-{len(active) + 101}"

        scratchpad_id = self.repo.create(
            ticket_number=ticket_number,
            client_name=client_name,
            title=title,
            content_html=content_html,
            status=STATUS_ACTIVE,
            tab_order=tab_order,
        )
        return self.repo.get_by_id(scratchpad_id) or {}

    def get_ticket(self, scratchpad_id: int) -> Optional[Dict[str, Any]]:
        """Retrieves ticket data by ID."""
        return self.repo.get_by_id(scratchpad_id)

    def get_active_tickets(self) -> List[Dict[str, Any]]:
        """Retrieves all active tickets in tab order."""
        return self.repo.get_active()

    def get_archived_tickets(self, limit: int = 100, offset: int = 0) -> List[Dict[str, Any]]:
        """Retrieves archived tickets."""
        return self.repo.get_archived(limit=limit, offset=offset)

    def save_content(
        self,
        scratchpad_id: int,
        content_html: str,
        in_memory_images: Dict[str, bytes],
    ) -> None:
        """Persists HTML content and syncs referenced images."""
        self.repo.update_content(scratchpad_id, content_html)
        self.image_service.sync_scratchpad_images(scratchpad_id, content_html, in_memory_images)

    def update_metadata(
        self,
        scratchpad_id: int,
        ticket_number: str,
        client_name: str,
        title: str,
    ) -> None:
        """Updates ticket metadata."""
        self.repo.update_metadata(scratchpad_id, ticket_number, client_name, title)

    def update_tab_orders(self, orders: List[Tuple[int, int]]) -> None:
        """Updates tab ordering for active scratchpads."""
        self.repo.update_tab_orders(orders)

    def archive_ticket(self, scratchpad_id: int) -> None:
        """Archives a ticket, moving it out of active tabs."""
        self.repo.archive(scratchpad_id)

    def restore_ticket(self, scratchpad_id: int) -> Optional[Dict[str, Any]]:
        """Restores an archived ticket as the last active tab."""
        active = self.repo.get_active()
        next_order = len(active)
        self.repo.restore(scratchpad_id, next_order)
        return self.repo.get_by_id(scratchpad_id)

    def delete_ticket_permanently(self, scratchpad_id: int) -> None:
        """Permanently deletes a scratchpad and all its images."""
        self.repo.delete_permanently(scratchpad_id)

    def search_tickets(self, query: str, status: Optional[str] = None) -> List[Dict[str, Any]]:
        """Performs full-text search across tickets."""
        return self.repo.search(query=query, status=status)

    def get_skeleton_names(self) -> List[str]:
        """Returns the list of available ticket skeleton template names."""
        return list(TICKET_SKELETONS.keys())

    def get_skeleton_html(self, name: str) -> str:
        """Returns the HTML for the named template skeleton."""
        return TICKET_SKELETONS.get(name, "")

    def export_as_plain_ticket_note(self, scratchpad_id: int) -> str:
        """
        Strips rich HTML formatting into clean plain text / Markdown,
        formatted for pasting into ticketing systems (ServiceNow, Jira, HaloPSA).
        """
        ticket = self.repo.get_by_id(scratchpad_id)
        if not ticket:
            return ""

        header_lines = [
            f"=== TICKET: {ticket.get('ticket_number', '')} ===",
        ]
        if ticket.get("client_name"):
            header_lines.append(f"Client: {ticket['client_name']}")
        if ticket.get("title"):
            header_lines.append(f"Subject: {ticket['title']}")
        header_lines.append("=" * 30 + "\n")

        html = ticket.get("content_html", "") or ""
        body = self.convert_html_to_clean_text(html)
        return "\n".join(header_lines) + body

    @staticmethod
    def convert_html_to_clean_text(html: str) -> str:
        """Converts HTML markup to clean readable plain text / Markdown."""
        if not html:
            return ""

        text = html
        # Replace line breaks and paragraphs
        text = re.sub(r'<br\s*/?>', '\n', text, flags=re.IGNORECASE)
        text = re.sub(r'</p>', '\n', text, flags=re.IGNORECASE)
        text = re.sub(r'</h1>', '\n\n', text, flags=re.IGNORECASE)
        text = re.sub(r'</h2>', '\n\n', text, flags=re.IGNORECASE)
        text = re.sub(r'</h3>', '\n\n', text, flags=re.IGNORECASE)
        text = re.sub(r'</h4>', '\n\n', text, flags=re.IGNORECASE)
        text = re.sub(r'</h1>', '\n', text, flags=re.IGNORECASE)

        # Replace headings
        text = re.sub(r'<h1[^>]*>', '# ', text, flags=re.IGNORECASE)
        text = re.sub(r'<h2[^>]*>', '## ', text, flags=re.IGNORECASE)
        text = re.sub(r'<h3[^>]*>', '### ', text, flags=re.IGNORECASE)
        text = re.sub(r'<h4[^>]*>', '#### ', text, flags=re.IGNORECASE)

        # Format lists
        text = re.sub(r'<li[^>]*>', '• ', text, flags=re.IGNORECASE)
        text = re.sub(r'</li>', '\n', text, flags=re.IGNORECASE)

        # Format bold & italic
        text = re.sub(r'<(?:strong|b)[^>]*>(.*?)</(?:strong|b)>', r'**\1**', text, flags=re.IGNORECASE | re.DOTALL)
        text = re.sub(r'<(?:em|i)[^>]*>(.*?)</(?:em|i)>', r'*\1*', text, flags=re.IGNORECASE | re.DOTALL)

        # Replace image tags with a clean placeholder
        text = re.sub(r'<img[^>]*src=["\']image://local/([^"\'>]+)["\'][^>]*>', r'[Screenshot: \1]', text, flags=re.IGNORECASE)

        # Format code blocks / pre
        text = re.sub(r'<pre[^>]*>(.*?)</pre>', r'```\n\1\n```', text, flags=re.IGNORECASE | re.DOTALL)
        text = re.sub(r'<code[^>]*>(.*?)</code>', r'`\1`', text, flags=re.IGNORECASE | re.DOTALL)

        # Remove remaining HTML tags
        text = re.sub(r'<[^>]+>', '', text)

        # Decode common HTML entities
        text = text.replace('&nbsp;', ' ')
        text = text.replace('&amp;', '&')
        text = text.replace('&lt;', '<')
        text = text.replace('&gt;', '>')
        text = text.replace('&quot;', '"')
        text = text.replace('&#39;', "'")

        # Normalize redundant empty lines
        text = re.sub(r'\n{3,}', '\n\n', text)
        return text.strip()
