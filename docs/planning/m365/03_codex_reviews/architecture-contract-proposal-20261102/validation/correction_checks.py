"""Offline contract predicates and adversarial examples; never a runtime backend.

All approval/connection records below are synthetic declarations. These checks
prove agreement between proposed documents and examples, not real authorization.
"""
from __future__ import annotations

import copy
from datetime import datetime
import json
import math
import re
import unicodedata


RESERVED = {name.casefold() for name in (
    "Context", "Parameters", "CancellationToken", "Verbose", "Debug",
    "ErrorAction", "WarningAction", "InformationAction", "ProgressAction",
    "ErrorVariable", "WarningVariable", "InformationVariable", "OutVariable",
    "OutBuffer", "PipelineVariable", "WhatIf", "Confirm",
)}
TIME_KEYS = {"requested_at", "started_at", "completed_at", "created_at",
             "lookback_start", "verified_at", "expires_at", "checked_at"}


def instant(value):
    if not isinstance(value, str) or not re.fullmatch(
        r"\d{4}-\d{2}-\d{2}T\d{2}:\d{2}:\d{2}(?:\.\d{1,6})?Z", value
    ):
        raise ValueError("UTC Z timestamp required")
    return datetime.fromisoformat(value)


def calendar_valid(value):
    if isinstance(value, dict):
        for key, item in value.items():
            if key in TIME_KEYS and item is not None:
                try:
                    instant(item)
                except ValueError:
                    return False
            if not calendar_valid(item):
                return False
    elif isinstance(value, list):
        return all(calendar_valid(item) for item in value)
    return True


def parameter_value(value, spec):
    kind = spec.get("type")
    types = {
        "string": isinstance(value, str) and len(value) <= 4096,
        "integer": type(value) is int and -(2**63) <= value < 2**63,
        "number": type(value) in (int, float) and abs(value) <= 1.7976931348623157e308,
        "boolean": type(value) is bool,
        "string_array": isinstance(value, list) and len(value) <= 1000
            and all(isinstance(x, str) and len(x) <= 4096 for x in value),
    }
    if not types.get(kind, False):
        return False
    if kind in ("integer", "number"):
        if not math.isfinite(value):
            return False
        if value < spec.get("minimum", -math.inf) or value > spec.get("maximum", math.inf):
            return False
    if kind == "string" and not spec.get("min_length", 0) <= len(value) <= spec.get("max_length", 4096):
        return False
    if kind == "string_array":
        if not spec.get("min_items", 0) <= len(value) <= spec.get("max_items", 1000):
            return False
        if any(not spec.get("item_min_length", 0) <= len(x) <= spec.get("item_max_length", 4096) for x in value):
            return False
    return "allowed_values" not in spec or value in spec["allowed_values"]


def descriptors_valid(parameters):
    names = [p["name"].casefold() for p in parameters]
    if len(names) != len(set(names)) or set(names) & RESERVED:
        return False
    constraints = {"minimum", "maximum", "min_length", "max_length", "min_items",
                   "max_items", "item_min_length", "item_max_length"}
    applicable = {"string": {"min_length", "max_length"}, "integer": {"minimum", "maximum"},
                  "number": {"minimum", "maximum"}, "boolean": set(),
                  "string_array": {"min_items", "max_items", "item_min_length", "item_max_length"}}
    for spec in parameters:
        kind = spec["type"]
        if kind not in applicable or (set(spec) & constraints) - applicable[kind]:
            return False
        for low, high, floor, cap in (("minimum", "maximum", -math.inf, math.inf),
                                     ("min_length", "max_length", 0, 4096),
                                     ("min_items", "max_items", 0, 1000),
                                     ("item_min_length", "item_max_length", 0, 4096)):
            if spec.get(low, floor) > spec.get(high, cap):
                return False
        if kind == "integer" and any(type(spec[k]) is not int for k in ("minimum", "maximum") if k in spec):
            return False
        allowed = spec.get("allowed_values", [])
        if "allowed_values" in spec:
            if kind == "string_array" or not allowed:
                return False
            encoded = [json.dumps(v, sort_keys=True) for v in allowed]
            if len(set(encoded)) != len(encoded):
                return False
            no_enum = {k: v for k, v in spec.items() if k != "allowed_values"}
            if not all(parameter_value(v, no_enum) for v in allowed):
                return False
        if "default" in spec and not parameter_value(spec["default"], spec):
            return False
    return True


