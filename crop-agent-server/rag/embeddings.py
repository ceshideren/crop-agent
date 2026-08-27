"""嵌入层：默认使用本地无依赖哈希嵌入，保证离线可跑；配置远端嵌入后自动切换。"""
import math
import re

_ZH = re.compile(r"[\u4e00-\u9fff]")
_TOKEN = re.compile(r"[a-z0-9]+")


def _hash(s: str) -> int:
    h = 0
    for ch in s:
        h = (h * 131 + ord(ch)) & 0x7FFFFFFF
    return h


def _bump(vec, token: str, dim: int) -> None:
    h = _hash(token)
    idx = h % dim
    sign = 1.0 if (h >> 1) & 1 else -1.0
    vec[idx] += sign


def local_hash_embed(text: str, dim: int = 384) -> list:
    """中文按字 + 二元组、英文按词做哈希投影，得到可归一化的确定性向量。"""
    vec = [0.0] * dim
    t = (text or "").lower()

    zh = _ZH.findall(t)
    for ch in zh:
        _bump(vec, ch, dim)
    for i in range(len(zh) - 1):
        _bump(vec, zh[i] + zh[i + 1], dim)
    for tok in _TOKEN.findall(t):
        _bump(vec, tok, dim)

    norm = math.sqrt(sum(v * v for v in vec)) or 1.0
    return [v / norm for v in vec]


class LocalHashEmbedding:
    """LlamaIndex 兼容接口的最小实现（dim 固定 384）。

    哈希嵌入的相似度量级（约 0.15–0.45）低于语义嵌入，因此声明更低的推荐阈值，
    供 Retriever 在本地模式自动采用；配置远端嵌入后则使用配置的 similarity_threshold。
    """

    dim = 384
    is_local = True
    recommended_threshold = 0.15

    def embed_query(self, text: str) -> list:
        return local_hash_embed(text, self.dim)

    def get_text_embedding(self, text: str) -> list:
        return local_hash_embed(text, self.dim)

    def embed_documents(self, texts: list) -> list:
        return [local_hash_embed(t, self.dim) for t in texts]


def get_embedder():
    """根据配置返回嵌入器。openai 需配置 OPENAI_API_KEY，否则回退本地哈希嵌入。"""
    from config import get_settings

    s = get_settings()
    if s.embedding_provider == "openai" and s.openai_api_key:
        try:
            from llama_index.embeddings.openai import OpenAIEmbedding

            return OpenAIEmbedding(
                model=s.openai_embedding_model, api_key=s.openai_api_key
            )
        except Exception:  # pragma: no cover - 依赖缺失时降级
            pass
    return LocalHashEmbedding()
