"""ISOLATED DRAFT PROTOTYPE. In-memory plans only; never imported by application.

The schema/policy remain unapproved. This API cannot write, authenticate or activate
production imports. Pass exact pinned draft bytes explicitly; no implicit IO.
"""
from copy import deepcopy
from dataclasses import dataclass
from datetime import datetime
import hashlib
import json
import re
import unicodedata
from uuid import UUID
from jsonschema import Draft202012Validator, FormatChecker

MAX_BYTES = 8 * 1024 * 1024
VERSION = "1.0.0-draft.1"
SCHEMA_SHA256 = "f82835998fa6d7d7d84aba6c10cd1254638b1f53c710b9456e95d5e83a6ee37a"
POLICY_SHA256 = "d01397ac3a964f6d2fb03afeeca82a57119665bbc76be0e4031165ed405e58a4"

class DesignValidationError(ValueError):
    """Safe stable code; never echoes imported values."""

def parse_document(raw):
    if not isinstance(raw, bytes) or len(raw) > MAX_BYTES:
        raise DesignValidationError("INPUT_SIZE_OR_TYPE")
    def pairs(items):
        obj = {}
        for key, value in items:
            if key in obj:
                raise DesignValidationError("DUPLICATE_JSON_KEY")
            obj[key] = value
        return obj
    def nonfinite(_):
        raise DesignValidationError("NONFINITE_JSON")
    try:
        text = raw.decode("utf-8", errors="strict")
        if text.startswith("\ufeff"):
            raise DesignValidationError("UTF8_BOM")
        value = json.loads(text, object_pairs_hook=pairs, parse_constant=nonfinite)
    except (UnicodeError, json.JSONDecodeError, RecursionError, ValueError) as exc:
        if isinstance(exc, DesignValidationError):
            raise
        raise DesignValidationError("MALFORMED_JSON") from None
    def depth(obj, level=0):
        if level > 32:
            raise DesignValidationError("DEPTH_LIMIT")
        if isinstance(obj, dict):
            for key, value in obj.items():
                depth(key, level + 1)
                depth(value, level + 1)
        elif isinstance(obj, list):
            for value in obj:
                depth(value, level + 1)
        elif isinstance(obj, str):
            try:
                obj.encode("utf-8", errors="strict")
            except UnicodeError:
                raise DesignValidationError("INVALID_UNICODE") from None
    depth(value)
    return value


def validate_semantics(document):
    """Call after schema validation. Additional policy beyond cross-field schema."""
    tenants, company_ids, names, owners = set(), set(), set(), {}
    for company in document["companies"]:
        tenant = str(UUID(company["tenant_id"]))
        cid = str(UUID(company["company_id"]))
        name = company["display_name"].strip().casefold()
        if not name or tenant in tenants or cid in company_ids or name in names:
            raise DesignValidationError("DUPLICATE_OR_EMPTY_COMPANY_IDENTITY")
        tenants.add(tenant)
        company_ids.add(cid)
        names.add(name)
        domains = [company["primary_domain"].lower(), *[d.lower() for d in company["additional_verified_domains"]]]
        if len(set(domains)) != len(domains):
            raise DesignValidationError("DUPLICATE_DOMAIN")
        for domain in domains:
            if domain in owners and owners[domain] != tenant:
                raise DesignValidationError("DOMAIN_TENANT_CONFLICT")
            owners[domain] = tenant
        ids, upns = set(), set()
        for admin in company["administrators"]:
            aid = str(UUID(admin["administrator_id"]))
            upn = unicodedata.normalize("NFC", admin["upn"].strip())
            if (not re.fullmatch(r"[^\s@\x00-\x1f\x7f*?]+@[^\s@\x00-\x1f\x7f*?]+\.[^\s@\x00-\x1f\x7f*?]+", upn)
                    or aid in ids or upn.casefold() in upns):
                raise DesignValidationError("DUPLICATE_OR_INVALID_ADMINISTRATOR")
            ids.add(aid)
            upns.add(upn.casefold())
        preferred = company["preferred_administrator_id"]
        if preferred is not None and str(UUID(preferred)) not in ids:
            raise DesignValidationError("DANGLING_PREFERRED_ADMINISTRATOR")
        try:
            created = datetime.fromisoformat(company["created_at"].replace("Z", "+00:00"))
            updated = datetime.fromisoformat(company["updated_at"].replace("Z", "+00:00"))
        except ValueError:
            raise DesignValidationError("TIMESTAMP_INVALID") from None
        if updated < created:
            raise DesignValidationError("TIMESTAMP_ORDER")


@dataclass(frozen=True)
class DraftContract:
    """Exact author draft bytes, never an approval or production trust token."""

    schema_bytes: bytes
    policy_bytes: bytes

    def validator(self):
        if (hashlib.sha256(self.schema_bytes).hexdigest() != SCHEMA_SHA256
                or hashlib.sha256(self.policy_bytes).hexdigest() != POLICY_SHA256):
            raise DesignValidationError("DRAFT_PIN_MISMATCH")
        schema = parse_document(self.schema_bytes)
        Draft202012Validator.check_schema(schema)
        return Draft202012Validator(schema, format_checker=FormatChecker())


