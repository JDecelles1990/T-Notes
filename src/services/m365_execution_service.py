"""Offline synthetic M365 execution, history, and note-insertion service (S2/S3).

All operations run against local synthetic fixtures or mocked cmdlets inside an
isolated PowerShell 7 worker with native return validation and Draft 2020-12
JSON Schema enforcement. Live Microsoft 365 authentication and tenant dispatch
remain disabled pending separate authorization.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from datetime import datetime, timezone
import hashlib
import json
import math
from pathlib import Path
import re
import shutil
import subprocess
import threading
import time
import unicodedata
from uuid import uuid4

from jsonschema import Draft202012Validator
from referencing import Registry, Resource

from src.services.m365_catalog_service import (
    CONTRACT_ROOT,
    M365CatalogService,
    ROOT,
    SCHEMAS,
    VERSION,
)


SYNTHETIC_CATALOG_PATH = ROOT / "assets/m365/synthetic-catalog.json"
SYNTHETIC_METADATA_DIR = ROOT / "assets/m365_synthetic"
LIBRARY_ROOT = ROOT / "scripts/m365"
PROTOCOL_PATH = ROOT / "prototypes/m365_official_engine/protocol.ps1"

MAX_INPUT = 65536
MAX_OUTPUT = 1048576

SAFE_MESSAGES = {
    "INVALID_PARAMETER": "Correct the request target or approved parameter values.",
    "CONTRACT_VIOLATION": "Review the pinned contract, catalog and worker protocol evidence.",
    "MODULE_MISSING": "Configure the explicitly trusted PowerShell executable and dependencies.",
    "AUTH_REQUIRED": "Confirm the company and connect the required synthetic service first.",
    "TENANT_MISMATCH": "The service connection tenant does not match the confirmed company tenant.",
    "ACCOUNT_MISMATCH": "The service connection account does not match the selected administrator.",
    "ACCESS_DENIED": "This operation is unavailable or denied under the current synthetic policy.",
    "TARGET_NOT_FOUND": "No matching synthetic fixture target exists.",
    "MAILBOX_NOT_FOUND": "No Exchange Online mailbox exists for the resolved target user.",
    "API_THROTTLED": "The synthetic provider throttled the request; retry after backoff.",
    "SERVICE_UNAVAILABLE": "The synthetic service is temporarily unavailable.",
    "CONNECTION_FAILED": "The synthetic connection is in an error or expired state.",
    "TIMEOUT": "The deadline expired; verify the outcome before an explicit new attempt.",
    "CANCELLED": "Cancellation was requested; no rollback or automatic retry is implied.",
    "OUTPUT_LIMIT": "The bounded transport limit was reached; narrow the operation.",
    "INTERNAL_ERROR": "The owned worker failed; investigate the safe correlation diagnostics.",
    "PROPERTY_UNAVAILABLE": "A synthetic property is unavailable in this partial fixture.",
}

SENSITIVE_RE = re.compile(
    r"(?i)(SYNTHETIC_SECRET_SENTINEL|bearer\s+\S+|(?:access_token|refresh_token|password)\s*[:=]\s*\S+|sk-proj-[a-z0-9_-]+)"
)


def utc_now() -> str:
    return datetime.now(timezone.utc).isoformat(timespec="seconds").replace("+00:00", "Z")


def sha256_file(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


def ensure_synthetic_metadata_dir() -> Path:
    """Ensure assets/m365_synthetic has synchronized categories, pins, and synthetic catalog."""
    SYNTHETIC_METADATA_DIR.mkdir(parents=True, exist_ok=True)
    base_assets = ROOT / "assets/m365"
    for name in ("categories.json", "contract-review-pins.json"):
        src = base_assets / name
        dst = SYNTHETIC_METADATA_DIR / name
        if not dst.exists() or dst.read_bytes() != src.read_bytes():
            shutil.copyfile(src, dst)
    catalog_dst = SYNTHETIC_METADATA_DIR / "catalog.json"
    if SYNTHETIC_CATALOG_PATH.exists():
        if not catalog_dst.exists() or catalog_dst.read_bytes() != SYNTHETIC_CATALOG_PATH.read_bytes():
            shutil.copyfile(SYNTHETIC_CATALOG_PATH, catalog_dst)
    return SYNTHETIC_METADATA_DIR


def build_synthetic_catalog_service(
    metadata_root: Path | None = None,
    library_root: Path | None = None,
    contract_root: Path | None = None,
) -> M365CatalogService:
    """Build an M365CatalogService populated with the 4 S2 User Snapshot operations."""
    meta = Path(metadata_root) if metadata_root is not None else ensure_synthetic_metadata_dir()
    lib = Path(library_root) if library_root is not None else LIBRARY_ROOT
    contract = Path(contract_root) if contract_root is not None else CONTRACT_ROOT
    return M365CatalogService(meta, lib, contract)


@dataclass(frozen=True)
class NoteInsertionPreview:
    token: str
    correlation_id: str
    script_id: str
    company_id: str
    tenant_id: str
    session_generation: int
    formatted_text: str
    text_sha256: str
    consumed: bool = False


@dataclass
class ExecutionOutcome:
    correlation_id: str
    script_id: str
    status: str
    operation_outcome: str
    result_envelope: dict
    history_record: dict
    summary_text: str
    sanitized_json: str
    insertion_preview: NoteInsertionPreview | None = None
    provenance: str = "synthetic"


class M365ExecutionService:
    """Manages S2/S3 offline synthetic PowerShell execution, cancellation, history, and note insertion."""

    def __init__(
        self,
        context_service,
        catalog_service: M365CatalogService | None = None,
        *,
        library_root: Path | None = None,
        contract_root: Path | None = None,
        pwsh_path: Path | None = None,
        max_history: int = 100,
    ):
        self.context_service = context_service
        self.catalog_service = catalog_service or build_synthetic_catalog_service()
        self.library_root = Path(library_root) if library_root is not None else LIBRARY_ROOT
        self.contract_root = Path(contract_root) if contract_root is not None else CONTRACT_ROOT
        self.pwsh_path = self._discover_pwsh(pwsh_path)
        self.max_history = max_history

        self._lock = threading.Lock()
        self._state = "idle"
        self._active_correlation_id: str | None = None
        self._cancel_event: threading.Event | None = None
        self._history: list[dict] = []
        self._results_by_correlation: dict[str, ExecutionOutcome] = {}
        self._previews: dict[str, NoteInsertionPreview] = {}
        self._resolved_identities: dict[tuple[str, str, str, int], dict[str, str]] = {}

        self._schemas, self._registry = self._load_schemas()

    @staticmethod
    def _discover_pwsh(explicit: Path | None) -> Path:
        if explicit is not None:
            return Path(explicit)
        anchor_path = ROOT / "prototypes/m365_official_engine/trust-anchor.json"
        if anchor_path.is_file():
            try:
                anchor = json.loads(anchor_path.read_text(encoding="utf-8"))
                candidate = Path(anchor["powershell"]["path"])
                if candidate.is_file():
                    return candidate
            except (OSError, ValueError, KeyError):
                pass
        found = shutil.which("pwsh")
        return Path(found) if found else Path("C:/Program Files/PowerShell/7/pwsh.exe")

    def _load_schemas(self) -> tuple[dict[str, dict], Registry]:
        schemas: dict[str, dict] = {}
        registry = Registry()
        for name in SCHEMAS:
            path = self.contract_root / f"schemas/{name}.schema.json"
            schema = json.loads(path.read_text(encoding="utf-8"))
            Draft202012Validator.check_schema(schema)
            registry = registry.with_resource(schema["$id"], Resource.from_contents(schema))
            schemas[name] = schema
        return schemas, registry

    def _validate_schema(self, schema_name: str, instance: dict, fragment: str | None = None) -> None:
        base_schema = self._schemas[schema_name]
        if fragment:
            target_schema = {"$ref": f"{base_schema['$id']}#{fragment.lstrip('#')}"}
        else:
            target_schema = base_schema
        validator = Draft202012Validator(target_schema, registry=self._registry)
        if not validator.is_valid(instance):
            errors = sorted(validator.iter_errors(instance), key=lambda e: list(e.path))
            detail = errors[0].message if errors else "Schema validation failed"
            raise ValueError(f"Schema validation failed ({schema_name}): {detail}")

    @property
    def state(self) -> str:
        return self._state

    @property
    def history(self) -> tuple[dict, ...]:
        return tuple(self._history)

    def clear_history(self) -> None:
        self._history.clear()
        self._results_by_correlation.clear()
        self._previews.clear()

    def get_outcome(self, correlation_id: str) -> ExecutionOutcome | None:
        return self._results_by_correlation.get(correlation_id)

    def manifest_for(self, script_id: str) -> tuple[dict, Path, dict]:
        operation = self.catalog_service.operation(script_id)
        details = json.loads(operation.details)
        script_rel = details["script_path"]
        manifest_path = (self.library_root / script_rel).parent / "operation.manifest.json"
        if not manifest_path.is_file():
            # Fallback for custom test library layouts
            for candidate in self.library_root.rglob("*.json"):
                try:
                    data = json.loads(candidate.read_text(encoding="utf-8"))
                    if data.get("script_id") == script_id:
                        manifest_path = candidate
                        break
                except (OSError, ValueError):
                    continue
        manifest = json.loads(manifest_path.read_text(encoding="utf-8"))
        self._validate_schema("script-manifest", manifest)
        schema_rel = manifest["expected_output_schema"].split("#", 1)[0]
        output_schema_path = self.contract_root / schema_rel
        release_binding = {
            "script_version": manifest["script_version"],
            "script_sha256": manifest["script_sha256"],
            "manifest_sha256": sha256_file(manifest_path),
            "output_schema_sha256": sha256_file(output_schema_path),
        }
        return manifest, manifest_path, release_binding

    def bind_parameters(self, manifest: dict, supplied: dict | None) -> dict:
        supplied = dict(supplied or {})
        specs = {p["name"]: p for p in manifest.get("parameters", [])}
        if set(supplied) - set(specs):
            raise ValueError("INVALID_PARAMETER")
        effective: dict = {}
        for name, spec in specs.items():
            if name in supplied:
                val = supplied[name]
            elif "default" in spec:
                val = spec["default"]
            elif spec.get("required"):
                raise ValueError("INVALID_PARAMETER")
            else:
                continue

            kind = spec["type"]
            if kind == "integer":
                if type(val) is not int:
                    raise ValueError("INVALID_PARAMETER")
                if not spec.get("minimum", -math.inf) <= val <= spec.get("maximum", math.inf):
                    raise ValueError("INVALID_PARAMETER")
            elif kind == "number":
                if type(val) not in (int, float) or not math.isfinite(val):
                    raise ValueError("INVALID_PARAMETER")
                if not spec.get("minimum", -math.inf) <= val <= spec.get("maximum", math.inf):
                    raise ValueError("INVALID_PARAMETER")
            elif kind == "boolean":
                if type(val) is not bool:
                    raise ValueError("INVALID_PARAMETER")
            elif kind == "string":
                if not isinstance(val, str) or not spec.get("min_length", 0) <= len(val) <= spec.get("max_length", 4096):
                    raise ValueError("INVALID_PARAMETER")
            elif kind == "string_array":
                if not isinstance(val, list) or not spec.get("min_items", 0) <= len(val) <= spec.get("max_items", 1000):
                    raise ValueError("INVALID_PARAMETER")
                if not all(isinstance(x, str) and spec.get("item_min_length", 0) <= len(x) <= spec.get("item_max_length", 4096) for x in val):
                    raise ValueError("INVALID_PARAMETER")
            if "allowed_values" in spec and val not in spec["allowed_values"]:
                raise ValueError("INVALID_PARAMETER")
            effective[name] = val
        return effective

    def check_operation_eligibility(self, script_id: str) -> tuple[bool, tuple[str, ...]]:
        """Evaluate whether a synthetic operation can be dispatched in the current context."""
        try:
            manifest, _, _ = self.manifest_for(script_id)
        except Exception as exc:
            return False, (f"INVALID_MANIFEST: {exc}",)

        ctx = self.context_service
        company = ctx.company
        reasons: list[str] = []
        if company is None:
            reasons.append("COMPANY_REQUIRED: Select a company first.")
        elif ctx.confirmed_company != (company.company_id, company.tenant_id, ctx.directory.revision, ctx.session_generation):
            reasons.append("COMPANY_CONFIRMATION_REQUIRED: Confirm the selected company.")

        for service_name in manifest.get("connection_requirements", []):
            conn = ctx.connections.state(service_name)
            if conn.state not in ("simulated", "permission_warning", "verified"):
                reasons.append(f"{service_name}: AUTH_REQUIRED ({conn.state})")
            else:
                if company and conn.tenant_id != company.tenant_id:
                    reasons.append(f"{service_name}: TENANT_MISMATCH")
                if conn.account_upn and conn.account_upn.casefold() != ctx.administrator_upn.casefold():
                    reasons.append(f"{service_name}: ACCOUNT_MISMATCH")
                if conn.session_generation != ctx.session_generation:
                    reasons.append(f"{service_name}: STALE_CONTEXT")

        target_policy = manifest["target_policy"]
        requires_resolved = target_policy.get("requires_resolved_identity", False)
        accepted_kinds = target_policy.get("accepted_kinds", [])

        if requires_resolved:
            resolved_id = self._resolve_object_id_for_current_context()
            if not resolved_id:
                reasons.append("TARGET_UNRESOLVED: Run Get-UserIdentity or Resolve Target (synthetic) first.")
        else:
            try:
                target = ctx.target_input.contract_target()
                if target["kind"] not in accepted_kinds:
                    reasons.append(f"TARGET_KIND_UNSUPPORTED: Requires {', '.join(accepted_kinds)}.")
            except ValueError:
                if ctx.target is not None and "object_id" in accepted_kinds:
                    pass
                else:
                    reasons.append("TARGET_REQUIRED: Enter a target UPN or Entra object ID.")

        return len(reasons) == 0, tuple(reasons)

    def _resolve_object_id_for_current_context(self) -> str | None:
        ctx = self.context_service
        company = ctx.company
        if company is None:
            return None
        if (
            ctx.target is not None
            and ctx.target.tenant_id == company.tenant_id
            and ctx.target.session_generation == ctx.session_generation
        ):
            return ctx.target.object_id
        key = (company.company_id, company.tenant_id, ctx.admin_identity_ref, ctx.session_generation)
        cached = self._resolved_identities.get(key)
        if cached:
            return cached.get("object_id")
        return None

    def request_cancel(self) -> bool:
        """Signal cooperative cancellation for the active operation."""
        if self._cancel_event is not None and self._state == "running":
            self._state = "cancelling"
            self._cancel_event.set()
            return True
        return False

    def execute(
        self,
        script_id: str,
        parameters: dict | None = None,
        *,
        ticket_id: str | int | None = None,
        cancellation: threading.Event | None = None,
        on_started=None,
    ) -> ExecutionOutcome:
        """Execute an offline synthetic M365 operation through the real PowerShell 7 worker boundary."""
        if not self._lock.acquire(blocking=False):
            return self._build_rejected_outcome(
                script_id,
                "ACCESS_DENIED",
                "Another operation is currently running; wait or cancel it first.",
            )

        correlation_id = str(uuid4())
        self._active_correlation_id = correlation_id
        self._cancel_event = cancellation if cancellation is not None else threading.Event()
        self._state = "running"
        requested_at = utc_now()
        started_monotonic = time.monotonic()

        try:
            manifest, _, release_binding = self.manifest_for(script_id)
            ctx = self.context_service
            company = ctx.company
            if company is None:
                return self._build_rejected_outcome(script_id, "AUTH_REQUIRED", SAFE_MESSAGES["AUTH_REQUIRED"], correlation_id, release_binding, requested_at)

            if ctx.confirmed_company != (company.company_id, company.tenant_id, ctx.directory.revision, ctx.session_generation):
                return self._build_rejected_outcome(script_id, "AUTH_REQUIRED", SAFE_MESSAGES["AUTH_REQUIRED"], correlation_id, release_binding, requested_at)

            try:
                bound_params = self.bind_parameters(manifest, parameters)
            except ValueError:
                return self._build_rejected_outcome(script_id, "INVALID_PARAMETER", SAFE_MESSAGES["INVALID_PARAMETER"], correlation_id, release_binding, requested_at)

            # Check service connections
            connections_abi: list[dict] = []
            for service_name in manifest.get("connection_requirements", []):
                conn = ctx.connections.state(service_name)
                if conn.state == "error":
                    return self._build_rejected_outcome(script_id, "CONNECTION_FAILED", SAFE_MESSAGES["CONNECTION_FAILED"], correlation_id, release_binding, requested_at)
                if conn.state not in ("simulated", "permission_warning", "verified"):
                    return self._build_rejected_outcome(script_id, "AUTH_REQUIRED", SAFE_MESSAGES["AUTH_REQUIRED"], correlation_id, release_binding, requested_at)
                if conn.tenant_id != company.tenant_id:
                    return self._build_rejected_outcome(script_id, "TENANT_MISMATCH", SAFE_MESSAGES["TENANT_MISMATCH"], correlation_id, release_binding, requested_at)
                if not conn.account_upn or conn.account_upn.casefold() != ctx.administrator_upn.casefold():
                    return self._build_rejected_outcome(script_id, "ACCOUNT_MISMATCH", SAFE_MESSAGES["ACCOUNT_MISMATCH"], correlation_id, release_binding, requested_at)
                if conn.session_generation != ctx.session_generation:
                    return self._build_rejected_outcome(script_id, "AUTH_REQUIRED", SAFE_MESSAGES["AUTH_REQUIRED"], correlation_id, release_binding, requested_at)
                if conn.state == "permission_warning":
                    return self._build_rejected_outcome(script_id, "ACCESS_DENIED", SAFE_MESSAGES["ACCESS_DENIED"], correlation_id, release_binding, requested_at)

                scopes = list(manifest.get("graph_scopes", [])) if service_name == "Graph" else []
                roles = [r["any_of"][0] for r in manifest.get("required_roles", []) if r["service"] == service_name and r.get("any_of")]
                connections_abi.append(
                    {
                        "service": service_name,
                        "connection_id": str(uuid4()),
                        "owner_worker_id": str(uuid4()),
                        "company_id": company.company_id,
                        "tenant_id": company.tenant_id,
                        "admin_identity_ref": ctx.admin_identity_ref,
                        "session_generation": ctx.session_generation,
                        "verified_account_upn": ctx.administrator_upn,
                        "state": "verified",
                        "verified_at": requested_at,
                        "expires_at": conn.expires_at.isoformat(timespec="seconds").replace("+00:00", "Z") if conn.expires_at else None,
                        "graph_scopes": scopes,
                        "effective_roles": roles,
                    }
                )

            # Resolve target according to target_policy
            target_policy = manifest["target_policy"]
            if target_policy.get("requires_resolved_identity"):
                resolved_id = self._resolve_object_id_for_current_context()
                if not resolved_id:
                    return self._build_rejected_outcome(script_id, "AUTH_REQUIRED", "Resolve target identity before running follow-on operations.", correlation_id, release_binding, requested_at)
                target = {"kind": "object_id", "value": resolved_id}
            else:
                try:
                    target = ctx.target_input.contract_target()
                except ValueError:
                    if ctx.target is not None:
                        target = {"kind": "object_id", "value": ctx.target.object_id}
                    else:
                        return self._build_rejected_outcome(script_id, "INVALID_PARAMETER", SAFE_MESSAGES["INVALID_PARAMETER"], correlation_id, release_binding, requested_at)

            if target["kind"] not in target_policy.get("accepted_kinds", []):
                return self._build_rejected_outcome(script_id, "INVALID_PARAMETER", SAFE_MESSAGES["INVALID_PARAMETER"], correlation_id, release_binding, requested_at)

            ticket_ctx = None
            if ticket_id is not None and re.fullmatch(r"[1-9][0-9]{0,18}", str(ticket_id)):
                ticket_ctx = {"ticket_id": str(ticket_id)}

            request_envelope = {
                "contract_version": VERSION,
                "correlation_id": correlation_id,
                "script_id": script_id,
                "company_id": company.company_id,
                "tenant_id": company.tenant_id,
                "admin_identity_ref": ctx.admin_identity_ref,
                "session_generation": ctx.session_generation,
                "target": target,
                "ticket_context": ticket_ctx,
                "parameters": bound_params,
                "requested_execution_mode": "isolated_worker",
                "authorization": {"confirmation_ref": None},
                "release_binding": release_binding,
            }
            self._validate_schema("execution-request", request_envelope)

            if self._cancel_event.is_set():
                return self._build_cancelled_outcome(request_envelope, requested_at, started_monotonic, dispatched=False)

            script_path = (self.library_root / manifest["script_path"]).resolve()
            if not script_path.is_file() or sha256_file(script_path) != manifest["script_sha256"]:
                return self._build_rejected_outcome(script_id, "CONTRACT_VIOLATION", SAFE_MESSAGES["CONTRACT_VIOLATION"], correlation_id, release_binding, requested_at)

            started_at = utc_now()
            op_return = self._invoke_powershell_worker(
                script_path=script_path,
                request_envelope=request_envelope,
                connections_abi=connections_abi,
                verified_account_upn=ctx.administrator_upn,
                timeout_seconds=manifest.get("timeout_seconds", 90),
                cancel_event=self._cancel_event,
                on_started=on_started,
            )

            completed_at = utc_now()
            duration_ms = max(1, int((time.monotonic() - started_monotonic) * 1000))

            if op_return.get("_host_terminal") == "CANCELLED" or self._cancel_event.is_set():
                return self._build_cancelled_outcome(request_envelope, started_at, started_monotonic, dispatched=True)
            if op_return.get("_host_terminal") == "TIMEOUT":
                return self._build_timeout_outcome(request_envelope, started_at, started_monotonic)

            status = op_return.get("status", "error")
            outcome_str = op_return.get("operation_outcome", "failed")
            data = op_return.get("data")
            warnings = self._sanitize_items(op_return.get("warnings", []))
            errors = self._sanitize_items(op_return.get("errors", []), is_error=True)

            exit_code = self._compute_logical_exit_code(status, errors)
            result_envelope = {
                "contract_version": VERSION,
                "correlation_id": correlation_id,
                "script_id": script_id,
                "company_id": company.company_id,
                "tenant_id": company.tenant_id,
                "context_state": "verified",
                "origin": "worker",
                "operation_outcome": outcome_str,
                "status": status,
                "started_at": started_at,
                "completed_at": completed_at,
                "duration_ms": duration_ms,
                "data": data,
                "warnings": warnings,
                "errors": errors,
                "release_binding": release_binding,
                "admin_identity_ref": ctx.admin_identity_ref,
                "session_generation": ctx.session_generation,
                "target": target,
                "operation_exit_code": exit_code,
            }

            # Validate result envelope and payload schema
            self._validate_schema("execution-result", result_envelope)
            if data is not None:
                _, fragment = manifest["expected_output_schema"].split("#", 1)
                self._validate_schema("operation-data", data, fragment=fragment)
                self._verify_output_binding(manifest, target, data)

            # Update retained identity resolution when Get-UserIdentity succeeds or partially succeeds
            if script_id == "M365.ENTRA.USER_IDENTITY" and status in ("success", "partial") and isinstance(data, dict):
                resolved_uid = data.get("id")
                resolved_upn = data.get("user_principal_name")
                if resolved_uid and resolved_upn:
                    key = (company.company_id, company.tenant_id, ctx.admin_identity_ref, ctx.session_generation)
                    self._resolved_identities[key] = {"object_id": resolved_uid, "upn": resolved_upn}
                    try:
                        ctx.resolve_synthetic(
                            tenant_id=company.tenant_id,
                            resolved_upn=resolved_upn,
                            resolved_object_id=resolved_uid,
                        )
                    except ValueError:
                        pass

            codes = [e["code"] for e in errors] + [w["code"] for w in warnings]
            history_record = {
                "contract_version": VERSION,
                "correlation_id": correlation_id,
                "script_id": script_id,
                "company_id": company.company_id,
                "tenant_id": company.tenant_id,
                "admin_identity_ref": ctx.admin_identity_ref,
                "session_generation": ctx.session_generation,
                "operation_outcome": outcome_str,
                "workflow_id": None,
                "release_binding": release_binding,
                "status": status,
                "stage": "completion",
                "origin": "worker",
                "requested_at": requested_at,
                "started_at": started_at,
                "completed_at": completed_at,
                "duration_ms": duration_ms,
                "codes": codes[:50],
                "provenance": "synthetic",
            }
            self._validate_schema("common", history_record, fragment="/$defs/history_record")

            summary_text = self._format_summary(manifest["title"], result_envelope, company.display_name)
            sanitized_json = json.dumps(result_envelope, indent=2, ensure_ascii=False)

            preview = None
            if status in ("success", "partial"):
                token = str(uuid4())
                preview = NoteInsertionPreview(
                    token=token,
                    correlation_id=correlation_id,
                    script_id=script_id,
                    company_id=company.company_id,
                    tenant_id=company.tenant_id,
                    session_generation=ctx.session_generation,
                    formatted_text=summary_text,
                    text_sha256=hashlib.sha256(summary_text.encode("utf-8")).hexdigest(),
                )
                self._previews[token] = preview

            self._state = {"success": "succeeded", "partial": "partial", "cancelled": "cancelled", "timeout": "timeout"}.get(status, "failed")
            outcome = ExecutionOutcome(
                correlation_id=correlation_id,
                script_id=script_id,
                status=status,
                operation_outcome=outcome_str,
                result_envelope=result_envelope,
                history_record=history_record,
                summary_text=summary_text,
                sanitized_json=sanitized_json,
                insertion_preview=preview,
            )
            self._record_history(outcome)
            return outcome

        except Exception:
            return self._build_rejected_outcome(
                script_id,
                "CONTRACT_VIOLATION",
                SAFE_MESSAGES["CONTRACT_VIOLATION"],
                correlation_id,
                None,
                requested_at,
            )
        finally:
            self._active_correlation_id = None
            self._cancel_event = None
            self._lock.release()

    def _invoke_powershell_worker(
        self,
        *,
        script_path: Path,
        request_envelope: dict,
        connections_abi: list[dict],
        verified_account_upn: str,
        timeout_seconds: int,
        cancel_event: threading.Event,
        on_started=None,
    ) -> dict:
        invocation_ctx = {
            "contract_version": VERSION,
            "correlation_id": request_envelope["correlation_id"],
            "script_id": request_envelope["script_id"],
            "company_id": request_envelope["company_id"],
            "tenant_id": request_envelope["tenant_id"],
            "admin_identity_ref": request_envelope["admin_identity_ref"],
            "session_generation": request_envelope["session_generation"],
            "target": request_envelope["target"],
            "ticket_context": request_envelope["ticket_context"],
            "release_binding": request_envelope["release_binding"],
            "verified_account_upn": verified_account_upn,
            "connections": connections_abi,
        }
        self._validate_schema("common", invocation_ctx, fragment="/$defs/invocation_context")

        worker_payload = {
            "protocol_path": str(PROTOCOL_PATH),
            "script_path": str(script_path),
            "context": invocation_ctx,
            "parameters": request_envelope["parameters"],
            "already_cancelled": cancel_event.is_set(),
        }

        runner_code = (
            "$ErrorActionPreference = 'Stop'; "
            "$raw = [Console]::In.ReadLine(); "
            "$payload = ConvertFrom-Json -InputObject $raw -Depth 25; "
            ". $payload.protocol_path; "
            "Initialize-NativeReturnValidation; "
            "$params = @{}; "
            "if ($null -ne $payload.parameters) { "
            "  foreach ($p in $payload.parameters.PSObject.Properties) { $params[$p.Name] = $p.Value } "
            "}; "
            "$cts = [System.Threading.CancellationTokenSource]::new(); "
            "if ([bool]$payload.already_cancelled) { $cts.Cancel() }; "
            "$ret = & $payload.script_path -Context $payload.context -Parameters $params -CancellationToken $cts.Token; "
            "Assert-NativeOperationReturn $ret; "
            "$json = ConvertTo-Json -InputObject $ret -Depth 20 -Compress; "
            "[Console]::Out.WriteLine($json)"
        )

        creationflags = getattr(subprocess, "CREATE_NO_WINDOW", 0)
        proc = subprocess.Popen(
            [
                str(self.pwsh_path),
                "-NoLogo",
                "-NoProfile",
                "-NonInteractive",
                "-Command",
                runner_code,
            ],
            stdin=subprocess.PIPE,
            stdout=subprocess.PIPE,
            stderr=subprocess.PIPE,
            cwd=str(self.library_root),
            creationflags=creationflags,
        )
        try:
            if on_started is not None:
                on_started()
            input_line = (json.dumps(worker_payload, ensure_ascii=False, separators=(",", ":")) + "\n").encode("utf-8")
            proc.stdin.write(input_line)
            proc.stdin.flush()
            proc.stdin.close()

            deadline = time.monotonic() + timeout_seconds
            while proc.poll() is None:
                if cancel_event.is_set():
                    proc.kill()
                    proc.wait(timeout=5)
                    return {"_host_terminal": "CANCELLED"}
                if time.monotonic() >= deadline:
                    proc.kill()
                    proc.wait(timeout=5)
                    return {"_host_terminal": "TIMEOUT"}
                time.sleep(0.02)

            stdout_bytes = proc.stdout.read(MAX_OUTPUT + 1)
            stderr_bytes = proc.stderr.read(65536)
            if len(stdout_bytes) > MAX_OUTPUT:
                return {
                    "status": "error",
                    "operation_outcome": "failed",
                    "data": None,
                    "warnings": [],
                    "errors": [{"code": "OUTPUT_LIMIT", "message": SAFE_MESSAGES["OUTPUT_LIMIT"], "retryable": False}],
                }
            if proc.returncode != 0 or stderr_bytes:
                return {
                    "status": "error",
                    "operation_outcome": "failed",
                    "data": None,
                    "warnings": [],
                    "errors": [{"code": "CONTRACT_VIOLATION", "message": SAFE_MESSAGES["CONTRACT_VIOLATION"], "retryable": False}],
                }
            parsed = json.loads(stdout_bytes.decode("utf-8").strip())
            self._validate_schema("common", parsed, fragment="/$defs/operation_return")
            return parsed
        finally:
            if proc.poll() is None:
                proc.kill()

    @staticmethod
    def _verify_output_binding(manifest: dict, target: dict, data: dict) -> None:
        binding = manifest["target_policy"]["output_binding"]
        kind = target["kind"]
        field_name = binding["upn_field" if kind == "upn" else "object_id_field"]
        actual = data.get(field_name)
        expected = target["value"]
        if kind == "upn":
            if not isinstance(actual, str) or unicodedata.normalize("NFC", actual).casefold() != unicodedata.normalize("NFC", expected).casefold():
                raise ValueError("Target UPN output binding mismatch.")
        else:
            if not isinstance(actual, str) or actual.lower() != expected.lower():
                raise ValueError("Target object_id output binding mismatch.")

    @staticmethod
    def _sanitize_items(items: list, *, is_error: bool = False) -> list[dict]:
        sanitized: list[dict] = []
        for item in items[:50]:
            if not isinstance(item, dict):
                continue
            code = str(item.get("code", "CONTRACT_VIOLATION"))
            msg = str(item.get("message", SAFE_MESSAGES.get(code, SAFE_MESSAGES["CONTRACT_VIOLATION"])))
            msg = SENSITIVE_RE.sub("[REDACTED]", msg)
            entry = {"code": code, "message": msg}
            if is_error:
                entry["retryable"] = bool(item.get("retryable", False))
            sanitized.append(entry)
        return sanitized

    @staticmethod
    def _compute_logical_exit_code(status: str, errors: list[dict]) -> int:
        if status == "success":
            return 0
        if status == "partial":
            return 2
        if status in ("cancelled", "timeout"):
            return 40
        codes = {e.get("code") for e in errors}
        if "INTERNAL_ERROR" in codes:
            return 50
        if codes & {"AUTH_REQUIRED", "TENANT_MISMATCH", "ACCOUNT_MISMATCH", "ACCESS_DENIED"}:
            return 20
        if codes & {"INVALID_PARAMETER", "CONTRACT_VIOLATION"}:
            return 10
        if codes & {"TIMEOUT", "CANCELLED"}:
            return 40
        return 30

    def _build_rejected_outcome(
        self,
        script_id: str,
        code: str,
        message: str,
        correlation_id: str | None = None,
        release_binding: dict | None = None,
        requested_at: str | None = None,
    ) -> ExecutionOutcome:
        correlation_id = correlation_id or str(uuid4())
        now_str = requested_at or utc_now()
        ctx = self.context_service
        company = ctx.company
        company_id = company.company_id if company else "00000000-0000-4000-8000-000000000000"
        if release_binding is None:
            try:
                _, _, release_binding = self.manifest_for(script_id)
            except Exception:
                release_binding = {
                    "script_version": "0.3.0-synthetic.1",
                    "script_sha256": "0" * 64,
                    "manifest_sha256": "0" * 64,
                    "output_schema_sha256": "0" * 64,
                }
        errors = [{"code": code, "message": SENSITIVE_RE.sub("[REDACTED]", message), "retryable": False}]
        exit_code = self._compute_logical_exit_code("error", errors)
        result_envelope = {
            "contract_version": VERSION,
            "correlation_id": correlation_id,
            "script_id": script_id,
            "company_id": company_id,
            "tenant_id": None,
            "context_state": "unverified",
            "origin": "host",
            "operation_outcome": "not_started",
            "status": "error",
            "started_at": now_str,
            "completed_at": now_str,
            "duration_ms": 0,
            "data": None,
            "warnings": [],
            "errors": errors,
            "release_binding": release_binding,
            "admin_identity_ref": ctx.admin_identity_ref,
            "session_generation": ctx.session_generation,
            "target": {"kind": "upn", "value": ctx.target_input.upn or "unresolved@example.invalid"},
            "operation_exit_code": exit_code,
        }
        history_record = {
            "contract_version": VERSION,
            "correlation_id": correlation_id,
            "script_id": script_id,
            "company_id": company_id,
            "tenant_id": None,
            "admin_identity_ref": ctx.admin_identity_ref,
            "session_generation": ctx.session_generation,
            "operation_outcome": "not_started",
            "workflow_id": None,
            "release_binding": release_binding,
            "status": "rejected",
            "stage": "preflight",
            "origin": "host",
            "requested_at": now_str,
            "started_at": None,
            "completed_at": now_str,
            "duration_ms": 0,
            "codes": [code],
            "provenance": "synthetic",
        }
        self._validate_schema("common", history_record, fragment="/$defs/history_record")
        summary_text = self._format_summary(script_id, result_envelope, company.display_name if company else "Unselected")
        sanitized_json = json.dumps(result_envelope, indent=2, ensure_ascii=False)
        self._state = "failed"
        outcome = ExecutionOutcome(
            correlation_id=correlation_id,
            script_id=script_id,
            status="error",
            operation_outcome="not_started",
            result_envelope=result_envelope,
            history_record=history_record,
            summary_text=summary_text,
            sanitized_json=sanitized_json,
            insertion_preview=None,
        )
        self._record_history(outcome)
        return outcome

    def _build_cancelled_outcome(
        self,
        request_envelope: dict,
        started_at: str,
        started_monotonic: float,
        *,
        dispatched: bool,
    ) -> ExecutionOutcome:
        completed_at = utc_now()
        duration_ms = max(0, int((time.monotonic() - started_monotonic) * 1000))
        outcome_str = "unknown" if dispatched else "not_started"
        errors = [{"code": "CANCELLED", "message": SAFE_MESSAGES["CANCELLED"], "retryable": False}]
        result_envelope = {
            "contract_version": VERSION,
            "correlation_id": request_envelope["correlation_id"],
            "script_id": request_envelope["script_id"],
            "company_id": request_envelope["company_id"],
            "tenant_id": None,
            "context_state": "unverified",
            "origin": "host",
            "operation_outcome": outcome_str,
            "status": "cancelled",
            "started_at": started_at,
            "completed_at": completed_at,
            "duration_ms": duration_ms,
            "data": None,
            "warnings": [],
            "errors": errors,
            "release_binding": request_envelope["release_binding"],
            "admin_identity_ref": request_envelope["admin_identity_ref"],
            "session_generation": request_envelope["session_generation"],
            "target": request_envelope["target"],
            "operation_exit_code": 40,
        }
        self._validate_schema("execution-result", result_envelope)
        history_record = {
            "contract_version": VERSION,
            "correlation_id": request_envelope["correlation_id"],
            "script_id": request_envelope["script_id"],
            "company_id": request_envelope["company_id"],
            "tenant_id": None,
            "admin_identity_ref": request_envelope["admin_identity_ref"],
            "session_generation": request_envelope["session_generation"],
            "operation_outcome": outcome_str,
            "workflow_id": None,
            "release_binding": request_envelope["release_binding"],
            "status": "cancelled",
            "stage": "capture" if dispatched else "preflight",
            "origin": "host",
            "requested_at": started_at,
            "started_at": started_at,
            "completed_at": completed_at,
            "duration_ms": duration_ms,
            "codes": ["CANCELLED"],
            "provenance": "synthetic",
        }
        self._validate_schema("common", history_record, fragment="/$defs/history_record")
        company = self.context_service.company
        summary_text = self._format_summary(request_envelope["script_id"], result_envelope, company.display_name if company else "Unknown")
        sanitized_json = json.dumps(result_envelope, indent=2, ensure_ascii=False)
        self._state = "cancelled"
        outcome = ExecutionOutcome(
            correlation_id=request_envelope["correlation_id"],
            script_id=request_envelope["script_id"],
            status="cancelled",
            operation_outcome=outcome_str,
            result_envelope=result_envelope,
            history_record=history_record,
            summary_text=summary_text,
            sanitized_json=sanitized_json,
            insertion_preview=None,
        )
        self._record_history(outcome)
        return outcome

    def _build_timeout_outcome(
        self,
        request_envelope: dict,
        started_at: str,
        started_monotonic: float,
    ) -> ExecutionOutcome:
        completed_at = utc_now()
        duration_ms = max(1, int((time.monotonic() - started_monotonic) * 1000))
        errors = [{"code": "TIMEOUT", "message": SAFE_MESSAGES["TIMEOUT"], "retryable": False}]
        result_envelope = {
            "contract_version": VERSION,
            "correlation_id": request_envelope["correlation_id"],
            "script_id": request_envelope["script_id"],
            "company_id": request_envelope["company_id"],
            "tenant_id": None,
            "context_state": "unverified",
            "origin": "host",
            "operation_outcome": "unknown",
            "status": "timeout",
            "started_at": started_at,
            "completed_at": completed_at,
            "duration_ms": duration_ms,
            "data": None,
            "warnings": [],
            "errors": errors,
            "release_binding": request_envelope["release_binding"],
            "admin_identity_ref": request_envelope["admin_identity_ref"],
            "session_generation": request_envelope["session_generation"],
            "target": request_envelope["target"],
            "operation_exit_code": 40,
        }
        self._validate_schema("execution-result", result_envelope)
        history_record = {
            "contract_version": VERSION,
            "correlation_id": request_envelope["correlation_id"],
            "script_id": request_envelope["script_id"],
            "company_id": request_envelope["company_id"],
            "tenant_id": None,
            "admin_identity_ref": request_envelope["admin_identity_ref"],
            "session_generation": request_envelope["session_generation"],
            "operation_outcome": "unknown",
            "workflow_id": None,
            "release_binding": request_envelope["release_binding"],
            "status": "timeout",
            "stage": "capture",
            "origin": "host",
            "requested_at": started_at,
            "started_at": started_at,
            "completed_at": completed_at,
            "duration_ms": duration_ms,
            "codes": ["TIMEOUT"],
            "provenance": "synthetic",
        }
        self._validate_schema("common", history_record, fragment="/$defs/history_record")
        company = self.context_service.company
        summary_text = self._format_summary(request_envelope["script_id"], result_envelope, company.display_name if company else "Unknown")
        sanitized_json = json.dumps(result_envelope, indent=2, ensure_ascii=False)
        self._state = "timeout"
        outcome = ExecutionOutcome(
            correlation_id=request_envelope["correlation_id"],
            script_id=request_envelope["script_id"],
            status="timeout",
            operation_outcome="unknown",
            result_envelope=result_envelope,
            history_record=history_record,
            summary_text=summary_text,
            sanitized_json=sanitized_json,
            insertion_preview=None,
        )
        self._record_history(outcome)
        return outcome

    def _record_history(self, outcome: ExecutionOutcome) -> None:
        self._history.insert(0, outcome.history_record)
        if len(self._history) > self.max_history:
            removed = self._history.pop()
            self._results_by_correlation.pop(removed["correlation_id"], None)
        self._results_by_correlation[outcome.correlation_id] = outcome

    @staticmethod
    def _format_summary(title: str, result: dict, company_name: str) -> str:
        lines = [
            f"=== M365 Diagnostic Snapshot: {title} ({result['script_id']}) ===",
            f"Company: {company_name} | Tenant: {result.get('tenant_id') or 'unverified'}",
            f"Target: {result['target']['kind']}={result['target']['value']}",
            f"Status: {result['status'].upper()} ({result['operation_outcome']}) | Duration: {result['duration_ms']} ms",
            f"Correlation ID: {result['correlation_id']} | Completed: {result['completed_at']}",
        ]
        data = result.get("data")
        if isinstance(data, dict):
            lines.append("Results:")
            for k, v in data.items():
                if isinstance(v, list):
                    lines.append(f"  - {k}: {len(v)} item(s)")
                    for idx, item in enumerate(v[:5], start=1):
                        if isinstance(item, dict):
                            compact = ", ".join(f"{ik}={iv}" for ik, iv in item.items() if not isinstance(iv, list))
                            lines.append(f"      [{idx}] {compact}")
                else:
                    lines.append(f"  - {k}: {v}")
        for w in result.get("warnings", []):
            lines.append(f"Warning [{w['code']}]: {w['message']}")
        for e in result.get("errors", []):
            lines.append(f"Error [{e['code']}]: {e['message']}")
        return "\n".join(lines)

    def insert_into_active_ticket(self, token: str, editor) -> str:
        """Validate a single-use preview token and insert the formatted summary into the active ticket editor."""
        if editor is None or not editor.isEnabled():
            raise ValueError("No active ticket editor is available for note insertion.")
        preview = self._previews.get(token)
        if preview is None:
            raise ValueError("Invalid or expired note insertion preview token.")
        if preview.consumed:
            raise ValueError("This result preview has already been inserted into the ticket.")

        ctx = self.context_service
        company = ctx.company
        if (
            company is None
            or company.company_id != preview.company_id
            or company.tenant_id != preview.tenant_id
            or ctx.session_generation != preview.session_generation
        ):
            raise ValueError("Company or session context changed since this result was captured; insertion blocked.")

        actual_hash = hashlib.sha256(preview.formatted_text.encode("utf-8")).hexdigest()
        if actual_hash != preview.text_sha256:
            raise ValueError("Result preview integrity check failed.")

        # Mark token consumed (single-use)
        consumed_preview = NoteInsertionPreview(
            token=preview.token,
            correlation_id=preview.correlation_id,
            script_id=preview.script_id,
            company_id=preview.company_id,
            tenant_id=preview.tenant_id,
            session_generation=preview.session_generation,
            formatted_text=preview.formatted_text,
            text_sha256=preview.text_sha256,
            consumed=True,
        )
        self._previews[token] = consumed_preview
        outcome = self._results_by_correlation.get(preview.correlation_id)
        if outcome is not None:
            outcome.insertion_preview = consumed_preview

        cursor = editor.textCursor()
        cursor.movePosition(cursor.MoveOperation.End)
        if editor.toPlainText().strip():
            cursor.insertText("\n\n" + preview.formatted_text + "\n")
        else:
            cursor.insertText(preview.formatted_text + "\n")
        editor.setTextCursor(cursor)
        return preview.formatted_text

