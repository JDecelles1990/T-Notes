# Changelog

All notable changes to the TechPad (T-Notes) project will be documented in this file.

## [1.3.0] - 2026-11-01

### Added
- **Rich Text, Color & Inline Image Clipboard Copying**:
  - Overrode `TechPadEditor.createMimeDataFromSelection()` to automatically resolve and convert internal `image://local/...` image URLs into self-contained Base64 Data URIs (`data:image/jpeg;base64,...`).
  - Enables copying large blocks of highlighted text along with custom font colors, highlights, code blocks, bold/italics, and embedded screenshots, and pasting directly into Microsoft Word, Microsoft Outlook, Microsoft Teams, Slack, Google Docs, Gmail, and web browsers with full visual fidelity.
  - Image-only selection automatically populates raw bitmap data (`mime_data.setImageData`) for bitmap-only paste targets (e.g. Paint).
  - Plain-text clipboard fallback replaces Unicode object replacement markers (`\uFFFC`) with clean `[Screenshot]` text tags.
  - Upgraded **`📋 Copy Note`** ribbon button into a dual-action menu button:
    - Default button click or **`Ctrl+Shift+C`**: Copies the entire active note formatted with rich text, custom colors, and embedded Base64 images.
    - Dropdown menu or **`Ctrl+Alt+N`**: Exports stripped clean Markdown/plain-text note for ticketing PSA tools (ServiceNow, Jira).
  - Added `📋 Copy Formatted Note (Rich Text & Images)` to tab header context menus and editor right-click menu.
- **Application Rebranding to T-Notes**:
  - Rebranded the application name from `TechPad` to `T-Notes` across the entire interface.
  - Window title bar at the top-left now dynamically displays `T-Notes v1.0.0 — Technician Scratchpad`.
  - Updated application metadata (`app.setApplicationName("T-Notes")`), default scratchpad welcome template header, preferences modal title, system tray action labels, and background notifications.
- **Image Context Menu (Copy Image & Save Image As...)**:
  - Right-clicking directly on any embedded screenshot or image in `TechPadEditor` surfaces dedicated image actions:
    - **`📋 Copy Image`**: Copies full-fidelity bitmap data to system clipboard (`QApplication.clipboard().setImage`), enabling direct pasting (`Ctrl+V`) into Teams, Slack, Outlook, Jira, or graphics apps.
    - **`💾 Save Image As...`**: Prompts file save dialog to export as PNG or JPEG on disk. Preserves raw stored JPEG bytes when exporting to JPEG to avoid generational recompression artifacts.
  - Automatically detects embedded image bounds via `_get_image_at_pos()`, seamlessly differentiating image clicks from standard text cursor positions.
- **Side-by-Side Split View & Dual Ticket Workspace (`Alt+Z` / `◫`)**:
  - Implemented dual side-by-side editing panes using a central horizontal `QSplitter` containing Primary (`TechPadTabWidget`) and Secondary (`TechPadTabWidget`) ticket workspaces.
  - Dedicated **`◫`** toggle button on Row 2 toolbar and global application shortcut **`Alt+Z`** to toggle Split View ON/OFF.
  - 6px draggable divider bar (`QSplitter::handle:horizontal`) styled with `#2d2d2d` and `#007acc` hover highlight, with `setChildrenCollapsible(False)` preventing accidental collapsing.
  - Automatic 50/50 spatial distribution on launch; preserves manual resizing proportions (60/40, 70/30).
  - Intelligent tab migration:
    - When toggled ON with 2+ tabs, moves the adjacent tab into the secondary pane.
    - When toggled ON with 1 tab, generates a fresh ticket scratchpad in the secondary pane.
    - When toggled OFF, flushes all debounced auto-saves, safely consolidates all secondary tabs back into the primary tab bar without state loss, and restores 100% full-width view.
  - Focus-aware micro-control routing:
    - Clicking either editor emits `editor_focused(scratchpad_id)`.
    - Automatically binds top ribbon formatting actions, stopwatch active tracking, and status bar metadata to the focused ticket pane.
  - Context menu integrations:
    - Primary & Secondary tab context menus offer *"◫ Move to Right/Left Pane"*.
    - History Drawer right-click menu offers *"◫ Open in Side-by-Side Split"*, restoring archived tickets directly into the secondary pane alongside active work.
  - Cross-Pane Tab Drag-and-Drop:
    - Left-clicking, dragging, and releasing any tab transfers it directly into the opposite split view pane.
    - Dropping over the destination tab bar calculates the exact insertion index (`insert_ticket_tab`) based on cursor drop coordinates.
    - Dropping over the note editor area appends the ticket as the active tab.
    - Dragging a tab into the right half of the window when Split View is closed automatically opens Split View mode.
    - Visual feedback with `Qt.DragMoveCursor` while dragging outside the source tab bar; cancellation via `Escape`.
  - Permanent status bar toggle button: `◫ Split (Alt+Z)` / `◫ Single (Alt+Z)`.
