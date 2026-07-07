# vNext Layer1 Missing Fundamental Source Acquisition / Readiness

Status: completed_missing_source_readiness_partial_core_contract_candidate

結論：
- 這是 source acquisition/readiness only；沒有 formal ingest、沒有 Experiments/replay、沒有 trade/report change。
- Core 可用 existing local source 建立 Layer1 fuller PIT contract 的「部分補強」，但不是 full exact。
- 可交 Core 的欄位：TPEx market cap proxy、TWSE capital stock/shares proxy、quarterly fundamentals 衍生 debt/leverage、listing/status partial proxy、TWSE industry diagnostic proxy。
- 仍 blocked：free-float market cap、cash-flow quality、current ratio、inventory/receivable risk、TPEx all-stock sector PIT、TWSE exact daily market cap。

Readiness:
- ready_for_core_layer1_fuller_contract_refresh=true
- ready_for_radar_source_acquisition=true
- ready_for_experiments=false
- ready_for_formal=false
- ready_for_strategy_replay=false
- not_live_rule=true
- future_data_violation_count=0

Source quality counts:
- PIT-ready: 1
- proxy: 3
- blocked: 6

PIT / future-data notes:
- MOPS quarterly fundamentals can support leverage/solvency only if Core accepts conservative statutory available_date; exact per-company filing timestamp remains missing。
- Current/static sector/theme maps remain excluded。
- Free-float market cap must not be inferred from current/static data。

下一棒：
- 交 Core/Data 判斷是否建立 refreshed Layer1 fuller PIT contract。
- 若 Strategy Center 堅持 free-float / cash-flow / current-ratio / inventory-receivable 必須納入 Layer1，Radar/Data 需要另開 bounded route acquisition：MOPS cash-flow route likely t163sb06、balance-sheet/ratio route likely t163sb05、free-float official source route。
