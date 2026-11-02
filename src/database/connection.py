"""Database connection manager for SQLite."""

import sqlite3
from pathlib import Path
from typing import Optional, Union
from src.config import DEFAULT_DB_PATH


class DatabaseManager:
    """Manages SQLite connections with WAL mode and foreign key enforcement."""

    def __init__(self, db_path: Optional[Union[str, Path]] = None):
        self.db_path = Path(db_path) if db_path else DEFAULT_DB_PATH
        self.db_path.parent.mkdir(parents=True, exist_ok=True)
        self._connection: Optional[sqlite3.Connection] = None

    def get_connection(self) -> sqlite3.Connection:
        """Returns the active SQLite connection, creating and configuring it if necessary."""
        if self._connection is None:
            self._connection = sqlite3.connect(
                str(self.db_path),
                timeout=5.0,
                check_same_thread=False
            )
            self._connection.row_factory = sqlite3.Row
            # Enable WAL mode and foreign keys per AGENTS.md guidelines
            self._connection.execute("PRAGMA journal_mode = WAL;")
            self._connection.execute("PRAGMA foreign_keys = ON;")
            self._connection.execute("PRAGMA busy_timeout = 5000;")
        return self._connection

    def close(self) -> None:
        """Closes the active database connection if open."""
        if self._connection is not None:
            try:
                self._connection.close()
            finally:
                self._connection = None


# Default global instance
_default_db_manager = DatabaseManager()


def get_db(db_path: Optional[Union[str, Path]] = None) -> sqlite3.Connection:
    """Convenience function returning the default SQLite connection."""
    if db_path:
        return DatabaseManager(db_path).get_connection()
    return _default_db_manager.get_connection()
