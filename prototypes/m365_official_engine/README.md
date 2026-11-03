# Official-version S1 engine candidate

This is the existing offline engine migrated to `tnotes.m365 / 0.3.0`.
It is an author candidate awaiting independent review, with no GUI dispatch.
The predecessor remains unchanged under `docs/planning/m365/`.

See [the S1 topic](../../docs/features/m365-s1-engine.md) for authority,
trust inventories, execution restrictions, verification and rollback.

From the repository root on Windows:

```powershell
.venv/Scripts/python.exe -B prototypes/m365_official_engine/run_tests.py --output-dir C:/path/to/external/evidence
```

The suite uses actual offline PowerShell processes, inherited ABI/fault fixtures
and native return-type regressions. The nested-payload cases use an external
repo-shaped fixture so the host and worker read the same pinned test manifest.
It does not deliver an S2 operation or connect to Microsoft 365.
Do not regenerate fixture pins to hide a mismatch. Independent reviewers should
verify the frozen inventory and run the tests without fixture authoring.
