# T-Notes

> Tech Ticket Notes Scratchpad with JPEG integration, SQLite, and PySide6.
**T-Notes** est une application de bureau conçue pour le support technique et les flux de travail en ingénierie, utilisant **PySide6** et une base de données **SQLite** avec prise en charge des images JPEG. La plateforme intègre une architecture **multiongllets** pour la gestion des tickets, un mode **division d'écran** côte à côte, ainsi qu'un panneau latéral d'historique avec recherche textuelle complète via FTS5\. Les sources documentent également une proposition de mise en œuvre pour un espace de travail **M365**, établissant des protocoles stricts de sécurité, d'authentification interactive déléguée et de validation de scripts PowerShell isolés. Enfin, le projet spécifie des règles rigoureuses pour la **persistance des sessions**, la gestion de la minuterie de facturation, les listes de tâches interactives et les garanties de sauvegarde automatique des notes.

## Overview
**T-Notes** is a desktop scratchpad application built for technical support and engineering workflows. It provides fast, tabbed note-taking for active tickets, debounced auto-saving, lightweight SQLite persistence, embedded JPEG image handling, and a clean dark theme.

## Features
- **Tabbed Scratchpad Interface:** Organize notes by ticket with dynamic tab ordering and session recovery.
- **Embedded Media Pipeline:** Efficient JPEG compression (quality 82–85) stored directly in SQLite BLOBs.
- **Debounced Auto-Saving:** Non-intrusive auto-save on typing pauses (1500ms debounce) and automatic state syncing on tab change or window exit.
- **Clean Dark Theme:** Built-in dark mode using clean QSS stylesheets.
- **SQLite Concurrency & Integrity:** WAL mode and foreign key constraints enabled for high-performance and data integrity.

## Architecture & Project Structure
```text
T-Notes/
├── assets/
│   ├── icons/
│   └── styles/
│       └── dark_theme.qss
├── src/
│   ├── core/           # Constants, debouncers, utilities
│   ├── database/       # SQLite connections, schema, migrations
│   ├── repositories/   # Data access layer
│   ├── services/       # Business logic, image processing, session management
│   └── ui/             # PySide6 windows, components, and dialogs
├── tests/              # Unit and integration test suite
├── AGENTS.md           # Development rules & operating standards
└── ARCHITECTURE.md     # Architectural blueprints
```

## Getting Started

### Prerequisites
- Python 3.10+
- PySide6

### Installation
```bash
git clone https://github.com/JDecelles1990/T-Notes.git
cd T-Notes
pip install -r requirements.txt
```

### Running the Application
```bash
python -m src.main
```

## License
MIT License

