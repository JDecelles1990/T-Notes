"""PROVISIONAL Windows-only owned processes and pinned trusted files.

A job is assigned while the worker is suspended, before worker code executes.
This is process ownership and cleanup, not a sandbox for hostile executable code.
"""
from __future__ import annotations
import ctypes as C
from ctypes import wintypes as W
from dataclasses import dataclass, field
import hashlib
import os
from pathlib import Path
import queue
import re
import subprocess
import threading
import time


class ProcessError(Exception):
    pass


if os.name == "nt":
    K = C.WinDLL("kernel32", use_last_error=True)
    def api(name, args, result=W.BOOL):
        fn = getattr(K, name)
        fn.argtypes, fn.restype = args, result
        return fn
    close = api("CloseHandle", [W.HANDLE])
    create_file = api("CreateFileW", [W.LPCWSTR, W.DWORD, W.DWORD, C.c_void_p, W.DWORD, W.DWORD, W.HANDLE], W.HANDLE)
    final_name = api("GetFinalPathNameByHandleW", [W.HANDLE, W.LPWSTR, W.DWORD, W.DWORD], W.DWORD)
    create_job = api("CreateJobObjectW", [C.c_void_p, W.LPCWSTR], W.HANDLE)
    set_job = api("SetInformationJobObject", [W.HANDLE, C.c_int, C.c_void_p, W.DWORD])
    assign_job = api("AssignProcessToJobObject", [W.HANDLE, W.HANDLE])
    terminate_job = api("TerminateJobObject", [W.HANDLE, W.UINT])
    query_job = api("QueryInformationJobObject", [W.HANDLE, C.c_int, C.c_void_p, W.DWORD, C.c_void_p])
    snapshot_threads = api("CreateToolhelp32Snapshot", [W.DWORD, W.DWORD], W.HANDLE)
    first_thread = api("Thread32First", [W.HANDLE, C.c_void_p])
    next_thread = api("Thread32Next", [W.HANDLE, C.c_void_p])
    open_thread = api("OpenThread", [W.DWORD, W.BOOL, W.DWORD], W.HANDLE)
    resume_thread = api("ResumeThread", [W.HANDLE], W.DWORD)
    get_info = api("GetFileInformationByHandleEx", [W.HANDLE, C.c_int, C.c_void_p, W.DWORD])

    class Limits(C.Structure):
        _fields_ = [("per_process", C.c_int64), ("per_job", C.c_int64),
                    ("flags", W.DWORD), ("min_working", C.c_size_t),
                    ("max_working", C.c_size_t), ("active_limit", W.DWORD),
                    ("affinity", C.c_size_t), ("priority", W.DWORD), ("scheduling", W.DWORD)]
    class IO(C.Structure):
        _fields_ = [(name, C.c_uint64) for name in ("ro", "wo", "oo", "rb", "wb", "ob")]
    class ExtendedLimits(C.Structure):
        _fields_ = [("basic", Limits), ("io", IO), ("process_memory", C.c_size_t),
                    ("job_memory", C.c_size_t), ("peak_process", C.c_size_t), ("peak_job", C.c_size_t)]
    class Accounting(C.Structure):
        _fields_ = [("user", C.c_int64), ("kernel", C.c_int64), ("period_user", C.c_int64),
                    ("period_kernel", C.c_int64), ("faults", W.DWORD), ("total", W.DWORD),
                    ("active", W.DWORD), ("terminated", W.DWORD)]
    class ThreadEntry(C.Structure):
        _fields_ = [("size", W.DWORD), ("usage", W.DWORD), ("tid", W.DWORD),
                    ("pid", W.DWORD), ("base", W.LONG), ("delta", W.LONG), ("flags", W.DWORD)]


def check(ok):
    if not ok:
        raise ProcessError("Windows ownership or file-pinning operation failed")
    return ok


