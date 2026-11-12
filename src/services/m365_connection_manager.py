"""Persistent worker-backed live Microsoft 365 connection lifecycle manager."""

from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime, timedelta, timezone
import json
from pathlib import Path
import threading
from typing import Callable
from uuid import uuid4

from src.services.m365_preflight_service import LIVE_PILOT_MANIFEST_PATHS, ROOT
from src.services.m365_worker_host import (
    M365WorkerHost,
    M365WorkerHostError,
    WorkerIdentity,
)


SERVICES = ("Graph", "ExchangeOnline")
DEFAULT_LEASE_MINUTES = 60
SUPPORTED_AUTH_MODES = ("browser", "device_code")


def _utc_now() -> datetime:
    return datetime.now(timezone.utc)


@dataclass(frozen=True)
class LiveConnectionState:
    """Host-owned lease record for one live M365 service inside a persistent worker."""

    service: str
    state: str = "disconnected"  # disconnected | connecting | verified | expired | error
    tenant_id: str | None = None
    account_upn: str | None = None
    auth_mode: str | None = None
    connected_at: datetime | None = None
    expires_at: datetime | None = None
    session_generation: int = 0
    warning: str | None = None
    error_code: str | None = None
    graph_scopes: tuple[str, ...] = ()
    effective_roles: tuple[str, ...] = ()
    connection_id: str | None = None
    owner_worker_id: str | None = None


def pilot_graph_scopes(library_root: Path | None = None) -> tuple[str, ...]:
    """Read required read-only Microsoft Graph scopes dynamically from the pilot manifests."""
    root = Path(library_root) if library_root is not None else ROOT / "scripts/m365"
    scopes: list[str] = []
    seen: set[str] = set()
    for rel in LIVE_PILOT_MANIFEST_PATHS:
        manifest_path = root / rel
        if not manifest_path.is_file():
            continue
        try:
            manifest = json.loads(manifest_path.read_text(encoding="utf-8"))
        except (OSError, ValueError):
            continue
        if "Graph" not in manifest.get("connection_requirements", []):
            continue
        for scope in manifest.get("graph_scopes", []):
            if isinstance(scope, str) and scope and scope not in seen:
                seen.add(scope)
                scopes.append(scope)
    return tuple(scopes)


def pilot_module_constraint(module_name: str, library_root: Path | None = None) -> dict[str, str]:
    """Return pinned SemVer bounds for a given module from the pilot manifests."""
    root = Path(library_root) if library_root is not None else ROOT / "scripts/m365"
    for rel in LIVE_PILOT_MANIFEST_PATHS:
        manifest_path = root / rel
        if not manifest_path.is_file():
            continue
        try:
            manifest = json.loads(manifest_path.read_text(encoding="utf-8"))
        except (OSError, ValueError):
            continue
        for mod in manifest.get("required_modules", []):
            if mod.get("name") == module_name:
                return {
                    "name": module_name,
                    "minimum_version": str(mod.get("minimum_version", "0.0.0")),
                    "maximum_version": str(mod.get("maximum_version", "999.999.999")),
                }
    return {
        "name": module_name,
        "minimum_version": "0.0.0",
        "maximum_version": "999.999.999",
    }


