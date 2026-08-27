"""端到端冒烟测试：无需模型 Key / chromadb，验证 FastAPI + RAG + 对话链路。

用法（在 crop-agent-server 目录）：
  uv run python scripts/smoke_test.py
或（未使用 uv 时，先 pip install -r requirements.txt 后）：
  python scripts/smoke_test.py
"""
import os
import sys

# Windows 控制台默认 GBK，无法打印部分 Unicode 字符（如 ⚠）→ 容错输出
if hasattr(sys.stdout, "reconfigure"):
    sys.stdout.reconfigure(encoding="utf-8", errors="replace")
    sys.stderr.reconfigure(encoding="utf-8", errors="replace")

# 将 server 根目录加入 sys.path，保证 `import main` 与 `from config import ...` 可用
_SERVER_ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, _SERVER_ROOT)

# 必须在导入 main 之前设置环境（使用内存 SQLite，避免依赖文件系统）
os.environ["DB_URL"] = "sqlite:///:memory:"
os.environ["VECTOR_PERSIST_DIR"] = "./storage/smoke_chroma"
os.environ["REINDEX"] = "true"

# 知识库使用临时副本：管理类端点（删除/重建）会改文件，不能动真实 knowledge/
import shutil  # noqa: E402

_SMOKE_KB = os.path.abspath("./storage/smoke_knowledge")
if os.path.isdir(_SMOKE_KB):
    shutil.rmtree(_SMOKE_KB, ignore_errors=True)
shutil.copytree(os.path.abspath("../knowledge"), _SMOKE_KB)
os.environ["KNOWLEDGE_DIR"] = _SMOKE_KB

from fastapi.testclient import TestClient  # noqa: E402

import main  # noqa: E402


def check(name, cond, extra=""):
    print(f"[{'PASS' if cond else 'FAIL'}] {name} {extra}")
    return bool(cond)


