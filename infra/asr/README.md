# ASR Runtime（FunASR · 自托管）

部署一个 OpenAI 兼容转写服务（POST /v1/audio/transcriptions、GET /health），
backend 通过 `ASR_PROVIDER=funasr` + `ASR_BASE_URL` 接入。

推荐镜像基础：`modelscope-registry.cn-hangzhou.cr.aliyuncs.com/.../funasr` 或自建
`FROM python:3.10-slim && pip install funasr modelscope torch --index-url ...`。
启动示例（funasr_wss_server / 官方 funasr-onnx http server 均可），关键点：

- 模型缓存目录挂载为卷（docker-compose: `asrmodels:/root/.cache`），避免重启重下；
- 模型：`paraformer-zh`（流式可加 `paraformer-zh-streaming`），VAD/标点模型可选；
- 磁盘：paraformer-zh ≈ 1GB，SenseVoice-Small ≈ 500MB（按需二选一）；
- License：代码 MIT；模型遵 ModelScope 官方协议，商用部署前请复核。
