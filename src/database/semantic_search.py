"""Optional local-first semantic embedding layer, QThread indexer, and Hybrid FTS5 + Vector RRF search."""

from __future__ import annotations

from array import array
from dataclasses import replace
from datetime import datetime, timezone
import hashlib
import html
import json
import math
from pathlib import Path
import re
import shutil
import sqlite3
import struct
import sys
import threading
import unicodedata
from typing import Any, Callable, Protocol, Sequence, runtime_checkable
import urllib.error
import urllib.request

from PySide6.QtCore import QThread, Signal

try:
    import numpy as _np
except ImportError:  # pragma: no cover - numpy is optional; pure-Python fallback is always present
    _np = None

from src.database.history_fts import (
    HistorySearchResult,
    _detect_schema,
    _fetch_taxonomy_map,
    _format_empty_preview,
    _get_main_db_file,
    _has_preexisting_ticket_data,
    _strip_known_html,
    _table_exists,
    migrate_history_fts,
    sanitize_fts5_query,
    search_history,
)

sys.modules.setdefault("semantic_search", sys.modules[__name__])

SEMANTIC_MIGRATION_VERSION = 4

DEFAULT_OLLAMA_URL = "http://127.0.0.1:11434"
DEFAULT_EMBEDDING_MODEL = "bge-m3"

SETTING_SEMANTIC_ENABLED = "semantic_search_enabled"
SETTING_OLLAMA_URL = "semantic_ollama_url"
SETTING_EMBEDDING_MODEL = "semantic_embedding_model"
SETTING_SEARCH_MODE = "semantic_search_mode"

_MAX_CARD_BODY_CHARS = 2000
_EXACT_CODE_TOKEN_RE = re.compile(r"[A-Za-z]{2,}-\d+|0x[0-9a-fA-F]{4,}|(?:AADSTS|ERR_|KB)\d+", re.IGNORECASE)

# Canonical EN/FR MSP concept buckets for deterministic offline FakeEmbeddingProvider tests.
_FAKE_CONCEPT_GROUPS: tuple[tuple[str, ...], ...] = (
    ("auth", "authentication", "signin", "sign-in", "login", "logon", "lockout", "locked", "verrouille", "compte", "mot de passe", "password", "entra", "aad", "mfa", "2fa", "token", "jeton", "authentification", "acces", "access"),
    ("mail", "email", "inbox", "courriel", "outlook", "exchange", "mailbox", "boite", "partagee", "ost", "pst", "autodiscover", "messagerie", "courrier", "smtp", "send", "receive", "outbox"),
    ("vpn", "network", "reseau", "forticlient", "anyconnect", "tunnel", "dns", "dhcp", "wifi", "wi-fi", "sans fil", "deconnexion", "disconnect", "offline", "hors ligne", "timeout", "gateway", "passerelle", "internet"),
    ("printer", "printers", "imprimante", "imprimantes", "print", "impression", "spooler", "spouleur", "toner", "papier", "paper", "bourrage", "bac", "cordon", "alimentation", "debranche", "pilote", "driver"),
    ("endpoint", "windows", "bsod", "crash", "plantage", "ecran bleu", "freeze", "gele", "hang", "fige", "reboot", "redemarrage", "profil", "profile", "update", "mise a jour", "performance", "lent", "lenteur"),
    ("storage", "onedrive", "sharepoint", "teams", "sync", "synchronisation", "fichier", "folder", "dossier", "quota", "espace disque", "disk"),
    ("security", "defender", "phishing", "hameconnage", "malware", "spam", "pourriel", "quarantine", "quarantaine", "compromis", "compromised", "alerte", "alert"),
    ("hardware", "monitor", "ecran", "moniteur", "dock", "usb", "keyboard", "clavier", "mouse", "souris", "battery", "batterie", "charging"),
)


def _fold_text(text: str) -> str:
    decomposed = unicodedata.normalize("NFKD", text or "")
    return "".join(ch for ch in decomposed if unicodedata.category(ch) != "Mn").lower()


# =============================================================================
# Semantic Settings Helpers (`app_settings` SQLite key/value table)
# =============================================================================


def get_semantic_settings(conn: sqlite3.Connection) -> dict[str, Any]:
    """Read semantic search settings from app_settings with safe local-first defaults."""
    defaults = {
        "enabled": False,
        "ollama_url": DEFAULT_OLLAMA_URL,
        "model_id": DEFAULT_EMBEDDING_MODEL,
        "search_mode": "exact",
    }
    if not _table_exists(conn, "app_settings"):
        return defaults

    rows = conn.execute(
        """
        SELECT key, value FROM app_settings
        WHERE key IN (?, ?, ?, ?)
        """,
        (
            SETTING_SEMANTIC_ENABLED,
            SETTING_OLLAMA_URL,
            SETTING_EMBEDDING_MODEL,
            SETTING_SEARCH_MODE,
        ),
    ).fetchall()
    raw = {str(r[0]): str(r[1]) for r in rows}

    enabled = raw.get(SETTING_SEMANTIC_ENABLED, "false").strip().lower() in ("1", "true", "yes", "on")
    url = raw.get(SETTING_OLLAMA_URL, DEFAULT_OLLAMA_URL).strip() or DEFAULT_OLLAMA_URL
    model = raw.get(SETTING_EMBEDDING_MODEL, DEFAULT_EMBEDDING_MODEL).strip() or DEFAULT_EMBEDDING_MODEL
    mode = raw.get(SETTING_SEARCH_MODE, "exact").strip().lower()
    if mode not in ("exact", "smart"):
        mode = "exact"
    return {
        "enabled": enabled,
        "ollama_url": url.rstrip("/"),
        "model_id": model,
        "search_mode": mode,
    }