- **Top Bar Ribbon Reorganization & Whitespace Elimination**:
  - Rebalanced the two-row ribbon to eliminate the 600px artificial expanding gap in Row 2:
    - **Row 1 (Formatting & Content):** `B`, `I`, `U`, `🎨`, `🖍️`, `</>`, `🏷️ Tag`, `☑ Checkbox`, `🕒`, `🖼️`.
    - **Row 2 (Ticket Workflow & Utilities):** Stopwatch (`⏱️ 00:00:00 ▶ ↺ 📋 Time`), `📋 Template`, `📤 Copy Note`, `👁️ 100%` Opacity Slider, `🕰️` History, `⚙️` Settings.
  - Added dedicated, clearly labeled **`☑ Checkbox`** button on Row 1 formatting ribbon (`Ctrl+Alt+L`) for instant 1-click task list insertion.
  - Replaced problematic glyphs on stopwatch buttons with crisp Unicode symbols (`▶` / `⏸` and `↺`) styled with explicit typography fonts to eliminate empty box `[ ][ ]` glyph rendering.
- **Automatic Tab Color Ownership**:
  - Each tab automatically and permanently owns a distinct, vibrant accent color from a curated 12-color technician palette (Sky Blue, Emerald, Purple, Amber, Rose, Cyan, Orange, Indigo, Lime, Pink, Teal, Lavender).
  - Rendered with a high-visibility 3px top accent stripe (2px when unselected) and a subtle 12%–14% ambient background tint.
  - Color ownership is deterministically bound to the ticket's `scratchpad_id`: moving, switching, or restoring tabs preserves each ticket's distinct color identity automatically without requiring manual configuration.
- **Interactive Task Checklists & Tab Progress Badges**:
  - Clickable task checkboxes (`[ ]` in accent blue `#007acc` and `[✔]` in success green `#4ade80`) anchored via custom `task://toggle` URI scheme.
  - 1-Click interactive toggling in `TechPadEditor` with automatic strikethrough styling (`text-decoration: line-through; color: #888888;`) for completed tasks.
  - Dynamic tab header progress badges updating live as tasks are checked or unchecked: `☑️{completed}/{total}` during progress (e.g. `#INC-1001 (14m) ☑️3/5 — Client`) and `✅{total}/{total}` upon 100% completion. Cleanly suppressed when a note contains no checklists.
  - Rich tab header tooltips displaying complete task statistics and percentage: `Tasks: 3/5 completed (60%)`.
  - Smart typing auto-conversion: typing `[] `, `[ ] `, or `- [ ] ` at the start of any line auto-transforms to an interactive checkbox.
  - Enter continuation: pressing `Enter` on a checklist line continues the list on the next line; pressing `Enter` on an empty checkbox line exits checklist mode.
  - Toolbar button `☑ Task` on Row 1 formatting toolbar, global shortcut `Ctrl+Alt+L`, and editor context menu integration.
  - Clean Markdown PSA Export: `ScratchpadService.convert_html_to_clean_text()` automatically converts `task://toggle` anchors to standard Markdown `- [ ] ` and `- [x] ` for ServiceNow, Jira, and GitHub compatibility.
