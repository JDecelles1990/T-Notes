"""Read-only candidate identity and entry preservation check; never approval."""

import hashlib
import json
from pathlib import Path
import subprocess

HERE = Path(__file__).resolve().parent
ROOT = HERE.parents[2]


def digest(path):
    return hashlib.sha256(path.read_bytes()).hexdigest()


def main():
    inventory = json.loads((HERE / "candidate-inventory.json").read_text(encoding="utf-8"))
    entry = json.loads((HERE / "entry.json").read_text(encoding="utf-8"))
    failures = []
    for name, expected in inventory["sha256"].items():
        path = ROOT / name
        if not path.is_file() or digest(path) != expected:
            failures.append(f"Candidate mismatch: {name}")
    authority = json.loads((HERE / "authority.json").read_text(encoding="utf-8"))
    for name, expected in authority["source_hashes"].items():
        if digest(ROOT / name) != expected:
            failures.append(f"Authority input changed: {name}")
    preserved = 0
    for name, expected in entry["files"].items():
        if name in inventory["modified_entry_paths"] or name in inventory.get("retained_concurrent_paths", []):
            continue
        path = ROOT / name
        if not path.is_file() or digest(path) != expected:
            failures.append(f"Unrelated entry drift: {name}")
        preserved += 1
    def git(*args):
        return subprocess.check_output(["git", "-C", str(ROOT), *args], text=True).strip()
    if git("rev-parse", "HEAD") != inventory["base"] or git("branch", "--show-current") != "main":
        failures.append("Branch or HEAD changed.")
    if git("diff", "--cached", "--name-only"):
        failures.append("Index has staged changes.")
    # All changed/untracked paths are enumerated, including this manifest itself.
    status = subprocess.check_output(["git", "-C", str(ROOT), "status", "--porcelain=v1", "--untracked-files=all", "-z"], text=True)
    expected_paths = set(inventory["sha256"]) | {"docs/reviews/m365-company-directory-20261102/candidate-inventory.json"} | set(inventory["retained_concurrent_paths"])
    actual_paths = {record[3:] for record in status.split("\0") if record}
    if actual_paths != expected_paths:
        failures.append("Changed-path inventory differs: " + repr(sorted(actual_paths ^ expected_paths)))
    print(json.dumps({"status": "FAIL" if failures else "PASS", "candidate_files": len(inventory["sha256"]),
                      "unchanged_entry_files": preserved, "failures": failures}, indent=2))
    return bool(failures)


if __name__ == "__main__":
    raise SystemExit(main())
