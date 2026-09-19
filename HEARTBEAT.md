# HEARTBEAT.md

## 周期性检查清单

- [ ] **未覆盖案例审查** — 检查 `luna_pipeline/data/unclassified_log.jsonl`
  - 今日未 review 案例数 > 0 → 推送给老吴，附 top-3 候选
  - 老吴回复格式示例：`AX-013: 制裁升级 → 供应链断裂风险, field=sanction_level, op=level_gte, threshold=significant`
  - 系统解析 → 调用 `POST /axioms` 新增公理 → 标记案例为 reviewed

- [ ] Luna SGP 服务健康 (:8001-:8004)
- [ ] 天气（若老吴今日有外出计划相关上下文）

## 状态文件
- `luna_pipeline/data/unclassified_log.jsonl` — 未覆盖案例日志
- `memory/heartbeat-state.json` — 上次检查时间戳
