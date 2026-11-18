"""Pure utility service for technician entity extraction and cryptographically safe generators."""

from __future__ import annotations

import ipaddress
import re
import secrets
import string
import uuid
from datetime import datetime, timezone
from typing import Dict, List, Optional


class TechToolsService:
    """Stateless extraction and generator helpers for IT technician workflows."""

    _EMAIL_RE = re.compile(r"\b[A-Za-z0-9._%+-]+@[A-Za-z0-9.-]+\.[A-Za-z]{2,}\b")
    _GUID_RE = re.compile(
        r"\b[0-9a-fA-F]{8}-[0-9a-fA-F]{4}-[0-9a-fA-F]{4}-[0-9a-fA-F]{4}-[0-9a-fA-F]{12}\b"
    )
    _IPV4_RE = re.compile(r"\b(?:\d{1,3}\.){3}\d{1,3}\b")
    _URL_RE = re.compile(r"https?://[^\s<>\"'\]\)]+")
    _TICKET_RE = re.compile(
        r"\b(?:INC|SR|CHG|PRB|TASK|REQ|RITM|TKT|CASE)-?\d{3,10}\b",
        re.IGNORECASE,
    )

    _SYMBOLS = "@#$%!&*?"
    _LOWER = "abcdefghjkmnpqrstuvwxyz"
    _UPPER = "ABCDEFGHJKLMNPQRSTUVWXYZ"
    _DIGITS = "23456789"

    @classmethod
    def extract_entities(cls, text: str) -> Dict[str, List[str]]:
        """Extract deduplicated Emails/UPNs, GUIDs, IPv4s, URLs, and Ticket IDs."""
        if not text:
            return {
                "emails": [],
                "guids": [],
                "ips": [],
                "urls": [],
                "tickets": [],
            }

        def _dedupe(items: List[str], normalizer=lambda s: s) -> List[str]:
            seen: set[str] = set()
            result: List[str] = []
            for item in items:
                key = normalizer(item)
                if key not in seen:
                    seen.add(key)
                    result.append(item)
            return result

        emails = _dedupe(cls._EMAIL_RE.findall(text), lambda s: s.lower())
        guids = _dedupe([g.lower() for g in cls._GUID_RE.findall(text)])

        valid_ips: List[str] = []
        for candidate in cls._IPV4_RE.findall(text):
            try:
                ipaddress.IPv4Address(candidate)
                valid_ips.append(candidate)
            except ValueError:
                continue
        ips = _dedupe(valid_ips)

        raw_urls = [u.rstrip(".,;:)>\"'") for u in cls._URL_RE.findall(text)]
        urls = _dedupe([u for u in raw_urls if len(u) > 8])

        tickets = _dedupe([t.upper() for t in cls._TICKET_RE.findall(text)])

        return {
            "emails": emails,
            "guids": guids,
            "ips": ips,
            "urls": urls,
            "tickets": tickets,
        }

    @staticmethod
    def generate_uuid() -> str:
        """Return a canonical lowercase UUID v4 string."""
        return str(uuid.uuid4())

    @classmethod
    def generate_temp_password(cls, length: int = 16) -> str:
        """Generate a cryptographically random temporary password.

        Guarantees at least one lowercase letter, uppercase letter, digit, and
        special character while avoiding visually ambiguous characters (0/O, 1/l/I).
        """
        target_len = max(8, min(64, int(length)))
        pool = cls._LOWER + cls._UPPER + cls._DIGITS + cls._SYMBOLS

        chars = [
            secrets.choice(cls._LOWER),
            secrets.choice(cls._UPPER),
            secrets.choice(cls._DIGITS),
            secrets.choice(cls._SYMBOLS),
        ]
        while len(chars) < target_len:
            chars.append(secrets.choice(pool))

        # Unbiased Fisher-Yates shuffle using secrets.randbelow
        for i in range(len(chars) - 1, 0, -1):
            j = secrets.randbelow(i + 1)
            chars[i], chars[j] = chars[j], chars[i]
        return "".join(chars)

    @staticmethod
    def format_iso_timestamp(dt: Optional[datetime] = None) -> Dict[str, str]:
        """Return formatted Local, UTC, and combined diagnostic timestamp strings."""
        now_local = dt if dt is not None else datetime.now().astimezone()
        if now_local.tzinfo is None:
            now_local = now_local.astimezone()
        now_utc = now_local.astimezone(timezone.utc)

        local_str = now_local.strftime("%Y-%m-%d %H:%M:%S %Z").strip()
        utc_str = now_utc.strftime("%Y-%m-%dT%H:%M:%SZ")
        return {
            "local": local_str,
            "utc": utc_str,
            "combined": f"Local: {local_str} | UTC: {utc_str}",
        }
