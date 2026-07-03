# Dynamic Pool1 quarterly fundamentals PIT source package

## 結論

狀態：`blocked_with_route_evidence`。

本棒完成 MOPS quarterly fundamentals route bounded probes，但沒有 accepted rows：

- source_probe_attempts：8
- accepted_quarterly_fundamentals_rows：0
- `quarterly_fundamentals_pit_ready=false`
- `quarterly_fundamentals_pit_partial_ready=false`
- `future_data_violation_count=0`

## 主要 blocker

MOPS `ajax_t163sb04` / `ajax_t163sb05` / `ajax_t163sb06` / `ajax_t164sb04` 直接 scripted request 回 security page：`FOR SECURITY REASONS, THIS PAGE CAN NOT BE ACCESSED`。猜測 XBRL/static download path 回 404 或同樣 security page。

因為沒有取得可解析資料表，也沒有確認 filing/source/available date 欄位，本棒不接受任何 quarterly fundamentals row。

## 下一步

1. 用 browser/devtools exact request extraction 取得 MOPS t163/t164 成功查詢時的 session/header/body/hidden fields。
2. 反查官方 XBRL bulk download 或 TWSE open-data catalog 的正確可下載路徑。
3. 若財報資料 route 解開後，再用 MOPS material information / financial report announcement crawler 補 filing_date。

## 邊界

- `ready_for_core_rerun=true`，讓 Core 記錄 blocker evidence。
- `ready_for_strategy_replay=false`
- `formal_model_changed=false`
- `trade_decision_changed=false`
- `active_in_trade_decision=false`
