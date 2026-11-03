"""Detached synthetic merge tests. No production adapter, approval or persistence."""

from copy import deepcopy
import json
from pathlib import Path
from uuid import UUID

import pytest
from PySide6.QtWidgets import QPushButton

from prototypes.company_directory_merge.company_directory_merge import (
    DraftContract, MAX_BYTES, canonical_bytes, plan_merge_prototype,
)
from src.ui.dialogs.settings_dialog import SettingsDialog

ROOT = Path(__file__).resolve().parents[1]
CONTRACT = ROOT / "docs/contracts/company-directory"


@pytest.fixture
def contract():
    return DraftContract((CONTRACT / "company-directory.schema.json").read_bytes(),
                         (CONTRACT / "MERGE_SPEC.md").read_bytes())


@pytest.fixture
def directory():
    return json.loads((CONTRACT / "exchange-fixtures.json").read_text())["cases"][0]["document"]


def encode(value):
    return json.dumps(value).encode()


def empty(directory):
    result = deepcopy(directory)
    result["companies"] = []
    return result


def test_new_companies_and_repeated_import(contract, directory):
    plan = plan_merge_prototype(empty(directory), encode(directory), contract)
    assert plan.changes_required and plan.prototype_only and not plan.durable
    assert plan.counts["companies_added"] == 2
    assert plan.counts["administrators_added"] == 2
    again = plan_merge_prototype(plan.candidate, encode(directory), contract)
    assert not again.changes_required and not again.conflicts
    assert canonical_bytes(again.candidate) == canonical_bytes(plan.candidate)


def test_existing_enrichment_default_and_ids(contract, directory):
    local = deepcopy(directory)
    local["companies"][0]["administrators"] = []
    local["companies"][0]["preferred_administrator_id"] = None
    incoming = deepcopy(directory)
    incoming["companies"][0]["company_id"] = "10000000-0000-4000-8000-999999999999"
    incoming["companies"][0]["additional_verified_domains"] = ["extra.example"]
    before = deepcopy(local)
    plan = plan_merge_prototype(local, encode(incoming), contract)
    company = plan.candidate["companies"][0]
    assert local == before
    assert company["company_id"] == local["companies"][0]["company_id"]
    assert company["preferred_administrator_id"] == directory["companies"][0]["preferred_administrator_id"]
    assert plan.counts["existing_companies_enriched"] == 1
    assert plan.counts["administrators_added"] == 2
    assert plan.counts["additional_domains_added"] == 1
    assert company["updated_at"] == local["companies"][0]["updated_at"]


@pytest.mark.parametrize("field,value", [
    ("display_name", "Imported different name"), ("notes", "Imported notes"),
    ("preferred_cloud", "China"), ("primary_domain", "alternative.example"),
    ("created_at", "2020-01-01T00:00:00Z"), ("updated_at", "2099-01-01T00:00:00Z"),
])
def test_local_scalar_preservation(contract, directory, field, value):
    incoming = deepcopy(directory)
    incoming["companies"][0][field] = value
    plan = plan_merge_prototype(directory, encode(incoming), contract)
    assert not plan.validation_failures
    assert canonical_bytes(plan.candidate) == canonical_bytes(directory)
    assert not plan.changes_required


def test_admin_alias_labels_and_defaults(contract, directory):
    incoming = deepcopy(directory)
    company = incoming["companies"][0]
    company["administrators"][0]["administrator_id"] = "30000000-0000-4000-8000-999999999999"
    company["administrators"][0]["upn"] = company["administrators"][0]["upn"].upper()
    company["administrators"][0]["display_label"] = "Imported label"
    company["preferred_administrator_id"] = company["administrators"][0]["administrator_id"]
    plan = plan_merge_prototype(directory, encode(incoming), contract)
    assert not plan.changes_required
    assert plan.counts["administrators_added"] == 0
    assert canonical_bytes(plan.candidate) == canonical_bytes(directory)
    assert [c["code"] for c in plan.conflicts] == ["VALUE_CONFLICT"]


def test_cross_tenant_admin_upn_does_not_combine_companies(contract, directory):
    incoming = deepcopy(directory)
    incoming["companies"][1]["administrators"] = deepcopy(incoming["companies"][0]["administrators"])
    plan = plan_merge_prototype(directory, encode(incoming), contract)
    assert len(plan.candidate["companies"]) == 2
    assert len(plan.candidate["companies"][1]["administrators"]) == 2
    assert plan.candidate["companies"][1]["tenant_id"] != plan.candidate["companies"][0]["tenant_id"]