- **System Tray Background Lifecycle & F8 Global Quick-Toggle**:
  - Closing the application window (`closeEvent`) minimizes TechPad to the Windows system tray (`QSystemTrayIcon`) rather than terminating the process, safeguarding ongoing notes and active stopwatch timers.
  - Generates crisp high-DPI application brand icon (`assets/icons/app_icon.png`) for window headers and system tray.
  - Configured `app.setQuitOnLastWindowClosed(False)` to preserve background execution.
  - Implemented **System-Wide Global `F8` Hotkey** (`GlobalHotkeyManager`, `WinNativeHotkeyFilter` via `user32.dll:RegisterHotKey`):
    - **When minimized, hidden in tray, or inactive:** Pressing `F8` pops TechPad to the foreground from any background application, restores normal window geometry, and focuses the note editor.
    - **When active on the screen:** Pressing `F8` minimizes TechPad out of the way.
  - System tray context menu providing 1-click toggling (`Show / Hide TechPad`), fresh tab creation (`➕ New Ticket Tab`), and clean exit (`✕ Quit TechPad`).
- **Two-Row Top Header Architecture (Zero Overflow / No 3-Dots Menu)**:
  - Re-architected the application header into two dedicated, non-movable toolbars via `addToolBarBreak()`:
    - **Row 1 (Formatting & Authoring):** Bold, Italic, Underline, Code Block, Log Badges, Text & Highlight Colors, Image Insertion, Timestamp, Templates, and Copy Clean Note.
    - **Row 2 (Workflow & System Utilities):** Ticket Stopwatch (`⏱️`), Play/Pause/Reset, Billing Copy Menu, Opacity Slider (`👁️ 100%`), History Drawer Toggle (`🕰️`), and Settings Gear (`⚙️`).
  - Completely eliminated the 3-dots (`...`) overflow button by providing ample horizontal breathing room across both rows and styling `QToolBarExtension` to 0px.
- **Ticket Stopwatch & MSP Billing Suite (`StopwatchService`, `TicketStopwatchWidget`)**:
  - Live Consolas monospace timer (`⏱️ HH:MM:SS`) tracking cumulative active troubleshooting time per tab.
  - Per-tab persistence: `elapsed_seconds` column in SQLite `scratchpads` table updated synchronously on tab switch, window close, and auto-save.
  - Formatted billing exports via `StopwatchService`:
    - Exact duration: `HH:MM:SS` (e.g. `00:14:32`).
    - Decimal hours: `0.24h` formatted with two decimals.
    - 15-minute rounded blocks: Rounds up to nearest 15-minute increment (e.g. `0.25h`, `0.50h`), standard in MSP/PSA client billing.
  - One-click copy dropdown (`📋 Time`) copying exact, decimal, or rounded blocks directly to clipboard with visual tooltip confirmation.
  - "Copy Note for Ticket Tool" option prepending billable troubleshooting time directly to clean plain-text/Markdown notes.
- **System Inactivity & Workstation Lock Auto-Pause**:
  - Low-overhead 1-second pulse timer polling Windows native APIs (`user32.dll:GetLastInputInfo` and `user32.dll:OpenInputDesktop`).
  - Automatically pauses active ticket stopwatch if the technician locks their workstation (`Win + L`) or leaves the workstation idle for > 300 seconds (5 minutes), preventing inflated billing hours.
  - Automatically resets pause state on manual resume (`▶️`) or when switching between tabs.
- **Dynamic Tab Header Minutes**:
  - Tab titles automatically append elapsed duration in minutes: `#{ticket_number} ({minutes}m) — {client_name | title}`.
  - Tab titles update live every minute while the stopwatch runs.
  - Automatically reverts to standard title without clutter when elapsed time is 0 or under 1 minute.
- **Ticket Archival Audit Trail**:
  - On ticket archival (`✕`, `Ctrl+W`, or context menu), `ScratchpadService.archive_ticket()` automatically calculates and appends an audit block to the note HTML:
    - Tab Created timestamp (UTC).
    - Tab Archived timestamp (UTC).
    - Total Tab Open Lifespan duration (wall-clock elapsed time).
    - Active Troubleshooting Time (exact stopwatch seconds and billable hours).
  - Idempotent styling prevents duplicate audit blocks if a restored ticket is re-archived.
- **Toolbar Quick History Access Button (`🕰️`)**:
  - Compact emoji button added to the top window toolbar between the Settings gear (`⚙️`) and Opacity Slider.
  - Enables 1-click toggling of the History & Archive Drawer.
