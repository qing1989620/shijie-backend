# FINAL REPORT · 最终报告（2026-09-05）

所有结论基于**真实执行结果**；未执行项如实标注 NOT RUN。

## 0. 工程约束验收（最高优先级）

| 项 | 结果 |
|---|---|
| WORKSPACE ROOT 仅 frontend/ + backend/ | **PASS**（`ls -A` 仅两目录） |
| 前端独立安装/构建（无父目录依赖） | **PASS**（npm ci 路径 + `npm run build`；业务代码零 `../` 逃逸） |
| 后端独立安装/测试（backend/.venv） | **PASS**（venv + requirements.lock + pytest） |
| 契约归属与同步 | **PASS**（backend/contracts/openapi.json 为源；前端快照 + 生成 client） |
| 运行时仅 REST + WebSocket | **PASS**（E2E 即跨进程 HTTP 通信，无共享文件/环境） |

## 1. 运行结果（真实执行）

```
Backend pytest:            37 passed, 0 failed
Backend ruff:              All checks passed
Frontend typecheck (strict, noImplicitAny): PASS, 0 errors
Frontend vitest:           5 passed, 0 failed
Frontend production build: PASS (built in ~2.2s)
Contract drift check:      PASS
Migration (empty DB → head): PASS
Playwright E2E (发布门禁):  1 passed（连续 2 次，11 张阶段截图）
WebSocket contract smoke:  PASS（ready→final→partial→error→closed，片段落库）
```

## 2. 模块状态

### Module 1 课堂 — **PASS**
课程/课堂 CRUD、音频上传（扩展名/大小校验）、finalize 最终校准转写（Mock ASR）、
转写分段存储 + 乐观并发编辑（409）、结构化课堂笔记（grounded：source_segment_ids + 时间戳跳转）、
知识点 canonical 化、**检索式找题**（本地 CC0 题库，检索不到如实提示）、收藏幂等进入题库。
实时转写：ticket + WS + 分片 + partial/final 信封（AsyncAPI 契约 + 冒烟 PASS）。

### Module 2 练习 — **PASS**
统一 Question 实体（UserQuestion 承载收藏/上传关系，无内容复制）、content_hash 去重、
OCR 预览→**人工校对**→确认入库、题目 AI 剖析→canonical 知识点树（core/prerequisite/method/extension）、
专项找题（basic/same_level/advanced）、随机/智能组题（顺序冻结）、Attempt（客观自动判定 / 主观强制自评）。

### Module 3 巩固 — **PASS（核心创新）**
**FSRS-4.5 MemoryEngine**（R/S/D 三变量 + 17 参数 + 行为→rating 映射 + r≤0.99 工程防护）；
每 (user, question) 独立 MemoryState（唯一约束 + 测试）；
**Review Planner**（记忆风险/薄弱/考试/重要度/逾期加权 + 每日时间装箱 + "为什么今天复习"文案）；
ReviewTask 全生命周期（scheduled/due/complete/snooze/skip≠答对/mastered=挂起不删）、
ReviewLog 审计、复习日历（真数据）、30 天记忆曲线（标注"估算"）、冷启动问卷（仅先验）。

## 3. 集成状态

| 集成 | 状态 |
|---|---|
| LLM (OpenRouter) | Mock **已测** / Real **NOT RUN**（无 Key；`LLM_PROVIDER=openrouter` 即切） |
| ASR (FunASR 自托管) | Mock **已测**（含 WS 实时契约）/ Real **NOT RUN**（Provider 客户端就绪） |
| OCR (PaddleOCR) | Mock **已测** / Real **NOT RUN** |
| 题源（LocalQuestionBank，自建 CC0 30 题） | **已测** |
| Storage (Local) | **已测**；S3/MinIO 生产位已预留 |

## 4. 安全

Argon2id；JWT access 30min + **旋转刷新**（重放阻断测试）；IDOR 作用域测试；
上传校验 + 路径遍历防护；错误统一信封（code 驱动，禁止文案判断）；CORS 精确域 + 最外层；
日志不含敏感值；录音采集用户主动可控并有合规提示。详见 docs/SECURITY.md。

## 5. 已知问题 / 边界（如实）

1. OpenRouter/FunASR/PaddleOCR 真实集成 **NOT RUN**（无 Key/运行时）——架构允许零代码切换。
2. Docker 镜像未实际构建（环境无 Docker）；compose/nginx/Dockerfile/CI 已提供。
3. 移动端做了布局适配（Sidebar→Topbar 导航），未逐视口截图复核。
4. 知识树当前为可交互缩进树（功能完整），React Flow 可视化列为升级项。
5. pytest 环境下 TestClient WebSocket 会挂起（环境门户问题），WS 契约改由
   `scripts/ws_smoke.py` 独立验证 **PASS**（已记录于 TEST_PLAN）。
6. 前端 bundle ~592KB（KaTeX 占比大），可按路由 code-split（非阻塞）。

## 6. 快速运行

```bash
# 后端
cd backend && python -m venv .venv && .venv/Scripts/pip install -r requirements.lock
cp .env.example .env && .venv/Scripts/alembic upgrade head && .venv/Scripts/python scripts/seed.py
.venv/Scripts/python -m uvicorn app.main:app --port 8000
# 前端
cd frontend && npm install && cp .env.example .env && npm run dev
# 演示账号 demo@shijie.app / demo12345 · E2E: npx playwright test
```