def test_domain_conflict_partial_enrichment(contract, directory):
    incoming = deepcopy(directory)
    incoming["companies"] = incoming["companies"][:1]
    incoming["companies"][0]["additional_verified_domains"] = ["BIRCH.EXAMPLE", "new.example"]
    plan = plan_merge_prototype(directory, encode(incoming), contract)
    assert plan.candidate["companies"][0]["additional_verified_domains"] == ["new.example"]
    assert plan.counts["conflicts_skipped"] == 1
    assert plan_merge_prototype(plan.candidate, encode(incoming), contract).changes_required is False


def test_company_id_cannot_rebind_to_different_tenant(contract, directory):
    incoming = deepcopy(directory)
    incoming["companies"] = incoming["companies"][:1]
    incoming["companies"][0]["company_id"] = directory["companies"][1]["company_id"]
    plan = plan_merge_prototype(directory, encode(incoming), contract)
    assert canonical_bytes(plan.candidate) == canonical_bytes(directory)
    assert plan.counts["companies_skipped"] == 1
    assert plan.conflicts[0]["code"] == "COMPANY_ID_TENANT_CONFLICT"


def test_determinism_equivalent_order_and_no_mutation(contract, directory):
    incoming = deepcopy(directory)
    incoming["companies"][0]["additional_verified_domains"] = ["z.example", "a.example"]
    reordered = deepcopy(incoming)
    reordered["companies"].reverse()
    reordered["companies"][1]["administrators"].reverse()
    reordered["companies"][1]["additional_verified_domains"].reverse()
    before = deepcopy(directory)
    first = plan_merge_prototype(directory, encode(incoming), contract)
    second = plan_merge_prototype(directory, encode(reordered), contract)
    assert directory == before
    assert first == second
    assert canonical_bytes(first.candidate) == canonical_bytes(second.candidate)


CASES = json.loads((CONTRACT / "exchange-fixtures.json").read_text())["cases"]


@pytest.mark.parametrize("case", CASES, ids=lambda c: c["name"])
def test_complete_document_validation(contract, directory, case):
    raw = case.get("raw_json", json.dumps(case.get("document"))).encode()
    plan = plan_merge_prototype(directory, raw, contract)
    assert bool(plan.validation_failures) is not case["accept"]
    if not case["accept"]:
        assert plan.candidate is None and not plan.changes_required
        assert not any(plan.counts.values())


def test_exact_contract_pins(contract, directory):
    plan = plan_merge_prototype(directory, encode(directory), DraftContract(contract.schema_bytes + b" ", contract.policy_bytes))
    assert plan.validation_failures == ({"stage": "contract", "code": "DRAFT_PIN_MISMATCH"},)


def test_size_limit_and_invalid_local(contract, directory):
    plan = plan_merge_prototype(directory, b" " * (MAX_BYTES + 1), contract)
    assert plan.validation_failures[0]["code"] == "INPUT_SIZE_OR_TYPE"
    bad = deepcopy(directory)
    bad["companies"][0]["tenant_id"] = "invalid"
    assert plan_merge_prototype(bad, encode(directory), contract).validation_failures[0]["stage"] == "local"


def test_unpaired_unicode_surrogate_rejects_whole_document(contract, directory):
    bad = deepcopy(directory)
    bad["companies"][0]["notes"] = "\ud800"
    plan = plan_merge_prototype(directory, encode(bad), contract)
    assert plan.candidate is None and plan.validation_failures


def test_golden_candidate_documents(contract):
    scenarios = json.loads((CONTRACT / "merge-golden-fixtures.json").read_text())["scenarios"]
    for scenario in scenarios:
        plan = plan_merge_prototype(scenario["local"], encode(scenario["imported"]), contract)
        assert not plan.validation_failures, scenario["name"]
        assert canonical_bytes(plan.candidate) == canonical_bytes(scenario["expected"]), scenario["name"]


def test_admin_id_collision_and_unavailable_default(contract, directory):
    incoming = deepcopy(directory)
    company = incoming["companies"][0]
    company["administrators"] = [company["administrators"][0]]
    company["administrators"][0]["upn"] = "new@alpine.example"
    plan = plan_merge_prototype(directory, encode(incoming), contract)
    assert not plan.changes_required
    assert canonical_bytes(plan.candidate) == canonical_bytes(directory)
    assert {c["code"] for c in plan.conflicts} == {"ADMIN_ID_UPN_CONFLICT", "DEFAULT_UNAVAILABLE"}


