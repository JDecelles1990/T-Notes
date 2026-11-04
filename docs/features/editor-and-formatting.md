# Rich-Text Editor & Technician Formatting Tools

## S001 workspace shortcut boundary

The S001 candidate suspends existing Notes QActions (including nested toolbar-menu
actions), Ctrl+S, Ctrl+H, Ctrl+comma and Alt+Z shortcuts while M365 is displayed.
Its application event filter bypasses ticket Ctrl+T/W/F4/Tab/PageUp/PageDown/number
handling there, preventing accidental edits, closing or reordering of hidden tabs.
Back restores exact prior enabled states, including previously disabled actions.
Notes shortcut behavior is unchanged. F8 remains global; Alt+T returns to Notes
before existing Mini-HUD behavior. Back and ticket-placeholder collapse controls
are keyboard-focusable; Space activates Back.

The original editor retains document, cursor/selection, undo and image resources.
The M365 page contains no QTextEdit and implements neither note synchronization
nor result insertion. Independent review/integration of this candidate is pending.

Alt+F8 is the application-level S001 workspace toggle. It remains enabled when
Notes-only shortcuts are suspended and works from editor, toolbar, Back or future
M365 form focus. Exactly one QShortcut owns it, with context set explicitly to
ApplicationShortcut and auto-repeat disabled; eventFilter does not also dispatch
this combination. Both visible navigation buttons call the same shared guard.
Modal/shutdown/reentrant or hidden/minimized states suppress it. Plain F8 keeps
its existing window/global-hotkey behavior; Alt+T and Alt+Z retain their existing
HUD and Notes split-view rules. The button tooltips advertise Alt+F8. Window flag
transitions when toggling Mini-HUD trigger `_activate_and_focus()` to guarantee
native window activation and focused controls survive handle changes on Windows.

## 1. Overview
The note-taking canvas in T-Notes is built upon `TechPadEditor`, a customized `QTextEdit` component integrated with `TechPadToolBar`. It balances rich-text capabilities (bold, italics, colors, embedded images) with developer-grade controls (monospace CLI blocks, timestamping, triage badges, URL auto-detection, and clean markdown export).

---

## 2. Keyboard Shortcuts Reference

### Formatting & Editing Shortcuts
| Action | Shortcut | Description |
| :--- | :--- | :--- |
| **Bold** | `Ctrl+B` | Toggles bold font weight for selected text. |
| **Italic** | `Ctrl+I` | Toggles italic text style. |
| **Underline** | `Ctrl+U` | Toggles text underline. |
| **Monospace Code Block** | `Ctrl+Alt+C` | Formats selected text or inserts a dark monospace container block. |
| **Insert Checklist Item** | `Ctrl+Alt+L` | Inserts an interactive task checklist item (`[ ]`) at current line. |
| **Insert Timestamp** | `F5` / `Ctrl+Alt+T` | Injects current timestamp in format `[YYYY-MM-DD HH:MM:SS]`. |
| **Insert Image File** | `Ctrl+Alt+I` | Prompts file picker to insert screenshot or image. |
| **Ticket Skeletons** | `Ctrl+Alt+S` | Opens template skeleton menu. |
| **Copy for PSA Note** | `Ctrl+Alt+N` | Exports clean Markdown/plain-text stripped of HTML to clipboard. |
| **Text Color** | `Ctrl+Alt+X` | Opens color picker for selected text. |
| **Highlight Background** | `Ctrl+Alt+H` | Opens highlight color picker for text background. |
| **Badge: 🟢 PASS** | `Alt+1` | Injects inline green PASS tag. |
| **Badge: 🔴 FAIL** | `Alt+2` | Injects inline red FAIL tag. |
| **Badge: 🟡 WARN** | `Alt+3` | Injects inline amber WARN tag. |
| **Badge: ℹ️ INFO** | `Alt+4` | Injects inline blue INFO tag. |
| **Open Preferences** | `Ctrl+,` | Launches the Preferences / Settings modal dialog. |
| **Toggle Split View** | `Alt+Z` | Toggles side-by-side dual ticket editing panes (50/50 draggable split). |
| **Slide Tab Left / Right** | `Ctrl+Shift+PgUp` / `PgDown` | Reorders current tab horizontally while typing (modifier-masked). |
| **Switch Next / Prev Tab** | `Ctrl+PgUp` / `PgDown` | Cycles active tab while typing in the editor. |
| **Global Quick-Launch / Toggle** | `F8` | System-wide hotkey: pops TechPad to front from any application, or minimizes it if active. |

