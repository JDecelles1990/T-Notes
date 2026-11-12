"""Persistent isolated PowerShell 7 worker host process manager."""

from __future__ import annotations

import ctypes
from dataclasses import dataclass
import json
from pathlib import Path
import queue
import shutil
import subprocess
import sys
import threading
import time
from typing import Any, Callable
from uuid import uuid4


ROOT = Path(__file__).resolve().parents[2]
DEFAULT_HOST_SCRIPT = ROOT / "scripts/m365/_host/M365WorkerHost.ps1"
MAX_FRAME_BYTES = 1024 * 1024  # 1 MiB per JSON protocol line
MAX_STDERR_BYTES = 64 * 1024


class _JOBOBJECT_BASIC_LIMIT_INFORMATION(ctypes.Structure):
    _fields_ = [
        ("PerProcessUserTimeLimit", ctypes.c_int64),
        ("PerJobUserTimeLimit", ctypes.c_int64),
        ("LimitFlags", ctypes.c_uint32),
        ("MinimumWorkingSetSize", ctypes.c_size_t),
        ("MaximumWorkingSetSize", ctypes.c_size_t),
        ("ActiveProcessLimit", ctypes.c_uint32),
        ("Affinity", ctypes.c_size_t),
        ("PriorityClass", ctypes.c_uint32),
        ("SchedulingClass", ctypes.c_uint32),
    ]


class _IO_COUNTERS(ctypes.Structure):
    _fields_ = [
        ("ReadOperationCount", ctypes.c_uint64),
        ("WriteOperationCount", ctypes.c_uint64),
        ("OtherOperationCount", ctypes.c_uint64),
        ("ReadTransferCount", ctypes.c_uint64),
        ("WriteTransferCount", ctypes.c_uint64),
        ("OtherTransferCount", ctypes.c_uint64),
    ]


class _JOBOBJECT_EXTENDED_LIMIT_INFORMATION(ctypes.Structure):
    _fields_ = [
        ("BasicLimitInformation", _JOBOBJECT_BASIC_LIMIT_INFORMATION),
        ("IoInfo", _IO_COUNTERS),
        ("ProcessMemoryLimit", ctypes.c_size_t),
        ("JobMemoryLimit", ctypes.c_size_t),
        ("PeakProcessMemoryUsed", ctypes.c_size_t),
        ("PeakJobMemoryUsed", ctypes.c_size_t),
    ]


_JOB_OBJECT_LIMIT_KILL_ON_JOB_CLOSE = 0x00002000
_JOB_OBJECT_EXTENDED_LIMIT_INFORMATION = 9


class _WinJobGuard:
    """Owns a Windows Job Object with KILL_ON_JOB_CLOSE for child cleanup."""

    def __init__(self) -> None:
        self._handle: int | None = None
        if sys.platform != "win32":
            return
        kernel32 = ctypes.windll.kernel32
        handle = kernel32.CreateJobObjectW(None, None)
        if not handle:
            return
        info = _JOBOBJECT_EXTENDED_LIMIT_INFORMATION()
        info.BasicLimitInformation.LimitFlags = _JOB_OBJECT_LIMIT_KILL_ON_JOB_CLOSE
        ok = kernel32.SetInformationJobObject(
            ctypes.c_void_p(handle),
            _JOB_OBJECT_EXTENDED_LIMIT_INFORMATION,
            ctypes.byref(info),
            ctypes.sizeof(info),
        )
        if not ok:
            kernel32.CloseHandle(ctypes.c_void_p(handle))
            return
        self._handle = int(handle)

    def assign(self, process_handle: int | None) -> bool:
        if sys.platform != "win32" or not self._handle or not process_handle:
            return False
        kernel32 = ctypes.windll.kernel32
        return bool(
            kernel32.AssignProcessToJobObject(
                ctypes.c_void_p(self._handle),
                ctypes.c_void_p(int(process_handle)),
            )
        )

    def terminate_and_close(self) -> None:
        if sys.platform != "win32" or not self._handle:
            return
        kernel32 = ctypes.windll.kernel32
        try:
            kernel32.TerminateJobObject(ctypes.c_void_p(self._handle), 1)
        except Exception:
            pass
        try:
            kernel32.CloseHandle(ctypes.c_void_p(self._handle))
        finally:
            self._handle = None


@dataclass(frozen=True)
class WorkerIdentity:
    """Tracks the bound company/admin context that owns a persistent worker."""

    worker_id: str
    company_id: str
    tenant_id: str
    admin_identity_ref: str
    session_generation: int


class M365WorkerHostError(RuntimeError):
    """Raised when the persistent PowerShell host cannot start or communicate."""

    def __init__(self, code: str, message: str) -> None:
        super().__init__(message)
        self.code = code
        self.message = message


def discover_pwsh(explicit: Path | None = None) -> Path | None:
    """Locate PowerShell 7 (`pwsh.exe` / `pwsh`)."""
    if explicit is not None:
        p = Path(explicit)
        return p if p.is_file() else None
    found = shutil.which("pwsh")
    if found:
        return Path(found)
    candidate = Path("C:/Program Files/PowerShell/7/pwsh.exe")
    return candidate if candidate.is_file() else None


