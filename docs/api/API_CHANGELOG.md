# API 变更日志

## 1.0.0（2026-09-05）— Contract V1 冻结

初始契约：auth / users / courses / lessons / recordings / transcript / summary /
realtime(tickets+WS) / questions(+ocr) / knowledge-points / exercise-searches /
practice-sets / attempts / review(profile,tasks,calendar,complete,skip,snooze,mastered) /
memory-state / memory-forecast / jobs / meta / health。

约定：
- 列表分页信封 `{items, next_cursor, has_more}`；
- 错误信封 `{code, detail, status, request_id}`；
- 所有 operationId 稳定可依赖（前端生成 client 使用）。

### Breaking Change 流程（跨仓库）

1. 优先向后兼容（新增字段而非修改语义）；
2. 必要 breaking → 升级 `/api/v2` 或 bump `contract_version` 并在此登记；
3. 同步更新 backend/contracts/openapi.json → 前端 `npm run api:generate` → 双方测试通过。
