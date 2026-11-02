# Tab Lifecycle & Workspace Management

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
2. The current tab order is saved.
3. The focused tab ID and window geometry are saved to `app_session`.
4. On reboot, all tabs are recreated in identical order, and the previously focused tab is selected.