def save_semantic_settings(
    conn: sqlite3.Connection,
    *,
    enabled: bool | None = None,
    ollama_url: str | None = None,
    model_id: str | None = None,
    search_mode: str | None = None,
) -> dict[str, Any]:
    """Persist semantic search settings into SQLite app_settings cleanly."""
    if _table_exists(conn, "app_settings"):
        updates: list[tuple[str, str]] = []
        if enabled is not None:
            updates.append((SETTING_SEMANTIC_ENABLED, "true" if enabled else "false"))
        if ollama_url is not None:
            cleaned_url = (ollama_url or "").strip().rstrip("/") or DEFAULT_OLLAMA_URL
            updates.append((SETTING_OLLAMA_URL, cleaned_url))
        if model_id is not None:
            cleaned_model = (model_id or "").strip() or DEFAULT_EMBEDDING_MODEL
            updates.append((SETTING_EMBEDDING_MODEL, cleaned_model))
        if search_mode is not None:
            cleaned_mode = search_mode.strip().lower()
            updates.append((SETTING_SEARCH_MODE, "smart" if cleaned_mode == "smart" else "exact"))

        if updates:
            in_tx = bool(conn.in_transaction)
            if not in_tx:
                conn.execute("BEGIN")
            try:
                for key, val in updates:
                    conn.execute(
                        "INSERT INTO app_settings (key, value) VALUES (?, ?) "
                        "ON CONFLICT(key) DO UPDATE SET value = excluded.value",
                        (key, val),
                    )
                if not in_tx:
                    conn.commit()
            except Exception:
                if not in_tx and conn.in_transaction:
                    conn.rollback()
                raise
    return get_semantic_settings(conn)


# =============================================================================
# Schema Migration (`PRAGMA user_version = 4`, `ticket_embeddings`)
# =============================================================================


def _ensure_pre_embeddings_backup(
    conn: sqlite3.Connection,
    *,
    current_version: int,
    target_version: int,
    schema_kind: str,
) -> Path | None:
    db_file = _get_main_db_file(conn)
    if db_file is None:
        return None
    if current_version == 0 and not _has_preexisting_ticket_data(conn, schema_kind):
        return None

    existing = list(
        db_file.parent.glob(f"{db_file.name}.*v{target_version}_*.pre_embeddings_migration.bak")
    )
    if existing:
        return existing[0]

    ts = datetime.now(timezone.utc).strftime("%Y%m%d_%H%M%S")
    bak_path = (
        db_file.parent
        / f"{db_file.name}.v{current_version}_to_v{target_version}_{ts}.pre_embeddings_migration.bak"
    )
    if not conn.in_transaction:
        bak_conn = sqlite3.connect(str(bak_path))
        try:
            conn.backup(bak_conn)
        finally:
            bak_conn.close()
    else:
        shutil.copy2(db_file, bak_path)
    return bak_path


def migrate_semantic_embeddings(
    conn: sqlite3.Connection,
    *,
    _test_hook: Callable[[sqlite3.Connection], None] | None = None,
) -> bool:
    """Safely upgrade SQLite schema to user_version=4 with `ticket_embeddings` and backup.

    Returns True if migration executed, False if already at SEMANTIC_MIGRATION_VERSION.
    """
    # Ensure Step 1–3 FTS5 + taxonomy tables are present first if starting from v0..v2
    migrate_history_fts(conn)

    current_version = conn.execute("PRAGMA user_version").fetchone()[0]
    if current_version >= SEMANTIC_MIGRATION_VERSION and _table_exists(conn, "ticket_embeddings"):
        return False

    schema_kind = _detect_schema(conn)
    ticket_table = "scratchpads" if schema_kind == "scratchpads" else "ticket_history"
    in_tx = bool(conn.in_transaction)

    if _get_main_db_file(conn) is not None and not in_tx:
        conn.execute("PRAGMA journal_mode = WAL;")
        conn.execute("PRAGMA busy_timeout = 5000;")

    _ensure_pre_embeddings_backup(
        conn,
        current_version=current_version,
        target_version=SEMANTIC_MIGRATION_VERSION,
        schema_kind=schema_kind,
    )

    prev_isolation = conn.isolation_level
    if not in_tx:
        conn.isolation_level = None

    try:
        if in_tx:
            conn.execute("SAVEPOINT semantic_embeddings_migration")
        else:
            conn.execute("BEGIN IMMEDIATE")

        conn.execute("PRAGMA foreign_keys = ON;")
        conn.execute(
            f"""
            CREATE TABLE IF NOT EXISTS ticket_embeddings (
                ticket_id INTEGER PRIMARY KEY REFERENCES {ticket_table}(id) ON DELETE CASCADE,
                model_id TEXT NOT NULL,
                dim INTEGER NOT NULL,
                content_hash TEXT NOT NULL,
                vector BLOB NOT NULL,
                updated_at TEXT NOT NULL
            )
            """
        )
        conn.execute(
            "CREATE INDEX IF NOT EXISTS idx_ticket_embeddings_model_id ON ticket_embeddings(model_id)"
        )

        if _test_hook is not None:
            _test_hook(conn)

        conn.execute(f"PRAGMA user_version = {SEMANTIC_MIGRATION_VERSION}")

        if in_tx:
            conn.execute("RELEASE SAVEPOINT semantic_embeddings_migration")
        else:
            conn.execute("COMMIT")
        return True
    except Exception:
        if in_tx:
            try:
                conn.execute("ROLLBACK TO SAVEPOINT semantic_embeddings_migration")
                conn.execute("RELEASE SAVEPOINT semantic_embeddings_migration")
            except sqlite3.Error:
                pass
        elif conn.in_transaction:
            conn.execute("ROLLBACK")
        raise
    finally:
        if not in_tx:
            conn.isolation_level = prev_isolation


