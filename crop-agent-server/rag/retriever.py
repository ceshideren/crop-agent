"""检索逻辑：query → 向量召回（recall_k）→ 阈值过滤 → 混合加权排序 → 文档级聚合。"""
import re
from dataclasses import dataclass, field
from typing import List, Optional

from services.tracing import traceable

_TOKEN = re.compile(r"[\u4e00-\u9fff]+|[a-z0-9]+")


@dataclass
class RetrievalHit:
    doc_id: str
    chunk_id: str
    title: str
    category: str
    source: str
    text: str
    score: float

    @property
    def source_label(self) -> str:
        return f"{self.doc_id}#{self.chunk_id.split('#')[-1]}"


@dataclass
class RetrievalChunk:
    chunk_id: str
    chunk_index: int
    text: str
    score: float


@dataclass
class RetrievalDoc:
    """文档级命中：score 为该文档所有命中 chunk 的最高分，chunks 按分数降序。"""

    doc_id: str
    title: str
    category: str
    source: str
    score: float
    chunks: List[RetrievalChunk] = field(default_factory=list)


def _query_tokens(query: str) -> List[str]:
    """查询词切分为 token 列表（中文连续片段 + 英文单词）。"""
    return [t for t in _TOKEN.findall((query or "").lower()) if t]


def _title_overlap(title: str, tokens: List[str]) -> float:
    """查询 token 在标题中的命中比例（0~1），用于混合检索加权。"""
    if not tokens:
        return 0.0
    t = (title or "").lower()
    hit = sum(1 for tok in tokens if tok in t)
    return hit / len(tokens)


class Retriever:
    """封装向量库与嵌入器，暴露统一的 search 接口（对应 search_knowledge_base 工具）。

    阈值说明：本地哈希嵌入的相似度量级（约 0.15–0.45）低于语义嵌入，
    因此本地模式采用嵌入器声明的推荐阈值（recommended_threshold），
    语义嵌入模式使用配置的 similarity_threshold —— 有效阈值通过
    effective_threshold 属性对外暴露，供前端诚实展示。
    """

    def __init__(
        self,
        store,
        embedder,
        top_k: int = 5,
        threshold: float = 0.65,
        recall_k: int = 20,
        hybrid_search: bool = True,
    ):
        self.store = store
        self.embedder = embedder
        self.top_k = top_k
        self.threshold = threshold
        self.recall_k = recall_k
        self.hybrid_search = hybrid_search
        self.effective_threshold = getattr(
            embedder, "recommended_threshold", self.threshold
        )
        self._last_query = ""

    @property
    def embedder_name(self) -> str:
        return getattr(self.embedder, "__class__", type(self.embedder)).__name__

    def _hybrid_score(self, raw: float, title: str, category: str) -> float:
        """混合加权：标题/分类与查询 token 重叠时小幅加分，排序用；展示分仍为 raw。

        轻量确定性的关键词加成（需求 5.4 的简化落地）：完整 BM25+RRF 列为后续工作。
        """
        if not self.hybrid_search:
            return raw
        tokens = _query_tokens(self._last_query)
        title_hit = _title_overlap(title, tokens)
        cat_hit = _title_overlap(category, tokens)
        boost = 0.08 * min(1.0, title_hit + 0.5 * cat_hit)
        return raw + boost

    def _recall(self, query: str, top_k: Optional[int]) -> List[RetrievalHit]:
        """召回 → 有效阈值过滤 → 混合加权排序 → RetrievalHit 列表（分数为 raw）。"""
        self._last_query = query
        emb = self.embedder.embed_query(query)
        rows = self.store.query(emb, self.recall_k)
        hits: List[RetrievalHit] = []
        for cid, score, doc, meta in rows:
            raw = round(float(score), 4)
            if raw < self.effective_threshold:
                continue
            hits.append(
                RetrievalHit(
                    doc_id=meta.get("doc_id", cid.split("#")[0]),
                    chunk_id=cid,
                    title=meta.get("title", ""),
                    category=meta.get("category", ""),
                    source=meta.get("source", ""),
                    text=doc,
                    score=raw,
                )
            )
        # 混合加权排序：final 分数参与排名，但 hit.score 保留原始相似度
        hits.sort(
            key=lambda h: self._hybrid_score(h.score, h.title, h.category),
            reverse=True,
        )
        return hits[:top_k] if top_k else hits

    @traceable("search_knowledge_base", run_type="retriever")
    def search(self, query: str, top_k: int = None) -> List[RetrievalHit]:
        query = (query or "").strip()
        if not query:
            return []
        return self._recall(query, top_k or self.top_k)

    def search_docs(
        self,
        query: str,
        top_k: int = None,
        category: Optional[str] = None,
    ) -> List[RetrievalDoc]:
        """文档级检索：召回 → 阈值过滤 → 分类过滤 → 按 doc_id 合并去重。

        返回文档级列表：score 取该文档命中 chunk 的最高分，
        chunks 为该文档下所有命中片段（按分数降序）。
        """
        query = (query or "").strip()
        if not query:
            return []
        hits = self._recall(query, None)
        if category:
            hits = [h for h in hits if h.category == category]

        docs: dict = {}
        for h in hits:
            d = docs.get(h.doc_id)
            if d is None:
                d = RetrievalDoc(
                    doc_id=h.doc_id,
                    title=h.title,
                    category=h.category,
                    source=h.source,
                    score=h.score,
                    chunks=[],
                )
                docs[h.doc_id] = d
            d.chunks.append(
                RetrievalChunk(
                    chunk_id=h.chunk_id,
                    chunk_index=_chunk_index_of(h.chunk_id),
                    text=h.text,
                    score=h.score,
                )
            )
            if h.score > d.score:
                d.score = h.score

        result = list(docs.values())
        result.sort(key=lambda d: d.score, reverse=True)
        # 文档级 top_k 裁剪（chunks 保持完整）
        if top_k:
            result = result[:top_k]
        return result


def _chunk_index_of(chunk_id: str) -> int:
    """从 chunk_id（如 K5BB418#chunk_01）解析序号；解析失败返回 0。"""
    tail = chunk_id.rsplit("#", 1)[-1]
    try:
        return int(tail.split("_")[-1])
    except (ValueError, IndexError):
        return 0
