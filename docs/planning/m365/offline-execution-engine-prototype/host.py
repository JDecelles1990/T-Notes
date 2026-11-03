"""PROVISIONAL OFFLINE ENGINE. No GUI, database, credentials or tenant access.

Only the operator-pinned synthetic catalog and synthetic context can dispatch.
An external caller must supply the expected anchor digest; location is no trust.
"""
from __future__ import annotations
from dataclasses import dataclass
import hashlib
import os
from pathlib import Path
import re
import threading
import time
import uuid

from contracts import (COMMON, VERSION, MAX_INPUT, MAX_OUTPUT, MESSAGES, Rejected,
                       fail, encode, strict_json, normalize, bind_parameters,
                       calendar, timestamp, utc, logical_exit, check_binding, sanitize, reject_sensitive_request)
from win_process import PinnedFiles, ProcessError, run_owned, Capture


def digest(path):
    return hashlib.sha256(Path(path).read_bytes()).hexdigest()


def local_path(root, name):
    if not isinstance(name, str) or not re.fullmatch(r"(?:[A-Za-z0-9_-]+/)*[A-Za-z0-9_-]+(?:\.[A-Za-z0-9_-]+)+", name):
        fail()
    path = Path(os.path.abspath(root / name))
    if not path.is_relative_to(root):
        fail()
    return path


@dataclass
class Execution:
    response: dict | None
    error_code: str | None
    message: str | None
    process_exit_code: int | None
    logical_exit_code: int | None
    telemetry: dict
    provenance: str = "PROVISIONAL_OFFLINE_SYNTHETIC"


