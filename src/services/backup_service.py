"""Automated SQLite database snapshot backups and bulk notes ZIP export."""

from datetime import datetime, timedelta
import json
from pathlib import Path
import re
import sqlite3
from typing import Any, Dict, List, Optional, Set
import zipfile

from src.config import DEFAULT_DB_PATH
from src.database.connection import DatabaseManager
from src.repositories.image_repository import ImageRepository
from src.repositories.scratchpad_repository import ScratchpadRepository


class BackupService:
    """Manages online daily database snapshots with 7-day retention and bulk ZIP exports."""

    def __init__(
        self,
        db_manager: DatabaseManager,
        scratchpad_repo: Optional[ScratchpadRepository] = None,
        image_repo: Optional[ImageRepository] = None,
        backup_dir: Optional[Path] = None,
    ):
        self.db_manager = db_manager
        self.scratchpad_repo = scratchpad_repo or ScratchpadRepository(db_manager)
        self.image_repo = image_repo or ImageRepository(db_manager)
        self.backup_dir = backup_dir or (DEFAULT_DB_PATH.parent / "backups")
        self.backup_dir.mkdir(parents=True, exist_ok=True)

    def create_backup_snapshot(self, custom_path: Optional[Path] = None, retention_days: int = 7) -> Path:
        """
        Creates a consistent, online SQLite database snapshot using SQLite's backup API.
        Guarantees zero database locking, WAL consistency, and prunes snapshots older than retention_days.
        """
        today_str = datetime.now().strftime("%Y-%m-%d")
        target_path = custom_path or (self.backup_dir / f"techpad_{today_str}.db.bak")
        target_path.parent.mkdir(parents=True, exist_ok=True)

        source_conn = self.db_manager.get_connection()
        dest_conn = sqlite3.connect(str(target_path))
        try:
            source_conn.backup(dest_conn)
        finally:
            dest_conn.close()

        self.purge_old_backups(retention_days=retention_days)
        return target_path

    def maybe_run_daily_backup(self, retention_days: int = 7) -> Optional[Path]:
        """Runs the daily snapshot if none exists for today."""
        today_str = datetime.now().strftime("%Y-%m-%d")
        expected_file = self.backup_dir / f"techpad_{today_str}.db.bak"
        if not expected_file.exists():
            return self.create_backup_snapshot(expected_file, retention_days=retention_days)
        return None

    def purge_old_backups(self, retention_days: int = 7) -> int:
        """Deletes database snapshots older than retention_days."""
        cutoff = datetime.now() - timedelta(days=retention_days)
        purged = 0
        for item in self.backup_dir.glob("techpad_*.db.bak"):
            try:
                mtime = datetime.fromtimestamp(item.stat().st_mtime)
                if mtime < cutoff:
                    item.unlink(missing_ok=True)
                    purged += 1
            except Exception:
                pass
        return purged

    def list_backups(self) -> List[Dict[str, Any]]:
        """Lists available backup snapshots sorted newest first."""
        results = []
        for item in sorted(self.backup_dir.glob("techpad_*.db.bak"), reverse=True):
            try:
                stat = item.stat()
                results.append({
                    "filename": item.name,
                    "path": str(item),
                    "size_bytes": stat.st_size,
                    "created_at": datetime.fromtimestamp(stat.st_mtime).strftime("%Y-%m-%d %H:%M:%S"),
                })
            except Exception:
                pass
        return results

    def export_all_notes_to_zip(self, zip_path: Path) -> Path:
        """
        Exports all active and archived tickets into a self-contained ZIP archive
        containing Markdown notes with YAML frontmatter, embedded images, and manifest.json.
        """
        zip_path = Path(zip_path)
        zip_path.parent.mkdir(parents=True, exist_ok=True)

        active_tickets = self.scratchpad_repo.get_active()
        archived_tickets = self.scratchpad_repo.get_archived(limit=999999)
        all_tickets = active_tickets + archived_tickets

        manifest_entries = []
        collected_images: Dict[str, bytes] = {}

        with zipfile.ZipFile(str(zip_path), "w", zipfile.ZIP_DEFLATED) as zf:
            for ticket in all_tickets:
                tid = ticket["id"]
                ticket_num = ticket.get("ticket_number") or f"TICK-{tid}"
                clean_num = re.sub(r'[^a-zA-Z0-9_\-]', '_', ticket_num)
                title = ticket.get("title") or "Untitled"
                clean_title = re.sub(r'[^a-zA-Z0-9_\-]', '_', title)[:40].strip('_')
                filename = f"{clean_num}_{clean_title}.md" if clean_title else f"{clean_num}.md"

                # Fetch images for this ticket
                images = self.image_repo.get_images_for_scratchpad(tid)
                for img_name, img_bytes in images.items():
                    collected_images[img_name] = img_bytes

                # Format markdown content
                html = ticket.get("content_html") or ""
                md_content = self._html_to_clean_markdown(html)

                frontmatter = (
                    f"---\n"
                    f"id: {tid}\n"
                    f"ticket_number: \"{ticket_num}\"\n"
                    f"client_name: \"{ticket.get('client_name', '')}\"\n"
                    f"title: \"{title}\"\n"
                    f"status: \"{ticket.get('status', 'active')}\"\n"
                    f"created_at: \"{ticket.get('created_at', '')}\"\n"
                    f"updated_at: \"{ticket.get('updated_at', '')}\"\n"
                    f"duration_seconds: {ticket.get('duration_seconds', 0)}\n"
                    f"---\n\n"
                    f"# {ticket_num}: {title}\n\n"
                    f"{md_content}\n"
                )

                zf.writestr(f"tickets/{filename}", frontmatter.encode("utf-8"))

                manifest_entries.append({
                    "id": tid,
                    "ticket_number": ticket_num,
                    "title": title,
                    "client_name": ticket.get("client_name", ""),
                    "status": ticket.get("status", "active"),
                    "file": f"tickets/{filename}",
                    "image_count": len(images),
                })

            # Write collected images
            for img_name, img_bytes in collected_images.items():
                zf.writestr(f"images/{img_name}", img_bytes)

            # Write manifest.json
            manifest_data = {
                "export_date": datetime.now().strftime("%Y-%m-%d %H:%M:%S"),
                "total_tickets": len(all_tickets),
                "total_images": len(collected_images),
                "tickets": manifest_entries,
            }
            zf.writestr("manifest.json", json.dumps(manifest_data, indent=2).encode("utf-8"))

        return zip_path

    @staticmethod
    def _html_to_clean_markdown(html: str) -> str:
        """Converts HTML markup into readable Markdown with image and checklist formatting."""
        if not html:
            return ""

        text = html
        # Convert images: image://local/<uuid>.jpg -> ![Screenshot](../images/<uuid>.jpg)
        text = re.sub(
            r'<img[^>]*src=["\'](?:image://local/)?([^"\']+)["\'][^>]*>',
            r'![Screenshot](../images/\1)',
            text,
            flags=re.IGNORECASE,
        )

        # Convert checklists
        text = re.sub(r'<a[^>]*href=["\']task://toggle["\'][^>]*>\[\s*\]</a>', '- [ ]', text, flags=re.IGNORECASE)
        text = re.sub(r'<a[^>]*href=["\']task://toggle["\'][^>]*>\[[✔xX]\]</a>', '- [x]', text, flags=re.IGNORECASE)

        # Convert headings
        text = re.sub(r'<h1[^>]*>(.*?)</h1>', r'# \1\n\n', text, flags=re.IGNORECASE | re.DOTALL)
        text = re.sub(r'<h2[^>]*>(.*?)</h2>', r'## \1\n\n', text, flags=re.IGNORECASE | re.DOTALL)
        text = re.sub(r'<h3[^>]*>(.*?)</h3>', r'### \1\n\n', text, flags=re.IGNORECASE | re.DOTALL)

        # Convert code blocks
        text = re.sub(r'<div[^>]*font-family:\s*Consolas[^>]*>.*?<code>(.*?)</code>.*?</div>', r'```\n\1\n```\n\n', text, flags=re.IGNORECASE | re.DOTALL)

        # Convert simple tags
        text = re.sub(r'<strong[^>]*>(.*?)</strong>', r'**\1**', text, flags=re.IGNORECASE | re.DOTALL)
        text = re.sub(r'<b[^>]*>(.*?)</b>', r'**\1**', text, flags=re.IGNORECASE | re.DOTALL)
        text = re.sub(r'<em[^>]*>(.*?)</em>', r'*\1*', text, flags=re.IGNORECASE | re.DOTALL)
        text = re.sub(r'<i[^>]*>(.*?)</i>', r'*\1*', text, flags=re.IGNORECASE | re.DOTALL)

        # Line breaks and paragraphs
        text = re.sub(r'<br\s*/?>', '\n', text, flags=re.IGNORECASE)
        text = re.sub(r'</p>', '\n\n', text, flags=re.IGNORECASE)

        # Strip remaining tags
        text = re.sub(r'<[^>]+>', '', text)

        # Unescape HTML entities
        text = (
            text.replace('&nbsp;', ' ')
            .replace('&amp;', '&')
            .replace('&lt;', '<')
            .replace('&gt;', '>')
            .replace('&quot;', '"')
            .replace('&#39;', "'")
        )

        # Clean excess blank lines
        return re.sub(r'\n{3,}', '\n\n', text).strip()

