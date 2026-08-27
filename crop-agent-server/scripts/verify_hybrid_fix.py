"""混合检索排序回归验证：向量 + BM25 融合是否把「逐字命中」排在第一。

背景：曾有缺陷把「向量+词法双命中」片段的 BM25 分静默丢弃，导致查询《西瓜种植
技术指南》原文时，向量分低到被阈值挡住、因而独占 BM25 分的《小麦》片段冲上第一
（0.8698），而逐字命中的西瓜只有 0.4859。本脚本把该行为固化为断言。

只读真实索引（storage/chroma），不启服务、不写库。用法（在 crop-agent-server 目录）：
  uv run python scripts/verify_hybrid_fix.py
  或  .venv/Scripts/python.exe scripts/verify_hybrid_fix.py
"""
import asyncio
import os
import sys

if hasattr(sys.stdout, "reconfigure"):
    sys.stdout.reconfigure(encoding="utf-8", errors="replace")

_SERVER_ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, _SERVER_ROOT)

# 必须在导入配置前固定为本地哈希嵌入：分级阈值按该量纲校准，.env 若配了 openai 会失准
os.environ["EMBEDDING_PROVIDER"] = "local"

from config import get_settings  # noqa: E402
from rag.embeddings import get_embedder  # noqa: E402
from rag.retriever import Retriever  # noqa: E402
from rag.vector_store import get_vector_store  # noqa: E402

# 逐字摘自《西瓜种植技术指南》正文，是检索应当命中的最强信号
MELON_QUERY = (
    "常见西瓜品种及特点 西瓜品种繁多，种植户应根据市场需求和当地气候条件"
    "选择合适的品种："
)
OFF_TOPIC = "量子计算机的退相干时间"

ok = True


def check(name, cond, extra=""):
    global ok
    print(f"[{'PASS' if cond else 'FAIL'}] {name} {extra}")
    ok &= bool(cond)
    return bool(cond)


def build() -> Retriever:
    s = get_settings()
    return Retriever(
        get_vector_store(os.path.join(_SERVER_ROOT, "storage", "chroma")),
        get_embedder(),
        s.top_k,
        s.similarity_threshold,
        s.recall_k,
        s.hybrid_search,
        s.hybrid_k,
        s.bm25_weight,
        s.vector_weight,
        s.lexical_min,
        s.rerank_k,
        None,
    )


r = build()
if r.store.count() == 0:
    print("SKIP：storage/chroma 为空，先启动一次服务建立索引再跑本脚本")
    sys.exit(0)

# ---- A1/A2：chunk 级 —— 逐字命中排第一，且分数达到高相关量级 ----
hits = r._recall(MELON_QUERY, None)
top = hits[0] if hits else None
check(
    "A1 chunk 级 Top1 是西瓜文档（修复前是小麦，因其独占 BM25 分）",
    top is not None and "西瓜" in top.title,
    repr([(h.title, h.score) for h in hits[:3]]),
)
check(
    "A2 Top1 展示分达到高相关量级（修复前 0.4859，含义还是纯向量分）",
    top is not None and top.score >= 0.45,
    f"score={top.score if top else None}",
)

# ---- A3/A4：文档级 —— 顺序继承 chunk 序，小麦被挤出前三 ----
docs = asyncio.run(r.search_docs(MELON_QUERY))
check(
    "A3 文档级 Top1 是西瓜且判为 high",
    docs and "西瓜" in docs[0].title and docs[0].relevance == "high",
    repr([(d.title, d.score, d.relevance) for d in docs[:3]]),
)
wheat_at = next((i for i, d in enumerate(docs) if "小麦" in d.title), -1)
check(
    "A4 小麦文档不在前三（修复前是第 1）",
    wheat_at == -1 or wheat_at >= 3,
    f"小麦位次={wheat_at}",
)

# ---- A5：无关查询不得产生 high —— 防止改回候选集内相对归一化 ----
off = asyncio.run(r.search_docs(OFF_TOPIC))
check(
    "A5 无关查询无 high（相对归一化会把 Top1 拉满到 1.0，破坏诚实性约定）",
    all(d.relevance != "high" for d in off),
    repr([(d.title, d.score, d.relevance) for d in off[:3]]),
)

# ---- 四类查询形态快照：正确文档必须排第一 ----
print("\n--- 查询形态快照 ---")
for q, want in [
    (MELON_QUERY, "西瓜"),
    ("稻瘟病", "水稻"),
    ("番茄早疫病", "番茄"),
    ("西瓜怎么选品种", "西瓜"),
]:
    ds = asyncio.run(r.search_docs(q))
    check(
        f"  「{q[:12]}…」Top1 含「{want}」" if len(q) > 12 else f"  「{q}」Top1 含「{want}」",
        ds and want in ds[0].title,
        repr([(d.title, round(d.score, 3), d.relevance) for d in ds[:2]]),
    )

print("\nVERIFY", "PASS" if ok else "FAIL")
sys.exit(0 if ok else 1)
