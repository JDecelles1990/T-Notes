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

---

## 3. URL Auto-Detection & Browser Launching

`TechPadEditor` automatically detects and formats web addresses (`https://...`, `http://...`, `www....`):
- **Typing Auto-Link:** When typing a URL and pressing `Space` or `Enter`, the preceding word is converted in-place to a styled HTML hyperlink (`<a href="..." style="color: #4fc1ff; text-decoration: underline;">...</a>`).
- **Pasting Auto-Link:** When pasting plain text containing URLs, the text is scanned with regex and bare URLs are converted into clickable links.
- **Pointing Hand Cursor:** Hovering the mouse over any link changes the cursor to `Qt.PointingHandCursor` and displays a tooltip previewing the target URL.
- **Click to Launch:** Clicking an anchor opens the link in the technician's default web browser via `QDesktopServices.openUrl()`.

---

## 4. Top Header Micro-Controls

### 4.1 Opacity Slider (60% to 100%)
Positioned at the top right of the application toolbar:
- Range: `60%` (translucent) to `100%` (fully opaque).
- Live adjustment via `window.setWindowOpacity(val / 100.0)`.
- Use Case: Enables technicians to read background CLI output, server management consoles, or remote desktop sessions behind the scratchpad while taking troubleshooting notes.
- Saved across restarts in `app_session`.

### 4.2 Settings Gear Icon (`⚙️`)
Clicking `⚙️` or pressing `Ctrl+,` opens `SettingsDialog`:
- **Default Ticket Prefix:** Custom prefix for new tabs (e.g. `INC-`, `REQ-`, `T-`).
- **Auto-Save Delay:** Configurable debounce delay between 500ms and 5000ms (default 1500ms).
- **Screenshot JPEG Quality:** Compression quality slider (50% to 100%, default 85%).
- **Tab Close Action:** Choice between prompting or immediately archiving to the History Drawer.
- **Default Opacity:** Default window translucency on startup.

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
6. Strips all remaining tags and copies the plain text to the clipboard with a status bar confirmation.
