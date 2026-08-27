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
    recall_k: int = 20  # 向量召回规模：先召回再过滤，保证阈值过滤真正生效
    similarity_threshold: float = 0.65
    hybrid_search: bool = True  # 查询词与标题/分类重叠的轻量加权（BM25+RRF 留作后续）
    chunk_size: int = 512
    chunk_overlap: int = 64
    reindex: bool = False

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
