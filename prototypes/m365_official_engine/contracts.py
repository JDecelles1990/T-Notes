"""Independent provisional protocol and semantic checks; no application imports."""
from __future__ import annotations
from datetime import datetime, timezone
import json
import math
import re
import unicodedata

VERSION = "0.3.0"
MAX_INPUT, MAX_OUTPUT = 65536, 1048576
COMMON = f"https://tnotes.invalid/m365/{VERSION}/schemas/common.schema.json"
MESSAGES = {
    "INVALID_PARAMETER": "Correct the request target or approved parameter values.",
    "CONTRACT_VIOLATION": "Review the pinned contract, catalog and worker protocol evidence.",
    "MODULE_MISSING": "Configure the explicitly trusted PowerShell executable and dependencies.",
    "AUTH_REQUIRED": "Only the pinned synthetic context is supported by this offline prototype.",
    "TENANT_MISMATCH": "The request does not match the pinned synthetic tenant.",
    "ACCOUNT_MISMATCH": "The request does not match the pinned synthetic account.",
    "ACCESS_DENIED": "This operation is unavailable under the configured offline policy.",
    "TARGET_NOT_FOUND": "No matching synthetic fixture target exists.",
    "TIMEOUT": "The deadline expired; verify the outcome before an explicit new attempt.",
    "CANCELLED": "Cancellation was requested; no rollback or automatic retry is implied.",
    "OUTPUT_LIMIT": "The bounded transport limit was reached; narrow the operation.",
    "INTERNAL_ERROR": "The owned worker failed; investigate the safe correlation diagnostics.",
    "PROPERTY_UNAVAILABLE": "A synthetic property is unavailable in this partial fixture.",
}


class Rejected(Exception):
    def __init__(self, code):
        self.code = code
        super().__init__(MESSAGES.get(code, MESSAGES["CONTRACT_VIOLATION"]))


def fail(code="CONTRACT_VIOLATION"):
    raise Rejected(code)


def utc():
    return datetime.now(timezone.utc).isoformat(timespec="microseconds").replace("+00:00", "Z")


def encode(value):
    try:
        return json.dumps(value, ensure_ascii=False, allow_nan=False, separators=(",", ":")).encode("utf-8")
    except (ValueError, TypeError, UnicodeError, RecursionError):
        fail("INVALID_PARAMETER")


def strict_json(raw, limit=MAX_OUTPUT, wire=False):
    if len(raw) > limit:
        fail("OUTPUT_LIMIT")
    if raw.startswith(b"\xef\xbb\xbf"):
        fail()
    if wire:
        body = raw[:-1] if raw.endswith(b"\n") else raw
        if b"\n" in body or b"\r" in body or not body.startswith(b"{") or not body.endswith(b"}"):
            fail()
    def pairs(values):
        result = {}
        for key, value in values:
            if key in result:
                fail()
            result[key] = value
        return result
    def invalid(_):
        fail()
    try:
        value = json.loads(raw.decode("utf-8", "strict"), object_pairs_hook=pairs, parse_constant=invalid)
        def visit(item, depth=0):
            if depth > 20 or isinstance(item, float) and not math.isfinite(item):
                fail()
            children = item.values() if isinstance(item, dict) else item if isinstance(item, list) else ()
            for child in children:
                visit(child, depth + 1)
        visit(value)
        if not isinstance(value, dict):
            fail()
        return value
    except (UnicodeError, ValueError, RecursionError):
        fail()


def timestamp(value):
    if not isinstance(value, str) or not re.fullmatch(r"\d{4}-\d{2}-\d{2}T\d{2}:\d{2}:\d{2}(?:\.\d{1,6})?Z", value):
        fail()
    try:
        return datetime.fromisoformat(value)
    except ValueError:
        fail()


def calendar(value):
    if isinstance(value, dict):
        for key, item in value.items():
            if key in {"started_at", "completed_at", "verified_at", "expires_at", "created_at", "lookback_start"} and item is not None:
                timestamp(item)
            calendar(item)
    elif isinstance(value, list):
        for item in value:
            calendar(item)


def normalize(request):
    request = strict_json(encode(request), MAX_INPUT)
    for field in ("company_id", "tenant_id", "correlation_id", "admin_identity_ref"):
        if isinstance(request.get(field), str):
            request[field] = request[field].strip().lower()
    target = request.get("target")
    if isinstance(target, dict) and isinstance(target.get("value"), str):
        value = unicodedata.normalize("NFC", target["value"].strip())
        if any(ord(c) < 32 or ord(c) == 127 for c in value):
            fail("INVALID_PARAMETER")
        target["value"] = value.lower() if target.get("kind") == "object_id" else value
    return request


RESERVED = {x.casefold() for x in "Context Parameters CancellationToken Verbose Debug ErrorAction WarningAction InformationAction ProgressAction ErrorVariable WarningVariable InformationVariable OutVariable OutBuffer PipelineVariable WhatIf Confirm".split()}


