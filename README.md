# 拾阶 · 后端（Shijie Backend）

智能学习闭环平台的后端服务：**课堂 → 练习 → 巩固** 完整数据链。

独立工程：可单独 clone / 单独部署，前端仅通过 REST + WebSocket 与本服务通信。

## 技术栈

FastAPI · SQLAlchemy 2 · Alembic · Pydantic v2 · JWT(access+rotating refresh) · Argon2id · SQLite(dev)/PostgreSQL(prod) · Provider 化的 LLM/ASR/OCR/Storage/题源

## 快速开始（本机开发）

```bash
cd backend

# 1) Python 环境（Windows）
python -m venv .venv
.venv\Scripts\pip install -r requirements.lock
# Linux/macOS:
# python3 -m venv .venv && .venv/bin/pip install -r requirements.lock

# 2) 环境变量
cp .env.example .env

# 3) 数据库迁移 + 种子数据（30 道自建 CC0 题目 + 演示用户）
.venv/Scripts/alembic upgrade head      # Linux: .venv/bin/alembic upgrade head
.venv/Scripts/python scripts/seed.py

# 4) 启动
.venv/Scripts/python -m uvicorn app.main:app --reload --port 8000
```

打开 <http://localhost:8000/docs> 查看 API；`demo@shijie.app / demo12345` 可直接登录。

## Docker 模式（PostgreSQL + Redis + MinIO + backend）

```bash
docker compose up -d
```

## 测试 / Lint / 契约

```bash
.venv/Scripts/python -m pytest tests/ -q          # 37 个集成+单元测试
.venv/Scripts/python -m ruff check app tests scripts
.venv/Scripts/python scripts/export_openapi.py    # 契约冻结 → contracts/openapi.json
```

## 目录

```
app/
├── api/v1/        # REST 路由（auth/course/lesson/recording/question/practice/review/...）
├── ai/            # MemoryEngine(FSRS-4.5) · ReviewPlanner · Agents · Prompts · 检索
├── providers/     # llm/asr/ocr/storage/exercise_source —— 全部 Provider 化
├── models/        # 30+ 张表（users/courses/lessons/questions/memory_states/...）
├── schemas/       # Pydantic 契约（OpenAPI 唯一来源）
├── services/      # 事务性业务（Attempt→Mastery→MemoryState→ReviewTask）
└── workers/       # 异步 Job 执行 + Transactional Outbox
contracts/         # openapi.json + asyncapi.yaml（机器契约）
docs/              # 产品/架构/数据库/AI/研究/测试/部署文档
```

## 前端

配套前端仓库见工作区 `frontend/`（或独立的 learning-platform-frontend 仓库），
通过 `VITE_API_BASE_URL` / `VITE_WS_BASE_URL` 指向本服务。
