"""Synthetic identity/context boundary. No authentication adapter or engine import.

The fixture manager cannot mint runtime identity proof. A later approved adapter
must own actual account/tenant/scopes/RBAC and the contract invocation context.
"""

from dataclasses import dataclass, replace
from datetime import datetime, timedelta, timezone
from uuid import uuid4

from src.services.m365_company_service import guid, upn

SERVICES = ("Graph", "ExchangeOnline")


@dataclass(frozen=True)
class SyntheticConnection:
    service: str
    state: str = "disconnected"
    tenant_id: str | None = None
    account_upn: str | None = None
    expires_at: datetime | None = None
    session_generation: int = 0
    warning: str = ""
    provenance: str = "synthetic"


@dataclass(frozen=True)
class TargetInput:
    upn: str = ""
    object_id: str = ""

    @classmethod
    def parse(cls, user_upn="", object_id=""):
        return cls(upn(user_upn) if user_upn.strip() else "", guid(object_id) if object_id.strip() else "")

    def contract_target(self):
        """Contract-shaped identifier only; does not construct an executable request."""
        if self.object_id:
            return {"kind": "object_id", "value": self.object_id}
        if self.upn:
            return {"kind": "upn", "value": self.upn}
        raise ValueError("Enter a client UPN or Entra object ID.")


@dataclass(frozen=True)
class SyntheticTarget:
    tenant_id: str
    upn: str
    object_id: str
    session_generation: int
    provenance: str = "synthetic"


@dataclass(frozen=True)
class Eligibility:
    eligible: bool
    reasons: tuple[str, ...]


class SyntheticConnectionManager:
    """RAM-only independent per-service states, deliberately never 'verified'."""

    def __init__(self, now=None):
        self.now = now or (lambda: datetime.now(timezone.utc))
        self.clear()

    def clear(self):
        self._states = {service: SyntheticConnection(service) for service in SERVICES}

    def state(self, service):
        value = self._states[service]
        if value.expires_at is not None and self.now() >= value.expires_at and value.state in ("simulated", "permission_warning"):
            value = replace(value, state="expired", warning="Synthetic session expired; reconnect explicitly.")
            self._states[service] = value
        return value

    def simulate(self, service, tenant_id, account_upn, generation, *, outcome="simulated", seconds=300):
        if service not in SERVICES or outcome not in ("simulated", "error", "permission_warning"):
            raise ValueError("Unsupported synthetic connection outcome.")
        warning = {"simulated": "Scopes and effective roles are unverified.",
                   "error": "Synthetic connection failed. No Microsoft sign-in occurred.",
                   "permission_warning": "Synthetic permission warning; consent/RBAC must be verified."}[outcome]
        self._states[service] = SyntheticConnection(service, outcome, guid(tenant_id), upn(account_upn),
                                                    self.now() + timedelta(seconds=seconds), generation, warning)


