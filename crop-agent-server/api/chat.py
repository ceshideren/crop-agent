"""对话与会话路由（/api/chat、/api/sessions）。"""
import uuid

from fastapi import APIRouter, Depends
from sqlalchemy import func
from sqlalchemy.orm import Session

from agent.registry import get_agent
from db.database import get_db
from db.models import Message, Session as SessionModel, SessionGroup, utc_iso
from db.schemas import (
    ApiResponse,
    BatchDeleteRequest,
    ChatRequest,
    MultimodalChatRequest,
    SessionCreateRequest,
    SessionUpdateRequest,
    Source,
)
from services.image_util import decode_data_url


def _decode_file(f) -> dict:
    """普通文件 → {name, mime, data(bytes)} 交给 agent 解析。"""
    return {
        "name": (f.name or "file")[:128],
        "mime": f.mime or "",
        "data": decode_data_url(f.data or ""),
    }

router = APIRouter(tags=["chat"])


def _to_sources(sources) -> list:
    return [
        Source(doc_id=s["doc_id"], chunk=s["chunk"], score=s["score"])
        for s in sources
    ]


def _vision_dict(v) -> dict:
    if v is None:
        return {}
    return {
        "task": v.task,
        "description": v.description,
        "labels": v.labels,
        "simulated": v.simulated,
    }


@router.post("/api/chat", response_model=ApiResponse)
async def chat(req: ChatRequest):
    agent = get_agent()
    res = await agent.run(req.content, session_id=req.session_id)
    return ApiResponse.ok(
        {
            "reply": res.reply,
            "session_id": res.session_id,
            "vision": _vision_dict(res.vision),
        },
        _to_sources(res.sources),
    )


@router.post("/api/chat/multimodal", response_model=ApiResponse)
async def chat_multimodal(req: MultimodalChatRequest):
    agent = get_agent()
    image_bytes = [decode_data_url(i) for i in req.images if i]
    files = [_decode_file(f) for f in (req.files or [])]
    res = await agent.run(
        req.content,
        images=image_bytes or None,
        image_urls=req.images,
        files=files or None,
        session_id=req.session_id,
    )
    return ApiResponse.ok(
        {
            "reply": res.reply,
            "session_id": res.session_id,
            "vision": _vision_dict(res.vision),
        },
        _to_sources(res.sources),
    )


@router.get("/api/chat/history", response_model=ApiResponse)
def chat_history(session_id: str, db: Session = Depends(get_db)):
    rows = (
        db.query(Message)
        .filter(Message.session_id == session_id)
        .order_by(Message.timestamp.asc())
        .all()
    )
    messages = [
        {
            "id": m.id,
            "role": m.role,
            "content": m.content,
            "image_urls": m.image_urls or [],
            "tool_calls": m.tool_calls or [],
            "timestamp": utc_iso(m.timestamp),
        }
        for m in rows
    ]
    return ApiResponse.ok({"messages": messages})


@router.get("/api/sessions", response_model=ApiResponse)
def list_sessions(db: Session = Depends(get_db)):
    """会话列表：置顶优先，其次按创建时间倒序；附带分组列表。

    message_count：每条会话的消息条数（前端用它识别「空对话」，
    新建对话时会优先复用已有的空对话，避免产生多余的空白会话）。
    """
    rows = (
        db.query(SessionModel)
        .order_by(SessionModel.pinned.desc(), SessionModel.created_at.desc())
        .all()
    )
    msg_counts = dict(
        db.query(Message.session_id, func.count(Message.id))
        .group_by(Message.session_id)
        .all()
    )
    sessions = [
        {
            "session_id": s.session_id,
            "title": s.title,
            "crop_context": s.crop_context,
            "pinned": bool(s.pinned),
            "group_id": s.group_id,
            "message_count": msg_counts.get(s.session_id, 0),
            "created_at": utc_iso(s.created_at),
        }
        for s in rows
    ]
    group_rows = db.query(SessionGroup).order_by(SessionGroup.created_at.asc()).all()
    groups = [
        {
            "id": g.id,
            "name": g.name,
            "created_at": utc_iso(g.created_at),
        }
        for g in group_rows
    ]
    return ApiResponse.ok({"sessions": sessions, "groups": groups})


@router.post("/api/sessions", response_model=ApiResponse)
def create_session(
    req: SessionCreateRequest | None = None, db: Session = Depends(get_db)
):
    """创建会话；带 group_id 时归属该分组，并校验分组内无「未使用的空对话」。"""
    payload = req or SessionCreateRequest()
    gid = payload.group_id
    sid = uuid.uuid4().hex

    if gid is not None:
        g = db.query(SessionGroup).filter(SessionGroup.id == gid).first()
        if not g:
            return ApiResponse.fail("分组不存在", code=404)
        # 服务端兜底：分组内存在 0 消息会话 → 拒绝创建（与前端同文案）
        group_sids = [
            s.session_id
            for s in db.query(SessionModel).filter(SessionModel.group_id == gid).all()
        ]
        if group_sids:
            counts = dict(
                db.query(Message.session_id, func.count(Message.id))
                .filter(Message.session_id.in_(group_sids))
                .group_by(Message.session_id)
                .all()
            )
            if any(counts.get(sid2, 0) == 0 for sid2 in group_sids):
                return ApiResponse.fail(
                    "已存在未使用的空对话，请先使用或清理后再新建", code=400
                )

    db.add(SessionModel(session_id=sid, title="新对话", group_id=gid))
    db.commit()
    return ApiResponse.ok({"session_id": sid})


@router.patch("/api/sessions/{session_id}", response_model=ApiResponse)
def update_session(
    session_id: str, req: SessionUpdateRequest, db: Session = Depends(get_db)
):
    """更新会话：重命名标题 / 切换置顶状态。"""
    row = (
        db.query(SessionModel)
        .filter(SessionModel.session_id == session_id)
        .first()
    )
    if not row:
        return ApiResponse.fail("会话不存在", code=404)
    if req.title is not None:
        title = req.title.strip()
        if not title:
            return ApiResponse.fail("对话名称不能为空", code=400)
        row.title = title[:128]
    if req.pinned is not None:
        row.pinned = bool(req.pinned)
    db.commit()
    return ApiResponse.ok(
        {
            "session_id": row.session_id,
            "title": row.title,
            "crop_context": row.crop_context,
            "pinned": bool(row.pinned),
            "group_id": row.group_id,
            "created_at": utc_iso(row.created_at),
        }
    )


@router.post("/api/sessions/batch-delete", response_model=ApiResponse)
def batch_delete_sessions(req: BatchDeleteRequest, db: Session = Depends(get_db)):
    """批量删除会话（级联清理 messages 表）。"""
    ids = list(dict.fromkeys(req.session_ids))  # 去重保序
    deleted: list[str] = []
    for sid in ids:
        row = (
            db.query(SessionModel)
            .filter(SessionModel.session_id == sid)
            .first()
        )
        if row:
            db.query(Message).filter(Message.session_id == sid).delete()
            db.delete(row)
            deleted.append(sid)
    db.commit()
    return ApiResponse.ok({"deleted": deleted, "count": len(deleted)})


@router.delete("/api/sessions/{session_id}", response_model=ApiResponse)
def delete_session(session_id: str, db: Session = Depends(get_db)):
    """删除会话及其全部消息（级联清理 messages 表）。"""
    db.query(Message).filter(Message.session_id == session_id).delete()
    row = (
        db.query(SessionModel)
        .filter(SessionModel.session_id == session_id)
        .first()
    )
    if row:
        db.delete(row)
    db.commit()
    return ApiResponse.ok({"deleted": session_id})
