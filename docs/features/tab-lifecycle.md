# Tab Lifecycle & Workspace Management

## 1. Overview
The multi-tab architecture in T-Notes organizes concurrent troubleshooting sessions into dedicated scratchpads. Each tab maps 1-to-1 with an active ticket record in SQLite.

---

## 2. Tab Bar Features (`TechPadTabWidget`)

### Dynamic Tab Title Formatting
Tabs display concise metadata formatted as:
```text
#{ticket_number} — {client_name | title}
```
- Example: `#INC-4092 — Acme Corp`
- Example without client: `#4821 — DNS Resolution Failure`
- Titles longer than 24 characters are truncated cleanly with an ellipsis (`...`) while preserving full tooltips on hover.

### Movable & Closable Tabs
- `setMovable(True)` allows technicians to drag and drop tabs to reorder priority tickets.
- Moving a tab emits `tabMoved`, which immediately persists the new `tab_order` sequence into SQLite.
- `setTabsClosable(True)` renders a close button (`✕`) on every tab.

### Corner Widget
A persistent `+` button in the top-right corner allows instantaneous tab creation without reaching for the keyboard, backed by the global shortcut `Ctrl+T`.

---

## 3. Tab Operations & State Transitions

### 3.1 Creation (`Ctrl+T` or `+`)
1. User clicks `+` or presses `Ctrl+T`.
2. `ScratchpadService.create_ticket()` generates a new ticket record with a default identifier (e.g. `T-102`).
3. A new `TechPadEditor` is instantiated, bound to the `scratchpad_id`, and added to `TechPadTabWidget`.
4. The newly created tab receives immediate focus.

### 3.2 Renaming (Double-Click Header)
1. Double-clicking any tab header triggers `TechPadTabBar.tab_double_clicked(index)`.
2. `EditTicketDialog` opens with the current values for Ticket Number, Client / Team, and Subject / Summary.
3. A live preview demonstrates the formatted tab header as the technician types.
4. On `Save Details`, `ScratchpadService.update_metadata()` updates SQLite and updates the tab header text and tooltip.

### 3.3 Closing & Archiving (`Ctrl+W` or `✕`)
When a tab is closed:
1. Any unsaved debounced edits are flushed synchronously to SQLite.
2. A confirmation dialog presents three choices:
   - **Archive to History:** Sets `status = 'archived'` in `scratchpads`. The tab is removed from the active tab bar and immediately appears in the History Drawer.
   - **Delete Permanently:** Deletes the record from `scratchpads` (cascading all associated images) and removes the tab.
   - **Cancel:** Aborts closure and leaves the tab open.
3. If the user closes the final active tab, the application automatically generates a fresh scratchpad (`INC-1001`) so the technician is never left with an empty workspace.

### 3.4 Session Persistence on Reboot
Upon closing the application:
1. All pending saves are flushed.
2. The current tab order is saved.
3. The focused tab ID and window geometry are saved to `app_session`.
4. On reboot, all tabs are recreated in identical order, and the previously focused tab is selected.
