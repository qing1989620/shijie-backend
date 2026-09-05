# 测试计划 · TEST_PLAN

## 后端（pytest，37 个用例全绿）

| 套件 | 覆盖 |
|---|---|
| test_memory_engine | 答错缩短间隔/连续答对增长/重复遗忘升难度/R 随时间衰减/行为→rating 映射/预测单调衰减/**题目间状态独立** |
| test_review_planner | 时间预算装箱/低保持率优先/逾期惩罚/考试加权/薄弱知识点优先 |
| test_auth | 注册登录/重复邮箱 409/错误密码 401/**刷新令牌轮换与重放阻断**/登出撤销/改密撤销会话/错误信封形状 |
| test_permissions | **IDOR**：他人课堂/搜索/任务 404 |
| test_module1_lesson | 课程→课堂→录音→finalize→转写→**乐观并发 409**→笔记（grounded source_segment_ids）→找题（检索非生成）→收藏幂等→题库出现；坏扩展名 415；无转写搜索 409 |
| test_module2_practice | 分析→树（canonical 名）/OCR 预览→校对→入库→**内容哈希去重**/专项找题（basic/same_level/advanced）/随机+智能组题/**顺序冻结**/客观题自动判定/主观题强制自评（422） |
| test_module3_review | Attempt→MemoryState→ReviewTask/**完成复习→ReviewLog→新 MemoryState→下一次任务**/Skip 不更新记忆/预测曲线/问卷/已掌握=挂起不删除 |

原则：不满足于 HTTP 200——断言正确结果、错误输入、权限、跨模块状态变化。
时间测试使用注入 `now`（Fake Clock 等价），不真实等待。

## 前端

- vitest（5 用例）：KaTeX 渲染、时间格式化、token 存取、LaTeX 剥离。
- Playwright E2E（发布门禁）：`e2e/full-loop.spec.ts` 真实浏览器全闭环 + 分步截图。

## 契约

- backend CI：live OpenAPI vs contracts/openapi.json drift check；空库 migration check。
- frontend CI：快照生成类型 → typecheck/test/build。

## 未覆盖（如实声明）

- 真实 OpenRouter / FunASR / PaddleOCR 的冒烟集成（无 Key/运行时，标记 NOT RUN）。
- 并发压力与时区 DST 全矩阵（Planner 时区参数已参数化）。
