# Layer1 cash-flow / inventory / receivable browser route capture

Status: partial_sample_unlocked_not_core_ingest_ready

結論：
- 這是 bounded browser route capture / readiness package，沒有回測、沒有 formal/report/trade decision change。
- MOPS 新版 SPA `t164sb05` 現金流量表 UI sample 成功，1101 latest 可解析 `營業活動之淨現金流入（流出）`、`投資活動之淨現金流入（流出）`、`取得不動產、廠房及設備`、現金流量表中的存貨/應收變動列。
- MOPS 新版 SPA `t164sb03` 合併資產負債表 UI sample 成功，1101 latest 可解析 `存貨`、`應收票據淨額`、`應收帳款淨額`、`其他應收款淨額`、`流動資產合計`、`流動負債合計`。
- 裸 POST 到 `/mops/api/t164sb05` 仍回 `code=500 傳入參數異常`，表示 full ingest 前還要補齊 browser-equivalent payload/context。
- TPEx 多檔樣本在這輪 browser-control 自動化不穩，未完成；不宣稱 TPEx universal ready。

Readiness:
- ready_for_core_rerun=false
- ready_for_core_parser_contract_design=true
- ready_for_core_layer1_cashflow_inventory_receivable_ingest=false
- ready_for_experiments=false
- ready_for_formal=false
- ready_for_strategy_replay=false
- future_data_violation_count=0
- future_data_violation_risk=medium_until_mops_disclosure_datetime_joined
- not_live_rule=true

下一棒：
- 不交 Experiments。
- 交 Core/Data 判斷是否先建立 `t164sb05/t164sb03` parser contract design，並要求補：MOPS disclosure datetime/asof join、direct/browser-equivalent payload replay、TPEx sample confirmation。
- 若 Strategy Center 要繼續補完整，下一步應是 bounded TPEx sample + SPA payload/context capture，不是全量 ingest。

Flags:
- formal_model_changed=false
- trade_decision_changed=false
- active_in_trade_decision=false
- report_changed=false
- portfolio_replay_executed=false
- ready_for_strategy_replay=false
- not_live_rule=true
