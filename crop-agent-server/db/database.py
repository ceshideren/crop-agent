"""数据库引擎与会话（SQLAlchemy 2.x）。SQLite → 后期仅改连接串即可迁移 PG/MySQL。"""
import os

from sqlalchemy import create_engine
from sqlalchemy.orm import declarative_base, sessionmaker
from sqlalchemy.pool import StaticPool

from config import get_settings

settings = get_settings()

_is_memory_sqlite = settings.db_url in ("sqlite://", "sqlite:///:memory:", ":memory:")

if settings.db_url.startswith("sqlite"):
    connect_args = {"check_same_thread": False}
    kwargs = {"connect_args": connect_args, "future": True}
    if _is_memory_sqlite:
        # 内存库：所有会话共享同一连接，保证建表后可见（用于测试）
        kwargs["poolclass"] = StaticPool
    engine = create_engine(settings.db_url, **kwargs)
else:
    engine = create_engine(settings.db_url, future=True)

SessionLocal = sessionmaker(bind=engine, autoflush=False, autocommit=False, future=True)
Base = declarative_base()


def init_db() -> None:
    """建表。模型需先被导入注册。"""
    from db import models  # noqa: F401

    Base.metadata.create_all(bind=engine)
    _migrate_sessions_pinned()
    _migrate_sessions_group()
    _migrate_messages_files()
    _migrate_knowledge_meta()


def _table_columns(table: str) -> list:
    from sqlalchemy import text

    if not settings.db_url.startswith("sqlite"):
        return []
    with engine.begin() as conn:
        rows = conn.execute(text(f"PRAGMA table_info({table})")).fetchall()
        return [r[1] for r in rows]


def _migrate_sessions_pinned() -> None:
    """轻量迁移：为旧库的 sessions 表补 pinned 列（幂等，SQLite）。"""
    from sqlalchemy import text

    if not settings.db_url.startswith("sqlite"):
        return
    if "pinned" not in _table_columns("sessions"):
        with engine.begin() as conn:
            conn.execute(text("ALTER TABLE sessions ADD COLUMN pinned BOOLEAN DEFAULT 0"))


def _migrate_sessions_group() -> None:
    """轻量迁移：为旧库的 sessions 表补 group_id 列（自定义分区外键）。"""
    from sqlalchemy import text

    if not settings.db_url.startswith("sqlite"):
        return
    if "group_id" not in _table_columns("sessions"):
        with engine.begin() as conn:
            conn.execute(text("ALTER TABLE sessions ADD COLUMN group_id INTEGER"))


def _migrate_messages_files() -> None:
    """轻量迁移：为旧库的 messages 表补 files 列（附件元信息）。"""
    from sqlalchemy import text

    if not settings.db_url.startswith("sqlite"):
        return
    if "files" not in _table_columns("messages"):
        with engine.begin() as conn:
            conn.execute(text("ALTER TABLE messages ADD COLUMN files JSON"))


def _migrate_knowledge_meta() -> None:
    """轻量迁移：为旧库的 knowledge_meta 表补状态/时间/大小/分类列，并尽力回填。"""
    from sqlalchemy import text

    if not settings.db_url.startswith("sqlite"):
        return
    cols = _table_columns("knowledge_meta")
    with engine.begin() as conn:
        if "status" not in cols:
            conn.execute(
                text(
                    "ALTER TABLE knowledge_meta "
                    "ADD COLUMN status VARCHAR(16) DEFAULT 'indexed'"
                )
            )
        if "updated_at" not in cols:
            conn.execute(text("ALTER TABLE knowledge_meta ADD COLUMN updated_at DATETIME"))
        if "file_size" not in cols:
            conn.execute(
                text("ALTER TABLE knowledge_meta ADD COLUMN file_size INTEGER DEFAULT 0")
            )
        if "category" not in cols:
            conn.execute(
                text("ALTER TABLE knowledge_meta ADD COLUMN category VARCHAR(64) DEFAULT ''")
            )
        # 回填：category 从 source 目录名推导；updated_at 取 created_at；file_size 尽力读取
        rows = conn.execute(
            text("SELECT doc_id, source, created_at FROM knowledge_meta")
        ).fetchall()
        for doc_id, source, created_at in rows:
            updates = []
            if not source:
                continue
            category = str(source).replace("\\", "/").rstrip("/").split("/")[-2] or ""
            if category:
                updates.append(f"category = '{category}'")
            updates.append("updated_at = COALESCE(updated_at, created_at)")
            try:
                if os.path.isfile(source):
                    updates.append(f"file_size = {os.path.getsize(source)}")
            except OSError:
                pass
            if updates:
                conn.execute(
                    text(
                        f"UPDATE knowledge_meta SET {', '.join(updates)} "
                        "WHERE doc_id = :doc_id"
                    ),
                    {"doc_id": doc_id},
                )


def get_db():
    """FastAPI 依赖：请求级会话。"""
    db = SessionLocal()
    try:
        yield db
    finally:
        db.close()