- **History Drawer Resizing & Drag Splitter Handle**:
  - Added dedicated styling for `QMainWindow::separator` with a 6px width, `#2d2d2d` dark background, and `#007acc` hover highlight so the resize boundary between the note editor and History drawer is clearly visible and easy to drag.
  - Set ergonomic default width of `380px` via `sizeHint(QSize(380, 600))` and `resizeDocks`, preventing ticket headers, timestamps, and snippets from clipping.
  - Enforced a minimum width constraint of `280px` to prevent collapsing into an unreadable state.
- **History Drawer Metadata Enhancements**:
  - History list items now display billable elapsed time tags: `⏱️ {minutes}m | 📅 {YYYY-MM-DD} | {preview}`.
  - Hover tooltips display complete ticket audit metadata: Ticket #, Client, Title, Created timestamp, Archived timestamp, and exact Troubleshooting seconds.
- **Global Application Shortcut Event Filter**:
  - Installed a centralized `eventFilter` on `QApplication.instance()` to handle `Ctrl+Shift+PageUp` and `Ctrl+Shift+PageDown` tab sliding.
  - Bitwise modifier masking (`mods & Qt.ControlModifier`, `mods & Qt.ShiftModifier`) reliably circumvents Windows hardware keypad modifier flags (`Qt.KeypadModifier`).
  - Restores active editor focus immediately after tab movement.
- **Database Schema Upgrades & Migrations**:
  - Safe, idempotent schema migrations in `src/database/migrations.py`.
  - Added `elapsed_seconds` and `archived_at` columns to `scratchpads`.
  - Added `window_opacity` column to `app_session` before singleton row insertion to prevent startup crashes on fresh databases.
  - Automated migration for legacy `scratchpad_fts` virtual tables: detects legacy schemas containing `content_text`, drops legacy triggers, rebuilds external content virtual table referencing `content_html`, and runs `rebuild`.
- **Expanded Test Suite**:
  - Expanded test coverage from 22 to 39 automated tests covering stopwatch formatting, 15-minute rounding, idle detection, archival audit injection, database migrations, and application event filter shortcut handling.

---

## [1.2.0] - 2026-11-01

### Added
- **Clickable URLs & Auto-Detection**:
  - Automatically detects typed and pasted URLs (`https://`, `http://`, `www.`) and transforms them into clickable HTML hyperlinks.
  - Hovering over a link changes the cursor to `Qt.PointingHandCursor` with a target URL tooltip.
  - Clicking any link immediately launches the destination in the default web browser via `QDesktopServices.openUrl()`.
- **Browser-Style Tab Keyboard Shortcuts**:
  - `Ctrl+W` / `Ctrl+F4`: Close active tab.
  - `Ctrl+Tab` / `Ctrl+PageDown`: Switch to next tab.
  - `Ctrl+Shift+Tab` / `Ctrl+PageUp`: Switch to previous tab.
  - `Ctrl+Shift+PageDown`: Slide / move active tab to the right.
  - `Ctrl+Shift+PageUp`: Slide / move active tab to the left.
  - `Ctrl+1` .. `Ctrl+8`: Switch directly to tab 1–8.
  - `Ctrl+9`: Switch directly to last tab.
  - `Ctrl+Shift+T`: Re-open / restore most recently closed/archived ticket tab.
- **Editing Button Shortcuts**:
  - `Ctrl+Alt+C`: Monospace code block.
  - `Alt+1` / `Alt+2` / `Alt+3` / `Alt+4`: Log triage tags (`🟢 PASS`, `🔴 FAIL`, `🟡 WARN`, `ℹ️ INFO`).
  - `F5` / `Ctrl+Alt+T`: Current timestamp insertion.
  - `Ctrl+Alt+I`: Insert image file dialog.
  - `Ctrl+Alt+S`: Structured ticket skeleton menu.
  - `Ctrl+Alt+N`: Export clean note for PSA / ticketing systems.
  - `Ctrl+Alt+X`: Text color picker.
  - `Ctrl+Alt+H`: Text highlight background picker.
  - `Ctrl+,`: Open Preferences / Settings dialog.
