# TASK-RADAR-DATA-VNEXT-SELECTED-STOCK-EXACT-EXDATE-CAPITAL-CHANGE-ROUTE-UNLOCK-001

## 結論

完成 selected ticker/event bounded t05st01 / t05st01_detail route unlock attempt。

- canonical events: 87
- selected tickers: 31
- accepted exact ex-date events: 59
- accepted payment-date events: 16
- high-priority exact ex-date accepted: 3/4
- non-dividend capital-change inventory candidate rows: 36
- blocked ledger rows: 98
- future_data_violation_count: 0

## 邊界

Radar/Data 只輸出 official source evidence / patch candidates。未計算 adjusted close、未計算 total-return factor、未用 board/shareholder date 當 ex-date、未用 query response datetime 當 market_available_at。

未能唯一對應的事件維持 blocked，不做 silent fill。