ok = True
with TestClient(main.app) as client:
    r = client.get("/health")
    ok &= check("GET /health", r.status_code == 200, str(r.json()))

    r = client.post("/api/chat", json={"content": "水稻稻瘟病怎么防治？"})
    ok &= check(
        "POST /api/chat",
        r.status_code == 200 and r.json().get("code") == 200,
    )
    data = r.json()
    reply = data.get("data", {}).get("reply", "")
    sources = data.get("sources", [])
    print("  reply head:", reply[:80].replace("\n", " "))
    print("  sources:", [(s["chunk"], s["score"]) for s in sources])
    ok &= check("  检索命中来源", len(sources) >= 1)

    r = client.get("/api/knowledge/search", params={"q": "番茄早疫病"})
    ok &= check(
        "GET /api/knowledge/search",
        r.status_code == 200,
    )
    data = r.json().get("data", {})
    print("  results:", len(data.get("results", [])))

    # ---- 知识库界面优化：文档级合并 / 阈值 meta / 分类过滤 ----
    results = data.get("results", [])
    ok &= check(
        "  搜索结果按文档合并（含 chunks 数组）",
        all("chunks" in d and isinstance(d["chunks"], list) for d in results),
        repr([(d["doc_id"], len(d.get("chunks", []))) for d in results]),
    )
    meta = data.get("meta", {})
    ok &= check(
        "  返回有效阈值 meta",
        isinstance(meta.get("threshold"), float),
        repr(meta),
    )
    ok &= check(
        "  空查询返回空数组",
        client.get("/api/knowledge/search", params={"q": ""}).json()["data"]["results"]
        == [],
    )
    r = client.get("/api/knowledge/search", params={"q": "种植", "category": "diseases"})
    ok &= check(
        "  分类过滤生效",
        all(d["category"] == "diseases" for d in r.json()["data"]["results"]),
    )

    r = client.get("/api/knowledge")
    docs = r.json()["data"]["docs"]
    ok &= check("GET /api/knowledge 含新字段", bool(docs) and all(
        k in docs[0] for k in ("status", "category", "file_size", "updated_at", "file_name")
    ), repr(docs[0]) if docs else "empty")
    ok &= check("  列表 meta 含阈值", "threshold" in r.json()["data"]["meta"])

    # 文档管理：chunks / content / reindex / delete / batch / chunk 删除
    if docs:
        doc_id = docs[0]["doc_id"]
        r = client.get(f"/api/knowledge/{doc_id}/chunks")
        chunk_list = r.json()["data"]["chunks"]
        ok &= check(
            "GET /{id}/chunks",
            r.status_code == 200 and len(chunk_list) >= 1 and "char_count" in chunk_list[0],
        )
        r = client.get(f"/api/knowledge/{doc_id}/content")
        ok &= check(
            "GET /{id}/content 原文预览",
            r.status_code == 200 and len(r.json()["data"]["content"]) > 0,
        )
        r = client.post(f"/api/knowledge/{doc_id}/reindex")
        ok &= check(
            "POST /{id}/reindex 单文档重建",
            r.json().get("code") == 200 and r.json()["data"]["chunk_count"] >= 1,
            repr(r.json()),
        )
        if len(chunk_list) > 1:
            cid = chunk_list[0]["chunk_id"]
            r = client.delete(f"/api/knowledge/chunks/{cid}")
            ok &= check(
                "DELETE /chunks/{id} 片段删除",
                r.json().get("code") == 200,
                repr(r.json()),
            )
            # 补回：重建索引恢复完整片段
            client.post(f"/api/knowledge/{doc_id}/reindex")
        elif chunk_list:
            cid = chunk_list[0]["chunk_id"]
            r = client.delete(f"/api/knowledge/chunks/{cid}")
            ok &= check(
                "  末个片段拒绝删除",
                r.json().get("code") == 400,
                repr(r.json()),
            )

        r = client.post("/api/knowledge/batch-reindex", json={"doc_ids": [doc_id]})
        ok &= check(
            "POST /batch-reindex",
            r.json().get("code") == 200 and r.json()["data"]["count"] == 1,
            repr(r.json()),
        )
        # 批量删除 + 单条删除（重建索引保证批量删除前文件存在）
        r = client.post("/api/knowledge/batch-delete", json={"doc_ids": [doc_id]})
        ok &= check(
            "POST /batch-delete",
            r.json().get("code") == 200 and r.json()["data"]["count"] == 1,
            repr(r.json()),
        )
        remain = [d["doc_id"] for d in client.get("/api/knowledge").json()["data"]["docs"]]
        ok &= check("  批量删除后列表不含", doc_id not in remain)
        r = client.delete(f"/api/knowledge/{doc_id}")
        ok &= check(
            "  已删除文档再删返回 404",
            r.json().get("code") == 404,
            repr(r.json()),
        )

        # 上传链路：新建临时文档 → 上传 → 列表出现 → 清理
        tmp_path = os.path.join(_SMOKE_KB, "冒烟测试临时文档.md")
        with open(tmp_path, "w", encoding="utf-8") as f:
            f.write("# 冒烟测试临时文档\n\n这是一份用于验证上传与单文档索引链路的文档。\n" * 5)
        with open(tmp_path, "rb") as f:
            r = client.post(
                "/api/knowledge/upload",
                files={"file": ("冒烟测试临时文档.md", f, "text/markdown")},
            )
        up_data = r.json()
        ok &= check(
            "POST /api/knowledge/upload",
            up_data.get("code") == 200 and up_data["data"].get("doc_id"),
            repr(up_data),
        )
        up_id = up_data["data"]["doc_id"]
        now_ids = [d["doc_id"] for d in client.get("/api/knowledge").json()["data"]["docs"]]
        ok &= check("  上传后列表包含新文档", up_id in now_ids)
        r = client.delete(f"/api/knowledge/{up_id}")
        ok &= check(
            "  上传文档可删除",
            r.json().get("code") == 200,
            repr(r.json()),
        )
        if os.path.isfile(tmp_path):
            os.remove(tmp_path)

    r = client.get("/api/sessions")
    sessions = r.json()["data"]["sessions"]
    ok &= check(
        "GET /api/sessions",
        r.status_code == 200 and len(sessions) >= 1,
    )
    ok &= check(
        "  会话标题取首轮提问",
        bool(sessions) and sessions[0]["title"].startswith("水稻稻瘟病"),
        repr(sessions[0]["title"] if sessions else None),
    )

    sid = sessions[0]["session_id"] if sessions else ""

    # ---- 会话管理新能力：重命名 / 置顶 / 批量删除 ----
    r = client.patch(f"/api/sessions/{sid}", json={"title": "重命名后的对话"})
    ok &= check(
        "PATCH /api/sessions/{id} 重命名",
        r.status_code == 200 and r.json()["data"]["title"] == "重命名后的对话",
        repr(r.json()),
    )

    r = client.patch(f"/api/sessions/{sid}", json={"pinned": True})
    ok &= check(
        "PATCH /api/sessions/{id} 置顶",
        r.status_code == 200 and r.json()["data"]["pinned"] is True,
    )
    r = client.get("/api/sessions")
    top = r.json()["data"]["sessions"][0]
    ok &= check(
        "  置顶会话排最前",
        top["session_id"] == sid and top["pinned"] is True,
        repr(top),
    )
    r = client.patch(f"/api/sessions/{sid}", json={"pinned": False})
    ok &= check("  取消置顶", r.json()["data"]["pinned"] is False)

    r = client.patch(f"/api/sessions/{sid}", json={"title": "   "})
    ok &= check(
        "  空标题被拒绝",
        r.json().get("code") == 400,
        repr(r.json()),
    )

    # 批量删除：新建 2 个会话后一次性删除
    batch_ids = []
    for _ in range(2):
        r = client.post("/api/sessions")
        batch_ids.append(r.json()["data"]["session_id"])
    r = client.post("/api/sessions/batch-delete", json={"session_ids": batch_ids})
    ok &= check(
        "POST /api/sessions/batch-delete",
        r.status_code == 200 and r.json()["data"]["count"] == 2,
        repr(r.json()),
    )
    r = client.get("/api/sessions")
    remain = [s["session_id"] for s in r.json()["data"]["sessions"]]
    ok &= check(
        "  批量删除后列表不含",
        all(i not in remain for i in batch_ids),
        repr(remain),
    )

    r = client.delete(f"/api/sessions/{sid}")
    ok &= check(
        "DELETE /api/sessions/{id}",
        r.status_code == 200 and r.json()["data"]["deleted"] == sid,
    )
    r = client.get("/api/chat/history", params={"session_id": sid})
    msgs = r.json()["data"]["messages"] if r.status_code == 200 else None
    ok &= check(
        "  删除后消息清空",
        msgs == [],
        repr(msgs),
    )

print("\nSMOKE", "PASS" if ok else "FAIL")
sys.exit(0 if ok else 1)