class PinnedFiles:
    """Pins ancestors against rename and files against writes/deletion."""
    def __init__(self):
        if os.name != "nt":
            raise ProcessError("Windows containment required; other platforms unsupported")
        self.handles, self.seen = [], set()

    def pin(self, path: Path, expected_sha256: str | None = None):
        if not isinstance(expected_sha256, str) or not re.fullmatch(r"[0-9a-f]{64}", expected_sha256):
            raise ProcessError("A complete explicit SHA-256 trust identity is required")
        path = Path(os.path.abspath(path))
        for current in [*reversed(path.parents), path]:
            key = os.path.normcase(str(current))
            if key in self.seen:
                continue
            directory = current != path
            handle = create_file(str(current), 0x80 if directory else 0x80000000,
                                 3 if directory else 1, None, 3,
                                 0x00200000 | (0x02000000 if directory else 0), None)
            if handle == C.c_void_p(-1).value:
                raise ProcessError("Trusted file unavailable or cannot be pinned")
            self.handles.append(handle)
            attrs = (W.DWORD * 2)()
            check(get_info(handle, 9, C.byref(attrs), C.sizeof(attrs)))
            if attrs[0] & 0x400:
                raise ProcessError("Reparse points are unsupported for trusted paths")
            buf = C.create_unicode_buffer(32768)
            size = final_name(handle, buf, len(buf), 0)
            check(size and size < len(buf))
            actual = buf.value.removeprefix("\\\\?\\")
            if os.path.normcase(os.path.abspath(actual)) != key:
                raise ProcessError("Trusted path resolved to a different object")
            self.seen.add(key)
        if hashlib.sha256(path.read_bytes()).hexdigest() != expected_sha256:
            raise ProcessError("Pinned content hash mismatch")
        return path

    def close(self):
        for handle in reversed(self.handles):
            close(handle)
        self.handles.clear()

    def __enter__(self):
        return self

    def __exit__(self, *_):
        self.close()


class Job:
    def __init__(self):
        self.handle = check(create_job(None, None))
        limits = ExtendedLimits()
        limits.basic.flags = 0x2000  # KILL_ON_JOB_CLOSE; no breakaway flags.
        try:
            check(set_job(self.handle, 9, C.byref(limits), C.sizeof(limits)))
        except Exception:
            self.close()
            raise

    def assign_and_resume(self, process):
        check(assign_job(self.handle, int(process._handle)))
        snapshot = snapshot_threads(4, 0)
        if snapshot == C.c_void_p(-1).value:
            raise ProcessError("Cannot identify suspended owned process thread")
        try:
            entry = ThreadEntry()
            entry.size = C.sizeof(entry)
            found, more = [], first_thread(snapshot, C.byref(entry))
            while more:
                if entry.pid == process.pid:
                    found.append(entry.tid)
                more = next_thread(snapshot, C.byref(entry))
            if len(found) != 1:
                raise ProcessError("Unexpected thread state before worker start")
            thread = check(open_thread(2, False, found[0]))
            try:
                check(resume_thread(thread) != 0xFFFFFFFF)
            finally:
                close(thread)
        finally:
            close(snapshot)

    def active(self):
        accounting = Accounting()
        check(query_job(self.handle, 1, C.byref(accounting), C.sizeof(accounting), None))
        return accounting.active

    def terminate(self):
        check(terminate_job(self.handle, 40))

    def close(self):
        if self.handle:
            close(self.handle)
            self.handle = None


@dataclass
class Capture:
    stdout: bytes = b""
    stderr_bytes: int = 0
    process_exit: int | None = None
    terminal: str | None = None
    worker_pid: int | None = None
    max_job_active: int = 0
    final_job_active: int | None = None
    control_sent: bool = False
    forced: bool = False
    elapsed_ms: int = 0
    states: list[str] = field(default_factory=list)


