"""历史对话分组（自定义分组）路由。

分组只影响历史列表的展示分组；删除分组不会删除分组内的会话，
分组内会话会被「释放」回日期区（今天/昨天/7日内/30日内/更早），
即恢复为按创建时间排序的原始顺序。
"""
from fastapi import APIRouter, Depends
from sqlalchemy.orm import Session

from db.database import get_db
from db.models import Session as SessionModel
from db.models import SessionGroup, utc_iso
from db.schemas import (
    ApiResponse,
    GroupAssignRequest,
    GroupBatchDeleteRequest,
    GroupCreateRequest,
    GroupUpdateRequest,
)

router = APIRouter(tags=["groups"])


def _group_dict(g: SessionGroup) -> dict:
    return {
        "id": g.id,
        "name": g.name,
        "created_at": utc_iso(g.created_at),
    }


@router.get("/api/groups", response_model=ApiResponse)
def list_groups(db: Session = Depends(get_db)):
    """全部分组（按创建时间升序）。"""
    rows = db.query(SessionGroup).order_by(SessionGroup.created_at.asc()).all()
    return ApiResponse.ok({"groups": [_group_dict(g) for g in rows]})


@router.post("/api/groups", response_model=ApiResponse)
def create_group(req: GroupCreateRequest, db: Session = Depends(get_db)):
    name = (req.name or "").strip()
    if not name:
        return ApiResponse.fail("分组名称不能为空", code=400)
    if len(name) > 64:
        name = name[:64]
    g = SessionGroup(name=name)
    db.add(g)
    db.commit()
    db.refresh(g)
    return ApiResponse.ok({"group": _group_dict(g)})


@router.patch("/api/groups/{group_id}", response_model=ApiResponse)
def rename_group(
    group_id: int, req: GroupUpdateRequest, db: Session = Depends(get_db)
):
    g = db.query(SessionGroup).filter(SessionGroup.id == group_id).first()
    if not g:
        return ApiResponse.fail("分组不存在", code=404)
    name = (req.name or "").strip()
    if not name:
        return ApiResponse.fail("分组名称不能为空", code=400)
    g.name = name[:64]
    db.commit()
    db.refresh(g)
    return ApiResponse.ok({"group": _group_dict(g)})


@router.delete("/api/groups/{group_id}", response_model=ApiResponse)
def delete_group(group_id: int, db: Session = Depends(get_db)):
    """删除单个分组：分组内会话 group_id 置空（回到日期区）。"""
    g = db.query(SessionGroup).filter(SessionGroup.id == group_id).first()
    if not g:
        return ApiResponse.fail("分组不存在", code=404)
    db.query(SessionModel).filter(SessionModel.group_id == group_id).update(
        {SessionModel.group_id: None}
    )
    db.delete(g)
    db.commit()
    return ApiResponse.ok({"deleted": group_id})


@router.post("/api/groups/batch-delete", response_model=ApiResponse)
def batch_delete_groups(
    req: GroupBatchDeleteRequest, db: Session = Depends(get_db)
):
    """批量删除分组：分组内会话全部释放回日期区（原始顺序）。"""
    ids = list(dict.fromkeys(req.group_ids))
    deleted: list[int] = []
    for gid in ids:
        g = db.query(SessionGroup).filter(SessionGroup.id == gid).first()
        if not g:
            continue
        db.query(SessionModel).filter(SessionModel.group_id == gid).update(
            {SessionModel.group_id: None}
        )
        db.delete(g)
        deleted.append(gid)
    db.commit()
    return ApiResponse.ok({"deleted": deleted, "count": len(deleted)})


@router.post("/api/sessions/assign-group", response_model=ApiResponse)
def assign_group(req: GroupAssignRequest, db: Session = Depends(get_db)):
    """批量把会话移入/移出分组：group_id 为 None 表示移出全部分组。"""
    ids = list(dict.fromkeys(req.session_ids))
    if not ids:
        return ApiResponse.fail("未选择任何会话", code=400)
    if req.group_id is not None:
        g = db.query(SessionGroup).filter(SessionGroup.id == req.group_id).first()
        if not g:
            return ApiResponse.fail("分组不存在", code=404)
    count = (
        db.query(SessionModel)
        .filter(SessionModel.session_id.in_(ids))
        .update({SessionModel.group_id: req.group_id}, synchronize_session=False)
    )
    db.commit()
    return ApiResponse.ok({"updated": count, "group_id": req.group_id})
