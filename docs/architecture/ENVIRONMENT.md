# 环境清单 · ENVIRONMENT（实测于 2026-09-05）

| 项 | 值 | 备注 |
|---|---|---|
| OS | Windows 11（Git Bash / PowerShell） | 路径含中文——openapi-typescript 需 ASCII 临时目录中转（已在生成脚本处理） |
| Python（backend/.venv） | 3.13.14 | `python -m venv`；机器无 uv，故未用 uv sync，锁定用 `requirements.lock`（pip freeze） |
| uv | 未安装 | 安装后可无缝切换：`uv venv .venv && uv pip install -r requirements.lock` |
| Node | 22.22.2（managed） | 前端 `.node-version`=22.22.2 |
| 包管理（前端） | npm 10.9.7（pnpm 未装） | 唯一 lockfile：package-lock.json |
| Docker | 未安装 | 本地以直连模式开发；`backend/docker-compose.yml` 提供 PG+Redis+MinIO+backend 全量编排 |
| PostgreSQL | 未本地安装（dev 用 SQLite） | 生产 DATABASE_URL 切换即可，迁移已用 render_as_batch 兼容 |
| GPU / CUDA | 无 | AI 全部 Provider 化 + Mock；ASR/OCR 模型运行时按 ADR-005 外置部署 |
| OPENROUTER_API_KEY | 未提供 | MockLLMProvider 承担（确定性），**真实 LLM 未验证** |

## 验证记录

```
backend/.venv/Scripts/python.exe --version   → Python 3.13.14
.venv/Scripts/python -m pytest tests/ -q     → 37 passed
.venv/Scripts/python -m ruff check ...       → All checks passed
node --version                               → v22.22.2
npm run build（frontend）                    → built in 2.48s
alembic upgrade head（空库）                  → OK（含 downgrade 链生成）
```
