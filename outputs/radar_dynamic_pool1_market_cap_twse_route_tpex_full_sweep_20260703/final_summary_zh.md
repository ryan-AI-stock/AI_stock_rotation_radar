# Dynamic Pool1 Market Cap PIT TWSE Route + TPEx Full Sweep

## 結論
- 狀態：`completed_partial_tpex_full_candidate_twse_blocked`
- TPEx：`dailyQuotes` full sweep 完成，accepted rows = `2123871`，以 `close_price * shares_outstanding` 建 total market cap source candidate。
- TWSE：仍 blocked。`MI_INDEX` 無 issued shares/direct market cap；MOPS SPA `t05st03` / `t51sb01` route 可靜態解出 current company basic/commonStockAmount 欄位，但本棒未找到 historical as-of/effective date 參數，不可回推 2015。
- Free-float market cap：未找到 official historical route，仍 blocked。

## PIT / formal 邊界
- `formal_exact=false`
- `market_cap_pit_ready=false`
- `market_cap_pit_partial_ready=true`
- `ready_for_core_rerun=true`
- `ready_for_strategy_replay=false`
- `future_data_violation_count=0`

## 可交 Core 的資料
- TPEx full rows 保存在本機 shards：`tpex_full_sweep_shards/`
- shard index：`accepted_market_cap_rows_manifest.csv`
- committed sample：`proxy_market_cap_rows.csv`
- coverage：`coverage_by_year.csv`、`coverage_by_market.csv`、`tpex_full_sweep_coverage.csv`

## Remaining blockers
- TWSE historical issued shares / direct official market cap route 未找到。
- MOPS current company profile route 不能當 PIT historical source。
- free-float market cap / free-float factor history 未取得。
