# Layer1 t164 payload / asof / TPEx follow-up

Status: payload_and_tpex_sample_unlocked_asof_exact_blocked

結論：
- 這是 bounded source/payload/asof readiness，沒有回測、沒有 formal/report/trade decision change。
- `/mops/api/t164sb05` 與 `/mops/api/t164sb03` direct/browser-equivalent replay 已解鎖：payload 必須保留 `year`, `season`, `subsidiaryCompanyId` 空字串 key；只送 `companyId + dataType` 會 `code=500 傳入參數異常`。
- TPEx bounded sample 已確認：`6488`、`8299` 的 t164sb05/t164sb03 latest sample 都 `code=200`，可解析現金流、存貨、應收、流動資產/負債等目標 label。
- `t163sb01` 財務報告公告 route 可作官方 announcement text source，但沒有精確 filing/disclosure datetime；不能把季度結束日或查詢時間當 available_date。
- label taxonomy policy 已產出草案；FCF proxy 與 receivables basket 仍需 human policy approval。

Readiness:
- ready_for_core_payload_replay_contract=true
- ready_for_core_t164_cashflow_inventory_receivable_full_ingest=false
- ready_for_core_rerun=false
- ready_for_experiments=false
- ready_for_formal=false
- ready_for_strategy_replay=false
- future_data_violation_count=0
- future_data_violation_risk=medium_until_exact_disclosure_datetime_joined
- not_live_rule=true

仍 blocked:
- exact MOPS disclosure datetime / asof join
- full-universe ingest runner
- FCF proxy / receivables basket formal policy
- legacy ajax route remains blocked and should not be bypassed

下一棒：
- 不交 Experiments。
- 回 Strategy Center 判斷：是否接受保守 filing-deadline proxy 作 diagnostic-only，或要求 Radar/Data/Core 繼續找 exact official filing timestamp route。
- Core/Data 可先使用本包建立 payload replay contract，但 full PIT ingest 仍需 asof 決策。

Flags:
- formal_model_changed=false
- trade_decision_changed=false
- active_in_trade_decision=false
- report_changed=false
- portfolio_replay_executed=false
- ready_for_strategy_replay=false
- not_live_rule=true
