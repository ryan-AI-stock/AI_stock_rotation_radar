# P1 legacy/regime selected-stock unadjusted OHLC source package

任務：TASK-RADAR-DATA-VNEXT-P1-LEGACY-REGIME-SELECTED-STOCK-UNADJUSTED-OHLC-SOURCE-PACKAGE-001

## 結論

以 selected ticker-month route 補 P1 legacy/regime ordinary-stock trade path 所需未還原 OHLC。未使用 00631L/excess reconstruction，未執行 Experiments/replay/formal。

## Coverage

- ticker-month routes：1379
- selected OHLC rows：4391
- ordinary stock trade path rows：10926
- path ready rows：10785
- blocked rows：141
- adjusted_close_ready=false
- future_data_violation_count=0

完整 rows 與 raw responses 為 local-only，避免推大檔到 Git。

## Blocked summary

141 ordinary-stock trade path rows remain blocked after selected-only official route attempts. Top blocked tickers are recorded in `p1_selected_ticker_path_coverage.csv`; detailed row-level blockers are in `p1_trade_path_blocked_price_ledger.csv`. No proxy, no forward/excess reconstruction, and no adjusted-close fabrication was used.
