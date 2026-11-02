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
│   ├── schema.md                         # Relational schema, SQLite PRAGMAs, and data dictionary
│   └── fts-and-search.md                 # FTS5 virtual table, triggers, and search syntax
├── features/
│   ├── tab-lifecycle.md                  # Tab creation, reordering, renaming, and closing
│   ├── editor-and-formatting.md          # Custom QTextEdit, hotkeys, code blocks, and badges
│   └── history-and-archive.md            # Archive drawer, state transitions, and restoration
└── decisions/
    ├── template.md                       # Architecture Decision Record (ADR) template
    └── 0001-sqlite-wal-and-jpeg-blobs.md # ADR 0001: SQLite WAL & Embedded JPEG BLOB Storage
```

---

## 🧭 Quick Component Navigation

| Domain | Document | Key Topics Covered |
| :--- | :--- | :--- |
| **System Architecture** | [`architecture/system-overview.md`](architecture/system-overview.md) | Layer boundaries (`ui/` → `services/` → `repositories/` → `database/`), Qt event loop, startup/teardown sequence. |
| **Media & Screenshots** | [`architecture/image-pipeline.md`](architecture/image-pipeline.md) | `Win+Shift+S` clipboard interception, 85% JPEG compression, `image://local/<uuid>` URI mapping, BLOB storage. |
| **Relational Data** | [`database/schema.md`](database/schema.md) | Data dictionary for `scratchpads`, `scratchpad_images`, `app_session`, foreign keys, cascade deletes, and migrations. |
| **Full-Text Search** | [`database/fts-and-search.md`](database/fts-and-search.md) | SQLite FTS5 configuration, prefix token matching, automatic sync triggers (`ai`, `ad`, `au`). |
| **Workspace & Tabs** | [`features/tab-lifecycle.md`](features/tab-lifecycle.md) | Multi-tab tracking, drag-and-drop reordering, double-click modal renaming, archive-on-close confirmation. |
| **Editor & Text Tools** | [`features/editor-and-formatting.md`](features/editor-and-formatting.md) | Rich text shortcuts, monospace CLI code blocks, Log Triage pills (`PASS`/`FAIL`/`WARN`), PSA note export. |
| **History & Drawer** | [`features/history-and-archive.md`](features/history-and-archive.md) | Collapsible side drawer (`Ctrl+H`), real-time FTS filtering, ticket restoration, permanent deletion. |
| **Architecture Decisions** | [`decisions/`](decisions/0001-sqlite-wal-and-jpeg-blobs.md) | Historical record of key technical and architectural decisions (ADRs). |

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

