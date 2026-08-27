"""检索逻辑：query → 向量召回 + BM25 词法召回 → 分源阈值过滤 → RRF 融合排序
→ （可选）重排 → 文档级聚合。

- 向量源：相似度 ≥ effective_threshold（过滤规则与旧版一致，既有命中不丢）；
- 词法源：BM25 归一化分 ≥ lexical_min（精确词条命中，短查询受益）；
- 展示分 S = w_v·raw + w_b·bm25_norm，缺失源记 0（无证据即无贡献）。
  两源都是与查询长度无关的绝对量纲，同一分数在不同查询间可比：逐字命中双源皆高，
  零星共字双源皆低。这是排序主键，也是 relevance_of() 分级的依据。
- RRF（rrf = Σ 1/(k + rank)，k 默认 60）降为同分时的 tie-breaker；
  文档级顺序继承其最优 chunk 的顺序，与 chunk 级口径一致。

注意：展示分刻意保持绝对量纲，不做候选集内相对归一化 —— 后者会把任意查询的
Top1 拉满到 1.0，使 build_context 喂给 LLM 的「相关度」失真，让模型对知识库里
根本没有的作物也自信作答，破坏 SYSTEM_PROMPT 的「未命中时诚实说明」约定。
"""
from dataclasses import dataclass, field
from typing import List, Optional

from rag.bm25 import BM25Index, tokenize
from services.tracing import traceable


def relevance_of(score: float) -> str:
    """\u5c55\u793a\u5206 \u2192 \u76f8\u5173\u6027\u7b49\u7ea7\u3002\u540e\u7aef\u662f\u5206\u7ea7\u7684\u552f\u4e00\u771f\u76f8\u6e90\uff0c\u524d\u7aef\u4e0d\u518d\u81ea\u884c\u5207\u9608\u503c\u3002

    \u9608\u503c\u6309\u672c\u5730\u54c8\u5e0c\u5d4c\u5165\u7684\u5c55\u793a\u5206\u91cf\u7eb2\u6821\u51c6\uff08\u89c1 config.relevance_*\uff09\uff1b
    \u6362\u7528\u8bed\u4e49\u5d4c\u5165\u540e\u91cf\u7eb2\u53d8\u5316\uff0c\u9700\u91cd\u65b0\u6821\u51c6\u3002
    """
    from config import get_settings

    s = get_settings()
    if score >= s.relevance_high:
        return "high"
    if score >= s.relevance_mid:
        return "mid"
    if score >= s.relevance_low:
        return "low"
    return "none"


@dataclass
class RetrievalHit:
    doc_id: str
    chunk_id: str
    title: str
    category: str
    source: str
    text: str
    score: float
    tags: List[str] = field(default_factory=list)

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
    """文档级命中：score 为该文档所有命中 chunk 的最高分，chunks 按分数降序。

    relevance 由 score 经 relevance_of() 派生，供前端直接分组展示。
    """

    doc_id: str
    title: str
    category: str
    source: str
    score: float
    relevance: str = ""
    chunks: List[RetrievalChunk] = field(default_factory=list)


