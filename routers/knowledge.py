"""RAG Knowledge Base REST API."""
from __future__ import annotations

from fastapi import APIRouter, HTTPException
from pydantic import BaseModel
from typing import Optional

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