def bind_parameters(manifest, supplied):
    if not descriptors_valid(manifest["parameters"]):
        return None
    specs = {p["name"]: p for p in manifest["parameters"]}
    if set(supplied) - set(specs):
        return None
    effective = copy.deepcopy(supplied)
    for name, spec in specs.items():
        if name not in effective and "default" in spec:
            effective[name] = copy.deepcopy(spec["default"])
        if name not in effective:
            if spec["required"]:
                return None
        elif not parameter_value(effective[name], spec):
            return None
    return effective


def payload_definition(manifest, schemas):
    path, _, fragment = manifest["expected_output_schema"].partition("#")
    name = path.removeprefix("schemas/")
    if name not in schemas or not fragment.startswith("/$defs/"):
        raise ValueError("Unknown local payload schema")
    node = schemas[name]
    for part in fragment.strip("/").split("/"):
        node = node[part]
    while "$ref" in node:
        target, _, pointer = node["$ref"].partition("#")
        node = next(s for s in schemas.values() if s["$id"] == target)
        for part in pointer.strip("/").split("/"):
            node = node[part]
    return node


def manifest_valid(manifest, schemas):
    if not descriptors_valid(manifest["parameters"]):
        return False
    services = manifest["connection_requirements"]
    if manifest["graph_scopes"] and "Graph" not in services:
        return False
    if any(p["service"] not in services for p in manifest["required_roles"]):
        return False
    if manifest["risk"] != "read_only" and not manifest["approval_requirements"]["confirmation_required"]:
        return False
    try:
        payload = payload_definition(manifest, schemas)
        binding = manifest["target_policy"]["output_binding"]
        kinds = manifest["target_policy"]["accepted_kinds"]
        for kind, key, typ in (("upn", "upn_field", "upn"), ("object_id", "object_id_field", "guid")):
            field = binding[key]
            if (kind in kinds or (key == "object_id_field" and manifest["target_policy"]["requires_resolved_identity"])) and field is None:
                return False
            if field is not None:
                prop = payload["properties"][field]
                if field not in payload["required"] or not prop.get("$ref", "").endswith("/$defs/" + typ):
                    return False
    except (KeyError, ValueError, StopIteration):
        return False
    return True


def upn_equal(a, b):
    return unicodedata.normalize("NFC", a.strip()).casefold() == unicodedata.normalize("NFC", b.strip()).casefold()


def connection_valid(lease, request, expected_account, owner, now):
    if lease["state"] != "verified" or lease["owner_worker_id"] != owner:
        return False
    for key in ("company_id", "tenant_id", "admin_identity_ref", "session_generation"):
        if lease[key] != request[key]:
            return False
    if not upn_equal(lease["verified_account_upn"], expected_account):
        return False
    try:
        # Synthetic dispatch uses a fresh observation at the supplied instant.
        if instant(lease["verified_at"]) != instant(now):
            return False
        if lease["expires_at"] is not None and instant(lease["expires_at"]) <= instant(now):
            return False
    except (ValueError, TypeError):
        return False
    return True


def trust_valid(trust, binding, registry):
    return (trust["trusted"] and not trust["reason_codes"]
            and bool(trust["approval_ref"]) and registry["approved"]
            and trust["approval_ref"] == registry["approval_ref"]
            and trust["inventory_sha256"] == registry["inventory_sha256"]
            and trust["release_binding"] == binding == registry["release_binding"]
            and registry["dependencies_match"] and registry["bytes_pinned"]
            and registry["path_safe"])


