"""Preserve every actual test attempt with safe diagnostics and exact command."""
from __future__ import annotations
import argparse
from datetime import datetime, timezone
import hashlib
import json
import os
from pathlib import Path
import sys
import tempfile
import time
import traceback
import unittest
import uuid

ROOT = Path(__file__).resolve().parent
if not __package__:
    sys.path.insert(0, str(ROOT.parents[1]))
    __package__ = "prototypes.m365_official_engine"
from .tests.test_engine import EngineTests


def utc():
    return datetime.now(timezone.utc).isoformat().replace("+00:00", "Z")


class EvidenceResult(unittest.TestResult):
    def __init__(self):
        super().__init__()
        self.rows = []

    def startTest(self, test):
        super().startTest(test)
        self.begun = time.monotonic()

    def record(self, test, status, error=None):
        row = {"test": test.id(), "result": status, "elapsed_ms": int((time.monotonic()-self.begun)*1000)}
        execution = getattr(test, "last_execution", None)
        if execution:
            row["execution"] = {"error_code": execution.error_code, "process_exit_code": execution.process_exit_code,
                                "logical_exit_code": execution.logical_exit_code, "telemetry": execution.telemetry}
        if error:
            row["exception_type"] = error[0].__name__
            row["locations"] = [{"file": frame.filename, "line": frame.lineno} for frame in traceback.extract_tb(error[2])]
        self.rows.append(row)
        print(status + " " + test.id(), flush=True)

    def addSuccess(self, test):
        super().addSuccess(test); self.record(test, "PASS")

    def addFailure(self, test, err):
        super().addFailure(test, err); self.record(test, "FAIL", err)

    def addError(self, test, err):
        super().addError(test, err); self.record(test, "FAIL", err)


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--case", action="append", help="Method name, e.g. test_success; default runs the full suite")
    parser.add_argument("--output-dir", help="Directory to write test evidence report; defaults to isolated temporary directory")
    parser.add_argument("--record-evidence", action="store_true", help="Explicitly write evidence report to evidence/ directory")
    parser.add_argument("--python", default=sys.executable, help="Path to Python interpreter; defaults to sys.executable")
    args = parser.parse_args()

    python_exe = Path(args.python).resolve()
    if not python_exe.is_file():
        raise RuntimeError(f"Python interpreter not found: {args.python}")

    examples_dir = ROOT / "examples"
    examples_before = {p.name: hashlib.sha256(p.read_bytes()).hexdigest() for p in examples_dir.glob("*.json")}

    temp_dir_obj = None
    if args.output_dir:
        out_dir = Path(args.output_dir).resolve()
        out_dir.mkdir(parents=True, exist_ok=True)
        owns_temp = False
    elif args.record_evidence:
        out_dir = ROOT / "evidence"
        out_dir.mkdir(parents=True, exist_ok=True)
        owns_temp = False
    else:
        temp_dir_obj = tempfile.TemporaryDirectory(prefix="tnotes-engine-run-")
        out_dir = Path(temp_dir_obj.name)
        owns_temp = True

    os.environ["TNOTES_TEST_OUTPUT_DIR"] = str(out_dir / "artifacts")

    started = utc()
    suite = unittest.TestSuite(EngineTests(name) for name in args.case) if args.case else unittest.defaultTestLoader.loadTestsFromTestCase(EngineTests)
    result = EvidenceResult()
    suite.run(result)

    examples_after = {p.name: hashlib.sha256(p.read_bytes()).hexdigest() for p in examples_dir.glob("*.json")}
    if examples_before != examples_after:
        raise RuntimeError("Source fixtures in examples/ were modified during test execution!")

    inventory = [{"path": p.relative_to(ROOT).as_posix(), "sha256": hashlib.sha256(p.read_bytes()).hexdigest()}
                 for p in sorted(ROOT.rglob("*")) if p.is_file() and "evidence" not in p.relative_to(ROOT).parts and "__pycache__" not in p.parts]
    preserved = json.loads((ROOT / "evidence/entry-preservation.json").read_text())
    repo = ROOT.parents[1]
    drift = []
    for item in preserved["files"]:
        path = repo / item["path"]
        observed = hashlib.sha256(path.read_bytes()).hexdigest() if path.is_file() else None
        if observed != item["sha256"]:
            drift.append({"path": item["path"], "entry_sha256": item["sha256"], "observed_sha256": observed})
    preservation_failures = [x["path"] for x in drift]
    report = {"provenance": "PROVISIONAL OFFLINE ENGINE; author-run real Windows/Python/PowerShell tests",
              "status": "PASS" if result.wasSuccessful() else "FAIL", "status_scope": "Engine test cases only; preservation is reported separately",
              "started_at": started, "completed_at": utc(), "command": [str(python_exe), "-B", str(Path(__file__).resolve()), *sys.argv[1:]],
              "python": sys.version, "platform": sys.platform, "powershell": "7.6.9 (see gate1.json; executable hash pinned)",
              "passed": sum(r["result"] == "PASS" for r in result.rows), "failed": sum(r["result"] == "FAIL" for r in result.rows),
              "tests": result.rows, "preservation_result": "FAIL" if drift else "PASS", "preservation_failures": preservation_failures,
              "concurrent_raw_byte_drift": drift, "protected_files_verified": len(preserved["files"])-len(drift),
              "artifacts": inventory, "not_run": ["Independent review", "live M365/authentication", "production integration", "GUI/SQLite/notes regression", "non-Windows platforms"]}
    name = "tests-" + datetime.now(timezone.utc).strftime("%Y%m%dT%H%M%SZ") + "-" + uuid.uuid4().hex[:8] + ".json"
    report_path = out_dir / name
    report_path.write_text(json.dumps(report, indent=2) + "\n", encoding="utf-8")

    if owns_temp:
        if report["status"] == "PASS":
            temp_dir_obj.cleanup()
            print(json.dumps({"status": report["status"], "passed": report["passed"], "failed": report["failed"],
                              "preservation_failures": preservation_failures, "isolation": "ISOLATED_TEMPORARY_CLEANED_UP"}), flush=True)
        else:
            temp_dir_obj._finalizer.detach()
            print(json.dumps({"status": report["status"], "passed": report["passed"], "failed": report["failed"],
                              "preservation_failures": preservation_failures, "report": str(report_path)}), flush=True)
    else:
        print(json.dumps({"status": report["status"], "passed": report["passed"], "failed": report["failed"],
                          "preservation_failures": preservation_failures, "report": str(report_path)}), flush=True)
    return 0 if report["status"] == "PASS" else 1


if __name__ == "__main__":
    raise SystemExit(main())
