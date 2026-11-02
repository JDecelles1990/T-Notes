# T-Notes Documentation

Welcome to the internal engineering documentation and architectural reference for **T-Notes** (TechPad). This knowledge base defines system design contracts, data dictionaries, media pipelines, and feature lifecycles.

---

## 🗺️ Documentation Directory Map

```text
docs/
├── index.md                              # Master index, routing table, and checklist
├── architecture/
│   ├── system-overview.md                # Layered design, threading model, and bootstrap
│   └── image-pipeline.md                 # Screenshot capture, JPEG compression, and BLOB lifecycle
├── database/
│   ├── schema.md                         # Relational schema, migrations, SQLite PRAGMAs, and data dictionary
│   └── fts-and-search.md                 # FTS5 virtual table, triggers, and search syntax
├── features/
│   ├── tab-lifecycle.md                  # Tab creation, reordering, live minutes, and shortcuts
│   ├── editor-and-formatting.md          # Custom QTextEdit, hotkeys, code blocks, stopwatch, and badges
│   └── history-and-archive.md            # Archive drawer, audit trail, search, and restoration
└── decisions/
    ├── template.md                       # Architecture Decision Record (ADR) template
    ├── 0001-sqlite-wal-and-jpeg-blobs.md # ADR 0001: SQLite WAL & Embedded JPEG BLOB Storage
    ├── 0002-win32-idle-and-lock-detection.md # ADR 0002: Win32 Idle & Lock Auto-Pause
    └── 0003-global-event-filtering-for-shortcuts.md # ADR 0003: Global Event Filtering for Shortcuts
```

---

## 🧭 Quick Component Navigation

| Domain | Document | Key Topics Covered |
| :--- | :--- | :--- |
| **System Architecture** | [`architecture/system-overview.md`](architecture/system-overview.md) | Layer boundaries (`ui/` → `services/` → `repositories/` → `database/`), Qt event loop, stopwatch service, settings repository, and bootstrap. |
| **Media & Screenshots** | [`architecture/image-pipeline.md`](architecture/image-pipeline.md) | `Win+Shift+S` clipboard interception, 85% JPEG compression, `image://local/<uuid>` URI mapping, BLOB storage. |
| **Relational Data** | [`database/schema.md`](database/schema.md) | Data dictionary for `scratchpads`, `scratchpad_images`, `app_session`, `app_settings`, foreign keys, cascade deletes, and schema migrations. |
| **Full-Text Search** | [`database/fts-and-search.md`](database/fts-and-search.md) | SQLite FTS5 configuration, prefix token matching, automatic sync triggers (`ai`, `ad`, `au`), and legacy table rebuild migrations. |
| **Workspace & Tabs** | [`features/tab-lifecycle.md`](features/tab-lifecycle.md) | Multi-tab tracking, live running minutes, drag reordering, browser-style shortcuts with bitwise modifier filters, and context menus. |
| **Editor & Text Tools** | [`features/editor-and-formatting.md`](features/editor-and-formatting.md) | Rich text shortcuts, monospace CLI code blocks, Log Triage pills, Ticket Stopwatch (`⏱️`), MSP billing copy, and opacity slider. |
| **History & Drawer** | [`features/history-and-archive.md`](features/history-and-archive.md) | Collapsible side drawer (`Ctrl+H` / `🕰️`), real-time FTS filtering, ticket archival audit trails, and tab restoration (`Ctrl+Shift+T`). |
| **Architecture Decisions** | [`decisions/`](decisions/) | Historical record of key technical and architectural decisions (ADRs 0001, 0002, 0003). |

---

## 📋 Standard Checklist for Documenting New Features

All developers and AI agents introducing or modifying features in T-Notes must adhere to the following checklist before finalizing changes:

- [ ] **Schema & Data Contracts:** If database tables or columns are added or changed, update [`database/schema.md`](database/schema.md) and provide migration routines in `src/database/migrations.py`.
- [ ] **FTS Synchronization:** If searchable fields change, update [`database/fts-and-search.md`](database/fts-and-search.md) and verify FTS triggers.
- [ ] **Layer Integrity:** Verify that UI components never invoke SQL queries directly and strictly interface with `src/services/`.
- [ ] **Media Handling:** Ensure any media addition satisfies the 85% JPEG compression policy outlined in [`architecture/image-pipeline.md`](architecture/image-pipeline.md).
- [ ] **Feature Specifications:** Add or update the corresponding document under `docs/features/`.
- [ ] **Architectural Decision Records:** If adopting a new library or altering a core architectural pattern, author a new ADR in `docs/decisions/` using [`decisions/template.md`](decisions/template.md).
- [ ] **Agent Governance:** Check that all changes comply with the Canonical [`AGENTS.md`](../AGENTS.md).

