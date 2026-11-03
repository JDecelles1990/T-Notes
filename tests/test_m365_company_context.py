"""Synthetic company/context tests. SQLite below is a test-only future adapter."""

from dataclasses import replace
from datetime import datetime, timedelta, timezone
import json
import sqlite3
from uuid import uuid4

import pytest

from src.services.m365_company_service import (
    Administrator, CompanyDirectory, guid, synthetic_directory, upn,
)
from src.services.m365_context_service import (
    CompanyContextService, SyntheticConnectionManager, TargetInput,
)


@pytest.fixture
def directory():
    return synthetic_directory()


@pytest.fixture
def context(directory):
    service = CompanyContextService(directory)
    service.select_company(directory.search()[0].company_id)
    return service


def test_sort_search_and_domains(directory):
    a, b = directory.search()
    directory.save(replace(a, display_name="zebra", additional_verified_domains=("other.example",)))
    directory.save(replace(b, display_name="Alpha"))
    assert [c.display_name for c in directory.search()] == ["Alpha", "zebra"]
    assert directory.search("ZEB")[0].company_id == a.company_id
    assert directory.search("OTHER.EX")[0].company_id == a.company_id
    assert directory.search("alpine")[0].company_id == a.company_id
    assert directory.search("not-present") == ()


@pytest.mark.parametrize("field", ["display_name", "tenant_id"])
def test_duplicate_company_or_tenant_rejected(directory, field):
    a, b = directory.search()
    value = a.display_name.swapcase() if field == "display_name" else a.tenant_id.upper()
    with pytest.raises(ValueError, match="already exists"):
        directory.save(replace(b, **{field: value}))
    assert directory.get(b.company_id) == b


@pytest.mark.parametrize("value", ["", "not-a-guid", "123", "20000000000040008000000000000001", "{20000000-0000-4000-8000-000000000001}"])
def test_invalid_tenant_id(directory, value):
    with pytest.raises(ValueError):
        replace(directory.search()[0], tenant_id=value)


@pytest.mark.parametrize("value", ["no-at", "admin@", "a@b", "*@alpine.example", "a?@alpine.example", "a\n@alpine.example", "a\x7f@alpine.example"])
def test_administrator_upn_validation(value):
    with pytest.raises(ValueError):
        upn(value)


def test_multiple_admin_crud_defaults_stable_id(directory):
    company = directory.search()[0]
    admin = company.administrators[0]
    with pytest.raises(ValueError, match="unique"):
        directory.save_administrator(company.company_id, Administrator(str(uuid4()), admin.upn.upper()))
    directory.save_administrator(company.company_id, replace(admin, upn="new@alpine.example", display_label="No role evidence"))
    assert directory.administrators(company.company_id, "NEW")[0].administrator_id == admin.administrator_id
    directory.set_default(company.company_id, admin.administrator_id)
    assert directory.get(company.company_id).preferred_admin_upn == "new@alpine.example"
    directory.remove_administrator(company.company_id, admin.administrator_id)
    assert directory.get(company.company_id).preferred_administrator_id is None
    with pytest.raises(ValueError, match="belong"):
        directory.set_default(company.company_id, str(uuid4()))
    # Same UPN at another company is permitted as metadata, never as tenant proof.
    other = directory.search()[1]
    directory.save_administrator(other.company_id, Administrator(str(uuid4()), "new@alpine.example"))


def test_profile_roundtrip_through_authorized_test_only_storage(directory, tmp_path):
    # Simulates the Phase B seam AFTER a fixture-only authorization. The application
    # has no persistence adapter or production path; this creates no production schema.
    path = tmp_path / "company-fixture.sqlite"
    payload = directory.export_metadata()
    with sqlite3.connect(path) as db:
        db.execute("PRAGMA journal_mode=WAL")
        db.execute("PRAGMA foreign_keys=ON")
        db.execute("CREATE TABLE fixture_profile (payload TEXT NOT NULL)")
        db.execute("INSERT INTO fixture_profile VALUES (?)", (json.dumps(payload),))
    with sqlite3.connect(path) as db:
        loaded = CompanyDirectory.from_metadata(json.loads(db.execute("SELECT payload FROM fixture_profile").fetchone()[0]))
    assert loaded.export_metadata() == json.loads(json.dumps(payload))
    assert loaded.search()[0].company_id == directory.search()[0].company_id


