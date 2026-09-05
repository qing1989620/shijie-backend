# ADR 索引

格式：Context / Options / Decision / Consequences。日期：2026-09-05。

## ADR-001 前端栈 — React 18 + Vite 5 + TS strict + Tailwind 4 + TanStack Query
- Options: Vue3+Vite / Next.js / React+Vite
- Decision: React+Vite SPA。学习平台是重交互工具而非内容站，无需 SSR/SEO。
- Consequences: 产物纯静态，部署面广；bundle 中 KaTeX 较大（~590KB min，182KB gzip），可后续 code-split。

## ADR-002 后端栈 — FastAPI + SQLAlchemy 2 + Pydantic v2（Python 3.13 dev）
- Options: FastAPI / Django REST / Flask
- Decision: FastAPI。原生 OpenAPI 支撑 Contract First；Pydantic 复用为 AI 结构化输出校验。
- Consequences: 需要自建 worker/迁移等配套（已含）。

## ADR-003 API 契约 — OpenAPI 3.1 唯一事实源 + openapi-typescript 生成
- Options: Orval / openapi-typescript+openapi-fetch / 手写 client
- Decision: openapi-typescript 生成 paths 类型，openapi-fetch 消费。轻、零运行时开销、类型全量。
- Consequences: 契约快照去 `/api/v1` 前缀后生成（redocly 不支持非 ASCII 路径，经 ASCII 临时目录中转）。

## ADR-004 数据库 — SQLite(dev) / PostgreSQL+pgvector(prod)，UTCDateTime TypeDecorator
- Options: 起步就用 PG / 仅 SQLite / 双轨
- Decision: 双轨。SQLite 让本地/CI 零依赖；生产 DDL 走同一套 Alembic。时间统一 UTCDateTime（naive-UTC 存储，tz-aware 读取）。
- Consequences: SQLite 无 `ALTER` 便利（迁移用 render_as_batch）与并发写限制，生产切 PG。

## ADR-005 ASR — Provider 化，Mock + FunASR 自托管（OpenAI 兼容 /v1/audio/transcriptions）
- Options: 云 ASR 免费层 / 自托管 FunASR(SenseVoice-小/Paraformer) / Whisper.cpp
- Decision: 不依赖任何"永久免费"商业 API；`FunASRProvider` 指向自托管运行时（`infra/asr/`，模型缓存卷持久化，镜像/模型清单在该目录 README）。中文课堂 + 中英混合场景 FunASR 中文准确率与热词支持最优；License（MIT/模型协议）允许商用部署。
- Consequences: 自托管需 GPU/CPU 资源；开发与 CI 用 MockASR（确定性课堂脚本），实时 partial/final 行为一致。

## ADR-006 LLM — OpenRouter Provider（模型可配置）+ MockLLM
- Decision: 不写死任何 :free 模型；`LLM_DEFAULT_MODEL`/`LLM_FALLBACK_MODELS` 配置化，无 Key 自动 Mock。结构化输出必须过 Pydantic。
- Consequences: 免费模型变动只改配置；CI 不烧真实额度。

## ADR-007 RAG — 词法检索起步（CJK bigram 余弦），pgvector+BGE-M3 为生产升级路径
- Options: 一开始上 LangChain 全家桶 / 轻量词法 / 直接 pgvector
- Decision: 轻量词法（零模型依赖、中文友好、可测试），接口保留 embedding 槽位；检索权限过滤在 SQL 层。
- Consequences: 长尾语义查询弱于向量方案——列入升级路径而非本阶段阻塞。

## ADR-008 后台任务 — 开发线程 Worker + Transactional Outbox；生产换 Dramatiq/Celery
- Options: Celery 全家桶 / FastAPI BackgroundTasks / 线程 worker
- Decision: `workers/runner.py` 线程执行 AI Job（独立 Session），`outbox_events` 保证"事务成功但异步副作用不丢"；Job 状态/进度/阶段落库供前端展示。函数签名与队列 worker 兼容，迁移成本低。
- Consequences: 单进程吞吐有限——当前规模足够，生产切 Redis+Dramatiq 只改 runner。

## ADR-009 巩固算法 — FSRS-4.5 基线 + Product Heuristic Planner（详见 REVIEW_ALGORITHM.md）
- Options: SM-2 / 固定间隔表 / FSRS
- Decision: FSRS-4.5（开源、有论文、参数默认即可用），科学层与产品层代码/文档分离，scheduler_version 可追溯。

## ADR-010 存储 — LocalStorage(dev) / S3 兼容(prod，MinIO)
- Decision: `StorageProvider` 协议；对象 Key 服务端生成（用户文件名只作 display_name），路径遍历防护内置。

## ADR-011 前后端物理独立（最高优先级约束）
- Decision: 两个独立工程、独立 Git/CI/部署；根目录只保留 frontend/、backend/；运行时仅 REST+WS 通信。
- Consequences: 契约经快照同步；E2E 把后端当外部 HTTP 服务。
