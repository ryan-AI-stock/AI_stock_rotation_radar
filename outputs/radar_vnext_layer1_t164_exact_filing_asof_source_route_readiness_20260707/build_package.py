import csv
import json
from pathlib import Path


OUT = Path(__file__).resolve().parent
FLAGS = {
    "formal_model_changed": False,
    "trade_decision_changed": False,
    "active_in_trade_decision": False,
    "report_changed": False,
    "portfolio_replay_executed": False,
    "ready_for_strategy_replay": False,
    "not_live_rule": True,
    "forward_returns_live_rule_usage": False,
}


def write_csv(name, rows):
    with (OUT / name).open("w", encoding="utf-8-sig", newline="") as f:
        writer = csv.DictWriter(f, fieldnames=list(rows[0].keys()))
        writer.writeheader()
        writer.writerows(rows)


def write_json(name, data):
    (OUT / name).write_text(json.dumps(data, ensure_ascii=False, indent=2), encoding="utf-8")


route_matrix = [
    {
        "route_id": "mops_api_t05st01_historical_material_information",
        "source": "MOPS 歷史重大訊息",
        "endpoint": "https://mops.twse.com.tw/mops/api/t05st01",
        "payload_schema": '{"companyId":"<ticker>","year":"<ROC_YEAR>","month":"<1-12|all>","firstDay":"<day|blank>","lastDay":"<day|blank>"}',
        "official_fields": "發言日期; 發言時間; 主旨; 詳細資料 api payload",
        "asof_candidate_type": "official_public_announcement_timestamp",
        "exact_filing_upload_timestamp": False,
        "official_publication_timestamp": True,
        "tpex_supported_bounded": True,
        "source_quality": "official_timestamp_route_for_material_information",
        "ready_for_core_t164_full_ingest_asof_join": False,
        "ready_for_core_official_announcement_timestamp_contract": True,
        "blocked_reason": "public announcement timestamp is official, but not proven to be exact filing/upload timestamp",
        **FLAGS,
    },
    {
        "route_id": "mops_api_t05st01_detail_material_information_detail",
        "source": "MOPS 歷史重大訊息詳細資料",
        "endpoint": "https://mops.twse.com.tw/mops/api/t05st01_detail",
        "payload_schema": '{"enterDate":"<ROC_YYYMMDD>","serialNumber":"<n>","companyId":"<ticker>","marketKind":"<sii|otc>"}',
        "official_fields": "發言日期; 發言時間; 主旨; 符合條款; 事實發生日; 說明",
        "asof_candidate_type": "official_public_announcement_timestamp_detail",
        "exact_filing_upload_timestamp": False,
        "official_publication_timestamp": True,
        "tpex_supported_bounded": True,
        "source_quality": "official_timestamp_detail_route_for_material_information",
        "ready_for_core_t164_full_ingest_asof_join": False,
        "ready_for_core_official_announcement_timestamp_contract": True,
        "blocked_reason": "detail confirms event timestamp and content, but some text says final upload occurs by regulatory deadline",
        **FLAGS,
    },
    {
        "route_id": "mops_api_t163sb01_financial_report_announcement",
        "source": "MOPS 財務報告公告",
        "endpoint": "https://mops.twse.com.tw/mops/api/t163sb01",
        "payload_schema": '{"companyId":"<ticker>","dataType":"2","year":"<ROC_YEAR>","season":"<1-4>","subsidiaryCompanyId":""}',
        "official_fields": "財務報告公告文本; marketName; year; seasonName",
        "asof_candidate_type": "official_announcement_text_no_timestamp",
        "exact_filing_upload_timestamp": False,
        "official_publication_timestamp": False,
        "tpex_supported_bounded": True,
        "source_quality": "official_text_route_no_timestamp",
        "ready_for_core_t164_full_ingest_asof_join": False,
        "ready_for_core_official_announcement_timestamp_contract": False,
        "blocked_reason": "no disclosure datetime; API response datetime is query time",
        **FLAGS,
    },
    {
        "route_id": "mops_api_t57sb01_q1_financial_report_document",
        "source": "MOPS 財務報告書 / doc.twse document URL",
        "endpoint": "https://mops.twse.com.tw/mops/api/t57sb01_q1",
        "payload_schema": '{"companyId":"<ticker>","year":"<ROC_YEAR>"}',
        "official_fields": "document URL",
        "asof_candidate_type": "document_route_no_authoritative_timestamp",
        "exact_filing_upload_timestamp": False,
        "official_publication_timestamp": False,
        "tpex_supported_bounded": True,
        "source_quality": "document_url_route_only",
        "ready_for_core_t164_full_ingest_asof_join": False,
        "ready_for_core_official_announcement_timestamp_contract": False,
        "blocked_reason": "HEAD probe returned no Last-Modified; even HTTP metadata would not be authoritative disclosure timestamp",
        **FLAGS,
    },
]

