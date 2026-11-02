# Rich-Text Editor & Technician Formatting Tools

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
- **Ticket Stopwatch & MSP Billing (`⏱️`):** Live Consolas monospace counter (`⏱️ HH:MM:SS`), crisp Unicode Play/Pause (`▶`/`⏸`), Reset (`↺`), and `📋 Time` dropdown (Exact, Decimal, 15m rounded blocks, Copy Note with billable time).
- **Ticket Templates (`📋 Template`):** Structured Skeleton templates (Incident Triage, Quick Fix, Maintenance).
- **PSA Ticket Export (`📤 Copy Note`):** Copies clean Markdown/plain-text note with converted `- [ ] ` checkboxes.
- **Window Opacity Slider (`👁️ 100%`):** Translucency control from 60% to 100% positioned naturally alongside workflow tools without artificial expanding voids.
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

### 5.4 "Copy for Ticket Note" (PSA Export `📤`)
Clicking **"Copy Note"** invokes `ScratchpadService.export_as_plain_ticket_note()`:
1. Generates a clean ticket header (`=== TICKET: INC-4092 ===`).
2. Converts HTML headings (`<h3>`) into Markdown headers (`###`).
3. Formats bullet points (`• `) and bold items (`**...**`).
4. Converts monospace blocks into markdown fences (```...```).
5. Replaces internal image URIs with clean placeholders (`[Screenshot: <uuid>.jpg]`).
6. Converts interactive task anchors (`task://toggle`) into standard Markdown checkboxes (`- [ ] ` and `- [x] `).
7. Strips all remaining tags and copies the plain text to the clipboard with a status bar confirmation.

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
