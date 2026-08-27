# 🌾 禾知 · 农作物多模态 RAG Agent

> 智慧农业 × AI Agent —— 一个可运行的「农作物识别 / 种植指导 / 病虫害诊断 / 知识问答」全栈项目。
>
> 依据 `农作物多模态RAG_Agent_全局提示词.md`（架构）与 `农作物Agent项目-UI设计风格规范.md`（视觉）构建。

## 一、项目结构

```
crop-agent/
├── crop-agent-web/          # 前端（Vue 3 + Element Plus + Vite + TS）
│   └── src/
│       ├── views/           # ChatView / KnowledgeBase / HistoryView
│       ├── components/      # MessageBubble / ImageUploader / SourceTag / StreamText
│       ├── composables/     # useChat / useWebSocket
│       ├── api/  router/  styles/  types/  utils/
│       └── main.ts / App.vue
├── crop-agent-server/       # 后端（FastAPI + LangChain + LlamaIndex + ChromaDB + SQLite）
│   ├── main.py              # 入口
│   ├── config.py            # 环境配置（.env）
│   ├── agent/               # crop_agent 编排 / tools / prompts
│   ├── rag/                 # indexer / retriever / vector_store / embeddings
│   ├── multimodal/          # image_analyzer / crop_classifier
│   ├── services/            # llm / answer_engine / image_util
│   ├── db/                  # models / database / schemas
│   └── api/                 # chat / knowledge / ws
├── knowledge/               # 原始知识文档（Markdown，可随时扩充）
│   ├── crops/  diseases/  techniques/
├── 农作物Agent项目-UI设计风格规范.md
├── 农作物多模态RAG_Agent_全局提示词.md
└── README.md
```

## 二、核心特性

- **多模态对话**：文本 + 图片（JPG/PNG/WebP ≤10MB，前端压缩至 1024px）。
- **RAG 检索**：LlamaIndex 分块思路 + ChromaDB（cosine），先召回（recall_k=20）再按有效阈值过滤（本地哈希嵌入 0.15 / 语义嵌入 0.65），查询词与标题/分类重叠轻量加权；命中片段标注来源。
- **Agent 编排**：意图路由（知识问答 / 病虫害 / 气候 / 行情 / 对比）→ 工具调用 → 生成回答。
- **流式输出**：WebSocket `/ws/chat/stream` 逐块推送，前端打字机渲染。
- **会话管理**：SQLite 存储 users / sessions / messages / favorites / knowledge_meta；前端 Pinia 全局状态保证多会话上下文隔离。
- **零 Key 可跑**：未配置模型 Key 时自动降级为「本地哈希嵌入 + 离线模板回答引擎」，开箱即用。
- **前端交互**：侧边栏收起/展开（localStorage 持久化）、新建对话、删除会话（二次确认）、历史列表（相对时间/高亮/空态）、移动端汉堡菜单抽屉。

## 三、运行环境

| 组件 | 版本要求 | 说明 |
|------|---------|------|
| Node.js | ≥ 18 | 前端运行（Vite 6 要求） |
| pnpm | ≥ 10 | 前端包管理；`pnpm approve-builds` 为 pnpm 10+ 命令 |
| Python | ≥ 3.12 | 后端运行 |
| uv | 最新即可 | 后端包管理，自动创建 .venv 并生成 uv.lock |
| 模型 API Key（可选） | DeepSeek / MIMO / OpenAI | 未配置时自动降级为离线模式 |

## 四、快速开始

### 1. 后端（Python 3.12+，uv 管理）

```bash
cd crop-agent-server

# 首次安装：自动创建 .venv、选用 Python 3.12、生成 uv.lock
uv sync

# （可选）激活虚拟环境；不激活也可以，uv run 会自动使用 .venv
# Windows (cmd / PowerShell): .venv\Scripts\activate
# Git Bash / macOS / Linux:   source .venv/Scripts/activate

# 复制并填写配置（可选，缺省也能跑）
copy .env.example .env      # Linux/macOS: cp .env.example .env

# 启动后端
uv run uvicorn main:app --reload --port 8000
```

接入真实模型 / 本地图片分析时，安装对应的可选依赖组（可选，不装也能演示）：

```bash
uv sync --extra deepseek --extra mimo --extra image
# 或一次性安装全部可选组：uv sync --all-extras
```

冒烟测试：

```bash
uv run python scripts/smoke_test.py     # 期望输出 SMOKE PASS
```

> 不使用 uv 的兼容方式：`pip install -r requirements.txt` 仍可用（仅核心依赖；可选组定义在 `pyproject.toml` 的 `[project.optional-dependencies]`）。

启动后：

- 首次启动自动索引 `knowledge/` 目录并建表。
- 健康检查：http://127.0.0.1:8000/health
- 接口文档：http://127.0.0.1:8000/docs

### 2. 前端（Node 18+ / pnpm 10+）

```bash
cd crop-agent-web
pnpm install
npm run dev
```

> 若 `pnpm install` 提示 `Ignored build scripts` 警告（pnpm 10+ 出于安全默认拦截依赖的安装后脚本），运行 `pnpm approve-builds` 交互式信任 `esbuild`、`vue-demi`，然后重新 `pnpm install` 即可完成安装；`@parcel/watcher` 已在 `pnpm-workspace.yaml` 中显式禁用，无需批准。