@dataclass(frozen=True)
class MergePlan:
    candidate: dict | None
    counts: dict
    conflicts: tuple[dict, ...]
    validation_failures: tuple[dict, ...]
    changed_company_ids: tuple[str, ...]
    records: tuple[dict, ...]
    prototype_only: bool = True
    durable: bool = False
    backup_status: str = "NOT IMPLEMENTED"

    @property
    def changes_required(self):
        return bool(self.changed_company_ids) and not self.validation_failures


def _normalize(document):
    doc = deepcopy(document)
    for company in doc["companies"]:
        for field in ("company_id", "tenant_id"):
            company[field] = str(UUID(company[field]))
        for field in ("display_name", "notes"):
            company[field] = company[field].strip()
        company["primary_domain"] = company["primary_domain"].lower()
        company["additional_verified_domains"] = sorted(d.lower() for d in company["additional_verified_domains"])
        if company["preferred_administrator_id"]:
            company["preferred_administrator_id"] = str(UUID(company["preferred_administrator_id"]))
        for admin in company["administrators"]:
            admin["administrator_id"] = str(UUID(admin["administrator_id"]))
            admin["upn"] = unicodedata.normalize("NFC", admin["upn"].strip())
            admin["display_label"] = admin["display_label"].strip()
        company["administrators"].sort(key=lambda a: (a["upn"].casefold(), a["administrator_id"]))
    doc["companies"].sort(key=lambda c: (c["tenant_id"], c["company_id"]))
    return doc


def _validate(document, validator):
    if next(validator.iter_errors(document), None) is not None:
        raise DesignValidationError("SCHEMA_INVALID")
    try:
        json.dumps(document, ensure_ascii=False, allow_nan=False).encode("utf-8", errors="strict")
    except (UnicodeError, ValueError):
        raise DesignValidationError("INVALID_UNICODE") from None
    normalized = _normalize(document)
    validate_semantics(normalized)
    if next(validator.iter_errors(normalized), None) is not None:
        raise DesignValidationError("NORMALIZED_SCHEMA_INVALID")
    return normalized


def canonical_bytes(document):
    """Deterministic envelope/schema field order without mutating the input."""
    doc = _normalize(document)
    company_fields = ("company_id", "display_name", "tenant_id", "primary_domain",
                      "additional_verified_domains", "administrators", "preferred_administrator_id",
                      "preferred_cloud", "notes", "created_at", "updated_at")
    companies = []
    for company in doc["companies"]:
        company["administrators"] = [
            {key: a[key] for key in ("administrator_id", "upn", "display_label")}
            for a in company["administrators"]
        ]
        companies.append({key: company[key] for key in company_fields})
    result = {"format": doc["format"], "schema_version": doc["schema_version"], "companies": companies}
    return (json.dumps(result, ensure_ascii=False, allow_nan=False, indent=2) + "\n").encode("utf-8")


