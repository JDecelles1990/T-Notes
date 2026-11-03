"""Read-only identity/preservation verification; never refreshes approval or pins."""

import hashlib
import json
from pathlib import Path
import subprocess
import sys


HERE = Path(__file__).resolve().parent
ROOT = HERE.parents[2]
CHANGED_EXISTING = {
    "docs/architecture/system-overview.md", "pyproject.toml", "requirements.txt",
    "src/ui/m365/launcher_widget.py", "tests/test_m365_workspace.py",
}


def digest(path):
    return hashlib.sha256(path.read_bytes()).hexdigest() if path.is_file() else None


def verify():
    entry = json.loads((HERE / "entry-state.json").read_text())
    inventory = json.loads((HERE / "candidate-inventory.json").read_text())
    candidate_mismatches = [path for path, expected in inventory["files"].items()
                            if digest(ROOT / path) != expected]
    preserved = {path: value for path, value in entry["files"].items() if path not in CHANGED_EXISTING}
    preservation_mismatches = [path for path, expected in preserved.items() if digest(ROOT / path) != expected]
    s002 = Path("C:/Dev/T-Notes-M365-S002")
    s002_mismatches = [path for path, expected in entry["s002_files"].items() if digest(s002 / path) != expected]
    branch = subprocess.check_output(["git", "-C", str(ROOT), "branch", "--show-current"], text=True).strip()
    head = subprocess.check_output(["git", "-C", str(ROOT), "rev-parse", "HEAD"], text=True).strip()
    index_preserved = digest(ROOT / ".git/index") == entry["index_sha256"]
    git_preserved = branch == entry["branch"] and head == entry["head"] and index_preserved
    return {"status": "PASS" if not candidate_mismatches + preservation_mismatches + s002_mismatches and git_preserved else "FAIL",
            "head": head, "branch": branch, "index_bytes_preserved": index_preserved,
            "candidate_files_checked": len(inventory["files"]), "candidate_mismatches": candidate_mismatches,
            "entry_files_checked": len(preserved), "preservation_mismatches": preservation_mismatches,
            "s002_files_checked": len(entry["s002_files"]), "s002_mismatches": s002_mismatches}


if __name__ == "__main__":
    result = verify()
    print(json.dumps(result, indent=2))
    sys.exit(0 if result["status"] == "PASS" else 1)
