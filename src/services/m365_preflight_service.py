"""Preflight environment, PowerShell 7, module, and schema readiness checker for M365."""

from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime, timezone
import json
from pathlib import Path
import re
import shutil
import subprocess
from typing import Callable, Iterable, Optional

from src.services.m365_catalog_service import (
    CONTRACT_ROOT,
    CatalogError,
    ManifestValidator,
    ROOT,
)


LIVE_PILOT_MANIFEST_PATHS: tuple[str, ...] = (
    "entra-id/user-identity/operation.manifest.json",
    "licensing/user-licenses/operation.manifest.json",
    "entra-id/user-signins/operation.manifest.json",
    "exchange-online/mailbox-summary/operation.manifest.json",
)

CORE_AUTH_MODULES: dict[str, tuple[str, str]] = {
    "Microsoft.Graph.Authentication": ("2.0.0", "Host Interactive Graph Sign-In"),
}


def _utc_now() -> str:
    return datetime.now(timezone.utc).isoformat(timespec="seconds").replace("+00:00", "Z")


def parse_semver_tuple(version_text: str) -> tuple[int, ...]:
    """Parse major.minor.patch numeric components cleanly (ignoring prerelease suffix)."""
    if not version_text:
        return ()
    core = version_text.strip().split("-", 1)[0]
    parts = []
    for seg in core.split("."):
        m = re.match(r"^(\d+)", seg)
        if not m:
            break
        parts.append(int(m.group(1)))
    return tuple(parts)


def version_at_least(installed: Optional[str], minimum: str) -> bool:
    """Compare installed SemVer string against minimum requirement numerically."""
    inst_t = parse_semver_tuple(installed or "")
    min_t = parse_semver_tuple(minimum or "")
    if not inst_t or not min_t:
        return False
    max_len = max(len(inst_t), len(min_t))
    inst_padded = inst_t + (0,) * (max_len - len(inst_t))
    min_padded = min_t + (0,) * (max_len - len(min_t))
    return inst_padded >= min_padded


@dataclass(frozen=True)
class ModuleCheck:
    name: str
    minimum_version: str
    installed_version: Optional[str]
    satisfied: bool
    install_command: str
    required_by: tuple[str, ...]


@dataclass(frozen=True)
class PreflightReport:
    checked_at: str
    pwsh_path: str
    pwsh_version: Optional[str]
    pwsh_edition: Optional[str]
    pwsh_ok: bool
    schemas_ok: bool
    schema_errors: tuple[str, ...]
    module_checks: tuple[ModuleCheck, ...]
    modules_ok: bool
    live_ready: bool
    remediation_commands: tuple[str, ...]
    error_code: Optional[str]
    summary: str


