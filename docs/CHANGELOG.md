# Changelog

All notable changes to the TechPad (T-Notes) project will be documented in this file.

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
