"""Persistent M365 company directory store bridging portable CompanyDirectory and SQLite."""

from __future__ import annotations

from dataclasses import asdict, dataclass, replace
from datetime import datetime, timezone
import hashlib
import json
import os
from pathlib import Path
from typing import Any, Optional
from uuid import uuid4

from src.config import DEFAULT_DB_PATH
from src.repositories.m365_company_repository import M365CompanyRepository
from src.services.m365_company_service import (
    Administrator,
    Company,
    CompanyDirectory,
    DIRECTORY_FORMAT,
    DIRECTORY_VERSION,
    synthetic_directory,
    utc_now,
)


SYNTHETIC_COMPANY_IDS = frozenset(
    {
        "10000000-0000-4000-8000-000000000001",
        "10000000-0000-4000-8000-000000000002",
    }
)
RESERVED_SYNTHETIC_SUFFIXES = (".example", ".invalid")
MAX_IMPORT_BYTES = 1048576  # 1 MiB strict import ceiling


def _assert_not_synthetic_record(company: Company) -> None:
    if company.company_id in SYNTHETIC_COMPANY_IDS:
        raise ValueError("Synthetic preview company IDs cannot be persisted to SQLite.")
    domains = (company.primary_domain, *company.additional_verified_domains)
    for dom in domains:
        if dom.strip().lower().endswith(RESERVED_SYNTHETIC_SUFFIXES):
            raise ValueError(f"Synthetic domain '{dom}' cannot be persisted to SQLite.")
    for admin in company.administrators:
        if admin.upn.strip().lower().endswith(RESERVED_SYNTHETIC_SUFFIXES):
            raise ValueError(f"Synthetic UPN '{admin.upn}' cannot be persisted to SQLite.")


def _strict_parse_json(raw_bytes: bytes) -> dict[str, Any]:
    if len(raw_bytes) > MAX_IMPORT_BYTES:
        raise ValueError("Directory JSON file exceeds 1 MiB safety limit.")
    if raw_bytes.startswith(b"\xef\xbb\xbf"):
        raise ValueError("UTF-8 BOM is not supported in directory JSON files.")

    def _no_duplicate_keys(pairs):
        obj = {}
        for k, v in pairs:
            if k in obj:
                raise ValueError(f"Duplicate JSON key rejected: {k}")
            obj[k] = v
        return obj

    def _reject_nonfinite(token):
        raise ValueError(f"Non-finite numeric literal rejected: {token}")

    parsed = json.loads(
        raw_bytes.decode("utf-8"),
        object_pairs_hook=_no_duplicate_keys,
        parse_constant=_reject_nonfinite,
    )
    if not isinstance(parsed, dict):
        raise ValueError("Directory JSON root must be an object.")
    return parsed


def _company_to_record(company: Company) -> dict[str, Any]:
    return {
        "company_id": company.company_id,
        "display_name": company.display_name,
        "tenant_id": company.tenant_id,
        "primary_domain": company.primary_domain,
        "additional_verified_domains": tuple(company.additional_verified_domains),
        "administrators": [
            {
                "administrator_id": a.administrator_id,
                "upn": a.upn,
                "display_label": a.display_label,
            }
            for a in company.administrators
        ],
        "preferred_administrator_id": company.preferred_administrator_id,
        "preferred_cloud": company.preferred_cloud,
        "notes": company.notes,
        "created_at": company.created_at,
        "updated_at": company.updated_at,
    }


def _hydrate_company(row: dict[str, Any]) -> Company:
    admins = tuple(
        Administrator(
            administrator_id=a["administrator_id"],
            upn=a["upn"],
            display_label=a.get("display_label", ""),
        )
        for a in row.get("administrators", ())
    )
    return Company(
        company_id=row["company_id"],
        display_name=row["display_name"],
        tenant_id=row["tenant_id"],
        primary_domain=row["primary_domain"],
        additional_verified_domains=tuple(row.get("additional_verified_domains", ())),
        administrators=admins,
        preferred_administrator_id=row.get("preferred_administrator_id"),
        preferred_cloud=row.get("preferred_cloud", "Global"),
        notes=row.get("notes", ""),
        created_at=row["created_at"],
        updated_at=row["updated_at"],
    )


