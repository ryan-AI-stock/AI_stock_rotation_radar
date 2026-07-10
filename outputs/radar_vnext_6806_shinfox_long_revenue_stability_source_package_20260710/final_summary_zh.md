# 6806 森崴能源 long revenue source package

## 結論

- 已完成 bounded source package，只針對 6806 森崴能源。
- source: MOPS official t21sc03 monthly revenue static HTML `pub` route + `ajax_t05st10_ifrs` company-specific gap fill。
- coverage: 2021-01 到 2026-05。
- accepted rows: 65。
- missing months: 1。
- future_data_violation_count=0。
- ready_for_core_6806_long_revenue_stability_ingest=true。

## PIT / asof policy

- available_date 使用保守口徑：營收月份次月 10 日，遇週末順延。
- 不使用 revenue period end date 當 available_date。
- 不使用 retrieval time / query response datetime 當 available_date。
- 這是 official higher-quality diagnostic PIT candidate，不是 formal exact filing timestamp。

## 邊界

- formal_model_changed=false
- trade_decision_changed=false
- active_in_trade_decision=false
- report_changed=false
- portfolio_replay_executed=false
- ready_for_strategy_replay=false
- ready_for_formal=false
- not_live_rule=true
- forward_returns_live_rule_usage=false

## 下一棒

交 Core/Data absorb 6806 monthly revenue rows，刷新 6806 sanity check：long revenue stability / revenue lumpiness / project-based risk proxy。注意 source_market_code=pub，不可假裝成 TWSE listed-company t21sc03 route。
完成後如果下一棒明確，請直接指派下一個 thread；如果下一棒不明確，請回報 Strategy Center 判斷。不要完成後停住不回報。
