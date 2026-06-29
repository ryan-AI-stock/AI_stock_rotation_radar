# 0050 PIT universe 剩餘 4 檔歷史價格缺口補齊

- 狀態：completed_candidate
- 輸出：`C:\Users\zergv\Documents\Codex\2026-05-23\ai-stock-rotation-radar-https-docs\outputs\radar_0050_pit_missing_price_coverage_4tickers_20260629`
- 來源：TWSE STOCK_DAY official daily OHLCV
- 完成檔數：4 / 4
- 候選價格列：2429
- source attempts：196
- adjusted close：來源未提供，`adjusted_close_available=false`；未把 close 假造為 adj_close。
- 邊界：`formal_model_changed=false`、`trade_decision_changed=false`、`formal_exact=false`。

## Coverage

| ticker | required range | candidate range | rows | status |
|---|---:|---:|---:|---|
| 2311.TW | 2014-11-28~2018-03-31 | 2014-11-28~2018-03-31 | 817 | completed_candidate |
| 2823.TW | 2016-11-30~2020-08-31 | 2016-11-30~2020-08-31 | 918 | completed_candidate |
| 2888.TW | 2019-09-27~2020-08-31 | 2019-09-27~2020-08-31 | 225 | completed_candidate |
| 3474.TW | 2014-11-28~2016-10-31 | 2014-11-28~2016-10-31 | 469 | completed_candidate |

## 使用限制

- 本批資料是 source-backed price candidate package，可交 Core 更新 cache/coverage ledger。
- TWSE `STOCK_DAY` 為未還原 OHLCV；若 Core 的正式績效需要 adjusted close，仍需 Core 判斷是否接受 unadjusted price candidate 或另接還原來源。
- 未使用現行公司代號替代下市、合併或更名代號；`corporate_action_mapping.csv` 只記錄未替代的治理邊界。