class Catalog:
    def __init__(self, root, expected_anchor_sha256, pins, anchor_name="trust-anchor.json"):
        self.root = Path(os.path.abspath(root))
        anchor_path = pins.pin(local_path(self.root, anchor_name), expected_anchor_sha256)
        self.anchor = strict_json(anchor_path.read_bytes())
        if self.anchor.get("contract_version") != VERSION or self.anchor.get("provenance") != "PROVISIONAL_OFFLINE_SYNTHETIC":
            fail()
        exe = Path(self.anchor["powershell"]["path"])
        if not exe.is_absolute() or not re.fullmatch(r"[A-Za-z]:", exe.drive) or exe.name.lower() != "pwsh.exe" or not exe.is_file():
            fail("MODULE_MISSING")
        self.executable = pins.pin(exe, self.anchor["powershell"]["sha256"])
        if not self.anchor["runtime_dependencies"]:
            fail()
        for dep in self.anchor["runtime_dependencies"]:
            dep_path = Path(dep["path"])
            if not dep_path.is_absolute() or not dep_path.is_relative_to(exe.parent):
                fail()
            pins.pin(dep_path, dep["sha256"])
        self.contract = self.root.parent / "03_codex_reviews/architecture-contract-proposal-20261102"
        if len(self.anchor["contract_artifacts"]) != 21:
            fail()
        for entry in self.anchor["contract_artifacts"]:
            pins.pin(local_path(self.contract, entry["path"]), entry["sha256"])
        self.schemas = {}
        for path in sorted((self.contract / "schemas").glob("*.schema.json")):
            value = strict_json(path.read_bytes())
            if value["$id"] != f"https://tnotes.invalid/m365/{VERSION}/schemas/{path.name}":
                fail()
            self.schemas[path.name] = value
        if len(self.schemas) != 7:
            fail()
        known = {s["$id"] for s in self.schemas.values()}
        def refs(value):
            if isinstance(value, dict):
                if "$ref" in value and value["$ref"].split("#")[0] not in known | {""}:
                    fail()
                for item in value.values():
                    refs(item)
            elif isinstance(value, list):
                for item in value:
                    refs(item)
        for schema in self.schemas.values():
            refs(schema)
        inv_path = pins.pin(local_path(self.root, self.anchor["inventory_path"]), self.anchor["inventory_sha256"])
        self.inventory = strict_json(inv_path.read_bytes())
        if self.inventory.get("provenance") != "PROVISIONAL_OFFLINE_SYNTHETIC":
            fail()
        self.assets = self.inventory["assets"]
        for name, sha in self.assets.items():
            pins.pin(local_path(self.root, name), sha)
        self.entries = self.inventory["operations"]
        ids = [x["script_id"] for x in self.entries]
        if len(set(ids)) != len(ids):
            fail()
        self.fixture = strict_json((self.root / "synthetic-context.json").read_bytes())
        if "synthetic-context.json" not in self.assets:
            fail()

    def asset(self, name):
        if name not in self.assets:
            fail()
        return local_path(self.root, name)

    def resolve(self, script_id):
        matches = [e for e in self.entries if e["script_id"] == script_id]
        if len(matches) != 1:
            fail("INVALID_PARAMETER")
        entry = matches[0]
        manifest_path = self.asset(entry["manifest"])
        manifest = strict_json(manifest_path.read_bytes())
        if manifest["script_id"] != script_id or manifest["contract_version"] != VERSION:
            fail()
        path = self.asset(manifest["script_path"])
        if path.suffix != ".ps1" or digest(path) != manifest["script_sha256"]:
            fail()
        if manifest["risk"] != "read_only" or manifest["execution_mode"] != "isolated_worker":
            fail("ACCESS_DENIED")
        schema_path, fragment = manifest["expected_output_schema"].split("#", 1)
        if not re.fullmatch(r"schemas/[a-z][a-z0-9-]*\.schema\.json", schema_path) or not re.fullmatch(r"/\$defs/[a-z_]+", fragment):
            fail()
        payload_path = local_path(self.contract, schema_path)
        if payload_path.name not in self.schemas:
            fail()
        payload = self.schemas[payload_path.name]
        for part in fragment.strip("/").split("/"):
            payload = payload[part]
        while "$ref" in payload:
            reference, pointer = payload["$ref"].split("#", 1)
            payload = next(v for v in self.schemas.values() if v["$id"] == reference)
            for part in pointer.strip("/").split("/"):
                payload = payload[part]
        binding = manifest["target_policy"]["output_binding"]
        for kind, field, suffix in (("object_id", binding["object_id_field"], "guid"), ("upn", binding["upn_field"], "upn")):
            if kind in manifest["target_policy"]["accepted_kinds"] and field is None:
                fail()
            if field is not None and (field not in payload["required"] or not payload["properties"][field].get("$ref", "").endswith("/$defs/" + suffix)):
                fail()
        release = {"script_version": manifest["script_version"], "script_sha256": manifest["script_sha256"],
                   "manifest_sha256": digest(manifest_path), "output_schema_sha256": digest(payload_path)}
        return manifest, release, entry


class SchemaValidator:
    """Uses pinned PowerShell-bundled Draft 2020-12 engine, plus calendar checks."""
    def __init__(self, catalog):
        self.catalog = catalog

    def validate(self, cases, timeout=15):
        c = self.catalog
        payload = {"schemas": list(c.schemas.values()), "cases": [{"reference": ref, "instance": value} for ref, value in cases]}
        result = run_owned([str(c.executable), "-NoLogo", "-NoProfile", "-NonInteractive", "-File", str(c.asset("schema-check.ps1"))],
                           encode(payload), timeout=timeout, stdout_limit=65536, cwd=c.root)
        if result.terminal == "TIMEOUT":
            fail("TIMEOUT")
        if result.terminal or result.process_exit != 0:
            fail()
        answer = strict_json(result.stdout, 65536, wire=True)
        if answer.get("valid") is not True:
            fail("INVALID_PARAMETER")
        for _, value in cases:
            calendar(value)


