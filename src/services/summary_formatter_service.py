"""Bilingual Client & PSA Ticket Summary Formatter Service (English & Français).

Parses raw ticket notes, detects structured sections in both English and French,
and formats them into client-ready resolution emails, standardized PSA notes,
and escalation handovers with billable time calculations.
"""

from dataclasses import dataclass, field
import html
import math
import re
from typing import Optional


@dataclass
class ParsedTicketSections:
    """Structured fields extracted from a ticket note."""
    ticket_number: str = ""
    client_name: str = ""
    title: str = ""
    elapsed_seconds: int = 0
    issue: str = ""
    work_performed: str = ""
    resolution: str = ""
    root_cause: str = ""
    next_steps: str = ""
    technician_name: str = ""
    technician_email: str = ""


class SummaryFormatterService:
    """Service providing smart bilingual section parsing and formatting for ticket summaries."""

    # Bilingual heading regex patterns
    RE_ISSUE = re.compile(
        r"^(?:#+\s*)?(?:issue|problem|symptoms?|reported(?:\s+issue)?|probl[èe]me|sympt[ôo]mes?|incident(?:\s+signal[ée])?|description)\s*[:\-\—]?",
        re.IGNORECASE,
    )
    RE_WORK = re.compile(
        r"^(?:#+\s*)?(?:troubleshooting|actions?(?:\s+taken)?|work(?:\s+performed)?|steps?(?:\s+taken)?|investigation|d[ée]pannage|actions?(?:\s+effectu[ée]es)?|travail(?:\s+effectu[ée])?|[ée]tapes?(?:\s+r[ée]alis[ée]es)?)\s*[:\-\—]?",
        re.IGNORECASE,
    )
    RE_RESOLUTION = re.compile(
        r"^(?:#+\s*)?(?:resolution|solution|fix|outcome|resolved|r[ée]solution|solution(?:\s+apport[ée]e)?|correctif|r[ée]solu)\s*[:\-\—]?",
        re.IGNORECASE,
    )
    RE_ROOT_CAUSE = re.compile(
        r"^(?:#+\s*)?(?:root(?:\s+cause)?|findings|cause(?:\s+racine|\s+premi[èe]re)?|constats?)\s*[:\-\—]?",
        re.IGNORECASE,
    )
    RE_NEXT_STEPS = re.compile(
        r"^(?:#+\s*)?(?:next(?:\s+steps)?|instructions|recommendations?|prochaines?(?:\s+[ée]tapes)?|recommandations?(?:\s+pour\s+l[\'’]usager)?)\s*[:\-\—]?",
        re.IGNORECASE,
    )

    @classmethod
    def calculate_billable_hours(cls, elapsed_seconds: int) -> float:
        """Calculates billable hours rounded up to nearest 15-minute block (0.25h)."""
        if elapsed_seconds <= 0:
            return 0.0
        blocks = max(1, math.ceil(elapsed_seconds / 900))
        return blocks * 0.25

    @classmethod
    def format_time_logged(cls, elapsed_seconds: int, lang: str = "en") -> str:
        """Formats elapsed time and billable duration in English or French."""
        if elapsed_seconds <= 0:
            return "0m" if lang == "en" else "0 min"

        hours = elapsed_seconds // 3600
        mins = (elapsed_seconds % 3600) // 60
        secs = elapsed_seconds % 60
        billable = cls.calculate_billable_hours(elapsed_seconds)

        if lang == "fr":
            billable_str = f"{billable:.2f}".replace(".", ",")
            return f"{hours:02d}:{mins:02d}:{secs:02d} ({billable_str} h facturable)"
        else:
            return f"{hours:02d}:{mins:02d}:{secs:02d} ({billable:.2f}h billable)"

    @classmethod
    def clean_html_to_markdown(cls, raw_html: str) -> str:
        """Converts HTML markup to clean readable plain text / Markdown."""
        if not raw_html:
            return ""

        text = raw_html

        # Remove head and style blocks completely (Qt rich text CSS rules)
        text = re.sub(r'<head[^>]*>.*?</head>', '', text, flags=re.IGNORECASE | re.DOTALL)
        text = re.sub(r'<style[^>]*>.*?</style>', '', text, flags=re.IGNORECASE | re.DOTALL)

        # Replace line breaks and paragraphs
        text = re.sub(r'<br\s*/?>', '\n', text, flags=re.IGNORECASE)
        text = re.sub(r'</p>', '\n', text, flags=re.IGNORECASE)
        text = re.sub(r'</h1>', '\n\n', text, flags=re.IGNORECASE)
        text = re.sub(r'</h2>', '\n\n', text, flags=re.IGNORECASE)
        text = re.sub(r'</h3>', '\n\n', text, flags=re.IGNORECASE)
        text = re.sub(r'</h4>', '\n\n', text, flags=re.IGNORECASE)

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
        text = html.unescape(text)
        text = text.replace('\xa0', ' ')
        # Clean up excess whitespace
        text = re.sub(r'\n{3,}', '\n\n', text)
        return text.strip()

    @classmethod
    def parse_ticket(
        cls,
        ticket: dict,
        technician_name: str = "",
        technician_email: str = "",
    ) -> ParsedTicketSections:
        """Parses ticket dictionary and returns structured ParsedTicketSections."""
        ticket_number = (ticket.get("ticket_number") or "").strip()
        client_name = (ticket.get("client_name") or "").strip()
        title = (ticket.get("title") or "").strip()
        elapsed_seconds = int(ticket.get("elapsed_seconds") or 0)

        raw_html = ticket.get("content_html") or ""
        text = cls.clean_html_to_markdown(raw_html)

        sections = ParsedTicketSections(
            ticket_number=ticket_number,
            client_name=client_name,
            title=title,
            elapsed_seconds=elapsed_seconds,
            technician_name=technician_name.strip(),
            technician_email=technician_email.strip(),
        )

        if not text:
            return sections

        lines = text.split("\n")
        current_section = None
        buckets: dict[str, list[str]] = {
            "issue": [],
            "work": [],
            "resolution": [],
            "root_cause": [],
            "next_steps": [],
            "unassigned": [],
        }

        checked_tasks: list[str] = []

        for raw_line in lines:
            line = raw_line.strip()
            if not line:
                if current_section:
                    buckets[current_section].append("")
                continue

            # Skip stray Qt CSS stylesheet definitions if any
            if re.search(r'(?:white-space\s*:|border-width\s*:|::marker|\bhr\s*\{|\bp,\s*li\s*\{)', line):
                continue

            # Check if this line is a completed or pending task
            if line.startswith(("- [x]", "- [✔]", "[x]", "[✔]")):
                checked_tasks.append(line)

            # Check if line matches section headers
            if cls.RE_ISSUE.match(line):
                current_section = "issue"
                # Strip header keyword if header line contains content
                remainder = cls.RE_ISSUE.sub("", line).strip()
                if remainder:
                    buckets["issue"].append(remainder)
            elif cls.RE_WORK.match(line):
                current_section = "work"
                remainder = cls.RE_WORK.sub("", line).strip()
                if remainder:
                    buckets["work"].append(remainder)
            elif cls.RE_RESOLUTION.match(line):
                current_section = "resolution"
                remainder = cls.RE_RESOLUTION.sub("", line).strip()
                if remainder:
                    buckets["resolution"].append(remainder)
            elif cls.RE_ROOT_CAUSE.match(line):
                current_section = "root_cause"
                remainder = cls.RE_ROOT_CAUSE.sub("", line).strip()
                if remainder:
                    buckets["root_cause"].append(remainder)
            elif cls.RE_NEXT_STEPS.match(line):
                current_section = "next_steps"
                remainder = cls.RE_NEXT_STEPS.sub("", line).strip()
                if remainder:
                    buckets["next_steps"].append(remainder)
            else:
                if current_section:
                    buckets[current_section].append(line)
                else:
                    buckets["unassigned"].append(line)

        # Assemble string representations
        sections.issue = "\n".join(buckets["issue"]).strip()
        sections.work_performed = "\n".join(buckets["work"]).strip()
        sections.resolution = "\n".join(buckets["resolution"]).strip()
        sections.root_cause = "\n".join(buckets["root_cause"]).strip()
        sections.next_steps = "\n".join(buckets["next_steps"]).strip()

        unassigned_str = "\n".join(buckets["unassigned"]).strip()

        # If no explicit sections were found, smart-allocate unassigned content
        if not sections.work_performed and not sections.issue and not sections.resolution:
            # Entire note is unstructured
            if checked_tasks:
                sections.work_performed = "\n".join(checked_tasks)
                remaining = [l for l in buckets["unassigned"] if l not in checked_tasks]
                sections.issue = "\n".join(remaining).strip() or title
            else:
                sections.work_performed = unassigned_str
        elif unassigned_str:
            if not sections.issue:
                sections.issue = unassigned_str
            elif not sections.work_performed:
                sections.work_performed = unassigned_str
            else:
                sections.work_performed = f"{sections.work_performed}\n\n{unassigned_str}".strip()

        # If resolution is missing but work contains resolved items, fallback smoothly
        if not sections.issue and title:
            sections.issue = title

        return sections

    @classmethod
    def format_client_email(
        cls,
        sections: ParsedTicketSections,
        lang: str = "en",
        include_time: bool = False,
    ) -> tuple[str, str]:
        """Formats client-facing resolution email. Returns (plain_text, rich_html)."""
        client = sections.client_name or ("Client" if lang == "en" else "Client")
        t_ref = f"#{sections.ticket_number}" if sections.ticket_number else ""
        t_title = f" — {sections.title}" if sections.title else ""
        ticket_header = f"{t_ref}{t_title}".strip()
        if not ticket_header:
            ticket_header = "Service Request" if lang == "en" else "Demande de service"

        # Technician name and email signature
        sig_lines = []
        if sections.technician_name:
            sig_lines.append(sections.technician_name)
        if sections.technician_email:
            sig_lines.append(sections.technician_email)
        tech_title = "Support informatique" if lang == "fr" else "IT Support"
        if not sections.technician_name and not sections.technician_email:
            sig_lines.append("Équipe du support informatique" if lang == "fr" else "IT Support Team")
        else:
            sig_lines.append(tech_title)
        sig_block = "\n".join(sig_lines)

        time_info = cls.format_time_logged(sections.elapsed_seconds, lang) if include_time and sections.elapsed_seconds > 0 else ""

        # Main body content
        actions_or_res = sections.resolution or sections.work_performed or (
            "The reported issue has been diagnosed and resolved."
            if lang == "en"
            else "Le problème signalé a été diagnostiqué et résolu avec succès."
        )

        issue_text = sections.issue or sections.title or (
            "Service request assistance" if lang == "en" else "Assistance pour votre demande de service"
        )

        if lang == "fr":
            lines = [
                f"Bonjour {client},",
                "",
                f"Concernant le billet {ticket_header} :",
                "",
                "Description du problème :",
                f"{issue_text}",
                "",
                "Actions effectuées et résolution :",
                f"{actions_or_res}",
            ]
            if sections.next_steps:
                lines.extend([
                    "",
                    "Prochaines étapes pour vous :",
                    f"{sections.next_steps}",
                ])
            if time_info:
                lines.extend([
                    "",
                    f"Temps consacré : {time_info}",
                ])
            lines.extend([
                "",
                "Nous vous invitons à vérifier le bon fonctionnement de votre côté. Pour toute question ou si vous avez besoin d'assistance supplémentaire, n'hésitez pas à répondre directement à ce message.",
                "",
                "Cordialement,",
                sig_block,
            ])
        else:
            lines = [
                f"Hello {client},",
                "",
                f"Regarding Ticket {ticket_header}:",
                "",
                "Summary of Issue:",
                f"{issue_text}",
                "",
                "Actions Taken & Resolution:",
                f"{actions_or_res}",
            ]
            if sections.next_steps:
                lines.extend([
                    "",
                    "Next Steps for You:",
                    f"{sections.next_steps}",
                ])
            if time_info:
                lines.extend([
                    "",
                    f"Time Logged: {time_info}",
                ])
            lines.extend([
                "",
                "Please verify on your end to ensure everything is working as expected. If you have any questions or require further assistance, simply reply directly to this ticket.",
                "",
                "Best regards,",
                sig_block,
            ])

        plain = "\n".join(lines)
        html_body = cls._text_to_rich_html(plain, title=f"Resolution: {ticket_header}")
        return plain, html_body

    @classmethod
    def format_psa_note(
        cls,
        sections: ParsedTicketSections,
        lang: str = "en",
        include_time: bool = True,
    ) -> tuple[str, str]:
        """Formats standardized internal PSA ticket note. Returns (plain_text, rich_html)."""
        t_ref = f"#{sections.ticket_number}" if sections.ticket_number else "N/A"
        client = sections.client_name or "N/A"
        subject = sections.title or "N/A"
        time_info = cls.format_time_logged(sections.elapsed_seconds, lang) if include_time and sections.elapsed_seconds > 0 else None

        tech_parts = []
        if sections.technician_name:
            tech_parts.append(sections.technician_name)
        if sections.technician_email:
            tech_parts.append(f"<{sections.technician_email}>")
        tech_full = " ".join(tech_parts)

        if lang == "fr":
            header_title = f"=== BILLET : {t_ref} | Client : {client} ==="
            lines = [
                header_title,
                f"Objet : {subject}",
            ]
            if tech_full:
                lines.append(f"Technicien : {tech_full}")
            if time_info:
                lines.append(f"Temps consigné : {time_info}")
            lines.extend([
                "=" * len(header_title),
                "",
                "PROBLÈME SIGNALÉ :",
                sections.issue or "Aucune description fournie.",
                "",
                "DÉPANNAGE / TRAVAIL EFFECTUÉ :",
                sections.work_performed or "Travaux effectués selon les notes de dépannage.",
                "",
                "CAUSE RACINE :",
                sections.root_cause or "S/O",
                "",
                "RÉSOLUTION :",
                sections.resolution or sections.work_performed or "Billet résolu avec succès.",
            ])
            if sections.next_steps:
                lines.extend([
                    "",
                    "PROCHAINES ÉTAPES :",
                    sections.next_steps,
                ])
            if tech_full:
                lines.extend([
                    "",
                    f"TECHNICIEN : {tech_full}",
                ])
            lines.append("=" * len(header_title))
        else:
            header_title = f"=== TICKET: {t_ref} | Client: {client} ==="
            lines = [
                header_title,
                f"Subject: {subject}",
            ]
            if tech_full:
                lines.append(f"Technician: {tech_full}")
            if time_info:
                lines.append(f"Time Logged: {time_info}")
            lines.extend([
                "=" * len(header_title),
                "",
                "ISSUE REPORTED:",
                sections.issue or "No description provided.",
                "",
                "WORK PERFORMED / TROUBLESHOOTING:",
                sections.work_performed or "Actions taken per troubleshooting notes.",
                "",
                "ROOT CAUSE:",
                sections.root_cause or "N/A",
                "",
                "RESOLUTION:",
                sections.resolution or sections.work_performed or "Resolved successfully.",
            ])
            if sections.next_steps:
                lines.extend([
                    "",
                    "NEXT STEPS:",
                    sections.next_steps,
                ])
            if tech_full:
                lines.extend([
                    "",
                    f"TECHNICIAN: {tech_full}",
                ])
            lines.append("=" * len(header_title))

        plain = "\n".join(lines)
        html_body = cls._text_to_rich_html(plain, title=header_title)
        return plain, html_body

    @classmethod
    def format_escalation_handover(
        cls,
        sections: ParsedTicketSections,
        lang: str = "en",
        include_time: bool = True,
    ) -> tuple[str, str]:
        """Formats Tier 2/3 escalation handover summary. Returns (plain_text, rich_html)."""
        t_ref = f"#{sections.ticket_number}" if sections.ticket_number else "N/A"
        client = sections.client_name or "N/A"
        subject = sections.title or "N/A"
        time_info = cls.format_time_logged(sections.elapsed_seconds, lang) if include_time and sections.elapsed_seconds > 0 else None

        tech_parts = []
        if sections.technician_name:
            tech_parts.append(sections.technician_name)
        if sections.technician_email:
            tech_parts.append(f"<{sections.technician_email}>")
        tech_full = " ".join(tech_parts)

        if lang == "fr":
            header_title = f"=== TRANSFERT D'ESCALADE : {t_ref} ==="
            lines = [
                header_title,
                f"Client : {client} | Objet : {subject}",
            ]
            if tech_full:
                lines.append(f"Transféré par : {tech_full}")
            if time_info:
                lines.append(f"Temps consacré à ce jour : {time_info}")
            lines.extend([
                "=" * len(header_title),
                "",
                "SITUATION ACTUELLE ET IMPACT :",
                sections.issue or "Détails non spécifiés.",
                "",
                "DÉPANNAGE RÉALISÉ ET PISTES ÉCARTÉES :",
                sections.work_performed or "Dépannage de premier niveau complété.",
                "",
                "CONSTATS ET RECHERCHE DE CAUSE :",
                sections.root_cause or "Non identifiée à ce stade.",
                "",
                "PROCHAINES ACTIONS RECOMMANDÉES :",
                sections.next_steps or sections.resolution or "Prise en charge par le palier supérieur.",
            ])
            if tech_full:
                lines.extend([
                    "",
                    f"TRANSFÉRÉ PAR : {tech_full}",
                ])
            lines.append("=" * len(header_title))
        else:
            header_title = f"=== ESCALATION HANDOVER: {t_ref} ==="
            lines = [
                header_title,
                f"Client: {client} | Subject: {subject}",
            ]
            if tech_full:
                lines.append(f"Escalated by: {tech_full}")
            if time_info:
                lines.append(f"Time Spent So Far: {time_info}")
            lines.extend([
                "=" * len(header_title),
                "",
                "CURRENT SITUATION & IMPACT:",
                sections.issue or "Details not specified.",
                "",
                "TROUBLESHOOTING COMPLETED & RULED OUT:",
                sections.work_performed or "First-level troubleshooting completed.",
                "",
                "FINDINGS & ROOT CAUSE INVESTIGATION:",
                sections.root_cause or "Unidentified at current tier.",
                "",
                "RECOMMENDED NEXT ACTIONS:",
                sections.next_steps or sections.resolution or "Awaiting Tier 2/3 engagement.",
            ])
            if tech_full:
                lines.extend([
                    "",
                    f"ESCALATED BY: {tech_full}",
                ])
            lines.append("=" * len(header_title))

        plain = "\n".join(lines)
        html_body = cls._text_to_rich_html(plain, title=header_title)
        return plain, html_body

        plain = "\n".join(lines)
        html_body = cls._text_to_rich_html(plain, title=header_title)
        return plain, html_body

    @classmethod
    def _text_to_rich_html(cls, plain_text: str, title: str = "") -> str:
        """Converts formatted summary plain text into clean, styled HTML with readable styling."""
        escaped = html.escape(plain_text)
        # Convert section headers (uppercase lines ending with colon or starting with ===)
        lines = escaped.split("\n")
        formatted_lines = []
        in_pre = False

        for line in lines:
            if line.startswith("===") and line.endswith("==="):
                formatted_lines.append(f'<div style="font-weight: bold; color: #007acc; font-size: 13px; margin: 8px 0;">{line}</div>')
            elif line.isupper() and line.endswith(":") and len(line) > 3:
                formatted_lines.append(f'<div style="font-weight: bold; color: #4ec9b0; margin-top: 10px; margin-bottom: 2px;">{line}</div>')
            elif line.startswith("- [x]") or line.startswith("- [✔]"):
                formatted_lines.append(f'<div style="color: #4ec9b0; padding-left: 12px;">☑ {line[5:].strip()}</div>')
            elif line.startswith("- [ ]"):
                formatted_lines.append(f'<div style="color: #dcdcaa; padding-left: 12px;">☐ {line[5:].strip()}</div>')
            elif line.startswith("• "):
                formatted_lines.append(f'<div style="padding-left: 12px;">• {line[2:].strip()}</div>')
            elif line.strip() == "":
                formatted_lines.append('<div style="height: 6px;"></div>')
            else:
                formatted_lines.append(f'<div>{line}</div>')

        content = "\n".join(formatted_lines)
        return f'<div style="font-family: -apple-system, BlinkMacSystemFont, \'Segoe UI\', Roboto, Consolas, sans-serif; font-size: 12px; line-height: 1.4; color: #cccccc;">{content}</div>'

