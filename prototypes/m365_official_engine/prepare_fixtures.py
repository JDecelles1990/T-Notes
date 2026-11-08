"""Explicit test-fixture authoring command, never called by the execution host.

Generates synthetic trust anchors, not approvals. Use only during this offline
prototype's development. Does not install dependencies or modify contract files.
"""
from __future__ import annotations
import copy
from datetime import datetime, timezone
import hashlib
import json
from pathlib import Path
import subprocess

ROOT = Path(__file__).resolve().parent
CONTRACT = ROOT.parents[1] / "docs/contracts/m365"


def sha(path):
    return hashlib.sha256(path.read_bytes()).hexdigest()


def save(name, value):
    path = ROOT / name
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(value, indent=2) + "\n", encoding="utf-8")
    return path


def prepare():
    report = json.loads((ROOT / "accepted-contract.json").read_text())
    assert report["contract_version"] == "0.3.0" and len(report["artifacts"]) == 27
    for entry in report["artifacts"]:
        assert sha(CONTRACT / entry["path"]) == entry["sha256"], entry["path"]
    mock = json.loads((CONTRACT / "examples/mock-compatibility.json").read_text())
    fixtures = json.loads((CONTRACT / "examples/fixtures.json").read_text())
    original = next(x["instance"] for x in fixtures["fixtures"] if x["name"] == "user_identity.manifest")
    manifest = copy.deepcopy(original)
    manifest.update(script_id="M365.TEST.ABI", title="Offline ABI Fixture", description="TEST ONLY: deterministic protocol fixture; no M365 operation.",
                    script_path="scripts/Fixture-Operation.ps1", script_version="0.0.1-provisional", required_modules=[], timeout_seconds=20)
    scenarios = ["success", "error", "partial", "throw", "extra_output", "console_noise", "immutable", "delay",
                 "process_nonzero", "malformed", "duplicate_keys", "invalid_utf8", "two_envelopes", "bad_correlation", "bad_version",
                 "bad_date", "mixed_version", "stderr_secret", "leak_data", "unknown_payload", "wrong_logical_exit", "oversize", "child_hang",
                 "native_hashtable", "native_datetime", "native_datetimeoffset", "native_enum", "native_nested_valid",
                 "native_nested_object", "native_nested_array", "native_nested_dictionary", "native_nested_null",
                 "native_null_data", "native_null_field", "native_cycle", "native_array_cycle", "native_depth",
                 "native_container", "native_nonfinite", "native_getter", "native_outer_dictionary", "native_type_method",
                 "native_nested_array_ets", "native_array_rank", "native_array_lowerbound", "native_array_gettype",
                 "native_array_ets_members", "native_array_multidim", "native_array_nonzero_bound"]
    manifest["parameters"] = [
        {"name": "Scenario", "type": "string", "required": False, "description": "Synthetic test case only", "allowed_values": scenarios, "default": "success", "max_length": 32},
        {"name":"Count","type":"integer","required":False,"description":"Int64 ABI","default":7},
        {"name":"Ratio","type":"number","required":False,"description":"Double ABI","default":1.5},
        {"name":"Flag","type":"boolean","required":False,"description":"Boolean ABI","default":False},
        {"name":"Names","type":"string_array","required":False,"description":"Readonly string list ABI","default":["one","two"]},
        {"name": "DelayMs", "type": "integer", "required": False, "description": "Synthetic cancellable wait", "minimum": 0, "maximum": 15000, "default": 0}]
    manifest["script_sha256"] = sha(ROOT / manifest["script_path"])
    save("manifest.json", manifest)
    pwsh = Path("C:/Program Files/PowerShell/7/pwsh.exe")
    if not pwsh.is_file():
        raise RuntimeError("Explicit local PowerShell 7 path unavailable; no discovery fallback")
    version = subprocess.check_output([str(pwsh), "-NoLogo", "-NoProfile", "-NonInteractive", "-Command", "$PSVersionTable.PSVersion.ToString()"], text=True).strip()
    selection = {k: mock["request"][k] for k in ("company_id", "tenant_id", "admin_identity_ref", "session_generation")}
    save("synthetic-context.json", {"provenance": "PROVISIONAL_OFFLINE_SYNTHETIC", "selection": selection,
                                    "account_upn": "admin@synthetic.example", "powershell_version": version})
    asset_names = ["protocol.ps1", "schema-check.ps1", "worker.ps1", "synthetic-context.json", "manifest.json",
                   "scripts/Fixture-Operation.ps1", "tests/fixtures/Fault-Worker.ps1", "tests/fixtures/Child-Sleeper.ps1"]
    assets = {name: sha(ROOT / name) for name in asset_names}
    inventory = {"provenance": "PROVISIONAL_OFFLINE_SYNTHETIC", "assets": assets,
                 "operations": [{"script_id": manifest["script_id"], "manifest": "manifest.json", "worker": "worker.ps1"}]}
    save("catalog.json", inventory)
    dependencies = sorted(set(pwsh.parent.glob("*.dll")) | set(pwsh.parent.glob("*.json")) |
                          {pwsh.parent / "Modules/Microsoft.PowerShell.Utility/Microsoft.PowerShell.Utility.psd1"})
    anchor = {"contract_version": "0.3.0", "provenance": "PROVISIONAL_OFFLINE_SYNTHETIC",
              "inventory_path": "catalog.json", "inventory_sha256": sha(ROOT / "catalog.json"),
              "powershell": {"path": str(pwsh), "sha256": sha(pwsh)},
              "runtime_dependencies": [{"path": str(p), "sha256": sha(p)} for p in dependencies],
              "contract_artifacts": report["artifacts"], "accepted_contract_sha256": sha(ROOT / "accepted-contract.json")}
    save("trust-anchor.json", anchor)
    fault_inventory = copy.deepcopy(inventory)
    fault_inventory["operations"][0]["worker"] = "tests/fixtures/Fault-Worker.ps1"
    variants = {"fault": (fault_inventory, None)}
    nested = copy.deepcopy(manifest)
    nested["expected_output_schema"] = "schemas/operation-data.schema.json#/$defs/user_signins"
    nested["target_policy"] = {"accepted_kinds": ["object_id"], "requires_resolved_identity": False,
                               "output_binding": {"object_id_field": "target_user_id", "upn_field": None}}
    save("tests/fixtures/manifest-native_nested.json", nested)
    nested_inventory = copy.deepcopy(inventory)
    nested_inventory["assets"]["tests/fixtures/manifest-native_nested.json"] = sha(ROOT / "tests/fixtures/manifest-native_nested.json")
    nested_inventory["operations"][0]["manifest"] = "tests/fixtures/manifest-native_nested.json"
    variants["native_nested"] = (nested_inventory, None)
    for name, mutate in (
        ("untrusted", lambda m: m.update(script_path="scripts/Not-Allowlisted.ps1")),
        ("traversal", lambda m: m.update(script_path="../worker.ps1")),
        ("hash_mismatch", lambda m: m.update(script_sha256="0" * 64)),
        ("bad_descriptor", lambda m: m["parameters"][1].update(minimum=20, maximum=10)),
        ("timeout", lambda m: m.update(timeout_seconds=1)),
        ("write_risk", lambda m: (m.update(risk="write"), m["approval_requirements"].update(confirmation_required=True))),
    ):
        changed = copy.deepcopy(manifest)
        mutate(changed)
        mname = "tests/fixtures/manifest-" + name + ".json"
        save(mname, changed)
        inv = copy.deepcopy(inventory)
        inv["assets"][mname] = sha(ROOT / mname)
        inv["operations"][0]["manifest"] = mname
        variants[name] = (inv, None)
    variants["missing_executable"] = (copy.deepcopy(inventory), "missing_executable")
    variants["executable_mismatch"] = (copy.deepcopy(inventory), "executable_mismatch")
    variants["dependency_mismatch"] = (copy.deepcopy(inventory), "dependency_mismatch")
    variants["fault_timeout"] = (copy.deepcopy(fault_inventory), "fault_timeout")
    pins = {"good": {"file": "trust-anchor.json", "sha256": sha(ROOT / "trust-anchor.json")}}
    for name, (inv, special) in variants.items():
        if special == "fault_timeout":
            inv["assets"]["tests/fixtures/manifest-timeout.json"] = sha(ROOT / "tests/fixtures/manifest-timeout.json")
            inv["operations"][0]["manifest"] = "tests/fixtures/manifest-timeout.json"
        iname = "tests/catalogs/" + name + ".json"
        save(iname, inv)
        a = copy.deepcopy(anchor)
        a.update(inventory_path=iname, inventory_sha256=sha(ROOT / iname))
        if special == "missing_executable":
            a["powershell"]["path"] = str(ROOT / "missing/pwsh.exe")
        elif special == "executable_mismatch":
            a["powershell"]["sha256"] = "0" * 64
        elif special == "dependency_mismatch":
            a["runtime_dependencies"][0]["sha256"] = "0" * 64
        aname = "tests/anchors/" + name + ".json"
        save(aname, a)
        pins[name] = {"file": aname, "sha256": sha(ROOT / aname)}
    save("tests/fixture-pins.json", pins)
    request = copy.deepcopy(mock["request"])
    request.update(script_id=manifest["script_id"], ticket_context=None, parameters={})
    request["release_binding"] = {"script_version": manifest["script_version"], "script_sha256": manifest["script_sha256"],
                                  "manifest_sha256": sha(ROOT / "manifest.json"), "output_schema_sha256": sha(CONTRACT / "schemas/operation-data.schema.json")}
    save("examples/request.json", request)
    save("evidence/gate1.json", {"status": "PASS", "scope": "Author verification of user-accepted contract identities; not independent approval",
                               "contract_version": "0.3.0", "contract_artifacts_verified": 27,
                               "authority": report["authority"],
                               "powershell_version": version, "runtime_files_pinned": len(dependencies),
                               "unresolved": ["Corrected contract final independent signoff remains a documented limitation",
                                              "S1 independent implementation review", "D01-D15 production decisions",
                                              "Real authentication/permissions", "Production signing and release policy",
                                              "One fresh worker per operation; persistent reuse is unsupported"],
                               "timestamp": datetime.now(timezone.utc).isoformat().replace("+00:00", "Z")})
    print(json.dumps({"fixtures": "SAVED", "contract_hashes": 27, "powershell": version, "runtime_files_pinned": len(dependencies)}))


if __name__ == "__main__":
    prepare()