---

## 3. URL Auto-Detection & Browser Launching

`TechPadEditor` automatically detects and formats web addresses (`https://...`, `http://...`, `www....`):
- **Typing Auto-Link:** When typing a URL and pressing `Space` or `Enter`, the preceding word is converted in-place to a styled HTML hyperlink (`<a href="..." style="color: #4fc1ff; text-decoration: underline;">...</a>`).
- **Pasting Auto-Link:** When pasting plain text containing URLs, the text is scanned with regex and bare URLs are converted into clickable links.
- **Pointing Hand Cursor:** Hovering the mouse over any link changes the cursor to `Qt.PointingHandCursor` and displays a tooltip previewing the target URL.
- **Click to Launch:** Clicking an anchor opens the link in the technician's default web browser via `QDesktopServices.openUrl()`.

---

## 4. Two-Row Top Header Architecture & Micro-Controls

The top header is structured into two dedicated rows to prevent button truncation and completely eliminate the 3-dots (`...`) toolbar overflow menu on standard display resolutions:

### 4.1 Row 1: Note Formatting, Styling & Markup Ribbon
Dedicated strictly to rich-text authoring, colors, and content markup:
- **Text Styling:** Bold (`B`), Italic (`I`), Underline (`U`)
- **Colors:** Text Color picker (`🎨`), Text Highlight background picker (`🖍️`)
- **Developer Markup:** Monospace CLI container (`</>`), Log Badges dropdown (`🏷️ Tag` for `PASS`, `FAIL`, `WARN`, `INFO`)
- **Checklists:** Dedicated Interactive Checkbox button (`☑ Checkbox` / `Ctrl+Alt+L`)
- **Injections:** Current timestamp injection (`🕒`), Screenshot/Image file insertion (`🖼️`)

### 4.2 Row 2: Ticket Workflow, Skeletons & Utilities Ribbon
Dedicated to ticket-level actions, troubleshooting duration, translucency, and preferences:
- **Ticket Stopwatch (`⏱️`):** Live Consolas monospace counter (`⏱️ HH:MM:SS`), crisp Unicode Play/Pause (`▶`/`⏸`), and Reset (`↺`).
- **Ticket Templates (`📋 Template`):** Structured Skeleton templates (Incident Triage, Quick Fix, Maintenance).
- **PSA Ticket Export (`📤 Copy Note`):** Copies clean Markdown/plain-text note with converted `- [ ] ` checkboxes.
- **Window Opacity Slider (`👁️ 100%`):** Translucency control from 60% to 100% positioned naturally alongside workflow tools without artificial expanding voids.
- **Split View Toggle (`◫` / `Alt+Z`):** Instant side-by-side dual ticket editing with draggable 6px divider.
- **History Drawer Toggle (`🕰️`):** Quick 1-click toggle for the History & Archival drawer.
- **Settings Gear (`⚙️`):** Launches preferences modal for defaults, delays, and compression.
- **Zero Whitespace & Zero Overflow:** Both rows feature balanced, compact grouping without artificial `QSizePolicy.Expanding` gaps, keeping all tools within easy reach while completely eliminating the 3-dots overflow button.
- **Auto-Pause on Lock or 5-Minute Inactivity:**
  - Uses Windows system APIs (`user32.dll:GetLastInputInfo` and `user32.dll:OpenInputDesktop`).
  - If the technician locks their screen (`Win + L`) or leaves the workstation idle for more than 5 minutes (300 seconds), the stopwatch automatically pauses to prevent accidental billing overages.
  - Clicking `▶️` or switching tabs clears the auto-pause state and resumes active tracking.

