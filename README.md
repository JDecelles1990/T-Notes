# T-Notes

> Desktop technician scratchpad and diagnostic workspace built with **PySide6**, **SQLite (WAL + FTS5)**, embedded **JPEG** screenshots, and an isolated **PowerShell 7 / Microsoft 365** launcher.

---

## Overview

**T-Notes** (TechPad) is a dark-mode desktop workspace built for IT support technicians, systems administrators, and MSP engineers. It combines multi-tab ticket note-taking, embedded visual screenshot annotation, ticket time tracking, bilingual summary formatting, and a contract-validated Microsoft 365 PowerShell diagnostic launcher backed by local SQLite persistence.

---

## Key Features

- **Multi-Tab Scratchpads, Split View & Mini-HUD:** Organize active tickets across reorderable tabs with session recovery, side-by-side Split View (`Alt+Z`), an always-on-top Mini-HUD (`Alt+T`), and background Windows System Tray persistence with a system-wide `F8` toggle ([tab lifecycle](docs/features/tab-lifecycle.md)).
- **Technician Editor, Checklists & Templates:** Dark QSS styling, interactive task checklists (`Ctrl+Alt+L`), monospace CLI code blocks (`Ctrl+Alt+C`), log triage badges (`Alt+1`–`Alt+4`), timestamps (`F5`), URL auto-linking, in-note Find & Replace (`Ctrl+F` / `Ctrl+H`), customizable rich templates, and a billable **Ticket Stopwatch** with Win32 idle/lock auto-pause ([editor guide](docs/features/editor-and-formatting.md)).
- **Image Pipeline & Full-Screen Image Editor:** Intercepts clipboard screenshots (`Win+Shift+S`) and image drops, compresses captures to JPEG (quality `85`) stored as SQLite BLOBs, supports interactive corner drag-resizing, and includes a full-screen-by-default **Image Editor** with a single-line icon toolbar for freehand pen, Shift-snapped straight lines, circles, rectangles, Paint-style text boxes, selection/rotation handles, and zoom/pan ([image pipeline](docs/architecture/image-pipeline.md)).
- **PSA Export, Bilingual Summary Formatter & Email:** Copy rich HTML with Base64-embedded images (`Ctrl+Shift+C`), export clean Markdown for ITSM/PSA tickets (`Ctrl+Alt+N`), write daily plain-text notes under `T-Notes/<YYYY-MM-DD>/` (`Ctrl+Alt+E`), generate English/French **Client & PSA Summaries**, or open a pre-filled draft in your default email client (`Ctrl+Alt+M`).
- **FTS5 History Drawer & Automated Backups:** Search archived and active tickets in real time via SQLite FTS5 (`Alt+H`), restore archived tabs non-destructively, and keep rolling daily online SQLite `.db.bak` snapshots ([FTS & search](docs/database/fts-and-search.md), [history & archive](docs/features/history-and-archive.md)).
- **M365 PowerShell Diagnostic Workspace (`Alt+F8`):** Runs **25 read-only PowerShell 7 diagnostic scripts** across 11 Microsoft 365 categories plus **5 guided triage workflows** under contract `tnotes.m365 / 0.3.0`. Supports both **Offline Synthetic** evaluation and **Live Tenant** execution with interactive Graph/Exchange sign-in, Win32 Job Object worker isolation, and 1-click Active Ticket note insertion ([M365 launcher](docs/features/m365-s2-s3-launcher.md), [M365 contract](docs/contracts/m365/CONTRACT.md)).

---

## Prerequisites

- **Python:** `>= 3.10` (developed and tested on Python 3.14 on Windows)
- **Python Packages:** See [`requirements.txt`](requirements.txt)
  - `PySide6>=6.6.0`
  - `Pillow>=10.0.0`
  - `jsonschema>=4.23,<5`
  - `referencing>=0.35.0`
  - `pytest>=8.0.0` (test suite)
- **Optional — Microsoft 365 Workspace:**
  - **PowerShell 7** (`pwsh` 7.4+)
  - For **Live Tenant** mode (read-only host-owned authentication):
    - `Microsoft.Graph.Authentication >= 2.0.0`
    - `Microsoft.Graph.Users >= 2.0.0`
    - `Microsoft.Graph.Reports >= 2.0.0`
    - `ExchangeOnlineManagement >= 3.4.0`

---

## Installation & Running

```bash
git clone https://github.com/JDecelles1990/T-Notes.git
cd T-Notes
python -m pip install -r requirements.txt
```

Launch the desktop application:

```bash
python -m src.main
```

Optional background tray launch flag (used by Windows startup registration):

```bash
python -m src.main --tray
```

---

## Local Data Locations

- **SQLite Database & Daily Backups:**
  - Windows: `%LOCALAPPDATA%\TechPad\techpad.db` (snapshots in `backups\`)
  - macOS / Linux: `~/.techpad/techpad.db`
- **Plain-Text Ticket Exports:** `T-Notes/<YYYY-MM-DD>/` inside the repository folder (git-ignored)

---

## Testing & Verification

Run the Python unit and integration test suite:

```bash
python -m pytest -q
```

Validate the offline M365 PowerShell contract package:

```bash
python -B docs/contracts/m365/validation/validate_contract.py
```

---

## Project Structure

```text
T-Notes/
├── assets/
│   ├── icons/                # Application icons
│   ├── m365/                 # Contract pins, empty production catalog, synthetic catalog (25 ops)
│   └── styles/               # Dark theme QSS stylesheet
├── docs/                     # Architecture overview, database schema, feature specs, ADRs, M365 contracts
├── prototypes/               # Official M365 PowerShell protocol engine helpers
├── scripts/
│   └── m365/                 # 25 standalone PowerShell 7 operations & persistent worker host
├── src/
│   ├── config.py             # Application data & export paths
│   ├── main.py               # Entry point, DB init, autostart, daily backup, GUI launch
│   ├── core/                 # Constants, debouncers, Win32 global hotkey manager
│   ├── database/             # SQLite WAL connection manager, schema, migrations
│   ├── repositories/         # Data access & atomic SQL transactions
│   ├── services/             # Business logic, image compression, formatting, M365 orchestration
│   └── ui/                   # PySide6 windows, editors, dialogs, and M365 launcher views
├── tests/                    # Pytest unit, service, contract, and UI integration suites
├── AGENTS.md                 # Architectural boundaries & documentation maintenance rules
├── ARCHITECTURE.md           # High-level layered architecture overview
├── pyproject.toml            # Project metadata & pytest configuration
├── README.md                 # Project overview and quick start
└── requirements.txt          # Python runtime & test dependencies
```

For detailed architecture specifications, database schemas, and ADRs, see [`docs/index.md`](docs/index.md) and [`ARCHITECTURE.md`](ARCHITECTURE.md).
