# Tab Lifecycle & Workspace Management

## S001 Notes/M365 workspace navigation candidate

Notes remains the default startup workspace on page 0 of MainWindow.workspace_stack;
the original splitter and both tab panes remain intact. Page 1 is the separate
M365LauncherWidget skeleton. M365 Launcher and Back switch pages in the same window
without editor copies, editor transfer, document reconstruction, schema changes or
a second application database. The future ticket sidebar is a placeholder only.

Before leaving Notes, cancel pending debounce timers and call the existing saver
directly for pending/dirty IDs. Successful persistence clears dirty tracking and
image caches. A failure keeps Notes active, retains unsaved state, and displays a
safe status message. A later explicit navigation attempt retries dirty IDs; an
idle failed timer does not count as saved. Ordinary 1500ms debounce behavior remains.

Switching preserves active ticket/pane, selection/cursor/undo, document/editor
identity, image resources, split membership, opacity, and stopwatch running/paused
state. Back restores prior Notes toolbars, history visibility and enabled controls.
Split/history controls are unavailable on M365. F8 restores the current page.
Alt+T from M365 returns to Notes before entering Mini-HUD; leaving HUD stays on
Notes. Opening M365 from HUD first exits through the existing HUD restoration path.
Tray New Ticket intentionally returns to Notes before creating a ticket.

Close-to-tray saves notes and session state and keeps the current page in RAM;
F8 reopens that page. A new MainWindow restores existing tickets and defaults to
Notes. History preference uses its saved Notes visibility rather than temporary
M365 hiding. No M365 state is added to SQLite. Existing combined tab-order/session
semantics and their split-pane restoration limits remain unchanged. This candidate
is uncommitted and pending independent review/integration.

### S001 Alt+F8 addendum

Alt+F8 toggles Notes and M365 from focus inside either workspace. The visible
M365 Launcher and Back buttons use the same `switch_workspace()` entry point,
including the pending/dirty save barrier and failure refusal. Repeated keys reuse
the same pages, tabs and editors. Auto-repeat is disabled to prevent held-key
page cycling. This is an application shortcut, not a Windows global hotkey.

An application-modal dialog, shutdown, hidden/minimized window or already-active
transition suppresses this route. From Mini-HUD it restores the saved normal
window geometry, topmost flag and control visibility before opening M365; Back
then shows the original normal Notes view. Focus changes during the transition
cannot reload/start/pause the selected ticket's timer. Active ticket, draft edits,
split state and stopwatch state remain preserved. No workspace persistence,
database field or PowerShell functionality is added by this addendum.

## 1. Overview
The multi-tab architecture in T-Notes organizes concurrent troubleshooting sessions into dedicated scratchpads. Each tab maps 1-to-1 with an active ticket record in SQLite.

---

## 2. Tab Bar Features (`TechPadTabWidget`)

### Dynamic Tab Title Formatting with Live Running Minutes & Task Badges
Tabs display concise metadata, real-time troubleshooting elapsed minutes, and live task checklist completion progress:
```text
#{ticket_number} ({minutes}m) {progress_tag} — {client_name | title}
```
- **In-Progress Tasks:** `#INC-4092 (14m) ☑️3/5 — Acme Corp`
- **100% Completed Tasks:** `#INC-4092 (14m) ✅5/5 — Acme Corp`
- **Without Tasks (Standard):** `#INC-4092 (14m) — Acme Corp`
- **When elapsed time is under 1 minute or at 0:** `#{ticket_number} ☑️1/3 — {secondary}`
- Titles longer than 24 characters are truncated cleanly with an ellipsis (`...`) while preserving full tooltips on hover.
- Tab titles update dynamically every minute as the technician works, and instantly whenever checklist tasks are added, removed, or clicked.
- Switching tabs seamlessly pauses the outgoing tab's stopwatch, persists elapsed seconds to SQLite, and loads/starts the incoming tab's stopwatch.