class CompanyContextService:
    """Owns selected metadata, generation, confirmation and synthetic context.

    Stable administrator-record IDs are metadata; admin_identity_ref is a separate
    transient host reference. Neither is proof. All dispatch is structurally absent.
    """

    def __init__(self, directory, *, connection_manager=None):
        self.directory = directory
        self.connections = connection_manager or SyntheticConnectionManager()
        self.company_id = None
        self.administrator_id = None
        self.admin_identity_ref = str(uuid4())
        self.session_generation = 0
        self._directory_revision = directory.revision
        self.confirmed_company = None
        self.administrator_upn = ""
        self.target_input = TargetInput()
        self.target = None
        self.target_status = "Unresolved — no client selected."

    def _invalidate(self):
        self.session_generation += 1
        self.admin_identity_ref = str(uuid4())
        self.connections.clear()
        self.confirmed_company = None
        self.target_input = TargetInput()
        self.target = None
        self.target_status = "Unresolved — context changed; enter client identity again."

    def synchronize(self):
        """Fail closed even when another metadata view edits the directory."""
        if self._directory_revision != self.directory.revision:
            self._directory_revision = self.directory.revision
            self._invalidate()
            if self.company_id:
                admins = self.directory.get(self.company_id).administrators
                selected = next((a for a in admins if a.administrator_id == self.administrator_id), None)
                self.administrator_id = selected.administrator_id if selected else None
                self.administrator_upn = selected.upn if selected else ""

    @property
    def company(self):
        self.synchronize()
        return self.directory.get(self.company_id) if self.company_id else None

    def select_company(self, company_id):
        company = self.directory.get(company_id) if company_id else None
        self._invalidate()
        self._directory_revision = self.directory.revision
        self.company_id = company_id
        self.administrator_id = None
        self.administrator_upn = ""
        if company and company.preferred_administrator_id:
            self.select_administrator(company.preferred_administrator_id)

    def select_administrator(self, administrator_id):
        company = self.company
        admin = next((a for a in company.administrators if a.administrator_id == administrator_id), None) if company else None
        if administrator_id and admin is None:
            raise ValueError("Administrator does not belong to the selected company.")
        self._invalidate()
        self.administrator_id = administrator_id
        self.administrator_upn = admin.upn if admin else ""

    def set_administrator_upn(self, value):
        normalized = upn(value) if value.strip() else ""
        self.synchronize()
        if normalized != self.administrator_upn:
            self._invalidate()
            self.administrator_id = None  # Edited hint is not a saved account selection.
            self.administrator_upn = normalized

    def confirm_company(self):
        company = self.company
        if company is None:
            raise ValueError("Select a company before confirming.")
        self.confirmed_company = (company.company_id, company.tenant_id, self.directory.revision, self.session_generation)

    def connect_synthetic(self, service, **fixture):
        company = self.company
        if company is None or not self.administrator_upn:
            raise ValueError("Select a company and enter an administrator UPN first.")
        self.confirmed_company = None
        self.target = None
        self.target_status = "Unresolved — connection context changed."
        self.connections.simulate(service, company.tenant_id, self.administrator_upn, self.session_generation, **fixture)

    def disconnect(self):
        self._invalidate()

    def set_target(self, user_upn="", object_id=""):
        self.synchronize()
        self.target = None
        self.target_input = TargetInput()  # A rejected edit must not leave an old target usable.
        self.target_status = "Invalid or unresolved client identity."
        self.target_input = TargetInput.parse(user_upn, object_id)
        self.target_status = "Unresolved — entered identifiers are hints only."

    def resolve_synthetic(self, *, tenant_id=None, resolved_upn=None, resolved_object_id=None):
        company = self.company
        self.target = None
        self.target_status = "Unresolved — no identity evidence."
        if company is None:
            raise ValueError("Select a company first.")
        self.target_input.contract_target()
        # Explicit deterministic fixture only; never labelled as provider evidence.
        candidate = SyntheticTarget(guid(tenant_id or company.tenant_id),
                                    upn(resolved_upn or self.target_input.upn or "client@example.invalid"),
                                    guid(resolved_object_id or self.target_input.object_id or "40000000-0000-4000-8000-000000000001"),
                                    self.session_generation)
        if candidate.tenant_id != company.tenant_id:
            self.target_status = "Tenant mismatch — synthetic target rejected."
            raise ValueError(self.target_status)
        if ((self.target_input.upn and candidate.upn.casefold() != self.target_input.upn.casefold()) or
            (self.target_input.object_id and candidate.object_id != self.target_input.object_id)):
            self.target_status = "Target mismatch — supplied UPN and object ID do not bind to the fixture."
            raise ValueError(self.target_status)
        self.target = candidate
        self.target_status = "Synthetic resolution only — target is not verified."

    def eligibility(self, required_services=SERVICES):
        company = self.company
        reasons = ["DISPATCH_DISABLED: no approved execution integration is installed.",
                   "CONTRACT_ENGINE_OPERATION_AUTH_GATES: individually required; synthetic state supplies no approval."]
        if company is None:
            reasons.append("COMPANY_REQUIRED")
        if company is None or self.confirmed_company != (company.company_id, company.tenant_id, self.directory.revision, self.session_generation):
            reasons.append("COMPANY_CONFIRMATION_REQUIRED")
        for service in required_services:
            state = self.connections.state(service)
            reasons.append(f"{service}: CONNECTION_UNVERIFIED ({state.state}; synthetic)")
            if company and state.tenant_id and state.tenant_id != company.tenant_id:
                reasons.append("TENANT_MISMATCH")
            if state.account_upn and state.account_upn.casefold() != self.administrator_upn.casefold():
                reasons.append("ACCOUNT_MISMATCH")
            if state.state != "disconnected" and state.session_generation != self.session_generation:
                reasons.append("STALE_CONTEXT")
        if self.target is None:
            reasons.append("TARGET_UNRESOLVED")
        elif (company is None or self.target.tenant_id != company.tenant_id or self.target.session_generation != self.session_generation
              or self.target_input.upn and self.target.upn.casefold() != self.target_input.upn.casefold()
              or self.target_input.object_id and self.target.object_id != self.target_input.object_id):
            reasons.append("TARGET_MISMATCH")
        else:
            reasons.append("TARGET_UNVERIFIED: synthetic resolution is not identity evidence.")
        return Eligibility(False, tuple(reasons))
