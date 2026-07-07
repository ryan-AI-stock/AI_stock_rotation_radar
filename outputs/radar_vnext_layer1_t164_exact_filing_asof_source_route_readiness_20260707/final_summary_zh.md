# vNext Layer1 t164 exact filing as-of source route readiness

Status: official_public_announcement_timestamp_route_ready_exact_upload_timestamp_blocked

結論：
- 這是 bounded source route readiness，沒有回測、沒有 formal/report/trade decision change。
- MOPS `t05st01/t05st01_detail` 是 official timestamp-level public announcement route，可取得財報重大訊息的 `發言日期` + `發言時間`。
- TWSE/TPEx bounded samples 成功：1101、6488、8299 都可找到財報通過重大訊息 timestamp。
- 但這仍不是 exact internal filing/upload timestamp；8299 detail 明確寫「詳細資訊將於主管機關規定期限內完成上傳作業」，表示 public announcement timestamp 可能早於 detailed report upload。
- 因此 `ready_for_core_t164_full_ingest_asof_join=false`，但 `ready_for_core_official_announcement_timestamp_contract=true`。

Sample evidence:
- 1101 TWSE 115Q1: 115/05/13 19:18:38，公告董事會通過 115年第1季合併財務報告。
- 6488 TPEx 115Q1: 115/05/05 15:11:12，公告董事會通過 115年第一季合併財務報告。
- 8299 TPEx 115Q1: 115/05/08 16:31:18，公告董事會決議通過民國115年第1季合併財務報告。

Readiness:
- official_public_announcement_timestamp_route_found=true
- exact_internal_filing_upload_timestamp_found=false
- mops_disclosure_datetime_asof_join_ready=false
- ready_for_core_official_announcement_timestamp_contract=true
- ready_for_core_t164_full_ingest_asof_join=false
- ready_for_experiments=false
- ready_for_formal=false
- ready_for_strategy_replay=false
- future_data_violation_count=0
- not_live_rule=true

Policy:
- quarter_end_date=prohibited。
- query_response_datetime=prohibited。
- statutory filing deadline proxy 仍只能 diagnostic-only candidate。
- 若 Strategy/Core 接受 public material-information timestamp 作 defensible available_at，Core 可設計 announcement timestamp contract；若要求 exact upload timestamp，仍 blocked。

Flags:
- formal_model_changed=false
- trade_decision_changed=false
- active_in_trade_decision=false
- report_changed=false
- portfolio_replay_executed=false
- ready_for_strategy_replay=false
- not_live_rule=true
- forward_returns_live_rule_usage=false