### 4.3 System Tray Lifecycle & F8 Global Hotkey
TechPad stays resident in the Windows system tray (`QSystemTrayIcon`) to ensure instantaneous access without cold reboots:
- **Minimize to Tray on Close:** Clicking `✕` closes the main window to the system tray rather than terminating the process. Unsaved note edits and active session states are synchronously flushed to SQLite before hiding. A toast notification confirms background execution.
- **System-Wide `F8` Hotkey:**
  - Registered via Win32 `RegisterHotKey` (`VK_F8 = 0x77`).
  - **When hidden, minimized, or inactive:** Pressing `F8` immediately restores the window (`SW_RESTORE`), brings it to the foreground (`SetForegroundWindow`), and sets keyboard focus directly to the active note editor.
  - **When active on the screen:** Pressing `F8` minimizes the window, allowing the technician to instantly return to their terminal, browser, or remote session.
- **Tray Context Menu:**
  - `Show / Hide TechPad (F8)`: Toggles window visibility.
  - `➕ New Ticket Tab (Ctrl+T)`: Unhides window and spawns a fresh ticket scratchpad.
  - `✕ Quit TechPad`: Performs complete teardown, unregisters global hotkeys, and cleanly terminates the process.

---

## 5. Technician Micro-Controls

### 5.1 Monospace Code Block (`</>`)
Inserts a container designed for CLI commands, event logs, and IP tables:
```html
<div style="background-color: #252526; border: 1px solid #3c3c3c; border-radius: 4px; padding: 6px; font-family: Consolas, monospace; color: #9cdcfe;">
    <code># CLI / PowerShell Output</code>
</div>
```

### 5.2 Log Triage Color Badges
One-click badges highlight critical event states inline:
- `🟢 PASS`: Green background (`#1b4d24`), text (`#4ade80`), border (`#22c55e`).
- `🔴 FAIL`: Red background (`#521616`), text (`#f87171`), border (`#ef4444`).
- `🟡 WARN`: Amber background (`#543810`), text (`#facc15`), border (`#eab308`).
- `ℹ️ INFO`: Blue background (`#1e3a5f`), text (`#60a5fa`), border (`#3b82f6`).

### 5.3 Structured Ticket Skeletons (`📋`)
A dropdown menu provides instant structured outlines:
- **Standard Incident Triage:** Sections for `[ISSUE DESCRIPTION]`, `[DIAGNOSTICS & TROUBLESHOOTING]`, `[ROOT CAUSE]`, and `[RESOLUTION STEPS]`.
- **Quick Triage / Quick Fix:** Brief fields for Caller, Problem, Action Taken, and Status.
- **Maintenance & Change Plan:** Outline covering Target Host, Pre-Execution Checks, Execution Steps, Post-Verification, and Rollback Plan.

### 5.4 "Copy Note" Dual Workflows (`📋` / `📤`)
The ribbon toolbar provides a dual-action popup button (`QToolButton.MenuButtonPopup`):
- **Click Button Directly or `Ctrl+Shift+C`:** Copies the entire active note with **Rich Text & Images** (see Section 8). Full HTML formatting, colors, bold/italics, code blocks, and embedded Base64 images are copied for pasting into Microsoft Word, Outlook, Teams, Slack, and Google Docs.
- **Dropdown Menu or `Ctrl+Alt+N` ("Copy Clean Note for Ticket Tool"):** Invokes `ScratchpadService.export_as_plain_ticket_note()`:
  1. Generates a clean ticket header (`=== TICKET: INC-4092 ===`).
  2. Converts HTML headings (`<h3>`) into Markdown headers (`###`).
  3. Formats bullet points (`• `) and bold items (`**...**`).
  4. Converts monospace blocks into markdown fences (```...```).
  5. Replaces internal image URIs with clean placeholders (`[Screenshot: <uuid>.jpg]`).
  6. Converts interactive task anchors (`task://toggle`) into standard Markdown checkboxes (`- [ ] ` and `- [x] `).
  7. Strips all remaining tags and copies clean plain text to the clipboard with status bar confirmation.