@pytest.mark.parametrize("secret", ["password", "access_token", "refresh_token", "credential_export", "connections"])
@pytest.mark.parametrize("level", ["root", "company", "administrator"])
def test_metadata_rejects_secret_and_unknown_fields(directory, secret, level):
    payload = json.loads(json.dumps(directory.export_metadata()))
    obj = payload if level == "root" else payload["companies"][0] if level == "company" else payload["companies"][0]["administrators"][0]
    obj[secret] = "SYNTHETIC-SECRET-SENTINEL"
    with pytest.raises(ValueError):
        CompanyDirectory.from_metadata(payload)
    assert "SYNTHETIC-SECRET-SENTINEL" not in json.dumps(directory.export_metadata())


def test_import_duplicate_ids_and_versions(directory):
    payload = json.loads(json.dumps(directory.export_metadata()))
    payload["companies"].append(payload["companies"][0])
    with pytest.raises(ValueError, match="Duplicate company IDs"):
        CompanyDirectory.from_metadata(payload)
    for version in (True, 2, "1"):
        payload = directory.export_metadata()
        payload["version"] = version
        with pytest.raises(ValueError):
            CompanyDirectory.from_metadata(payload)


def test_empty_state_and_company_confirmation():
    context = CompanyContextService(CompanyDirectory())
    assert context.company is None
    assert not context.eligibility().eligible
    with pytest.raises(ValueError):
        context.confirm_company()
    with pytest.raises(ValueError):
        context.connect_synthetic("Graph")


def test_company_and_administrator_switch_invalidates_all_context(context, directory):
    context.connect_synthetic("Graph")
    context.set_target("client@alpine.example")
    context.resolve_synthetic()
    context.confirm_company()
    before = context.session_generation
    ref = context.admin_identity_ref
    context.select_administrator(context.company.administrators[1].administrator_id)
    assert context.session_generation > before and context.admin_identity_ref != ref
    assert context.target is None and context.confirmed_company is None
    assert context.connections.state("Graph").state == "disconnected"
    assert not context.target_input.upn
    context.select_company(directory.search()[1].company_id)
    assert not context.administrator_upn and context.administrator_id is None
    assert context.target is None
    with pytest.raises(ValueError):
        context.select_administrator(directory.search()[0].administrators[0].administrator_id)


def test_profile_edit_invalidates_context(context, directory):
    context.connect_synthetic("Graph")
    context.confirm_company()
    original = context.company
    directory.save(replace(original, tenant_id=str(uuid4())))
    assert "COMPANY_CONFIRMATION_REQUIRED" in context.eligibility().reasons
    assert context.connections.state("Graph").state == "disconnected"
    assert context.target is None


def test_admin_hint_edit_invalidates_and_never_authenticates(context):
    context.connect_synthetic("Graph")
    context.set_administrator_upn("other@alpine.example")
    assert context.administrator_id is None
    assert context.connections.state("Graph").state == "disconnected"
    assert not context.eligibility().eligible


def test_independent_connections_and_expiration(directory):
    clock = [datetime(2026, 11, 2, tzinfo=timezone.utc)]
    manager = SyntheticConnectionManager(lambda: clock[0])
    context = CompanyContextService(directory, connection_manager=manager)
    context.select_company(directory.search()[0].company_id)
    context.connect_synthetic("Graph", seconds=10)
    assert manager.state("ExchangeOnline").state == "disconnected"
    context.connect_synthetic("ExchangeOnline", outcome="permission_warning", seconds=30)
    clock[0] += timedelta(seconds=11)
    assert manager.state("Graph").state == "expired"
    assert manager.state("ExchangeOnline").state == "permission_warning"
    assert any("expired" in r for r in context.eligibility().reasons)
    context.connect_synthetic("Graph", outcome="error")
    assert manager.state("Graph").state == "error"
    context.disconnect()
    assert all(manager.state(s).state == "disconnected" for s in ("Graph", "ExchangeOnline"))


def test_tenant_account_and_generation_mismatch_rejected(context):
    manager = context.connections
    manager.simulate("Graph", str(uuid4()), context.administrator_upn, context.session_generation)
    assert "TENANT_MISMATCH" in context.eligibility().reasons
    manager.simulate("Graph", context.company.tenant_id, "someone@alpine.example", context.session_generation)
    assert "ACCOUNT_MISMATCH" in context.eligibility().reasons
    manager.simulate("Graph", context.company.tenant_id, context.administrator_upn, context.session_generation - 1)
    assert "STALE_CONTEXT" in context.eligibility().reasons


