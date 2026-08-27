"""FastAPI 入口：装配依赖、启动索引、挂载路由。"""
from contextlib import asynccontextmanager
from pathlib import Path

from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware

from agent.crop_agent import CropAgent
from agent.registry import set_agent
from api import chat, groups, knowledge, ws
from config import get_settings
from db.database import SessionLocal, init_db
from multimodal.image_analyzer import ImageAnalyzer
from rag.embeddings import get_embedder
from rag.retriever import Retriever
from rag.vector_store import get_vector_store
from services.llm import LLMClient

BASE_DIR = Path(__file__).resolve().parent


def _resolve(path: str) -> str:
    p = Path(path)
    if not p.is_absolute():
        p = BASE_DIR / p
    return str(p)


def _seed_default_user() -> None:
    from db.models import User

    db = SessionLocal()
    try:
        if db.query(User).count() == 0:
            db.add(User(name="演示用户"))
            db.commit()
    finally:
        db.close()


@asynccontextmanager
async def lifespan(app: FastAPI):
    settings = get_settings()
    init_db()
    _seed_default_user()

    embedder = get_embedder()
    store = get_vector_store(_resolve(settings.vector_persist_dir))
    retriever = Retriever(
        store,
        embedder,
        settings.top_k,
        settings.similarity_threshold,
        settings.recall_k,
        settings.hybrid_search,
    )
    analyzer = ImageAnalyzer(settings)
    llm = LLMClient(settings)
    agent = CropAgent(
        retriever=retriever,
        analyzer=analyzer,
        llm=llm,
        db_factory=SessionLocal,
        knowledge_dir=_resolve(settings.knowledge_dir),
        settings=settings,
    )

    if settings.reindex or store.count() == 0:
        agent.reindex()

    set_agent(agent)
    yield


app = FastAPI(title="禾知 · 农作物多模态 RAG Agent", lifespan=lifespan)

app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

app.include_router(chat.router)
app.include_router(groups.router)
app.include_router(knowledge.router)
app.include_router(ws.router)


@app.get("/health")
def health():
    return {"status": "ok"}