timestamp_probe = [
    {
        "ticker": "1101",
        "market": "TWSE",
        "route_id": "mops_api_t05st01",
        "payload": '{"companyId":"1101","year":"115","month":"5","firstDay":"1","lastDay":"31"}',
        "matched_subject": "公告本公司董事會通過115年第1季合併財務報告",
        "announcement_date": "115/05/13",
        "announcement_time": "19:18:38",
        "detail_route": "t05st01_detail",
        "detail_payload": '{"enterDate":"1150513","serialNumber":"1","companyId":"1101","marketKind":"sii"}',
        "fact_date": "115/05/13",
        "period": "115/01/01~115/03/31",
        "detail_note": "財報期間與期末總資產/負債等摘要欄位可由說明欄解析",
        "asof_quality": "official_public_announcement_timestamp",
        "exact_filing_upload_timestamp_found": False,
        **FLAGS,
    },
    {
        "ticker": "6488",
        "market": "TPEx",
        "route_id": "mops_api_t05st01",
        "payload": '{"companyId":"6488","year":"115","month":"5","firstDay":"1","lastDay":"31"}',
        "matched_subject": "公告本公司董事會通過115年第一季合併財務報告",
        "announcement_date": "115/05/05",
        "announcement_time": "15:11:12",
        "detail_route": "t05st01_detail",
        "detail_payload": '{"enterDate":"1150504","serialNumber":"1","companyId":"6488","marketKind":"otc"}',
        "fact_date": "115/05/05",
        "period": "115/01/01~115/03/31",
        "detail_note": "財報期間與期末總資產/負債等摘要欄位可由說明欄解析",
        "asof_quality": "official_public_announcement_timestamp",
        "exact_filing_upload_timestamp_found": False,
        **FLAGS,
    },
    {
        "ticker": "8299",
        "market": "TPEx",
        "route_id": "mops_api_t05st01",
        "payload": '{"companyId":"8299","year":"115","month":"5","firstDay":"1","lastDay":"31"}',
        "matched_subject": "公告董事會決議通過民國115年第1季合併財務報告",
        "announcement_date": "115/05/08",
        "announcement_time": "16:31:18",
        "detail_route": "t05st01_detail",
        "detail_payload": '{"enterDate":"1150421","serialNumber":"1","companyId":"8299","marketKind":"otc"}',
        "fact_date": "115/05/08",
        "period": "115/01/01-115/03/31",
        "detail_note": "說明欄含：相關詳細資訊將於主管機關規定期限內完成上傳作業",
        "asof_quality": "official_public_announcement_timestamp_not_upload_timestamp",
        "exact_filing_upload_timestamp_found": False,
        **FLAGS,
    },
    {
        "ticker": "1101",
        "market": "TWSE",
        "route_id": "mops_api_t05st01",
        "payload": '{"companyId":"1101","year":"115","month":"all","firstDay":"","lastDay":""}',
        "matched_subject": "公告本公司董事會通過114年第4季合併財務報告",
        "announcement_date": "115/03/11",
        "announcement_time": "19:21:45",
        "detail_route": "t05st01_detail",
        "detail_payload": '{"enterDate":"1150311","serialNumber":"2","companyId":"1101","marketKind":"sii"}',
        "fact_date": "not probed in this package",
        "period": "114年第4季 from subject",
        "detail_note": "cross-period evidence only",
        "asof_quality": "official_public_announcement_timestamp",
        "exact_filing_upload_timestamp_found": False,
        **FLAGS,
    },
]

