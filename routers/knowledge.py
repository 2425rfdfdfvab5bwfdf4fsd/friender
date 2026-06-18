"""RAG Knowledge Base REST API."""
from __future__ import annotations

import tempfile
from pathlib import Path
from typing import Optional

from fastapi import APIRouter, File, HTTPException, UploadFile
from pydantic import BaseModel

from arix.memory.rag_ingester import get_knowledge_base

router = APIRouter(prefix="/api/knowledge", tags=["knowledge"])


class IngestRequest(BaseModel):
    file_path: str
    doc_name: Optional[str] = None


class QueryRequest(BaseModel):
    query: str
    top_k: int = 5
    doc_filter: Optional[str] = None


@router.get("")
async def list_docs():
    kb = get_knowledge_base()
    return {"docs": kb.list_docs(), "stats": kb.get_stats()}


@router.get("/stats")
async def get_stats():
    return get_knowledge_base().get_stats()


@router.post("/ingest")
async def ingest_document(req: IngestRequest):
    kb = get_knowledge_base()
    result = kb.ingest(req.file_path, req.doc_name)
    if not result.get("ok"):
        raise HTTPException(status_code=400, detail=result.get("error", "Ingest failed"))
    return result


@router.post("/query")
async def query_knowledge(req: QueryRequest):
    kb = get_knowledge_base()
    return kb.query(req.query, top_k=req.top_k, doc_filter=req.doc_filter)


@router.delete("/docs/{doc_id}")
async def delete_doc(doc_id: str):
    ok = get_knowledge_base().delete_doc(doc_id)
    if not ok:
        raise HTTPException(status_code=404, detail=f"Document {doc_id} not found")
    return {"ok": True, "doc_id": doc_id}


@router.post("/upload")
async def upload_document(file: UploadFile = File(...), doc_name: Optional[str] = None):
    """Accept a file upload (PDF/DOCX/TXT/MD/code) and ingest it into the knowledge base."""
    _ALLOWED_SUFFIXES = {
        ".pdf", ".docx", ".txt", ".md", ".markdown", ".rst", ".csv",
        ".py", ".js", ".ts", ".go", ".rs", ".java", ".cpp", ".c", ".h",
        ".json", ".yaml", ".yml", ".log",
    }
    fname = file.filename or "upload"
    suffix = Path(fname).suffix.lower()
    if suffix not in _ALLOWED_SUFFIXES:
        raise HTTPException(
            status_code=415,
            detail=f"Unsupported file type '{suffix}'. Allowed: {', '.join(sorted(_ALLOWED_SUFFIXES))}",
        )

    content = await file.read()
    if len(content) > 50 * 1024 * 1024:
        raise HTTPException(status_code=413, detail="File too large (max 50 MB)")

    with tempfile.NamedTemporaryFile(suffix=suffix, delete=False) as tmp:
        tmp.write(content)
        tmp_path = tmp.name

    try:
        kb = get_knowledge_base()
        result = kb.ingest(tmp_path, doc_name or fname)
    finally:
        try:
            Path(tmp_path).unlink(missing_ok=True)
        except Exception:
            pass

    if not result.get("ok"):
        raise HTTPException(status_code=400, detail=result.get("error", "Ingest failed"))
    return {**result, "filename": fname}
