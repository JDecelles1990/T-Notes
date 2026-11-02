# ADR 0008 — M365 workspace foundation

- Date: 2026-11-02
- Status: S001 implementation candidate; independent review/integration pending
- Scope: same-window presentation foundation only

## Context

Notes uses a QSplitter with two ticket panes and MainWindow-owned save, focus,
stopwatch, tray and hotkey behavior. S001 adds an expandable M365 shell while
preserving those objects. Draft PowerShell contracts are not implementation authority.

## Decision

Place the existing Notes splitter on page 0 of a QStackedWidget; add one separate
M365LauncherWidget on page 1 during initial UI construction. Default to Notes.
Append M365 Launcher to formatting row 1; expose back_requested on the new widget.
Use existing QSS, Qt layouts/splitters and explicitly unimplemented placeholders.
No backend or active-ticket editor sidebar is implemented.

Before navigation call the existing saver directly for pending/dirty IDs. Dirty
tracking clears only after successful content/image persistence. Catch failure
at the page boundary rather than relying on propagation through Qt signals.
Hide/suspend Notes controls while on M365 and restore exact prior states. Keep F8
global; route HUD entry back through Notes. Preserve timing on page-only focus
changes and save the Notes history preference when closing from M365.

The S001 Alt+F8 addendum uses one QShortcut with explicit ApplicationShortcut
context and auto-repeat disabled. Both visible navigation signals and that
shortcut call `switch_workspace()`, which suppresses modal, shutdown, hidden,
minimized and reentrant input and chooses the existing guarded destination path.
Do not duplicate Alt+F8 handling in eventFilter or register it through Win32.
Restore normal Mini-HUD state before switching and suppress timer reloads from
transition-induced focus changes. Active window raising/activation and explicit
focus routing are enforced via _activate_and_focus() to prevent deactivation
defects from native window flag recreation on Windows. This extends S001 without a separate slice.

The high-DPI and compact-screen addendum introduces workspace-specific minimum
dimensions (`640x380` on M365, `660x400` on Notes, `340x200` on Mini-HUD) and
adaptive layout reflow in M365LauncherWidget. When center scroll viewport width
falls below 500px, content groupboxes automatically rearrange from 2 columns to
1 column without widget recreation. Category navigation and ticket sidebars are
collapsible via dedicated toggle controls and resizable splitters, and normal
geometry restoration clamps to the active screen's available work area.

The portrait monitor 150% scaling addendum accommodates a 700-logical-pixel viewport
(e.g. physical resolution 1050x1680 at 150% scaling):
1. `TechPadToolBar` implements automatic Compact Mode (<775px) vs Normal Mode (>=800px)
   with hysteresis, collapsing secondary actions (`act_badge`, `act_timestamp`, `act_image`)
   into a `More ▾` overflow menu while preserving action shortcuts and restoring editor focus.
2. The History drawer automatically collapses when width < 850px to prioritize the active
   ticket canvas, restoring at >= 900px, while preserving explicit user preference across sessions.
3. Split View automatically switches to a compact single-pane mode when width < 750px,
   providing an accessible switcher button `btn_switch_split_pane` (`Alt+Shift+Z`) and
   restoring side-by-side editing at >= 780px without ticket or document recreation.
4. The status bar active ticket label utilizes `CompactLabel` with unconstrained minimum width,
   reducing status bar minimum width from >800px to 380px and eliminating horizontal overflow.

## Alternatives

Rebuilding Notes risks unsaved content/resources/undo. A second window violates
the requested boundary. Copying/transferring an editor expands ownership and
persistence risk outside S001. Complete launcher/backend work requires later scope.

## Consequences and verification

MainWindow retains lifecycle coordination; Gemini can expand only the separate
presentation component after review/approval. No unused service abstraction,
dependency, schema/migration, connector, manifest parser or execution is added.
Test identity, pending/failing saves, timer state, split/history/HUD/tray/F8,
shortcuts, layout and schema identity with synthetic fixtures. Native smoke and
visual inspection do not establish physical keyboard, alternate DPI or full
accessibility acceptance. Canonical data and unrelated work stay outside the candidate.
### Independent Review Findings and Data-Integrity Corrections Addendum

Following independent review by Codex Sol High (disposition `CHANGES_REQUIRED`), targeted corrections were implemented to protect technician notes against loss, prevent false save indicators, and ensure consistent responsive behavior:

1. **P0 Case-Note Loss Prevention on Failed Navigation & Shutdown:**
   - **Root Cause:** If a background autosave failed while transitioning workspaces or closing the application, `flush_all_saves()` previously ignored stopped debounce timers and dirty IDs, falsely displaying `● Saved` (green) and allowing the window to close or navigate away with unpersisted draft text and in-memory images.
   - **Correction:** `flush_all_saves() -> bool` aggregates all active debounce timers and `_dirty_scratchpad_ids`, attempting synchronous retry for every pending ticket. If persistence fails or dirty IDs remain, the status bar displays `● Save Failed` (red), `show_m365_workspace()` aborts, and `closeEvent()` invokes `event.ignore()` with a clear error prompt to keep the application open until saves succeed.

2. **Compact Toolbar Mouse & Shortcut Parity:**
   - **Root Cause:** Calling `act.setVisible(False)` on `QAction` objects hid them within the `More ▾` popup menu and disabled shortcut evaluation (`F5`).
   - **Correction:** Toolbar button widgets (`act_timestamp_btn`, `act_image_btn`) are managed separately from the underlying `QAction` instances (`act_timestamp`, `act_image`). In compact mode, the toolbar button widgets are hidden, while the actions remain visible in `menu_more` and accessible via mouse clicks or `F5` / `Ctrl+Alt+I`. `main_window.eventFilter` also explicitly dispatches `F5` across all widgets in the Notes workspace.

3. **Mini-HUD Visibility from Compact Split View:**
   - **Root Cause:** Entering Mini-HUD mode while in compact single-pane mode (pane 2 active) hid the secondary tab widget without unhiding the primary tab widget, leaving both editor canvases hidden.
   - **Correction:** `_enable_mini_hud()` explicitly ensures `tab_widget` is displayed and focused, saving `_compact_active_pane` so returning to normal split view restores the technician's active split pane.

4. **M365 Responsive History Isolation:**
   - **Root Cause:** Window resize events while viewing M365 triggered `_check_responsive_history()`, inadvertently reopening the Notes History drawer if the window was resized narrow then wide.
   - **Correction:** `_check_responsive_layout()` immediately returns when `is_m365_workspace` is True, ensuring Notes toolbars and drawers remain completely hidden.

5. **Logical Active Ticket Tracking on Shutdown from M365:**
   - **Root Cause:** Determining the active ticket ID on application close relied on visible/focused widgets (`_get_active_editor()`). When closing from M365, all Notes widgets are hidden, causing session persistence to fall back to tab 0 instead of the secondary or active ticket.
   - **Correction:** `MainWindow` maintains `_logical_active_scratchpad_id` updated during tab switches, editor focus changes, and pane toggles, ensuring session restore accurately remembers the technician's true active ticket.

