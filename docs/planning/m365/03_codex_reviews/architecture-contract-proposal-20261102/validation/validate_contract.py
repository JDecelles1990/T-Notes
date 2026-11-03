"""Offline proposal checks only. Never import this as a production boundary.

Uses Python stdlib and the schema engine bundled with installed PowerShell 7.
No application import, package install, tenant connection, script execution,
database access, clipboard access or remote schema retrieval.
"""

from __future__ import annotations

import argparse
import copy
from datetime import datetime, timezone
import hashlib
import json
import math
from pathlib import Path, PurePosixPath
import re
import shutil
import subprocess
import sys
import uuid

from correction_checks import (calendar_valid as calendar_sample, parameter_value,
    preflight_sample, make_trusted, add_schema_cases, run_checks)


ROOT = Path(__file__).resolve().parents[1]
REPO = ROOT.parents[4]
VERSION = "0.3.0-proposed.1"
MAX_OUTPUT = 1024 * 1024
PS_ENGINE = r"""
$ErrorActionPreference = 'Stop'
$inputBatch = [Console]::In.ReadToEnd() | ConvertFrom-Json -Depth 100
Test-Json -Json '{}' -Schema '{"type":"object"}' | Out-Null
$options = [Json.Schema.EvaluationOptions]::new()
$options.EvaluateAs = [Json.Schema.SpecVersion]::Draft202012
$options.RequireFormatValidation = $true
# Every schema is explicitly checked below. Avoid recursive automatic checking
# while evaluating the engine's metaschema against schema documents.
$options.ValidateAgainstMetaSchema = $false
foreach ($entry in $inputBatch.schemas) {
    $schema = [Json.Schema.JsonSchema]::FromText([string]$entry.text)
    $options.SchemaRegistry.Register($schema)
}
$metaResults = @()
foreach ($entry in $inputBatch.schemas) {
    $node = [System.Text.Json.Nodes.JsonNode]::Parse([string]$entry.text)
    $ok = [Json.Schema.MetaSchemas]::Draft202012.Evaluate($node, $options).IsValid
    $metaResults += @{name=$entry.name; valid=$ok}
}
$invalidMeta = [System.Text.Json.Nodes.JsonNode]::Parse('{"type":"invalid-type"}')
$metaResults += @{name='engine-negative-metaschema-probe'; valid=([Json.Schema.MetaSchemas]::Draft202012.Evaluate($invalidMeta, $options).IsValid); expected=$false}
$caseResults = @()
foreach ($case in $inputBatch.cases) {
    $reference = @{ '$ref'=[string]$case.reference } | ConvertTo-Json -Compress
    $schema = [Json.Schema.JsonSchema]::FromText($reference)
    $node = [System.Text.Json.Nodes.JsonNode]::Parse([string]$case.instance)
    $ok = $schema.Evaluate($node, $options).IsValid
    $caseResults += @{name=$case.name; valid=$ok; expected=$case.expected}
}
@{powershell=$PSVersionTable.PSVersion.ToString(); engine=[Json.Schema.JsonSchema].Assembly.GetName().Name; engine_version=[Json.Schema.JsonSchema].Assembly.GetName().Version.ToString(); metaschemas=$metaResults; cases=$caseResults} | ConvertTo-Json -Depth 10 -Compress
"""


def strict_loads(raw: str):
    def pairs(items):
        value = {}
        for key, item in items:
            if key in value:
                raise ValueError("duplicate JSON key")
            value[key] = item
        return value

    def nonfinite(_):
        raise ValueError("nonfinite JSON number")

    return json.loads(raw, object_pairs_hook=pairs, parse_constant=nonfinite)


def wire_sample(raw: bytes):
    """Reference acceptance predicate for synthetic samples, not a runtime parser."""
    if len(raw) > MAX_OUTPUT or raw.startswith(b"\xef\xbb\xbf"):
        raise ValueError("output size or BOM")
    value = strict_loads(raw.decode("utf-8", errors="strict"))
    if not isinstance(value, dict):
        raise ValueError("envelope must be an object")

    def visit(item, depth=0):
        if depth > 20:
            raise ValueError("nesting limit")
        if isinstance(item, float) and not math.isfinite(item):
            raise ValueError("nonfinite numeric overflow")
        children = item.values() if isinstance(item, dict) else item if isinstance(item, list) else ()
        for child in children:
            visit(child, depth + 1)

    visit(value)
    return value