class Retriever:
    """封装向量库与嵌入器，暴露统一的 search / search_docs 接口。

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
        hybrid_k: int = 60,
        bm25_weight: float = 0.5,
        vector_weight: float = 0.5,
        lexical_min: float = 0.2,
        rerank_k: int = 20,
        reranker=None,
    ):
        self.store = store
        self.embedder = embedder
        self.top_k = top_k
        self.threshold = threshold
        self.recall_k = recall_k
        self.hybrid_search = hybrid_search
        self.hybrid_k = hybrid_k
        self.bm25_weight = bm25_weight
        self.vector_weight = vector_weight
        self.lexical_min = lexical_min
        self.rerank_k = rerank_k
        self.reranker = reranker
        self.effective_threshold = getattr(
            embedder, "recommended_threshold", self.threshold
        )

    @property
    def embedder_name(self) -> str:
        return getattr(self.embedder, "__class__", type(self.embedder)).__name__

    def _recall(self, query: str, top_k: Optional[int]) -> List[RetrievalHit]:
        """召回 → 分源阈值过滤 → 加权融合排序 → RetrievalHit 列表（score 为展示分）。"""
        emb = self.embedder.embed_query(query)
        vec_rows = self.store.query(emb, self.recall_k)

        lex_rows = []
        if self.hybrid_search and hasattr(self.store, "lexical_search"):
            lex_rows = self.store.lexical_search(query, self.recall_k)

        # 分源过滤（保持各自原有过滤语义）
        vec: dict = {}
        for cid, score, doc, meta in vec_rows:
            raw = round(float(score), 4)
            if raw < self.effective_threshold:
                continue
            vec[cid] = (raw, doc, meta)

        # 按查询唯一 token 数摊平 BM25，消除长查询下的饱和（切分口径须与索引侧一致）
        query_len = len(set(tokenize(query)))
        lex: dict = {}
        for cid, bm25 in lex_rows:
            norm = round(BM25Index.normalize(float(bm25), query_len), 4)
            if norm < self.lexical_min:
                continue
            lex[cid] = norm

        # 词法命中的 doc/meta：向量已召回的直接复用，其余从向量库补齐（查不到的丢弃）。
        # 双命中项必须一并保留 —— 曾因只补齐「仅词法」项、再按 isinstance(tuple) 过滤，
        # 把双命中的 BM25 分连同条目一起丢掉，使混合检索只对向量未召回的片段生效。
        missing = [cid for cid in lex if cid not in vec]
        backfill = {
            cid: (doc, meta) for cid, doc, meta in self.store.get_by_ids(missing)
        } if missing else {}
        lex_full: dict = {}
        for cid, norm in lex.items():  # 按 BM25 降序重建，lex_rank 依赖该顺序
            if cid in vec:
                lex_full[cid] = (norm, vec[cid][1], vec[cid][2])
            elif cid in backfill:
                lex_full[cid] = (norm, *backfill[cid])
        lex = lex_full

        if not vec and not lex:
            return []

        # 加权融合
        vec_rank = {cid: i + 1 for i, cid in enumerate(vec)}
        lex_rank = {cid: i + 1 for i, cid in enumerate(lex)}
        all_ids = list(dict.fromkeys([*vec.keys(), *lex.keys()]))
        k = self.hybrid_k
        # 运行时归一权重：配置里两权重之和写成非 1 也不会改变展示分量纲
        tw = (self.vector_weight + self.bm25_weight) or 1.0
        w_v, w_b = self.vector_weight / tw, self.bm25_weight / tw

        fused = []  # (rrf, score, hit)
        for cid in all_ids:
            v = vec.get(cid)
            lx = lex.get(cid)
            rrf = 0.0
            raw = norm = 0.0
            if v:
                rrf += 1.0 / (k + vec_rank[cid])
                raw = v[0]
            if lx:
                rrf += 1.0 / (k + lex_rank[cid])
                norm = lx[0]
            # 缺失源记 0：单源命中不再被「按出现源归一」抬到与双命中同一量级
            score = w_v * raw + w_b * norm
            doc, meta = (v or lx)[1], (v or lx)[2]
            fused.append(
                (
                    rrf,
                    score,
                    RetrievalHit(
                        doc_id=meta.get("doc_id", cid.split("#")[0]),
                        chunk_id=cid,
                        title=meta.get("title", ""),
                        category=meta.get("category", ""),
                        source=meta.get("source", ""),
                        text=doc,
                        score=round(score, 4),
                        tags=list(meta.get("tags") or []),
                    ),
                )
            )

        # 展示分为主序（量纲绝对可比），RRF 仅在同分时作 tie-breaker
        fused.sort(key=lambda t: (-t[1], -t[0]))
        hits = [t[2] for t in fused]
        return hits[:top_k] if top_k else hits

    @traceable("search_knowledge_base", run_type="retriever")
    async def search(self, query: str, top_k: int = None) -> List[RetrievalHit]:
        query = (query or "").strip()
        if not query:
            return []
        limit = top_k or self.top_k
        if self.reranker is None:
            return self._recall(query, limit)
        hits = self._recall(query, self.rerank_k)
        hits = await self.reranker.rerank(query, hits)
        return hits[:limit]

    async def search_docs(
        self,
        query: str,
        top_k: int = None,
        category: Optional[str] = None,
        tags: Optional[List[str]] = None,
    ) -> List[RetrievalDoc]:
        """文档级检索：召回 → 分源过滤 → 加权融合 → 分类/tag 过滤 → 按 doc_id 合并去重。

        返回文档级列表：score 取该文档命中 chunk 的最高展示分，
        chunks 为该文档下所有命中片段（按分数降序），relevance 由 score 派生。
        """
        query = (query or "").strip()
        if not query:
            return []
        hits = self._recall(query, None)
        if self.reranker is not None:
            hits = await self.reranker.rerank(
                query, hits[: self.rerank_k]
            )
        if category:
            hits = [h for h in hits if h.category == category]
        if tags:
            wanted = set(tags)
            hits = [h for h in hits if wanted & set(h.tags)]

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

        # 文档序继承其最优 chunk 的顺序：hits 已按展示分降序，故各文档首次出现的
        # 位置就是它的最高分位置，docs 的插入序即文档序，无需再按分数重排。
        result = list(docs.values())
        for d in result:
            d.relevance = relevance_of(d.score)
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
