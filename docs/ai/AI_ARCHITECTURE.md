# AI 架构 · AGENTS / RAG / LLM

## Agent 清单（能力严格收口，无万能 Chat）

| Agent | 输入 | 输出 Schema | 工具白名单 |
|---|---|---|---|
| `LessonSummaryAgent` | 转写片段（分块） | `LessonSummaryResult` | summarize_transcript |
| `QuestionAnalysisAgent` | 题干 + canonical 知识点词表 | `QuestionAnalysisResult`（树） | normalize_kp_names, analyze_structure |
| `ExerciseRetrievalAgentBase` | 知识点/学科/难度 | `ExerciseQueryRewrite` | **search_question_bank, rerank_questions only** |

纪律：
- **找题 ≠ 生成题**。检索不到时如实返回"没有找到足够相关的练习"。
- Agent 输出一律 `Pydantic` 校验后才进 Service；Agent 永不直接写库。
- Prompt 集中在 `app/ai/prompts/registry.py`（name + version + system + output schema），不散落业务代码。
- 每次 AI 调用写 `AIRun`（provider/model/latency/tokens/status）审计。

## LLM Provider（`app/providers/llm/provider.py`）

- `LLMProvider` 协议：`complete_structured(prompt_key, system, user, schema)`。
- `MockLLMProvider`：确定性（CI/离线可用）；按 prompt_key 注册 handler，**只做结构整形**，不虚构内容。
- `OpenRouterProvider`：OpenAI 兼容；模型来自配置（`LLM_DEFAULT_MODEL` + 逗号分隔 fallback），**不写死任何 :free 模型**；
  timeout / 指数退避 / 逐模型 fallback / JSON 抽取 / Schema 校验失败重试。
- 无 Key 时自动回落 Mock——系统功能链路完整可用，且 UI/文档明确标注 Mock。

## 知识点 Canonicalization（`agents.canonicalize_kp`）

解决"椭圆标准式 / 椭圆的标准方程 / 椭圆标准方程"分裂问题，五级策略：

1. 精确同名 → 2. Alias 表 → 3. 归一化名（`normalize_kp_name`）→
4. 字符 bigram 词法相似度 ≥0.55 归并（接入 BGE 后此级升级为 embedding 相似度）→ 5. 新建 canonical。

## RAG（`models/system.py` RAGDocument/RAGChunk + workers._run_rag_indexing）

- 用途：课堂转写切块索引（6 段/块，带 `[秒]` 时间戳前缀）→ 后续课堂问答/相似题检索的底层。
- 开发期：词法检索（`retrievers/lexical.py`，CJK 字符 bigram + 余弦）；生产：pgvector + BGE-M3 embedding（`EMBEDDING_PROVIDER=bge` 即插）+ 可选 reranker。
- 权限：RAGDocument 带 `user_id / visibility`——私人课堂永远只能被本人检索。

## Prompt Injection 与不可信内容

课堂转写 / 上传题目 / 外部检索摘要均为 UNTRUSTED：进入 prompt 前不拼接任何指令性上下文；
Agent 的工具白名单与输出 Schema 保证即使内容含 "ignore previous instructions" 也无法改变系统行为
（Agent 无 shell / 任意 SQL / 用户管理等工具，输出必须通过 Schema 才可能产生副作用）。
