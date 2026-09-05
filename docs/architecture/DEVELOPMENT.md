# 开发手册 · DEVELOPMENT

## 日常命令（backend/ 下）

```bash
.venv/Scripts/python -m uvicorn app.main:app --reload   # 启动（Linux: .venv/bin/…）
.venv/Scripts/python -m pytest tests/ -q                # 测试
.venv/Scripts/python -m ruff check app tests scripts    # lint
.venv/Scripts/python scripts/seed.py                    # 种子（幂等）
.venv/Scripts/python scripts/export_openapi.py          # 契约冻结
.venv/Scripts/alembic upgrade head                      # 迁移
.venv/Scripts/alembic revision --autogenerate -m "..."  # 生成迁移
```

## 如何加一个 API

1. `app/schemas/schemas.py`：定义 Request/Response Pydantic 模型（契约源头）。
2. `app/api/v1/<module>.py`：路由 + `operation_id`（稳定、唯一——前端生成 client 依赖它）。
3. `app/main.py`：include_router（如新建 router）。
4. 权限：私有资源查询必须带 `user_id`（或 `owner_or_404`）。
5. 写测试（`tests/`）；跑 `export_openapi.py` 冻结契约；前端 `npm run api:generate`。

## 如何加一个迁移

改 `app/models/` → `alembic revision --autogenerate -m "..."` → 检查生成文件
（SQLite 注意 batch 操作）→ `alembic upgrade head` → 空库升级验证。

## 如何加一个 Agent / Prompt

1. `app/ai/prompts/registry.py`：新增 `<name>_v<N>`（name、version、system、output_schema）。
2. `app/providers/llm/mock_handlers.py`：注册同名确定性 handler（只整形、不虚构）。
3. `app/ai/agents/agents.py`：新建 Agent 类，声明 `prompt_key` 与**工具白名单**注释；
   输出过 Schema 后由 Service 落库；`_log_run` 审计。

## 如何加一个 Provider

在 `app/providers/<kind>/` 定义协议实现（参考 `asr/provider.py`），
工厂函数按 `settings.<KIND>_PROVIDER` 切换；核心业务永不 import 具体厂商 SDK。

## 如何运行 E2E

```bash
# 终端1 backend: uvicorn app.main:app --port 8000
# 终端2 frontend: npm run dev
cd frontend && npx playwright test
```
