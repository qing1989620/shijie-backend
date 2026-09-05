# 技术调研 · TECH_RESEARCH（调研日期：2026-09-05）

来源优先级：官方文档 > 官方 GitHub > 论文 > 工程博客。结论已写入对应 ADR。

## 1. 自托管中文 ASR（ADR-005）

| 方案 | 中文课堂准确率 | Streaming | 部署 | License |
|---|---|---|---|---|
| **FunASR / Paraformer-zh + SenseVoice-Small**（GitHub modelscope/FunASR，活跃维护） | 优（课堂/中英混/热词） | 支持（WS 流式） | 官方提供 OpenAI 兼容 runtime；模型缓存可卷化 | 代码 MIT，模型按官方协议 |
| Whisper.cpp | 良（中文略弱，幻觉率需调） | 非原生（VAD 切片） | CPU 友好 | MIT |
| 商业"免费层" API | — | — | — | **随时限流/变协议，明确不用** |

结论：FunASR 为主目标（`FunASRProvider` 已实现 HTTP 客户端，`infra/asr/` 预留部署位），
热词表可按课程/学科动态注入（`docs/ai/AI_ARCHITECTURE.md`）。开发/CI 用确定性 MockASR。

## 2. FSRS 巩固算法（ADR-009）

- 官方代码 open-spaced-repetition/py-fsrs（MIT）+ 官方 Wiki 的 FSRS-4.5 公式与默认 17 参数。
- 与 SM-2 对比：FSRS 以 Difficulty/Stability/Retrievability 三变量建模，可给出**任意时刻的回忆概率**（产品需要"预计当前记忆 74%"这类输出），SM-2 只能给间隔序列。已实现并测试。

## 3. 结构化输出 / LLM（ADR-006）

- OpenRouter 当前提供 OpenAI 兼容 `chat/completions` 与 `response_format: json_object`；免费模型池动态变化 → 模型只走配置。
- 结构化可靠性：JSON 抽取（围栏/首尾大括号）+ Pydantic 校验失败重试 + 逐模型 fallback（实现于 `OpenRouterProvider`）。

## 4. 中文检索 / Embedding

- 词法：字符 bigram + TF 余弦对中文短语（"椭圆标准方程" vs "椭圆的标准方程"）相似度 ~0.78，够用作 canonical 归并与题库检索主信号。
- Embedding 升级路径：BGE-M3（MIT，1024 维，多语/长文本，CPU 可跑低量化）；pgvector 0.7。接口已预留（`EMBEDDING_PROVIDER`）。

## 5. OCR

- PaddleOCR（Apache-2.0）中文/公式场景成熟；Pix2Text 适合公式行混排。`OCRProvider` 协议 + Mock；生产以 sidecar HTTP 服务接入（同 ASR 模式）。

## 6. 浏览器录音

- MediaRecorder + `getUserMedia`：Chromium/ Firefox / Safari 14.1+ 均可用；非 HTTPS 不可用（localhost 除外）→ 已写进部署文档。WS 握手无法带 Authorization 头 → 一次性 ticket（`POST /realtime/tickets`）。
