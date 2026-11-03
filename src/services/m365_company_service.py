"""Portable, non-secret company metadata. No Qt, SQLite, authentication or IO."""

from dataclasses import asdict, dataclass, replace
from datetime import datetime, timezone
import re
import unicodedata
from uuid import UUID, uuid4


DIRECTORY_FORMAT = "m365.company-directory"
DIRECTORY_VERSION = 1  # Independent of the PowerShell wire contract.
CLOUDS = ("Global", "USGov", "USGovDoD", "China")


def guid(value):
    if not isinstance(value, str):
        raise ValueError("Identifier must be text.")
    value = value.strip()
    if not re.fullmatch(r"[0-9a-fA-F]{8}(?:-[0-9a-fA-F]{4}){3}-[0-9a-fA-F]{12}", value):
        raise ValueError("Enter a canonical tenant or object UUID.")
    return str(UUID(value))


def upn(value):
    if not isinstance(value, str):
        raise ValueError("UPN must be text.")
    value = unicodedata.normalize("NFC", value.strip())
    if not 3 <= len(value) <= 254 or not re.fullmatch(r"[^\s@\x00-\x1f\x7f*?]+@[^\s@\x00-\x1f\x7f*?]+\.[^\s@\x00-\x1f\x7f*?]+", value):
        raise ValueError("Enter a valid email / UPN without wildcards or control characters.")
    return value


def text(value, limit, *, required=False):
    if not isinstance(value, str):
        raise ValueError("Metadata must be text.")
    value = value.strip()
    if len(value) > limit or (required and not value) or any(ord(c) < 32 or ord(c) == 127 for c in value):
        raise ValueError(f"Enter {'1' if required else '0'}–{limit} characters without control characters.")
    return value


def domain(value):
    value = text(value, 253, required=True).lower()
    if len(value.split(".")) < 2 or any(not re.fullmatch(r"[a-z0-9](?:[a-z0-9-]{0,61}[a-z0-9])?", label) for label in value.split(".")):
        raise ValueError("Enter a valid DNS domain.")
    return value


def utc_now():
    return datetime.now(timezone.utc).isoformat().replace("+00:00", "Z")


def validate_timestamp(value, name, *, allow_empty=False):
    if isinstance(value, bool) or not isinstance(value, str):
        raise ValueError(f"{name} must be an ISO 8601 UTC string.")
    if not value:
        if allow_empty:
            return utc_now()
        raise ValueError(f"{name} cannot be empty.")
    if not value.endswith("Z"):
        raise ValueError(f"{name} must be UTC with a Z suffix.")
    try:
        dt = datetime.fromisoformat(value[:-1] + "+00:00")
    except ValueError as exc:
        raise ValueError(f"Invalid timestamp format for {name}: {value}") from exc
    if dt.tzinfo != timezone.utc:
        raise ValueError(f"{name} must be in UTC timezone.")
    return value


@dataclass(frozen=True)
class Administrator:
    administrator_id: str
    upn: str
    display_label: str = ""

    def __post_init__(self):
        object.__setattr__(self, "administrator_id", guid(self.administrator_id))
        object.__setattr__(self, "upn", upn(self.upn))
        object.__setattr__(self, "display_label", text(self.display_label, 128))


@dataclass(frozen=True)
class Company:
    company_id: str
    display_name: str
    tenant_id: str
    primary_domain: str
    additional_verified_domains: tuple[str, ...] = ()
    administrators: tuple[Administrator, ...] = ()
    preferred_administrator_id: str | None = None
    preferred_cloud: str = "Global"
    notes: str = ""
    created_at: str = ""
    updated_at: str = ""

    def __post_init__(self):
        for key in ("company_id", "tenant_id"):
            object.__setattr__(self, key, guid(getattr(self, key)))
        object.__setattr__(self, "display_name", text(self.display_name, 128, required=True))
        object.__setattr__(self, "primary_domain", domain(self.primary_domain))
        domains = tuple(domain(d) for d in self.additional_verified_domains)
        if len(domains) > 30 or len(set((self.primary_domain, *domains))) != len(domains) + 1:
            raise ValueError("Domains must be unique; at most 30 additional domains are supported.")
        object.__setattr__(self, "additional_verified_domains", domains)
        admins = tuple(self.administrators)
        if len(admins) > 100 or any(not isinstance(a, Administrator) for a in admins):
            raise ValueError("Invalid administrator records.")
        if len({a.administrator_id for a in admins}) != len(admins) or len({a.upn.casefold() for a in admins}) != len(admins):
            raise ValueError("Administrator IDs and UPNs must be unique within a company.")
        if self.preferred_administrator_id is not None and self.preferred_administrator_id not in {a.administrator_id for a in admins}:
            raise ValueError("Preferred administrator must belong to this company.")
        object.__setattr__(self, "administrators", admins)
        if self.preferred_cloud not in CLOUDS:
            raise ValueError("Unsupported cloud environment.")
        object.__setattr__(self, "notes", text(self.notes, 1024))
        for key in ("created_at", "updated_at"):
            value = validate_timestamp(getattr(self, key), key, allow_empty=True)
            object.__setattr__(self, key, value)
        created_dt = datetime.fromisoformat(self.created_at[:-1] + "+00:00")
        updated_dt = datetime.fromisoformat(self.updated_at[:-1] + "+00:00")
        if updated_dt < created_dt:
            raise ValueError("Updated timestamp precedes creation.")

    @property
    def preferred_admin_upn(self):
        return next((a.upn for a in self.administrators if a.administrator_id == self.preferred_administrator_id), None)