### Rich Tab Hover Tooltips
Hovering over any tab header displays an instant summary of ticket details, task completion breakdown, and accumulated troubleshooting time:
```text
Ticket: INC-4092
Client: Acme Corp
Title: Server Migration
Tasks: 3/5 completed (60%)
Troubleshooting Time: 14m
```

### Automatic Tab Color Ownership (Unique Color per Ticket)
To prevent disorientation across concurrent support sessions, each tab automatically and permanently owns a distinct, vibrant accent color from a curated 12-color technician palette:
- **Curated Palette:** Sky Blue (`#38bdf8`), Emerald (`#34d399`), Purple (`#a855f7`), Amber (`#fbbf24`), Rose (`#f43f5e`), Cyan (`#06b6d4`), Orange (`#fb923c`), Indigo (`#818cf8`), Lime (`#a3e635`), Pink (`#ec4899`), Teal (`#2dd4bf`), and Lavender (`#c084fc`).
- **Visual Presentation:**
  - **Top Accent Line:** Rendered in `TechPadTabBar.paintEvent()` directly atop each tab (3px thick on active tab, 2px on background tabs).
  - **Ambient Background Tint:** A subtle 12%–14% ambient tint (32% when selected) overlays the dark tab background.
- **Persistent Ownership by Ticket ID:** Colors map deterministically to each ticket's `scratchpad_id`. Dragging/reordering tabs, switching between tickets, or restoring archived tickets guarantees that each ticket retains its exact color identity without requiring manual user configuration.

### Slide-Reorganizing & Movable Tabs
- Tabs can be clicked and slid horizontally to reorganize their order in real time.
- `setMovable(True)` and `setDocumentMode(True)` enable fluid visual drag animations.
- Reorganizing tabs emits `tabMoved`, which immediately persists the new `tab_order` sequence into SQLite.
- `setUsesScrollButtons(True)` automatically renders dark-themed scroll navigation arrows when numerous tabs overflow the window width.

### Closable Tabs & Corner Widget
- `setTabsClosable(True)` renders a close button (`✕`) on every tab.
- A persistent `+` button in the top-right corner allows instantaneous tab creation without reaching for the keyboard, backed by the global shortcut `Ctrl+T`.

### Browser-Style Keyboard Shortcuts

All tab shortcuts are intercepted centrally at the `QApplication` level via `TechPadMainWindow.eventFilter()`. This prevents focused widgets (such as `TechPadEditor` or `TechPadTabBar`) from swallowing navigation events and ensures reliable operation on physical Windows keyboards where hardware drivers attach `Qt.KeypadModifier` to extended navigation keys (`PageDown`/`PageUp`).

| Shortcut | Action | Description |
| :--- | :--- | :--- |
| `Ctrl+T` | New Tab | Opens a fresh ticket scratchpad. |
| `Ctrl+W` / `Ctrl+F4` | Close / Archive Tab | Closes active tab (prompts or directly archives based on preferences). |
| `Ctrl+Tab` / `Ctrl+PageDown` | Next Tab | Cycles focus to the adjacent tab on the right. |
| `Ctrl+Shift+Tab` / `Ctrl+PageUp` | Previous Tab | Cycles focus to the adjacent tab on the left. |
| `Ctrl+Shift+PageDown` | Slide Tab Right | Moves/slides the active tab one position to the right. |
| `Ctrl+Shift+PageUp` | Slide Tab Left | Moves/slides the active tab one position to the left. |
| `Ctrl+1` .. `Ctrl+8` | Select Tab 1–8 | Directly jumps to tab indices 1 through 8. |
| `Ctrl+9` | Select Last Tab | Jumps directly to the last open tab. |
| `Ctrl+Shift+T` | Re-open Closed Tab | Restores the most recently archived ticket from the History Drawer. |