---

## 6. Interactive Task Checklists & Action Items

To streamline multi-step incident troubleshooting, server maintenance checklists, and ticket resolution procedures, `TechPadEditor` features native, clickable task lists with live tab status badges:

### 6.1 Checkbox Architecture & URI Scheme (`task://toggle`)
Checklist items utilize custom HTML anchor tags that map directly into Qt's `QTextDocument` resource tree:
- **Unchecked Item:**
  ```html
  <a href="task://toggle" style="text-decoration:none; color:#007acc; font-weight:bold; font-family:Consolas, monospace;">[ ]</a> Task Description
  ```
- **Completed Item:**
  ```html
  <a href="task://toggle" style="text-decoration:none; color:#4ade80; font-weight:bold; font-family:Consolas, monospace;">[✔]</a> <span style="text-decoration: line-through; color: #888888;">Task Description</span>
  ```

### 6.2 1-Click Interactive Toggling
- **Mouse Hover:** Hovering over any `[ ]` or `[✔]` anchor changes the cursor to `Qt.PointingHandCursor` and renders a tooltip: *"Click to toggle task completion"*.
- **Click Routing:** `mouseReleaseEvent()` intercepts clicks on `task://toggle` anchors (as well as direct clicks within bracket bounds). It immediately toggles the symbol between `[ ]` (accent blue `#007acc`) and `[✔]` (success green `#4ade80`), and toggles strikethrough styling (`#888888`) across the remaining line text without launching an external browser.
- **Real-Time Signal Dispatch:** Toggling emits `checklist_stats_changed(scratchpad_id, completed, total)`, immediately updating the active tab title badge.

### 6.3 Smart Typing Auto-Conversions
- **Markdown Typing Trigger:** Typing `[] `, `[ ] `, or `- [ ] ` at the start of any line followed by `Space` automatically transforms the typed text in-place into an interactive checklist anchor.
- **Enter Key List Continuation:**
  - Pressing `Enter` on a non-empty checklist line automatically starts a new unchecked task (`[ ] `) on the subsequent line.
  - Pressing `Enter` on an empty checklist line erases the empty checkbox and converts the line into a normal blank paragraph, smoothly exiting checklist authoring mode.

### 6.4 Micro-Controls & Access Points
1. **Toolbar Button:** Dedicated `☑ Task` button on Row 1 formatting toolbar.
2. **Keyboard Shortcut:** `Ctrl+Alt+L` instantly inserts an interactive checklist item at current cursor position.
3. **Context Menu:** Right-clicking anywhere in the editor offers `☑ Insert Checklist Item (Ctrl+Alt+L)`.

### 6.5 Clean Ticketing System Export (PSA / Markdown)
When exporting notes via **📤 Copy Note** (`Ctrl+Alt+N`) or copying note text with elapsed billable time:
- `ScratchpadService.convert_html_to_clean_text()` automatically converts `<a href="task://toggle">[ ]</a>` into standard Markdown `- [ ] `.
- Automatically converts `<a href="task://toggle">[✔]</a>` into standard Markdown `- [x] `.
- This ensures notes copied into PSA ticket portals (ConnectWise, ServiceNow, Jira, GitHub Issues) render clean, native markdown checkboxes with zero proprietary HTML tags.

---

## 7. Image Context Menu: Copy & Save As...

When right-clicking on any embedded screenshot or image in `TechPadEditor`:
- **📋 Copy Image:** Copies the full-resolution bitmap directly into the system clipboard (`QApplication.clipboard().setImage`), ready to paste (`Ctrl+V`) into external applications such as Slack, Microsoft Teams, Outlook, Word, or Jira.
- **💾 Save Image As...:** Opens a file dialog allowing export to `.png` (lossless) or `.jpg` (raw original bytes without recompression artifacts).
- Both actions display instantaneous feedback in the window status bar (`✓ Copied image to clipboard!` / `✓ Saved image to <path>`).

---

## 8. Rich Text, Color & Image Clipboard Pipeline

When copying highlighted selections or copying the entire note for use in other applications:

