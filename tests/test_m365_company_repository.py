"""Tests for SQLite persistence of M365 company directory, atomic merge, backup, and synthetic isolation."""

from __future__ import annotations

import json
import sqlite3
from pathlib import Path

import pytest

from src.database.connection import DatabaseManager
from src.database.migrations import init_database
from src.repositories.m365_company_repository import M365CompanyRepository
from src.services.backup_service import BackupService
from src.services.m365_company_service import Administrator, Company, DIRECTORY_FORMAT
from src.services.m365_company_store import PersistentCompanyDirectory, _company_to_record


COMPANY_ID = "10000000-0000-4000-8000-000000000101"
TENANT_ID = "20000000-0000-4000-8000-000000000202"
ADMIN_ID = "30000000-0000-4000-8000-000000000303"


def _make_company(
    company_id: str = COMPANY_ID,
    name: str = "Contoso Production",
    tenant_id: str = TENANT_ID,
    domain: str = "contoso.com",
    admin_upn: str = "alex@contoso.com",
) -> Company:
    admin = Administrator(ADMIN_ID, admin_upn, "Primary Admin")
    return Company(
        company_id=company_id,
        display_name=name,
        tenant_id=tenant_id,
        primary_domain=domain,
        additional_verified_domains=("mail.contoso.com",),
        administrators=(admin,),
        preferred_administrator_id=ADMIN_ID,
        notes="Customer tenant metadata",
    )


def _init_db(tmp_path: Path) -> DatabaseManager:
    db_path = tmp_path / "techpad.db"
    db = DatabaseManager(db_path)
    init_database(db)
    return db


def test_schema_creates_m365_tables_and_fk_cascade(tmp_path):
    db = _init_db(tmp_path)
    repo = M365CompanyRepository(db)
    assert repo.get_revision() >= 0
    assert not repo.has_companies()

    company = _make_company()
    rev = repo.upsert_company(_company_to_record(company), expected_revision=repo.get_revision())
    assert rev >= 1
    assert repo.has_companies()

    conn = db.get_connection()
    admin_rows = conn.execute("SELECT COUNT(*) FROM m365_administrators").fetchone()[0]
    assert admin_rows == 1

    repo.delete_company(company.company_id)
    admin_rows_after = conn.execute("SELECT COUNT(*) FROM m365_administrators").fetchone()[0]
    comp_rows_after = conn.execute("SELECT COUNT(*) FROM m365_companies").fetchone()[0]
    assert admin_rows_after == 0
    assert comp_rows_after == 0


def test_persistent_directory_synthetic_preview_stays_out_of_sqlite(tmp_path):
    db = _init_db(tmp_path)
    repo = M365CompanyRepository(db)
    store = PersistentCompanyDirectory(repo, fallback_to_synthetic=True, backup_dir=tmp_path / "backups")

    assert store.is_synthetic_preview is True
    assert store.persisted_count() == 0
    assert len(store.search("")) >= 2  # Synthetic preview entries visible in RAM

    # Synthetic IDs must never leak into SQLite when empty
    assert not repo.has_companies()

    # Explicitly reject saving synthetic .example domains to SQLite
    synthetic_like = _make_company(domain="contoso.example", admin_upn="admin@contoso.example")
    with pytest.raises(ValueError, match="Synthetic"):
        store.save(synthetic_like)
    assert not repo.has_companies()

    # Saving a real company transitions store out of synthetic preview into SQLite persistence
    real_company = _make_company()
    saved = store.save(real_company)
    assert saved.company_id == COMPANY_ID
    assert store.is_synthetic_preview is False
    assert store.persisted_count() == 1

    # Fresh instance on the same DB loads persisted records and never re-enters synthetic preview
    store2 = PersistentCompanyDirectory(M365CompanyRepository(db), fallback_to_synthetic=True, backup_dir=tmp_path / "backups")
    assert store2.is_synthetic_preview is False
    assert store2.get(COMPANY_ID).display_name == "Contoso Production"
    assert store2.get(COMPANY_ID).administrators[0].upn == "alex@contoso.com"


