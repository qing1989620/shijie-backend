# API 契约（人类阅读版）

机器契约：`contracts/openapi.json`（唯一事实源，`/openapi.json` 实时导出）。
所有 ID 为 UUID 字符串；时间 UTC 存储、ISO-8601 传输；列表统一分页
`{items, next_cursor, has_more}`；错误统一 Problem Details 信封
`{type,title,status,code,detail,request_id,errors}`——前端按 `code` 分支。

## 端点总览（prefix=/api/v1）

### auth / users
| Method | Path | operationId | 说明 |
|---|---|---|---|
| POST | /auth/register | auth_register | 201；邮箱唯一 |
| POST | /auth/login | auth_login | TokenPair |
| POST | /auth/refresh | auth_refresh | **旋转刷新**：旧 refresh 立即失效 |
| POST | /auth/logout | auth_logout | 撤销 refresh |
| GET/PATCH | /users/me | users_me_get/update | |
| POST | /users/me/change-password | users_change_password | 撤销全部会话 |

### courses / lessons / recording / transcript / summary
| Method | Path | operationId |
|---|---|---|
| GET/POST | /courses | courses_list / courses_create |
| GET/PATCH/DELETE | /courses/{course_id} | course_get/update/delete |
| GET/POST | /lessons | lessons_list / lessons_create |
| GET/PATCH/DELETE | /lessons/{lesson_id} | lesson_get/update/delete |
| POST | /lessons/{lesson_id}/recordings | recordings_create（音频上传，扩展名/MIME/大小校验） |
| POST | /recordings/{recording_id}/finalize | recording_finalize（最终校准转写） |
| GET | /lessons/{lesson_id}/transcript | transcript_get |
| PATCH | /transcript-segments/{segment_id} | transcript_segment_update（**乐观并发**：version 不符 409） |
| POST | /lessons/{lesson_id}/summary-jobs | summary_job_create（202 + job_id） |
| GET | /lessons/{lesson_id}/summary | lesson_summary_get |

### realtime（WebSocket，契约见 contracts/asyncapi.yaml）
| Method | Path | operationId |
|---|---|---|
| POST | /realtime/tickets | realtime_ticket_create（一次性握手票据） |
| WS | /ws/v1/lessons/{lesson_id}/transcription | —（session.start→ready→partial/final→closed） |

### questions / knowledge / search
| Method | Path | operationId |
|---|---|---|
| GET | /questions | questions_list（分页 + favorites_only/wrong_only/search） |
| POST | /questions/import | question_import（content_hash 去重） |
| POST | /questions/ocr | question_ocr_preview（202，草稿不落库为题） |
| GET/DELETE | /questions/{question_id} | question_get / question_delete |
| POST/DELETE | /questions/{question_id}/favorite | question_favorite / question_unfavorite（幂等） |
| POST | /questions/{question_id}/analysis-jobs | analysis_job_create（202） |
| GET | /questions/{question_id}/knowledge-tree | knowledge_tree_get（含 mastery_estimate） |
| GET | /knowledge-points | knowledge_points_list（薄弱优先） |
| GET | /knowledge-points/{kp_id} | knowledge_point_get |
| POST | /lessons/{lesson_id}/exercise-searches | lesson_exercise_search_create |
| POST | /knowledge-points/{kp_id}/exercise-searches | kp_exercise_search_create |
| GET | /exercise-searches/{search_id} | exercise_search_get |

### practice / review（Module 3 核心）
| Method | Path | operationId |
|---|---|---|
| POST | /practice-sets | practice_set_create（random/smart；顺序冻结） |
| GET | /practice-sets/{set_id} | practice_set_get |
| POST | /practice-sets/{set_id}/attempts | attempt_create（**单事务**驱动 M3） |
| POST | /attempts | attempt_create_standalone（复习作答） |
| GET/PUT | /review/profile | review_profile_get / review_profile_update（冷启动问卷） |
| GET | /review/tasks | review_tasks_today（Planner 排序 + reason + 预计保持率） |
| GET | /review/calendar | review_calendar（真数据日历） |
| GET | /review/tasks/{task_id} | review_task_get |
| POST | /review/tasks/{task_id}/complete | review_task_complete（→ReviewLog→MemoryState'→下一任务） |
| POST | /review/tasks/{task_id}/skip | review_task_skip（≠答对，重排） |
| POST | /review/tasks/{task_id}/snooze | review_task_snooze |
| POST | /review/tasks/{task_id}/mastered | review_task_mastered（挂起不删除） |
| GET | /questions/{question_id}/memory-state | memory_state_get |
| GET | /questions/{question_id}/memory-forecast | memory_forecast_get（30 天曲线） |

### jobs / meta
| Method | Path | operationId |
|---|---|---|
| GET | /jobs/{job_id} | job_get（status/progress/stage） |
| GET | /jobs/{job_id}/events | job_events_sse |
| GET | /meta/version | meta_version（contract_version 跨仓库对齐用） |
| GET | /health · /ready | health / ready（ready 检查 DB；OpenRouter 故障不置灰全站） |

## 幂等性

收藏、导入（content_hash）、favorite 具备幂等；`Idempotency-Key` 头为生产增强位（预留）。

## 变更流程

见 docs/api/API_CHANGELOG.md：契约先行，任何变更经
Schema → OpenAPI → 冻结 → 前端 regenerate → 测试 → Changelog。
