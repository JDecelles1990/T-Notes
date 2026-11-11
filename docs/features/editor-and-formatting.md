# Rich-Text Editor & Technician Formatting Tools

## S001 workspace shortcut boundary

The S001 candidate suspends existing Notes QActions (including nested toolbar-menu
actions), Ctrl+S, Ctrl+F, Ctrl+H, Alt+H, Ctrl+comma and Alt+Z shortcuts while M365 is displayed.
Its application event filter bypasses ticket Ctrl+T/W/F4/Tab/PageUp/PageDown/number
handling there, preventing accidental edits, closing or reordering of hidden tabs.
Back restores exact prior enabled states, including previously disabled actions.
Notes shortcut behavior is unchanged. F8 remains global; Alt+T returns to Notes
before existing Mini-HUD behavior. Back and ticket-placeholder collapse controls
are keyboard-focusable; Space activates Back.

The original editor retains document, cursor/selection, undo and image resources.
The M365 page binds its Active Ticket sidebar directly to the focused note's document
using shared in-memory document architecture (`setDocument()`), providing full formatting,
stopwatch time tracking, image insertion, and rich note copying without architectural drift.

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
| **Find in Note** | `Ctrl+F` | Opens the floating in-editor search overlay bar. |
| **Replace in Note** | `Ctrl+H` | Opens the floating in-editor search and replace overlay bar. |
| **Bold** | `Ctrl+B` | Toggles bold font weight for selected text. |
| **Italic** | `Ctrl+I` | Toggles italic text style. |
| **Underline** | `Ctrl+U` | Toggles text underline. |
| **Monospace Code Block** | `Ctrl+Alt+C` | Formats selected text or inserts a dark monospace container block. |
| **Insert Checklist Item** | `Ctrl+Alt+L` | Inserts an interactive task checklist item (`[ ]`) at current line. |
| **Insert Timestamp** | `F5` / `Ctrl+Alt+T` | Injects current timestamp in format `[YYYY-MM-DD HH:MM:SS]`. |
| **Insert Image File** | `Ctrl+Alt+I` | Prompts file picker to insert screenshot or image. |
| **Ticket Skeletons** | `Ctrl+Alt+S` | Opens template skeleton menu. |
| **Copy for PSA Note** | `Ctrl+Alt+N` | Exports clean Markdown/plain-text stripped of HTML to clipboard. |
| **Export Note to File** | `Ctrl+Alt+E` | Exports clean plain-text active ticket note to daily folder in `T-Notes\`. |
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
- **Ticket Templates (`📋 Template`):** Structured Skeleton templates (Incident Triage, Quick Fix, Maintenance) plus customizable user templates via `🔳 Add a new template`.
- **Formatted Note Copy (`📋 Copy Note` / `Ctrl+Shift+C`):** Copies all text formatting (colors, bold, monospace code containers, checklist states) and embedded images (converted to Base64 data URIs) of the **Active Ticket note** (the pane/tab where the text cursor is currently placed, in either Split View side panel or main window) into the Windows Clipboard. Also provides dropdown actions for clean plain Markdown exports (`📤 Copy Clean Note for Ticket Tool` / `Ctrl+Alt+N`) and direct plain-text file export (`💾 Export Note (T-Notes Folder)` / `Ctrl+Alt+E`).
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

### 5.3 Structured Ticket Skeletons (`📋`) & Custom Template Management
A dropdown menu provides instant structured outlines and complete custom template lifecycle controls:
- **Standard Incident Triage:** Sections for `[ISSUE DESCRIPTION]`, `[DIAGNOSTICS & TROUBLESHOOTING]`, `[ROOT CAUSE]`, and `[RESOLUTION STEPS]`.
- **Quick Triage / Quick Fix:** Brief fields for Caller, Problem, Action Taken, and Status.
- **Maintenance & Change Plan:** Outline covering Target Host, Pre-Execution Checks, Execution Steps, Post-Verification, and Rollback Plan.
- **Custom Template Management (`🔳 Add a new template`):** Selecting `🔳 Add a new template` launches the unified `AddTemplateDialog` modal equipped with creation, modification, and deletion workflows:
  - **Template Selector & Mode Switcher:** Top row dropdown allows choosing between `➕ [Create New Template]` and any previously created custom templates (`📋 <title>`). A dedicated `➕ New Template` button allows resetting back to create mode with one click.
  - **Mode Badge Indicator:** Displays current operational state (`Mode: Create New` in electric blue vs. `Mode: Modify (#<id>)` in emerald green).
  - **Modify Existing Templates:** Selecting an existing template immediately populates the Title field and editor canvas, updates the dialog window title to `Modify Template — <title>`, shifts the primary action button to `Update Template`, and reveals the red `🗑️ Delete Template` button. Saving commits atomic updates to SQLite (`custom_templates`) and immediately synchronizes toolbar menus.
  - **Delete Existing Templates:** Clicking `🗑️ Delete Template` prompts an explicit safety confirmation dialog (`QMessageBox.question`). Once confirmed, the template is permanently deleted from SQLite, removed from the dropdown list, fields are cleared, and the mode is smoothly reset back to create mode. Menus in both the T-Notes toolbar and M365 Launcher are refreshed immediately.
  - **Template Title & Rich-Text Canvas:** Title input with duplicate-name validation, plus a full-featured `TemplateEditor` with rich formatting (Bold, Italic, Underline, Strikethrough, Text Color, Highlight Color, Headings H1-H3, Bullet & Numbered Lists, Monospace Code Block, and Embedded Images).
  - **Vibrant Glowing Button Animations:** All interactive buttons (Save/Update, New, Delete, Cancel, and formatting tool buttons) are wrapped with `apply_glow_to_buttons` to deliver vibrant cycling glow effects on hover and press flares matching the T-Notes dark theme.
  - **Insertion at Cursor:** Selecting any custom template from the dropdown menu inserts its formatted content directly at the active cursor position in the focused note editor.

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

### 5.5 Active Ticket Plain-Text File Export (`💾 Export Note` / `Ctrl+Alt+E`)
The `Copy Note` dropdown menu features `💾 Export Note (T-Notes Folder)` (shortcut `Ctrl+Alt+E`), which exports the active ticket unformatted plain-text note directly into the project repository folder:
- **Active Ticket Reconnaissance & Split View Scope:** Automatically resolves whichever ticket editor currently holds cursor placement or focus, across the primary tab editor, secondary Split View sidebar pane, or M365 Launcher right sidebar. When typing or clicking in a Split View side-panel ticket tab, the application immediately recognizes that tab as the Active Ticket, ensuring `Export Note` writes the Split panel note rather than defaulting to the main window's tab.
- **Pure Plain Text:** Strips all HTML markup, formatting tags, image binaries, and embedded image placeholders (`\uFFFC`).
- **Save Location:** Saved into a daily subfolder inside `C:\Dev\T-Notes\T-Notes\`:
  `C:\Dev\T-Notes\T-Notes\<YYYY-MM-DD>\` (e.g. `C:\Dev\T-Notes\T-Notes\2026-11-04\`). The subfolder is automatically created if it does not exist.
- **Filename Assembly:** Built by sanitizing components and joining them with underscores:
  - If client name is present: `{ticket_name}_{client_name}_{YYYY-MM-DD_HHh}.txt` (e.g. `INC-2020_Wayne_Enterprises_2026-11-04_14h.txt`).
  - If client name is absent: `{ticket_name}_{YYYY-MM-DD_HHh}.txt`.
- **Same-Hour Overwrite:** If triggered multiple times within the same hour, the file cleanly overwrites itself within the day's folder, allowing technicians to save frequently without folder clutter.
- **Status Bar Feedback:** Confirms successful export with relative path notification (e.g. `✓ Exported note (#INC-2020) to T-Notes/2026-11-04/INC-2020_Wayne_Enterprises_2026-11-04_14h.txt`).

---

### 5.6 Interactive Image Resizing & Split-View Fitting
`TechPadEditor` allows embedded screenshots and images to be resized interactively in both standard/normal editor views and side-by-side Split View sidebar panes:
- **Interactive Corner Dragging:**
  - Clicking any embedded image reveals an accent selection outline (`#007acc`) and bottom-right corner resize handle.
  - Hovering over the handle displays a diagonal resize cursor (`Qt.SizeFDiagCursor`).
  - Dragging the handle resizes the image with a live dashed bounding box and dimension pill (e.g. `450 × 225 px`).
  - Aspect ratio is locked by default for proportional scaling; holding `Shift` unlocks independent width/height resizing.
- **Context Menu Quick Resize (`📏 Quick Resize`):**
  - Right-clicking an image reveals quick scaling presets: `Fit to Pane Width`, `100% (Original Size)`, `75%`, `50%`, `25%`.
  - `Fit to Pane Width` automatically computes available editor space (`viewport().width() - 24`), perfectly fitting large images into the narrower Split View side panel without horizontal scrolling.
- **Custom Dimension Modal (`📐 Custom Resize...` / Double-Click):**
  - Double-clicking an image launches `ResizeImageDialog` with Width and Height spinboxes, aspect ratio locking, and one-click percentage presets.

---

### 5.7 In-Note Search & Replace Overlay (`Ctrl+F`)
`TechPadEditor` integrates a floating, VS Code-style search & replace overlay bar (`FindReplaceBar`) positioned at the top-right of the editor canvas:
- **Instant Search-as-You-Type:** Typing immediately scans the document and displays a match count badge (`X of Y` in emerald green, or `0 of 0` in red when no matches exist).
- **Match Highlighting:** Leverages `QTextEdit.ExtraSelection` to provide non-destructive visual highlighting:
  - All matching occurrences across the document are softly tinted in amber (`rgba(100, 75, 0, 0.6)`).
  - The current active match is highlighted with a bright blue accent (`#007acc`).
  - Automatically scrolls the editor viewport to ensure the active match is visible (`ensureCursorVisible()`).
- **Match Navigation:** Navigate forward (`Enter` or `▼`) and backward (`Shift+Enter` or `▲`). Pressing `Ctrl+F` while the bar is open toggles between Find and Replace modes.
- **Match Case Toggle (`Aa`):** Toggles case-sensitive string matching.
- **In-Place Text Replacement:** Clicking `▶` expands the Replace row:
  - `Replace`: Replaces the current active match and jumps immediately to the next match.
  - `Replace All`: Atomically replaces all occurrences in reverse document order within a single edit block (`beginEditBlock()`), preserving undo stack integrity.
- **Quick Dismissal:** Pressing `Esc` or clicking `✕` closes the overlay, removes all highlights, and restores text cursor focus directly to the editor.

---

### 5.8 M365 PowerShell Diagnostic Output Bridge
The M365 Launcher features a direct one-click `📤 Insert into Active Ticket` action:
- **Monospace Container Formatting:** Wraps raw PowerShell script outputs and JSON summaries inside an isolated dark container block:
  ```html
  <div style="background-color: #252526; border: 1px solid #3c3c3c; border-radius: 4px; padding: 8px; font-family: Consolas, monospace; color: #9cdcfe;">
    <div style="color: #4fc1ff; font-weight: bold; margin-bottom: 4px;">=== M365 Output: <script_id> (<timestamp>) ===</div>
    <pre style="margin: 0; white-space: pre-wrap; font-family: Consolas, monospace; color: #cccccc;"><code>...</code></pre>
  </div><br>
  ```
- **Active Ticket Scope:** Injects directly into the focused note editor across either primary, secondary (Split View), or M365 sidebar panels, with status bar notification.
- **Keyboard Deletion:**
  - Pressing `Delete` or `Backspace` while an image is selected immediately deletes the image from the note.

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

## 7. Image Manipulation & Annotation Pipeline: Resize, Draw, Shapes, Text & Colors

Double-clicking any embedded screenshot or image (or choosing **📐 Resize & Annotate Image...** from the right-click context menu) launches the modal `ResizeImageDialog`.

### 7.1 Interactive Visual Annotation Canvas (`ImageAnnotationCanvas`)
Technicians can annotate, call out, and mark up screenshots directly within T-Notes without needing an external image editor:
- **✏️ Freehand Pen (`TOOL_PEN`):** Freeform pen drawing with anti-aliasing and smooth joint caps for circling anomalous log lines or diagram components.
- **⭕ Circle / Ellipse Callout (`TOOL_CIRCLE`):** Interactive click-and-drag ellipse tool with real-time drag preview for highlighting buttons, badges, or error messages.
- **🔲 Rectangle Callout Box (`TOOL_RECTANGLE`):** Interactive click-and-drag rectangle box with real-time drag preview for bounding text blocks or IP configurations.
- **🔤 Text Overlay with High-Contrast Shadow (`TOOL_TEXT`):** Clicking anywhere on the canvas opens a text prompt dialog. Rendered text includes an automated 8-directional drop shadow (dark perimeter outline) to guarantee legibility over both dark backgrounds (terminal consoles) and bright backgrounds (Word/Excel dialogs).
- **🎨 Color Palette & Custom Color Picker:** Instant selection of high-visibility callout colors:
  - 🔴 Red (`#ff3b30`)
  - 🟡 Yellow (`#ffcc00`)
  - 🟢 Green (`#34c759`)
  - 🔵 Cyan (`#00e5ff`)
  - ⚪ White (`#ffffff`)
  - ⚫ Black (`#000000`)
  - Dedicated **🎨 More...** button opening `QColorDialog` for full 24-bit custom color selection.
- **Line Stroke Width Selector:** Switch line thickness between `2px` (fine detail), `4px` (standard callout, default), and `8px` (bold highlight).

### 7.2 Reversible History Stack (Undo, Redo & Reset)
All markup actions can be completely reversed:
- **↺ Undo (`Ctrl+Z`):** Steps backward through the 30-level annotation snapshot stack, reverting image state.
- **↻ Redo (`Ctrl+Y` / `Ctrl+Shift+Z`):** Re-applies undone annotation operations.
- **🔄 Reset Image:** Restores the image back to its pristine base state when the dialog opened, while still recording an undo snapshot in case the reset was accidental.
- **Cancel:** Dismissing the dialog with `Cancel` or `Esc` discards all in-progress markup without touching the document.

### 7.3 Proportional Resizing & Aspect Ratio Lock
The right side panel integrates dimension controls:
- **Spinboxes:** Direct numerical width and height adjustments in pixels.
- **🔗 Lock Aspect Ratio:** Preserves proportional scaling when enabled (default). Unchecking allows independent horizontal/vertical resizing.
- **Quick Presets:** Instant scaling buttons for `25%`, `50%`, `75%`, and `100%` (original size).
- **Fit to Pane Width:** Automatically scales the image to the editor's current pane width (respecting split-view side pane boundaries).

### 7.4 Auto-Save & Storage Pipeline Integration
When the dialog is accepted (`OK`):
1. The modified `QImage` is compressed to JPEG (quality 85 per `AGENTS.md`) using `ImageService.compress_qimage_to_jpeg()`.
2. The JPEG bytes are stored in the editor's `in_memory_images` cache under the image UUID key.
3. The `QTextDocument` resource cache is refreshed (`addResource`) so the document repaints instantaneously.
4. Auto-save signal `content_modified(scratchpad_id)` is emitted, scheduling SQLite persistence to the `scratchpad_images` table during the debounced write cycle.

### 7.5 Image Context Menu: Copy & Save As...

When right-clicking on any embedded screenshot or image in `TechPadEditor`:
- **📐 Resize & Annotate Image...:** Launches the full annotation and resize modal dialog.
- **📏 Quick Resize Submenu:** Offers one-click presets (`Fit to Pane Width`, `100%`, `75%`, `50%`, `25%`).
- **📋 Copy Image:** Copies the full-resolution bitmap directly into the system clipboard (`QApplication.clipboard().setImage`), ready to paste (`Ctrl+V`) into external applications such as Slack, Microsoft Teams, Outlook, Word, or Jira.
- **💾 Save Image As...:** Opens a file dialog allowing export to `.png` (lossless) or `.jpg` (raw original bytes without recompression artifacts).
- All actions display instantaneous feedback in the window status bar (`✓ Copied image to clipboard!` / `✓ Saved image to <path>`).

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
- **Active Ticket Notes Toggle:** The `Active Ticket` toggle button (`ticket_panel_toggle`, synchronized with status bar `btn_m365_active_ticket`) allows hiding or showing the right sidebar to prioritize administrative workspace or ticket notes.
- **State Preservation:** Navigation selection, scroll position, and panel collapsed/expanded states survive across Alt+F8 workspace switches.

### 9.3 Workspace-Specific Minimum Dimensions & Bounds Clamping
- **M365 Minimum Size:** Set to `640x380` on entering M365 workspace, allowing the window to fit comfortably within 720p displays at 150% scaling without pushing bottom content off-screen.
- **Notes Minimum Size:** Restored to `660x400` when returning to Notes, preserving the two-row formatting ribbon, tabs, and editor on portrait monitors down to 700 logical pixels.
- **Geometry Clamping:** Restoring normal geometry from Mini-HUD clamps window boundaries to the active monitor's available desktop work area (`screen.availableGeometry()`), preventing off-screen window drift.

### 9.4 Save Barrier & Data Integrity on Workspace Switch and Exit
- **Atomic Save Barrier (`flush_all_saves() -> bool`):** Before switching to the M365 Launcher or closing the application, all active debounce timers and dirty scratchpad IDs are immediately flushed and saved to SQLite.
- **Save Status Accuracy:** If any ticket fails to persist or dirty notes remain, the status bar displays `● Save Failed` in bold red (never falsely showing `● Saved`).
- **Guarded Navigation & Refused Exit:** Failed saves immediately abort workspace switching (`show_m365_workspace()` returns `False`), and `closeEvent()` calls `event.ignore()` with a status bar alert to keep the window open and preserve all in-memory drafts and images. Subsequent user actions cleanly retry the stopped timers without data loss.

### 9.5 M365 Active Ticket Right Sidebar & Zero-Lag Shared Document Architecture
- **Active Ticket Resolution:** When entering the M365 Launcher module, `show_m365_workspace()` resolves the Active Ticket directly from `_get_active_editor()` (the ticket tab where the cursor/keyboard focus was placed in T-Notes, across either Split View side panel or Main Window).
- **Shared In-Memory Document (`QTextDocument`):** The sidebar's embedded `TechPadEditor` calls `setDocument(active_editor.document())` and references `active_editor.in_memory_images`. This provides instantaneous, zero-lag bidirectional synchronization: edits, character formatting, pasted screenshots, and checklists typed in the M365 sidebar immediately reflect in the underlying document.
- **Ticket Header Card:** Displays ticket identification pill (`#INC-xxx`), client name, and subject/title alongside synchronized troubleshooting stopwatch controls (`⏱️ HH:MM:SS`, `▶`/`⏸` play/pause, `↺` reset) directly wired to the ticket's active stopwatch state.
- **Top-Right Corner Micro-Controls (`id_client_row`):** To maximize editor height, dedicated toolbar rows are eliminated in favor of three compact corner controls (26x22px) anchored at the top right of the header card:
  - `btn_template` (`"🗒️"`): Structured ticket template dropdown (`InstantPopup` mode) inserting pre-configured diagnostic skeletons or custom user templates via `🔳 Add a new template`.
  - `btn_copy_note` (`"📋"`): Formatted note copy (`Ctrl+Shift+C`) on click, packaging rich HTML with Base64 embedded images to the Windows Clipboard; dropdown actions for clean Markdown export (`📤 Copy Clean Note for Ticket Tool` / `Ctrl+Alt+N`) and direct plain-text file export (`💾 Export Note (T-Notes Folder)` / `Ctrl+Alt+E`) to daily timestamped subfolders in `T-Notes\`.
  - `btn_more` (`"..."`, `HoverToolButton`): Opens the comprehensive text formatting and insert menu on hover or click.
- **Hover & Click Text Features Menu (`menu_text_features`):** Features instantaneous popup access to all text styling tools:
  - Checkable formatting toggles: `B Bold (Ctrl+B)`, `I Italic (Ctrl+I)`, `U Underline (Ctrl+U)` with real-time format state reflection.
  - Formatting pickers: `🎨 Text Color... (Ctrl+Alt+X)`, `🖍️ Highlight Color... (Ctrl+Alt+H)`, `</> Monospace Code Block (Ctrl+Alt+C)`.
  - Submenu: `🏷️ Log Badges` (PASS, FAIL, WARN, INFO triage labels).
  - Insertion utilities: `☑ Checkbox (Ctrl+Alt+L)`, `🕒 Current Timestamp (F5)`, `🖼️ Insert Image File... (Ctrl+Alt+I)`.
- **Maximized Vertical Note Canvas:** Eliminating the previous two horizontal toolbar rows recovers approximately 60 vertical pixels, allocating 100% of the reclaimed vertical space directly to `self.ticket_editor` (`TechPadEditor`).
- **Autosave Persistence:** Modifying the sidebar editor emits `note_modified(scratchpad_id)`, restarting the 1500ms debounced autosave timer in SQLite. Switching workspaces or clicking Copy Note forces immediate synchronous persistence.

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
- **User Intent Preservation:** The user's explicit visibility preference (`_user_history_drawer_open`) is tracked separately from responsive overrides. If the user explicitly toggles the drawer (via `Alt+H` or toolbar button) while in narrow mode, their explicit choice takes precedence and clears the auto-collapse flag.
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


---

## 11. Custom Ticket Templates & Add Template Dialog

### 11.1 Overview & Menu Integration
In addition to built-in structured triage skeletons (`Standard Incident Triage`, `Quick Triage / Quick Fix`, `Maintenance & Change Plan`), technicians can create and persist user-defined templates via the `📋 Template` dropdown menu:
- **Menu Hierarchy:** Built-in skeletons -> separator -> user-defined custom templates -> separator -> `🔳 Add a new template`.
- **Action Trigger:** Clicking `🔳 Add a new template` opens the `AddTemplateDialog` modal.

### 11.2 Add Template Dialog (`AddTemplateDialog`)
The template creation dialog provides a self-contained rich-text authoring environment:
- **Top Labeled Textbox (`Title`):** A `QLineEdit` for naming the template (e.g., `Firewall Ticket Triage`, `VPN Onboarding Checklist`). Validates that the title is non-empty before saving.
- **Formatting Ribbon:**
  - **Font Styles:** Bold (`B`, `Ctrl+B`), Italic (`I`, `Ctrl+I`), Underline (`U`, `Ctrl+U`), and Strikethrough (`S`).
  - **Color Pickers:** Foreground text color (`🎨`, `QColorDialog`) and highlighted text background color (`🖍️`, `QColorDialog`).
  - **Headings & Structure:** Headings selector (`Heading 1`, `Heading 2`, `Heading 3`, `Normal Text`), Bullet List (`• List`), and Numbered List (`1. List`).
  - **Code Blocks:** Monospace container formatting (`</>`) applying `Consolas` monospace font and dark container styling.
  - **Image Button:** `🖼️ Image` button invoking `QFileDialog` to select image files (`PNG`, `JPG`, `JPEG`, `BMP`, `WEBP`, `GIF`).
- **Down Labeled Textbox (`Template`):** Built upon `TemplateEditor` (`QTextEdit`), providing full clipboard fidelity:
  - Copy and paste of formatted rich text, HTML, and images.
  - Clipboard screenshot pasting (`Win+Shift+S` / `Ctrl+V`).
  - Drag-and-drop of image files from Windows Explorer.
  - Automatic JPEG compression at quality factor 85 per AGENTS.md media guidelines.
  - Self-contained HTML export: Local `image://local/...` references are converted to embedded `data:image/jpeg;base64,...` URIs upon saving, ensuring templates remain fully portable.

### 11.3 Active Ticket Cursor Insertion Workflow
When a template is selected from the `📋 Template` dropdown menu:
1. `_on_skeleton_selected(name)` retrieves the template's markup from `ScratchpadService.get_skeleton_html(name)`.
2. The active focused ticket's `TechPadEditor` receives the markup via `insert_template_html(html)`.
3. Any embedded Base64 image data URIs are automatically unpacked into unique JPEG resources (`image://local/<uuid>.jpg`), registered in the `QTextDocument` resource cache, and added to the editor's `in_memory_images`.
4. The rich content is inserted directly at the active cursor position (`cursor.insertHtml(...)`), preserving existing ticket context.
5. Auto-save is triggered via `content_modified(scratchpad_id)`, persisting all newly unpacked images to `scratchpad_images` in SQLite.

---

## 12. Bilingual Client & PSA Summary Formatter (English & Français)

The `📋 Copy Note` tool button on the secondary toolbar integrates a comprehensive bilingual summary formatting suite:

### 12.1 One-Click Toolbar Actions
Under the `📋 Copy Note` dropdown menu, technicians can instantly generate and copy clean, targeted summaries:
- **`✉️ Copy Client Email (EN)`**: Generates a polite, clear client resolution email in English with greetings, issue description, actions taken, next steps, and sign-off.
- **`✉️ Copier le courriel client (FR)`**: Generates an equivalent client resolution email in French with standardized courteous phrasing (`Bonjour...`, `Actions effectuées et résolution...`, `Cordialement...`).
- **`🏢 Copy PSA Note (EN)`**: Formats an internal ticketing work note (ConnectWise, ServiceNow, Jira, HaloPSA) with ticket header, billable time (rounded up to 15-minute / 0.25h increments), issue, chronological troubleshooting, root cause, and resolution.
- **`🏢 Copier la note PSA (FR)`**: Formats an internal French PSA work note with standard French headings (`BILLET`, `PROBLÈME SIGNALÉ`, `DÉPANNAGE / TRAVAIL EFFECTUÉ`, `CAUSE RACINE`, `RÉSOLUTION`).

### 12.2 Interactive Summary Formatter Dialog (`SummaryFormatterDialog`)
Clicking **`✨ Format Ticket Summary... / Résumé...`** opens a two-column modal workspace:
- **Language Switcher**: Instant `🇬🇧 English` | `🇫🇷 Français` toggle dynamically updates all dialog field labels, preset options, and live preview text in real time.
- **Target Presets**:
  1. *Client Resolution Email / Courriel de résolution client*: Customer-facing message omitting internal-only diagnostics.
  2. *Internal PSA Note / Note interne PSA*: Standardized engineering work note with logged billable time.
  3. *Escalation Handover / Transfert d'escalade*: Technical handover summary for Tier 2/3 and Engineering escalation.
- **Smart Bilingual Section Detection**: Automatically extracts content by parsing note HTML and markdown across English and French keywords (`Issue` / `Problème`, `Troubleshooting` / `Dépannage`, `Resolution` / `Résolution`, `Root Cause` / `Cause racine`, `Next Steps` / `Prochaines étapes`) and interactive checklist items (`- [x]`).
- **Output Formats**: Single-click buttons for copying plain text or rich HTML formatting.
- **Preferences Persistence**: Default Name (e.g., `Jonathan Decelles`), Default Email (e.g., `Jonathan_Decelles1990@hotmail.com`), and preferred default summary language (`en` or `fr`) are persisted in `app_settings` via `SessionService` and configurable in both `SettingsDialog` and `SummaryFormatterDialog`. These fields automatically populate the technician signature block at the end of client emails and PSA ticket notes.
