# PROGRESS · 进度看板（2026-09-05）

| 阶段 | 状态 | 验证证据 |
|---|---|---|
| 0 工作区纠正（仅 frontend/ + backend/，两独立工程） | DONE | `ls -A` 仅两目录；无跨仓库依赖（grep 审计） |
| 1 环境引导 | DONE | backend/.venv (Python 3.13.14) + requirements.lock；frontend npm + package-lock；ENVIRONMENT.md |
| 2 技术调研 | DONE | docs/research/TECH_RESEARCH.md（ASR/FSRS/LLM/检索/OCR，含来源与结论） |
| 3 产品与架构 | DONE | PRODUCT_SPEC / ARCHITECTURE / ERD / AI_ARCHITECTURE / REVIEW_ALGORITHM / ADR-INDEX |
| 4 契约冻结 | DONE | contracts/openapi.json + asyncapi.yaml；drift check PASS；前端 client 自动生成 |
| 5 Core（Auth/Courses/Storage/Jobs/Observability） | DONE | pytest test_auth/test_permissions 全绿；Argon2id + 旋转 refresh |
| 6 Module 1 课堂 | DONE | 录音→转写→笔记(grounded)→找题→收藏 全链路：pytest test_module1 + E2E 截图 03/04 |
| 7 Module 2 练习 | DONE | 统一题库/OCR 预览校对/知识树/专项找题/组题/Attempt：pytest test_module2 + E2E 截图 05–08 |
| 8 Module 3 巩固 | DONE | FSRS MemoryEngine + Planner + ReviewTask/日历/曲线：pytest test_module3 + E2E 截图 09–11 |
| 9 Full Loop E2E（发布门禁） | DONE | frontend/e2e/full-loop.spec.ts PASS（连续 2 次）；WS 冒烟 PASS |
| 10 UI Polish | PARTIAL | 1440 视口全页截图检查通过；390/768 布局已适配（Topbar 导航）但未逐视口截图复核 |
| 11 Production Readiness | DONE | lint/typecheck/test/build/contract/migration 全 PASS；Docker/Compose/nginx/CI 文件就绪（未实际 docker build：环境无 Docker） |

## 如实声明（NOT RUN / NOT IMPLEMENTED）

- OpenRouter 真实调用：**NOT RUN**（无 Key；MockLLMProvider 承担，填 Key 即切换）
- FunASR / PaddleOCR 真实运行时：**NOT RUN**（Provider 客户端已实现，部署位 infra/asr）
- Docker 镜像构建：**NOT RUN**（本机无 Docker；docker-compose.yml 已提供）
- xyflow/React Flow 知识树可视化：**NOT IMPLEMENTED**（当前为可交互缩进树 + 详情面板，满足功能；可视化升级见 ADR-001）
- 移动端逐视口截图 QA：**PARTIAL**
