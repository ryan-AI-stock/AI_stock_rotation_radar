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
}


def write_csv(name, rows):
    with (OUT / name).open("w", encoding="utf-8-sig", newline="") as f:
        writer = csv.DictWriter(f, fieldnames=list(rows[0].keys()))
        writer.writeheader()
        writer.writerows(rows)


def write_json(name, data):
    (OUT / name).write_text(json.dumps(data, ensure_ascii=False, indent=2), encoding="utf-8")


inventory = [
    {
        "route_id": "mops_api_t05st01_historical_material_information",
        "source": "MOPS 歷史重大訊息",
        "endpoint": "https://mops.twse.com.tw/mops/api/t05st01",
        "method": "POST",
        "payload_schema": '{"companyId":"<ticker>","year":"<ROC_YEAR>","month":"<1-12|all>","firstDay":"<day|blank>","lastDay":"<day|blank>"}',
        "fields_found": "公司代號,公司名稱,發言日期,發言時間,主旨,詳細資料",
        "asof_quality": "official_announcement_timestamp_route",
        "bounded_sample_status": "pass_1101_twse_6488_tpex",
        "ready_for_core_asof_join_contract": True,
        "accepted_for_formal": False,
        "human_review_required": True,
        **FLAGS,
    },
    {
        "route_id": "mops_api_t05st01_detail_material_information_detail",
        "source": "MOPS 歷史重大訊息詳細資料",
        "endpoint": "https://mops.twse.com.tw/mops/api/t05st01_detail",
        "method": "POST",
        "payload_schema": '{"enterDate":"<ROC_YYYMMDD>","serialNumber":"<n>","companyId":"<ticker>","marketKind":"<sii|otc>"}',
        "fields_found": "發言日期,發言時間,主旨,符合條款,事實發生日,說明",
        "asof_quality": "official_announcement_timestamp_detail_route",
        "bounded_sample_status": "pass_1101_twse_6488_tpex",
        "ready_for_core_asof_join_contract": True,
        "accepted_for_formal": False,
        "human_review_required": True,
        **FLAGS,
    },
    {
        "route_id": "mops_api_t163sb01_financial_report_announcement_text",
        "source": "MOPS 財務報告公告",
        "endpoint": "https://mops.twse.com.tw/mops/api/t163sb01",
        "method": "POST",
        "payload_schema": '{"companyId":"<ticker>","dataType":"2","year":"<ROC_YEAR>","season":"<1-4>","subsidiaryCompanyId":""}',
        "fields_found": "財務報告公告文本, year, seasonName, marketName",
        "asof_quality": "official_announcement_text_no_timestamp",
        "bounded_sample_status": "pass_prior_package",
        "ready_for_core_asof_join_contract": False,
        "accepted_for_formal": False,
        "human_review_required": True,
        **FLAGS,
    },
    {
        "route_id": "mops_api_t57sb01_q1_financial_report_document",
        "source": "MOPS 財務報告書",
        "endpoint": "https://mops.twse.com.tw/mops/api/t57sb01_q1",
        "method": "POST",
        "payload_schema": '{"companyId":"<ticker>","year":"<ROC_YEAR>"}',
        "fields_found": "financial report document URL",
        "asof_quality": "document_route_no_timestamp",
        "bounded_sample_status": "pass_url_only",
        "ready_for_core_asof_join_contract": False,
        "accepted_for_formal": False,
        "human_review_required": True,
        **FLAGS,
    },
]