#### Architectural Note on Modifier Handling:
Standard `QShortcut` registrations fail on Windows when keys emit `Qt.KeypadModifier` alongside `Qt.ControlModifier` and `Qt.ShiftModifier`. The application event filter uses bitwise checking:
```python
mods = event.modifiers()
has_ctrl = bool(mods & Qt.ControlModifier)
has_shift = bool(mods & Qt.ShiftModifier)
```
This isolates the key logic from hardware driver flags, guaranteeing that `Ctrl+Shift+PageUp` and `Ctrl+Shift+PageDown` slide tabs regardless of keyboard manufacturer or focus state. Immediately following each tab slide or selection change, focus is automatically returned to the active `TechPadEditor`.

---

## 3. Right-Click Context Menu & Tab Operations

Right-clicking any tab header (or empty space on the tab bar) triggers `TechPadTabBar.contextMenuEvent()`, surfacing a technician-focused context menu:

| Context Action | Icon / Label | Behavior |
| :--- | :--- | :--- |
| **Rename / Edit Metadata** | `✏️ Rename Ticket #<id>...` | Opens the `EditTicketDialog` modal to update ticket number, client, and summary. |
| **Duplicate Note** | `📋 Duplicate Ticket Note` | Clones the note body, ticket metadata, and all embedded screenshot BLOBs into a fresh tab (`<ticket>-COPY`). |
| **Copy for PSA** | `📤 Copy Note for Ticket Tool` | Exports clean Markdown/plain-text stripped of HTML directly to the clipboard. |
| **Split View / Move** | `◫ Open in Side-by-Side Split (Alt+Z)` / `◫ Move to Right/Left Pane` | Toggles dual side-by-side editing panes or transfers tabs between primary and secondary panes. |
| **Archive Ticket** | `📦 Archive to History` | Flushes pending edits and archives the ticket directly into the History Drawer. |
| **Close Tab** | `✕ Close Tab` | Prompts to archive or permanently delete the tab. |
| **Close Other Tabs** | `Close Other Tabs` | Archives all other tabs, keeping only the targeted tab open. |
| **New Ticket Tab** | `➕ New Ticket Tab (Ctrl+T)` | Instantiates a fresh ticket scratchpad. |

---

## 4. Tab Operations & State Transitions

### 4.1 Creation (`Ctrl+T` or `+`)
1. User clicks `+`, presses `Ctrl+T`, or selects `New Ticket Tab` from the tab context menu.
2. `ScratchpadService.create_ticket()` generates a new ticket record with a default identifier (e.g. `T-102`).
3. A new `TechPadEditor` is instantiated, bound to the `scratchpad_id`, and added to `TechPadTabWidget`.
4. The newly created tab receives immediate focus.

### 4.2 Renaming (Double-Click or Right-Click Context Menu)
1. Double-clicking any tab header or selecting **✏️ Rename Ticket** from the right-click menu opens `EditTicketDialog`.
2. The dialog loads the current Ticket Number, Client / Team, and Subject / Summary.
3. A live preview demonstrates the formatted tab header as the technician types.
4. On `Save Details`, `ScratchpadService.update_metadata()` updates SQLite and modifies the tab header text and tooltip.

### 4.3 Closing & Archiving (`Ctrl+W` or `✕`)
When a tab is closed:
1. Any unsaved debounced edits are flushed synchronously to SQLite.
2. A confirmation dialog presents three choices:
   - **Archive to History:** Sets `status = 'archived'` in `scratchpads`. The tab is removed from the active tab bar and immediately appears in the History Drawer.
   - **Delete Permanently:** Deletes the record from `scratchpads` (cascading all associated images) and removes the tab.
   - **Cancel:** Aborts closure and leaves the tab open.
3. If the user closes the final active tab, the application automatically generates a fresh scratchpad (`INC-1001`) so the technician is never left with an empty workspace.

### 4.4 Session Persistence on Reboot
Upon closing the application:
1. All pending saves are flushed.
2. The current tab order is saved across primary and secondary panes.
3. The focused tab ID and window geometry are saved to `app_session`.
4. On reboot, all tabs are recreated in identical order, and the previously focused tab is selected.

