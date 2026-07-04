# Pool1B price cache repair 20260704

## 結論
- 狀態：`completed_all_requested_tickers_ready`
- requested tickers：19
- completed tickers：19
- failed / partial tickers：0
- accepted price rows：11439
- coverage：`2024-01-01` 到 `2026-07-02`
- repaired cache output：`C:\Users\zergv\Documents\Codex\2026-05-23\ai-stock-rotation-radar-https-docs\outputs\radar_pool1b_price_cache_repair_20260704\cache_compatible`

## 邊界
- 來源是前一棒已驗證的官方 TWSE/TPEx full-market daily trading shards。
- OHLCV 為官方未還原價格；`adjusted_close_available=false`，沒有偽造 adjusted close。
- `formal_model_changed=false`
- `trade_decision_changed=false`
- `active_in_trade_decision=false`
- `future_data_violation_count=0`

## 是否可交下一棒
- Pool1B / material-layer short-cycle diagnostic rerun ready：`true`
- 若 Core/Experiments 需要 adjusted close，仍需另一條除權息/還原價來源；本包只提供未還原官方 OHLCV。
