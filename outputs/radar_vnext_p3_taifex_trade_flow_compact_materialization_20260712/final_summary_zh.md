# P3 TAIFEX trade-flow + OI compact

- 重用既有官方728日實體compact，沒有新增下載。
- trade net口數/金額與OI net口數/金額已同表materialize，無缺值、無重複。
- trade flow不是OI change proxy。
- 官方range下載未提供exact publication timestamp，因此不杜撰market_available_at；以次一交易日PIT eligible date join。
- ready_for_core_p3_taifex_trade_flow_absorption=true；future_data_violation_count=0。
- 下一棒交Core/Data重算full_spec_v2/rechain，不直接交Experiments。
