"""知识库路由（/api/knowledge）：检索、元信息列表、上传、预览、删除、重建索引。"""
import os

from fastapi import APIRouter, Depends, File, UploadFile
from pydantic import BaseModel
from sqlalchemy.orm import Session

from agent.registry import get_agent
from db.database import get_db
from db.models import KnowledgeMeta, utc_iso
from db.schemas import ApiResponse

router = APIRouter(prefix="/api/knowledge", tags=["knowledge"])


class BatchRequest(BaseModel):
    doc_ids: list[str]


def _doc_payload(row: KnowledgeMeta) -> dict:
    """DB 行 → 前端文档对象（时间统一 utc_iso 带 Z）。"""
    return {
        "doc_id": row.doc_id,
        "title": row.title,
        "source": row.source,
        "file_name": os.path.basename(row.source) if row.source else "",
        "category": row.category or "",
        "status": row.status or "indexed",
        "chunk_count": row.chunk_count or 0,
        "file_size": row.file_size or 0,
        "created_at": utc_iso(row.created_at),
        "updated_at": utc_iso(row.updated_at),
    }


def _enrich_docs(docs, db: Session) -> list:
    """按 doc_id 批量补齐 DB 元信息（status/updated_at/file_size/chunk_count）。"""
    ids = [d.doc_id for d in docs]
    rows = (
        db.query(KnowledgeMeta).filter(KnowledgeMeta.doc_id.in_(ids)).all()
        if ids
        else []
    )
    meta_map = {r.doc_id: r for r in rows}
    out = []
    for d in docs:
        row = meta_map.get(d.doc_id)
        payload = {
            "doc_id": d.doc_id,
            "title": d.title,
            "category": d.category,
            "source": d.source,
            "file_name": os.path.basename(d.source) if d.source else "",
            "score": d.score,
            "chunks": [
                {
                    "chunk_id": c.chunk_id,
                    "chunk_index": c.chunk_index,
                    "text": c.text,
                    "score": c.score,
                }
                for c in d.chunks
            ],
            # 默认值：向量库有而 DB 无（陈旧数据）时给兜底
            "status": row.status if row else "indexed",
            "updated_at": utc_iso(row.updated_at) if row else None,
            "file_size": row.file_size if row else 0,
            "chunk_count": row.chunk_count if row else len(d.chunks),
        }
        out.append(payload)
    return out


@router.get("/search", response_model=ApiResponse)
def search_knowledge(
    q: str, category: str = "", db: Session = Depends(get_db)
):
    agent = get_agent()
    docs = agent.retriever.search_docs(q, category=category or None)
    results = _enrich_docs(docs, db)
    total_chunks = sum(len(d["chunks"]) for d in results)
    high = sum(1 for d in results if d["score"] >= 0.8)
    return ApiResponse.ok(
        {
            "results": results,
            "meta": {
                "threshold": agent.retriever.effective_threshold,
                "embedder": agent.retriever.embedder_name,
                "doc_count": len(results),
                "total_chunks": total_chunks,
                "high": high,
            },
        }
    )


@router.get("", response_model=ApiResponse)
def list_knowledge(db: Session = Depends(get_db)):
    agent = get_agent()
    rows = db.query(KnowledgeMeta).order_by(KnowledgeMeta.created_at.desc()).all()
    docs = [_doc_payload(r) for r in rows]
    return ApiResponse.ok(
        {
            "docs": docs,
            "meta": {
                "threshold": agent.retriever.effective_threshold,
                "embedder": agent.retriever.embedder_name,
            },
        }
    )


@router.post("/upload", response_model=ApiResponse)
async def upload_knowledge(file: UploadFile = File(...)):
    agent = get_agent()
    if not file.filename.lower().endswith((".md", ".txt")):
        return ApiResponse.fail("仅支持 .md / .txt 文档", code=400)
    safe_name = os.path.basename(file.filename)
    dest = os.path.join(agent.knowledge_dir, safe_name)
    os.makedirs(agent.knowledge_dir, exist_ok=True)
    content = await file.read()
    with open(dest, "wb") as f:
        f.write(content)
    try:
        stats = agent.index_file(dest)
    except Exception as exc:
        return ApiResponse.fail(f"索引失败：{exc}", code=500)
    return ApiResponse.ok(
        {
            "filename": safe_name,
            "doc_id": stats["doc_id"],
            "chunks": stats["chunk_count"],
        }
    )


