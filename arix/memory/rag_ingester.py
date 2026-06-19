"""RAG Knowledge Base — document ingestion and BM25 + vector retrieval.

Ingests PDF, DOCX, Markdown, and plain text documents into a searchable
knowledge base. Inspired by AstrBot's RAG system (BM25 + dense retrieval).

Storage: ~/.arix/knowledge/  (index JSON + raw chunk store)
"""
from __future__ import annotations

import hashlib
import json
import logging
import math
import os
import re
import time
import uuid
from collections import Counter
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any, Dict, List, Optional, Tuple

log = logging.getLogger(__name__)

_KNOWLEDGE_DIR = Path.home() / ".arix" / "knowledge"
_INDEX_FILE = _KNOWLEDGE_DIR / "index.json"
_CHUNK_SIZE = 400        # tokens (approx words)
_CHUNK_OVERLAP = 50
_TOP_K = 5


# ── Data models ───────────────────────────────────────────────────────────────

@dataclass
class KnowledgeChunk:
    chunk_id: str
    doc_id: str
    doc_name: str
    text: str
    char_start: int
    page: int = 0
    score: float = 0.0

    def to_dict(self) -> dict:
        return {
            "chunk_id": self.chunk_id,
            "doc_id": self.doc_id,
            "doc_name": self.doc_name,
            "text": self.text,
            "char_start": self.char_start,
            "page": self.page,
        }

    @classmethod
    def from_dict(cls, d: dict) -> "KnowledgeChunk":
        return cls(**{k: d[k] for k in ("chunk_id", "doc_id", "doc_name", "text", "char_start", "page")})


@dataclass
class KnowledgeDoc:
    doc_id: str
    name: str
    path: str
    file_type: str
    char_count: int
    chunk_count: int
    ingested_at: float = field(default_factory=time.time)
    checksum: str = ""

    def to_dict(self) -> dict:
        return {
            "doc_id": self.doc_id,
            "name": self.name,
            "path": self.path,
            "file_type": self.file_type,
            "char_count": self.char_count,
            "chunk_count": self.chunk_count,
            "ingested_at": self.ingested_at,
            "checksum": self.checksum,
        }

    @classmethod
    def from_dict(cls, d: dict) -> "KnowledgeDoc":
        return cls(**d)


# ── Text extraction ───────────────────────────────────────────────────────────

def _extract_text(path: Path) -> Tuple[str, str]:
    """Extract plain text from a file. Returns (text, file_type)."""
    suffix = path.suffix.lower()

    if suffix == ".pdf":
        return _extract_pdf(path), "pdf"
    elif suffix == ".docx":
        return _extract_docx(path), "docx"
    elif suffix in (".md", ".markdown"):
        return path.read_text(errors="ignore"), "markdown"
    elif suffix in (".txt", ".rst", ".csv", ".log"):
        return path.read_text(errors="ignore"), "text"
    elif suffix in (".py", ".js", ".ts", ".go", ".rs", ".java", ".cpp", ".c", ".h"):
        return path.read_text(errors="ignore"), "code"
    elif suffix in (".json",):
        try:
            data = json.loads(path.read_text(errors="ignore"))
            return json.dumps(data, indent=2)[:50000], "json"
        except Exception:
            return path.read_text(errors="ignore")[:50000], "text"
    else:
        # Best-effort plain text
        try:
            text = path.read_text(errors="ignore")
            return text[:100000], "text"
        except Exception as e:
            raise ValueError(f"Cannot read {path.name}: {e}") from e


def _extract_pdf(path: Path) -> str:
    try:
        import pypdf
        reader = pypdf.PdfReader(str(path))
        pages = []
        for i, page in enumerate(reader.pages):
            text = page.extract_text() or ""
            pages.append(f"[Page {i+1}]\n{text}")
        return "\n\n".join(pages)
    except ImportError:
        pass
    try:
        import pdfminer.high_level as pdfminer
        return pdfminer.extract_text(str(path))
    except ImportError:
        raise ValueError("PDF extraction requires pypdf: pip install pypdf")


def _extract_docx(path: Path) -> str:
    try:
        import docx
        doc = docx.Document(str(path))
        return "\n".join(p.text for p in doc.paragraphs)
    except ImportError:
        raise ValueError("DOCX extraction requires python-docx: pip install python-docx")