class M365WorkerHost:
    """Manages one persistent `pwsh` process bound to an active M365 context."""

    def __init__(
        self,
        identity: WorkerIdentity,
        *,
        pwsh_path: Path | None = None,
        host_script: Path | None = None,
        startup_timeout_seconds: float = 15.0,
    ) -> None:
        self.identity = identity
        resolved_pwsh = discover_pwsh(pwsh_path)
        if resolved_pwsh is None or not resolved_pwsh.is_file():
            raise M365WorkerHostError(
                "PS_VERSION_UNSUPPORTED",
                "PowerShell 7 (pwsh) could not be found on this workstation.",
            )
        self.pwsh_path = resolved_pwsh
        self.host_script = Path(host_script) if host_script is not None else DEFAULT_HOST_SCRIPT
        if not self.host_script.is_file():
            raise M365WorkerHostError(
                "CONTRACT_VIOLATION",
                f"Worker host script missing: {self.host_script}",
            )
        self.startup_timeout_seconds = startup_timeout_seconds

        self._job = _WinJobGuard()
        self._proc: subprocess.Popen | None = None
        self._stdout_thread: threading.Thread | None = None
        self._stderr_thread: threading.Thread | None = None
        self._stderr_tail = bytearray()

        self._request_lock = threading.Lock()
        self._state_lock = threading.Lock()
        self._ready_event = threading.Event()
        self._closed_event = threading.Event()
        self._responses: dict[str, queue.Queue[dict[str, Any]]] = {}
        self._event_callbacks: dict[str, Callable[[dict[str, Any]], None]] = {}
        self._global_event_callback: Callable[[dict[str, Any]], None] | None = None
        self._closed = False
        self._pid: int | None = None

    @property
    def is_alive(self) -> bool:
        return (
            not self._closed
            and self._proc is not None
            and self._proc.poll() is None
            and not self._closed_event.is_set()
        )

    @property
    def pid(self) -> int | None:
        return self._pid

    def start(self) -> None:
        """Spawn the persistent PowerShell 7 worker and wait for the ready frame."""
        if self._closed:
            raise M365WorkerHostError("WORKER_CRASHED", "Worker host is already closed.")
        if self.is_alive:
            return

        creationflags = getattr(subprocess, "CREATE_NO_WINDOW", 0)
        self._proc = subprocess.Popen(
            [
                str(self.pwsh_path),
                "-NoLogo",
                "-NoProfile",
                "-NonInteractive",
                "-File",
                str(self.host_script),
            ],
            stdin=subprocess.PIPE,
            stdout=subprocess.PIPE,
            stderr=subprocess.PIPE,
            cwd=str(self.host_script.parent),
            creationflags=creationflags,
            bufsize=0,
        )
        self._pid = self._proc.pid
        self._job.assign(getattr(self._proc, "_handle", None))

        self._stdout_thread = threading.Thread(
            target=self._read_stdout_loop,
            name=f"m365-worker-out-{self._proc.pid}",
            daemon=True,
        )
        self._stderr_thread = threading.Thread(
            target=self._read_stderr_loop,
            name=f"m365-worker-err-{self._proc.pid}",
            daemon=True,
        )
        self._stdout_thread.start()
        self._stderr_thread.start()

        deadline = time.monotonic() + self.startup_timeout_seconds
        while time.monotonic() < deadline:
            if self._ready_event.is_set():
                return
            if self._closed_event.is_set() or self._proc.poll() is not None:
                self.shutdown(force=True)
                raise M365WorkerHostError(
                    "WORKER_CRASHED",
                    "Persistent PowerShell worker exited before sending ready frame.",
                )
            time.sleep(0.02)

        self.shutdown(force=True)
        raise M365WorkerHostError(
            "TIMEOUT",
            "Timed out waiting for persistent PowerShell worker startup.",
        )

    def _read_stdout_loop(self) -> None:
        proc = self._proc
        assert proc is not None and proc.stdout is not None
        try:
            while True:
                raw_line = proc.stdout.readline(MAX_FRAME_BYTES + 1)
                if not raw_line:
                    break
                if len(raw_line) > MAX_FRAME_BYTES:
                    self._dispatch_oversize_error()
                    break
                text = raw_line.decode("utf-8", errors="replace").strip()
                if not text:
                    continue
                try:
                    frame = json.loads(text)
                except ValueError:
                    continue
                if not isinstance(frame, dict):
                    continue

                frame_type = frame.get("type")
                if frame_type == "event":
                    if frame.get("event") == "ready":
                        self._ready_event.set()
                        continue
                    self._dispatch_event(frame)
                elif frame_type == "response":
                    req_id = str(frame.get("id") or "")
                    with self._state_lock:
                        resp_q = self._responses.get(req_id)
                    if resp_q is not None:
                        resp_q.put(frame)
        finally:
            self._closed_event.set()
            with self._state_lock:
                for resp_q in self._responses.values():
                    resp_q.put({"type": "response", "ok": False, "_eof": True})

    def _read_stderr_loop(self) -> None:
        proc = self._proc
        assert proc is not None and proc.stderr is not None
        try:
            while True:
                chunk = proc.stderr.read(4096)
                if not chunk:
                    break
                if len(self._stderr_tail) < MAX_STDERR_BYTES:
                    remaining = MAX_STDERR_BYTES - len(self._stderr_tail)
                    self._stderr_tail.extend(chunk[:remaining])
        except Exception:
            pass

    def _dispatch_oversize_error(self) -> None:
        with self._state_lock:
            for resp_q in self._responses.values():
                resp_q.put(
                    {
                        "type": "response",
                        "ok": False,
                        "code": "OUTPUT_LIMIT",
                        "message": "PowerShell worker output exceeded allowed size.",
                    }
                )

    def _dispatch_event(self, frame: dict[str, Any]) -> None:
        req_id = str(frame.get("request_id") or "")
        cb = None
        with self._state_lock:
            if req_id:
                cb = self._event_callbacks.get(req_id)
            if cb is None:
                cb = self._global_event_callback
        if cb is not None:
            try:
                cb(frame)
            except Exception:
                pass

    def send_command(
        self,
        cmd: str,
        payload: dict[str, Any] | None = None,
        *,
        timeout_seconds: float = 90.0,
        cancel_event: threading.Event | None = None,
        on_event: Callable[[dict[str, Any]], None] | None = None,
    ) -> dict[str, Any]:
        """Send one structured JSON command to the running worker and wait for its response."""
        with self._request_lock:
            if not self.is_alive:
                self.start()

            req_id = str(uuid4())
            resp_q: queue.Queue[dict[str, Any]] = queue.Queue(maxsize=4)
            with self._state_lock:
                self._responses[req_id] = resp_q
                if on_event is not None:
                    self._event_callbacks[req_id] = on_event

            frame = {"cmd": cmd, "id": req_id}
            if payload:
                frame.update(payload)

            try:
                self._write_frame(frame)
                deadline = time.monotonic() + float(timeout_seconds)
                cancel_sent = False
                cancel_grace_deadline: float | None = None

                while True:
                    now = time.monotonic()
                    if cancel_event is not None and cancel_event.is_set():
                        if not cancel_sent:
                            cancel_sent = True
                            cancel_grace_deadline = now + 1.5
                            try:
                                self._write_frame({"cmd": "cancel", "target_id": req_id})
                            except Exception:
                                pass
                        elif cancel_grace_deadline is not None and now >= cancel_grace_deadline:
                            self.shutdown(force=True)
                            return {"_host_terminal": "CANCELLED"}

                    if now >= deadline:
                        self.shutdown(force=True)
                        return {"_host_terminal": "TIMEOUT"}

                    try:
                        resp = resp_q.get(timeout=0.05)
                    except queue.Empty:
                        if self._closed_event.is_set() or (self._proc and self._proc.poll() is not None):
                            return {
                                "ok": False,
                                "code": "CONNECTION_FAILED",
                                "message": "PowerShell worker terminated unexpectedly.",
                            }
                        continue

                    if resp.get("_eof"):
                        if cancel_sent or (cancel_event is not None and cancel_event.is_set()):
                            return {"_host_terminal": "CANCELLED"}
                        return {
                            "ok": False,
                            "code": "CONNECTION_FAILED",
                            "message": "PowerShell worker closed before returning a response.",
                        }
                    return resp
            finally:
                with self._state_lock:
                    self._responses.pop(req_id, None)
                    self._event_callbacks.pop(req_id, None)

    def _write_frame(self, frame: dict[str, Any]) -> None:
        proc = self._proc
        if proc is None or proc.stdin is None or proc.poll() is not None:
            raise M365WorkerHostError("CONNECTION_FAILED", "Worker stdin pipe is unavailable.")
        raw = (json.dumps(frame, ensure_ascii=False, separators=(",", ":")) + "\n").encode("utf-8")
        proc.stdin.write(raw)
        proc.stdin.flush()

    def shutdown(self, *, force: bool = False) -> None:
        """Stop the persistent worker synchronously and terminate any child processes in its job."""
        self._closed = True
        proc = self._proc
        if proc is not None and proc.poll() is None:
            if not force and proc.stdin is not None:
                try:
                    self._write_frame({"cmd": "shutdown", "id": str(uuid4())})
                    proc.wait(timeout=2.0)
                except Exception:
                    pass
            if proc.poll() is None:
                try:
                    proc.kill()
                    proc.wait(timeout=3.0)
                except Exception:
                    pass
        self._job.terminate_and_close()
        self._closed_event.set()
        if proc is not None:
            for stream in (proc.stdin, proc.stdout, proc.stderr):
                if stream is not None:
                    try:
                        stream.close()
                    except Exception:
                        pass
        self._proc = None