def test_conflicting_default_and_empty_label_remain_local(contract, directory):
    local = deepcopy(directory)
    local["companies"][0]["administrators"][0]["display_label"] = ""
    incoming = deepcopy(directory)
    incoming["companies"][0]["preferred_administrator_id"] = incoming["companies"][0]["administrators"][1]["administrator_id"]
    plan = plan_merge_prototype(local, encode(incoming), contract)
    assert canonical_bytes(plan.candidate) == canonical_bytes(local)
    assert {c["code"] for c in plan.conflicts} == {"VALUE_CONFLICT", "DEFAULT_CONFLICT"}


@pytest.mark.parametrize("kind", ["domains", "administrators"])
def test_capacity_skips_entire_delta(contract, directory, kind):
    local = deepcopy(directory)
    company = local["companies"][0]
    if kind == "domains":
        company["additional_verified_domains"] = [f"d{i}.example" for i in range(30)]
    else:
        company["administrators"] = [dict(administrator_id=str(UUID(int=i + 1)), upn=f"admin{i}@alpine.example", display_label="") for i in range(100)]
        company["preferred_administrator_id"] = None
    incoming = deepcopy(directory)
    incoming["companies"][0]["additional_verified_domains"] = ["new.example"]
    plan = plan_merge_prototype(local, encode(incoming), contract)
    assert canonical_bytes(plan.candidate) == canonical_bytes(local)
    assert not plan.changes_required
    assert plan.conflicts[0]["code"] == "CAPACITY_CONFLICT"
    assert plan.counts["administrators_added"] == 0 and plan.counts["additional_domains_added"] == 0


@pytest.mark.parametrize("field,value,code", [
    ("display_name", "Synthetic Alpine", "NAME_COLLISION"),
    ("primary_domain", "alpine.example", "DOMAIN_TENANT_CONFLICT"),
])
def test_new_tenant_conflicts_skip_company(contract, directory, field, value, code):
    imported = deepcopy(directory)
    imported["companies"] = imported["companies"][1:]
    imported["companies"][0][field] = value
    local = deepcopy(directory)
    local["companies"] = local["companies"][:1]
    plan = plan_merge_prototype(local, encode(imported), contract)
    assert canonical_bytes(plan.candidate) == canonical_bytes(local)
    assert plan.counts["companies_skipped"] == 1 and plan.conflicts[0]["code"] == code


def test_invalid_tail_rejects_entire_import(contract, directory):
    incoming = deepcopy(directory)
    incoming["companies"][0]["additional_verified_domains"] = ["safe-new.example"]
    incoming["companies"][1]["access_token"] = "SYNTHETIC-SECRET-SENTINEL"
    before = deepcopy(directory)
    plan = plan_merge_prototype(directory, encode(incoming), contract)
    assert directory == before and plan.candidate is None and not plan.changes_required
    assert "SYNTHETIC-SECRET-SENTINEL" not in repr(plan)


def test_new_company_filters_only_unsafe_additional_domains(contract, directory):
    local = deepcopy(directory)
    local["companies"] = local["companies"][:1]
    incoming = deepcopy(directory)
    incoming["companies"] = incoming["companies"][1:]
    incoming["companies"][0]["additional_verified_domains"] = ["alpine.example", "safe.example"]
    plan = plan_merge_prototype(local, encode(incoming), contract)
    assert plan.changes_required and plan.counts["companies_added"] == 1
    assert plan.candidate["companies"][1]["additional_verified_domains"] == ["safe.example"]
    assert not plan_merge_prototype(plan.candidate, encode(incoming), contract).changes_required


def test_settings_merge_disabled_and_no_persistence(qapp):
    settings = {"ticket_prefix": "SYNTHETIC-"}
    dialog = SettingsDialog(settings)
    before = dialog.get_settings()
    assert [b.text() for b in dialog.findChildren(QPushButton)].count("Merge") == 1
    assert not dialog.btn_merge.isEnabled()
    assert "session-only" in dialog.merge_status.text()
    dialog.btn_merge.click()
    dialog.reject()
    assert dialog.get_settings() == before and settings == {"ticket_prefix": "SYNTHETIC-"}
    dialog.deleteLater()


def test_core_has_no_host_storage_or_network_imports():
    import ast
    path = ROOT / "prototypes/company_directory_merge/company_directory_merge.py"
    tree = ast.parse(path.read_text())
    imports = set()
    for node in ast.walk(tree):
        if isinstance(node, ast.Import):
            imports.update(alias.name.split(".")[0] for alias in node.names)
        elif isinstance(node, ast.ImportFrom):
            imports.add(node.module.split(".")[0])
    assert imports <= {"copy", "dataclasses", "datetime", "hashlib", "json", "re", "unicodedata", "uuid", "jsonschema"}
