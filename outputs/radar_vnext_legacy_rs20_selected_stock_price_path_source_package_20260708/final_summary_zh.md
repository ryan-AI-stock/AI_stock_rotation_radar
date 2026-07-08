# Legacy RS20 selected-stock price path source package

任務：TASK-RADAR-DATA-VNEXT-LEGACY-RS20-SELECTED-STOCK-PRICE-PATH-SOURCE-PACKAGE-001

## 結論

已用本機 `radar_dynamic_pool1_all_listed_liquid_universe_full_sweep_20260703` monthly shards，抽出 Core request 的 selected ticker primary window：2024-01-02 到 2026-06-05。沒有重新下載，沒有讀 Google/Drive，沒有使用 00631L + excess 重建個股 path。

## Coverage

- request rows：389
- selected unique tickers：388
- selected price rows：219088
- required trading dates：586
- markets：TPEx,TWSE
- full unadjusted open/close coverage tickers：0
- missing/partial unadjusted coverage tickers：388

## Readiness

- ready_for_core_legacy_rs20_unadjusted_open_close_path_ingest=false
- next_trading_day_close_path_ready=false
- next_trading_day_open_path_ready=false
- exact_selected_stock_adjusted_close_path_ready=false
- adjusted_close_available=false
- ready_for_legacy_rs20_exact_cost_timing_diagnostic=false
- ready_for_experiments=false
- ready_for_formal=false
- future_data_violation_count=0

## 邊界

`adjusted_close` 不可由官方未還原 close 偽造；本包把 adjusted close 明確標 blocked。若 Core 的 exact diagnostic 必須用 adjusted close，仍 blocked；若 Core 接受 unadjusted official open/close 作 timing/cost path，則可用本包 local-only full rows + tracked coverage/readiness 建 ingest contract。

大型完整 rows：`selected_stock_price_rows_local_only.csv` 已用 `.gitignore` local-only，不推 Git；repo 只追 sample、coverage、manifest、readiness。

## Trade path availability audit

- primary trade path rows audited：1476
- unadjusted requested timing prices available rows：1464
- missing unadjusted rows：12
- adjusted close requested rows remain blocked because official source is unadjusted。

## Blocked detail

12 unadjusted missing rows are all 8249 exit-price rows where the requested exit dates 2024-10-11 or 2024-10-15 are absent from the local official daily full-sweep rows. They are left blocked; no forward/excess/proxy fill is used.
