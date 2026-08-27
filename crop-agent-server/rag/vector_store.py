"""向量库封装：优先 ChromaDB（PersistentClient，cosine 空间），不可用时降级为内存实现。

两个 store 均维护一个 BM25 词法索引（rag.bm25.BM25Index），
在 add/delete/clear 时同步，供混合检索（向量 + 词法 + RRF）使用。
"""
import os
from typing import List, Optional

from rag.bm25 import BM25Index


def _cosine(a: list, b: list) -> float:
    dot = sum(x * y for x, y in zip(a, b))
    na = sum(x * x for x in a) ** 0.5
    nb = sum(y * y for y in b) ** 0.5
    return dot / ((na * nb) or 1.0)


def _meta_match(meta: dict, where: dict) -> bool:
    """where 子句逐键等值匹配（当前只支持等值，与 Chroma where 的用法对齐）。"""
    return all(meta.get(k) == v for k, v in where.items())


class MemoryStore:
    """纯 Python 内存向量库（cosine 相似度），用于 chromadb 缺失时的兜底。"""

    def __init__(self):
        self._ids: List[str] = []
        self._embeddings: list = []
        self._documents: list = []
        self._metadatas: list = []
        self._lex = BM25Index()

    def add(self, ids, embeddings, documents, metadatas) -> None:
        # upsert 语义：同名 id 覆盖（上传同名文件时向量不重复）
        for i, e, d, m in zip(ids, embeddings, documents, metadatas):
            if i in self._ids:
                idx = self._ids.index(i)
                self._embeddings[idx] = e
                self._documents[idx] = d
                self._metadatas[idx] = m or {}
                continue
            self._ids.append(i)
            self._embeddings.append(e)
            self._documents.append(d)
            self._metadatas.append(m or {})
        self._lex.add(ids, documents)

    def query(self, embedding, top_k=5) -> list:
        scored = [
            (_cosine(embedding, e), i) for i, e in enumerate(self._embeddings)
        ]
        scored.sort(key=lambda x: -x[0])
        out = []
        for sim, i in scored[:top_k]:
            out.append((self._ids[i], sim, self._documents[i], self._metadatas[i]))
        return out

    def count(self) -> int:
        return len(self._ids)

    def clear(self) -> None:
        self._ids, self._embeddings, self._documents, self._metadatas = [], [], [], []
        self._lex.clear()

    def delete_by_meta(self, where: dict) -> int:
        """按元数据等值匹配删除，返回删除条数。"""
        old_ids = list(self._ids)
        keep = [
            (i, e, d, m)
            for i, e, d, m in zip(
                self._ids, self._embeddings, self._documents, self._metadatas
            )
            if not _meta_match(m or {}, where)
        ]
        removed = len(old_ids) - len(keep)
        self._ids = [x[0] for x in keep]
        self._embeddings = [x[1] for x in keep]
        self._documents = [x[2] for x in keep]
        self._metadatas = [x[3] for x in keep]
        if removed:
            keep_ids = {x[0] for x in keep}
            self._lex.remove([i for i in old_ids if i not in keep_ids])
        return removed

    def delete(self, ids: list) -> int:
        """按 id 列表直接删除，返回删除条数。"""
        gone = set(ids)
        keep = [
            (i, e, d, m)
            for i, e, d, m in zip(
                self._ids, self._embeddings, self._documents, self._metadatas
            )
            if i not in gone
        ]
        removed = len(self._ids) - len(keep)
        self._ids = [x[0] for x in keep]
        self._embeddings = [x[1] for x in keep]
        self._documents = [x[2] for x in keep]
        self._metadatas = [x[3] for x in keep]
        if removed:
            self._lex.remove(ids)
        return removed

    def get_by_ids(self, ids: list) -> list:
        """按 id 列表返回 [(id, doc, meta)]，保持传入顺序，缺失的跳过。"""
        out = []
        for cid in ids or []:
            if cid in self._ids:
                i = self._ids.index(cid)
                out.append((cid, self._documents[i], self._metadatas[i] or {}))
        return out

    def lexical_search(self, query: str, top_k: int = 20) -> list:
        """BM25 词法召回：返回 [(chunk_id, bm25_score)]，按得分降序。"""
        return self._lex.search(query, top_k)

    def get_by_meta(self, where: dict) -> list:
        """按元数据等值匹配返回 [(id, doc, meta)]，保持插入顺序。"""
        out = []
        for i, d, m in zip(self._ids, self._documents, self._metadatas):
            if _meta_match(m or {}, where):
                out.append((i, d, m or {}))
        return out

    def update_meta(self, where: dict, updates: dict) -> int:
        """按元数据等值匹配原地更新（如改分类），返回命中条数。"""
        n = 0
        for i, m in enumerate(self._metadatas):
            meta = m or {}
            if _meta_match(meta, where):
                meta.update(updates)
                self._metadatas[i] = meta
                n += 1
        return n


