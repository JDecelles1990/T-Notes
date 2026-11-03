# Validation attempts and diagnoses

All datasets and database paths were synthetic/temporary. No authentication,
PowerShell engine or tenant operation was run. Tests used Qt windows unless noted.
Reports are retained under their original attempt names; FAIL is not relabelled.

| Attempt | Result | Diagnosis / scope |
|---|---|---|
| Initial combined offscreen run | INCONCLUSIVE retained tool output | Partial output only; no durable completion summary captured |
| Isolated offscreen workspace test | FAIL, 1 failed | Existing toolbar visibility assertion; Qt offscreen backend is not certified by this milestone; tool transcript retains failure |
| focused-windows-01 | FAIL, 16 passed / 1 failed | Export retained tuples rather than JSON arrays; corrected JSON-native metadata construction |
| focused-windows-02 | FAIL, 161 passed / 1 failed | Existing catalog test expected Back as the only button; updated explicit UI allowlist while preserving no execution action in catalog |
| full-windows-03 | FAIL, 226 passed / 2 failed | Existing HUD window activation and hidden-pane debounce assertions; preview GUI process overlapped this run, so focus/timing interference was possible, not proven |
| diagnostic-isolated-04 | PASS, 3 passed | Same HUD and hidden-pane tests in isolation, no competing GUI process |
| full-windows-05 | FAIL, 226 passed / 2 failed | Different existing tab-drag tests failed; no competing preview process |
| diagnostic-drag-current-06 | PASS, 2 passed | Same tab-drag tests with current launcher, isolated |
| diagnostic-entry-baseline-07 | PASS, 173 passed / 1 deselected | Loaded HEAD launcher source in memory, no repository replacement; deselected changed catalog button assertion; existing suite only |
| full-windows-08 | PASS, 228 passed | Status timer now stops when launcher hidden; explicit new-fixture deferred deletion; no parallel GUI process |
| scale-125 / scale-15 | PASS, 11 each | Automated 125% / 150% Qt layouts; three new context widths plus eight existing navigation/responsive cases |
| full-windows-09 | See final checkpoint and XML | Final full suite after giving identity/target status labels sufficient height; no functional or code changes follow this run |
| review-correction-p1-p2 | PASS, 80 passed in focused suite | Corrected P1 (lossless multiline domain input, 30-domain name-only edit preservation, RFC boundary enforcement) and P2 (controlled ISO 8601 UTC timestamp validation, negative tests for int/null/bool/float/timezone violations, immutable directory protection) |


The transition from variable existing-GUI failures to PASS does not prove a single
cause. The candidate was improved to avoid hidden-workspace polling and lingering
new fixture widgets, and the final run was isolated. No Notes implementation or
existing Notes assertion was changed to obtain a pass.

Windows logs contain a `0x8001010d` exception diagnostic emitted during window
showing, including the entry-baseline comparison. Processes continued to complete
pytest with XML and exit status. This remains a recorded native-environment
limitation; it is not evidence of physical desktop or accessibility acceptance.
Existing editor QMouseEvent.pos deprecation warnings are also retained.

Visual review found the selected tenant/cloud and later target-status text could
be clipped after dynamic label changes. Explicit label minimum heights prevent
adjacent controls from hiding that text. Initial and intermediate images remain;
the accepted synthetic captures use the `company-preview-accepted-*` names.

The first two native attempts used the discovered system Python 3.14.6. Final full,
baseline, scale and diagnostic runs used repository `.venv/Scripts/python.exe`
(Python 3.14.5, PySide6 6.12.0). No dependencies were installed or upgraded.

Initial candidate-path verification returned FAIL because two unrelated untracked
root PNGs appeared after entry. They were left untouched and recorded separately
by pathname in the inventory. The verifier now uses NUL-delimited Git paths and
compares task paths plus these explicit concurrent paths. This is a changed
preservation diagnosis, not permission to include or edit those images.
