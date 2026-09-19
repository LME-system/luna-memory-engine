# HEARTBEAT.md

## 周期性检查清单

- [ ] **公理置信度刷新** — 调用 `POST /axioms/refresh` (dry_run 先检查)
  - 低于 0.3 的公理自动标记 deprecated → 进 review 队列
  - 衰减公式: base_conf × (0.95 ^ days_since_last_hit) × (tp/(tp+fp+1))

## 状态文件
- `luna_pipeline/data/unclassified_log.jsonl` — 未覆盖案例日志
- `memory/heartbeat-state.json` — 上次检查时间戳