# =============================================================================
# Semantic Card Builder & Stdlib Float32 Vector Math
# =============================================================================


def build_semantic_card(
    ticket: dict[str, Any],
    taxonomy_labels: Sequence[str] = (),
) -> tuple[str, str]:
    """Compose a compact semantic card from taxonomy, metadata, and cleaned notes + SHA-256 hash."""
    t_num = re.sub(r"\s+", " ", str(ticket.get("ticket_number", "") or "")).strip()
    client = re.sub(
        r"\s+",
        " ",
        str(ticket.get("client", ticket.get("client_name", "")) or ""),
    ).strip()
    title = re.sub(r"\s+", " ", str(ticket.get("title", "") or "")).strip()
    tags = re.sub(r"\s+", " ", str(ticket.get("tags", "") or "")).strip()

    raw_body = str(ticket.get("content_html", ticket.get("body", "")) or "")
    body_clean = _strip_known_html(raw_body)
    body_clean = re.sub(r"\s+", " ", body_clean).strip()[:_MAX_CARD_BODY_CHARS]

    clean_tax = [re.sub(r"\s+", " ", str(lbl)).strip() for lbl in taxonomy_labels if str(lbl).strip()]

    lines: list[str] = []
    if clean_tax:
        lines.append(f"Taxonomy: {' | '.join(clean_tax)}")
    if client:
        lines.append(f"Client: {client}")
    if t_num or title:
        header = " ".join(part for part in (f"#{t_num}" if t_num else "", title) if part)
        lines.append(f"Ticket: {header}")
    if tags:
        lines.append(f"Tags: {tags}")
    if body_clean:
        lines.append(f"Notes: {body_clean}")

    card_text = "\n".join(lines).strip()
    content_hash = hashlib.sha256(card_text.encode("utf-8")).hexdigest()
    return card_text, content_hash


def l2_normalize(vec: Sequence[float]) -> list[float]:
    """Return L2-normalized copy of vec (or zeros if norm == 0)."""
    vals = [float(v) for v in vec]
    if not vals:
        return []
    sq_sum = sum(v * v for v in vals)
    if sq_sum <= 0.0:
        return [0.0] * len(vals)
    norm = math.sqrt(sq_sum)
    return [v / norm for v in vals]


def pack_vector(vec: Sequence[float], *, normalize: bool = True) -> bytes:
    """Serialize float sequence to IEEE-754 little-endian float32 bytes."""
    vals = l2_normalize(vec) if normalize else [float(v) for v in vec]
    if not vals:
        raise ValueError("Cannot pack empty embedding vector.")
    return struct.pack(f"<{len(vals)}f", *vals)


def unpack_vector(blob: bytes) -> array:
    """Deserialize IEEE-754 little-endian float32 BLOB into array('f')."""
    arr = array("f")
    if not blob:
        return arr
    arr.frombytes(blob)
    if sys.byteorder != "little":
        arr.byteswap()
    return arr


def cosine_dot(a: Sequence[float] | bytes, b: Sequence[float] | bytes) -> float:
    """Compute dot product / cosine similarity for L2-normalized vectors or packed float32 BLOBs."""
    if _np is not None:
        vec_a = (
            _np.frombuffer(a, dtype="<f4")
            if isinstance(a, (bytes, bytearray, memoryview))
            else _np.asarray(a, dtype=_np.float32)
        )
        vec_b = (
            _np.frombuffer(b, dtype="<f4")
            if isinstance(b, (bytes, bytearray, memoryview))
            else _np.asarray(b, dtype=_np.float32)
        )
        if vec_a.size == 0 or vec_a.size != vec_b.size:
            return 0.0
        return float(_np.dot(vec_a, vec_b))

    vals_a = unpack_vector(bytes(a)) if isinstance(a, (bytes, bytearray, memoryview)) else a
    vals_b = unpack_vector(bytes(b)) if isinstance(b, (bytes, bytearray, memoryview)) else b
    if not vals_a or len(vals_a) != len(vals_b):
        return 0.0
    return float(sum(x * y for x, y in zip(vals_a, vals_b)))


