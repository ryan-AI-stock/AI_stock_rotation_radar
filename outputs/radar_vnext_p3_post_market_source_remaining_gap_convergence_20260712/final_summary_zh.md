# P3 主線剩餘資料缺口收斂

## 結論

- 目前沒有仍可合法免費補抓的真 source gap；本次新增下載 0 rows，避免重抓與無限 probe。
- 7 月 Layer4 缺口是 Core 尚未依 frozen contract 重新 materialize，不是 Radar 缺行情或籌碼。不得把 2026-06-29 名單 carry-forward 成 exact PIT。
- 法人、融資融券、借券、外資持股 20D warmup 的 source_gap_count=0；剩餘列均為官方 zero/not-applicable。
- TAIFEX、全市場成交額、全市場融資、SOX/Nasdaq/VIX/USD-TWD source ready。
- Phase A/B 仍不可放行，主因是 Core 尚未計算 daily RS/MA/BIAS/KD、5/10/20D 籌碼 rollup、三群 market state，以及 7 月 exact Layer4。
- adjusted analysis 舊碼與 corporate-action no-event completeness 維持 structural/partial，只阻止 formal completeness，不再重探已耗盡免費路線。

## 下一棒

交 Core/Data 吸收本包，執行 daily feature materialization 與 7 月 exact Layer4 frozen-contract recompute。不得直接交 Experiments。

## 固定旗標

formal_model_changed=false；trade_decision_changed=false；active_in_trade_decision=false；report_changed=false；portfolio_replay_executed=false；ready_for_strategy_replay=false；ready_for_formal=false；not_live_rule=true；future_data_violation_count=0。
