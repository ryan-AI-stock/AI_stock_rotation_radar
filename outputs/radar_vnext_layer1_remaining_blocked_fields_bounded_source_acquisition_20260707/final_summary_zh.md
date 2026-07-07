# vNext Layer1 Remaining Blocked Fields Bounded Source Acquisition

Status: completed_bounded_source_route_readiness_partial_not_ingest_ready

結論：
- 這是 source-route acquisition/readiness only，沒有回測、沒有 formal ingest、沒有 trade/report change。
- 本機已找到 t163sb05 對 current_ratio / inventory / receivable 的官方 PIT route candidate，但欄位尚未 materialize；下一步需要 bounded parser/sample，不可直接交 Experiments。
- t163sb06 cash-flow 目前只有 route asset evidence，仍 blocked，需要 bounded route unlock/sample parse。
- TPEx all-stock sector PIT 與 TWSE exact daily market cap 仍 blocked。
- free-float market cap 沒有本機可用 source，需 Strategy/Core 決策是否接受 total market cap proxy，否則需另找官方 dated free-float route。

Readiness:
- ready_for_core_layer1_remaining_source_refresh=true
- ready_for_core_ingest_contract_build=false
- ready_for_radar_bounded_route_unlock=true
- ready_for_experiments=false
- ready_for_formal=false
- ready_for_strategy_replay=false
- not_live_rule=true
- future_data_violation_count=0

Source status counts:
- PIT-ready_route_candidate: 3
- proxy: 0
- blocked: 4
- requires-human-policy: 1

下一棒：
- 若 Core 只需要 source-route readiness，交 Core/Data 判斷 contract design。
- 若要真的補 remaining fields，Radar/Data 下一步應跑 bounded sample parser：MOPS t163sb05 current_assets/current_liabilities/inventory/receivables；MOPS t163sb06 cash-flow statement sample。
- Strategy Center 需決定：free-float market cap 是否可先用 total market cap proxy；TWSE monthly-anchor sector proxy 是否可作 diagnostic-only Layer1 sector control。