---

## 5. Side-by-Side Split View (`Alt+Z` or Ribbon `◫`)

### 5.1 Architecture & Pane Division
T-Notes supports dual concurrent ticket editing via a horizontal `QSplitter` containing two independent `TechPadTabWidget` instances:
- **Primary Pane (Left):** Houses primary tickets and remains permanently visible.
- **Secondary Pane (Right):** Collapsible split view pane that toggles on demand.
- **Draggable Handle (6px):** 6-pixel wide splitter divider (`#2d2d2d`, highlighting to `#007acc` on hover) allowing fluid 50/50, 60/40, or custom spatial partitioning. `setChildrenCollapsible(False)` prevents either pane from accidentally vanishing when dragged.

### 5.2 Opening & Tab Migration
- **Triggered via `Alt+Z`, Ribbon `◫`, Status Bar `◫ Split`, or Tab/History Context Menus.**
- When opened:
  - If 2+ tabs are open in the primary pane, the adjacent tab moves seamlessly to the secondary pane.
  - If only 1 tab is open, a new ticket scratchpad is created in the secondary pane.
  - If opened from the History Drawer (*"◫ Open in Side-by-Side Split"*), the archived ticket is restored directly into the secondary pane without displacing active tabs.
- Technicians can freely migrate tickets between panes using the right-click context menu (*"◫ Move to Right Pane"* / *"◫ Move to Left Pane"*).

### 5.3 Focus-Aware Routing
- Clicking inside either editor immediately routes:
  1. **Toolbar Actions:** Bold, Italic, Code block, Checklists, Badges format the focused editor.
  2. **Billing Stopwatch:** Automatically synchronizes to track troubleshooting time for the focused ticket.
  3. **Status Bar Metadata:** Displays active ticket number, client, and subject for the focused editor.

### 5.4 Closing & Re-merging
- Closing Split View via `Alt+Z`, Ribbon `◫`, or closing the last secondary tab:
  1. Flushes all debounced auto-saves synchronously.
  2. Re-merges all open secondary tabs back into the primary tab bar without state loss.
  3. Hides the secondary pane and restores full 100% width to the primary pane.

### 5.5 Cross-Pane Tab Drag-and-Drop
Technicians can seamlessly migrate tickets between split view panes using natural drag-and-drop:
1. **Click and Drag:** Left-clicking and holding any tab header in either pane initiates tab movement.
2. **Visual Feedback:** Dragging the mouse outside the source tab bar transforms the cursor to `Qt.DragMoveCursor`.
3. **Drop and Insert:** Releasing the tab over the opposite pane transfers the ticket instantly:
   - **Target Tab Bar:** Dropping on the opposite tab bar computes the exact insertion index (`target_index`) based on cursor coordinates, placing the ticket exactly between existing tabs or at the end.
   - **Editor Area:** Dropping anywhere over the opposite note editor body appends the ticket as the active tab.
4. **Opening Split View via Drag:** Dragging a tab from the primary pane into the right half of the window when Split View is closed automatically triggers Split View mode and places the dragged ticket in the secondary pane.
5. **State Preservation:** Transferring tabs preserves all embedded image BLOBs, checklist progress badges, ticket color identity, and active billing stopwatch seconds.



## Failed close and Quit recovery

All window-close and explicit/tray Quit requests pass through `closeEvent` before
teardown. Dirty snapshots save even with inactive timers; an unavailable dirty
editor blocks completion. Save or session-persistence failure cancels shutdown,
restores Notes visibly, requests focus and retains the F8/tray controls. Ctrl+S
retries without another edit. F8 unregistration, tray hiding and QApplication quit
follow accepted shutdown only. Ordinary successful close-to-tray retains the
existing background behavior. Synthetic tests cover visible/hidden failures and
retry; physical desktop acceptance is separate.
