"""Agent 编排：意图路由 → 查询改写 → 工具调用 → 回答生成 → 会话落库。"""
import os
import uuid
from dataclasses import dataclass, field
from typing import List, Optional

from agent.query_rewriter import QueryRewriter
from multimodal.crop_classifier import classify_crop
from services.answer_engine import build_fallback_answer
from services.tracing import traceable

_DISEASE_KW = ["病", "斑", "烂", "枯", "虫", "黄叶", "枯萎", "霉", "斑点", "病害", "锈", "疫", "瘟"]
_PRICE_KW = ["价格", "行情", "多少钱", "市场", "报价", "收购"]
_CLIMATE_KW = ["气候", "温度", "降水", "积温", "适宜", "产区", "哪里", "地区", "播种", "什么时候种"]
_COMPARE_KW = ["对比", "比较", "哪个", "区别", "品种"]


@dataclass
class AgentResponse:
    reply: str
    sources: list = field(default_factory=list)
    vision: object = None
    session_id: str = ""


class CropAgent:
    def __init__(self, retriever, analyzer, llm, db_factory, knowledge_dir, settings):
        self.retriever = retriever
        self.analyzer = analyzer
        self.llm = llm
        self.db_factory = db_factory
        self.knowledge_dir = knowledge_dir
        self.settings = settings
        self.chunk_size = settings.chunk_size
        self.chunk_overlap = settings.chunk_overlap
        self.rewriter = QueryRewriter(llm, settings)

    # ---- 会话与消息 ----
    def _ensure_session(self, session_id: Optional[str], first_content: str = "") -> str:
        from db.models import Session

        db = self.db_factory()
        try:
            if session_id:
                exists = (
                    db.query(Session).filter(Session.session_id == session_id).first()
                )
                if exists:
                    # 首轮对话后，把默认标题"新对话"更新为第一轮提问的前几个字
                    if first_content and (not exists.title or exists.title == "新对话"):
                        exists.title = first_content[:20]
                        db.commit()
                    return session_id
            sid = uuid.uuid4().hex
            title = (first_content or "新对话")[:20]
            db.add(Session(session_id=sid, title=title))
            db.commit()
            return sid
        finally:
            db.close()

    def _save_message(
        self, session_id, role, content, image_urls=None, tool_calls=None, files=None
    ):
        from db.models import Message

        db = self.db_factory()
        try:
            db.add(
                Message(
                    session_id=session_id,
                    role=role,
                    content=content,
                    image_urls=image_urls or [],
                    tool_calls=tool_calls or [],
                    files=files or [],
                )
            )
            db.commit()
        finally:
            db.close()

    def _get_messages(self, session_id: str, n: int = 6) -> list:
        from db.models import Message

        db = self.db_factory()
        try:
            rows = (
                db.query(Message)
                .filter(Message.session_id == session_id)
                .order_by(Message.timestamp.desc())
                .limit(n)
                .all()
            )
            return [
                {"role": m.role, "content": m.content} for m in reversed(rows)
            ]
        finally:
            db.close()

    # ---- 意图与查询 ----
    @staticmethod
    def _parse_intent(content: str) -> str:
        if any(k in content for k in _DISEASE_KW):
            return "disease"
        if any(k in content for k in _PRICE_KW):
            return "price"
        if any(k in content for k in _CLIMATE_KW):
            return "climate"
        if any(k in content for k in _COMPARE_KW):
            return "compare"
        return "knowledge"

    @staticmethod
    def _build_query(content: str, vision) -> str:
        parts = [content]
        if vision and vision.description and not vision.simulated:
            parts.append(vision.description)
        for label in classify_crop(content):
            parts.append(label["label"])
        return " ".join(p for p in parts if p)

    # ---- 附件解析 ----
    @staticmethod
    def _parse_files(files) -> tuple:
        """普通文件附件 → (元信息列表, 提取文本列表)。解析失败不阻断对话。"""
        from services.file_parser import extract_file_text

        metas: list = []
        texts: list = []
        for f in files or []:
            name = (f.get("name") or "file")[:128]
            data = f.get("data") or b""
            texts.append(f"[附件文件：{name}]\n{extract_file_text(name, data)}")
            metas.append({"name": name, "mime": f.get("mime", ""), "size": len(data)})
        return metas, texts

    # ---- 主流程 ----
    @traceable("crop_agent.run", run_type="chain")
    async def run(
        self,
        content: str,
        images: Optional[List[bytes]] = None,
        image_urls: Optional[List[str]] = None,
        files: Optional[List[dict]] = None,
        session_id: Optional[str] = None,
    ) -> AgentResponse:
        content = (content or "").strip()
        session_id = self._ensure_session(session_id, content)

        file_metas, file_texts = self._parse_files(files)
        # 供 LLM/检索使用的完整内容：原文 + 附件文本（落库仍只存原文）
        llm_content = content
        if file_texts:
            llm_content = (content + "\n\n" + "\n\n".join(file_texts)).strip()

        self._save_message(
            session_id, "user", content, image_urls=image_urls or [], files=file_metas
        )

        history = self._get_messages(session_id, 6)
        intent = self._parse_intent(llm_content)

        tool_calls = []
        vision = None
        if images:
            task = "diagnose" if intent == "disease" else "identify"
            vision = await self.analyzer.analyze(images[0], task=task)
            tool_calls.append(f"image:{task}")

        # 文本部分（原文 + 作物标签）先做 LLM 改写，图片描述不参与改写（避免事实被改写）
        query = self._build_query(llm_content, None)
        if self.rewriter.enabled(query):
            query = await self.rewriter.rewrite(query)
        if vision and vision.description:
            query = (query + " " + vision.description).strip()
        hits = await self.retriever.search(query)
        tool_calls.append("search_knowledge_base")

        if self.llm.available:
            reply = await self._llm_reply(llm_content, hits, vision, history)
            if not reply:
                reply = build_fallback_answer(llm_content, hits, vision)
        else:
            reply = build_fallback_answer(llm_content, hits, vision)

        sources = [
            {"doc_id": h.doc_id, "chunk": h.source_label, "score": h.score}
            for h in hits
        ]
        self._save_message(session_id, "assistant", reply, tool_calls=tool_calls)
        return AgentResponse(
            reply=reply, sources=sources, vision=vision, session_id=session_id
        )

    async def _llm_reply(self, content, hits, vision, history) -> str:
        from agent.prompts import SYSTEM_PROMPT, build_context_prompt

        messages = [
            {"role": "system", "content": SYSTEM_PROMPT},
            {
                "role": "system",
                "content": "知识库检索上下文：\n" + build_context_prompt(hits),
            },
        ]
        for m in history[:-1]:  # 排除刚写入的当前 user 消息，避免重复
            messages.append({"role": m["role"], "content": m["content"]})
        user_content = content
        if vision and vision.description:
            user_content += "\n\n[图片识别] " + vision.description
        messages.append({"role": "user", "content": user_content})
        try:
            return await self.llm.generate(messages)
        except Exception:
            return ""

    # ---- 索引重建 ----
    def reindex(self) -> dict:
        from db.models import KnowledgeMeta
        from rag.indexer import build_index

        self.retriever.store.clear()
        ids, metas = build_index(
            self.knowledge_dir,
            self.retriever.store,
            self.retriever.embedder,
            self.chunk_size,
            self.chunk_overlap,
        )
        db = self.db_factory()
        try:
            db.query(KnowledgeMeta).delete()
            for m in metas:
                db.add(self._meta_row(m))
            db.commit()
        finally:
            db.close()
        return {"chunks": len(ids), "docs": len(metas)}

    @staticmethod
    def _meta_row(m: dict) -> "KnowledgeMeta":
        """meta dict → KnowledgeMeta ORM 行（含状态/时间/大小/分类）。"""
        from datetime import datetime, timezone

        from db.models import KnowledgeMeta

        updated_at = m.get("updated_at")
        if updated_at is None:
            updated_at = datetime.now(timezone.utc).replace(tzinfo=None)
        return KnowledgeMeta(
            doc_id=m["doc_id"],
            title=m["title"],
            source=m["source"],
            category=m.get("category", ""),
            chunk_count=m["chunk_count"],
            status="indexed",
            updated_at=updated_at,
            file_size=m.get("file_size", 0),
        )

    def index_file(self, path: str) -> dict:
        """上传后仅索引单个文件（upsert 语义）；返回 {doc_id, chunk_count}。"""
        from db.models import KnowledgeMeta
        from rag.indexer import build_doc_index

        _, meta = build_doc_index(
            path,
            self.retriever.store,
            self.retriever.embedder,
            self.chunk_size,
            self.chunk_overlap,
        )
        if meta is None:
            raise ValueError(f"文档为空或无法分块：{path}")
        db = self.db_factory()
        try:
            row = db.get(KnowledgeMeta, meta["doc_id"])
            if row:
                row.title = meta["title"]
                row.source = meta["source"]
                row.category = meta["category"]
                row.chunk_count = meta["chunk_count"]
                row.status = "indexed"
                row.updated_at = meta["updated_at"]
                row.file_size = meta["file_size"]
            else:
                db.add(self._meta_row(meta))
            db.commit()
        finally:
            db.close()
        return {"doc_id": meta["doc_id"], "chunk_count": meta["chunk_count"]}

    def reindex_doc(self, doc_id: str) -> dict:
        """单文档重建索引：清掉旧 chunk → 重新分块/嵌入 → 更新元信息。"""
        from db.models import KnowledgeMeta
        from rag.indexer import build_doc_index

        db = self.db_factory()
        try:
            row = db.get(KnowledgeMeta, doc_id)
            if row is None:
                raise KeyError(f"文档不存在：{doc_id}")
            source = row.source
            if not os.path.isfile(source):
                row.status = "failed"
                db.commit()
                raise FileNotFoundError(f"源文件缺失：{source}")
            row.status = "indexing"
            db.commit()
            try:
                self.retriever.store.delete_by_meta({"doc_id": doc_id})
                _, meta = build_doc_index(
                    source,
                    self.retriever.store,
                    self.retriever.embedder,
                    self.chunk_size,
                    self.chunk_overlap,
                )
                if meta is None:
                    raise ValueError("文档为空或无法分块")
                row.title = meta["title"]
                row.source = meta["source"]
                row.category = meta["category"]
                row.chunk_count = meta["chunk_count"]
                row.file_size = meta["file_size"]
                row.updated_at = meta["updated_at"]
                row.status = "indexed"
                db.commit()
            except Exception:
                row.status = "failed"
                db.commit()
                raise
            return {"doc_id": doc_id, "chunk_count": row.chunk_count}
        finally:
            db.close()

    def delete_doc(self, doc_id: str) -> bool:
        """删除文档：向量 chunk + 源文件 + 元信息行。"""
        from db.models import KnowledgeMeta

        db = self.db_factory()
        try:
            row = db.get(KnowledgeMeta, doc_id)
            if row is None:
                raise KeyError(f"文档不存在：{doc_id}")
            self.retriever.store.delete_by_meta({"doc_id": doc_id})
            db.query(KnowledgeMeta).filter(KnowledgeMeta.doc_id == doc_id).delete()
            db.commit()
            try:
                if row.source and os.path.isfile(row.source):
                    os.remove(row.source)
            except OSError:
                pass
            return True
        finally:
            db.close()

    def update_doc_category(self, doc_id: str, category: str) -> dict:
        """修改文档分类：同步向量 chunk 元数据（检索过滤源）与 DB 行，不重新嵌入。"""
        from db.models import KnowledgeMeta

        # 先同步向量元数据，保证检索测试的分类过滤即时生效
        self.retriever.store.update_meta({"doc_id": doc_id}, {"category": category})
        db = self.db_factory()
        try:
            row = db.get(KnowledgeMeta, doc_id)
            if row is None:
                raise KeyError(f"文档不存在：{doc_id}")
            row.category = category
            db.commit()
        finally:
            db.close()
        return {"doc_id": doc_id, "category": category}

    def get_doc_chunks(self, doc_id: str) -> list:
        """按 doc_id 读取该文档全部 chunk：[(chunk_id, text)]（按 chunk 序号排序）。"""
        rows = self.retriever.store.get_by_meta({"doc_id": doc_id})
        rows.sort(key=lambda r: _chunk_index(r[0]))
        return [(cid, text) for cid, text, _meta in rows]

    def delete_chunk(self, chunk_id: str, doc_id: str) -> bool:
        """删除单个 chunk（drawer 内管理）；最后一个 chunk 由路由层拒绝。"""
        removed = self.retriever.store.delete([chunk_id])
        if not removed:
            return False
        from db.models import KnowledgeMeta

        db = self.db_factory()
        try:
            row = db.get(KnowledgeMeta, doc_id)
            if row and row.chunk_count > 0:
                row.chunk_count -= 1
                db.commit()
        finally:
            db.close()
        return True


def _chunk_index(chunk_id: str) -> int:
    """从 chunk_id（如 K5BB418#chunk_01）解析序号；解析失败返回 0。"""
    tail = chunk_id.rsplit("#", 1)[-1]
    try:
        return int(tail.split("_")[-1])
    except (ValueError, IndexError):
        return 0
