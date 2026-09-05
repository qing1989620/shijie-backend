# 部署 · DEPLOYMENT

## 形态 A：Docker Compose（backend/ 自带）

```bash
cd backend
docker compose up -d        # postgres + redis + minio + backend(自动迁移)
```

- backend 容器内启动前执行 `alembic upgrade head`。
- ASR 运行时（可选 profile）：`infra/asr/`，模型缓存卷 `asrmodels` 避免重启重复下载；
  模型体积与磁盘要求见该目录 README（Paraformer-zh ~1GB 级，SenseVoice-Small ~500MB 级）。
- 前端独立部署（frontend/Dockerfile 或任意静态托管），`VITE_API_BASE_URL` 指向本机/域名 API。

## 形态 B：云服务器手工部署（生产建议）

```
Browser ──HTTPS──► Nginx ──► 静态前端 dist/
              └──► Nginx ──► uvicorn(backend, 多 worker) ──► PostgreSQL / Redis / MinIO / ASR runtime
```

要点：
1. **HTTPS 必须**（浏览器麦克风权限要求；WS 走 wss）。
2. 反代 WS：`Upgrade/Connection` 头透传。
3. 环境：`backend/.env` 中 `JWT_SECRET` 换 64 位随机串、`CORS_ORIGINS` 精确域、`DATABASE_URL` 切 PG、`STORAGE_PROVIDER=s3`。
4. 迁移：发布流程第一步 `alembic upgrade head`（原子、可回滚脚本化）。
5. 备份：PG 定时 dump + MinIO/对象存储桶生命周期；录音属高敏感数据，保留策略需与用户协议一致。
6. 健康检查：`/health`（进程）与 `/ready`（依赖）分离——OpenRouter 抖动不应让 LB 摘除后端。
7. Worker：生产把 `workers/runner.run_job_async` 替换为 Dramatiq/Celery worker（函数签名一致），Redis 作 broker。

## 前端（见 frontend/docs/DEPLOYMENT.md）

静态托管 + SPA 回退；构建期注入 `VITE_API_BASE_URL / VITE_WS_BASE_URL`。
