"""SQLAlchemy ORM 模型（与全局提示词第七节表结构一致）。"""
from datetime import datetime, timezone

from sqlalchemy import Boolean, Column, DateTime, ForeignKey, Integer, JSON, String, Text

from db.database import Base


def _now() -> datetime:
    """数据库默认时间：统一存 naive UTC（避免本地时区污染）。

    注意：datetime.utcnow() 已弃用，且语义含糊（返回 naive UTC），
    这里显式取 UTC 再剥离 tzinfo，保证所有写入列都是「naive UTC」。
    """
    return datetime.now(timezone.utc).replace(tzinfo=None)


def utc_iso(dt: datetime | None) -> str | None:
    """把 DB 中的 naive UTC 时间序列化为带 Z 后缀的 ISO 串。

    这是前后端时间契约的唯一出口：不带头尾时区标记的字符串会被浏览器
    new Date() 当作「本地时间」解析，导致跨时区时日期桶错位（如今天→昨天）。
    统一补上 "Z" 后，客户端按 UTC 瞬间解析，再换算本地自然日，结果才准确。
    """
    if dt is None:
        return None
    if dt.tzinfo is None:
        return dt.isoformat() + "Z"
    return dt.astimezone(timezone.utc).isoformat()


class User(Base):
    __tablename__ = "users"

    id = Column(Integer, primary_key=True, autoincrement=True)
    name = Column(String(64), nullable=False, default="匿名用户")
    created_at = Column(DateTime, default=_now)


class SessionGroup(Base):
    """自定义历史对话分区（分组）。"""

    __tablename__ = "groups"

    id = Column(Integer, primary_key=True, autoincrement=True)
    name = Column(String(64), nullable=False)
    created_at = Column(DateTime, default=_now)


class Session(Base):
    __tablename__ = "sessions"

    session_id = Column(String(64), primary_key=True)
    user_id = Column(Integer, ForeignKey("users.id"), nullable=True)
    title = Column(String(128), default="新对话")
    crop_context = Column(String(256), nullable=True)
    pinned = Column(Boolean, default=False)  # 置顶（历史列表排序权重最高）
    group_id = Column(Integer, ForeignKey("groups.id"), nullable=True)  # 所属自定义分区
    created_at = Column(DateTime, default=_now)


class Message(Base):
    __tablename__ = "messages"

    id = Column(Integer, primary_key=True, autoincrement=True)
    session_id = Column(String(64), ForeignKey("sessions.session_id"), index=True)
    role = Column(String(16), nullable=False)  # user | assistant
    content = Column(Text, nullable=False)
    image_urls = Column(JSON, default=list)
    files = Column(JSON, default=list)  # [{name, mime, size}]
    tool_calls = Column(JSON, default=list)
    timestamp = Column(DateTime, default=_now, index=True)


class Favorite(Base):
    __tablename__ = "favorites"

    id = Column(Integer, primary_key=True, autoincrement=True)
    user_id = Column(Integer, ForeignKey("users.id"), nullable=True)
    doc_id = Column(String(64), index=True)
    created_at = Column(DateTime, default=_now)


class KnowledgeMeta(Base):
    __tablename__ = "knowledge_meta"

    doc_id = Column(String(64), primary_key=True)
    title = Column(String(256), nullable=False)
    source = Column(String(512), nullable=False)
    chunk_count = Column(Integer, default=0)
    # 知识库界面优化：状态 / 更新时间 / 文件大小 / 分类
    status = Column(String(16), default="indexed")  # indexed | indexing | failed
    updated_at = Column(DateTime, default=_now)
    file_size = Column(Integer, default=0)
    category = Column(String(64), default="")
    created_at = Column(DateTime, default=_now)
