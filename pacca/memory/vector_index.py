"""PACCA Vector Memory Index — Gap #2 (true neural embeddings).

Replaces keyword TF-IDF with OpenAI text-embedding-3-small (1536-dim)
stored as numpy BLOB in SQLite.  Cosine similarity via numpy — exact
ANN at this scale (thousands of docs) is fast enough without sqlite-vec.

Provider priority:
  1. OpenAI text-embedding-3-small  (OPENAI_API_KEY)
  2. No-op fallback — semantic_search() stays on IDF-TF

Design:
  - Embeddings stored in a separate `vec_embeddings` table, keyed by
    SHA-256(content[:1000]) so duplicates are never re-embedded.
  - A single SQLite connection shared with MemoryManager is accepted so
    the caller controls transaction lifecycle.
  - All I/O is synchronous (SQLite + blocking HTTP) so it fits naturally
    inside MemoryManager's sync methods.  Async callers should use
    asyncio.to_thread().
"""
from __future__ import annotations

import hashlib
import json
import os
import sqlite3
import struct
import time
from typing import Any

import numpy as np

# ── constants ─────────────────────────────────────────────────────────────────
_MODEL = "text-embedding-3-small"
_DIM   = 1536
_BATCH = 32          # max texts per OpenAI embedding request


# ── helpers ───────────────────────────────────────────────────────────────────

def _content_hash(text: str) -> str:
    return hashlib.sha256(text[:1000].encode("utf-8")).hexdigest()


def _to_blob(vec: np.ndarray) -> bytes:
    return vec.astype(np.float32).tobytes()


def _from_blob(blob: bytes) -> np.ndarray:
    return np.frombuffer(blob, dtype=np.float32)


def _cosine_np(a: np.ndarray, B: np.ndarray) -> np.ndarray:
    """Cosine similarity of vector a against each row of matrix B."""
    norm_a = np.linalg.norm(a)
    norms_B = np.linalg.norm(B, axis=1)
    if norm_a == 0:
        return np.zeros(len(B), dtype=np.float32)
    denom = norms_B * norm_a
    denom = np.where(denom == 0, 1e-9, denom)
    return (B @ a) / denom


# ── VectorIndex ───────────────────────────────────────────────────────────────