# =============================================================================
# Pluggable Embedding Providers (`OllamaEmbeddingProvider`, `FakeEmbeddingProvider`)
# =============================================================================


@runtime_checkable
class EmbeddingProvider(Protocol):
    model_id: str

    def is_available(self) -> bool: ...

    def embed_texts(self, texts: list[str]) -> list[list[float]]: ...


class OllamaEmbeddingProvider:
    """Local HTTP embedding client for Ollama (`/api/embed` with `/api/embeddings` 404 fallback)."""

    def __init__(
        self,
        *,
        base_url: str = DEFAULT_OLLAMA_URL,
        model_id: str = DEFAULT_EMBEDDING_MODEL,
        availability_timeout: float = 1.5,
        embed_timeout: float = 5.0,
    ) -> None:
        cleaned = (base_url or DEFAULT_OLLAMA_URL).strip().rstrip("/")
        self.base_url = cleaned or DEFAULT_OLLAMA_URL
        self.model_id = (model_id or DEFAULT_EMBEDDING_MODEL).strip() or DEFAULT_EMBEDDING_MODEL
        self.availability_timeout = float(availability_timeout)
        self.embed_timeout = float(embed_timeout)

    def is_available(self) -> bool:
        req = urllib.request.Request(f"{self.base_url}/api/tags", method="GET")
        try:
            with urllib.request.urlopen(req, timeout=self.availability_timeout) as resp:
                return 200 <= getattr(resp, "status", 200) < 300
        except (urllib.error.URLError, urllib.error.HTTPError, OSError, TimeoutError, ValueError):
            return False

    def _post_json(self, path: str, payload: dict[str, Any], timeout: float) -> dict[str, Any]:
        body = json.dumps(payload).encode("utf-8")
        req = urllib.request.Request(
            f"{self.base_url}{path}",
            data=body,
            headers={"Content-Type": "application/json"},
            method="POST",
        )
        with urllib.request.urlopen(req, timeout=timeout) as resp:
            return json.loads(resp.read().decode("utf-8"))

    def embed_texts(self, texts: list[str]) -> list[list[float]]:
        if not texts:
            return []
        try:
            data = self._post_json(
                "/api/embed",
                {"model": self.model_id, "input": texts},
                timeout=self.embed_timeout,
            )
            raw_vecs = data.get("embeddings") or []
            if len(raw_vecs) == len(texts):
                return [l2_normalize(v) for v in raw_vecs]
        except urllib.error.HTTPError as err:
            if err.code != 404:
                raise

        # Legacy Ollama API fallback (`POST /api/embeddings`)
        vectors: list[list[float]] = []
        for text in texts:
            data = self._post_json(
                "/api/embeddings",
                {"model": self.model_id, "prompt": text},
                timeout=self.embed_timeout,
            )
            vec = data.get("embedding") or []
            if not vec:
                raise ValueError(f"Ollama returned empty embedding for model '{self.model_id}'.")
            vectors.append(l2_normalize(vec))
        return vectors


class FakeEmbeddingProvider:
    """Deterministic pure-Python normalized embedding provider for offline pytest verification."""

    def __init__(
        self,
        *,
        model_id: str = "fake-bge-m3",
        dim: int = 64,
        available: bool = True,
        fail_after: int | None = None,
        custom_vectors: dict[str, Sequence[float]] | None = None,
    ) -> None:
        self.model_id = model_id
        self.dim = max(16, int(dim))
        self.available = available
        self.fail_after = fail_after
        self.custom_vectors = {k: l2_normalize(v) for k, v in (custom_vectors or {}).items()}
        self.calls: list[list[str]] = []

    def is_available(self) -> bool:
        return bool(self.available)

    def _encode_one(self, text: str) -> list[float]:
        if text in self.custom_vectors:
            vec = list(self.custom_vectors[text])
            if len(vec) == self.dim:
                return vec

        vec = [0.0] * self.dim
        folded = _fold_text(text)

        # 1. Concept dimensions so EN/FR synonym pairs overlap cleanly even with zero shared literals
        concept_base = len(_FAKE_CONCEPT_GROUPS)
        for idx, keywords in enumerate(_FAKE_CONCEPT_GROUPS):
            hits = 0
            for kw in keywords:
                if f" {kw} " in f" {folded} " or (len(kw) >= 4 and kw in folded):
                    hits += 1
            if hits > 0:
                vec[idx % self.dim] += 2.5 * min(hits, 3)

        # 2. Hashed token + character 3-gram features in remaining dimensions
        hash_span = max(8, self.dim - concept_base)
        tokens = re.findall(r"[a-z0-9]{2,}", folded)
        for tok in tokens:
            digest = hashlib.blake2b(tok.encode("utf-8"), digest_size=8).digest()
            slot = concept_base + (int.from_bytes(digest[:4], "little") % hash_span)
            sign = 1.0 if (digest[4] & 1) == 0 else -1.0
            vec[slot] += sign * 0.45

        return l2_normalize(vec)

    def embed_texts(self, texts: list[str]) -> list[list[float]]:
        self.calls.append(list(texts))
        if not self.available:
            raise ConnectionError("Embedding provider is offline.")
        if self.fail_after is not None and len(self.calls) > self.fail_after:
            raise ConnectionError("Simulated mid-batch Ollama failure.")
        return [self._encode_one(t) for t in texts]