def make_trusted(manifest, request, mock, schemas):
    state = copy.deepcopy(mock)
    leases = []
    for service in manifest["connection_requirements"]:
        lease = copy.deepcopy(state["context"]["connections"][0])
        lease.update(service=service, graph_scopes=manifest["graph_scopes"],
                     effective_roles=[g["any_of"][0] for g in manifest["required_roles"] if g["service"] == service])
        leases.append(lease)
    trust = copy.deepcopy(state["trust"])
    trust["release_binding"] = request["release_binding"]
    return {**copy.deepcopy(request), "release_approved": True,
            "approved_hash": manifest["script_sha256"], "schemas": schemas,
            "runtime": {"edition": "Core", "version": "7.6.9"},
            "modules": {p["name"]: p["minimum_version"] for p in manifest["required_modules"]},
            "account": state["context"]["verified_account_upn"],
            "owner": leases[0]["owner_worker_id"], "now": leases[0]["verified_at"],
            "connections": leases, "trust": trust,
            "registry": {"approved": True, "approval_ref": trust["approval_ref"],
                         "inventory_sha256": trust["inventory_sha256"],
                         "release_binding": request["release_binding"],
                         "dependencies_match": True, "bytes_pinned": True, "path_safe": True},
            "resolution": {"company_id": request["company_id"], "tenant_id": request["tenant_id"],
                           "admin_identity_ref": request["admin_identity_ref"],
                           "session_generation": request["session_generation"],
                           "object_id": state["return"]["data"]["id"],
                           "upn": state["return"]["data"]["user_principal_name"]}}


def eligibility(manifest, request, trusted):
    reasons = []
    def reject(code):
        if code not in reasons:
            reasons.append(code)
    if not manifest_valid(manifest, trusted["schemas"]):
        reject("INVALID_MANIFEST")
    def version(value):
        return tuple(int(part) for part in value.split("."))
    runtime = trusted["runtime"]
    if (runtime["edition"] != manifest["supported_powershell"]["edition"]
            or version(runtime["version"]) < version(manifest["supported_powershell"]["minimum_version"])):
        reject("UNSUPPORTED_RUNTIME")
    for module in manifest["required_modules"]:
        installed = trusted["modules"].get(module["name"])
        if installed is None or version(installed) < version(module["minimum_version"]):
            reject("MODULE_MISSING")
    binding = request["release_binding"]
    if (not trusted["release_approved"] or manifest["script_sha256"] != trusted["approved_hash"]
            or manifest["script_version"] != binding["script_version"]
            or manifest["script_sha256"] != binding["script_sha256"]
            or not trust_valid(trusted["trust"], binding, trusted["registry"])):
        reject("UNTRUSTED_EXECUTABLE")
    for key, reason in (("company_id", "STALE_CONTEXT"), ("tenant_id", "TENANT_MISMATCH"),
                        ("admin_identity_ref", "ACCOUNT_MISMATCH"), ("session_generation", "STALE_CONTEXT"),
                        ("target", "STALE_CONTEXT"), ("release_binding", "UNTRUSTED_EXECUTABLE")):
        if request[key] != trusted[key]:
            reject(reason)
    if request["script_id"] != manifest["script_id"] or request["contract_version"] != manifest["contract_version"]:
        reject("INVALID_MANIFEST")
    if request["requested_execution_mode"] != manifest["execution_mode"]:
        reject("INVALID_MANIFEST")
    if not re.fullmatch(r"(?:[A-Za-z0-9_-]+/)*[A-Za-z0-9_-]+\.ps1", manifest["script_path"]):
        reject("UNTRUSTED_EXECUTABLE")
    if bind_parameters(manifest, request["parameters"]) != request["parameters"]:
        reject("INVALID_PARAMETER")
    policy = manifest["target_policy"]
    if request["target"]["kind"] not in policy["accepted_kinds"]:
        reject("TARGET_KIND_UNSUPPORTED")
    if policy["requires_resolved_identity"]:
        resolution = trusted.get("resolution")
        if not resolution or request["target"]["kind"] != "object_id" or request["target"]["value"] != resolution["object_id"]:
            reject("TARGET_UNRESOLVED")
        elif any(resolution[k] != request[k] for k in ("company_id", "tenant_id", "admin_identity_ref", "session_generation")):
            reject("TARGET_UNRESOLVED")
    for service in manifest["connection_requirements"]:
        leases = [x for x in trusted["connections"] if x["service"] == service]
        if len(leases) != 1 or not connection_valid(leases[0], request, trusted["account"], trusted["owner"], trusted["now"]):
            reject("CONNECTION_UNVERIFIED")
            continue
        lease = leases[0]
        if service == "Graph" and not set(manifest["graph_scopes"]) <= set(lease["graph_scopes"]):
            reject("SCOPE_MISSING")
        for group in manifest["required_roles"]:
            if group["service"] == service and not set(group["any_of"]) & set(lease["effective_roles"]):
                reject("ROLE_UNVERIFIED")
    if manifest["risk"] == "high_impact":
        reject("HIGH_IMPACT_DISABLED")
    if manifest["risk"] == "write":
        confirmation = request["authorization"]["confirmation_ref"]
        if (not confirmation or confirmation != trusted.get("confirmation_ref")
                or trusted.get("confirmation_expired", True) or trusted.get("confirmation_used", True)
                or trusted.get("confirmed_parameters") != request["parameters"]):
            reject("CONFIRMATION_REQUIRED")
    return {"eligible": not reasons, "reasons": [{"code": c, "message": "Synthetic gate: " + c} for c in reasons]}


