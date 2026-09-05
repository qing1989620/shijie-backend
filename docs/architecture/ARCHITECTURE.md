# 架构总览 · ARCHITECTURE

Modular Monolith + 内嵌 Worker（线程）+ 独立 ASR/OCR 运行时（生产容器化）。
前后端完全独立部署，唯一运行时连接：REST + WebSocket。

## 系统图

```
Browser (React SPA)
   │  HTTPS REST (VITE_API_BASE_URL)      WSS 转写流 (ticket 握手)
   ▼                                        ▼
FastAPI Modular Monolith ──────────► WebSocket /ws/v1/lessons/{id}/transcription
   │
   ├─ api/v1        路由层（契约：Pydantic → openapi.json）
   ├─ services      事务性业务（Attempt→Mastery→MemoryState→ReviewTask 单事务）
   ├─ ai            MemoryEngine(FSRS) · ReviewPlanner · Agents · Prompts · 检索
   ├─ providers     llm / asr / ocr / storage / exercise_source（全部接口化）
   ├─ workers       AI Job 执行（线程池；生产换 Dramatiq/Celery）+ Transactional Outbox
   └─ models        SQLAlchemy 2 实体（Alembic 迁移）
   ▼
SQLite(dev) / PostgreSQL+pgvector(prod)   LocalFS(dev) / MinIO·S3(prod)
   ▼ (providers)
OpenRouter(LLM) · FunASR 自托管(ASR) · PaddleOCR 自托管(OCR) · 自建CC0题库(题源)
```

## 关键数据流

### 课堂数据流
```
Lesson → Recording(分片上传/WS) → ASR Provider → TranscriptSegment(is_final, version)
      → LessonSummaryAgent(分块→合并→知识点) → LessonSummary(payload 带 source_segment_ids)
      → LessonKnowledgePoint(canonical) → Outbox:index_lesson → RAGChunk 索引
```

### 练习数据流
```
ExerciseSearchAgent: 知识点 → Query Rewrite → ExerciseSourceProvider.search(词法+知识点强信号)
  → ExerciseSearchResult(score, band, reason) → 收藏 → UserQuestion(origin) → 统一 Question 池
Attempt 提交（单事务）: Attempt → 判定(objective/self) → UserKnowledgeMastery EMA
  → MemoryEngine.update(rating) → MemoryState → ReviewTask 创建/重排
```

### 复习数据流
```
GET /review/tasks: due 任务 → Planner(priority=0.4·(1-R)+0.2·薄弱+0.2·考试+0.1·重要+0.1·逾期)
  → 按 available_minutes 装箱 → 今日任务(含 reason)
完成复习: complete → ReviewLog → MemoryEngine.update → MemoryState'
  → 下一 ReviewTask(due=FSRS interval) → Calendar 可见
```

### AI 数据流
```
所有 AI 能力: Prompt Registry(版本化) → LLM Provider(mock/openrouter, structured output)
  → Pydantic Schema 校验 → Service 业务规则 → 单事务落库 → AIRun 审计(provider/model/latency)
```

## 决策要点（ADR 索引见 docs/adr/）

- Contract First：`/openapi.json` 是唯一机器契约，CI 做 drift check。
- 统一 Question 实体：模块间只引用不复制（UserQuestion 承载收藏/来源）。
- Attempt 提交是**后端单事务**，前端不得拆成多次调用。
- 所有外部依赖 Provider 化；无 Key 时 Mock 完整可用（不冒充真实）。
- 检索是**诚实检索**：题源只有 LocalQuestionBankProvider（自建 CC0），不足时明示"没有找到足够相关的练习"。
