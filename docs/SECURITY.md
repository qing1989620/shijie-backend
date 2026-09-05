# 安全与隐私 · SECURITY

## 认证与会话

- 密码：**Argon2id**（argon2-cffi 默认参数）；禁用 MD5/裸 SHA。
- Access token 30 分钟（HS256）；Refresh token 14 天、**旋转 + 可撤销**：
  刷新即吊销旧 jti，重放旧 token 返回 401（有测试）；改密撤销全部会话。
- 开发模式 token 在 localStorage；生产应迁移 HttpOnly Cookie（见前端 API_INTEGRATION）。
- WS 握手：一次性 ticket（POST /realtime/tickets 需 Bearer），5 分钟内有效、用后即焚。

## 授权 / IDOR

所有私有资源查询强制 `user_id` 作用域（Repository 层 `owner_or_404`）；
tests/test_permissions.py 验证跨用户访问返回 404（不泄露存在性）。

## 输入与文件

- 上传：扩展名白名单 + 大小上限（音频 200MB / 图片 20MB）；对象 Key 服务端随机生成，
  `LocalStorageProvider._resolve` 显式阻断路径遍历；用户文件名仅作 display_name。
- 主观题不可伪造判定：无标准答案时必须 `is_correct + grading_source=self`（否则 422）。

## 注入 / 注入面

- SQLAlchemy 全参数化；无字符串拼 SQL。
- 转写/上传内容视为不可信输入：Agent 工具白名单 + 输出 Schema 双重围栏，Prompt Injection 无法转化为系统副作用。

## CORS / CSRF

`CORS_ORIGINS` 环境变量精确列举，禁止生产 `*` + credentials 组合；
token 走 Authorization 头（天然免疫经典 CSRF）；Cookie 模式启用时需 SameSite 方案配合。

## 日志

结构化访问日志（method/path/status/latency/request_id）；**不记录**密码、token、API key、录音内容。

## 隐私

- 录音仅在用户主动开始/结束的会话中采集，UI 全程显示录音状态与用途提示。
- 发往外部的 AI 内容（课堂转写片段、题干）与目的（OpenRouter/自托管）在架构上可整体切换
  （Provider 化）；删除课堂走软删 + worker 硬删音频/转写/索引。

## Rate Limit / 暴力破解

登录接口按 IP+账号限流为生产增强项（当前阶段以 Argon2 成本因子 + 会话轮换缓解，
部署层可用 Nginx limit_req）。
