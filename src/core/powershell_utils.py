"""Shared Windows-safe PowerShell 7 subprocess helpers."""

from __future__ import annotations

import os
from pathlib import Path
import subprocess
import sys
from typing import Any


def build_powershell_file_command(
    pwsh_path: Path | str,
    script_path: Path | str,
    extra_args: tuple[str, ...] = (),
) -> list[str]:
    """Builds a PowerShell 7 CLI invocation executing a bundled .ps1 file cleanly."""
    return [
        str(pwsh_path),
        "-NoLogo",
        "-NoProfile",
        "-NonInteractive",
        "-ExecutionPolicy",
        "Bypass",
        "-File",
        str(script_path),
        *extra_args,
    ]


def hidden_subprocess_kwargs() -> dict[str, Any]:
    """Returns subprocess kwargs suppressing flashing console windows on Windows."""
    if sys.platform != "win32":
        return {}
    kwargs: dict[str, Any] = {
        "creationflags": getattr(subprocess, "CREATE_NO_WINDOW", 0),
    }
    startupinfo_cls = getattr(subprocess, "STARTUPINFO", None)
    if startupinfo_cls is not None:
        si = startupinfo_cls()
        si.dwFlags |= getattr(subprocess, "STARTF_USESHOWWINDOW", 0)
        si.wShowWindow = getattr(subprocess, "SW_HIDE", 0)
        kwargs["startupinfo"] = si
    return kwargs