# =============================================================================
# Thread-Safe Background Indexing (`index_pending_embeddings_sync` & `QThread`)
# =============================================================================


def _fetch_taxonomy_label_map(conn: sqlite3.Connection, ticket_ids: Sequence[int]) -> dict[int, list[str]]:
    if not ticket_ids or not _table_exists(conn, "ticket_taxonomy"):
        return {}
    placeholders = ",".join("?" for _ in ticket_ids)
    rows = conn.execute(
        f"""
        SELECT tt.ticket_id, tn.label
        FROM ticket_taxonomy tt
        JOIN taxonomy_nodes tn ON tn.id = tt.node_id
        WHERE tt.ticket_id IN ({placeholders})
        ORDER BY tn.axis ASC, tn.sort_order ASC, tn.slug ASC
        """,
        list(ticket_ids),
    ).fetchall()
    mapping: dict[int, list[str]] = {}
    for tid, lbl in rows:
        mapping.setdefault(int(tid), []).append(str(lbl))
    return mapping


def _collect_pending_embedding_cards(
    conn: sqlite3.Connection,
    model_id: str,
) -> list[tuple[int, str, str]]:
    """Return [(ticket_id, card_text, content_hash)] for archived tickets needing embeddings."""
    if not _table_exists(conn, "ticket_embeddings"):
        return []

    schema_kind = _detect_schema(conn)
    if schema_kind == "scratchpads":
        rows = conn.execute(
            """
            SELECT
                h.id, h.ticket_number, COALESCE(h.client_name, ''), COALESCE(h.title, ''),
                COALESCE(h.tags, ''), COALESCE(h.content_html, ''),
                e.model_id, e.content_hash
            FROM scratchpads AS h
            LEFT JOIN ticket_embeddings AS e ON e.ticket_id = h.id
            WHERE h.status = 'archived'
            ORDER BY h.id DESC
            """
        ).fetchall()
    else:
        rows = conn.execute(
            """
            SELECT
                h.id, h.ticket_number, COALESCE(h.client, ''), COALESCE(h.title, ''),
                COALESCE(h.tags, ''), COALESCE(h.body, ''),
                e.model_id, e.content_hash
            FROM ticket_history AS h
            LEFT JOIN ticket_embeddings AS e ON e.ticket_id = h.id
            ORDER BY h.id DESC
            """
        ).fetchall()

    label_map = _fetch_taxonomy_label_map(conn, [int(r[0]) for r in rows])
    pending: list[tuple[int, str, str]] = []
    for row in rows:
        tid = int(row[0])
        ticket_dict = {
            "id": tid,
            "ticket_number": row[1] or "",
            "client": row[2] or "",
            "title": row[3] or "",
            "tags": row[4] or "",
            "body": row[5] or "",
        }
        card_text, card_hash = build_semantic_card(ticket_dict, label_map.get(tid, ()))
        if not card_text:
            continue
        existing_model = row[6]
        existing_hash = row[7]
        if existing_model == model_id and existing_hash == card_hash:
            continue
        pending.append((tid, card_text, card_hash))
    return pending


def index_pending_embeddings_sync(
    conn: sqlite3.Connection,
    provider: EmbeddingProvider,
    *,
    batch_size: int = 12,
    stop_event: threading.Event | None = None,
    progress_cb: Callable[[int, int], None] | None = None,
) -> tuple[int, str]:
    """Incrementally index archived tickets missing or stale in `ticket_embeddings`.

    Returns ``(count_indexed, final_status_message)``.
    """
    if not _table_exists(conn, "ticket_embeddings"):
        return 0, "Schema missing ticket_embeddings"

    try:
        if not provider.is_available():
            return 0, "Offline"
    except Exception:
        return 0, "Offline"

    pending = _collect_pending_embedding_cards(conn, provider.model_id)
    total = len(pending)
    if total == 0:
        return 0, "Up to date"

    batch_n = max(1, int(batch_size))
    indexed = 0
    if progress_cb is not None:
        progress_cb(0, total)

    for start in range(0, total, batch_n):
        if stop_event is not None and stop_event.is_set():
            return indexed, "Stopped"
        chunk = pending[start : start + batch_n]
        texts = [item[1] for item in chunk]
        try:
            vectors = provider.embed_texts(texts)
        except Exception:
            return indexed, "Offline"

        if len(vectors) != len(chunk):
            return indexed, "Offline"

        now_str = datetime.now(timezone.utc).strftime("%Y-%m-%d %H:%M:%S")
        in_tx = bool(conn.in_transaction)
        if not in_tx:
            conn.execute("BEGIN")
        try:
            for (tid, _text, content_hash), vec in zip(chunk, vectors):
                blob = pack_vector(vec, normalize=True)
                conn.execute(
                    """
                    INSERT INTO ticket_embeddings (ticket_id, model_id, dim, content_hash, vector, updated_at)
                    VALUES (?, ?, ?, ?, ?, ?)
                    ON CONFLICT(ticket_id) DO UPDATE SET
                        model_id = excluded.model_id,
                        dim = excluded.dim,
                        content_hash = excluded.content_hash,
                        vector = excluded.vector,
                        updated_at = excluded.updated_at
                    """,
                    (tid, provider.model_id, len(vec), content_hash, blob, now_str),
                )
            if not in_tx:
                conn.commit()
        except Exception:
            if not in_tx and conn.in_transaction:
                conn.rollback()
            raise

        indexed += len(chunk)
        if progress_cb is not None:
            progress_cb(indexed, total)

    return indexed, f"Indexed {indexed} tickets"


