"""查询改写：检索前用 LLM 把短查询扩展为语义更丰富的查询（方案 P0）。

LLM 不可用 / 查询过长 / 调用失败 / 输出异常时一律原样返回，永不阻断检索。
"""

from agent.prompts import REWRITE_PROMPT


class QueryRewriter:
    def __init__(self, llm, settings=None):
        self.llm = llm
        self.settings = settings

    def enabled(self, query: str) -> bool:
        """是否应该改写：LLM 可用 + 未全局关闭 + 查询长度不超过上限。"""
        if not self.llm or not getattr(self.llm, "available", False):
            return False
        if self.settings and not getattr(self.settings, "query_rewrite", True):
            return False
        max_len = getattr(self.settings, "rewrite_max_len", 30) if self.settings else 30
        return 0 < len((query or "").strip()) <= max_len

    async def rewrite(self, query: str) -> str:
        query = (query or "").strip()
        if not query or not self.enabled(query):
            return query
        try:
            out = await self.llm.generate(
                [
                    {"role": "system", "content": REWRITE_PROMPT},
                    {"role": "user", "content": query},
                ]
            )
            out = (out or "").strip().strip('"').strip("'")
            if out and len(out) <= 200:
                return out
        except Exception:
            pass
        return query
