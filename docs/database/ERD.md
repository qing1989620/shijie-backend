# ERD（核心关系）

Mermaid ER 图。所有主表含 `id(UUID) / created_at / updated_at`，按需 `deleted_at`（软删）。

```mermaid
erDiagram
    users ||--o| user_profiles : has
    users ||--o| user_preferences : has
    users ||--o{ refresh_tokens : rotates
    users ||--o{ courses : owns
    courses ||--o{ lessons : contains
    users ||--o{ lessons : owns
    lessons ||--o{ recordings : has
    lessons ||--o{ transcript_segments : has
    lessons ||--o| lesson_summaries : has
    lessons ||--o{ lesson_knowledge_points : extracts

    knowledge_points ||--o{ knowledge_point_aliases : canonicalizes
    knowledge_points ||--o{ lesson_knowledge_points : appears_in
    knowledge_points ||--o{ question_knowledge_points : tagged_by
    knowledge_points ||--o{ user_knowledge_mastery : measured_by

    question_sources ||--o{ questions : sources
    questions ||--o{ user_questions : related_via
    users ||--o{ user_questions : favorites_uploads
    questions ||--o{ question_knowledge_points : analyzed_into
    questions ||--o| question_analyses : has
    question_analyses ||--o{ knowledge_tree_snapshots : snapshots
    questions ||--o{ attempts : answered_by

    exercise_searches ||--o{ exercise_search_results : returns
    exercise_search_results }o--|| questions : refers

    users ||--o{ practice_sets : creates
    practice_sets ||--o{ practice_set_items : freezes_order
    practice_set_items }o--|| questions : includes
    attempts }o--o| practice_sets : belongs_to
    attempts }o--o| review_tasks : completes

    users ||--o| review_profiles : cold_start
    users ||--o{ memory_states : per_question
    questions ||--o{ memory_states : per_user
    memory_states ||--o{ review_tasks : schedules
    users ||--o{ review_tasks : plans
    review_tasks ||--o{ review_logs : logged_by

    users ||--o{ ai_jobs : triggers
    ai_jobs ||--o{ ai_runs : audited
    rag_documents ||--o{ rag_chunks : chunked
    users ||--o{ attachments : uploads
```

## 关键约束

| 约束 | 说明 |
|---|---|
| `uq_memory_state (user_id, question_id)` | 每用户每题独立记忆状态 |
| `uq_user_question (user_id, question_id)` | 收藏/上传关系唯一，不复制题目 |
| `uq_segment_lesson_seq (lesson_id, sequence)` | 转写片段顺序唯一 |
| `uq_ps_item_pos (practice_set_id, position)` | 组题顺序冻结 |
| `uq_kp_alias (alias)` | 知识点别名指向唯一 canonical |
| `ix_ms_user_due (user_id, next_review_at)` | 今日任务查询 |
| `ix_rt_user_status_due (user_id, status, due_at)` | Planner 候选查询 |
| `ix_segments_lesson_start (lesson_id, start_ms)` | 转写时间跳转 |
| `content_hash` on questions | 跨来源题目去重 |

## 时区与时间

所有时间列使用 `UTCDateTime`（TypeDecorator）：存 naive-UTC、读出 tz-aware UTC；
用户本地日期（复习任务 scheduled_date）按 Asia/Shanghai +8 折算，生产由 profile.timezone 驱动。
