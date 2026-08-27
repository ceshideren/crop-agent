"""BM25 词法检索：纯 Python 实现（无第三方依赖）。

与 LocalHashEmbedding 的 token 方案保持一致（中文单字 + 相邻二元组 + 英文/数字词），
保证向量检索与词法检索的 token 空间对齐：短查询的精确词条即使向量分低于阈值，
也能通过 BM25 命中召回（方案 P0：混合检索）。

索引由向量库（MemoryStore / ChromaStore）维护，add/remove/clear 钩子同步；
语料规模小（chunks < 1000），df/avgdl 在 search 时现算，避免增量统计的一致性负担。
"""

import math
import re

_ZH = re.compile(r"[\u4e00-\u9fff]+")
_EN = re.compile(r"[a-z0-9]+")


def tokenize(text: str) -> list:
    """切分为 token 列表：中文连续段拆为单字 + 相邻二元组，英文/数字为单词。"""
    t = (text or "").lower()
    tokens: list = []
    for zh in _ZH.findall(t):
        for ch in zh:
            tokens.append(ch)
        for i in range(len(zh) - 1):
            tokens.append(zh[i] + zh[i + 1])
    tokens.extend(_EN.findall(t))
    return tokens


class BM25Index:
    """内存 BM25 索引。

    采用 BM25+（δ 平滑 IDF），k1=1.5、b=0.75；原始分可经 normalize 映射到 (0,1)。
    """

    K1 = 1.5
    B = 0.75
    DELTA = 0.5

    def __init__(self):
        self._docs: dict = {}  # chunk_id -> tokens
        self._doc_len: dict = {}  # chunk_id -> token 数

    def add(self, ids, texts) -> None:
        """批量 upsert 文档文本（同名 id 覆盖）。"""
        for cid, text in zip(ids, texts):
            tokens = tokenize(text)
            self._docs[cid] = tokens
            self._doc_len[cid] = len(tokens)

    def remove(self, ids) -> None:
        for cid in ids or []:
            self._docs.pop(cid, None)
            self._doc_len.pop(cid, None)

    def clear(self) -> None:
        self._docs.clear()
        self._doc_len.clear()

    def count(self) -> int:
        return len(self._docs)

    def search(self, query: str, top_k: int = 20) -> list:
        """返回 [(chunk_id, score)]，按 BM25 得分降序；空语料/空查询返回 []。"""
        q_tokens = tokenize(query)
        if not q_tokens or not self._docs:
            return []
        n = len(self._docs)
        avgdl = sum(self._doc_len.values()) / n

        # 文档频率现算（语料小）
        df: dict = {}
        for tokens in self._docs.values():
            for tok in set(tokens):
                df[tok] = df.get(tok, 0) + 1

        scores: dict = {}
        for cid, tokens in self._docs.items():
            dl = self._doc_len.get(cid, len(tokens))
            tf: dict = {}
            for tok in tokens:
                tf[tok] = tf.get(tok, 0) + 1
            s = 0.0
            for tok in set(q_tokens):
                f = tf.get(tok, 0)
                if f == 0:
                    continue
                idf = math.log(
                    (n - df.get(tok, 0) + 0.5) / (df.get(tok, 0) + 0.5) + 1.0
                )
                k_factor = 1.0 - self.B + self.B * dl / avgdl if avgdl else 1.0
                s += idf * (f * (self.K1 + 1)) / (f + self.K1 * k_factor)
            if s > 0:
                scores[cid] = s
        ranked = sorted(scores.items(), key=lambda kv: -kv[1])
        return ranked[:top_k] if top_k else ranked

    @staticmethod
    def normalize(score: float, query_len: int = 1) -> float:
        """BM25 原始分 → (0,1) 归一化（单调、绝对量纲）。

        原始分随查询 token 数近似线性增长，长查询下累加会使所有片段饱和到 0.9 上下，
        逐字命中与零星共字的差距被压平。先按查询唯一 token 数摊平为「平均每 token
        匹配强度」再做饱和映射，得到与查询长度无关的绝对量纲。
        query_len 默认 1 时退化为原行为。
        """
        x = score / max(query_len, 1)
        return x / (x + 1.0)