def preflight_sample(manifest, request, trusted):
    return eligibility(manifest, request, trusted)["eligible"]


def history_valid(record):
    if not calendar_valid(record):
        return False
    requested = instant(record["requested_at"])
    start = instant(record["started_at"]) if record["started_at"] else None
    end = instant(record["completed_at"]) if record["completed_at"] else None
    if start and start < requested or end and end < (start or requested):
        return False
    status = record["status"]
    if status in ("queued", "running"):
        return (end is None and record["duration_ms"] is None
                and (start is not None) == (status == "running")
                and record["origin"] == "host"
                and record["operation_outcome"] == ("not_started" if status == "queued" else "unknown"))
    if end is None or type(record["duration_ms"]) is not int or record["duration_ms"] < 0:
        return False
    if status == "rejected":
        return start is None and record["operation_outcome"] == "not_started" and record["origin"] == "host" and bool(record["codes"])
    if status in ("success", "partial"):
        return start is not None and record["origin"] == "worker" and record["tenant_id"] is not None and record["operation_outcome"] == ("succeeded" if status == "success" else "partially_succeeded")
    if status in ("cancelled", "timeout"):
        return status.upper() in record["codes"] and record["operation_outcome"] in ("not_started", "unknown")
    return status == "error" and bool(record["codes"]) and record["operation_outcome"] in ("not_started", "failed", "unknown")


def notes_ack(editor):
    return (editor["receipt"] == "saved" and editor["revision"] == editor["persisted_revision"]
            and editor["pending_images"] == 0)


def abi_mapping_valid(mock):
    request, context, returned, envelope = (mock[k] for k in ("request", "context", "return", "envelope"))
    context_fields = {"contract_version", "correlation_id", "script_id", "company_id", "tenant_id",
                      "admin_identity_ref", "session_generation", "target", "ticket_context", "release_binding"}
    if any(context[k] != request[k] for k in context_fields) or mock["parameters"] != request["parameters"]:
        return False
    if any(envelope[k] != returned[k] for k in ("status", "operation_outcome", "data", "warnings", "errors")):
        return False
    if mock["persistent_process_exit"] is not None or mock["shutdown_process_exit"] != 0:
        return False
    for lease in context["connections"]:
        if not connection_valid(lease, request, context["verified_account_upn"],
                                context["connections"][0]["owner_worker_id"], lease["verified_at"]):
            return False
    return True


