# Dynamic Pool1 TPEx suspension/resumption transition event ledger

## 結論

狀態：`completed_transition_candidate_ledger_unverified`。

本棒將上一棒 `accepted_status_snapshot_rows.csv` 依 ticker/date 差分，產出 TPEx 2015-2025 transition event candidate ledger。

- transition candidates：2295
- announcement verification attempts：160
- announcement verified events：0
- unverified candidates：2295
- `future_data_violation_count=0`

## 邊界

`transition_event_candidates.csv` 主要是 `inferred_from_daily_status_snapshot`，不是 TPEx official explicit event ledger。只有 `announcement_verified_events.csv` 中的 rows 才升級為 `announcement_verified`，且仍需 Core 判斷是否足以支援 Dynamic Pool1 universe integrity。

## Readiness

- `ready_for_core_rerun=true`
- `ready_for_strategy_replay=false`
- `formal_model_changed=false`
- `trade_decision_changed=false`
- `active_in_trade_decision=false`

## 下一步

交 Core 重跑 Dynamic Pool1 readiness。若 Core 仍要求更高比例 official verification，下一棒 Radar/Data 擴大 `bulletin/annDownload` ZIP archive extraction window，或針對 high-impact tickers 做 announcement text parser。