announcement_probe = [
    {
        "ticker": "1101",
        "market": "TWSE",
        "route_id": "mops_api_t05st01_historical_material_information",
        "payload": '{"companyId":"1101","year":"115","month":"5","firstDay":"1","lastDay":"31"}',
        "matched_subject": "公告本公司董事會通過115年第1季合併財務報告",
        "announcement_date": "115/05/13",
        "announcement_time": "19:18:38",
        "detail_api": "t05st01_detail",
        "detail_payload": '{"enterDate":"1150513","serialNumber":"1","companyId":"1101","marketKind":"sii"}',
        "fact_date": "115/05/13",
        "period_text": "115/01/01~115/03/31",
        "timestamp_level": "date_time",
        "source_quality": "official_material_information_timestamp",
        **FLAGS,
    },
    {
        "ticker": "6488",
        "market": "TPEx",
        "route_id": "mops_api_t05st01_historical_material_information",
        "payload": '{"companyId":"6488","year":"115","month":"5","firstDay":"1","lastDay":"31"}',
        "matched_subject": "公告本公司董事會通過115年第一季合併財務報告",
        "announcement_date": "115/05/05",
        "announcement_time": "15:11:12",
        "detail_api": "t05st01_detail",
        "detail_payload": '{"enterDate":"1150504","serialNumber":"1","companyId":"6488","marketKind":"otc"}',
        "fact_date": "115/05/05",
        "period_text": "115/01/01~115/03/31",
        "timestamp_level": "date_time",
        "source_quality": "official_material_information_timestamp",
        **FLAGS,
    },
    {
        "ticker": "1101",
        "market": "TWSE",
        "route_id": "mops_api_t05st01_historical_material_information",
        "payload": '{"companyId":"1101","year":"115","month":"all","firstDay":"","lastDay":""}',
        "matched_subject": "公告本公司董事會通過114年第4季合併財務報告",
        "announcement_date": "115/03/11",
        "announcement_time": "19:21:45",
        "detail_api": "t05st01_detail",
        "detail_payload": '{"enterDate":"1150311","serialNumber":"2","companyId":"1101","marketKind":"sii"}',
        "fact_date": "not probed in detail in this package",
        "period_text": "114年第4季 from subject",
        "timestamp_level": "date_time",
        "source_quality": "official_material_information_timestamp",
        **FLAGS,
    },
]

policy = [
    {
        "asof_candidate": "t05st01 發言日期 + 發言時間",
        "quality": "official timestamp-level public announcement route",
        "recommended_usage": "PIT available_at candidate for diagnostic/Core contract design after matching subject/period/ticker",
        "policy_question": "Can financial statement availability be anchored to material-information announcement timestamp when t164 statement data is already returned for same report period?",
        "risk": "announcement timestamp is a material-information disclosure timestamp, not necessarily the internal filing upload timestamp",
        "decision_needed": "Core/Strategy policy approval before formal/full PIT ingest",
        **FLAGS,
    },
    {
        "asof_candidate": "t05st01_detail 事實發生日",
        "quality": "official date-only fact date",
        "recommended_usage": "do not use as available_at; use only as cross-check for board approval date",
        "policy_question": "None; it is not the release timestamp",
        "risk": "can precede or equal public disclosure, but not sufficient for PIT availability",
        "decision_needed": "no use for asof except auxiliary evidence",
        **FLAGS,
    },
    {
        "asof_candidate": "t163sb01 財務報告公告 text route",
        "quality": "official announcement text, no exact timestamp",
        "recommended_usage": "link statement period to announcement narrative; not standalone available_at",
        "policy_question": "Can be used as text evidence only",
        "risk": "response datetime is query time and must not be used",
        "decision_needed": "blocked for timestamp",
        **FLAGS,
    },
    {
        "asof_candidate": "conservative filing-deadline proxy",
        "quality": "diagnostic-only proxy accepted by Strategy Center for staging",
        "recommended_usage": "diagnostic-only fallback when exact timestamp missing",
        "policy_question": "Already accepted only as diagnostic staging, not formal",
        "risk": "coarser than real disclosure and can delay availability; should not be formal-ready",
        "decision_needed": "keep explicit proxy flag",
        **FLAGS,
    },
]

