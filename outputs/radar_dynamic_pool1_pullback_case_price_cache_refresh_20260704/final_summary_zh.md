# Pullback case price cache refresh

## 結論
- 狀態：`completed_targeted_case_trace_price_refresh`
- requested tickers：5
- completed tickers：5
- failed / partial tickers：0
- accepted price rows：15
- required through date：`2026-07-03`
- source：TWSE official `STOCK_DAY`
- `adjusted_close_available=false`
- `future_data_violation_count=0`

## 邊界
- 只供 Experiments / Research 補 6669、2308、2317 case trace 到 2026-07-03。
- 沒有 strategy replay。
- 沒有 report change。
- 沒有 formal model / trade decision change。
- OHLCV 為官方未還原價格，沒有偽造 adjusted close。