class VectorIndex:
    """Semantic vector index backed by a SQLite BLOB column.

    Usage::

        idx = VectorIndex(conn)
        idx.set_openai_client(openai_client)   # call once at startup
        idx.upsert("Python project dependencies analysed — 3 outdated pkgs")
        results = idx.search("what packages does my repo use?", top_k=5)
    """

    _SCHEMA = """
        CREATE TABLE IF NOT EXISTS vec_embeddings (
            id           INTEGER PRIMARY KEY AUTOINCREMENT,
            content_hash TEXT    NOT NULL UNIQUE,
            content      TEXT    NOT NULL,
            source       TEXT    NOT NULL DEFAULT 'episodic',
            tags         TEXT    NOT NULL DEFAULT '[]',
            embedding    BLOB    NOT NULL,
            model        TEXT    NOT NULL DEFAULT 'text-embedding-3-small',
            created_at   REAL    NOT NULL
        );
        CREATE INDEX IF NOT EXISTS idx_vec_created ON vec_embeddings(created_at);
    """

    def __init__(self, conn: sqlite3.Connection) -> None:
        self._conn = conn
        self._client: Any = None   # openai.OpenAI instance, set via set_openai_client()
        conn.executescript(self._SCHEMA)
        conn.commit()

    # ── provider wiring ───────────────────────────────────────────────────────

    def set_openai_client(self, client: Any) -> None:
        """Wire an openai.OpenAI (or AsyncOpenAI) instance for embedding calls."""
        self._client = client

    def is_available(self) -> bool:
        """Return True when an embedding provider is ready."""
        return self._client is not None

    def _auto_init_client(self) -> bool:
        """Try to create an OpenAI client from OPENAI_API_KEY if not set."""
        if self._client is not None:
            return True
        api_key = os.environ.get("OPENAI_API_KEY", "")
        if not api_key:
            return False
        try:
            import openai
            self._client = openai.OpenAI(api_key=api_key)
            return True
        except Exception:
            return False

    # ── embedding ─────────────────────────────────────────────────────────────

    def _embed_texts(self, texts: list[str]) -> list[np.ndarray] | None:
        """Embed a batch of texts, returning numpy arrays or None on failure."""
        if not self._auto_init_client():
            return None
        try:
            cleaned = [t.replace("\n", " ")[:8000] for t in texts]
            resp = self._client.embeddings.create(model=_MODEL, input=cleaned)
            return [np.array(item.embedding, dtype=np.float32) for item in resp.data]
        except Exception:
            return None

    def embed_one(self, text: str) -> np.ndarray | None:
        """Embed a single text. Returns float32 ndarray or None."""
        result = self._embed_texts([text])
        return result[0] if result else None

    # ── upsert ────────────────────────────────────────────────────────────────

    def upsert(self, content: str, source: str = "episodic",
               tags: list[str] | None = None) -> bool:
        """Embed content and store in SQLite.  Skips if already stored.

        Returns True if a new embedding was stored, False otherwise.
        """
        if not self._auto_init_client():
            return False
        content = content[:1000]
        chash = _content_hash(content)

        existing = self._conn.execute(
            "SELECT id FROM vec_embeddings WHERE content_hash=?", (chash,)
        ).fetchone()
        if existing:
            return False

        vec = self.embed_one(content)
        if vec is None:
            return False

        self._conn.execute(
            """INSERT OR IGNORE INTO vec_embeddings
               (content_hash, content, source, tags, embedding, model, created_at)
               VALUES (?, ?, ?, ?, ?, ?, ?)""",
            (chash, content, source, json.dumps(tags or []),
             _to_blob(vec), _MODEL, time.time())
        )
        self._conn.commit()
        return True

    def upsert_batch(self, items: list[dict]) -> int:
        """Batch-upsert list of {content, source, tags} dicts.

        Makes a single API call for all new texts, reducing latency.
        Returns count of newly stored embeddings.
        """
        if not self._auto_init_client():
            return 0

        new_items = []
        for item in items:
            content = item.get("content", "")[:1000]
            if not content:
                continue
            chash = _content_hash(content)
            existing = self._conn.execute(
                "SELECT id FROM vec_embeddings WHERE content_hash=?", (chash,)
            ).fetchone()
            if not existing:
                new_items.append({**item, "content": content, "hash": chash})

        if not new_items:
            return 0

        stored = 0
        for i in range(0, len(new_items), _BATCH):
            batch = new_items[i:i + _BATCH]
            texts = [b["content"] for b in batch]
            vecs = self._embed_texts(texts)
            if not vecs:
                continue
            for item_meta, vec in zip(batch, vecs):
                try:
                    self._conn.execute(
                        """INSERT OR IGNORE INTO vec_embeddings
                           (content_hash, content, source, tags, embedding, model, created_at)
                           VALUES (?, ?, ?, ?, ?, ?, ?)""",
                        (item_meta["hash"],
                         item_meta["content"],
                         item_meta.get("source", "episodic"),
                         json.dumps(item_meta.get("tags") or []),
                         _to_blob(vec), _MODEL, time.time())
                    )
                    stored += 1
                except Exception:
                    pass
        self._conn.commit()
        return stored

    # ── search ────────────────────────────────────────────────────────────────

    def search(self, query: str, top_k: int = 5,
               min_score: float = 0.30) -> list[dict]:
        """Semantic ANN search via cosine similarity.

        Returns list of {content, source, tags, score, created_at} dicts,
        sorted by descending cosine similarity.

        Falls back to [] if no provider or no stored embeddings.
        """
        if not self._auto_init_client():
            return []

        q_vec = self.embed_one(query)
        if q_vec is None:
            return []

        rows = self._conn.execute(
            """SELECT content, source, tags, embedding, created_at
               FROM vec_embeddings
               ORDER BY created_at DESC
               LIMIT 2000"""
        ).fetchall()
        if not rows:
            return []

        contents    = [r["content"]    for r in rows]
        sources     = [r["source"]     for r in rows]
        tags_json   = [r["tags"]       for r in rows]
        created_ats = [r["created_at"] for r in rows]
        blobs       = [r["embedding"]  for r in rows]

        # Build matrix — skip rows with wrong dim
        valid_idx   = []
        valid_vecs  = []
        for i, blob in enumerate(blobs):
            try:
                v = _from_blob(blob)
                if len(v) == _DIM:
                    valid_idx.append(i)
                    valid_vecs.append(v)
            except Exception:
                pass

        if not valid_vecs:
            return []

        B      = np.stack(valid_vecs)          # (N, 1536)
        scores = _cosine_np(q_vec, B)          # (N,)

        results = []
        for rank_i, orig_i in enumerate(valid_idx):
            score = float(scores[rank_i])
            if score < min_score:
                continue
            try:
                tags = json.loads(tags_json[orig_i])
            except Exception:
                tags = []
            results.append({
                "content":    contents[orig_i],
                "source":     sources[orig_i],
                "tags":       tags,
                "score":      round(score, 4),
                "created_at": created_ats[orig_i],
            })

        results.sort(key=lambda x: x["score"], reverse=True)
        return results[:top_k]

    # ── maintenance ───────────────────────────────────────────────────────────

    def count(self) -> int:
        return self._conn.execute(
            "SELECT COUNT(*) FROM vec_embeddings"
        ).fetchone()[0]

    def delete_old(self, keep_days: int = 90) -> int:
        cutoff = time.time() - keep_days * 86400
        cur = self._conn.execute(
            "DELETE FROM vec_embeddings WHERE created_at < ?", (cutoff,)
        )
        self._conn.commit()
        return cur.rowcount

    def provider_name(self) -> str:
        """Human-readable name of the active embedding provider."""
        if self._client is not None:
            return f"OpenAI/{_MODEL}"
        if os.environ.get("OPENAI_API_KEY"):
            return f"OpenAI/{_MODEL} (lazy)"
        return "none (TF-IDF fallback)"
