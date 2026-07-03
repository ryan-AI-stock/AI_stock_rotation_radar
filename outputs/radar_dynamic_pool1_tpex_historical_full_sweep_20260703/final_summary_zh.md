# Dynamic Pool1 TPEx historical listing/status full sweep

## 結論

狀態：`completed_full_route_coverage_suspension_events_still_blocked`。

本棒把上一棒 sample route 擴成 2015-01-01 到 2025-12-31 full sweep package：

- `company/latest`：2015-2025 yearly sweep，accepted listing rows = 294
- `company/deListed`：2015-2025 yearly sweep，accepted delisting rows = 104
- `afterTrading/chtm`：2015-01-01～2025-12-31 daily sweep，accepted status snapshot rows = 90865
- `accepted_suspension_event_rows=0`

## Readiness

- `full_tpex_2015_2025_route_coverage_ready=true`
- `full_tpex_2015_2025_master_ready=false`
- `ready_for_core_rerun=true`
- `ready_for_strategy_replay=false`
- `future_data_violation_count=0`
- `formal_model_changed=false`
- `trade_decision_changed=false`
- `active_in_trade_decision=false`

## 邊界

`afterTrading/chtm` 是每日 status snapshot，可判斷某日是否變更交易、分盤交易、管理股票、停止交易，但不是 suspension/resumption transition event ledger。`bulletin/sprc` 仍是 current-only，沒有 historical date parameter，所以 suspension event rows 仍為 0。

## 下一步

1. 交 Core 重跑 Dynamic Pool1 readiness，判斷 TPEx full route coverage + daily status snapshot 是否足以讓 listing/status master 從 partial 再升級。
2. 若 Core 仍要求 explicit transition event dates，下一棒 Radar/Data 需跑 `bulletin/annDownload` ZIP keyword extraction 或以 `afterTrading/chtm` daily snapshot diff 產生 inferred transition candidates，再用公告 archive 驗證。
3. 可選 cross-check：下載 `company/applicantStatDl?type=list|app&date=YYYY` annual files，和 `company/latest` listing rows 對帳。