class CompanyDirectory:
    """RAM-only directory; future storage adapters consume the versioned metadata seam.

    No path/default DB, automatic save, production migration, or authentication state.
    """

    def __init__(self, companies=()):
        self._companies = {}
        self.revision = 0
        for company in companies:
            self.save(company)

    def get(self, company_id):
        return self._companies[company_id]

    def search(self, query=""):
        words = query.casefold().split()
        return tuple(sorted((c for c in self._companies.values() if all(
            w in " ".join((c.display_name, c.primary_domain, *c.additional_verified_domains)).casefold() for w in words)),
            key=lambda c: (c.display_name.casefold(), c.company_id)))

    def save(self, company):
        if not isinstance(company, Company):
            raise ValueError("Expected a company profile.")
        for other in self._companies.values():
            if other.company_id != company.company_id and (
                other.tenant_id == company.tenant_id or other.display_name.casefold() == company.display_name.casefold()
            ):
                raise ValueError("A company with this name or tenant already exists. Edit that profile.")
        previous = self._companies.get(company.company_id)
        if previous:
            company = replace(company, created_at=previous.created_at, updated_at=utc_now())
        self._companies[company.company_id] = company
        self.revision += 1
        return company

    def administrators(self, company_id, query=""):
        return tuple(sorted((a for a in self.get(company_id).administrators if query.casefold() in
                            f"{a.upn} {a.display_label}".casefold()), key=lambda a: (a.upn.casefold(), a.administrator_id)))

    def save_administrator(self, company_id, administrator):
        company = self.get(company_id)
        admins = tuple(a for a in company.administrators if a.administrator_id != administrator.administrator_id)
        return self.save(replace(company, administrators=(*admins, administrator)))

    def remove_administrator(self, company_id, administrator_id):
        company = self.get(company_id)
        return self.save(replace(company, administrators=tuple(a for a in company.administrators if a.administrator_id != administrator_id),
                                 preferred_administrator_id=None if company.preferred_administrator_id == administrator_id else company.preferred_administrator_id))

    def set_default(self, company_id, administrator_id):
        return self.save(replace(self.get(company_id), preferred_administrator_id=administrator_id))

    def export_metadata(self):
        """Explicit metadata only; no context, connections, credentials or arbitrary fields."""
        return {"format": DIRECTORY_FORMAT, "version": DIRECTORY_VERSION,
                "companies": [{**asdict(c), "administrators": [asdict(a) for a in c.administrators],
                               "additional_verified_domains": list(c.additional_verified_domains)} for c in self.search()]}

    @classmethod
    def from_metadata(cls, payload):
        if not isinstance(payload, dict) or set(payload) != {"format", "version", "companies"} or payload["format"] != DIRECTORY_FORMAT or type(payload["version"]) is not int or payload["version"] != DIRECTORY_VERSION:
            raise ValueError("Unsupported company-directory metadata format.")
        if not isinstance(payload["companies"], list) or len(payload["companies"]) > 1000:
            raise ValueError("Invalid company inventory.")
        companies = []
        for raw in payload["companies"]:
            if not isinstance(raw, dict) or set(raw) != set(Company.__dataclass_fields__):
                raise ValueError("Unknown or missing profile fields; secrets are prohibited.")
            for ts_key in ("created_at", "updated_at"):
                validate_timestamp(raw.get(ts_key), ts_key, allow_empty=False)
            fields = dict(raw)
            if not isinstance(fields["administrators"], (list, tuple)) or not isinstance(fields["additional_verified_domains"], (list, tuple)):
                raise ValueError("Expected metadata arrays.")
            admins = []
            for a in fields["administrators"]:
                if not isinstance(a, dict) or set(a) != set(Administrator.__dataclass_fields__):
                    raise ValueError("Unknown administrator fields; credentials are prohibited.")
                admins.append(Administrator(**a))
            fields["administrators"] = tuple(admins)
            companies.append(Company(**fields))
        if len({c.company_id for c in companies}) != len(companies):
            raise ValueError("Duplicate company IDs in import.")
        return cls(companies)


def synthetic_directory():
    """Clearly fictitious records; never derived from a production Notes database."""
    return CompanyDirectory((
        Company("10000000-0000-4000-8000-000000000001", "Example Alpine (synthetic)",
                "20000000-0000-4000-8000-000000000001", "alpine.example",
                administrators=(Administrator("30000000-0000-4000-8000-000000000001", "admin@alpine.example", "Primary (hint)"),
                                Administrator("30000000-0000-4000-8000-000000000002", "backup@alpine.example", "Backup (hint)")),
                preferred_administrator_id="30000000-0000-4000-8000-000000000001"),
        Company("10000000-0000-4000-8000-000000000002", "Example Birch (synthetic)",
                "20000000-0000-4000-8000-000000000002", "birch.example"),
    ))
