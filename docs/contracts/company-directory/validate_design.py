"""Offline draft-contract validator for synthetic fixtures, not an import adapter."""

from datetime import datetime
import json
from pathlib import Path
import re
import unicodedata
from uuid import UUID

from jsonschema import Draft202012Validator, FormatChecker

HERE = Path(__file__).resolve().parent
MAX_BYTES = 8 * 1024 * 1024


class DesignValidationError(ValueError):
    """Stable diagnostics contain codes, never imported field values."""


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
            for value in obj.values():
                depth(value, level + 1)
        elif isinstance(obj, list):
            for value in obj:
                depth(value, level + 1)
    depth(value)
    return value


def validate_schema(document):
    schema = json.loads((HERE / "company-directory.schema.json").read_text(encoding="utf-8"))
    Draft202012Validator.check_schema(schema)
    validator = Draft202012Validator(schema, format_checker=FormatChecker())
    if next(validator.iter_errors(document), None) is not None:
        raise DesignValidationError("SCHEMA_INVALID")


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


def validate_bytes(raw):
    document = parse_document(raw)
    validate_schema(document)
    validate_semantics(document)
    return document