def add_schema_cases(cases, schemas, mock):
    common = schemas["common.schema.json"]["$id"]
    def add(name, definition, value, valid=True):
        cases.append({"name": "correction." + name, "reference": common + "#/$defs/" + definition,
                      "instance": json.dumps(value), "expected": valid})
    for key, definition in (("context", "invocation_context"), ("return", "operation_return"),
                            ("cancel_control", "cancel_control"),
                            ("trust", "trust_state"), ("history", "history_record"),
                            ("eligible", "eligibility"), ("ineligible", "eligibility"),
                            ("dynamic_manifest", "manifest")):
        add(key, definition, mock[key])
    for field in ("context", "parameters", "raw_exception"):
        add("extra-return-" + field, "operation_return", {**mock["return"], field: {}}, False)
    for status, outcome, code in (("partial", "partially_succeeded", "OUTPUT_LIMIT"),
                                  ("error", "failed", "ACCESS_DENIED"),
                                  ("cancelled", "unknown", "CANCELLED"),
                                  ("timeout", "unknown", "TIMEOUT")):
        value = copy.deepcopy(mock["return"])
        value.update(status=status, operation_outcome=outcome)
        if status == "partial":
            value["warnings"] = [{"code": code, "message": "Synthetic partial"}]
        else:
            value.update(data=None, errors=[{"code": code, "message": "Synthetic failure", "retryable": False}])
        add("return-" + status, "operation_return", value)
    add("partial-without-warning", "operation_return", {**mock["return"], "status": "partial", "operation_outcome": "partially_succeeded"}, False)
    add("success-with-errors", "operation_return", {**mock["return"], "errors": [{"code": "INTERNAL_ERROR", "message": "Synthetic", "retryable": False}]}, False)
    add("trusted-without-approval", "trust_state", {**mock["trust"], "approval_ref": None}, False)
    add("eligible-with-reasons", "eligibility", {**mock["ineligible"], "eligible": True}, False)
    add("ineligible-without-reasons", "eligibility", {"eligible": False, "reasons": []}, False)
    add("history-missing-completion", "history_record", {**mock["history"], "completed_at": None}, False)
    for bad in ("2026-11-02T18:00:00+00:00", "2026-11-02T18:00:00", "2026-02-30T18:00:00Z"):
        add("history-date-" + bad, "history_record", {**mock["history"], "requested_at": bad}, False)
    base = {"name": "Example", "type": "string", "required": False, "description": "Synthetic"}
    for kind, valid_extra, bad_extra in (
        ("string", {"min_length": 1, "max_length": 5, "default": "abc"}, {"minimum": 1}),
        ("integer", {"minimum": 1, "maximum": 3, "default": 2}, {"default": True}),
        ("number", {"minimum": 1, "maximum": 3, "default": 1.5}, {"max_length": 3}),
        ("boolean", {"default": False}, {"minimum": 0}),
        ("string_array", {"min_items": 1, "max_items": 2, "item_max_length": 5, "default": ["abc"]}, {"default": [1]}),
    ):
        add("descriptor-" + kind, "parameter", {**base, "type": kind, **valid_extra})
        add("bad-descriptor-" + kind, "parameter", {**base, "type": kind, **bad_extra}, False)