tpex_probe = [
    {
        "ticker": "6488",
        "market": "TPEx",
        "route_id": "t05st01/t05st01_detail",
        "sample_result": "pass",
        "announcement_timestamp": "115/05/05 15:11:12",
        "matched_subject": "公告本公司董事會通過115年第一季合併財務報告",
        "universal_tpex_ready": False,
        "assessment": "bounded TPEx support confirmed, not universal readiness",
        **FLAGS,
    },
    {
        "ticker": "8299",
        "market": "TPEx",
        "route_id": "t05st01/t05st01_detail",
        "sample_result": "pass",
        "announcement_timestamp": "115/05/08 16:31:18",
        "matched_subject": "公告董事會決議通過民國115年第1季合併財務報告",
        "universal_tpex_ready": False,
        "assessment": "second bounded TPEx sample confirmed; exact upload timestamp still not available",
        **FLAGS,
    },
]

policy_options = [
    {
        "option": "official_public_announcement_timestamp",
        "source_route": "t05st01/t05st01_detail",
        "definition": "Use MOPS material-information 發言日期 + 發言時間 when subject/detail match the target financial report period",
        "quality": "official timestamp-level public disclosure event",
        "ready_for_core_contract_design": True,
        "ready_for_full_ingest_formal": False,
        "risk": "not necessarily exact internal filing/upload timestamp; may precede detailed report upload in some disclosures",
        "recommended_status": "policy_required_source_ready_candidate",
        **FLAGS,
    },
    {
        "option": "exact_internal_filing_upload_timestamp",
        "source_route": "not found",
        "definition": "Timestamp when financial report was uploaded/filed to MOPS/doc system",
        "quality": "blocked",
        "ready_for_core_contract_design": False,
        "ready_for_full_ingest_formal": False,
        "risk": "cannot build exact PIT full ingest without another official route or policy substitute",
        "recommended_status": "blocked",
        **FLAGS,
    },
    {
        "option": "statutory_filing_deadline_proxy",
        "source_route": "policy proxy, not source route",
        "definition": "Use regulatory filing deadline by report type as conservative proxy",
        "quality": "diagnostic-only staging proxy",
        "ready_for_core_contract_design": True,
        "ready_for_full_ingest_formal": False,
        "risk": "coarse and not actual disclosure; should not enter interim diagnostic unless explicitly accepted",
        "recommended_status": "diagnostic_only_candidate",
        **FLAGS,
    },
    {
        "option": "official_publication_date_only",
        "source_route": "not needed for sampled t05st01 because time exists",
        "definition": "Official date without time",
        "quality": "inferior to timestamp route",
        "ready_for_core_contract_design": False,
        "ready_for_full_ingest_formal": False,
        "risk": "date-only loses intraday order; only use if timestamp unavailable",
        "recommended_status": "superseded_by_t05st01_timestamp",
        **FLAGS,
    },
]

blocked = [
    {
        "field_or_policy": "exact_internal_filing_upload_timestamp",
        "status": "blocked",
        "evidence": "t05st01_detail gives public material-information timestamp and states in 8299 sample that detailed report information will be uploaded by regulatory deadline",
        "prohibited": False,
        "impact": "ready_for_core_t164_full_ingest_asof_join remains false if exact upload timestamp is required",
        "next_action": "Strategy/Core decide whether official public announcement timestamp is acceptable as defensible available_at",
        **FLAGS,
    },
    {
        "field_or_policy": "quarter_end_date",
        "status": "prohibited",
        "evidence": "quarter end precedes disclosure and is explicitly disallowed",
        "prohibited": True,
        "impact": "cannot be available_date",
        "next_action": "keep excluded from all contracts",
        **FLAGS,
    },
    {
        "field_or_policy": "query_response_datetime",
        "status": "prohibited",
        "evidence": "API response datetime is query time, not historical availability",
        "prohibited": True,
        "impact": "cannot be available_date",
        "next_action": "drop from all asof contracts",
        **FLAGS,
    },
    {
        "field_or_policy": "doc_twse_http_metadata",
        "status": "blocked_non_authoritative",
        "evidence": "bounded HEAD probe returned no Last-Modified for 1101/6488 document URLs; HTTP metadata would not be official disclosure time",
        "prohibited": False,
        "impact": "do not use document HTTP header as asof",
        "next_action": "use only document evidence, not timestamp",
        **FLAGS,
    },
]

