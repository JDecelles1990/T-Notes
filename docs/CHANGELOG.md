# Changelog

All notable changes to the TechPad (T-Notes) project will be documented in this file.

## [1.3.0] - 2026-11-01

### Added
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
