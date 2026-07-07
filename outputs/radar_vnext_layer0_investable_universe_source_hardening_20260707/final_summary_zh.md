# Layer0 investable universe source hardening

任務：TASK-RADAR-DATA-VNEXT-LAYER0-INVESTABLE-UNIVERSE-SOURCE-HARDENING-001

## 結論

Radar/Data 只用本機既有 source package 做 Layer0 source hardening，沒有讀 Google/Drive，沒有下載新資料，沒有繼續 Layer1 t164。

可交 Core/Data 的結論：

- daily per-stock traded value：可作 Layer0 主要低成本 pruning source，由 Core 建 contract。
- total market traded value：可由同一批 official daily rows 依 date/market 加總衍生。
- instrument type master：仍 partial，不能宣告 full PIT common-stock / ETF / ETN / warrant / preferred master。
- PIT disposition / full-delivery / suspended / delisted event ledger：suspension/resumption 有 partial dated source，full-delivery/disposition 仍 blocked/unverified。
- market-cap rank：direct exact route 仍 blocked；capital_stock x close 只能 diagnostic proxy，不可 formal。

## Readiness

- ready_for_core_layer0_source_contract_refresh=true
- ready_for_core_layer0_traded_value_contract_refresh=true
- ready_for_core_layer0_total_market_turnover_contract_refresh=true
- ready_for_core_layer0_instrument_type_master_contract=false
- ready_for_core_layer0_pit_event_ledger_contract=false
- ready_for_core_layer0_market_cap_rank_contract=false
- ready_for_experiments=false
- ready_for_formal=false
- ready_for_strategy_replay=false
- future_data_violation_count=0

## 邊界

- Layer0 是 data-pruning / investable universe filter，不是交易規則。
- KY tag separately；不得只因名稱自動排除。
- ETF/ETN 放 benchmark/fallback universe，不進 ordinary stock pool。
- 不用 forward returns。
- 不用 current/static/generated map 回推歷史。
- 不把 proxy / partial 包裝成 formal-ready。

## 建議交棒

交 Core/Data 建立 Layer0 source contract：

1. 以 traded_value 作主要 universe pruning source。
2. instrument / event / market-cap 欄位用 explicit unknown/blocked/proxy ledger，不 silent fill。
3. market cap rank 先只作 diagnostic comparison，正式 Layer0 初版以 traded value + buffer 為主。
