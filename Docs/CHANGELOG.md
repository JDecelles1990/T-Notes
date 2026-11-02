# Changelog

All notable changes to the TechPad (T-Notes) project will be documented in this file.

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