### 8.1 Base64 Data URI Image Embedding
- **Automatic Translation:** Overrides `TechPadEditor.createMimeDataFromSelection()`. Any embedded image referencing `image://local/<uuid>.jpg` is automatically retrieved from memory cache (`in_memory_images`) or the database repository, converted into JPEG bytes, Base64-encoded, and embedded inline as `data:image/jpeg;base64,...` in the `text/html` clipboard fragment.
- **External Compatibility:** Microsoft Word, Microsoft Outlook, Microsoft Teams, Slack, Google Docs, Gmail, Chrome, Edge, and Confluence natively parse `data:image/jpeg;base64,...` inside incoming `CF_HTML` clipboard data, rendering text formatting, custom colors, bold/italics, code blocks, and images together with zero broken links.
- **Standalone Image Handling:** If a user selects only an image (with no accompanying text), `mime_data.setImageData(first_qimage)` is populated to support image-only target apps (e.g. MS Paint, photo editors).
- **Clean Plain-Text Fallback:** In the plain-text clipboard representation (`text/plain`), the Unicode object replacement character `\uFFFC` is automatically replaced with `[Screenshot]` to avoid broken box characters when pasting into text terminals or Notepad.

### 8.2 Access Points & Shortcuts
1. **Highlight & Copy:** Select any text and images using mouse or `Ctrl+A`, then press `Ctrl+C` or right-click `Copy`.
2. **Copy Note Button (`📋 Copy Note`):** Click the ribbon button directly or press `Ctrl+Shift+C` to copy the entire active note formatted with rich text and images.
3. **Tab Context Menu:** Right-click any primary or secondary tab header and choose `📋 Copy Formatted Note (Rich Text & Images)`.
4. **Editor Context Menu:** Right-click anywhere inside the editor and choose `📋 Copy Entire Formatted Note (Ctrl+Shift+C)`.



---

## 9. M365 Adaptive & High-DPI Viewport Layout

To support compact displays and Windows high-DPI scaling (125% and 150% scaling on 1280x720 and 1600x900 screens):

### 9.1 Responsive Column Reflow (1-Column vs 2-Column)
- **Viewport Width Detection:** `M365LauncherWidget` dynamically measures center viewport width in `resizeEvent`.
- **Adaptive Stacking:** When available center width is `< 500px`, the 6 administrative sections automatically reflow into a single vertical column (`index, 0`), ensuring titles like `"Authentication & Tenant Context"` have ample horizontal space without clipping or truncation.
- **2-Column Mode:** When center width is `>= 500px`, sections arrange in a balanced `3x2` grid.
- **Instance Preservation:** Rearrangement retains identical widget instances without recreating or re-instantiating widgets during resizing.

### 9.2 Collapsible Navigation & Active Ticket Sidebars
- **Collapsible Splitter:** `workspace_splitter.setChildrenCollapsible(True)` allows both sidebars to collapse down cleanly.
- **Category Navigation Toggle:** A compact `☰ Categories` toggle button (`nav_toggle`) allows collapsing the left list to reclaim 130px+ of horizontal space on narrow screens.
- **Active Ticket Notes Toggle:** The `Active Ticket Notes (future)` toggle button (`ticket_panel_toggle`) allows hiding the right sidebar placeholder to reclaim 140px+ for the main workspace.
- **State Preservation:** Navigation selection, scroll position, and panel collapsed/expanded states survive across Alt+F8 workspace switches.

### 9.3 Workspace-Specific Minimum Dimensions & Bounds Clamping
- **M365 Minimum Size:** Set to `640x380` on entering M365 workspace, allowing the window to fit comfortably within 720p displays at 150% scaling without pushing bottom content off-screen.
- **Notes Minimum Size:** Restored to `660x400` when returning to Notes, preserving the two-row formatting ribbon, tabs, and editor on portrait monitors down to 700 logical pixels.
- **Geometry Clamping:** Restoring normal geometry from Mini-HUD clamps window boundaries to the active monitor's available desktop work area (`screen.availableGeometry()`), preventing off-screen window drift.

