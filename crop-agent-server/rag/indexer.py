"""知识库加载与索引构建（LlamaIndex 文档加载/分块思路 + 向量库持久化）。"""
import hashlib
import os
import re
from dataclasses import dataclass
from datetime import datetime, timezone
from typing import List


@dataclass
class DocChunk:
    doc_id: str
    title: str
    source: str
    category: str
    chunk_index: int
    text: str
    file_size: int = 0
    updated_at: datetime | None = None


def _read_text(path: str) -> str:
    with open(path, "r", encoding="utf-8") as f:
        return f.read()


# 知识库支持的文档类型（md/txt 直读；docx/pptx 解析二进制提取文本）
_SUPPORTED_EXTS = (".md", ".txt", ".docx", ".pptx")
_TEXT_EXTS = (".md", ".txt")
_BINARY_EXTS = (".docx", ".pptx")
# file_parser 解析失败/缺库时的占位前缀，命中即视为无法解析（禁止入索引）
_PARSE_FAIL_PREFIXES = ("[文件解析失败", "[未安装", "[暂不支持", "未提取到文本")


def _read_document(path: str) -> str:
    """按扩展名读取文档文本；无法解析时抛 ValueError。"""
    fn = os.path.basename(path)
    ext = os.path.splitext(fn)[1].lower()
    if ext in _TEXT_EXTS:
        return _read_text(path)
    if ext in _BINARY_EXTS:
        from services.file_parser import extract_file_text

        with open(path, "rb") as f:
            data = f.read()
        text = extract_file_text(fn, data)
        if text.startswith(_PARSE_FAIL_PREFIXES):
            raise ValueError(f"无法解析文档 {fn}：{text}")
        return text
    raise ValueError(f"不支持的文件类型：{fn}")


def _file_stats(path: str) -> tuple:
    """返回 (file_size, updated_at_naive_utc)；文件不可读时返回默认值。"""
    try:
        st = os.stat(path)
        mtime = datetime.fromtimestamp(st.st_mtime, tz=timezone.utc).replace(tzinfo=None)
        return st.st_size, mtime
    except OSError:
        return 0, None


def load_document(path: str) -> dict:
    """读取单个 md/txt/docx/pptx 文档 → doc dict（供上传 / 单文档重建复用）。"""
    text = _read_document(path)
    fn = os.path.basename(path)
    return {
        "path": path,
        "title": os.path.splitext(fn)[0],
        "category": os.path.basename(os.path.dirname(path)),
        "text": text,
    }


def load_documents(knowledge_dir: str) -> List[dict]:
    """遍历 knowledge/ 目录，读取 md/txt/docx/pptx 文档。"""
    docs: List[dict] = []
    if not os.path.isdir(knowledge_dir):
        return docs
    for root, _, files in os.walk(knowledge_dir):
        for fn in sorted(files):
            if not fn.lower().endswith(_SUPPORTED_EXTS):
                continue
            path = os.path.join(root, fn)
            try:
                text = _read_document(path)
            except Exception:
                continue
            docs.append(
                {
                    "path": path,
                    "title": os.path.splitext(fn)[0],
                    "category": os.path.basename(root),
                    "text": text,
                }
            )
    return docs


def _split_markdown(text: str, chunk_size: int, overlap: int) -> List[str]:
    """按 Markdown 标题优先分块，再按空行段落做滑窗合并。"""
    blocks = re.split(r"\n#{1,6}\s+", text)
    chunks: List[str] = []
    buf = ""
    for block in blocks:
        paras = [p.strip() for p in re.split(r"\n\s*\n", block) if p.strip()]
        for p in paras:
            if buf and len(buf) + len(p) + 2 > chunk_size:
                chunks.append(buf)
                buf = buf[-overlap:] if overlap else ""
            buf = f"{buf}\n\n{p}".strip() if buf else p
    if buf:
        chunks.append(buf)
    return chunks or [text[:chunk_size]]


def _doc_id(path: str) -> str:
    return "K" + hashlib.md5(path.encode("utf-8")).hexdigest()[:6].upper()


def split_documents(docs: List[dict], chunk_size: int, overlap: int) -> List[DocChunk]:
    chunks: List[DocChunk] = []
    for d in docs:
        doc_id = _doc_id(d["path"])
        size, mtime = _file_stats(d["path"])
        for ci, text in enumerate(_split_markdown(d["text"], chunk_size, overlap)):
            chunks.append(
                DocChunk(
                    doc_id=doc_id,
                    title=d["title"],
                    source=d["path"],
                    category=d["category"],
                    chunk_index=ci,
                    text=text,
                    file_size=size,
                    updated_at=mtime,
                )
            )
    return chunks


def split_document(doc: dict, chunk_size: int, overlap: int) -> List[DocChunk]:
    """单个 doc dict → chunk 列表（doc_id 稳定为 md5(path)）。"""
    return split_documents([doc], chunk_size, overlap)


def _doc_meta(chunks: List[DocChunk]) -> List[dict]:
    """chunk 列表 → knowledge_meta 列表（含分类 / 文件大小 / 更新时间）。"""
    meta_map = {}
    for c in chunks:
        m = meta_map.setdefault(
            c.doc_id,
            {
                "doc_id": c.doc_id,
                "title": c.title,
                "source": c.source,
                "category": c.category,
                "chunk_count": 0,
                "file_size": c.file_size,
                "updated_at": c.updated_at,
            },
        )
        m["chunk_count"] += 1
        if c.file_size:
            m["file_size"] = c.file_size
        if c.updated_at:
            m["updated_at"] = c.updated_at
    return list(meta_map.values())


def build_index(knowledge_dir: str, store, embedder, chunk_size=512, overlap=64):
    """加载 → 分块 → 嵌入 → 入库；返回 (chunk_ids, knowledge_meta 列表)。"""
    docs = load_documents(knowledge_dir)
    chunks = split_documents(docs, chunk_size, overlap)
    if not chunks:
        return [], []

    ids = [f"{c.doc_id}#chunk_{c.chunk_index:02d}" for c in chunks]
    texts = [c.text for c in chunks]
    embeddings = embedder.embed_documents(texts)
    metadatas = [
        {
            "doc_id": c.doc_id,
            "title": c.title,
            "source": c.source,
            "category": c.category,
            "chunk_index": c.chunk_index,
        }
        for c in chunks
    ]
    store.add(ids, embeddings, texts, metadatas)
    return ids, _doc_meta(chunks)


def build_doc_index(path: str, store, embedder, chunk_size=512, overlap=64):
    """单个文档 → 分块 → 嵌入 → 入库；返回 (chunk_ids, meta)。

    供上传 / 单文档重建复用；doc_id 稳定（md5(path)），store 为 upsert 语义，
    同名文档重复索引不会产生重复向量。
    """
    doc = load_document(path)
    chunks = split_document(doc, chunk_size, overlap)
    ids = [f"{c.doc_id}#chunk_{c.chunk_index:02d}" for c in chunks]
    texts = [c.text for c in chunks]
    embeddings = embedder.embed_documents(texts)
    metadatas = [
        {
            "doc_id": c.doc_id,
            "title": c.title,
            "source": c.source,
            "category": c.category,
            "chunk_index": c.chunk_index,
        }
        for c in chunks
    ]
    store.add(ids, embeddings, texts, metadatas)
    metas = _doc_meta(chunks)
    return ids, metas[0] if metas else None
