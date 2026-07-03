# Dynamic Pool1 historical market cap PIT

## 判定
- status: `completed_partial_tpex_total_market_cap_proxy_sample_twse_blocked`
- market_cap_pit_ready: `false`
- market_cap_pit_partial_ready: `true`
- accepted rows: `240`
- accepted market: `TPEx`
- blocked market: `TWSE`
- source_type: `shares_derived_official_daily_candidate`
- formal_exact: `false`
- free_float_market_cap_ready: `false`
- future_data_violation_count: `0`
- ready_for_core_rerun: `true`
- ready_for_strategy_replay: `false`

## 已解開的部分
TPEx 官方 `dailyQuotes` 在 sample 日期含 `收盤` 與 `發行股數`，可用同日資料推導 total market cap：

`market_cap = close_price * shares_outstanding`

本 package 已對 2015-01-05、2024-07-01、2026-07-02 做 bounded sample，產出 `accepted_market_cap_rows.csv` / `proxy_market_cap_rows.csv`。

## 仍 blocked
- TWSE `MI_INDEX?type=ALLBUT0999` 有 close/turnover，但 sample response 無發行股數或個股市值。
- TWSE/MOPS `t187ap03_L` company basic open data 有實收資本額/已發行普通股數，但為 current snapshot，不可回推 2015。
- direct legacy MOPS company basic route 回 security page。
- free-float market cap 尚未找到 official historical route。

## 下一步
優先找 TWSE historical issued shares / capital changes / direct market cap official route；若找不到，再將 TPEx daily total market cap 做 full 2015-latest sweep，並把 TWSE 維持 blocked，不可用 current snapshot 補洞。