class M365PreflightService:
    """Checks PowerShell 7 runtime, pinned contract schemas, and required M365 modules cleanly."""

    def __init__(
        self,
        *,
        pwsh_path: Optional[Path] = None,
        library_root: Optional[Path] = None,
        metadata_root: Optional[Path] = None,
        contract_root: Optional[Path] = None,
        pilot_manifests: Optional[Iterable[str]] = None,
        probe_runner: Optional[Callable[[Path, tuple[str, ...]], dict]] = None,
    ):
        self.library_root = Path(library_root) if library_root else ROOT / "scripts/m365"
        self.metadata_root = Path(metadata_root) if metadata_root else ROOT / "assets/m365"
        self.contract_root = Path(contract_root) if contract_root else CONTRACT_ROOT
        self.pilot_manifests = tuple(pilot_manifests) if pilot_manifests is not None else LIVE_PILOT_MANIFEST_PATHS
        self.pwsh_path = self._discover_pwsh(pwsh_path)
        self._probe_runner = probe_runner or self._run_pwsh_probe

    @staticmethod
    def _discover_pwsh(explicit: Optional[Path]) -> Path:
        if explicit is not None:
            return Path(explicit)
        found = shutil.which("pwsh")
        if found:
            return Path(found)
        anchor_path = ROOT / "prototypes/m365_official_engine/trust-anchor.json"
        if anchor_path.is_file():
            try:
                anchor = json.loads(anchor_path.read_text(encoding="utf-8"))
                candidate = Path(anchor["powershell"]["path"])
                if candidate.is_file():
                    return candidate
            except Exception:
                pass
        return Path("C:/Program Files/PowerShell/7/pwsh.exe")

    def collect_module_requirements(self) -> tuple[str, dict[str, tuple[str, list[str]]]]:
        """Read minimum PS version and module requirements directly from manifests."""
        min_ps = "7.0.0"
        reqs: dict[str, tuple[str, list[str]]] = {}
        for mod_name, (min_ver, owner) in CORE_AUTH_MODULES.items():
            reqs[mod_name] = (min_ver, [owner])

        for rel in self.pilot_manifests:
            manifest_path = self.library_root / rel
            if not manifest_path.is_file():
                continue
            manifest = json.loads(manifest_path.read_text(encoding="utf-8"))
            ps_req = manifest.get("supported_powershell", {})
            ps_min = ps_req.get("minimum_version", "7.0.0")
            if not version_at_least(min_ps, ps_min):
                min_ps = ps_min
            script_id = manifest.get("script_id", rel)
            for mod in manifest.get("required_modules", []):
                name = str(mod["name"])
                ver = str(mod.get("minimum_version", "0.0.0"))
                if name not in reqs:
                    reqs[name] = (ver, [script_id])
                else:
                    existing_ver, owners = reqs[name]
                    best_ver = ver if not version_at_least(existing_ver, ver) else existing_ver
                    if script_id not in owners:
                        owners.append(script_id)
                    reqs[name] = (best_ver, owners)
        return min_ps, reqs

    @staticmethod
    def _run_pwsh_probe(pwsh_path: Path, module_names: tuple[str, ...]) -> dict:
        if not pwsh_path.is_file():
            return {"pwsh_found": False}

        names_json = json.dumps(list(module_names))
        probe_ps = (
            "$ErrorActionPreference = 'Stop'; "
            f"$names = ConvertFrom-Json -InputObject '{names_json}'; "
            "$mods = @{}; "
            "foreach ($n in $names) { "
            "  $best = Get-Module -ListAvailable -Name $n | Sort-Object Version -Descending | Select-Object -First 1; "
            "  $mods[$n] = if ($null -ne $best) { $best.Version.ToString() } else { $null } "
            "}; "
            "$out = [pscustomobject]@{ "
            "  pwsh_found = $true; "
            "  version = $PSVersionTable.PSVersion.ToString(); "
            "  edition = [string]$PSVersionTable.PSEdition; "
            "  modules = $mods "
            "}; "
            "[Console]::Out.WriteLine((ConvertTo-Json -InputObject $out -Depth 5 -Compress))"
        )
        creationflags = getattr(subprocess, "CREATE_NO_WINDOW", 0)
        proc = subprocess.run(
            [str(pwsh_path), "-NoLogo", "-NoProfile", "-NonInteractive", "-Command", probe_ps],
            capture_output=True,
            text=True,
            encoding="utf-8",
            timeout=20,
            creationflags=creationflags,
        )
        if proc.returncode != 0 or not proc.stdout.strip():
            raise RuntimeError(proc.stderr.strip() or "PowerShell preflight probe failed.")
        lines = [ln.strip() for ln in proc.stdout.splitlines() if ln.strip()]
        return json.loads(lines[-1])

    def run_check(self) -> PreflightReport:
        """Execute a complete non-destructive readiness check for live M365 operations."""
        min_ps, reqs = self.collect_module_requirements()
        schema_errors: list[str] = []
        try:
            ManifestValidator(self.contract_root, self.metadata_root / "contract-review-pins.json")
            schemas_ok = True
        except (CatalogError, OSError, ValueError) as exc:
            schemas_ok = False
            schema_errors.append(str(exc))

        probe: dict = {}
        pwsh_version: Optional[str] = None
        pwsh_edition: Optional[str] = None
        pwsh_ok = False
        probe_err: Optional[str] = None
        try:
            probe = self._probe_runner(self.pwsh_path, tuple(reqs.keys()))
            if probe.get("pwsh_found"):
                pwsh_version = probe.get("version")
                pwsh_edition = probe.get("edition")
                pwsh_ok = (pwsh_edition == "Core") and version_at_least(pwsh_version, min_ps)
        except Exception as exc:
            probe_err = str(exc)

        installed_map = probe.get("modules", {}) if isinstance(probe.get("modules"), dict) else {}
        checks: list[ModuleCheck] = []
        remediation: list[str] = []

        if not pwsh_ok:
            remediation.append("winget install --id Microsoft.PowerShell --source winget")

        for mod_name in sorted(reqs.keys()):
            min_ver, owners = reqs[mod_name]
            inst_ver = installed_map.get(mod_name)
            satisfied = pwsh_ok and version_at_least(inst_ver, min_ver)
            install_cmd = f"Install-Module {mod_name} -MinimumVersion {min_ver} -Scope CurrentUser -Repository PSGallery"
            if not satisfied:
                remediation.append(install_cmd)
            checks.append(
                ModuleCheck(
                    name=mod_name,
                    minimum_version=min_ver,
                    installed_version=inst_ver,
                    satisfied=satisfied,
                    install_command=install_cmd,
                    required_by=tuple(owners),
                )
            )

        modules_ok = all(c.satisfied for c in checks)
        live_ready = pwsh_ok and schemas_ok and modules_ok

        if live_ready:
            error_code = None
            summary = f"Live Readiness OK — PowerShell {pwsh_version} ({pwsh_edition}), {len(checks)}/{len(checks)} modules & pinned schemas verified."
        elif not schemas_ok:
            error_code = "CONTRACT_VIOLATION"
            summary = f"Schema pin validation failed: {schema_errors[0]}"
        elif not pwsh_ok:
            error_code = "PS_VERSION_UNSUPPORTED"
            summary = probe_err or f"PowerShell 7+ Core unavailable at '{self.pwsh_path}'."
        else:
            missing_names = [c.name for c in checks if not c.satisfied]
            error_code = "MODULE_MISSING"
            summary = f"Missing or outdated M365 PowerShell modules: {', '.join(missing_names)}."

        return PreflightReport(
            checked_at=_utc_now(),
            pwsh_path=str(self.pwsh_path),
            pwsh_version=pwsh_version,
            pwsh_edition=pwsh_edition,
            pwsh_ok=pwsh_ok,
            schemas_ok=schemas_ok,
            schema_errors=tuple(schema_errors),
            module_checks=tuple(checks),
            modules_ok=modules_ok,
            live_ready=live_ready,
            remediation_commands=tuple(remediation),
            error_code=error_code,
            summary=summary,
        )