class LiveConnectionManager:
    """Owns one persistent `pwsh` worker per active context and verifies every live lease."""

    def __init__(
        self,
        *,
        pwsh_path: Path | None = None,
        library_root: Path | None = None,
        lease_minutes: int = DEFAULT_LEASE_MINUTES,
        worker_factory: Callable[[WorkerIdentity], M365WorkerHost] | None = None,
    ) -> None:
        self.pwsh_path = Path(pwsh_path) if pwsh_path is not None else None
        self.library_root = Path(library_root) if library_root is not None else ROOT / "scripts/m365"
        self.lease_minutes = lease_minutes
        self._worker_factory = worker_factory
        self._lock = threading.RLock()
        self._worker: M365WorkerHost | None = None
        self._states: dict[str, LiveConnectionState] = {
            svc: LiveConnectionState(service=svc) for svc in SERVICES
        }

    @property
    def worker_host(self) -> M365WorkerHost | None:
        with self._lock:
            return self._worker

    def state(self, service: str) -> LiveConnectionState:
        with self._lock:
            return self._states[service]

    def states(self) -> dict[str, LiveConnectionState]:
        with self._lock:
            return dict(self._states)

    def clear(self, reason: str | None = None) -> None:
        """Synchronously terminate the active worker and clear all live leases."""
        worker_to_close: M365WorkerHost | None = None
        with self._lock:
            worker_to_close = self._worker
            self._worker = None
            for svc in SERVICES:
                self._states[svc] = LiveConnectionState(service=svc, warning=reason)
        if worker_to_close is not None:
            worker_to_close.shutdown()

    def expire_elapsed(self, now: datetime | None = None) -> bool:
        """Mark expired verified leases and shut down the worker if no verified lease remains."""
        current = now or _utc_now()
        changed = False
        has_active = False
        with self._lock:
            for svc, st in list(self._states.items()):
                if st.state == "verified" and st.expires_at is not None and current >= st.expires_at:
                    self._states[svc] = LiveConnectionState(
                        service=svc,
                        state="expired",
                        tenant_id=st.tenant_id,
                        account_upn=st.account_upn,
                        auth_mode=st.auth_mode,
                        session_generation=st.session_generation,
                        warning="Live service lease expired; sign in again.",
                    )
                    changed = True
                elif self._states[svc].state == "verified":
                    has_active = True
            worker_to_close = self._worker if (changed and not has_active) else None
            if worker_to_close is not None:
                self._worker = None
        if worker_to_close is not None:
            worker_to_close.shutdown()
        return changed

    def _ensure_worker_for(
        self,
        *,
        company_id: str,
        tenant_id: str,
        admin_identity_ref: str,
        session_generation: int,
    ) -> M365WorkerHost:
        old_worker: M365WorkerHost | None = None
        with self._lock:
            current = self._worker
            same_context = (
                current is not None
                and current.is_alive
                and current.identity.company_id == company_id
                and current.identity.tenant_id.lower() == tenant_id.lower()
                and current.identity.admin_identity_ref == admin_identity_ref
                and current.identity.session_generation == session_generation
            )
            if same_context:
                return current  # type: ignore[return-value]
            old_worker = current
            self._worker = None
            for svc in SERVICES:
                self._states[svc] = LiveConnectionState(service=svc)

        if old_worker is not None:
            old_worker.shutdown()

        identity = WorkerIdentity(
            worker_id=str(uuid4()),
            company_id=company_id,
            tenant_id=tenant_id,
            admin_identity_ref=admin_identity_ref,
            session_generation=session_generation,
        )
        worker = (
            self._worker_factory(identity)
            if self._worker_factory is not None
            else M365WorkerHost(identity, pwsh_path=self.pwsh_path)
        )
        worker.start()
        with self._lock:
            self._worker = worker
        return worker

    def connect_service(
        self,
        *,
        service: str,
        company_id: str,
        tenant_id: str,
        admin_identity_ref: str,
        expected_account_upn: str,
        session_generation: int,
        auth_mode: str = "browser",
        scopes: tuple[str, ...] | None = None,
        organization: str | None = None,
        timeout_seconds: float = 180.0,
        cancel_event: threading.Event | None = None,
        on_event: Callable[[dict], None] | None = None,
    ) -> LiveConnectionState:
        """Establish and hard-verify an interactive live service connection inside the worker."""
        if service not in SERVICES:
            raise ValueError(f"Unsupported M365 service: {service}")
        if auth_mode not in SUPPORTED_AUTH_MODES:
            raise ValueError(f"Unsupported interactive auth mode: {auth_mode}")

        with self._lock:
            self._states[service] = LiveConnectionState(
                service=service,
                state="connecting",
                tenant_id=tenant_id,
                account_upn=expected_account_upn,
                auth_mode=auth_mode,
                session_generation=session_generation,
            )

        try:
            worker = self._ensure_worker_for(
                company_id=company_id,
                tenant_id=tenant_id,
                admin_identity_ref=admin_identity_ref,
                session_generation=session_generation,
            )
        except M365WorkerHostError as exc:
            err_state = LiveConnectionState(
                service=service,
                state="error",
                tenant_id=tenant_id,
                account_upn=expected_account_upn,
                auth_mode=auth_mode,
                session_generation=session_generation,
                warning=exc.message,
                error_code=exc.code,
            )
            with self._lock:
                self._states[service] = err_state
            return err_state

        if service == "Graph":
            cmd = "connect_graph"
            effective_scopes = tuple(scopes) if scopes is not None else pilot_graph_scopes(self.library_root)
            payload = {
                "tenant_id": tenant_id,
                "expected_account_upn": expected_account_upn,
                "scopes": list(effective_scopes),
                "auth_mode": auth_mode,
                "module": pilot_module_constraint("Microsoft.Graph.Authentication", self.library_root),
            }
        else:
            cmd = "connect_exchange"
            payload = {
                "tenant_id": tenant_id,
                "expected_account_upn": expected_account_upn,
                "organization": organization or tenant_id,
                "auth_mode": auth_mode,
                "module": pilot_module_constraint("ExchangeOnlineManagement", self.library_root),
            }

        resp = worker.send_command(
            cmd,
            payload,
            timeout_seconds=timeout_seconds,
            cancel_event=cancel_event,
            on_event=on_event,
        )

        if resp.get("_host_terminal") in ("CANCELLED", "TIMEOUT"):
            terminal = resp["_host_terminal"]
            err_state = LiveConnectionState(
                service=service,
                state="disconnected" if terminal == "CANCELLED" else "error",
                tenant_id=tenant_id,
                account_upn=expected_account_upn,
                auth_mode=auth_mode,
                session_generation=session_generation,
                warning="Interactive sign-in cancelled." if terminal == "CANCELLED" else "Interactive sign-in timed out.",
                error_code=terminal,
            )
            with self._lock:
                self._states[service] = err_state
            return err_state

        if not resp.get("ok"):
            err_state = LiveConnectionState(
                service=service,
                state="error",
                tenant_id=tenant_id,
                account_upn=expected_account_upn,
                auth_mode=auth_mode,
                session_generation=session_generation,
                warning=str(resp.get("message") or "Live sign-in failed."),
                error_code=str(resp.get("code") or "CONNECTION_FAILED"),
            )
            with self._lock:
                self._states[service] = err_state
            return err_state

        data = resp.get("data") or {}
        actual_tenant = str(data.get("tenant_id") or "").strip().lower()
        actual_upn = str(data.get("account_upn") or "").strip()

        if actual_tenant != tenant_id.strip().lower():
            self.disconnect(service)
            err_state = LiveConnectionState(
                service=service,
                state="error",
                tenant_id=tenant_id,
                account_upn=expected_account_upn,
                auth_mode=auth_mode,
                session_generation=session_generation,
                warning=f"Authenticated tenant '{actual_tenant}' does not match confirmed company tenant '{tenant_id}'.",
                error_code="TENANT_MISMATCH",
            )
            with self._lock:
                self._states[service] = err_state
            return err_state

        if actual_upn.casefold() != expected_account_upn.strip().casefold():
            self.disconnect(service)
            err_state = LiveConnectionState(
                service=service,
                state="error",
                tenant_id=tenant_id,
                account_upn=expected_account_upn,
                auth_mode=auth_mode,
                session_generation=session_generation,
                warning=f"Authenticated account '{actual_upn}' does not match selected admin '{expected_account_upn}'.",
                error_code="ACCOUNT_MISMATCH",
            )
            with self._lock:
                self._states[service] = err_state
            return err_state

        now = _utc_now()
        verified_state = LiveConnectionState(
            service=service,
            state="verified",
            tenant_id=actual_tenant,
            account_upn=actual_upn,
            auth_mode=auth_mode,
            connected_at=now,
            expires_at=now + timedelta(minutes=self.lease_minutes),
            session_generation=session_generation,
            warning=None,
            error_code=None,
            graph_scopes=tuple(str(s) for s in data.get("scopes", []) if s),
            effective_roles=tuple(str(r) for r in data.get("effective_roles", []) if r),
            connection_id=str(uuid4()),
            owner_worker_id=worker.identity.worker_id,
        )
        with self._lock:
            self._states[service] = verified_state
        return verified_state

    def disconnect(self, service: str | None = None) -> None:
        """Disconnect one live service inside the worker, or shut down the whole worker."""
        if service is None:
            self.clear()
            return
        if service not in SERVICES:
            raise ValueError(f"Unsupported M365 service: {service}")

        worker_to_close: M365WorkerHost | None = None
        with self._lock:
            worker = self._worker
            self._states[service] = LiveConnectionState(service=service)
            other_active = any(
                s != service and st.state == "verified"
                for s, st in self._states.items()
            )
            if not other_active and worker is not None:
                worker_to_close = worker
                self._worker = None

        if worker_to_close is not None:
            worker_to_close.shutdown()
        elif worker is not None and worker.is_alive:
            try:
                worker.send_command("disconnect", {"services": [service]}, timeout_seconds=10.0)
            except Exception:
                pass

