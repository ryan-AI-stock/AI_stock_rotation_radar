# P2 2023 selected-stock OHLC source gap fill

任務：TASK-RADAR-DATA-VNEXT-P2-2023-SELECTED-STOCK-OHLC-SOURCE-GAP-FILL-001

## 結論

以 Core gap ledger 為 source of truth，只對 2023 selected ticker/date 需要的官方未還原 OHLC 做 selected-only 補價。未做 full-market mass download，未使用 00631L/excess reconstruction，未偽造 adjusted_close。

## Coverage

- ledger timing rows：1368
- path ready rows：1359
- blocked rows：9
- selected OHLC rows：525
- bounded TWSE MI_INDEX day fallback rows：2
- adjusted_close_ready=false
- future_data_violation_count=0

## Blocked

剩餘 blocked rows 皆為 2023-12-29 same-week comparator 且 Core ledger 的 exit_date 為空白；Radar/Data 無可查的 official exit date，不做 silent fill。

完整 525 列 OHLC rows 已輸出為可追蹤 CSV；raw response cache 仍為 local-only，不推 Git。