def run_checks(check, schemas, samples, mock, result_binding):
    check("correction.abi-mapping", abi_mapping_valid(mock))
    control = mock["cancel_control"]
    def matches(frame):
        return all(frame[k] == mock["request"][k] for k in ("contract_version", "correlation_id", "company_id", "session_generation"))
    check("correction.cancel-bound-to-active", matches(control))
    for key in ("correlation_id", "company_id", "session_generation"):
        check("correction.reject-stale-cancel." + key, matches({**control, key: "foreign"}), False)
    for case in mock["terminal_cases"]:
        event = case["events"][0]
        status = {"validated_response": "success", "deadline": "timeout", "user_cancel": "cancelled", "crash": "error"}[event]
        outcome = "succeeded" if status == "success" else "unknown" if case["dispatch_started"] else "not_started"
        check("correction.terminal." + case["name"], [status, outcome], [case["expected_status"], case["expected_outcome"]])
    for section, field, value in (("context", "tenant_id", "foreign"),
                                  ("context", "session_generation", 999),
                                  ("parameters", "Extra", True),
                                  ("return", "data", None)):
        altered = copy.deepcopy(mock)
        altered[section][field] = value
        check("correction.reject-abi." + section + "." + field, abi_mapping_valid(altered), False)
    for key in ("user_identity", "user_licenses", "user_signins", "mailbox_summary"):
        manifest, request = samples[key + ".manifest"], samples[key + ".request"]
        trusted = make_trusted(manifest, request, mock, schemas)
        check("correction.eligibility." + key, preflight_sample(manifest, request, trusted))
        for field, value in (("runtime", {"edition": "Desktop", "version": "5.1.0"}), ("modules", {})):
            altered = copy.deepcopy(trusted)
            altered[field] = value
            check("correction.reject-prerequisite." + key + "." + field, preflight_sample(manifest, request, altered), False)
        altered = copy.deepcopy(trusted)
        altered["modules"] = {p["name"]: "0.0.1" for p in manifest["required_modules"]}
        check("correction.reject-module-version." + key, preflight_sample(manifest, request, altered), False)
        for field, value in (("state", "expired"), ("owner_worker_id", "foreign"),
                             ("tenant_id", "foreign"), ("verified_account_upn", "other@synthetic.example"),
                             ("session_generation", 999), ("verified_at", "2026-11-02T17:00:00Z"),
                             ("expires_at", trusted["now"])):
            altered = copy.deepcopy(trusted)
            altered["connections"][0][field] = value
            check("correction.reject-connection." + key + "." + field, preflight_sample(manifest, request, altered), False)
        for field in ("approved", "dependencies_match", "bytes_pinned", "path_safe"):
            altered = copy.deepcopy(trusted)
            altered["registry"][field] = False
            check("correction.reject-trust." + key + "." + field, preflight_sample(manifest, request, altered), False)
        for field in request["release_binding"]:
            altered = copy.deepcopy(request)
            altered["release_binding"][field] = "f" * 64 if field.endswith("sha256") else "9.9.9"
            check("correction.reject-binding." + key + "." + field, preflight_sample(manifest, altered, trusted), False)
        if manifest["graph_scopes"]:
            altered = copy.deepcopy(trusted)
            altered["connections"][0]["graph_scopes"] = []
            check("correction.reject-scopes." + key, preflight_sample(manifest, request, altered), False)
        if manifest["required_roles"]:
            altered = copy.deepcopy(trusted)
            altered["connections"][0]["effective_roles"] = []
            check("correction.reject-role." + key, preflight_sample(manifest, request, altered), False)
        if manifest["target_policy"]["requires_resolved_identity"]:
            altered = copy.deepcopy(trusted)
            altered["resolution"] = None
            check("correction.reject-unresolved." + key, preflight_sample(manifest, request, altered), False)
            altered = copy.deepcopy(request)
            altered["target"] = copy.deepcopy(mock["request"]["target"])
            state = make_trusted(manifest, altered, mock, schemas)
            check("correction.reject-followon-upn." + key, preflight_sample(manifest, altered, state), False)
        result = copy.deepcopy(samples[key + ".success"])
        result["operation_exit_code"] = 30
        check("correction.reject-logical-exit." + key, result_binding(request, result, manifest=manifest), False)
        result = copy.deepcopy(samples[key + ".success"])
        result["release_binding"]["output_schema_sha256"] = "f" * 64
        check("correction.reject-result-release." + key, result_binding(request, result, manifest=manifest), False)
    dynamic = mock["dynamic_manifest"]
    request = copy.deepcopy(mock["request"])
    request["script_id"] = dynamic["script_id"]
    trusted = make_trusted(dynamic, request, mock, schemas)
    check("correction.dynamic-unknown-id-eligible", preflight_sample(dynamic, request, trusted))
    request["target"] = {"kind": "object_id", "value": mock["return"]["data"]["id"]}
    trusted = make_trusted(dynamic, request, mock, schemas)
    check("correction.dynamic-upn-only-rejects-id", preflight_sample(dynamic, request, trusted), False)
    manifest = samples["user_identity.manifest"]
    request = mock["identity_by_object_id"]["request"]
    trusted = make_trusted(manifest, request, mock, schemas)
    check("correction.identity-object-id-eligible", preflight_sample(manifest, request, trusted))
    result = copy.deepcopy(mock["envelope"])
    result["target"] = request["target"]
    check("correction.identity-object-id-result", result_binding(request, result, manifest=manifest))
    result["data"]["id"] = "f" * 36
    check("correction.identity-object-id-mismatch", result_binding(request, result, manifest=manifest), False)
    manifest = samples["user_signins.manifest"]
    check("correction.defaults-before-required", bind_parameters(manifest, {}), {"LookbackDays": 7, "MaxRecords": 20})
    base = {"name": "Example", "type": "string", "required": False, "description": "Synthetic"}
    for name, specs in (
        ("case-duplicate", [base, {**base, "name": "EXAMPLE"}]),
        ("reserved", [{**base, "name": "Context"}]),
        ("common-reserved", [{**base, "name": "ErrorAction"}]),
        ("inverted-string", [{**base, "min_length": 8, "max_length": 2}]),
        ("inverted-array", [{**base, "type": "string_array", "min_items": 3, "max_items": 2}]),
        ("inverted-item", [{**base, "type": "string_array", "item_min_length": 3, "item_max_length": 2}]),
        ("bad-array-default", [{**base, "type": "string_array", "default": ["long"], "item_max_length": 2}]),
        ("default-outside-enum", [{**base, "default": "z", "allowed_values": ["a"]}]),
        ("enum-outside-bounds", [{**base, "max_length": 2, "allowed_values": ["long"]}]),
        ("wrong-enum-type", [{**base, "type": "integer", "allowed_values": [True]}]),
        ("duplicate-enum", [{**base, "allowed_values": ["a", "a"]}]),
        ("fractional-integer-bound", [{**base, "type": "integer", "minimum": 0.5}]),
        ("numeric-on-string", [{**base, "minimum": 1}]),
    ):
        check("correction.reject-descriptor." + name, descriptors_valid(specs), False)
    for name, updates in (("scope-without-graph", {"connection_requirements": ["ExchangeOnline"]}),
                          ("role-wrong-service", {"required_roles": [{"service": "ExchangeOnline", "any_of": ["Reader"]}]}),
                          ("missing-schema", {"expected_output_schema": "schemas/absent.schema.json#/$defs/absent"}),
                          ("unknown-fragment", {"expected_output_schema": "schemas/operation-data.schema.json#/$defs/absent"})):
        check("correction.reject-metadata." + name, manifest_valid({**samples["user_identity.manifest"], **updates}, schemas), False)
    for case in mock["notes_barrier_cases"]:
        acks = [notes_ack(e) for e in case["editors"]]
        check("correction.notes-ack." + case["name"], acks, case["saved_acknowledgements"])
        check("correction.notes-transition." + case["name"], all(acks), case["transition_allowed"])
    check("correction.history-success", history_valid(mock["history"]))
    for status in ("queued", "running", "rejected", "partial", "error", "cancelled", "timeout"):
        history = copy.deepcopy(mock["history"])
        history["status"] = status
        history["codes"] = [status.upper()]
        if status in ("queued", "running"):
            history.update(completed_at=None, duration_ms=None, origin="host", operation_outcome="not_started" if status == "queued" else "unknown")
        if status in ("queued", "rejected"):
            history.update(started_at=None, origin="host", operation_outcome="not_started")
        if status in ("cancelled", "timeout"):
            history.update(operation_outcome="unknown")
        if status == "partial":
            history.update(operation_outcome="partially_succeeded")
        if status == "error":
            history.update(operation_outcome="failed")
        check("correction.history-coverage." + status, history_valid(history))
    for field, value in (("requested_at", "2026-11-02T19:00:00Z"),
                         ("completed_at", "2026-11-02T00:00:00Z"),
                         ("started_at", "2026-02-30T18:00:00Z"),
                         ("completed_at", None), ("duration_ms", -1)):
        check("correction.reject-history." + field + "." + str(value), history_valid({**mock["history"], field: value}), False)
    check("correction.parsed-fractional-time", instant("2026-11-02T18:00:00.1Z") < instant("2026-11-02T18:00:00.11Z"))
