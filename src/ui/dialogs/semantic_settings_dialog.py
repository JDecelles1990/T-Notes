"""Semantic Search settings and Ollama Re-index dialog."""

from __future__ import annotations

import sqlite3
import sys
from pathlib import Path
from typing import Callable

from PySide6.QtCore import QThread, Signal
from PySide6.QtWidgets import (
    QCheckBox,
    QDialog,
    QFormLayout,
    QFrame,
    QHBoxLayout,
    QLabel,
    QLineEdit,
    QPushButton,
    QVBoxLayout,
    QWidget,
)

from src.database.history_fts import _get_main_db_file
from src.database.semantic_search import (
    DEFAULT_EMBEDDING_MODEL,
    DEFAULT_OLLAMA_URL,
    EmbeddingIndexWorker,
    EmbeddingProvider,
    OllamaEmbeddingProvider,
    get_semantic_settings,
    save_semantic_settings,
)

sys.modules.setdefault("semantic_settings_dialog", sys.modules[__name__])


class _ConnectionProbeWorker(QThread):
    probed = Signal(bool, str)

    def __init__(self, provider: EmbeddingProvider, parent=None) -> None:
        super().__init__(parent)
        self._provider = provider

    def run(self) -> None:
        ok = False
        try:
            ok = bool(self._provider.is_available())
        except Exception:
            ok = False
        msg = "Connected" if ok else "Ollama not detected — Exact FTS5 remains active"
        self.probed.emit(ok, msg)


