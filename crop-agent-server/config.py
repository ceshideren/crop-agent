"""全局配置：从环境变量 / .env 读取。"""
from functools import lru_cache

from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    model_config = SettingsConfigDict(
        env_file=".env", env_file_encoding="utf-8", extra="ignore"
    )

    # 基础
    app_name: str = "禾知 · 农作物多模态 RAG Agent"
    api_prefix: str = "/api"
    db_url: str = "sqlite:///./crop_agent.db"

    # RAG
    knowledge_dir: str = "../knowledge"
    vector_persist_dir: str = "./storage/chroma"
    top_k: int = 5
    recall_k: int = 20  # 向量/词法召回规模：先召回再过滤，保证阈值过滤真正生效
    similarity_threshold: float = 0.65
    hybrid_search: bool = True  # 混合检索：向量 + BM25 词法 + RRF 融合
    hybrid_k: int = 60  # RRF 常数 k
    bm25_weight: float = 0.5  # 展示分中 BM25 权重（与 vector_weight 之和建议为 1）
    vector_weight: float = 0.5  # 展示分中向量相似度权重
    lexical_min: float = 0.2  # BM25 归一化分下限（过滤词法噪声）
    # 相关性分级阈值：后端是唯一真相源，前端按 relevance 标签分组而非自行比分。
    # 数值按本地哈希嵌入的展示分量纲校准（逐字命中约 0.53、口语命中约 0.44、
    # 无关查询最高约 0.30）；换用语义嵌入后量纲变化，需重新校准。
    relevance_high: float = 0.42
    relevance_mid: float = 0.32
    relevance_low: float = 0.20
    chunk_size: int = 400
    chunk_overlap: int = 40
    reindex: bool = False

    # 查询改写（P0）：检索前用 LLM 把短查询扩展为语义更丰富的查询
    query_rewrite: bool = True
    rewrite_max_len: int = 30  # 超过此长度的查询不改写（省调用）

    # 重排序（P1）：none | llm（cohere/bge 等接入点后续扩展）
    reranker: str = "none"
    rerank_k: int = 20  # 重排候选数（= recall_k）

    # 元数据标签（P1）：规则标签始终启用；meta_tagging 预留 LLM 打标签
    meta_tagging: bool = False

    # 文本生成（deepseek-v4-flash 目标模型，走 DeepSeek OpenAI 兼容端点）
    deepseek_api_key: str = ""
    deepseek_base_url: str = "https://api.deepseek.com"
    deepseek_model: str = "deepseek-v4-flash"

    # 多模态（mimo-2.5）
    mimo_api_key: str = ""
    mimo_base_url: str = ""
    mimo_model: str = "mimo-2.5"

    # 嵌入
    embedding_provider: str = "local"  # local | openai
    openai_api_key: str = ""
    openai_embedding_model: str = "text-embedding-3-small"

    # 可观测性（LangSmith；tracing=false 或 key 为空时完全不生效）
    langsmith_tracing: bool = False
    langsmith_api_key: str = ""
    langsmith_project: str = "crop-agent-server"
    langsmith_endpoint: str = "https://api.smith.langchain.com"


@lru_cache
def get_settings() -> Settings:
    return Settings()