def test_optimistic_revision_conflict_rolls_back(tmp_path):
    db = _init_db(tmp_path)
    repo = M365CompanyRepository(db)
    initial_rev = repo.get_revision()
    c1 = _make_company()
    repo.upsert_company(_company_to_record(c1), expected_revision=initial_rev)

    # Stale expected revision must reject cleanly without corrupting SQLite
    c2 = _make_company(company_id="10000000-0000-4000-8000-000000000199", name="Other Corp", tenant_id="20000000-0000-4000-8000-000000000299", domain="other.com", admin_upn="a@other.com")
    with pytest.raises(ValueError, match="concurrently|revision"):
        repo.upsert_company(_company_to_record(c2), expected_revision=initial_rev)
    assert len(repo.load_all()[1]) == 1


def test_export_and_atomic_prebackup_merge(tmp_path):
    db = _init_db(tmp_path)
    repo = M365CompanyRepository(db)
    backup_dir = tmp_path / "backups"
    store = PersistentCompanyDirectory(repo, fallback_to_synthetic=True, backup_dir=backup_dir)

    store.save(_make_company())
    export_path = tmp_path / "dir-export.json"
    store.export_to_file(export_path)
    payload = json.loads(export_path.read_text(encoding="utf-8"))
    assert payload["format"] == DIRECTORY_FORMAT
    assert len(payload["companies"]) == 1

    # Merge second company + check pre-merge backup file created
    merge_src = tmp_path / "incoming.json"
    second_id = "10000000-0000-4000-8000-000000000102"
    second_tenant = "20000000-0000-4000-8000-000000000203"
    second_admin_id = "30000000-0000-4000-8000-000000000304"
    incoming = {
        "format": DIRECTORY_FORMAT,
        "version": 1,
        "companies": [
            payload["companies"][0],  # unchanged
            {
                "company_id": second_id,
                "display_name": "Fabrikam Live",
                "tenant_id": second_tenant,
                "primary_domain": "fabrikam.com",
                "additional_verified_domains": [],
                "administrators": [
                    {"administrator_id": second_admin_id, "upn": "ops@fabrikam.com", "display_label": "Ops"}
                ],
                "preferred_administrator_id": second_admin_id,
                "notes": "Merged",
                "preferred_cloud": "Global",
                "created_at": "2026-11-12T10:00:00Z",
                "updated_at": "2026-11-12T10:00:00Z",
            },
        ],
    }
    merge_src.write_text(json.dumps(incoming), encoding="utf-8")
    summary = store.merge_from_file(merge_src)
    assert summary.companies_added == 1
    assert summary.companies_updated == 0
    assert store.persisted_count() == 2
    assert summary.backup_path is not None and summary.backup_path.is_file()

    # Corrupt merge file (synthetic .example domain) rejects atomically without altering DB
    bad_src = tmp_path / "bad.json"
    incoming_bad = dict(incoming)
    incoming_bad["companies"] = [
        *incoming["companies"],
        {
            "company_id": "10000000-0000-4000-8000-000000000199",
            "display_name": "Bad Synthetic",
            "tenant_id": "20000000-0000-4000-8000-000000000299",
            "primary_domain": "bad.example",
            "additional_verified_domains": [],
            "administrators": [],
            "preferred_administrator_id": None,
            "notes": "",
            "preferred_cloud": "Global",
            "created_at": "2026-11-12T10:00:00Z",
            "updated_at": "2026-11-12T10:00:00Z",
        },
    ]
    bad_src.write_text(json.dumps(incoming_bad), encoding="utf-8")
    with pytest.raises(ValueError):
        store.merge_from_file(bad_src)
    assert store.persisted_count() == 2


def test_backup_service_includes_m365_directory_tables(tmp_path):
    db = _init_db(tmp_path)
    store = PersistentCompanyDirectory(M365CompanyRepository(db), fallback_to_synthetic=True, backup_dir=tmp_path / "backups")
    store.save(_make_company())

    backup_svc = BackupService(db, backup_dir=tmp_path / "app_backups")
    snap_path = tmp_path / "full-backup.db"
    backup_svc.create_backup_snapshot(custom_path=snap_path)

    with sqlite3.connect(snap_path) as check_conn:
        count = check_conn.execute("SELECT COUNT(*) FROM m365_companies").fetchone()[0]
        assert count == 1