class Engine:
    def __init__(self, prototype_root, expected_anchor_sha256, anchor_name="trust-anchor.json", on_started=None):
        self.root = Path(os.path.abspath(prototype_root))
        self.anchor_sha256 = expected_anchor_sha256
        self.anchor_name = anchor_name
        self.on_started = on_started
        self._gate = threading.Lock()

    def execute(self, incoming, cancellation=None):
        if not self._gate.acquire(blocking=False):
            return Execution(None, "ACCESS_DENIED", MESSAGES["ACCESS_DENIED"], None, None, {"states": ["rejected_busy"]})
        request, capture, validated = None, None, False
        start, start_wall = time.monotonic(), utc()
        try:
            request = normalize(incoming)
            reject_sensitive_request(request)
            if request.get("contract_version") != VERSION:
                fail()
            with PinnedFiles() as pins:
                catalog = Catalog(self.root, self.anchor_sha256, pins, self.anchor_name)
                validator = SchemaValidator(catalog)
                validator.validate([(catalog.schemas["execution-request.schema.json"]["$id"], request)])
                validated = True
                manifest, release, entry = catalog.resolve(request["script_id"])
                validator.validate([(catalog.schemas["script-manifest.schema.json"]["$id"], manifest)])
                if request["release_binding"] != release:
                    fail()
                request["parameters"] = bind_parameters(manifest["parameters"], request["parameters"])
                if len(encode(request)) > MAX_INPUT:
                    fail("OUTPUT_LIMIT")
                if request["target"]["kind"] not in manifest["target_policy"]["accepted_kinds"]:
                    fail("INVALID_PARAMETER")
                # No real auth adapter exists here. Only an explicitly pinned synthetic identity.
                fixture = catalog.fixture
                for key, code in (("company_id", "TENANT_MISMATCH"), ("tenant_id", "TENANT_MISMATCH"),
                                  ("admin_identity_ref", "ACCOUNT_MISMATCH"), ("session_generation", "AUTH_REQUIRED")):
                    if request[key] != fixture["selection"][key]:
                        fail(code)
                if manifest["target_policy"]["requires_resolved_identity"]:
                    fail("AUTH_REQUIRED")  # No synthetic resolution service is implemented.
                if manifest["connection_requirements"] != ["Graph"] or manifest["graph_scopes"] != ["User.Read.All"] or manifest["required_roles"]:
                    fail("AUTH_REQUIRED")
                if manifest["required_modules"]:
                    fail("MODULE_MISSING")  # Test fixture operations have no M365 modules.
                if manifest["supported_powershell"]["edition"] != "Core":
                    fail("MODULE_MISSING")
                if tuple(map(int, fixture["powershell_version"].split("."))) < tuple(map(int, manifest["supported_powershell"]["minimum_version"].split("."))):
                    fail("MODULE_MISSING")
                if cancellation and cancellation.is_set():
                    return self._host_failure(request, "CANCELLED", start_wall, start, None, False)
                operation_start, operation_wall = time.monotonic(), utc()
                def control(reason):
                    return encode({"message_type": "cancel", "contract_version": VERSION,
                                   "correlation_id": request["correlation_id"], "company_id": request["company_id"],
                                   "session_generation": request["session_generation"],
                                   "reason": "deadline" if reason == "TIMEOUT" else "user_cancel"}) + b"\n"
                capture = run_owned([str(catalog.executable), "-NoLogo", "-NoProfile", "-NonInteractive", "-File",
                                     str(catalog.asset(entry["worker"])), "-PrototypeRoot", str(catalog.root),
                                     "-ContractRoot", str(catalog.contract)],
                                    encode(request) + b"\n", timeout=manifest["timeout_seconds"], cancel=cancellation,
                                    control=control, framed=True, cwd=catalog.root, on_started=self.on_started)
                if capture.terminal:
                    return self._host_failure(request, capture.terminal, operation_wall, operation_start, capture, True)
                if capture.process_exit != 0 or capture.stderr_bytes:
                    fail()
                response = strict_json(capture.stdout, MAX_OUTPUT, wire=True)
                remaining = manifest["timeout_seconds"] - (time.monotonic() - operation_start)
                if remaining <= 0 or cancellation and cancellation.is_set():
                    return self._host_failure(request, "CANCELLED" if cancellation and cancellation.is_set() else "TIMEOUT", operation_wall, operation_start, capture, True)
                schema_ref = catalog.schemas[manifest["expected_output_schema"].split("#")[0].split("/")[-1]]["$id"] + "#" + manifest["expected_output_schema"].split("#")[1]
                cases = [(catalog.schemas["execution-result.schema.json"]["$id"], response)]
                if response.get("data") is not None:
                    cases.append((schema_ref, response["data"]))
                try:
                    validator.validate(cases, timeout=min(remaining, 15))
                except Rejected as exc:
                    if exc.code == "TIMEOUT":
                        raise
                    fail()
                check_binding(request, response, manifest)
                response = sanitize(response)
                remaining = manifest["timeout_seconds"] - (time.monotonic() - operation_start)
                if remaining <= 0:
                    return self._host_failure(request, "TIMEOUT", operation_wall, operation_start, capture, True)
                try:
                    validator.validate([(catalog.schemas["execution-result.schema.json"]["$id"], response)] + ([(schema_ref, response["data"])] if response["data"] is not None else []), timeout=min(remaining, 15))
                except Rejected as exc:
                    if exc.code == "TIMEOUT":
                        raise
                    fail()
                check_binding(request, response, manifest)
                # Commit only after complete validation; pending cancel/deadline wins.
                if time.monotonic() - operation_start >= manifest["timeout_seconds"] or cancellation and cancellation.is_set():
                    return self._host_failure(request, "CANCELLED" if cancellation and cancellation.is_set() else "TIMEOUT", operation_wall, operation_start, capture, True)
                response["duration_ms"] = int((time.monotonic() - operation_start) * 1000)
                return Execution(response, None, None, capture.process_exit, response["operation_exit_code"], self._telemetry(capture))
        except Rejected as exc:
            if validated:
                return self._host_failure(request, exc.code, start_wall, start, capture, capture is not None)
            return Execution(None, exc.code, MESSAGES.get(exc.code, MESSAGES["CONTRACT_VIOLATION"]), None, None, {"states": ["rejected"]})
        except (OSError, ProcessError, KeyError, TypeError, ValueError, StopIteration):
            code = "CONTRACT_VIOLATION"
            if validated:
                return self._host_failure(request, code, start_wall, start, capture, capture is not None)
            return Execution(None, code, MESSAGES[code], None, None, {"states": ["rejected"]})
        finally:
            self._gate.release()

    @staticmethod
    def _telemetry(capture):
        if capture is None:
            return {"states": ["rejected"], "dispatched": False}
        return {k: getattr(capture, k) for k in ("worker_pid", "max_job_active", "final_job_active", "control_sent", "forced", "elapsed_ms", "states")} | {"dispatched": True, "stderr_bytes": capture.stderr_bytes}

    def _host_failure(self, request, code, wall, start, capture, dispatched):
        response = {k: request[k] for k in ("contract_version", "script_id", "correlation_id", "company_id",
                                           "admin_identity_ref", "session_generation", "target", "release_binding")}
        status = "timeout" if code == "TIMEOUT" else "cancelled" if code == "CANCELLED" else "error"
        response.update(tenant_id=None, context_state="unverified", origin="host", status=status,
                        operation_outcome="unknown" if dispatched else "not_started", started_at=wall,
                        completed_at=utc(), duration_ms=min(305000, int((time.monotonic() - start) * 1000)),
                        data=None, warnings=[], errors=[{"code": code, "message": MESSAGES.get(code, MESSAGES["CONTRACT_VIOLATION"]), "retryable": False}])
        response["operation_exit_code"] = logical_exit(response)
        if capture:
            response["diagnostics"] = {"stage": "capture", "worker_exit_code": capture.process_exit, "attempt_count": 1,
                                       "output_truncated": code == "OUTPUT_LIMIT"}
        return Execution(response, code, response["errors"][0]["message"], capture.process_exit if capture else None,
                         response["operation_exit_code"], self._telemetry(capture))
