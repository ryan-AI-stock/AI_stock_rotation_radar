# Layer1 exact filing timestamp route search

Status: official_announcement_timestamp_route_found_policy_required_for_filing_asof

結論：
- 這是 bounded source route search，沒有回測、沒有 formal/report/trade decision change。
- 找到 MOPS official timestamp-level route：`/mops/api/t05st01` 歷史重大訊息與 `/mops/api/t05st01_detail` 詳細資料。
- 這條 route 回 `發言日期`、`發言時間`、主旨、事實發生日、說明；1101 上市與 6488 上櫃財報通過重大訊息樣本都成功。
- 這是官方公開重大訊息 timestamp，可交 Core 設計 `official_announcement_timestamp` asof join contract。
- 但尚未找到「內部 filing/upload timestamp」；若政策要求 filing upload time 而非 public announcement time，仍 blocked。

Sample evidence:
- 1101 TWSE 115Q1: `115/05/13 19:18:38`，主旨：公告董事會通過 115年第1季合併財務報告。
- 6488 TPEx 115Q1: `115/05/05 15:11:12`，主旨：公告董事會通過 115年第一季合併財務報告。
- 1101 TWSE 114Q4: `115/03/11 19:21:45`，主旨：公告董事會通過 114年第4季合併財務報告。

Readiness:
- official_announcement_timestamp_route_found=true
- exact_internal_filing_upload_timestamp_found=false
- ready_for_core_official_announcement_timestamp_asof_contract=true
- ready_for_core_exact_filing_asof_join=false
- ready_for_experiments=false
- ready_for_formal=false
- ready_for_strategy_replay=false
- future_data_violation_count=0
- not_live_rule=true

Policy note:
- 不可用 API response `datetime`，那是查詢時間。
- 不可用季度結束日。
- `t05st01` public announcement timestamp 是否可作財報 available_at，需要 Strategy/Core policy approval；若接受，可進 Core asof contract design。
- conservative filing-deadline proxy 仍只能 diagnostic-only staging。

Flags:
- formal_model_changed=false
- trade_decision_changed=false
- active_in_trade_decision=false
- report_changed=false
- portfolio_replay_executed=false
- ready_for_strategy_replay=false
- not_live_rule=true