class SemanticSettingsDialog(QDialog):
    """Lightweight dark-mode settings & local Ollama indexing control dialog."""

    settings_saved = Signal(dict)

    def __init__(
        self,
        get_conn: Callable[[], sqlite3.Connection],
        *,
        provider: EmbeddingProvider | None = None,
        db_path: Path | None = None,
        parent: QWidget | None = None,
    ) -> None:
        super().__init__(parent)
        self._get_conn = get_conn
        self._injected_provider = provider
        self._db_path = db_path or _get_main_db_file(self._get_conn())
        self._probe_worker: _ConnectionProbeWorker | None = None
        self._index_worker: EmbeddingIndexWorker | None = None

        self.setWindowTitle("Semantic Search Settings (Local Ollama)")
        self.setModal(True)
        self.setMinimumWidth(500)

        current = get_semantic_settings(self._get_conn())
        self._build_ui(current)

    def _build_ui(self, current: dict) -> None:
        root = QVBoxLayout(self)
        root.setContentsMargins(16, 14, 16, 14)
        root.setSpacing(10)

        self.chk_enabled = QCheckBox("Enable local Smart Search (Hybrid FTS5 + Embeddings)", self)
        self.chk_enabled.setChecked(bool(current.get("enabled", False)))
        root.addWidget(self.chk_enabled)

        form = QFormLayout()
        form.setSpacing(8)

        self.url_input = QLineEdit(str(current.get("ollama_url", DEFAULT_OLLAMA_URL)), self)
        self.url_input.setPlaceholderText(DEFAULT_OLLAMA_URL)
        form.addRow("Ollama URL:", self.url_input)

        self.model_input = QLineEdit(str(current.get("model_id", DEFAULT_EMBEDDING_MODEL)), self)
        self.model_input.setPlaceholderText(DEFAULT_EMBEDDING_MODEL)
        form.addRow("Embedding Model:", self.model_input)
        root.addLayout(form)

        helper = QLabel(
            "Default: bge-m3 (strong EN/FR bilingual retrieval). "
            "Lighter alternative: nomic-embed-text. Ticket text never leaves 127.0.0.1.",
            self,
        )
        helper.setWordWrap(True)
        helper.setStyleSheet("color: #94a3b8; font-size: 11px;")
        root.addWidget(helper)

        # Test & Re-index action strip
        tools_row = QHBoxLayout()
        tools_row.setSpacing(8)
        self.test_btn = QPushButton("Test Connection", self)
        self.test_btn.clicked.connect(self._on_test_connection)
        self.reindex_btn = QPushButton("Re-index Archived Tickets", self)
        self.reindex_btn.clicked.connect(self._on_reindex_clicked)
        tools_row.addWidget(self.test_btn)
        tools_row.addWidget(self.reindex_btn)
        tools_row.addStretch(1)
        root.addLayout(tools_row)

        self.status_label = QLabel("", self)
        self.status_label.setWordWrap(True)
        self.status_label.setStyleSheet("color: #7dd3fc; font-size: 11px;")
        self.progress_label = QLabel("", self)
        self.progress_label.setWordWrap(True)
        self.progress_label.setStyleSheet("color: #a78bfa; font-size: 11px;")
        root.addWidget(self.status_label)
        root.addWidget(self.progress_label)

        divider = QFrame(self)
        divider.setFrameShape(QFrame.Shape.HLine)
        root.addWidget(divider)

        btn_row = QHBoxLayout()
        btn_row.addStretch(1)
        self.cancel_btn = QPushButton("Cancel", self)
        self.cancel_btn.setObjectName("btnCancel")
        self.cancel_btn.clicked.connect(self.reject)

        self.save_btn = QPushButton("Save", self)
        self.save_btn.setObjectName("btnPrimary")
        self.save_btn.setDefault(True)
        self.save_btn.clicked.connect(self._on_save_clicked)

        btn_row.addWidget(self.cancel_btn)
        btn_row.addWidget(self.save_btn)
        root.addLayout(btn_row)

    def _build_provider(self) -> EmbeddingProvider:
        if self._injected_provider is not None:
            return self._injected_provider
        return OllamaEmbeddingProvider(
            base_url=self.url_input.text().strip() or DEFAULT_OLLAMA_URL,
            model_id=self.model_input.text().strip() or DEFAULT_EMBEDDING_MODEL,
        )

    def _on_test_connection(self) -> None:
        if self._probe_worker is not None and self._probe_worker.isRunning():
            return
        self.test_btn.setEnabled(False)
        self.status_label.setText("Checking local Ollama endpoint...")
        self._probe_worker = _ConnectionProbeWorker(self._build_provider(), parent=self)
        self._probe_worker.probed.connect(self._on_probe_finished)
        self._probe_worker.start()

    def _on_probe_finished(self, ok: bool, message: str) -> None:
        self.test_btn.setEnabled(True)
        self.status_label.setText(message)
        if not ok:
            self.status_label.setStyleSheet("color: #fbbf24; font-size: 11px;")
        else:
            self.status_label.setStyleSheet("color: #4ade80; font-size: 11px;")

    def _on_reindex_clicked(self) -> None:
        if self._index_worker is not None and self._index_worker.isRunning():
            return
        if self._db_path is None:
            self.progress_label.setText("Background re-indexing requires a file-based SQLite database.")
            return
        self.reindex_btn.setEnabled(False)
        self.progress_label.setText("Starting background indexing...")
        self._index_worker = EmbeddingIndexWorker(
            self._db_path,
            self._build_provider(),
            parent=self,
        )
        self._index_worker.progress_updated.connect(
            lambda done, total: self.progress_label.setText(f"Indexed {done} / {total} tickets...")
        )
        self._index_worker.indexing_finished.connect(self._on_reindex_finished)
        self._index_worker.start()

    def _on_reindex_finished(self, count: int, status: str) -> None:
        self.reindex_btn.setEnabled(True)
        if status == "Offline":
            self.progress_label.setText("Ollama not detected — Exact FTS5 remains active")
        elif count == 0 and status == "Up to date":
            self.progress_label.setText("All archived tickets are already up to date.")
        else:
            self.progress_label.setText(status)

    def _stop_workers(self) -> None:
        if self._probe_worker is not None:
            if self._probe_worker.isRunning():
                self._probe_worker.wait(2000)
            self._probe_worker.deleteLater()
            self._probe_worker = None
        if self._index_worker is not None:
            self._index_worker.stop_and_wait(3000)
            self._index_worker.deleteLater()
            self._index_worker = None

    def _on_save_clicked(self) -> None:
        saved = save_semantic_settings(
            self._get_conn(),
            enabled=self.chk_enabled.isChecked(),
            ollama_url=self.url_input.text().strip() or DEFAULT_OLLAMA_URL,
            model_id=self.model_input.text().strip() or DEFAULT_EMBEDDING_MODEL,
        )
        self._stop_workers()
        self.settings_saved.emit(saved)
        self.accept()

    def reject(self) -> None:
        self._stop_workers()
        super().reject()

    def closeEvent(self, event) -> None:
        self._stop_workers()
        super().closeEvent(event)