### 9.4 Save Barrier & Data Integrity on Workspace Switch and Exit
- **Atomic Save Barrier (`flush_all_saves() -> bool`):** Before switching to the M365 Launcher or closing the application, all active debounce timers and dirty scratchpad IDs are immediately flushed and saved to SQLite.
- **Save Status Accuracy:** If any ticket fails to persist or dirty notes remain, the status bar displays `● Save Failed` in bold red (never falsely showing `● Saved`).
- **Guarded Navigation & Refused Exit:** Failed saves immediately abort workspace switching (`show_m365_workspace()` returns `False`), and `closeEvent()` calls `event.ignore()` with a status bar alert to keep the window open and preserve all in-memory drafts and images. Subsequent user actions cleanly retry the stopped timers without data loss.

---

## 10. Responsive Formatting Toolbar, History Drawer & Split View

To support portrait monitors (e.g. 1050x1680 at 150% scaling yielding a 700-logical-pixel viewport) and constrained screen widths:

### 10.1 Responsive Formatting Toolbar (`TechPadToolBar`)
- **Normal Mode (width >= 800px):** All primary formatting tools, log triage badge selector, timestamp, and screenshot buttons are displayed directly inline on row 1. Overflow action button `More ▾` is hidden.
- **Compact Mode (width < 775px):** Secondary tools (`act_badge`, `act_timestamp`, `act_image`) automatically move their toolbar representations into the compact `More ▾` popup menu (`btn_more` / `menu_more`). Dedicated toolbar button widgets (`act_timestamp_btn`, `act_image_btn`) are hidden from the toolbar row, while their underlying `QAction` objects remain active and visible in the `More ▾` menu. All keyboard shortcuts (`Alt+1..4`, `F5`/`Ctrl+Alt+T`, `Ctrl+Alt+I`) remain fully operational with 100% action parity. Triggering any action from the `More ▾` menu restores keyboard focus to the active `TechPadEditor`.
- **Hysteresis:** Thresholds (compact < 775px, normal >= 800px) prevent resize flickering or oscillating layouts during window dragging.
- **Secondary Micro-Toolbar Adaptations:** Under compact mode, `Copy Note` shortens to `Copy`, `Template` shortens, and opacity slider width contracts from 85px to 50px, ensuring row 2 controls never clip or overflow.
- **M365 Launcher Button:** Positioned on the left side of the bottom status bar, placed 2nd between the HUD and Split buttons, persistently accessible across all window widths and in HUD mode. While in the M365 PowerShell Launcher module, this button dynamically transforms into 'T-Notes', remaining enabled to permit seamless bidirectional toggling between T-Notes and M365 Launcher in normal and HUD modes.

### 10.2 Responsive History Drawer Auto-Collapse
- **Automatic Collapse:** When horizontal workspace width falls below 850px, the History drawer automatically hides (`history_auto_collapsed = True`) to prioritize the active ticket editor canvas.
- **Automatic Restoration:** When width expands to 900px or greater, the History drawer automatically reopens (`history_auto_collapsed = False`).
- **User Intent Preservation:** The user's explicit visibility preference (`_user_history_drawer_open`) is tracked separately from responsive overrides. If the user explicitly toggles the drawer (via `Ctrl+H` or toolbar button) while in narrow mode, their explicit choice takes precedence and clears the auto-collapse flag.
- **Session Persistence Safety:** Saving workspace state on window close records the user's explicit preference, ensuring an auto-collapsed drawer is never permanently marked as closed in persistent session storage.

### 10.3 Responsive Compact Split View (Single-Pane Mode)
- **Automatic Single-Pane Transition:** When Split View is active and window width falls below 750px, the workspace automatically collapses to display only one editor pane (`split_auto_single_pane = True`).
- **Active Pane Retention:** The currently focused ticket editor remains visible, while the inactive split pane is hidden.
- **Pane Switcher Control:** A status bar button (`⇋ Switch Pane (Alt+Shift+Z)`) appears dynamically in compact mode, allowing technicians to toggle between primary and secondary panes.
- **Data & Identity Integrity:** Both `TechPadTabWidget` instances, `TechPadEditor` widgets, `QTextDocument` structures, undo stacks, in-memory images, and scratchpad IDs remain alive and unmodified. Auto-save continues flushing modifications in either pane without data loss.
- **Side-by-Side Restoration:** When window width expands to 780px or greater, two-pane side-by-side editing is restored with previously saved splitter proportions.