blocked = [
    {
        "field": "internal_exact_filing_upload_timestamp",
        "status": "blocked",
        "evidence": "No bounded official route found that exposes internal filing/upload timestamp separate from public material-information announcement time",
        "impact": "formal exact filing timestamp remains blocked if policy requires upload timestamp rather than public announcement timestamp",
        "next_action": "Strategy/Core decide whether t05st01 public announcement timestamp is acceptable as official disclosure available_at",
        **FLAGS,
    },
    {
        "field": "date_only_announcement_route",
        "status": "superseded_by_timestamp_route",
        "evidence": "t05st01/t05st01_detail return both 發言日期 and 發言時間",
        "impact": "date-only official route not needed for sampled material-information path",
        "next_action": "Use date_time route where matched",
        **FLAGS,
    },
    {
        "field": "query_datetime",
        "status": "forbidden",
        "evidence": "API response datetime reflects query time, e.g. 115/07/07 10:52:13",
        "impact": "must not be used as PIT available_at",
        "next_action": "drop from asof contract",
        **FLAGS,
    },
    {
        "field": "quarter_end_date",
        "status": "forbidden",
        "evidence": "User/Strategy explicitly disallow quarter-end date as available date",
        "impact": "must not be used as PIT available_at",
        "next_action": "drop from asof contract",
        **FLAGS,
    },
]

readiness = {
    "task_id": "TASK-BACKTEST-RADAR-VNEXT-LAYER1-EXACT-FILING-TIMESTAMP-ROUTE-SEARCH-001",
    "status": "official_announcement_timestamp_route_found_policy_required_for_filing_asof",
    "diagnostic_only": True,
    "source": "MOPS official SPA API t05st01/t05st01_detail plus bounded asset inspection",
    "coverage": "bounded samples: 1101 TWSE 115Q1 and 114Q4 material-info timestamps; 6488 TPEx 115Q1 material-info timestamp",
    "official_announcement_timestamp_route_found": True,
    "exact_internal_filing_upload_timestamp_found": False,
    "date_only_official_route_only": False,
    "ready_for_core_exact_filing_asof_join": False,
    "ready_for_core_official_announcement_timestamp_asof_contract": True,
    "ready_for_experiments": False,
    "ready_for_formal": False,
    "ready_for_strategy_replay": False,
    "future_data_violation_count": 0,
    "future_data_violation_risk": "low_if_t05st01_announcement_timestamp_policy_approved_else_medium",
    "blocked_reason": "public announcement timestamp route found, but internal filing/upload timestamp remains blocked; policy decision needed before using announcement timestamp as available_at",
    "not_live_rule": True,
    "forward_returns_live_rule_usage": False,
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
    "ready_for_core_exact_filing_asof_join": False,
    "ready_for_core_official_announcement_timestamp_asof_contract": True,
    "formal_model_changed": False,
    "trade_decision_changed": False,
    "active_in_trade_decision": False,
    "report_changed": False,
    "portfolio_replay_executed": False,
    "not_live_rule": True,
    "files": [
        "exact_filing_timestamp_source_route_inventory.csv",
        "mops_financial_report_announcement_route_probe.csv",
        "official_announcement_date_vs_timestamp_policy_ledger.csv",
        "blocked_or_partial_asof_fields.csv",
        "readiness_for_core_exact_filing_asof_join.json",
        "manifest.json",
        "final_summary_zh.md",
    ],
}

write_csv("exact_filing_timestamp_source_route_inventory.csv", inventory)
write_csv("mops_financial_report_announcement_route_probe.csv", announcement_probe)
write_csv("official_announcement_date_vs_timestamp_policy_ledger.csv", policy)
write_csv("blocked_or_partial_asof_fields.csv", blocked)
write_json("readiness_for_core_exact_filing_asof_join.json", readiness)
write_json("manifest.json", manifest)

summary = """# Layer1 exact filing timestamp route search

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
"""
(OUT / "final_summary_zh.md").write_text(summary, encoding="utf-8")

print(f"wrote package to {OUT}")