@router.get("/{doc_id}/chunks", response_model=ApiResponse)
def list_doc_chunks(doc_id: str, db: Session = Depends(get_db)):
    agent = get_agent()
    row = db.get(KnowledgeMeta, doc_id)
    if row is None:
        return ApiResponse.fail(f"文档不存在：{doc_id}", code=404)
    chunks = agent.get_doc_chunks(doc_id)
    return ApiResponse.ok(
        {
            "doc_id": doc_id,
            "chunk_count": len(chunks),
            "chunks": [
                {
                    "chunk_id": cid,
                    "chunk_index": i,
                    "text": text,
                    "char_count": len(text),
                }
                for i, (cid, text) in enumerate(chunks)
            ],
        }
    )


@router.get("/{doc_id}/content", response_model=ApiResponse)
def get_doc_content(doc_id: str, db: Session = Depends(get_db)):
    agent = get_agent()
    row = db.get(KnowledgeMeta, doc_id)
    if row is None:
        return ApiResponse.fail(f"文档不存在：{doc_id}", code=404)
    if not row.source or not os.path.isfile(row.source):
        return ApiResponse.fail("源文件缺失，无法预览", code=404)
    try:
        with open(row.source, "r", encoding="utf-8") as f:
            content = f.read()
    except OSError as exc:
        return ApiResponse.fail(f"读取源文件失败：{exc}", code=500)
    return ApiResponse.ok(
        {"doc_id": doc_id, "title": row.title, "source": row.source, "content": content}
    )


@router.delete("/{doc_id}", response_model=ApiResponse)
def delete_knowledge(doc_id: str):
    agent = get_agent()
    try:
        agent.delete_doc(doc_id)
    except KeyError as exc:
        return ApiResponse.fail(str(exc), code=404)
    return ApiResponse.ok({"deleted": doc_id})


@router.post("/{doc_id}/reindex", response_model=ApiResponse)
def reindex_knowledge(doc_id: str):
    agent = get_agent()
    try:
        stats = agent.reindex_doc(doc_id)
    except KeyError as exc:
        return ApiResponse.fail(str(exc), code=404)
    except (FileNotFoundError, ValueError) as exc:
        return ApiResponse.fail(str(exc), code=400)
    return ApiResponse.ok({"doc_id": doc_id, "chunk_count": stats["chunk_count"]})


@router.post("/batch-delete", response_model=ApiResponse)
def batch_delete_knowledge(req: BatchRequest):
    agent = get_agent()
    count = 0
    failed = []
    for doc_id in req.doc_ids:
        try:
            agent.delete_doc(doc_id)
            count += 1
        except KeyError:
            failed.append(doc_id)
    return ApiResponse.ok({"count": count, "failed": failed})


@router.post("/batch-reindex", response_model=ApiResponse)
def batch_reindex_knowledge(req: BatchRequest):
    agent = get_agent()
    count = 0
    failed = []
    for doc_id in req.doc_ids:
        try:
            agent.reindex_doc(doc_id)
            count += 1
        except (KeyError, FileNotFoundError, ValueError):
            failed.append(doc_id)
    return ApiResponse.ok({"count": count, "failed": failed})


@router.delete("/chunks/{chunk_id}", response_model=ApiResponse)
def delete_chunk(chunk_id: str, db: Session = Depends(get_db)):
    """drawer 内删除单个 chunk；最后一个 chunk 拒绝删除。"""
    doc_id = chunk_id.split("#", 1)[0]
    agent = get_agent()
    row = db.get(KnowledgeMeta, doc_id)
    if row is None:
        return ApiResponse.fail(f"文档不存在：{doc_id}", code=404)
    if (row.chunk_count or 0) <= 1:
        return ApiResponse.fail("至少保留一个片段，如需删除请删除整个文档", code=400)
    if not agent.delete_chunk(chunk_id, doc_id):
        return ApiResponse.fail(f"片段不存在：{chunk_id}", code=404)
    db.refresh(row)
    return ApiResponse.ok({"deleted": chunk_id, "chunk_count": row.chunk_count})
