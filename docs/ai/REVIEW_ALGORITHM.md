# 巩固算法 · REVIEW_ALGORITHM

> 科学与产品的边界必须清晰：**Memory Model（FSRS）是算法层；其余全部是 Product Planning Heuristic。**
> 不把产品经验包装成记忆科学。

## 第一层：Memory Engine（`app/ai/memory_engine.py`）

实现 **FSRS-4.5**（Free Spaced Repetition Scheduler，参考 open-spaced-repetition/py-fsrs，MIT）。

- 可回忆性：`R(t,S) = (1 + t/(9S))^DECAY`，DECAY=-0.5
- 稳定性（成功）：`S' = S·(1 + e^w8·(11-D)·S^(-w9)·(e^(w10(1-R))-1)·HardPenalty·EasyBonus)`
- 稳定性（遗忘）：`S' = w11·D^(-w12)·((S+1)^w13 - 1)·e^(w14(1-R))`
- 难度：`D' = clamp(D - w6·(rating-3), 1, 10)`，再做均值回归 `D'' = w5·D0(rating) + (1-w5)·D'`
- 下次间隔：`I = 9S·(r*^(1/DECAY) - 1)`，r* 为目标保持率（默认 0.9，用户可调 0.7–0.95）

工程防护：`r ≤ 0.99` 截断——瞬时重答（r≈1）时成功分支零增长，截断保证每次复习必有正向学习。

### 行为 → 评分映射（确定性程序，非 AI）

`map_rating()` 综合 是否正确 / 用时 / 提示次数 / 自信心(1-5) / 改答案次数：

| 行为特征 | Rating |
|---|---|
| 答错 | Again(1) |
| 答对但提示≥2 或 信心≤2 或 改答案≥2 | Hard(2) |
| 答对且信心=5 且 用时<45s 且 无提示 | Easy(4) |
| 其余答对 | Good(3) |

原始行为数据（Attempt）全量保存——未来算法升级可离线重算。

### 状态独立

`MemoryState` 以 `(user_id, question_id)` 唯一。任何人、任何题的状态互不影响（有测试验证）。

## 第二层：Review Planner（`app/ai/review_planner.py`，Product Heuristic）

```
priority = 0.40·(1 - R)            # 记忆风险（来自 Memory Engine）
         + 0.20·(1 - mastery)      # 知识点薄弱（EMA 估算）
         + 0.20·exam_urgency       # 考试 ≤3 天=1.0；≤14 天=0.7；≤30 天=0.4；否则 0.15
         + 0.10·importance         # 知识点重要度
         + 0.10·overdue            # 逾期天数/7，封顶 1.0
```

按 priority 排序后**装箱**进用户 `daily_minutes`（问卷先验；行为会覆盖）。
优先级最高因子生成 UI 文案「为什么今天复习」。

### 首次复习的特例（Heuristic）

练习中答错的新题：先安排**当天 +15 分钟**的再练（学习步骤思想），
从该次复习起 FSRS 间隔接管。答对的题直接按 FSRS 初始间隔。

## 版本与追溯

- `MemoryState.scheduler_version = "fsrs45-baseline"`
- 全局 `SCHEDULER_VERSION` 常量；算法变更必须 bump 并可对 ReviewLog 重放。

## 用户话语规范

- 对用户展示「预计记忆保持率 / 根据学习行为估算」；禁止宣称"精确测量大脑记忆"。
- Skip ≠ 答对：跳过不更新 MemoryState，由 Planner 另行安排（有测试验证）。
- 「已掌握」= 挂起（stability 提到 120 天），可恢复，永不直接删除。