访问 http://127.0.0.1:5173 。Vite 已把 `/api`、`/ws` 代理到 `127.0.0.1:8000`。

### 3. 接入真实模型（可选）

在 `crop-agent-server/.env` 中配置：

| 变量 | 说明 |
|------|------|
| `DEEPSEEK_API_KEY` / `DEEPSEEK_MODEL` | 文本生成（目标模型 deepseek-v4-flash，端点走 DeepSeek OpenAI 兼容协议） |
| `MIMO_API_KEY` / `MIMO_BASE_URL` / `MIMO_MODEL` | 多模态识别（mimo-2.5） |
| `EMBEDDING_PROVIDER=openai` + `OPENAI_API_KEY` | 远端语义嵌入（缺省为本地哈希嵌入） |

未配置时：文本生成降级为本地模板引擎、图片识别返回友好提示、嵌入用本地哈希 —— 全流程依然可演示。

## 五、API 契约（前后端）

| 方法 | 路径 | 说明 |
|------|------|------|
| POST | `/api/chat` | 文本对话 |
| POST | `/api/chat/multimodal` | 文本 + 图片 + 文件（`files: [{name,mime,data(base64)}]`）对话 |
| GET | `/api/chat/history?session_id=` | 历史消息 |
| GET | `/api/sessions` | 会话列表（含 `group_id`）+ 分区列表 `groups` |
| POST | `/api/sessions` | 新建会话（标题先为"新对话"，首轮对话后自动更新为提问前几个字） |
| PATCH | `/api/sessions/{session_id}` | 重命名 / 置顶 |
| DELETE | `/api/sessions/{session_id}` | 删除会话及其全部消息 |
| POST | `/api/sessions/batch-delete` | 批量删除会话 |
| POST | `/api/sessions/assign-group` | 批量把会话移入/移出分区（`group_id: null` 即移出） |
| GET | `/api/groups` | 分区列表 |
| POST | `/api/groups` | 新建分区 |
| PATCH | `/api/groups/{group_id}` | 重命名分区 |
| DELETE | `/api/groups/{group_id}` | 删除分区（分区内会话释放回日期区） |
| POST | `/api/groups/batch-delete` | 批量删除分区 |
| GET | `/api/knowledge/search?q=&category=` | 文档级检索（同一文档多片段已合并，返回 `chunks` 数组 + `meta.threshold` 有效阈值） |
| GET | `/api/knowledge` | 知识库文档元信息（含 status / category / file_size / updated_at）+ `meta` |
| POST | `/api/knowledge/upload` | 上传 .md/.txt 并索引该文档（返回 `doc_id`） |
| GET | `/api/knowledge/{doc_id}/chunks` | 文档片段明细（drawer 展示） |
| GET | `/api/knowledge/{doc_id}/content` | 文档原始 Markdown 内容（预览） |
| DELETE | `/api/knowledge/{doc_id}` | 删除文档（向量 + 文件 + 元信息） |
| POST | `/api/knowledge/{doc_id}/reindex` | 单文档重建索引（失败置 status=failed） |
| POST | `/api/knowledge/batch-delete` | 批量删除文档 |
| POST | `/api/knowledge/batch-reindex` | 批量重建索引 |
| DELETE | `/api/knowledge/chunks/{chunk_id}` | 删除单个片段（末个片段拒绝删除） |
| WS | `/ws/chat/stream` | 流式接收 LLM 回复（payload 支持 `images` 与 `files`） |

统一响应：

```json
{
  "code": 200,
  "data": { "reply": "...", "session_id": "..." },
  "sources": [{ "doc_id": "K0231AB", "chunk": "K0231AB#chunk_01", "score": 0.87 }],
  "message": "success"
}
```

## 六、扩展知识库

直接向 `knowledge/` 添加 Markdown 文档（按 `crops / diseases / techniques` 分类），然后：

- 重启后端（启动时若向量库为空会自动索引）；
- 或设置 `REINDEX=true` 强制重建；
- 或通过「知识库」页面 / `POST /api/knowledge/upload` 上传。

## 七、数据库迁移路径

```
SQLite（开发/MVP）
   └─ 修改 db/database.py 连接串 + alembic 迁移
      └─ PostgreSQL / MySQL（生产）
         └─ 向量库独立部署 → Milvus / Weaviate（大规模检索）
```

业务代码经 SQLAlchemy ORM 抽象，迁移时仅改连接串与 dialect。

## 八、安全与边界（已内置）

- 不编造检索依据；未命中时诚实说明并标注「⚠️ 非知识库内容」。
- 病虫害诊断仅供参考，提示咨询农技部门。
- 不推荐农药品牌（只讲有效成分）、不涉及转基因价值判断、不做无关闲聊。
- 用药与大面积种植决策附「仅供参考，请结合当地实际」。

## 九、UI 规范落地

品牌色田野绿 `#3D8B37`、麦穗金 `#E8B930`、土壤棕 `#8B6F47`、天空蓝 `#4A9BD5`；卡片圆角 16px、按钮胶囊形；思考中三颗绿点呼吸动画、数据加载“生长”进度条；响应式：桌面侧栏 / 平板图标栏 / 手机底部 Tab。详见 `src/styles/index.css` 与各组件。
