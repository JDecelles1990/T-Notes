# [ADR-0006] Side-by-Side Split View & Dual Ticket Workspace

- **Status:** Accepted
- **Date:** 2026-11-02
- **Author(s):** Application Architecture Team
- **Deciders:** Principal Desktop Architect

---

## 1. Context and Problem Statement
IT support technicians frequently triage or troubleshoot multiple related issues concurrently:
1. Comparing error logs between two different machines or tickets.
2. Cross-referencing an ongoing incident against a previously resolved ticket note or standard operating procedure.
3. Managing incoming high-priority triage while keeping a long-running diagnostic script or maintenance task open.

In a single-pane tabbed workspace, comparing two tickets requires constantly switching back and forth between tabs (`Ctrl+Tab`, `Ctrl+PgUp/PgDown`), losing visual context and interrupting workflow. Technicians requested an ergonomic way to view and edit two tickets simultaneously side-by-side.

---

## 2. Decision Drivers
- **Seamless Spatial Partitioning:** Enable 50/50 dual-editor layout with fluid resizing via a draggable divider.
- **Zero Data Loss & Safe State Synchronization:** Opening, closing, or moving tabs across panes must never lose unsaved keystrokes, embedded images, or active stopwatch timestamps.
- **Unified Micro-Controls:** Toolbar actions (formatting, tags, checkboxes, templates), stopwatch billing, and status bar metadata must dynamically track whichever pane currently holds keyboard focus.
- **Frictionless Shortcuts:** Instant toggle via global shortcut `Alt+Z`, ribbon button `◫`, status bar button, or tab/history right-click context menus.
- **Lightweight Native Qt Architecture:** Retain low memory footprint (~45MB RAM) without spawning heavy secondary processes or redundant window frames.

---

## 3. Considered Options

1. **Option 1: Multi-Window Floating Dialogs (`QMainWindow` detachment)**
   - *Problem:* Allowing tabs to tear off into separate native OS windows introduces window management clutter, taskbar fragmentation, and complex multi-window focus routing for global shortcuts and toolbars.

2. **Option 2: Secondary QDockWidget containing a duplicate editor**
   - *Problem:* `QDockWidget` headers consume substantial vertical screen space and behave awkwardly when docked inside the central widget alongside `TechPadTabWidget`. Tab management and ordering across two fundamentally different container widgets is brittle.

3. **Option 3: Central Draggable `QSplitter` hosting Dual `TechPadTabWidget` Panes**
   - Replace the single central widget with a horizontal `QSplitter` containing a Primary `TechPadTabWidget` (Left) and a Secondary `TechPadTabWidget` (Right).
   - Collapse the secondary pane (`secondary_tab_widget.hide()`) in single-ticket mode.
   - Reveal the secondary pane and divide space equally (50% / 50%) when Split View is enabled.
   - Synchronize focus enter events (`focusInEvent`) from `TechPadEditor` to dynamically re-bind the top toolbar and active stopwatch.

---

## 4. Decision Outcome
**Chosen Option:** Option 3 (`QSplitter` hosting Dual `TechPadTabWidget` Panes).

### Rationale
- **Consistent Feature Parity:** Because both left and right panes are instances of `TechPadTabWidget`, both sides enjoy full feature parity: tab color ownership, live running minute tags, task checklist progress badges, hover tooltips, drag-and-drop tab reordering, and rich context menus.
- **Clean Draggable Divider:** The 6px divider bar is styled with `#2d2d2d` and highlighted with `#007acc` on hover. `setChildrenCollapsible(False)` guarantees neither pane is accidentally crushed to zero width while dragging.
- **Safe Re-merging Lifecycle:** When toggling Split View OFF, all secondary tabs are safely merged back into the primary tab bar after flushing pending saves, ensuring no drafts or active tabs are ever discarded.

---

## 5. Consequences

### Positive Consequences
- Technicians can edit two tickets side-by-side with instantaneous `Alt+Z` or `◫` toggling.
- Dragging the 6px divider bar allows custom spatial allocation (50/50, 60/40, 70/30).
- Clicking either editor instantly routes toolbar actions and stopwatch tracking to the active note.
- History Drawer right-click action (*"◫ Open in Side-by-Side Split"*) allows comparing archived solutions alongside current active tickets.
- Right-clicking tab headers allows moving tabs between left and right panes effortlessly.

### Trade-offs & Mitigations
- *Focus Ambiguity:* Having two editors visible simultaneously could cause confusion over which ticket is receiving formatting commands.
  - *Mitigation:* The status bar clearly displays `Active Ticket: #...`, and `focusInEvent` automatically synchronizes the ribbon and stopwatch the moment the user clicks or types into either editor.