@dataclass(frozen=True)
class MergeSummary:
    companies_added: int
    companies_updated: int
    companies_skipped: int
    administrators_added: int
    domains_added: int
    conflicts_skipped: int
    backup_status: str  # "not needed" | "verified"
    backup_path: Optional[Path] = None
    backup_sha256: Optional[str] = None


class PersistentCompanyDirectory(CompanyDirectory):
    """SQLite-backed company directory that keeps synthetic preview records strictly in RAM."""

    def __init__(
        self,
        repository: M365CompanyRepository,
        *,
        fallback_to_synthetic: bool = True,
        backup_dir: Optional[Path] = None,
    ):
        self._repository = repository
        self._fallback_to_synthetic = fallback_to_synthetic
        self._backup_dir = Path(backup_dir) if backup_dir else (DEFAULT_DB_PATH.parent / "backups" / "company-directory")
        self.is_synthetic_preview = False
        self._db_revision = 1
        super().__init__(())
        self.reload_from_repository()

    def reload_from_repository(self) -> None:
        """Load real persisted companies from SQLite, falling back to RAM synthetic preview if empty."""
        db_rev, rows = self._repository.load_all()
        self._db_revision = db_rev
        self._companies = {}
        if rows:
            self.is_synthetic_preview = False
            for row in rows:
                company = _hydrate_company(row)
                self._companies[company.company_id] = company
        elif self._fallback_to_synthetic:
            self.is_synthetic_preview = True
            for company in synthetic_directory().search():
                self._companies[company.company_id] = company
        else:
            self.is_synthetic_preview = False
        self.revision += 1

    def switch_to_live_directory(self) -> None:
        """Drop any ephemeral synthetic preview items and show only persisted DB companies."""
        db_rev, rows = self._repository.load_all()
        self._db_revision = db_rev
        self._companies = {}
        self.is_synthetic_preview = False
        for row in rows:
            company = _hydrate_company(row)
            self._companies[company.company_id] = company
        self.revision += 1

    def load_synthetic_preview(self) -> None:
        """Switch RAM directory view to offline synthetic sample tenants without mutating DB."""
        self._companies = {}
        self.is_synthetic_preview = True
        for company in synthetic_directory().search():
            self._companies[company.company_id] = company
        self.revision += 1

    def persisted_count(self) -> int:
        """Return count of real companies persisted in SQLite."""
        _, rows = self._repository.load_all()
        return len(rows)

    def save(self, company: Company) -> Company:
        if not isinstance(company, Company):
            raise ValueError("Expected a company profile.")

        # Saving/editing the hardcoded synthetic fixtures while in preview stays RAM-only
        if self.is_synthetic_preview and company.company_id in SYNTHETIC_COMPANY_IDS:
            return super().save(company)

        _assert_not_synthetic_record(company)

        # Transition from RAM-only synthetic preview -> real persisted directory on first real company
        was_preview = self.is_synthetic_preview
        prev_snapshot = dict(self._companies)
        prev_rev = self._db_revision
        if was_preview:
            self._companies = {
                cid: comp for cid, comp in self._companies.items() if cid not in SYNTHETIC_COMPANY_IDS
            }
            self.is_synthetic_preview = False

        try:
            saved = super().save(company)
            self._db_revision = self._repository.upsert_company(
                _company_to_record(saved),
                expected_revision=self._db_revision,
            )
            return saved
        except Exception:
            self._companies = prev_snapshot
            self.is_synthetic_preview = was_preview
            self._db_revision = prev_rev
            raise

    def delete_company(self, company_id: str) -> None:
        """Remove a customer company profile from persisted storage (or RAM preview)."""
        if company_id not in self._companies:
            raise ValueError("Company profile not found.")
        if self.is_synthetic_preview and company_id in SYNTHETIC_COMPANY_IDS:
            del self._companies[company_id]
            self.revision += 1
            return

        prev_snapshot = dict(self._companies)
        prev_rev = self._db_revision
        try:
            del self._companies[company_id]
            self._db_revision = self._repository.delete_company(
                company_id,
                expected_revision=self._db_revision,
            )
            self.revision += 1
        except Exception:
            self._companies = prev_snapshot
            self._db_revision = prev_rev
            raise

    def export_persisted_metadata(self) -> dict[str, Any]:
        """Export only real persisted SQLite records in canonical portable JSON shape."""
        _, rows = self._repository.load_all()
        real_dir = CompanyDirectory(_hydrate_company(r) for r in rows)
        return real_dir.export_metadata()

    def export_to_file(self, dest_path: Path) -> Path:
        """Write canonical non-secret company directory JSON to disk."""
        target = Path(dest_path)
        target.parent.mkdir(parents=True, exist_ok=True)
        payload = self.export_persisted_metadata()
        raw = (json.dumps(payload, indent=2, ensure_ascii=False) + "\n").encode("utf-8")
        tmp_path = target.with_name(f".{target.name}.{uuid4().hex}.tmp")
        try:
            with open(tmp_path, "wb") as f:
                f.write(raw)
                f.flush()
                os.fsync(f.fileno())
            os.replace(tmp_path, target)
        finally:
            if tmp_path.exists():
                tmp_path.unlink(missing_ok=True)
        return target

    def _write_verified_backup(self, snapshot_payload: dict[str, Any]) -> tuple[Path, str]:
        self._backup_dir.mkdir(parents=True, exist_ok=True)
        stamp = datetime.now(timezone.utc).strftime("%Y%m%d-%H%M%S")
        final_path = self._backup_dir / f"company-directory-backup-{stamp}-{uuid4().hex}.json"
        tmp_path = self._backup_dir / f".company-directory-backup-{uuid4().hex}.tmp"
        serialized = json.dumps(snapshot_payload, separators=(",", ":"), sort_keys=True, ensure_ascii=False).encode("utf-8")
        expected_sha = hashlib.sha256(serialized).hexdigest()
        try:
            with open(tmp_path, "wb") as f:
                f.write(serialized)
                f.flush()
                os.fsync(f.fileno())
            os.replace(tmp_path, final_path)
        finally:
            if tmp_path.exists():
                tmp_path.unlink(missing_ok=True)

        # Independently reopen & verify digest + schema semantics before modifying DB
        reopened = final_path.read_bytes()
        if hashlib.sha256(reopened).hexdigest() != expected_sha:
            raise ValueError("Published directory backup verification checksum mismatch.")
        CompanyDirectory.from_metadata(_strict_parse_json(reopened))
        return final_path, expected_sha

    def merge_from_file(self, src_path: Path) -> MergeSummary:
        """Validate, local-first merge, snapshot-backup, and atomically commit directory JSON."""
        raw = Path(src_path).read_bytes()
        incoming_payload = _strict_parse_json(raw)
        incoming_dir = CompanyDirectory.from_metadata(incoming_payload)
        for inc_company in incoming_dir.search():
            _assert_not_synthetic_record(inc_company)

        db_rev, current_rows = self._repository.load_all()
        current_companies = [_hydrate_company(r) for r in current_rows]
        local_dir = CompanyDirectory(current_companies)
        before_snapshot = local_dir.export_metadata()

        by_tenant = {c.tenant_id: c for c in current_companies}
        used_names = {c.display_name.casefold(): c.company_id for c in current_companies}
        used_domains = {
            d.casefold(): c.company_id
            for c in current_companies
            for d in (c.primary_domain, *c.additional_verified_domains)
        }

        added = 0
        updated = 0
        skipped = 0
        admins_added = 0
        domains_added = 0
        conflicts = 0

        candidate_map: dict[str, Company] = {c.company_id: c for c in current_companies}

        for inc in incoming_dir.search():
            existing = by_tenant.get(inc.tenant_id)
            if existing is None:
                # Reject conflicting ID, name, or domain across different tenants
                if inc.company_id in candidate_map:
                    conflicts += 1
                    skipped += 1
                    continue
                if inc.display_name.casefold() in used_names:
                    conflicts += 1
                    skipped += 1
                    continue
                if inc.primary_domain.casefold() in used_domains:
                    conflicts += 1
                    skipped += 1
                    continue

                filtered_extra = []
                for dom in inc.additional_verified_domains:
                    if dom.casefold() in used_domains:
                        conflicts += 1
                    else:
                        filtered_extra.append(dom)
                        used_domains[dom.casefold()] = inc.company_id

                new_comp = replace(inc, additional_verified_domains=tuple(filtered_extra))
                candidate_map[new_comp.company_id] = new_comp
                by_tenant[new_comp.tenant_id] = new_comp
                used_names[new_comp.display_name.casefold()] = new_comp.company_id
                used_domains[new_comp.primary_domain.casefold()] = new_comp.company_id
                added += 1
                admins_added += len(new_comp.administrators)
                domains_added += len(new_comp.additional_verified_domains)
                continue

            # Enrich existing company conservatively (local-first scalar & conflict preservation)
            cur = candidate_map[existing.company_id]
            cur_domains = list(cur.additional_verified_domains)
            cur_admins = list(cur.administrators)
            cur_admin_ids = {a.administrator_id for a in cur_admins}
            cur_admin_upns = {a.upn.casefold(): a for a in cur_admins}

            added_dom_here = 0
            for dom in inc.additional_verified_domains:
                if len(cur_domains) >= 30:
                    conflicts += 1
                    break
                owner = used_domains.get(dom.casefold())
                if owner is not None and owner != cur.company_id:
                    conflicts += 1
                    continue
                if dom.casefold() not in {d.casefold() for d in (cur.primary_domain, *cur_domains)}:
                    cur_domains.append(dom)
                    used_domains[dom.casefold()] = cur.company_id
                    added_dom_here += 1

            added_adm_here = 0
            for adm in inc.administrators:
                if len(cur_admins) >= 100:
                    conflicts += 1
                    break
                if adm.upn.casefold() in cur_admin_upns or adm.administrator_id in cur_admin_ids:
                    if adm.upn.casefold() in cur_admin_upns and cur_admin_upns[adm.upn.casefold()].administrator_id != adm.administrator_id:
                        conflicts += 1
                    continue
                cur_admins.append(adm)
                cur_admin_ids.add(adm.administrator_id)
                cur_admin_upns[adm.upn.casefold()] = adm
                added_adm_here += 1

            pref_adm = cur.preferred_administrator_id
            if pref_adm is None and inc.preferred_administrator_id in {a.administrator_id for a in cur_admins}:
                pref_adm = inc.preferred_administrator_id

            if added_dom_here or added_adm_here or pref_adm != cur.preferred_administrator_id:
                enriched = replace(
                    cur,
                    additional_verified_domains=tuple(cur_domains),
                    administrators=tuple(cur_admins),
                    preferred_administrator_id=pref_adm,
                    updated_at=utc_now(),
                )
                candidate_map[cur.company_id] = enriched
                updated += 1
                admins_added += added_adm_here
                domains_added += added_dom_here

        if added == 0 and updated == 0:
            return MergeSummary(
                companies_added=0,
                companies_updated=0,
                companies_skipped=skipped,
                administrators_added=0,
                domains_added=0,
                conflicts_skipped=conflicts,
                backup_status="not needed",
            )

        # Validate full candidate before writing backup or DB
        validated_dir = CompanyDirectory(candidate_map.values())
        candidate_records = [_company_to_record(c) for c in validated_dir.search()]

        backup_path, backup_sha = self._write_verified_backup(before_snapshot)
        new_rev = self._repository.replace_all(candidate_records, expected_revision=db_rev)
        self._db_revision = new_rev
        self._companies = {c.company_id: c for c in validated_dir.search()}
        self.is_synthetic_preview = False
        self.revision += 1

        return MergeSummary(
            companies_added=added,
            companies_updated=updated,
            companies_skipped=skipped,
            administrators_added=admins_added,
            domains_added=domains_added,
            conflicts_skipped=conflicts,
            backup_status="verified",
            backup_path=backup_path,
            backup_sha256=backup_sha,
        )