class EmbeddingIndexWorker(QThread):
    """Thread-safe background indexer opening its own dedicated WAL SQLite connection."""

    progress_updated = Signal(int, int)
    status_changed = Signal(str)
    indexing_finished = Signal(int, str)

    def __init__(
        self,
        db_path: str | Path,
        provider: EmbeddingProvider,
        *,
        batch_size: int = 12,
        parent=None,
    ) -> None:
        super().__init__(parent)
        self._db_path = Path(db_path)
        self._provider = provider
        self._batch_size = max(1, int(batch_size))
        self._stop_event = threading.Event()

    def request_stop(self) -> None:
        self._stop_event.set()
        self.requestInterruption()

    def stop_and_wait(self, timeout_ms: int = 3000) -> bool:
        self.request_stop()
        if self.isRunning():
            return self.wait(timeout_ms)
        return True

    def run(self) -> None:
        worker_conn: sqlite3.Connection | None = None
        count = 0
        status = "Idle"
        try:
            self.status_changed.emit("Indexing...")
            worker_conn = sqlite3.connect(
                str(self._db_path),
                timeout=5.0,
                check_same_thread=False,
            )
            worker_conn.execute("PRAGMA journal_mode = WAL;")
            worker_conn.execute("PRAGMA foreign_keys = ON;")
            worker_conn.execute("PRAGMA busy_timeout = 5000;")

            count, status = index_pending_embeddings_sync(
                worker_conn,
                self._provider,
                batch_size=self._batch_size,
                stop_event=self._stop_event,
                progress_cb=lambda done, total: self.progress_updated.emit(done, total),
            )
        except Exception:
            status = "Offline"
        finally:
            if worker_conn is not None:
                try:
                    worker_conn.close()
                except sqlite3.Error:
                    pass
        self.status_changed.emit(status)
        self.indexing_finished.emit(count, status)


class QueryEmbeddingWorker(QThread):
    """Off-UI-thread query embedder so Smart search typing stays completely lag-free."""

    query_embedded = Signal(int, str, object)  # (generation, raw_query, list[float] | None)

    def __init__(
        self,
        generation: int,
        raw_query: str,
        provider: EmbeddingProvider,
        parent=None,
    ) -> None:
        super().__init__(parent)
        self.generation = generation
        self.raw_query = raw_query
        self._provider = provider

    def run(self) -> None:
        vector: list[float] | None = None
        try:
            if not self.isInterruptionRequested() and self._provider.is_available():
                res = self._provider.embed_texts([self.raw_query])
                if res:
                    vector = l2_normalize(res[0])
        except Exception:
            vector = None
        self.query_embedded.emit(self.generation, self.raw_query, vector)


# =============================================================================
# Hybrid FTS5 + Vector Reciprocal Rank Fusion Search (`search_history_hybrid`)
# =============================================================================


def _build_filtered_ticket_sql(
    schema_kind: str,
    *,
    client: str | None = None,
    date_from: str | None = None,
    date_to: str | None = None,
    taxonomy_slugs: Sequence[str] | str | None = None,
) -> tuple[str, str, str, str, list[str], list[object]]:
    if schema_kind == "scratchpads":
        table_name = "scratchpads"
        archived_expr = "COALESCE(NULLIF(h.archived_at, ''), h.updated_at, '')"
        client_col = "h.client_name"
        select_cols = (
            "h.id, h.ticket_number, COALESCE(h.client_name, ''), "
            "COALESCE(h.title, ''), COALESCE(h.tags, ''), "
            f"{archived_expr} AS archived_ts, COALESCE(h.content_html, '')"
        )
        filters: list[str] = ["h.status = 'archived'"]
    else:
        table_name = "ticket_history"
        archived_expr = "h.archived_at"
        client_col = "h.client"
        select_cols = (
            "h.id, h.ticket_number, COALESCE(h.client, ''), "
            "COALESCE(h.title, ''), COALESCE(h.tags, ''), "
            "COALESCE(h.archived_at, '') AS archived_ts, COALESCE(h.body, '')"
        )
        filters = []

    params: list[object] = []
    if client:
        filters.append(f"{client_col} = ?")
        params.append(client)
    if date_from:
        filters.append(f"{archived_expr} >= ?")
        params.append(date_from)
    if date_to:
        upper = f"{date_to}\uffff" if len(date_to) == 10 else date_to
        filters.append(f"{archived_expr} <= ?")
        params.append(upper)

    if isinstance(taxonomy_slugs, str):
        slug_list = [s.strip() for s in taxonomy_slugs.split(",") if s.strip()]
    else:
        slug_list = [str(s).strip() for s in (taxonomy_slugs or ()) if str(s).strip()]

    for slug in slug_list:
        filters.append(
            """
            EXISTS (
                SELECT 1
                FROM ticket_taxonomy tt
                JOIN taxonomy_nodes tn ON tn.id = tt.node_id
                WHERE tt.ticket_id = h.id AND (tn.slug = ? OR tn.parent_slug = ?)
            )
            """
        )
        params.extend([slug, slug])

    return table_name, archived_expr, client_col, select_cols, filters, params