def relative_script_sample(path):
    """Lexical checks only: actual reparse/ACL/trust enforcement is NOT RUN."""
    return (
        isinstance(path, str)
        and re.fullmatch(r"(?:[A-Za-z0-9_-]+/)*[A-Za-z0-9_-]+\.ps1", path) is not None
        and not PurePosixPath(path).is_absolute()
        and all(part not in (".", "..") for part in PurePosixPath(path).parts)
    )


def result_binding_sample(request, result, exit_code=None, manifest=None):
    for key in ("company_id", "correlation_id", "script_id", "contract_version", "admin_identity_ref", "session_generation", "target", "release_binding"):
        if request[key] != result[key]:
            return False
    if result["context_state"] == "verified" and result["tenant_id"] != request["tenant_id"]:
        return False
    if result["context_state"] == "unverified" and result["tenant_id"] is not None:
        return False
    if datetime.fromisoformat(result["completed_at"]) < datetime.fromisoformat(result["started_at"]):
        return False
    if exit_code not in (None, 0) or result["operation_exit_code"] != operation_exit(result):
        return False
    data = result["data"]
    if data is not None:
        if result["status"] == "success" and "account_enabled" in data and data["account_enabled"] is None:
            return False
        if result["status"] == "success" and "mailbox_exists" in data and any(data[field] is None for field in ("total_item_size_bytes", "prohibit_send_quota_bytes")):
            return False
        if manifest is None:
            return False
        binding = manifest["target_policy"]["output_binding"]
        field = binding["object_id_field" if request["target"]["kind"] == "object_id" else "upn_field"]
        actual = data.get(field)
        expected = request["target"]["value"]
        if request["target"]["kind"] == "upn":
            from correction_checks import upn_equal
            if not isinstance(actual, str) or not upn_equal(actual, expected):
                return False
        elif actual != expected:
            return False
        for name in ("events", "licenses"):
            if name in data and data["returned_count"] != len(data[name]):
                return False
        for event in data.get("events", []):
            if event["success"] != (event["error_code"] == 0):
                return False
            if not (datetime.fromisoformat(data["lookback_start"]) <= datetime.fromisoformat(event["created_at"]) <= datetime.fromisoformat(result["completed_at"])):
                return False
        if "events" in data and len(data["events"]) > request["parameters"]["MaxRecords"]:
            return False
        if data.get("truncated") and (result["status"] != "partial" or not any(w["code"] == "OUTPUT_LIMIT" for w in result["warnings"])):
            return False
    return "SYNTHETIC_SECRET_SENTINEL" not in json.dumps(result)