# ── Chunking ──────────────────────────────────────────────────────────────────

def _chunk_text(text: str, doc_id: str, doc_name: str,
                chunk_size: int = _CHUNK_SIZE,
                overlap: int = _CHUNK_OVERLAP) -> List[KnowledgeChunk]:
    words = text.split()
    chunks = []
    i = 0
    char_cursor = 0

    while i < len(words):
        end = min(i + chunk_size, len(words))
        chunk_words = words[i:end]
        chunk_text = " ".join(chunk_words)

        # Estimate char_start
        char_start = len(" ".join(words[:i]))
        page = max(1, (i // 500) + 1)   # rough page estimate

        chunks.append(KnowledgeChunk(
            chunk_id=str(uuid.uuid4())[:8],
            doc_id=doc_id,
            doc_name=doc_name,
            text=chunk_text,
            char_start=char_start,
            page=page,
        ))
        i += (chunk_size - overlap)

    return chunks


# ── BM25 scorer ───────────────────────────────────────────────────────────────

class BM25:
    """Simple BM25 implementation for local keyword search."""

    def __init__(self, k1: float = 1.5, b: float = 0.75) -> None:
        self.k1 = k1
        self.b = b
        self._docs: List[List[str]] = []
        self._chunk_ids: List[str] = []
        self._idf: Dict[str, float] = {}
        self._avgdl: float = 0.0

    def _tokenize(self, text: str) -> List[str]:
        return re.findall(r'\b\w+\b', text.lower())

    def index(self, chunks: List[KnowledgeChunk]) -> None:
        self._docs = [self._tokenize(c.text) for c in chunks]
        self._chunk_ids = [c.chunk_id for c in chunks]
        N = len(self._docs)
        self._avgdl = sum(len(d) for d in self._docs) / max(N, 1)

        df: Counter = Counter()
        for doc in self._docs:
            for term in set(doc):
                df[term] += 1

        self._idf = {
            term: math.log((N - freq + 0.5) / (freq + 0.5) + 1)
            for term, freq in df.items()
        }

    def score(self, query: str, top_k: int = _TOP_K) -> List[Tuple[str, float]]:
        if not self._docs:
            return []
        q_terms = self._tokenize(query)
        scores = []
        for idx, doc in enumerate(self._docs):
            dl = len(doc)
            tf_map = Counter(doc)
            sc = 0.0
            for term in q_terms:
                tf = tf_map.get(term, 0)
                idf = self._idf.get(term, 0.0)
                numerator = tf * (self.k1 + 1)
                denominator = tf + self.k1 * (1 - self.b + self.b * dl / self._avgdl)
                sc += idf * numerator / max(denominator, 1e-6)
            scores.append((self._chunk_ids[idx], sc))

        scores.sort(key=lambda x: x[1], reverse=True)
        return scores[:top_k]


# ── Knowledge Base ────────────────────────────────────────────────────────────

class KnowledgeBase:
    """Document ingestion and retrieval knowledge base."""

    def __init__(self) -> None:
        _KNOWLEDGE_DIR.mkdir(parents=True, exist_ok=True)
        self._docs: Dict[str, KnowledgeDoc] = {}
        self._chunks: Dict[str, KnowledgeChunk] = {}
        self._bm25 = BM25()
        self._embedding_provider: Any = None
        self._embeddings: Dict[str, List[float]] = {}
        self._loaded = False

    def set_embedding_provider(self, provider: Any) -> None:
        self._embedding_provider = provider

    def _load(self) -> None:
        if self._loaded:
            return
        self._loaded = True
        try:
            if _INDEX_FILE.exists():
                data = json.loads(_INDEX_FILE.read_text(encoding="utf-8"))
                for d in data.get("docs", []):
                    doc = KnowledgeDoc.from_dict(d)
                    self._docs[doc.doc_id] = doc
                for c in data.get("chunks", []):
                    chunk = KnowledgeChunk.from_dict(c)
                    self._chunks[chunk.chunk_id] = chunk
                self._rebuild_bm25()
        except Exception as e:
            log.warning("KnowledgeBase load error: %s", e)

    def _save(self) -> None:
        try:
            data = {
                "docs": [d.to_dict() for d in self._docs.values()],
                "chunks": [c.to_dict() for c in self._chunks.values()],
            }
            _INDEX_FILE.write_text(json.dumps(data, indent=2))
        except Exception as e:
            log.warning("KnowledgeBase save error: %s", e)

    def _rebuild_bm25(self) -> None:
        self._bm25.index(list(self._chunks.values()))

    def ingest(self, file_path: str, doc_name: Optional[str] = None) -> dict:
        """Ingest a document into the knowledge base."""
        self._load()
        path = Path(file_path).expanduser().resolve()
        if not path.exists():
            return {"ok": False, "error": f"File not found: {file_path}"}

        raw = path.read_bytes()
        checksum = hashlib.sha256(raw).hexdigest()[:16]

        for doc in self._docs.values():
            if doc.checksum == checksum:
                return {
                    "ok": True,
                    "doc_id": doc.doc_id,
                    "doc_name": doc.name,
                    "chunks": doc.chunk_count,
                    "cached": True,
                    "message": f"Document '{doc.name}' already indexed.",
                }

        try:
            text, file_type = _extract_text(path)
        except Exception as e:
            return {"ok": False, "error": str(e)}

        name = doc_name or path.name
        doc_id = str(uuid.uuid4())[:8]
        chunks = _chunk_text(text, doc_id, name)

        doc = KnowledgeDoc(
            doc_id=doc_id,
            name=name,
            path=str(path),
            file_type=file_type,
            char_count=len(text),
            chunk_count=len(chunks),
            checksum=checksum,
        )

        self._docs[doc_id] = doc
        for chunk in chunks:
            self._chunks[chunk.chunk_id] = chunk

        self._rebuild_bm25()
        self._save()

        return {
            "ok": True,
            "doc_id": doc_id,
            "doc_name": name,
            "chunks": len(chunks),
            "file_type": file_type,
            "char_count": len(text),
            "cached": False,
            "message": f"Ingested '{name}' → {len(chunks)} chunks indexed.",
        }

    def query(self, query_text: str, top_k: int = _TOP_K,
              doc_filter: Optional[str] = None) -> dict:
        """Query the knowledge base and return top relevant chunks."""
        self._load()
        if not self._chunks:
            return {"ok": False, "results": [], "message": "Knowledge base is empty. Ingest documents first."}

        candidates = list(self._chunks.values())
        if doc_filter:
            candidates = [c for c in candidates if doc_filter.lower() in c.doc_name.lower()]

        bm25_scores = dict(self._bm25.score(query_text, top_k=top_k * 2))

        # Score and rank candidates
        scored = []
        for chunk in candidates:
            sc = bm25_scores.get(chunk.chunk_id, 0.0)
            if sc > 0:
                scored.append((chunk, sc))

        scored.sort(key=lambda x: x[1], reverse=True)
        top = scored[:top_k]

        results = []
        for chunk, score in top:
            results.append({
                "chunk_id": chunk.chunk_id,
                "doc_id": chunk.doc_id,
                "doc_name": chunk.doc_name,
                "text": chunk.text[:600],
                "page": chunk.page,
                "score": round(score, 3),
            })

        return {
            "ok": True,
            "query": query_text,
            "results": results,
            "total_chunks_searched": len(candidates),
            "message": f"Found {len(results)} relevant passages.",
        }

    def list_docs(self) -> List[dict]:
        self._load()
        return [d.to_dict() for d in sorted(self._docs.values(), key=lambda d: d.ingested_at, reverse=True)]

    def delete_doc(self, doc_id: str) -> bool:
        self._load()
        if doc_id not in self._docs:
            return False
        del self._docs[doc_id]
        to_remove = [cid for cid, c in self._chunks.items() if c.doc_id == doc_id]
        for cid in to_remove:
            del self._chunks[cid]
        self._rebuild_bm25()
        self._save()
        return True

    def get_stats(self) -> dict:
        self._load()
        return {
            "total_docs": len(self._docs),
            "total_chunks": len(self._chunks),
            "total_chars": sum(d.char_count for d in self._docs.values()),
            "file_types": list({d.file_type for d in self._docs.values()}),
        }


# ── Singleton ─────────────────────────────────────────────────────────────────

_kb: Optional[KnowledgeBase] = None


def get_knowledge_base() -> KnowledgeBase:
    global _kb
    if _kb is None:
        _kb = KnowledgeBase()
    return _kb
