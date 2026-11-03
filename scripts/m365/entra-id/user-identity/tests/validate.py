"""Offline PS7/Pester + pinned local schema checks. Writes only new evidence here."""
from __future__ import annotations

import copy
from datetime import datetime, timezone
import hashlib
import json
from pathlib import Path
import shutil
import subprocess
import sys
import uuid

from jsonschema import Draft202012Validator, FormatChecker
from referencing import Registry, Resource

HERE = Path(__file__).resolve().parent
OPERATION = HERE.parent
ROOT = OPERATION.parents[3]
CONTRACT = ROOT / "docs/planning/m365/03_codex_reviews/architecture-contract-proposal-20261102"
sys.path.insert(0, str(ROOT))
from src.services.m365_catalog_service import ManifestValidator  # read-only metadata validation


def sha(path):
    return hashlib.sha256(path.read_bytes()).hexdigest()


def read(path):
    return json.loads(path.read_text(encoding="utf-8"))


def validate():
    stamp = datetime.now(timezone.utc).strftime("%Y%m%dT%H%M%SZ") + "-" + uuid.uuid4().hex[:8]
    output = HERE / "evidence" / f"validation-{stamp}.json"
    entry = read(HERE / "evidence/entry-preservation.json")
    inputs = {p: value for p, value in entry["files"].items()
              if p.startswith("docs/planning/") or p in ("AGENTS.md", "GEMINI.md", "scripts/m365/README.md",
                  "assets/m365/categories.json", "assets/m365/catalog.json", "assets/m365/contract-review-pins.json",
                  "src/services/m365_catalog_service.py")}
    report = {"scope": "PROVISIONAL_SYNTHETIC_OFFLINE_ONLY", "started_at": datetime.now(timezone.utc).isoformat().replace("+00:00", "Z"),
              "checks": [], "inputs": inputs, "status": "FAIL"}

    def check(name, passed):
        report["checks"].append({"name": name, "status": "PASS" if passed else "FAIL"})

    try:
        mismatches = [p for p, digest in inputs.items() if not (ROOT / p).is_file() or sha(ROOT / p) != digest]
        check("read_inputs_preserved", not mismatches)
        report["input_mismatches"] = mismatches
        if mismatches:
            raise ValueError("Read contract/input identity changed; independent re-review required.")
        registry = Registry()  # no remote retrieval callback
        schemas = {}
        for path in sorted((CONTRACT / "schemas").glob("*.schema.json")):
            schema = read(path)
            Draft202012Validator.check_schema(schema)
            schemas[path.stem.removesuffix(".schema")] = schema
            registry = registry.with_resource(schema["$id"], Resource.from_contents(schema))
        common = schemas["common"]

        def definition(name):
            return Draft202012Validator({"$ref": common["$id"] + "#/$defs/" + name},
                                        registry=registry, format_checker=FormatChecker())

        design = read(OPERATION / "operation.design.json")
        fixtures = read(HERE / "fixtures.json")
        definition("invocation_context").validate(fixtures["context"])
        check("synthetic_frozen_context_schema", True)
        categories = read(ROOT / "assets/m365/categories.json")["categories"]
        check("category_is_presentation_only", any(c["id"] == design["category"] and c["kind"] == "operations" for c in categories))
        check("production_catalog_remains_empty", read(ROOT / "assets/m365/catalog.json")["operations"] == [])
        check("no_live_executable_or_manifest", not list(OPERATION.glob("*.ps1")) and not list(OPERATION.glob("*manifest*")))
        check("creation_date_not_in_contract", "created_at" not in common["$defs"]["user_identity"]["properties"] and
              len(common["$defs"]["user_identity"]["properties"]) == 5)

        # A schema-only projection exists in RAM, never as a discoverable manifest.
        shared_fixtures = read(CONTRACT / "examples/fixtures.json")["fixtures"]
        projection = copy.deepcopy(next(f["instance"] for f in shared_fixtures if f["name"] == "user_identity.manifest"))
        for key in set(projection) & set(design):
            projection[key] = copy.deepcopy(design[key])
        projection["script_path"] = "entra-id/user-identity/Get-UserIdentity.ps1"
        # Existing synthetic fixture hashes remain synthetic placeholders, not trust.
        Draft202012Validator(schemas["script-manifest"], registry=registry).validate(projection)
        validator = ManifestValidator(CONTRACT, ROOT / "assets/m365/contract-review-pins.json")
        validator.validate(projection)
        check("in_memory_design_manifest_schema_and_semantics", True)
        for name, descriptors in (
            ("reserved", [{"name": "Context", "type": "string", "required": False, "description": "Synthetic invalid"}]),
            ("inverted", [{"name": "Count", "type": "integer", "required": False, "description": "Synthetic invalid", "minimum": 5, "maximum": 1}]),
        ):
            invalid = copy.deepcopy(projection)
            invalid["parameters"] = descriptors
            rejected = False
            try:
                validator.validate(invalid)
            except ValueError:
                rejected = True
            check("reject_" + name + "_parameter_descriptor", rejected)

        pwsh = shutil.which("pwsh")
        if not pwsh:
            raise RuntimeError("PowerShell 7 unavailable; no dependency installation attempted.")
        command = [pwsh, "-NoLogo", "-NoProfile", "-NonInteractive", "-File", str(HERE / "Run-OfflineTests.ps1")]
        report["command"] = command
        run = subprocess.run(command, cwd=ROOT, capture_output=True, text=True, encoding="utf-8", timeout=90)
        report["powershell_exit_code"] = run.returncode
        # Only synthetic fixtures may enter these local test logs.
        report["test_stdout"] = run.stdout
        report["test_stderr"] = run.stderr
        check("powershell_test_runner_exit", run.returncode == 0)
        if run.returncode != 0:
            raise RuntimeError("Offline test runner failed; inspect retained test_stderr and Pester evidence.")
        result = json.loads(run.stdout)
        report["powershell"] = result["powershell"]
        report["pester"] = result["pester"]
        check("pester", result["pester"]["status"] == "PASS")
        check("syntax_and_abi", result["syntax_and_abi"] == "PASS")
        check("all_fixture_cases_exercised", len(result["offline_cases"]) == len(fixtures["cases"]))
        for case in result["offline_cases"]:
            returned = case["return_object"]
            definition("operation_return").validate(returned)
            if returned["data"] is not None:
                definition("user_identity").validate(returned["data"])
            check(case["name"] + ".return_and_payload_schema", True)
        check("reference_input_identities_after_tests", all(sha(ROOT / p) == digest for p, digest in inputs.items()))
        report["status"] = "PASS" if all(c["status"] == "PASS" for c in report["checks"]) else "FAIL"
    except Exception as exc:
        report["failure"] = type(exc).__name__ + ": " + str(exc)
    finally:
        report["finished_at"] = datetime.now(timezone.utc).isoformat().replace("+00:00", "Z")
        report["operation_source_hashes"] = {p.relative_to(OPERATION).as_posix(): sha(p) for p in OPERATION.rglob("*")
                                             if p.is_file() and "evidence" not in p.parts and p.name != "SHA256SUMS.json"}
        with output.open("x", encoding="utf-8", newline="\n") as stream:
            json.dump(report, stream, indent=2)
            stream.write("\n")
    print(json.dumps({"status": report["status"], "checks": len(report["checks"]), "pester": report.get("pester"),
                      "failure": report.get("failure"), "evidence": str(output)}, indent=2))
    return 0 if report["status"] == "PASS" else 1


if __name__ == "__main__":
    raise SystemExit(validate())
