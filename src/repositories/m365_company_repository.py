"""Repository for non-secret M365 customer tenant profiles and admin UPN hints."""

from datetime import datetime, timezone
import json
from typing import Any, Optional

from src.database.connection import DatabaseManager


def _utc_now() -> str:
    return datetime.now(timezone.utc).isoformat().replace("+00:00", "Z")


class M365CompanyRepository:
    """Owns SQLite persistence for M365 company profiles and administrator hints."""

    def __init__(self, db_manager: DatabaseManager):
        self.db = db_manager

    def get_revision(self) -> int:
        """Return the current optimistic concurrency revision of the directory."""
        conn = self.db.get_connection()
        row = conn.execute("SELECT revision FROM m365_directory_meta WHERE id = 1").fetchone()
        return int(row["revision"]) if row else 1

    def has_companies(self) -> bool:
        """Return True if at least one real company profile is stored in SQLite."""
        conn = self.db.get_connection()
        row = conn.execute("SELECT 1 FROM m365_companies LIMIT 1").fetchone()
        return row is not None

    def load_all(self) -> tuple[int, list[dict[str, Any]]]:
        """Load the stored revision and all persisted non-secret company records."""
        conn = self.db.get_connection()
        rev_row = conn.execute("SELECT revision FROM m365_directory_meta WHERE id = 1").fetchone()
        revision = int(rev_row["revision"]) if rev_row else 1

        comp_rows = conn.execute(
            """
            SELECT company_id, display_name, tenant_id, primary_domain,
                   additional_verified_domains_json, preferred_administrator_id,
                   preferred_cloud, notes, created_at, updated_at
            FROM m365_companies
            ORDER BY display_name COLLATE NOCASE ASC, company_id ASC
            """
        ).fetchall()

        admin_rows = conn.execute(
            """
            SELECT administrator_id, company_id, upn, display_label
            FROM m365_administrators
            ORDER BY upn COLLATE NOCASE ASC, administrator_id ASC
            """
        ).fetchall()

        admins_by_company: dict[str, list[dict[str, str]]] = {}
        for row in admin_rows:
            admins_by_company.setdefault(row["company_id"], []).append(
                {
                    "administrator_id": row["administrator_id"],
                    "upn": row["upn"],
                    "display_label": row["display_label"] or "",
                }
            )

        companies: list[dict[str, Any]] = []
        for row in comp_rows:
            try:
                domains = json.loads(row["additional_verified_domains_json"] or "[]")
            except ValueError:
                domains = []
            companies.append(
                {
                    "company_id": row["company_id"],
                    "display_name": row["display_name"],
                    "tenant_id": row["tenant_id"],
                    "primary_domain": row["primary_domain"],
                    "additional_verified_domains": tuple(domains),
                    "administrators": admins_by_company.get(row["company_id"], []),
                    "preferred_administrator_id": row["preferred_administrator_id"],
                    "preferred_cloud": row["preferred_cloud"],
                    "notes": row["notes"] or "",
                    "created_at": row["created_at"],
                    "updated_at": row["updated_at"],
                }
            )
        return revision, companies

    def _bump_revision(self, conn, expected_revision: Optional[int]) -> int:
        row = conn.execute("SELECT revision FROM m365_directory_meta WHERE id = 1").fetchone()
        current_rev = int(row["revision"]) if row else 1
        if expected_revision is not None and current_rev != expected_revision:
            raise ValueError("Company directory changed concurrently; reload before saving.")
        new_rev = current_rev + 1
        now = _utc_now()
        conn.execute(
            """
            INSERT INTO m365_directory_meta (id, revision, updated_at)
            VALUES (1, ?, ?)
            ON CONFLICT(id) DO UPDATE SET
                revision = excluded.revision,
                updated_at = excluded.updated_at
            """,
            (new_rev, now),
        )
        return new_rev

    def upsert_company(self, company_data: dict[str, Any], *, expected_revision: Optional[int] = None) -> int:
        """Atomically save one company profile and synchronize its administrator rows."""
        conn = self.db.get_connection()
        domains_json = json.dumps(list(company_data.get("additional_verified_domains", ())), ensure_ascii=False)
        admins = list(company_data.get("administrators", ()))
        with conn:
            new_rev = self._bump_revision(conn, expected_revision)
            conn.execute(
                """
                INSERT INTO m365_companies (
                    company_id, display_name, tenant_id, primary_domain,
                    additional_verified_domains_json, preferred_administrator_id,
                    preferred_cloud, notes, created_at, updated_at
                )
                VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
                ON CONFLICT(company_id) DO UPDATE SET
                    display_name = excluded.display_name,
                    tenant_id = excluded.tenant_id,
                    primary_domain = excluded.primary_domain,
                    additional_verified_domains_json = excluded.additional_verified_domains_json,
                    preferred_administrator_id = excluded.preferred_administrator_id,
                    preferred_cloud = excluded.preferred_cloud,
                    notes = excluded.notes,
                    updated_at = excluded.updated_at
                """,
                (
                    company_data["company_id"],
                    company_data["display_name"],
                    company_data["tenant_id"],
                    company_data["primary_domain"],
                    domains_json,
                    company_data.get("preferred_administrator_id"),
                    company_data.get("preferred_cloud", "Global"),
                    company_data.get("notes", ""),
                    company_data["created_at"],
                    company_data["updated_at"],
                ),
            )
            conn.execute("DELETE FROM m365_administrators WHERE company_id = ?", (company_data["company_id"],))
            if admins:
                conn.executemany(
                    """
                    INSERT INTO m365_administrators (administrator_id, company_id, upn, display_label)
                    VALUES (?, ?, ?, ?)
                    """,
                    [
                        (
                            a["administrator_id"],
                            company_data["company_id"],
                            a["upn"],
                            a.get("display_label", ""),
                        )
                        for a in admins
                    ],
                )
        return new_rev

    def delete_company(self, company_id: str, *, expected_revision: Optional[int] = None) -> int:
        """Atomically delete a company profile and cascade-delete its administrators."""
        conn = self.db.get_connection()
        with conn:
            new_rev = self._bump_revision(conn, expected_revision)
            conn.execute("DELETE FROM m365_companies WHERE company_id = ?", (company_id,))
        return new_rev

    def replace_all(self, companies_data: list[dict[str, Any]], *, expected_revision: Optional[int] = None) -> int:
        """Atomically replace stored directory rows (used for validated merge/restore commits)."""
        conn = self.db.get_connection()
        with conn:
            new_rev = self._bump_revision(conn, expected_revision)
            conn.execute("DELETE FROM m365_administrators")
            conn.execute("DELETE FROM m365_companies")
            for company_data in companies_data:
                domains_json = json.dumps(list(company_data.get("additional_verified_domains", ())), ensure_ascii=False)
                conn.execute(
                    """
                    INSERT INTO m365_companies (
                        company_id, display_name, tenant_id, primary_domain,
                        additional_verified_domains_json, preferred_administrator_id,
                        preferred_cloud, notes, created_at, updated_at
                    )
                    VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
                    """,
                    (
                        company_data["company_id"],
                        company_data["display_name"],
                        company_data["tenant_id"],
                        company_data["primary_domain"],
                        domains_json,
                        company_data.get("preferred_administrator_id"),
                        company_data.get("preferred_cloud", "Global"),
                        company_data.get("notes", ""),
                        company_data["created_at"],
                        company_data["updated_at"],
                    ),
                )
                admins = list(company_data.get("administrators", ()))
                if admins:
                    conn.executemany(
                        """
                        INSERT INTO m365_administrators (administrator_id, company_id, upn, display_label)
                        VALUES (?, ?, ?, ?)
                        """,
                        [
                            (
                                a["administrator_id"],
                                company_data["company_id"],
                                a["upn"],
                                a.get("display_label", ""),
                            )
                            for a in admins
                        ],
                    )
        return new_rev