### 10.4 Right-Sidebar Mini-HUD Mode & Down-Left Status Control
- **Right-Sidebar Docking & Elongated Height:** Mini-HUD mode (`Alt+T`) docks TechPad as an always-on-top right sidebar (`Qt.WindowStaysOnTopHint`) positioned along the right edge of the monitor's available screen geometry (`sidebar_x = avail.x() + avail.width() - sidebar_width`, `sidebar_width = min(440, avail.width())`).
- **Taskbar Boundary Clamping & Frame Metric Compensation:** To prevent the bottom status bar from submerging behind the Windows taskbar, HUD mode calculates native window frame decorations (`extra_h = frameGeometry().height() - geometry().height()`, `title_h = max(0, geometry().y() - frameGeometry().y())`). Client height is bounded to `avail.height() - extra_h` and client Y is set to `avail.y() + title_h`. Furthermore, `setMaximumHeight(avail.height() - extra_h)` and dynamic clamping in `resizeEvent` and `moveEvent` (`_clamp_hud_geometry()`) ensure manual window resizing or moving never extends the window frame past `screen.availableGeometry().bottom()`. Exiting HUD mode cleanly resets `maximumHeight` to restore standard unconstrained window resizing.
- **Left-Side Bottom Bar Module Clusters:** The bottom bar provides module-aware controls positioned at the exact same left emplacement in both standard workspace mode and HUD mode:
  - **T-Notes Module:** Features `HUD` -> `M365 Launcher` -> `Split` -> `History`. The `Split` and `History` buttons belong strictly to T-Notes and are visible exclusively within this module.
  - **M365 PowerShell Launcher Module:** When viewing M365 Launcher, `Split` and `History` are removed from the bottom bar and replaced with `Categories` (which toggles the left navigation sidebar) and `Active Ticket` (which toggles the right active ticket sidebar): `HUD` -> `T-Notes` -> `Categories` -> `Active Ticket`. Both buttons feature bidirectional synchronization with the launcher's sidebar toggles (`nav_toggle` and `ticket_panel_toggle`).
- **Tabs Bar Navigation Arrows (`◀` and `▶`):** In HUD mode, left (`btn_prev` at `Qt.TopLeftCorner`) and right (`btn_next` at `Qt.TopRightCorner`) arrow buttons are displayed on the tabs bar, allowing technicians to quickly cycle through open ticket tabs in the narrow sidebar with automatic wrap-around, active editor focus, and title updates.
- **Persistent Visibility During Status Messages:** Connected to `status_bar.messageChanged` to ensure the left-side bottom bar buttons (`HUD`, `M365 Launcher`, `Split`, `History`) remain persistently visible even when temporary notification messages are posted to the status bar.
- **Clean Sidebar Layout:** Top formatting toolbars are automatically hidden in HUD mode to eliminate crowding and keep focus on the active ticket note, while core window controls remain accessible along the bottom bar.


## Revision-bound save acknowledgement

Each live ticket has a monotonic in-session revision incremented by content/image
changes. Saving snapshots HTML, pending JPEG bytes and that revision synchronously.
`SaveReceipt(ticket_id, attempted_revision, persisted_revision, status, error_code)`
acknowledges `saved` only after the repository transaction commits. Exceptions
produce no saved receipt and retain dirty IDs, undo state, document and images.
The coordinator rejects stale/mismatched acknowledgements and keeps newer edits
dirty. Ctrl+S retries the latest snapshot, including when no debounce timer remains
active. Creating a new ticket cannot display Saved while another ticket is dirty.
This is an application persistence receipt, not a PowerShell wire schema, approved
M365 adapter or contract release.
