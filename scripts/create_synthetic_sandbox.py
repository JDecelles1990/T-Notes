"""Create an isolated synthetic sandbox database in %TEMP% without touching live user data."""

from __future__ import annotations

import argparse
import os
from pathlib import Path
import subprocess
import sys
import tempfile

_REPO_ROOT = Path(__file__).resolve().parent.parent
if str(_REPO_ROOT) not in sys.path:
    sys.path.insert(0, str(_REPO_ROOT))

from src.core.paths import get_app_data_dir  # noqa: E402
from src.database.history_fts import assign_ticket_taxonomy, suggest_taxonomy_for_text  # noqa: E402
from tests.synthetic_tickets import SYNTHETIC_TICKETS, populate_synthetic_database  # noqa: E402


DEFAULT_SANDBOX_PATH = Path(tempfile.gettempdir()) / "tnotes_synthetic_sandbox.db"


def build_sandbox_database(target_path: Path | None = None) -> Path:
    """Create and populate the isolated synthetic sandbox database safely inside %TEMP%."""
    resolved = Path(target_path or DEFAULT_SANDBOX_PATH).expanduser().resolve()
    live_db = (get_app_data_dir() / "techpad.db").resolve()
    if resolved == live_db or str(live_db.parent).lower() in str(resolved).lower():
        raise RuntimeError(
            f"Refusing to write sandbox inside live user data directory: {resolved}"
        )

    db_mgr, id_map = populate_synthetic_database(resolved, auto_tag_post_migration=True)
    try:
        conn = db_mgr.get_connection()
        # Also auto-tag pre-migration synthetic archived tickets in the visual sandbox
        # so filtering by Domain/Symptom/Resolution showcases all 31 technical archived cards immediately.
        for spec in SYNTHETIC_TICKETS:
            if spec.is_archived and spec.pre_migration and spec.has_technical_cues:
                tid = id_map[spec.ticket_number]
                sug = suggest_taxonomy_for_text(title=spec.title, body=spec.body_text, conn=conn, max_per_axis=2)
                picked: list[str] = []
                for axis in ("domain", "symptom", "resolution"):
                    for item in sug.get(axis, ()):
                        if axis == "domain" and item.get("parent_slug") is None:
                            continue
                        if float(item.get("score", 0.0)) >= 1.5:
                            picked.append(str(item["slug"]))
                            break
                if picked:
                    assign_ticket_taxonomy(conn, tid, picked, source="auto", confidence=0.85, replace_existing=True)

        archived_count = conn.execute(
            "SELECT COUNT(*) FROM scratchpads WHERE status = 'archived'"
        ).fetchone()[0]
        active_count = conn.execute(
            "SELECT COUNT(*) FROM scratchpads WHERE status = 'active'"
        ).fetchone()[0]
    finally:
        db_mgr.close()

    # Remove sidecar pre-migration .bak artifacts created during synthetic seed so %TEMP% stays clean
    for bak in resolved.parent.glob(f"{resolved.name}.*migration.bak"):
        try:
            bak.unlink()
        except OSError:
            pass

    print("=" * 72)
    print("T-Notes Synthetic MSP Visual Sandbox Ready")
    print("=" * 72)
    print(f"Sandbox DB Path : {resolved}")
    print(f"Live DB untouched: {live_db}")
    print(f"Populated Rows  : {archived_count} archived history tickets, {active_count} active tabs")
    print("")
    print("Launch T-Notes against this isolated sandbox in PowerShell:")
    print(f'  $env:TNOTES_DB_PATH="{resolved}"; python src\\main.py')
    print("=" * 72)
    return resolved


def main() -> int:
    parser = argparse.ArgumentParser(
        description="Generate an isolated synthetic T-Notes database in %TEMP%."
    )
    parser.add_argument(
        "--output",
        type=Path,
        default=DEFAULT_SANDBOX_PATH,
        help="Target sandbox database path (defaults to %%TEMP%%\\tnotes_synthetic_sandbox.db).",
    )
    parser.add_argument(
        "--launch",
        action="store_true",
        help="Immediately launch T-Notes against the generated sandbox database.",
    )
    args = parser.parse_args()

    sandbox_path = build_sandbox_database(args.output)
    if args.launch:
        env = os.environ.copy()
        env["TNOTES_DB_PATH"] = str(sandbox_path)
        subprocess.Popen([sys.executable, str(_REPO_ROOT / "src" / "main.py")], env=env)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