readiness = {
    "task_id": "TASK-RADAR-DATA-VNEXT-LAYER1-T164-EXACT-FILING-ASOF-SOURCE-ROUTE-READINESS-001",
    "status": "official_public_announcement_timestamp_route_ready_exact_upload_timestamp_blocked",
    "diagnostic_only": True,
    "source": "MOPS official SPA API t05st01/t05st01_detail, t163sb01, t57sb01_q1 bounded probes",
    "coverage": "bounded route readiness only: TWSE 1101, TPEx 6488 and 8299, 115Q1; 1101 114Q4 cross-period sample",
    "official_public_announcement_timestamp_route_found": True,
    "exact_internal_filing_upload_timestamp_found": False,
    "mops_disclosure_datetime_asof_join_ready": False,
    "ready_for_core_official_announcement_timestamp_contract": True,
    "ready_for_core_t164_full_ingest_asof_join": False,
    "ready_for_experiments": False,
    "ready_for_formal": False,
    "ready_for_strategy_replay": False,
    "tpex_bounded_asof_route_confirmed": True,
    "tpex_universal_ready": False,
    "statutory_filing_deadline_proxy_status": "diagnostic_only_candidate",
    "quarter_end_date_status": "prohibited",
    "query_response_datetime_status": "prohibited",
    "future_data_violation_count": 0,
    "future_data_violation_risk": "low_if_official_announcement_timestamp_policy_approved_else_medium",
    "blocked_reason": "official public announcement timestamp route is defensible, but exact internal filing/upload timestamp remains blocked; full ingest asof join needs policy approval or another official upload timestamp route",
    **FLAGS,
}

manifest = {
    "task_id": readiness["task_id"],
    "created_at": "2026-07-07",
    "source": readiness["source"],
    "coverage": readiness["coverage"],
    "future_data_violation_count": 0,
    "ready_for_core_rerun": False,
    "ready_for_strategy_replay": False,
    "ready_for_core_t164_full_ingest_asof_join": False,
    "ready_for_core_official_announcement_timestamp_contract": True,
    "formal_model_changed": False,
    "trade_decision_changed": False,
    "active_in_trade_decision": False,
    "report_changed": False,
    "portfolio_replay_executed": False,
    "not_live_rule": True,
    "forward_returns_live_rule_usage": False,
    "files": [
        "radar_t164_exact_filing_asof_source_route_matrix.csv",
        "radar_t164_mops_disclosure_timestamp_probe.csv",
        "radar_t164_tpex_asof_route_probe.csv",
        "radar_t164_asof_policy_options.csv",
        "radar_t164_blocked_prohibited_ledger.csv",
        "readiness_for_core_t164_asof_source_route.json",
        "final_summary_zh.md",
        "manifest.json",
    ],
}

write_csv("radar_t164_exact_filing_asof_source_route_matrix.csv", route_matrix)
write_csv("radar_t164_mops_disclosure_timestamp_probe.csv", timestamp_probe)
write_csv("radar_t164_tpex_asof_route_probe.csv", tpex_probe)
write_csv("radar_t164_asof_policy_options.csv", policy_options)
write_csv("radar_t164_blocked_prohibited_ledger.csv", blocked)
write_json("readiness_for_core_t164_asof_source_route.json", readiness)
write_json("manifest.json", manifest)

summary = """# vNext Layer1 t164 exact filing as-of source route readiness

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
"""
(OUT / "final_summary_zh.md").write_text(summary, encoding="utf-8")

print(f"wrote package to {OUT}")
