# vNext Funnel Layer 1 Fundamental Source Inventory / Readiness

Status: completed_inventory_ready_for_core_layer1_contract_refresh_partial_not_experiments

結論：
- 這是 source inventory/readiness only，沒有 formal ingest、沒有 Experiments/replay。
- 既有本機資料足以讓 Core 做 Layer 1 refreshed PIT contract 的「部分升級」：monthly revenue、quarterly fundamentals、TWSE capital stock proxy、listing/status partial event source。
- 不足以直接進 Experiments，也不足以 formal：industry/sector、cash-flow quality、current ratio、inventory/receivable risk、完整 market cap/free-float market cap 仍 blocked 或 proxy。
- Layer 1 partial/proxy diagnostic 的 no-go 不代表基本面 thesis 失敗；目前判定是 source quality 不足。

Readiness:
- ready_for_core_layer1_contract_refresh=true
- ready_for_radar_source_acquisition=true
- ready_for_experiments=false
- ready_for_formal=false
- ready_for_strategy_replay=false
- not_live_rule=true
- forward_returns_live_rule_usage=false
- future_data_violation_count=0
- source_route_recommendation=existing_local_plus_external_source_needed

可先交 Core 的 existing_local sources:
- MOPS monthly revenue full-universe PIT: 2015-01..2026-05, 244620 rows, 1971 symbols。
- Quarterly fundamentals full sweep: 2015Q1..2026Q1, 79046 rows, 1970 symbols。
- TWSE capital stock proxy contract: 43705 rows, 1079 symbols。
- Listing/status partial event source: 可作 listing board/status proxy，master 仍 not ready。

主要缺口：
- per-company exact filing timestamp 大多沒有，需 Core 採 conservative available_date policy 或另開 acquisition。
- cash-flow statement、current assets/current liabilities、inventory/receivable 欄位未 materialized。
- market_cap/free-float market cap 還不是 full exact。
- TPEx all-stock historical sector membership route 仍 locked。

下一棒：
- 直接交 Core/Data 判斷是否建立 Layer 1 refreshed PIT contract。
- Radar/Data 後續只需針對 cash-flow / balance-sheet detail / exact filing timestamp / TPEx sector / market cap 做 bounded acquisition。