def _has_exact_identifier_match(raw_query: str, result: HistorySearchResult) -> bool:
    q = (raw_query or "").strip().lower()
    if not q:
        return False
    t_num = (result.ticket_number or "").strip().lower()
    if t_num and (q == t_num or (len(q) >= 3 and any(ch.isdigit() for ch in q) and q in t_num)):
        return True
    for code in _EXACT_CODE_TOKEN_RE.findall(raw_query or ""):
        low_code = code.lower()
        hay = _fold_text(
            f"{result.ticket_number} {result.title} {html.unescape(result.snippet_html)}"
        )
        if low_code in hay:
            return True
    return False


def _vector_search_filtered(
    conn: sqlite3.Connection,
    query_vec: Sequence[float],
    *,
    model_id: str,
    min_similarity: float = 0.25,
    client: str | None = None,
    date_from: str | None = None,
    date_to: str | None = None,
    taxonomy_slugs: Sequence[str] | str | None = None,
    exclude_id: int | None = None,
) -> list[tuple[HistorySearchResult, float]]:
    if not _table_exists(conn, "ticket_embeddings"):
        return []

    schema_kind = _detect_schema(conn)
    table_name, _arch, _cc, select_cols, filters, filter_params = _build_filtered_ticket_sql(
        schema_kind,
        client=client,
        date_from=date_from,
        date_to=date_to,
        taxonomy_slugs=taxonomy_slugs,
    )
    where_parts = ["e.model_id = ?", *filters]
    params: list[object] = [model_id, *filter_params]
    if exclude_id is not None:
        where_parts.append("h.id <> ?")
        params.append(int(exclude_id))

    rows = conn.execute(
        f"""
        SELECT {select_cols}, e.vector
        FROM ticket_embeddings AS e
        JOIN {table_name} AS h ON h.id = e.ticket_id
        WHERE {' AND '.join(where_parts)}
        ORDER BY archived_ts DESC, h.id DESC
        """,
        params,
    ).fetchall()

    norm_q = l2_normalize(query_vec)
    scored: list[tuple[int, sqlite3.Row, float]] = []
    for row in rows:
        sim = cosine_dot(norm_q, row[7])
        if sim >= float(min_similarity):
            scored.append((int(row[0]), row, sim))

    if not scored:
        return []

    scored.sort(key=lambda entry: (-entry[2], str(entry[1][5] or ""), entry[0]))
    tax_map = _fetch_taxonomy_map(conn, [entry[0] for entry in scored])

    results: list[tuple[HistorySearchResult, float]] = []
    for tid, row, sim in scored:
        res = HistorySearchResult(
            id=tid,
            ticket_number=row[1] or "",
            client=row[2] or "",
            title=row[3] or "",
            tags=row[4] or "",
            archived_at=row[5] or "",
            snippet_html=_format_empty_preview(row[6] or ""),
            rank=-sim,
            taxonomy_slugs=tax_map.get(tid, ()),
            match_type="semantic",
        )
        results.append((res, sim))
    return results


