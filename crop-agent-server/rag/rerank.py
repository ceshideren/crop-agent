"""重排序层：初次召回候选 → 精排 → 返回最终顺序（方案 P1）。

- 默认恒等（reranker=none），不改变召回顺序；
- reranker=llm 时用 LLM 对候选片段做 listwise 排序（只调一次 LLM），
  输出解析失败时回退恒等，检索永不因重排失败而中断；
- cohere / bge 等模型接入点为 build_reranker，后续按配置扩展。
"""

import json
import re

from agent.prompts import RERANK_PROMPT

_CHUNK_ID_RE = re.compile(r"[A-Z0-9]{7}#chunk_\d+")


class Reranker:
    """恒等重排：不改变顺序。"""

    async def rerank(self, query: str, hits) -> list:
        return hits


class LLMReranker(Reranker):
    """用 LLM 对候选片段排序（listwise）。"""

    def __init__(self, llm, top_k: int = 20, max_chars: int = 200):
        self.llm = llm
        self.top_k = top_k
        self.max_chars = max_chars

    async def rerank(self, query: str, hits) -> list:
        if not hits or not self.llm or not getattr(self.llm, "available", False):
            return hits
        cands = hits[: self.top_k]
        items = "\n".join(
            f"{i}. [{h.chunk_id}] {h.text[: self.max_chars]}" for i, h in enumerate(cands)
        )
        try:
            out = await self.llm.generate(
                [
                    {"role": "system", "content": RERANK_PROMPT},
                    {"role": "user", "content": f"查询：{query}\n候选片段：\n{items}"},
                ]
            )
        except Exception:
            return hits
        order = self._parse(out, {h.chunk_id for h in cands})
        if not order:
            return hits
        by_id = {h.chunk_id: h for h in cands}
        ranked = [by_id[cid] for cid in order if cid in by_id]
        seen = set(order)
        ranked.extend(h for h in cands if h.chunk_id not in seen)
        return ranked + hits[len(cands):]

    @staticmethod
    def _parse(text: str, known: set) -> list:
        """从 LLM 输出提取 chunk_id 有序列表（JSON 优先，其次按出现顺序）。"""
        if not text:
            return []
        m = re.search(r"\{.*\}", text, re.S)
        if m:
            try:
                data = json.loads(m.group(0))
                arr = data.get("ranking") or data.get("order") or data.get("chunk_ids")
                if isinstance(arr, list):
                    return [str(x) for x in arr]
            except (ValueError, AttributeError):
                pass
        return [tok for tok in _CHUNK_ID_RE.findall(text) if tok in known]


def build_reranker(mode: str = "none", llm=None, top_k: int = 20) -> Reranker:
    mode = (mode or "none").lower()
    if mode == "llm":
        return LLMReranker(llm=llm, top_k=top_k)
    # cohere / bge-reranker 等接入点（需相应 API Key / 模型环境）
    return Reranker()
