"""Official catalog compatibility and offline engine provenance; no dispatch."""
import hashlib
import json

import pytest

from src.services.m365_catalog_service import (
    CatalogError, CONTRACT_ROOT, ManifestValidator, ROOT,
)


def validator():
    return ManifestValidator(CONTRACT_ROOT, ROOT / "assets/m365/contract-review-pins.json")


def test_official_manifest_accepted():
    manifest = json.loads((ROOT / "tests/fixtures/m365/manifest.json").read_text())
    assert manifest["contract_version"] == "0.3.0"
    validator().validate(manifest)


@pytest.mark.parametrize("version", ["0.3.0-proposed.1", "0.3.0-proposed.1-mixed", "0.3.1", "0.3"])
def test_catalog_rejects_predecessor_mixed_and_unknown_versions(version):
    manifest = json.loads((ROOT / "tests/fixtures/m365/manifest.json").read_text())
    manifest["contract_version"] = version
    with pytest.raises(CatalogError):
        validator().validate(manifest)


def test_changed_schema_pin_fails_closed(tmp_path):
    pins = json.loads((ROOT / "assets/m365/contract-review-pins.json").read_text())
    pins["schemas"]["common"] = "0" * 64
    path = tmp_path / "pins.json"
    path.write_text(json.dumps(pins))
    with pytest.raises(CatalogError):
        ManifestValidator(CONTRACT_ROOT, path)


def test_official_reference_graph_resolves_locally():
    current = validator()
    count = 0

    def visit(value, resolver):
        nonlocal count
        if isinstance(value, dict):
            if "$ref" in value:
                resolver.lookup(value["$ref"])
                count += 1
            for child in value.values():
                visit(child, resolver)
        elif isinstance(value, list):
            for child in value:
                visit(child, resolver)

    for schema in current.schemas.values():
        visit(schema, current.registry.resolver(schema["$id"]))
    assert count == 97


def test_engine_contract_inventory_and_original_runtime_identity():
    engine = ROOT / "prototypes/m365_official_engine"
    accepted = json.loads((engine / "accepted-contract.json").read_text())
    assert accepted["contract_version"] == "0.3.0"
    assert len(accepted["artifacts"]) == 27
    assert len({item["path"] for item in accepted["artifacts"]}) == 27
    for item in accepted["artifacts"]:
        assert hashlib.sha256((CONTRACT_ROOT / item["path"]).read_bytes()).hexdigest() == item["sha256"]
    anchor = json.loads((engine / "trust-anchor.json").read_text())
    historical = ROOT / "docs/planning/m365/offline-execution-engine-prototype"
    original = json.loads((historical / "trust-anchor.json").read_text())
    assert anchor["powershell"] == original["powershell"]
    assert anchor["runtime_dependencies"] == original["runtime_dependencies"]
    assert (engine / "win_process.py").read_bytes() == (historical / "win_process.py").read_bytes()
    assert anchor["contract_artifacts"] == accepted["artifacts"]
    assert anchor["accepted_contract_sha256"] == hashlib.sha256((engine / "accepted-contract.json").read_bytes()).hexdigest()