- **Top Opacity Slider (60% to 100%)**:
  - Horizontal slider at top right of the toolbar enabling translucent window overlays (`setWindowOpacity`) so technicians can read background logs and terminals while typing.
  - Persisted across restarts in `app_session`.
- **Settings Gear Modal (`⚙️`) & Preferences**:
  - Gear button on top toolbar and `Ctrl+,` shortcut opening `SettingsDialog`.
  - Configurable ticket prefix (`INC-`, `REQ-`, `T-`).
  - Configurable auto-save debounce delay (500ms to 5000ms).
  - Configurable screenshot JPEG compression quality (50% to 100%).
  - Configurable close-tab workflow (`prompt` vs `archive directly`).
  - New SQLite table `app_settings` for persistent configuration.
- **Automated Tests**:
  - Added unit and UI integration tests for URL linkification, opacity slider bounds, and browser tab navigation shortcuts. Total test suite expanded to 22 tests.

---

## [1.1.0] - 2026-11-01

### Added
- **Right-Click Tab Context Menu**:
  - `✏️ Rename Ticket #<id>...`: Launches `EditTicketDialog` directly from tab context menu.
  - `📋 Duplicate Ticket Note`: Clones the note body, metadata, and embedded image BLOBs to a fresh tab.
  - `📤 Copy Note for Ticket Tool`: Exports stripped clean Markdown/plain-text to clipboard.
  - `📦 Archive Ticket to History`: Directly archives the ticket to the History Drawer.
  - `✕ Close Tab`: Prompts to archive or permanently delete the ticket.
  - `Close Other Tabs`: Closes and archives all other tabs except the selected one.
  - `➕ New Ticket Tab (Ctrl+T)`: Adds a new tab directly from the tab bar context menu.
- **Slide-Reorganizing Tabs**:
  - Ensured `movable` and `documentMode` are configured on the underlying `QTabBar` post-initialization.
  - Enabled smooth horizontal dragging and animated slide-swapping for multi-tab organization.
  - Added dark theme styling for `QTabBar QToolButton` tab bar scroll navigation when tabs overflow.
- **Automated Tests**:
  - Added UI integration tests for tab movable properties, slide reordering, tab duplication, and context archiving. Total test count increased to 19 tests.

---

## [1.0.0] - 2026-11-01

### Added
- **Multi-Tab Architecture**: Movable, closable tabs with `#<ticket_number> - <client_name | title>` naming convention.
- **Rich Text & Screenshot Engine (`TechPadEditor`)**:
  - Catches clipboard screenshot paste (`Win+Shift+S`, `Ctrl+V`) and image drag-and-drop.
  - Automatically compresses images to JPEG (85% quality factor) and stores as SQLite BLOBs.
  - Registers images with `document.addResource(ImageResource, QUrl("image://local/<uuid>"), qimage)`.
  - Clickable URL handling via `QDesktopServices.openUrl()`.
- **Technician Micro-Controls**:
  - Monospace code blocks (`</>`) for CLI / PowerShell logs.
  - 1-click Log Triage badges (`🟢 PASS`, `🔴 FAIL`, `🟡 WARN`, `ℹ️ INFO`).
  - Color pickers for text and highlights.
  - Timestamp insertion (`🕒` / `Ctrl+Shift+T`).
  - Predefined structured ticket skeletons (`📋`).
  - "Copy for Ticket Note" (`📤`) exporting stripped, clean text/markdown ready for PSA/ticketing systems.
- **1500ms Debounced Auto-Saving**:
  - Debounced auto-save via `DebounceTimer` with zero UI blocking.
  - Synchronous save flush on tab switch and application exit (`closeEvent`).
  - Visual save state indicators (`● Saved` / `↻ Saving...`).
- **Session Persistence**:
  - Full restoration of open tabs, tab ordering, and active tab on reboot.
- **Searchable History Drawer**:
  - Collapsible side panel (`Ctrl+H`) backed by SQLite FTS5 for real-time full-text search across tickets and note bodies.
  - Restore archived tickets or delete permanently.
- **Clean Dark Theme**: High-contrast, clean QSS stylesheet (`assets/styles/dark_theme.qss`).
- **Automated Test Suite**: 17 comprehensive unit and UI integration tests with 100% pass rate.
