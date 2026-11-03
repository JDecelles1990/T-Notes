# T-Notes M365 architecture and PowerShell contract proposal

Status: **PROPOSED — NOT APPROVED FOR IMPLEMENTATION**.
Proposed contract: `tnotes.m365 / 0.3.0-proposed.1`. Date: 2026-11-02.

This is a review package, not canonical contract promotion or runtime integration.
Only explicit user approval can adopt its architecture and exact contract files.

Correction candidate for the user's independent CHANGES_REQUIRED findings B1–B3
and I1–I4. See [correction handoff](CONTRACT_CORRECTION_HANDOFF.md) for the exact
scope, fresh outcomes and independent review instructions. The original
0.2.0-proposed.1 results and source snapshot are preserved as historical evidence.

## Documentation index

| Artifact | Owner and status |
|---|---|
| [Workspace architecture](workspace-architecture.md) | Proposed product, GUI, notes panel and storage |
| [Security and execution](security-and-execution.md) | Proposed company/auth/tenant model, catalog and worker lifecycle |
| [Shared contract](CONTRACT.md) | Proposed wire/version/error/exit/normalization rules |
| [User Snapshot](user-snapshot.md) | Proposed four-operation workflow and typed payloads |
| [Validation and roadmap](validation-and-roadmap.md) | Test matrix, implementation slices and open decisions |
| [Agent handoff](AGENT_HANDOFF.md) | Independent review instructions and responsibilities |
| [Proposed Gemini instructions](GEMINI.md) | Review copy only; root GEMINI.md remains unchanged |
| `schemas/` and `examples/fixtures.json` | Proposed schemas and synthetic positive/negative fixtures |
| `validation/validate_contract.py` | Offline design-validation tool, not a production parser/worker |
| `validation/results.json` and `validation/results-*.json` | Preserved original 0.2.0-proposed.1 evidence; not current-candidate validation |
| `validation/correction-results.json` and unique correction attempts | Fresh correction outcomes and artifact identities; not approval |
| `examples/mock-compatibility.json`, `validation/correction_checks.py` | Declarative synthetic ABI, eligibility, notes and history checks; no backend |
| `validation/correction-baseline.json` | Entry hashes protecting unrelated files and original validation evidence |
| `validation/source-snapshot.json` | Inspected inputs, Git state and preserved-work identities |

Existing engineering rules remain in root AGENTS.md and the current topic docs.
This package is the consolidated **proposed** review owner, not a replacement for
approved architecture. No runtime, live authentication or GUI delivery is claimed.

## Prior inputs and disposition

| Actual input | Observed status and disposition |
|---|---|
| `00_packages/TNotes-M365-Shared-Contract-DRAFT/` | Preserved untracked kit; CONTRACT and schemas use `1.0.0-draft.1`, module functions and host serialization; competing proposal reconciled here |
| `00_packages/T-Notes-M365-User-Snapshot-Spec-v0.1-DRAFT/` | Preserved packaged snapshot and prompt; historical proposal |
| `01_shared_contract_draft/USER_SNAPSHOT_SPEC.md` and `GEMINI_FIRST_SCRIPT_PROMPT.md` | Preserved copies referencing `0.1.0` and absent `contracts/m365/` paths; superseded only for this proposed review by CONTRACT.md |
| Root `GEMINI.md` revision 1 | Installed untracked instruction file; remains unchanged and requires approved inputs |
| `02_user_snapshot_draft/`, `03_codex_reviews/`, `04_decisions/` | Directories existed, no prior files found during inspection; no independent report overwritten |
| Earlier root-level `CONTRACT.md`, `result.schema.json`, `AGENT_HANDOFF.md` | Not found at expected draft-root paths; actual packaged CONTRACT and execution-result schema inspected instead |
| Canonical `docs/contracts/m365/` | Absent; future approval/promotion task only |

## Verified current architecture

Branch `main`, HEAD `3b8485fa874c7f5a4506089d0189270d72743da7`.
Existing dirty work: modified `docs/decisions/0007-always-on-top-mini-hud.md`,
untracked root GEMINI.md and 17 existing M365 draft/package files. SHA-256
preservation checks protect those files and AGENTS.md. Root AGENTS.md is the only
discovered repository instruction file. No Git mutation is authorized here.

| Source inspected | Static finding and implication |
|---|---|
| `src/main.py:main` | One QApplication, services/repositories and MainWindow; quit-on-last-window disabled |
| `main_window.py:_setup_ui` | Central workspace_splitter owns two TechPadTabWidget panes; toolbars/history/status are MainWindow children |
| `main_window.py:_create_editor`, `editor.py` | One editor/document/image cache and debouncer per ticket; signals wired once |
| `_find_editor_by_id`, `_execute_save` | Save lookup searches only the two tab panes; individual editor transfer breaks this assumption |
| `ScratchpadService.save_content`, ImageService/repositories | HTML update and image synchronization are separate repository operations, not one demonstrated atomic transaction |
| SessionService/SessionRepository | Active ID, geometry, opacity, drawer persisted; combined tab order in scratchpads; split-pane membership and M365 state not persisted |
| `_on_editor_focused`, StopwatchWidget | Toolbar reference routes editor actions; one active ticket timer can pause/reload/auto-start on focus change |
| `eventFilter`, GlobalHotkeyManager | Application-level tab/Alt+Z/Alt+T shortcuts and native F8; new workspace focus routing is required |
| Mini-HUD methods | Existing RAM geometry/visibility state and topmost flag; preserve its state machine |
| `closeEvent`, `quit_application` | Timer save, debounce flush, tab order/session save; tray hide differs from explicit Quit |
| DatabaseManager/migrations/repositories | WAL, FK, busy_timeout; existing settings access through SessionService; no worker use of app SQLite connection |
| Six test modules and fixtures | UI, database/migrations, images, scratchpads and stopwatch checks exist; inspected, not rerun here |
| Inspected `src/` | No delivered M365 GUI/catalog/connector/worker found; separate Gemini GUI request is not implementation evidence |

Also inspected AGENTS.md, GEMINI.md, ARCHITECTURE.md, README.md, docs/index.md,
system overview, image pipeline, tab lifecycle, editor/formatting, database schema,
all service/repository/database modules, toolbar, tab widget and editor ownership.
Exact source hashes and inventory are in validation/source-snapshot.json.

No application launch, operational DB, real clipboard, Graph/Exchange connection,
Pester operation suite or native GUI acceptance is part of this evidence.

## Requested deliverable coverage

A–D: workspace-architecture.md; E–F and L–M: security-and-execution.md;
G–K: CONTRACT.md plus schemas; N: user-snapshot.md; O/R:
validation-and-roadmap.md; P: AGENT_HANDOFF.md; Q: GEMINI.md.
Six Mermaid diagrams cover workspace, execution boundaries, authentication,
execution sequence, parsing and active-note synchronization.
