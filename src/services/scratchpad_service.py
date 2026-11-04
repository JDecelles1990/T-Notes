"""Business logic service for scratchpad operations and note formatting."""

import re
from dataclasses import dataclass
from datetime import datetime, timezone
from typing import Any, Dict, List, Optional, Tuple
from src.core.constants import STATUS_ACTIVE, STATUS_ARCHIVED, TICKET_SKELETONS
from src.repositories.image_repository import ImageRepository
from src.repositories.scratchpad_repository import ScratchpadRepository
from src.repositories.template_repository import TemplateRepository
from src.services.image_service import ImageService
from src.services.stopwatch_service import StopwatchService


@dataclass(frozen=True)
class SaveReceipt:
    """Application acknowledgement; never an M365 wire envelope or approval.

    Errors raise before any saved receipt exists. Synchronous callers own the
    attempted editor revision and must reject an acknowledgement for older edits.
    """

    ticket_id: int
    attempted_revision: int
    persisted_revision: int | None
    status: str
    error_code: str | None = None


class ScratchpadService:
    """Orchestrates scratchpad creation, persistence, image synchronization, and note export."""

    def __init__(
        self,
        scratchpad_repo: ScratchpadRepository,
        image_service: ImageService,
        template_repo: Optional[TemplateRepository] = None,
    ):
        self.repo = scratchpad_repo
        self.image_service = image_service
        self.template_repo = template_repo or TemplateRepository(scratchpad_repo.db)

    def create_ticket(
        self,
        ticket_number: str = "",
        client_name: str = "",
        title: str = "",
        content_html: str = "",
        tab_order: Optional[int] = None,
        elapsed_seconds: int = 0,
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
            elapsed_seconds=elapsed_seconds,
        )
        return self.repo.get_by_id(scratchpad_id) or {}

    def update_elapsed_time(self, scratchpad_id: int, elapsed_seconds: int) -> None:
        """Persists cumulative troubleshooting time in seconds."""
        self.repo.update_elapsed_time(scratchpad_id, elapsed_seconds)

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
        expected_revision: int = 0,
    ) -> SaveReceipt:
        """Acknowledge the snapshot only after HTML and images commit together."""
        active = self.image_service.extract_referenced_image_names(content_html)
        self.repo.save_content_with_images(scratchpad_id, content_html, dict(in_memory_images), active)
        return SaveReceipt(scratchpad_id, expected_revision, expected_revision, "saved")

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

    def archive_ticket(self, scratchpad_id: int) -> Optional[Dict[str, Any]]:
        """
        Archives a ticket:
        1. Captures the creation time and archiving timestamp.
        2. Computes the total lifespan the tab was open (wall-clock duration).
        3. Appends a structured audit summary block to the ticket's HTML content.
        4. Updates status to 'archived' and records archived_at timestamp.
        """
        ticket = self.repo.get_by_id(scratchpad_id)
        if not ticket:
            return None

        now_dt = datetime.now(timezone.utc)
        archived_at_str = now_dt.strftime("%Y-%m-%d %H:%M:%S")

        # Parse created_at and calculate total open duration
        created_str = str(ticket.get("created_at", ""))
        total_open_str = "N/A"
        if created_str:
            for fmt in ("%Y-%m-%d %H:%M:%S", "%Y-%m-%dT%H:%M:%S"):
                try:
                    created_dt = datetime.strptime(created_str.split(".")[0], fmt).replace(tzinfo=timezone.utc)
                    delta = now_dt - created_dt
                    total_secs = int(max(0, delta.total_seconds()))
                    hrs = total_secs // 3600
                    mins = (total_secs % 3600) // 60
                    secs = total_secs % 60
                    if hrs > 0:
                        total_open_str = f"{hrs}h {mins}m {secs}s"
                    elif mins > 0:
                        total_open_str = f"{mins}m {secs}s"
                    else:
                        total_open_str = f"{secs}s"
                    break
                except ValueError:
                    continue

        elapsed_seconds = ticket.get("elapsed_seconds", 0) or 0
        stopwatch_fmt = StopwatchService.format_time(elapsed_seconds)

        # Generate audit footer HTML
        audit_html = (
            f'<div class="ticket-archive-audit" style="margin-top: 20px; padding: 10px 14px; '
            f'background-color: #1e1e1e; border: 1px solid #3c3c3c; border-left: 4px solid #007acc; '
            f'border-radius: 4px; font-family: Consolas, monospace; font-size: 11px; color: #a0a0a0;">'
            f'<div style="font-weight: bold; color: #4fc1ff; margin-bottom: 6px;">📦 Ticket Archive Audit Summary</div>'
            f'<div>• <b>Tab Created:</b> {created_str} UTC</div>'
            f'<div>• <b>Tab Archived:</b> {archived_at_str} UTC</div>'
            f'<div>• <b>Total Tab Open Duration:</b> {total_open_str}</div>'
            f'<div>• <b>Active Troubleshooting Time:</b> {stopwatch_fmt.display} ({stopwatch_fmt.rounded_15m} billable)</div>'
            f'</div>'
        )

        current_html = ticket.get("content_html", "") or ""
        # Strip any existing audit block if re-archiving
        clean_html = re.sub(r'<div class="ticket-archive-audit".*?</div>\s*</div>', '', current_html, flags=re.DOTALL)
        updated_html = f"{clean_html.rstrip()}<br/>{audit_html}"

        self.repo.update_content(scratchpad_id, updated_html)
        self.repo.archive(scratchpad_id, archived_at=archived_at_str)
        return self.repo.get_by_id(scratchpad_id)

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
        """Returns the HTML for the named template skeleton or custom template."""
        if name in TICKET_SKELETONS:
            return TICKET_SKELETONS[name]
        custom = self.template_repo.get_by_title(name)
        if custom:
            return custom.get("content_html", "")
        return ""

    def get_custom_templates(self) -> List[Dict[str, Any]]:
        """Returns all custom user-defined templates."""
        return self.template_repo.get_all()

    def get_custom_template_titles(self) -> List[str]:
        """Returns titles of all custom user-defined templates."""
        return [t["title"] for t in self.template_repo.get_all()]

    def add_custom_template(self, title: str, content_html: str) -> int:
        """
        Validates and adds or updates a custom user template.
        Raises ValueError if title or content is empty.
        """
        clean_title = title.strip()
        if not clean_title:
            raise ValueError("Template title cannot be empty.")
        if not content_html or not content_html.strip():
            raise ValueError("Template content cannot be empty.")
        return self.template_repo.create(clean_title, content_html)

    def delete_custom_template(self, template_id: int) -> bool:
        """Deletes a custom template by its ID."""
        return self.template_repo.delete(template_id)

    def delete_custom_template_by_title(self, title: str) -> bool:
        """Deletes a custom template by its title."""
        return self.template_repo.delete_by_title(title)

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
        if ticket.get("elapsed_seconds"):
            hours = ticket["elapsed_seconds"] // 3600
            mins = (ticket["elapsed_seconds"] % 3600) // 60
            secs = ticket["elapsed_seconds"] % 60
            import math
            blocks = max(1, math.ceil(ticket["elapsed_seconds"] / 900))
            rounded = f"{blocks * 0.25:.2f}h"
            header_lines.append(f"Time Logged: {hours:02d}:{mins:02d}:{secs:02d} ({rounded} billable)")
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

        # Convert interactive checklists to Markdown task lists (- [ ] / - [x])
        text = re.sub(r'<a[^>]*href=["\']task://toggle["\'][^>]*>\s*\[\s*\]\s*</a>\s*', '- [ ] ', text, flags=re.IGNORECASE)
        text = re.sub(r'<a[^>]*href=["\']task://toggle["\'][^>]*>\s*\[(?:✔|x|X)\]\s*</a>\s*', '- [x] ', text, flags=re.IGNORECASE)

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