class ChromaStore:
    """ChromaDB 持久化向量库。"""

    def __init__(self, persist_dir: str, collection_name: str = "crop_knowledge"):
        import chromadb

        self._client = chromadb.PersistentClient(path=persist_dir)
        self._col = self._client.get_or_create_collection(
            name=collection_name, metadata={"hnsw:space": "cosine"}
        )
        # 词法索引：启动时从已有文档全量构建（知识库规模小，成本可忽略）
        self._lex = BM25Index()
        try:
            res = self._col.get(include=["documents"])
            ids = res.get("ids", []) or []
            docs = res.get("documents", []) or []
            if ids:
                self._lex.add(ids, docs)
        except Exception:
            pass

    def add(self, ids, embeddings, documents, metadatas) -> None:
        self._col.upsert(
            ids=ids, embeddings=embeddings, documents=documents, metadatas=metadatas
        )
        self._lex.add(ids, documents)

    def query(self, embedding, top_k=5) -> list:
        res = self._col.query(query_embeddings=[embedding], n_results=top_k)
        ids = res.get("ids", [[]])[0]
        dists = res.get("distances", [[]])[0]
        docs = res.get("documents", [[]])[0]
        metas = res.get("metadatas", [[]])[0]
        out = []
        for cid, dist, doc, meta in zip(ids, dists, docs, metas):
            out.append((cid, 1.0 - dist, doc, meta or {}))
        return out

    def count(self) -> int:
        return self._col.count()

    def clear(self) -> None:
        try:
            self._col.delete(where={})
        except Exception:
            pass
        self._lex.clear()

    def delete_by_meta(self, where: dict) -> int:
        """按元数据等值匹配删除，返回删除条数。"""
        try:
            ids = self._col.get(where=where).get("ids", [])
        except Exception:
            ids = []
        if ids:
            self._col.delete(ids=ids)
            self._lex.remove(ids)
        return len(ids)

    def delete(self, ids: list) -> int:
        """按 id 列表直接删除，返回删除条数。"""
        if not ids:
            return 0
        self._col.delete(ids=list(ids))
        self._lex.remove(ids)
        return len(ids)

    def get_by_ids(self, ids: list) -> list:
        """按 id 列表返回 [(id, doc, meta)]，保持传入顺序，缺失的跳过。"""
        if not ids:
            return []
        res = self._col.get(ids=list(ids), include=["documents", "metadatas"])
        out = []
        for cid, doc, meta in zip(
            res.get("ids", []),
            res.get("documents", []),
            res.get("metadatas", []),
        ):
            out.append((cid, doc, meta or {}))
        return out

    def lexical_search(self, query: str, top_k: int = 20) -> list:
        """BM25 词法召回：返回 [(chunk_id, bm25_score)]，按得分降序。"""
        return self._lex.search(query, top_k)

    def get_by_meta(self, where: dict) -> list:
        """按元数据等值匹配返回 [(id, doc, meta)]。"""
        res = self._col.get(where=where, include=["documents", "metadatas"])
        out = []
        for cid, doc, meta in zip(
            res.get("ids", []),
            res.get("documents", []),
            res.get("metadatas", []),
        ):
            out.append((cid, doc, meta or {}))
        return out

    def update_meta(self, where: dict, updates: dict) -> int:
        """按元数据等值匹配更新（如改分类），返回命中条数。"""
        try:
            res = self._col.get(where=where, include=["metadatas"])
        except Exception:
            return 0
        ids = res.get("ids", [])
        metas = res.get("metadatas", [])
        if not ids:
            return 0
        new_metas = []
        for m in metas:
            merged = dict(m or {})
            merged.update(updates)
            new_metas.append(merged)
        self._col.update(ids=ids, metadatas=new_metas)
        return len(ids)


def get_vector_store(persist_dir: Optional[str] = None):
    from config import get_settings

    s = get_settings()
    persist_dir = persist_dir or s.vector_persist_dir
    try:
        os.makedirs(persist_dir, exist_ok=True)
        return ChromaStore(persist_dir)
    except Exception:
        # chromadb 未安装或初始化失败 → 内存兜底，保证服务可用
        return MemoryStore()