def run_owned(argv, payload, *, timeout, cancel=None, control=None,
              framed=False, stdout_limit=1048576, stderr_limit=65536, cwd=None, on_started=None):
    """Bounded capture. Stderr content and OS exception messages are never retained."""
    if os.name != "nt":
        raise ProcessError("Windows-only runner")
    capture = Capture(states=["starting"])
    job, process = Job(), None
    events, halt, threads = queue.Queue(maxsize=32), threading.Event(), []
    writes = queue.Queue(maxsize=4)
    begun = time.monotonic()
    deadline, stop_deadline = begun + timeout, None
    closed_input, eof = False, set()

    def reader(name, stream):
        try:
            while not halt.is_set():
                chunk = stream.read(4096)
                while not halt.is_set():
                    try:
                        events.put((name, chunk), timeout=0.05)
                        break
                    except queue.Full:
                        pass
                if not chunk:
                    break
        except OSError:
            pass

    def close_input():
        nonlocal closed_input
        if not closed_input:
            closed_input = True
            try:
                process.stdin.close()
            except OSError:
                pass

    def writer():
        try:
            while not halt.is_set():
                try:
                    data = writes.get(timeout=0.05)
                except queue.Empty:
                    continue
                if data is None:
                    close_input()
                    return
                offset = 0
                while offset < len(data) and not halt.is_set():
                    count = process.stdin.write(data[offset:])
                    if not count:
                        return
                    offset += count
                process.stdin.flush()
        except (OSError, ValueError):
            pass

    try:
        environment = {k: os.environ[k] for k in ("SystemRoot", "WINDIR", "TEMP", "TMP") if k in os.environ}
        environment.update(PSModulePath="", POWERSHELL_TELEMETRY_OPTOUT="1", POWERSHELL_UPDATECHECK="Off")
        process = subprocess.Popen(argv, stdin=subprocess.PIPE, stdout=subprocess.PIPE,
                                   stderr=subprocess.PIPE, shell=False, bufsize=0,
                                   creationflags=0x08000000 | 0x4, env=environment, cwd=cwd)
        capture.worker_pid = process.pid
        job.assign_and_resume(process)
        capture.states.append("running")
        for name, stream in (("stdout", process.stdout), ("stderr", process.stderr)):
            thread = threading.Thread(target=reader, args=(name, stream), daemon=True)
            thread.start()
            threads.append(thread)
        thread = threading.Thread(target=writer, daemon=True)
        thread.start()
        threads.append(thread)
        writes.put_nowait(payload)
        if not framed:
            writes.put_nowait(None)
        if on_started:
            on_started()
        while True:
            now, active = time.monotonic(), job.active()
            capture.max_job_active = max(capture.max_job_active, active)
            if capture.terminal is None and ((cancel and cancel.is_set()) or now >= deadline):
                capture.terminal = "CANCELLED" if cancel and cancel.is_set() else "TIMEOUT"
                capture.states.append("cancelling")
                stop_deadline = now + 5.0
                if control and not closed_input:
                    try:
                        writes.put_nowait(control(capture.terminal))
                        capture.control_sent = True
                    except queue.Full:
                        pass
            if stop_deadline is not None and now >= stop_deadline and active:
                job.terminate()
                capture.forced, stop_deadline = True, None
            try:
                name, chunk = events.get(timeout=0.01)
                if not chunk:
                    eof.add(name)
                elif name == "stderr":
                    capture.stderr_bytes += len(chunk)
                    if capture.stderr_bytes > stderr_limit and capture.terminal is None:
                        capture.terminal = "OUTPUT_LIMIT"
                        job.terminate()
                        capture.forced = True
                elif len(capture.stdout) + len(chunk) > stdout_limit:
                    if capture.terminal is None:
                        capture.terminal = "OUTPUT_LIMIT"
                    job.terminate()
                    capture.forced = True
                else:
                    capture.stdout += chunk
                    if framed and b"\n" in capture.stdout and not closed_input:
                        try:
                            writes.put_nowait(None)
                        except queue.Full:
                            pass
            except queue.Empty:
                pass
            if process.poll() is not None:
                close_input()
                if job.active():
                    job.terminate()
                    capture.forced = True
                if len(eof) == 2:
                    break
            if time.monotonic() > deadline + 7:
                raise ProcessError("Owned process did not drain within cleanup bound")
        capture.process_exit = process.wait(timeout=1)
        for _ in range(100):
            if job.active() == 0:
                break
            time.sleep(0.01)
        capture.final_job_active = job.active()
        if capture.final_job_active != 0:
            raise ProcessError("Owned process cleanup could not be verified")
        capture.elapsed_ms = int((time.monotonic() - begun) * 1000)
        capture.states.append("completed")
        return capture
    finally:
        if process is not None and process.poll() is None:
            process.kill()  # Includes assignment failure: still the suspended owned PID.
        job.close()
        halt.set()
        if process is not None:
            try:
                process.wait(timeout=2)
            except subprocess.TimeoutExpired:
                pass
            for stream in (process.stdin, process.stdout, process.stderr):
                if stream:
                    try:
                        stream.close()
                    except OSError:
                        pass
        for thread in threads:
            thread.join(timeout=1)