def operation_exit(result):
    if result["status"] == "success":
        return 0
    if result["status"] == "partial":
        return 2
    if result["status"] in ("timeout", "cancelled"):
        return 40
    classes = {
        50: {"INTERNAL_ERROR"},
        20: {"AUTH_REQUIRED", "TENANT_MISMATCH", "ACCOUNT_MISMATCH", "ACCESS_DENIED"},
        10: {"INVALID_PARAMETER", "CONTRACT_VIOLATION"},
        40: {"TIMEOUT", "CANCELLED"},
        30: {"TARGET_NOT_FOUND", "MAILBOX_NOT_FOUND", "MODULE_MISSING", "API_THROTTLED", "SERVICE_UNAVAILABLE", "CONNECTION_FAILED", "OUTPUT_LIMIT"},
    }
    codes = {e["code"] for e in result["errors"]}
    return next((number for number, group in classes.items() if codes & group), 50)


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--pwsh", default=shutil.which("pwsh"))
    parser.add_argument("--attempt-name", help="Optional unique correction-results UTC filename; existing evidence is never overwritten")
    args = parser.parse_args()
    if args.attempt_name and (not re.fullmatch(r"correction-results-\d{8}T\d{6}-[0-9a-f]{8}\.json", args.attempt_name)
                              or (ROOT / "validation" / args.attempt_name).exists()):
        parser.error("attempt-name must be a new safe correction-results UTC filename")
    started = datetime.now(timezone.utc).isoformat().replace("+00:00", "Z")
    checks = []
    environment = {"python": sys.version, "powershell_path": args.pwsh}

    def check(name, actual, expected=True):
        checks.append({"name": name, "result": "PASS" if actual == expected else "FAIL", "actual": actual, "expected": expected})

    def rejects(fn):
        try:
            fn()
        except (ValueError, UnicodeError, KeyError, TypeError):
            return True
        return False

    try:
        if not args.pwsh:
            raise RuntimeError("PowerShell 7 not found; schema checks BLOCKED")
        schema_paths = sorted((ROOT / "schemas").glob("*.schema.json"))
        schemas = {p.name: strict_loads(p.read_text(encoding="utf-8")) for p in schema_paths}
        known_ids = {s["$id"] for s in schemas.values()}
        for name, schema in schemas.items():
            check("syntax." + name, schema["$schema"] == "https://json-schema.org/draft/2020-12/schema")
            def refs(item):
                if isinstance(item, dict):
                    if "$ref" in item:
                        reference = item["$ref"]
                        target, _, fragment = reference.partition("#")
                        if target and target not in known_ids:
                            raise ValueError("Unknown schema ref; remote retrieval forbidden")
                        node = next((s for s in schemas.values() if s["$id"] == target), schema)
                        if fragment:
                            for segment in fragment.lstrip("/").split("/"):
                                node = node[segment.replace("~1", "/").replace("~0", "~")]
                    for value in item.values():
                        refs(value)
                elif isinstance(item, list):
                    for value in item:
                        refs(value)
            refs(schema)
            check("offline-refs." + name, True)
        fixture_file = strict_loads((ROOT / "examples/fixtures.json").read_text(encoding="utf-8"))
        check("fixture-version", fixture_file["contract_version"] == VERSION)
        fixtures = fixture_file["fixtures"]
        samples = {f["name"]: f["instance"] for f in fixtures}
        schema_cases = [{"name": f["name"], "reference": schemas[f["schema"]]["$id"] + (f["fragment"] or ""), "instance": json.dumps(f["instance"]), "expected": f["valid"]} for f in fixtures]
        mock = strict_loads((ROOT / "examples/mock-compatibility.json").read_text(encoding="utf-8"))
        add_schema_cases(schema_cases, schemas, mock)
        for key in ("user_identity", "user_licenses", "user_signins", "mailbox_summary"):
            manifest = samples[key + ".manifest"]
            schema_cases.append({"name": "selected-payload." + key, "reference": schemas["operation-data.schema.json"]["$id"] + "#" + manifest["expected_output_schema"].split("#", 1)[1], "instance": json.dumps(samples[key + ".success"]["data"]), "expected": True})
        # Additional negative shapes independent of any production implementation.
        for index, path in enumerate(("/absolute.ps1", "C:/escape.ps1", "//server/file.ps1", "scripts\\file.ps1", "scripts/file.ps1:stream", "scripts/%2e%2e/file.ps1")):
            value = copy.deepcopy(samples["user_identity.manifest"])
            value["script_path"] = path
            schema_cases.append({"name": "negative.path." + str(index), "reference": schemas["script-manifest.schema.json"]["$id"], "instance": json.dumps(value), "expected": False})
        for name, updates in (("errors-on-success", {"errors": [samples["error.ACCESS_DENIED"]]}), ("unverified-context", {"context_state": "unverified"}), ("partial-without-warning", {"status": "partial", "operation_outcome": "partially_succeeded"})):
            value = copy.deepcopy(samples["user_identity.success"])
            value.update(updates)
            schema_cases.append({"name": "negative." + name, "reference": schemas["execution-result.schema.json"]["$id"], "instance": json.dumps(value), "expected": False})
        for name, schema_name, value in (
            ("secret-payload", "operation-data.schema.json", {**samples["user_identity.data"], "access_token": "SYNTHETIC_SECRET_SENTINEL"}),
            ("company-password", "company-profile.schema.json", {**samples["company.synthetic"], "password": "SYNTHETIC_SECRET_SENTINEL"}),
            ("non-powershell-file", "script-manifest.schema.json", {**samples["user_identity.manifest"], "script_path": "scripts/unsafe.exe"}),
            ("excessive-timeout", "script-manifest.schema.json", {**samples["user_identity.manifest"], "timeout_seconds": 301}),
        ):
            schema_cases.append({"name": "negative." + name, "reference": schemas[schema_name]["$id"], "instance": json.dumps(value), "expected": False})
        payload = {"schemas": [{"name": name, "text": json.dumps(schema)} for name, schema in schemas.items()], "cases": schema_cases}
        engine = subprocess.run([args.pwsh, "-NoLogo", "-NoProfile", "-NonInteractive", "-Command", PS_ENGINE], input=json.dumps(payload), text=True, capture_output=True, timeout=90, encoding="utf-8", shell=False)
        if engine.returncode:
            raise RuntimeError("Schema engine failed: " + engine.stderr[:2000])
        engine_result = strict_loads(engine.stdout)
        environment.update({key: engine_result[key] for key in ("powershell", "engine", "engine_version")})
        for group in ("metaschemas", "cases"):
            for row in engine_result[group]:
                if group == "cases":
                    case = next(case for case in schema_cases if case["name"] == row["name"])
                    calendar_valid = calendar_sample(strict_loads(case["instance"]))
                    check("schema-and-format." + row["name"], row["valid"] and calendar_valid, row["expected"])
                    checks[-1].update(schema_engine_valid=row["valid"], calendar_valid=calendar_valid)
                else:
                    check(group + "." + row["name"], row["valid"], row.get("expected", True))

        for key in ("user_identity", "user_licenses", "user_signins", "mailbox_summary"):
            manifest, request, result = (samples[key + suffix] for suffix in (".manifest", ".request", ".success"))
            trusted = make_trusted(manifest, request, mock, schemas)
            check("semantic.preflight." + key, preflight_sample(manifest, request, trusted))
            check("semantic.result-binding." + key, result_binding_sample(request, result, manifest=manifest))
            check("semantic.payload-ref." + key, manifest["expected_output_schema"] == "schemas/operation-data.schema.json#/$defs/" + key)
            # Simulated trust fixture is not registration of an actual executable.
            for field, value in (("tenant_id", str(uuid.uuid4())), ("company_id", str(uuid.uuid4())), ("admin_identity_ref", str(uuid.uuid4())), ("session_generation", 99), ("target", {"kind": "object_id", "value": str(uuid.uuid4())})):
                altered = copy.deepcopy(request)
                altered[field] = value
                check("reject.preflight." + key + "." + field, preflight_sample(manifest, altered, trusted), False)
            for field in ("correlation_id", "tenant_id", "company_id", "script_id"):
                altered = copy.deepcopy(result)
                altered[field] = str(uuid.uuid4())
                check("reject.result." + key + "." + field, result_binding_sample(request, altered, manifest=manifest), False)
            check("reject.nonzero-success." + key, result_binding_sample(request, result, 50, manifest=manifest), False)
            check("reject.unapproved-release." + key, preflight_sample(manifest, request, {**trusted, "release_approved": False}), False)
            check("reject.tampered-hash." + key, preflight_sample(manifest, request, {**trusted, "approved_hash": "f" * 64}), False)
            altered = copy.deepcopy(request)
            altered["parameters"]["Password"] = "SYNTHETIC_SECRET_SENTINEL"
            check("reject.unknown-parameter." + key, preflight_sample(manifest, altered, trusted), False)

        manifest, request = samples["user_signins.manifest"], samples["user_signins.request"]
        trusted = make_trusted(manifest, request, mock, schemas)
        for value in (True, 0, 51, "20", None):
            altered = copy.deepcopy(request)
            altered["parameters"]["MaxRecords"] = value
            check("reject.record-bound." + repr(value), preflight_sample(manifest, altered, trusted), False)
        for spec_change in ("bad_default", "duplicate_parameter", "inverted_bounds"):
            altered = copy.deepcopy(manifest)
            if spec_change == "bad_default":
                altered["parameters"][0]["default"] = 100
            elif spec_change == "duplicate_parameter":
                altered["parameters"].append(altered["parameters"][0])
            else:
                altered["parameters"][0].update(minimum=31, maximum=30)
            check("reject.manifest." + spec_change, preflight_sample(altered, request, trusted), False)
        for risk in ("write", "high_impact"):
            altered = copy.deepcopy(manifest)
            altered["risk"] = risk
            check("reject.unauthorized." + risk, preflight_sample(altered, request, trusted), False)
        write_manifest = copy.deepcopy(manifest)
        write_manifest["risk"] = "write"
        write_manifest["approval_requirements"]["confirmation_required"] = True
        write_request = copy.deepcopy(request)
        write_request["authorization"]["confirmation_ref"] = "66666666-6666-4666-8666-666666666666"
        confirmed = {**trusted, "confirmation_ref": write_request["authorization"]["confirmation_ref"], "confirmation_expired": False, "confirmation_used": False, "confirmed_parameters": dict(request["parameters"])}
        check("semantic.synthetic-confirmation", preflight_sample(write_manifest, write_request, confirmed))
        for field, value in (("confirmation_expired", True), ("confirmation_used", True), ("confirmed_parameters", {})):
            check("reject.confirmation." + field, preflight_sample(write_manifest, write_request, {**confirmed, field: value}), False)
        for key in ("user_licenses", "user_signins"):
            result = copy.deepcopy(samples[key + ".success"])
            result["data"]["returned_count"] = 1
            check("reject.false-count." + key, result_binding_sample(samples[key + ".request"], result, manifest=samples[key + ".manifest"]), False)
        for key, field in (("user_identity", "account_enabled"), ("mailbox_summary", "total_item_size_bytes"), ("mailbox_summary", "prohibit_send_quota_bytes")):
            result = copy.deepcopy(samples[key + ".success"])
            result["data"][field] = None
            check("reject.incomplete-success." + key + "." + field, result_binding_sample(samples[key + ".request"], result, manifest=samples[key + ".manifest"]), False)
            result.update(status="partial", operation_outcome="partially_succeeded", operation_exit_code=2, warnings=[{"code": "PROPERTY_UNAVAILABLE", "message": "Synthetic missing property"}])
            check("semantic.partial-property." + key + "." + field, result_binding_sample(samples[key + ".request"], result, manifest=samples[key + ".manifest"]))
        leaked = copy.deepcopy(samples["user_identity.success"])
        leaked["warnings"] = [{"code": "TEST", "message": "SYNTHETIC_SECRET_SENTINEL"}]
        check("reject.synthetic-secret-in-message", result_binding_sample(samples["user_identity.request"], leaked, manifest=samples["user_identity.manifest"]), False)
        check("exit.success", operation_exit(samples["user_identity.success"]), 0)
        for status, expected in (("partial", 2), ("error", 20), ("cancelled", 40), ("timeout", 40)):
            check("exit." + status, operation_exit(samples["result." + status]), expected)
        for name, error in samples.items():
            if name.startswith("error."):
                expected = 50 if error["code"] == "INTERNAL_ERROR" else 20 if error["code"] in {"AUTH_REQUIRED", "TENANT_MISMATCH", "ACCOUNT_MISMATCH", "ACCESS_DENIED"} else 10 if error["code"] in {"INVALID_PARAMETER", "CONTRACT_VIOLATION"} else 40 if error["code"] in {"TIMEOUT", "CANCELLED"} else 30
                check("exit-code." + error["code"], operation_exit({"status": "error", "errors": [error]}), expected)

        run_checks(check, schemas, samples, mock, result_binding_sample)

        good = json.dumps(samples["user_identity.success"]).encode("utf-8")
        check("wire.single-envelope", wire_sample(good + b"\n") == samples["user_identity.success"])
        check("calendar.valid-leap-day", calendar_sample({"created_at": "2024-02-29T00:00:00Z"}))
        check("calendar.invalid-leap-day", calendar_sample({"created_at": "2026-02-29T00:00:00Z"}), False)
        check("request.synthetic-byte-cap", len(json.dumps(samples["user_identity.request"]).encode("utf-8")) <= 65536)
        check("request.oversize-rejected", len(json.dumps({**samples["user_identity.request"], "parameters": {"Oversize": "x" * 65536}}).encode("utf-8")) > 65536)
        malformed = {"two-envelopes": good + good, "truncated": good[:-1], "invalid-utf8": b"\xff", "bom": b"\xef\xbb\xbf" + good, "duplicate": b'{"x":1,"x":2}', "nested-duplicate": b'{"x":{"y":1,"y":2}}', "nan": b'{"x":NaN}', "overflow": b'{"x":1e309}', "extra-text": good + b"banner", "array-root": b"[]", "size": b" " * (MAX_OUTPUT + 1), "depth": ('{"x":' * 22 + '0' + '}' * 22).encode()}
        for name, raw in malformed.items():
            check("reject.wire." + name, rejects(lambda raw=raw: wire_sample(raw)))
        for path in ("../escape.ps1", "scripts/x.exe", "C:/x.ps1", "//server/x.ps1", "scripts/%2e%2e/x.ps1", "scripts/x.ps1:stream"):
            check("reject.lexical-path." + path, relative_script_sample(path), False)

        for path in ROOT.glob("*.md"):
            text = path.read_text(encoding="utf-8")
            check("markdown.fences." + path.name, text.count("```") % 2 == 0)
            check("markdown.whitespace." + path.name, not any(line.endswith((" ", "\t")) for line in text.splitlines()))
            for target in re.findall(r"\[[^\]]+\]\(([^)]+)\)", text):
                if "://" not in target and not target.startswith("#"):
                    check("link." + path.name + "." + target, (path.parent / target.split("#")[0]).is_file())
        snapshot = strict_loads((ROOT / "validation/source-snapshot.json").read_text(encoding="utf-8"))
        for entry in snapshot["inputs"] + snapshot["prior_drafts"] + snapshot.get("protected_at_task_entry", []):
            check("preservation." + entry["path"], hashlib.sha256((REPO / entry["path"]).read_bytes()).hexdigest() == entry["sha256"])
        baseline = strict_loads((ROOT / "validation/correction-baseline.json").read_text(encoding="utf-8"))
        allowed = {p.relative_to(REPO).as_posix() for p in ROOT.glob("*.md")}
        allowed |= {p.relative_to(REPO).as_posix() for p in (ROOT / "schemas").glob("*.json")}
        allowed |= {(ROOT / p).relative_to(REPO).as_posix() for p in ("examples/fixtures.json", "validation/validate_contract.py")}
        for entry in baseline["files"]:
            if entry["path"] not in allowed:
                check("correction.preservation." + entry["path"], hashlib.sha256((REPO / entry["path"]).read_bytes()).hexdigest() == entry["sha256"])
    except Exception as exc:
        checks.append({"name": "harness-completion", "result": "FAIL", "detail": str(exc)})

    finished = datetime.now(timezone.utc).isoformat().replace("+00:00", "Z")
    failures = [row for row in checks if row["result"] != "PASS"]
    artifact_paths = sorted(p for p in ROOT.rglob("*") if p.is_file() and not p.name.startswith(("results", "correction-results")) and p.name != "correction-baseline.json" and p.suffix in (".md", ".json", ".py"))
    report = {"schema_version": 1, "contract_version": VERSION, "result": "FAIL" if failures else "PASS", "provenance": "FRESH synthetic/offline design validation only", "started_at": started, "finished_at": finished, "command": [sys.executable, "-B", str(Path(__file__).resolve()), "--pwsh", args.pwsh], "environment": environment, "checks_passed": len(checks) - len(failures), "checks_failed": len(failures), "checks": checks, "not_run": ["production parser/worker", "actual filesystem ACL/reparse/integrity enforcement", "application persistence failure injection/hidden editor/Quit", "existing application regression suites", "Pester operation scripts", "Qt/native Windows GUI", "live Microsoft authentication or tenant operations", "independent review of correction candidate"], "artifacts": [{"path": p.relative_to(ROOT).as_posix(), "sha256": hashlib.sha256(p.read_bytes()).hexdigest()} for p in artifact_paths]}
    attempt = args.attempt_name or ("correction-results-" + datetime.now(timezone.utc).strftime("%Y%m%dT%H%M%S") + "-" + uuid.uuid4().hex[:8] + ".json")
    if args.attempt_name:
        report["command"].extend(["--attempt-name", args.attempt_name])
    report["attempt_file"] = attempt
    rendered = json.dumps(report, indent=2, ensure_ascii=False) + "\n"
    (ROOT / "validation" / attempt).write_text(rendered, encoding="utf-8")
    (ROOT / "validation/correction-results.json").write_text(rendered, encoding="utf-8")
    print(json.dumps({"result": report["result"], "passed": report["checks_passed"], "failed": report["checks_failed"], "failures": failures, "report": str(ROOT / "validation/correction-results.json")}, indent=2))
    return 1 if failures else 0


if __name__ == "__main__":
    raise SystemExit(main())