def parameter_valid(value, spec):
    kind = spec["type"]
    if kind == "integer":
        valid = type(value) is int and -(2**63) <= value < 2**63
    elif kind == "number":
        valid = type(value) in (int, float) and abs(value) <= 1.7976931348623157e308
    elif kind == "boolean":
        valid = type(value) is bool
    elif kind == "string":
        valid = isinstance(value, str) and spec.get("min_length", 0) <= len(value) <= spec.get("max_length", 4096)
    elif kind == "string_array":
        valid = (isinstance(value, list) and spec.get("min_items", 0) <= len(value) <= spec.get("max_items", 1000)
                 and all(isinstance(x, str) and spec.get("item_min_length", 0) <= len(x) <= spec.get("item_max_length", 4096) for x in value))
    else:
        return False
    if not valid:
        return False
    if kind in ("integer", "number") and (not math.isfinite(value) or not spec.get("minimum", -math.inf) <= value <= spec.get("maximum", math.inf)):
        return False
    return "allowed_values" not in spec or value in spec["allowed_values"]


def bind_parameters(descriptors, supplied):
    names = [p["name"].casefold() for p in descriptors]
    if len(names) != len(set(names)) or set(names) & RESERVED:
        fail()
    specs = {p["name"]: p for p in descriptors}
    if set(supplied) - set(specs):
        fail("INVALID_PARAMETER")
    effective = dict(supplied)
    for name, spec in specs.items():
        for low, high in (("minimum", "maximum"), ("min_length", "max_length"),
                          ("min_items", "max_items"), ("item_min_length", "item_max_length")):
            if low in spec and high in spec and spec[low] > spec[high]:
                fail()
        allowed = spec.get("allowed_values")
        if allowed is not None:
            if len({encode(x) for x in allowed}) != len(allowed):
                fail()
            scalar = {k: v for k, v in spec.items() if k != "allowed_values"}
            if not all(parameter_valid(x, scalar) for x in allowed):
                fail()
        if "default" in spec and not parameter_valid(spec["default"], spec):
            fail()
        if name not in effective and "default" in spec:
            effective[name] = spec["default"]
        if name not in effective:
            if spec["required"]:
                fail("INVALID_PARAMETER")
        elif not parameter_valid(effective[name], spec):
            fail("INVALID_PARAMETER")
    return effective


def logical_exit(result):
    status = result["status"]
    if status == "success":
        return 0
    if status == "partial":
        return 2
    if status in ("cancelled", "timeout"):
        return 40
    codes = {x["code"] for x in result["errors"]}
    for number, group in ((50, {"INTERNAL_ERROR"}), (20, {"AUTH_REQUIRED", "TENANT_MISMATCH", "ACCOUNT_MISMATCH", "ACCESS_DENIED"}),
                          (10, {"INVALID_PARAMETER", "CONTRACT_VIOLATION"}), (40, {"TIMEOUT", "CANCELLED"})):
        if codes & group:
            return number
    return 30


def check_binding(request, response, manifest):
    for key in ("contract_version", "script_id", "correlation_id", "company_id", "admin_identity_ref", "session_generation", "target", "release_binding"):
        if response[key] != request[key]:
            fail()
    if response["context_state"] != "verified" or response["tenant_id"] != request["tenant_id"]:
        fail()
    if timestamp(response["completed_at"]) < timestamp(response["started_at"]):
        fail()
    if response["operation_exit_code"] != logical_exit(response):
        fail()
    if response["data"] is not None:
        binding = manifest["target_policy"]["output_binding"]
        kind = request["target"]["kind"]
        field = binding["upn_field" if kind == "upn" else "object_id_field"]
        actual, expected = response["data"].get(field), request["target"]["value"]
        if kind == "upn":
            if not isinstance(actual, str) or unicodedata.normalize("NFC", actual).casefold() != expected.casefold():
                fail()
        elif actual != expected:
            fail()
        if response["status"] == "success" and "account_enabled" in response["data"] and response["data"]["account_enabled"] is None:
            fail()


SENSITIVE = re.compile(r"(?i)(SYNTHETIC_SECRET_SENTINEL|bearer\s+\S+|(?:access_token|refresh_token|password)\s*[:=]\s*\S+|sk-proj-[a-z0-9_-]+)")


def reject_sensitive_request(value):
    if isinstance(value, dict):
        for key, item in value.items():
            if key.casefold() in {"password", "access_token", "refresh_token", "credential", "credentials"}:
                fail("INVALID_PARAMETER")
            reject_sensitive_request(item)
    elif isinstance(value, list):
        for item in value:
            reject_sensitive_request(item)
    elif isinstance(value, str) and SENSITIVE.search(value):
        fail("INVALID_PARAMETER")


def sanitize(value):
    if isinstance(value, dict):
        result = {k: sanitize(v) for k, v in value.items()}
        for key in ("warnings", "errors"):
            if key in result:
                for item in result[key]:
                    item["message"] = MESSAGES.get(item["code"], "Review the safe operation status and correlation.")
        return result
    if isinstance(value, list):
        return [sanitize(x) for x in value]
    if isinstance(value, str):
        return SENSITIVE.sub("[REDACTED]", value)
    return value