def test_target_upn_object_id_and_contract_shape(context):
    object_id = str(uuid4())
    context.set_target(" Client@Alpine.Example ", object_id.upper())
    assert context.target_input.contract_target() == {"kind": "object_id", "value": object_id}
    context.resolve_synthetic(resolved_upn="client@alpine.example", resolved_object_id=object_id)
    assert context.target.upn != context.administrator_upn
    context.set_target("client@alpine.example")
    assert context.target_input.contract_target() == {"kind": "upn", "value": "client@alpine.example"}
    assert context.target is None
    context.set_target("", object_id)
    context.resolve_synthetic()
    with pytest.raises(ValueError):
        context.set_target("bad-upn", "not-a-guid")
    assert context.target is None and not context.target_input.upn
    with pytest.raises(ValueError):
        TargetInput().contract_target()


def test_target_tenant_and_identifier_mismatch(context):
    context.set_target("client@alpine.example", str(uuid4()))
    for kwargs in ({"tenant_id": str(uuid4())}, {"resolved_upn": "other@alpine.example"}, {"resolved_object_id": str(uuid4())}):
        with pytest.raises(ValueError, match="mismatch"):
            context.resolve_synthetic(**kwargs)
        assert context.target is None


def test_no_dispatch_even_fully_populated_synthetic_context(context, monkeypatch):
    import subprocess
    import socket
    def forbidden(*args, **kwargs):
        raise AssertionError("Synthetic context attempted IO or PowerShell dispatch")
    monkeypatch.setattr(subprocess, "Popen", forbidden)
    monkeypatch.setattr(socket, "socket", forbidden)
    for service in ("Graph", "ExchangeOnline"):
        context.connect_synthetic(service)
    context.set_target("client@alpine.example")
    context.resolve_synthetic()
    context.confirm_company()
    for _ in range(3):
        assert context.eligibility().eligible is False
        assert any("DISPATCH_DISABLED" in r for r in context.eligibility().reasons)
    exported = json.dumps(context.directory.export_metadata())
    for forbidden_field in ("admin_identity_ref", "session_generation", "connections", "expires_at", "password", "access_token", "refresh_token"):
        assert forbidden_field not in exported


def test_contract_target_schema_compatibility(context):
    # Candidate shape check only; never release approval or engine compatibility.
    from pathlib import Path
    from jsonschema import Draft202012Validator
    from referencing import Registry, Resource
    path = Path(__file__).resolve().parents[1] / "docs/contracts/m365/schemas/common.schema.json"
    schema = json.loads(path.read_text(encoding="utf-8"))
    registry = Registry().with_resource(schema["$id"], Resource.from_contents(schema))
    validator = Draft202012Validator({"$ref": schema["$id"] + "#/$defs/target"}, registry=registry)
    for args in (("client@alpine.example", ""), ("", str(uuid4()))):
        validator.validate(TargetInput.parse(*args).contract_target())


@pytest.mark.parametrize("field", ["created_at", "updated_at"])
@pytest.mark.parametrize("invalid_value", [
    1234567890,
    None,
    True,
    False,
    1700000000.5,
    "",
    "not-a-dateZ",
    "2026-99-99T99:99:99Z",
    "2026-11-02T12:00:00",
    "2026-11-02T12:00:00+02:00",
    "2026-11-02T12:00:00-05:00",
])
def test_import_timestamp_validation_and_negative_cases(directory, field, invalid_value):
    payload = json.loads(json.dumps(directory.export_metadata()))
    payload["companies"][0][field] = invalid_value
    with pytest.raises(ValueError):
        CompanyDirectory.from_metadata(payload)


def test_company_timestamp_type_validation_and_ordering():
    from src.services.m365_company_service import Company
    for bad_ts in (12345, None, True, False, 99.9, "badZ", "2026-11-02T12:00:00+01:00"):
        with pytest.raises(ValueError):
            Company(str(uuid4()), "Test", str(uuid4()), "test.example", created_at=bad_ts)
        with pytest.raises(ValueError):
            Company(str(uuid4()), "Test", str(uuid4()), "test.example", updated_at=bad_ts)

    # Updated timestamp precedes creation
    with pytest.raises(ValueError, match="Updated timestamp precedes creation"):
        Company(str(uuid4()), "Test", str(uuid4()), "test.example",
                created_at="2026-11-02T12:00:00Z", updated_at="2026-11-01T12:00:00Z")


def test_malformed_import_never_modifies_existing_directory(directory):
    original_revision = directory.revision
    original_export = json.loads(json.dumps(directory.export_metadata()))
    malformed_payload = json.loads(json.dumps(original_export))
    malformed_payload["companies"][0]["created_at"] = 1234567890
    with pytest.raises(ValueError):
        CompanyDirectory.from_metadata(malformed_payload)

    assert directory.revision == original_revision
    assert directory.export_metadata() == original_export

