# Codex task — Analyze before implementation

Objective: Analyze T-Notes (`JDecelles1990/T-Notes`) for adding a full-window M365 Launcher with a collapsible live active-ticket side panel.

First read repository root `AGENTS.md`, `ARCHITECTURE.md`, `docs/architecture/system-overview.md`, `docs/features/tab-lifecycle.md`, the relevant `src/ui/main_window.py`, `src/ui/components/toolbar.py`, `src/ui/components/editor.py`, services, and existing integration tests, plus `docs/contracts/m365/CONTRACT.md` and JSON schemas.

Explicitly analyze the existing splitter, history dock, split-view editor ownership, global keyboard filtering, F8 shortcut, Mini-HUD, autosave, active ticket identity and close-to-tray flows. Recommend a `QStackedWidget` outer workspace only if it can preserve existing behavior. The collapsible side panel must reuse the single authoritative ticket document and persistence path; discuss options and risks, do not assume two independent editors can write safely.

Keep the proposed contract independent of process transport. Authentication connector must verify actual account/tenant and not accept passwords in wire messages or store secrets. When script integration is authorized, validate manifest, request and result at boundaries; never execute arbitrary paths or AI strings.

Deliver: verified inventory, options/tradeoffs, proposed file diff, test matrix, security and interaction risks, acceptance criteria, clear minimal slices. This prompt authorizes **analysis and plan only**. No code edits, no new DB tables, no real M365 connections and no commit or merge. Finish `READY_FOR_USER_REVIEW`.