def search_history_hybrid(
    conn: sqlite3.Connection,
    query: str = "",
    *,
    mode: str = "exact",
    provider: EmbeddingProvider | None = None,
    query_vector: Sequence[float] | None = None,
    model_id: str | None = None,
    min_similarity: float = 0.25,
    client: str | None = None,
    boost_client: str | None = None,
    date_from: str | None = None,
    date_to: str | None = None,
    taxonomy_slugs: Sequence[str] | str | None = None,
    match_any: bool = False,
    sort_by: str = "relevance",
    limit: int = 100,
    offset: int = 0,
) -> tuple[list[HistorySearchResult], int]:
    """Hybrid FTS5 + Vector Reciprocal Rank Fusion search with automatic Exact FTS5 fallback."""
    mode_clean = (mode or "exact").strip().lower()
    if mode_clean != "smart" or sanitize_fts5_query(query, match_any=match_any) is None:
        return search_history(
            conn,
            query,
            client=client,
            boost_client=boost_client,
            date_from=date_from,
            date_to=date_to,
            taxonomy_slugs=taxonomy_slugs,
            match_any=match_any,
            sort_by=sort_by,
            limit=limit,
            offset=offset,
        )

    active_model = (model_id or getattr(provider, "model_id", "") or "").strip()
    if not active_model or not _table_exists(conn, "ticket_embeddings"):
        return search_history(
            conn,
            query,
            client=client,
            boost_client=boost_client,
            date_from=date_from,
            date_to=date_to,
            taxonomy_slugs=taxonomy_slugs,
            match_any=match_any,
            sort_by=sort_by,
            limit=limit,
            offset=offset,
        )

    has_rows = conn.execute(
        "SELECT 1 FROM ticket_embeddings WHERE model_id = ? LIMIT 1",
        (active_model,),
    ).fetchone()
    if has_rows is None:
        return search_history(
            conn,
            query,
            client=client,
            boost_client=boost_client,
            date_from=date_from,
            date_to=date_to,
            taxonomy_slugs=taxonomy_slugs,
            match_any=match_any,
            sort_by=sort_by,
            limit=limit,
            offset=offset,
        )

    q_vec: list[float] | None = None
    if query_vector is not None:
        q_vec = l2_normalize(query_vector)
    elif provider is not None:
        try:
            if provider.is_available():
                vecs = provider.embed_texts([query])
                if vecs:
                    q_vec = l2_normalize(vecs[0])
        except Exception:
            q_vec = None

    if not q_vec:
        return search_history(
            conn,
            query,
            client=client,
            boost_client=boost_client,
            date_from=date_from,
            date_to=date_to,
            taxonomy_slugs=taxonomy_slugs,
            match_any=match_any,
            sort_by=sort_by,
            limit=limit,
            offset=offset,
        )

    fts_results, _ = search_history(
        conn,
        query,
        client=client,
        boost_client=boost_client,
        date_from=date_from,
        date_to=date_to,
        taxonomy_slugs=taxonomy_slugs,
        match_any=match_any,
        sort_by="relevance",
        limit=max(200, limit + offset),
        offset=0,
    )
    vec_results = _vector_search_filtered(
        conn,
        q_vec,
        model_id=active_model,
        min_similarity=min_similarity,
        client=client,
        date_from=date_from,
        date_to=date_to,
        taxonomy_slugs=taxonomy_slugs,
    )

    fts_ranks: dict[int, tuple[int, HistorySearchResult]] = {
        res.id: (idx + 1, res) for idx, res in enumerate(fts_results)
    }
    vec_ranks: dict[int, tuple[int, HistorySearchResult, float]] = {
        res.id: (idx + 1, res, sim) for idx, (res, sim) in enumerate(vec_results)
    }

    all_ids = set(fts_ranks.keys()) | set(vec_ranks.keys())
    if not all_ids:
        return [], 0

    k = 60.0
    combined: list[tuple[float, bool, str, int, HistorySearchResult]] = []
    for tid in all_ids:
        fts_entry = fts_ranks.get(tid)
        vec_entry = vec_ranks.get(tid)

        if fts_entry is not None and vec_entry is not None:
            match_type = "both"
            base_res = fts_entry[1]
        elif fts_entry is not None:
            match_type = "exact"
            base_res = fts_entry[1]
        else:
            match_type = "semantic"
            base_res = vec_entry[1]  # type: ignore[index]

        exact_hit = _has_exact_identifier_match(query, base_res)
        rrf = 0.0
        if fts_entry is not None:
            fts_weight = 1.25 if exact_hit else 1.0
            rrf += fts_weight / (k + fts_entry[0])
        if vec_entry is not None:
            rrf += 1.0 / (k + vec_entry[0])
        if exact_hit:
            rrf += 0.05

        final_res = replace(base_res, rank=-rrf, match_type=match_type)
        combined.append((rrf, exact_hit, final_res.archived_at or "", tid, final_res))

    if sort_by == "date":
        combined.sort(key=lambda item: (item[2], item[3]), reverse=True)
    else:
        combined.sort(key=lambda item: (-item[0], not item[1], -item[3]))

    total = len(combined)
    paged = [item[4] for item in combined[offset : offset + limit]]
    return paged, total


def find_similar_tickets(
    conn: sqlite3.Connection,
    text: str,
    provider: EmbeddingProvider,
    *,
    exclude_id: int | None = None,
    min_similarity: float = 0.25,
    limit: int = 5,
) -> list[HistorySearchResult]:
    """Return top semantically similar archived tickets for live triage or related recommendations."""
    clean_text = (text or "").strip()
    if not clean_text or provider is None or not _table_exists(conn, "ticket_embeddings"):
        return []
    try:
        if not provider.is_available():
            return []
        vecs = provider.embed_texts([clean_text])
        if not vecs:
            return []
    except Exception:
        return []

    hits = _vector_search_filtered(
        conn,
        vecs[0],
        model_id=provider.model_id,
        min_similarity=min_similarity,
        exclude_id=exclude_id,
    )
    return [res for res, _sim in hits[: max(1, int(limit))]]
