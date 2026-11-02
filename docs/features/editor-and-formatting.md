# Rich-Text Editor & Technician Formatting Tools

## 1. Overview
The note-taking canvas in T-Notes is built upon `TechPadEditor`, a heavily customized `QTextEdit` component integrated with `TechPadToolBar`. It balances rich-text capabilities (bold, italics, colors, embedded images) with developer-grade controls (monospace CLI blocks, timestamping, triage badges, and clean markdown export).

---

## 2. Keyboard Shortcuts & Formatting Actions

| Action | Shortcut | Description |
| :--- | :--- | :--- |
| **Bold** | `Ctrl+B` | Toggles bold font weight for selected text. |
| **Italic** | `Ctrl+I` | Toggles italic text style. |
| **Underline** | `Ctrl+U` | Toggles text underline. |
| **Insert Timestamp** | `Ctrl+Shift+T` | Injects current local timestamp in format `[YYYY-MM-DD HH:MM:SS]`. |
| **Monospace Code Block** | Toolbar `</>` | Formats selected text or inserts a dark monospace container block for CLI/PowerShell output. |
| **New Tab** | `Ctrl+T` | Creates a new ticket scratchpad tab. |
| **Close Tab** | `Ctrl+W` | Prompts to archive or delete the active ticket tab. |
| **Force Save** | `Ctrl+S` | Immediately flushes all debounced writes to SQLite. |
| **Toggle History Drawer** | `Ctrl+H` | Collapses or expands the ticket archive drawer. |

---

## 3. Technician Micro-Controls

### 3.1 Monospace Code Block (`</>`)
Inserts a container designed for CLI commands, event logs, and IP tables:
```html
<div style="background-color: #252526; border: 1px solid #3c3c3c; border-radius: 4px; padding: 6px; font-family: Consolas, monospace; color: #9cdcfe;">
    <code># CLI / PowerShell Output</code>
</div>
```

### 3.2 Log Triage Color Badges
One-click badges highlight critical event states inline:
- `🟢 PASS`: Green background (`#1b4d24`), text (`#4ade80`), border (`#22c55e`).
- `🔴 FAIL`: Red background (`#521616`), text (`#f87171`), border (`#ef4444`).
- `🟡 WARN`: Amber background (`#543810`), text (`#facc15`), border (`#eab308`).
- `ℹ️ INFO`: Blue background (`#1e3a5f`), text (`#60a5fa`), border (`#3b82f6`).

### 3.3 Structured Ticket Skeletons (`📋`)
A dropdown menu provides instant structured outlines:
- **Standard Incident Triage:** Sections for `[ISSUE DESCRIPTION]`, `[DIAGNOSTICS & TROUBLESHOOTING]`, `[ROOT CAUSE]`, and `[RESOLUTION STEPS]`.
- **Quick Triage / Quick Fix:** Brief fields for Caller, Problem, Action Taken, and Status.
- **Maintenance & Change Plan:** Outline covering Target Host, Pre-Execution Checks, Execution Steps, Post-Verification, and Rollback Plan.

### 3.4 "Copy for Ticket Note" (PSA Export `📤`)
Technicians often take rich notes with images and colors but must paste them into ticketing portals (ServiceNow, HaloPSA, Jira, ConnectWise) that reject messy HTML.

Clicking **"Copy Note"** invokes `ScratchpadService.export_as_plain_ticket_note()`:
1. Generates a clean ticket header (`=== TICKET: INC-4092 ===`).
2. Converts HTML headings (`<h3>`) into Markdown headers (`###`).
3. Formats bullet points (`• `) and bold items (`**...**`).
4. Converts monospace blocks into markdown fences (```...```).
5. Replaces internal image URIs with clean placeholders (`[Screenshot: <uuid>.jpg]`).
6. Strips all remaining tags and copies the plain text to the clipboard with a status bar confirmation.

---

## 4. Clickable Hyperlinks
`TechPadEditor.mousePressEvent()` inspects `anchorAt(event.pos())`. If the technician clicks on an `http://`, `https://`, or `mailto:` link, the URL is opened directly in their default web browser via `QDesktopServices.openUrl()`.