def plan_merge_prototype(local, imported_json: bytes, contract: DraftContract) -> MergePlan:
    """Validate both complete inputs and the result, return a detached draft plan.

    No production entrypoint is provided while approval/storage gates are pending.
    Diagnostics use canonical incoming indices, independent of JSON array ordering.
    No timestamps are changed; changed_company_ids require future commit stamping.
    """
    counts = dict(companies_added=0, existing_companies_enriched=0,
                  administrators_added=0, additional_domains_added=0,
                  records_unchanged=0, companies_skipped=0, conflicts_skipped=0)
    stage = "contract"
    try:
        validator = contract.validator()
        stage = "local"
        local = _validate(local, validator)
        stage = "imported"
        incoming = _validate(parse_document(imported_json), validator)
    except DesignValidationError as exc:
        return MergePlan(None, counts, (), ({"stage": stage, "code": str(exc)},), (), ())

    companies = {c["tenant_id"]: c for c in local["companies"]}
    ids = {c["company_id"]: c["tenant_id"] for c in companies.values()}
    names = {c["display_name"].casefold(): c["tenant_id"] for c in companies.values()}
    owners = {d: c["tenant_id"] for c in companies.values()
              for d in (c["primary_domain"], *c["additional_verified_domains"])}
    conflicts, changed, records = [], [], []

    for index, imported in enumerate(incoming["companies"]):
        tenant = imported["tenant_id"]
        existing = companies.get(tenant)
        diagnostics = []
        def conflict(code, field, scope="field", administrator_index=None):
            item = dict(code=code, scope=scope, company_index=index, field=field)
            if administrator_index is not None:
                item["administrator_index"] = administrator_index
            diagnostics.append(item)

        skip = None
        if imported["company_id"] in ids and ids[imported["company_id"]] != tenant:
            skip = ("COMPANY_ID_TENANT_CONFLICT", "company_id")
        elif existing is None and imported["display_name"].casefold() in names:
            skip = ("NAME_COLLISION", "display_name")
        elif existing is None and imported["primary_domain"] in owners and owners[imported["primary_domain"]] != tenant:
            skip = ("DOMAIN_TENANT_CONFLICT", "primary_domain")
        if skip:
            conflict(*skip, scope="company")
            counts["companies_skipped"] += 1
            records.append(dict(company_index=index, status="skipped"))
            conflicts.extend(diagnostics)
            continue

        candidate = deepcopy(existing if existing is not None else imported)
        if existing is None:
            candidate["additional_verified_domains"] = []
            if len(companies) >= 1000:
                conflict("CAPACITY_CONFLICT", "companies", "company")
                counts["companies_skipped"] += 1
                records.append(dict(company_index=index, status="skipped"))
                conflicts.extend(diagnostics)
                continue
        else:
            for field in ("display_name", "notes", "preferred_cloud"):
                if imported[field] != existing[field]:
                    conflict("VALUE_CONFLICT", field)
            if imported["primary_domain"] != existing["primary_domain"]:
                code = "DOMAIN_TENANT_CONFLICT" if owners.get(imported["primary_domain"], tenant) != tenant else "PRIMARY_DOMAIN_DIFFERENCE"
                conflict(code, "primary_domain")

        domains_added = 0
        for domain in imported["additional_verified_domains"]:
            if domain in (candidate["primary_domain"], *candidate["additional_verified_domains"]):
                continue
            if owners.get(domain, tenant) != tenant:
                conflict("DOMAIN_TENANT_CONFLICT", "additional_verified_domains", "domain")
                continue
            candidate["additional_verified_domains"].append(domain)
            domains_added += 1

        admins_added = len(candidate["administrators"]) if existing is None else 0
        if existing is not None:
            by_upn = {a["upn"].casefold(): a for a in candidate["administrators"]}
            by_id = {a["administrator_id"]: a for a in candidate["administrators"]}
            aliases = {}
            for ai, admin in enumerate(imported["administrators"]):
                matched = by_upn.get(admin["upn"].casefold())
                if matched:
                    aliases[admin["administrator_id"]] = matched["administrator_id"]
                    if admin["display_label"] != matched["display_label"]:
                        conflict("VALUE_CONFLICT", "display_label", "admin", ai)
                elif admin["administrator_id"] in by_id:
                    conflict("ADMIN_ID_UPN_CONFLICT", "administrator_id", "admin", ai)
                else:
                    added = deepcopy(admin)
                    candidate["administrators"].append(added)
                    by_upn[admin["upn"].casefold()] = added
                    by_id[admin["administrator_id"]] = added
                    aliases[admin["administrator_id"]] = admin["administrator_id"]
                    admins_added += 1
            preferred = imported["preferred_administrator_id"]
            if preferred:
                mapped = aliases.get(preferred)
                if mapped is None:
                    conflict("DEFAULT_UNAVAILABLE", "preferred_administrator_id")
                elif candidate["preferred_administrator_id"] is None:
                    candidate["preferred_administrator_id"] = mapped
                elif candidate["preferred_administrator_id"] != mapped:
                    conflict("DEFAULT_CONFLICT", "preferred_administrator_id")

        if len(candidate["additional_verified_domains"]) > 30 or len(candidate["administrators"]) > 100:
            diagnostics = []  # The whole delta is skipped; no partial success counts.
            conflict("CAPACITY_CONFLICT", "company", "company")
            counts["companies_skipped"] += 1
            records.append(dict(company_index=index, status="skipped"))
            conflicts.extend(diagnostics)
            continue

        candidate["additional_verified_domains"].sort()
        candidate["administrators"].sort(key=lambda a: (a["upn"].casefold(), a["administrator_id"]))
        if existing is None or candidate != existing:
            companies[tenant] = candidate
            ids[candidate["company_id"]] = tenant
            names[candidate["display_name"].casefold()] = tenant
            for domain in (candidate["primary_domain"], *candidate["additional_verified_domains"]):
                owners[domain] = tenant
            counts["companies_added" if existing is None else "existing_companies_enriched"] += 1
            counts["administrators_added"] += admins_added
            counts["additional_domains_added"] += domains_added
            changed.append(candidate["company_id"])
            status = "added" if existing is None else "enriched"
        else:
            counts["records_unchanged"] += 1
            status = "unchanged"
        records.append(dict(company_index=index, status=status))
        conflicts.extend(diagnostics)

    counts["conflicts_skipped"] = len(conflicts)
    result = dict(format=local["format"], schema_version=VERSION, companies=list(companies.values()))
    try:
        result = _validate(result, validator)
    except DesignValidationError:
        empty = {key: 0 for key in counts}
        return MergePlan(None, empty, (), ({"stage": "result", "code": "RESULT_INVALID"},), (), ())
    conflicts.sort(key=lambda d: (d["company_index"], d["scope"], d["field"], d.get("administrator_index", -1), d["code"]))
    return MergePlan(result, counts, tuple(conflicts), (), tuple(changed), tuple(records))


