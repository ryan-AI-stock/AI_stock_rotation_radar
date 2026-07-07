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


payload_capture = [
    {
        "api": "t164sb05",
        "endpoint": "https://mops.twse.com.tw/mops/api/t164sb05",
        "method": "POST",
        "payload_case": "latest_required_empty_keys",
        "sanitized_payload_schema": '{"companyId":"1101","dataType":"1","year":"","season":"","subsidiaryCompanyId":""}',
        "required_context": "Content-Type=application/json; Accept JSON; Origin/Referer/User-Agent accepted; no cookie persisted",
        "result": "code=200 query_success",
        "evidence": "1101 latest returned reportList rows with OCF/investing cash flow/capex labels",
        "direct_browser_equivalent_replay_feasible": True,
        "cookie_or_session_saved": False,
        "accepted_for_formal": False,
        "human_review_required": True,
        **FLAGS,
    },
    {
        "api": "t164sb03",
        "endpoint": "https://mops.twse.com.tw/mops/api/t164sb03",
        "method": "POST",
        "payload_case": "latest_required_empty_keys",
        "sanitized_payload_schema": '{"companyId":"1101","dataType":"1","year":"","season":"","subsidiaryCompanyId":""}',
        "required_context": "Content-Type=application/json; Accept JSON; Origin/Referer/User-Agent accepted; no cookie persisted",
        "result": "code=200 query_success",
        "evidence": "1101 latest returned reportList rows with inventory/receivables/current assets/current liabilities labels",
        "direct_browser_equivalent_replay_feasible": True,
        "cookie_or_session_saved": False,
        "accepted_for_formal": False,
        "human_review_required": True,
        **FLAGS,
    },
    {
        "api": "t164sb05",
        "endpoint": "https://mops.twse.com.tw/mops/api/t164sb05",
        "method": "POST",
        "payload_case": "custom_period_required_empty_subsidiary_key",
        "sanitized_payload_schema": '{"companyId":"1101","dataType":"2","year":"115","season":"1","subsidiaryCompanyId":""}',
        "required_context": "ROC year; season numeric 1-4; subsidiaryCompanyId key retained even when empty",
        "result": "code=200 query_success",
        "evidence": "1101 115Q1 returned rows=75",
        "direct_browser_equivalent_replay_feasible": True,
        "cookie_or_session_saved": False,
        "accepted_for_formal": False,
        "human_review_required": True,
        **FLAGS,
    },
    {
        "api": "t164sb03",
        "endpoint": "https://mops.twse.com.tw/mops/api/t164sb03",
        "method": "POST",
        "payload_case": "custom_period_required_empty_subsidiary_key",
        "sanitized_payload_schema": '{"companyId":"1101","dataType":"2","year":"115","season":"1","subsidiaryCompanyId":""}',
        "required_context": "ROC year; season numeric 1-4; subsidiaryCompanyId key retained even when empty",
        "result": "code=200 query_success",
        "evidence": "1101 115Q1 returned rows=70",
        "direct_browser_equivalent_replay_feasible": True,
        "cookie_or_session_saved": False,
        "accepted_for_formal": False,
        "human_review_required": True,
        **FLAGS,
    },
]

direct_replay = [
    {
        "test_case": "minimal_payload_missing_empty_keys",
        "api": "t164sb05/t164sb03",
        "payload_pattern": '{"companyId":"1101","dataType":"1"}',
        "result": "code=500 傳入參數異常",
        "feasibility": "blocked_if_empty_keys_are_dropped",
        "core_contract_implication": "runner must preserve year, season, subsidiaryCompanyId keys as empty strings for latest queries",
        **FLAGS,
    },
    {
        "test_case": "latest_payload_with_empty_keys",
        "api": "t164sb05/t164sb03",
        "payload_pattern": '{"companyId":"<ticker>","dataType":"1","year":"","season":"","subsidiaryCompanyId":""}',
        "result": "code=200 for 1101, 6488, 8299 bounded samples",
        "feasibility": "direct_replay_feasible_bounded",
        "core_contract_implication": "payload replay prerequisite passed for bounded samples; still needs PIT/asof join before full ingest",
        **FLAGS,
    },
    {
        "test_case": "custom_period_payload_with_empty_subsidiary",
        "api": "t164sb05/t164sb03",
        "payload_pattern": '{"companyId":"<ticker>","dataType":"2","year":"<ROC_YEAR>","season":"<1-4>","subsidiaryCompanyId":""}',
        "result": "code=200 for 1101 115Q1",
        "feasibility": "direct_replay_feasible_bounded",
        "core_contract_implication": "custom period can be replayed without browser UI when required keys are retained",
        **FLAGS,
    },
]

asof_route = [
    {
        "route_id": "mops_api_t163sb01_financial_report_announcement",
        "source": "MOPS 財務報告公告",
        "endpoint": "https://mops.twse.com.tw/mops/api/t163sb01",
        "payload_schema": '{"companyId":"<ticker>","dataType":"2","year":"<ROC_YEAR>","season":"<1-4>","subsidiaryCompanyId":""}',
        "bounded_samples": "1101 115Q1; 6488 115Q1",
        "sample_result": "code=200; announcement text and company/market/report year/season returned",
        "available_date_quality": "partial_official_announcement_text_no_exact_datetime",
        "asof_ready": False,
        "blocked_reason": "response does not expose precise disclosure/filing datetime; response datetime is query time and cannot be used as PIT available_date",
        "next_step": "find official MOPS filing timestamp route or local filing log before full PIT ingest",
        "future_data_violation_count": 0,
        "future_data_violation_risk": "medium_until_exact_disclosure_datetime_joined",
        **FLAGS,
    },
    {
        "route_id": "mops_api_t57sb01_q1_financial_report_pdf",
        "source": "MOPS 財務報告書",
        "endpoint": "https://mops.twse.com.tw/mops/api/t57sb01_q1",
        "payload_schema": '{"companyId":"<ticker>","year":"<ROC_YEAR>"}',
        "bounded_samples": "asset route inspected only",
        "sample_result": "route returns report URL/open-window contract, not proven disclosure datetime route",
        "available_date_quality": "source_route_candidate_not_asof_exact",
        "asof_ready": False,
        "blocked_reason": "financial report document route is not sufficient by itself as available_date",
        "next_step": "use only as document evidence unless timestamp source is separately materialized",
        "future_data_violation_count": 0,
        "future_data_violation_risk": "medium_until_exact_disclosure_datetime_joined",
        **FLAGS,
    },
]

tpex_samples = [
    {
        "ticker": "1101",
        "market_sample_role": "TWSE",
        "api": "t164sb05",
        "payload": '{"companyId":"1101","dataType":"2","year":"115","season":"1","subsidiaryCompanyId":""}',
        "code": 200,
        "year": "115",
        "season": "1",
        "rows": 75,
        "target_labels_found": "營業活動之淨現金流入（流出）; 投資活動之淨現金流入（流出）; 取得不動產、廠房及設備",
        "bounded_sample_confirmation": True,
        **FLAGS,
    },
    {
        "ticker": "1101",
        "market_sample_role": "TWSE",
        "api": "t164sb03",
        "payload": '{"companyId":"1101","dataType":"2","year":"115","season":"1","subsidiaryCompanyId":""}',
        "code": 200,
        "year": "115",
        "season": "1",
        "rows": 70,
        "target_labels_found": "應收帳款淨額; 存貨; 流動資產合計; 流動負債合計",
        "bounded_sample_confirmation": True,
        **FLAGS,
    },
    {
        "ticker": "6488",
        "market_sample_role": "TPEx",
        "api": "t164sb05",
        "payload": '{"companyId":"6488","dataType":"1","year":"","season":"","subsidiaryCompanyId":""}',
        "code": 200,
        "year": "115",
        "season": "1",
        "rows": 61,
        "target_labels_found": "營業活動之淨現金流入（流出）; 投資活動之淨現金流入（流出）; 取得不動產、廠房及設備",
        "bounded_sample_confirmation": True,
        **FLAGS,
    },
    {
        "ticker": "6488",
        "market_sample_role": "TPEx",
        "api": "t164sb03",
        "payload": '{"companyId":"6488","dataType":"1","year":"","season":"","subsidiaryCompanyId":""}',
        "code": 200,
        "year": "115",
        "season": "1",
        "rows": 57,
        "target_labels_found": "應收帳款淨額; 存貨; 流動資產合計; 流動負債合計",
        "bounded_sample_confirmation": True,
        **FLAGS,
    },
    {
        "ticker": "8299",
        "market_sample_role": "TPEx",
        "api": "t164sb05",
        "payload": '{"companyId":"8299","dataType":"1","year":"","season":"","subsidiaryCompanyId":""}',
        "code": 200,
        "year": "115",
        "season": "1",
        "rows": 67,
        "target_labels_found": "營業活動之淨現金流入（流出）; 投資活動之淨現金流入（流出）; 取得不動產、廠房及設備",
        "bounded_sample_confirmation": True,
        **FLAGS,
    },
    {
        "ticker": "8299",
        "market_sample_role": "TPEx",
        "api": "t164sb03",
        "payload": '{"companyId":"8299","dataType":"1","year":"","season":"","subsidiaryCompanyId":""}',
        "code": 200,
        "year": "115",
        "season": "1",
        "rows": 61,
        "target_labels_found": "應收帳款淨額; 存貨; 流動資產合計; 流動負債合計",
        "bounded_sample_confirmation": True,
        **FLAGS,
    },
]

label_policy = [
    {
        "canonical_field": "operating_cash_flow",
        "primary_labels": "營業活動之淨現金流入（流出）",
        "secondary_labels": "營運產生之現金流入（流出）",
        "policy": "exact label match first; trim full-width spaces; keep statement row sign as reported",
        "ambiguity": "low",
        "human_review_required": False,
        **FLAGS,
    },
    {
        "canonical_field": "investing_cash_flow",
        "primary_labels": "投資活動之淨現金流入（流出）",
        "secondary_labels": "",
        "policy": "exact label match first; keep sign as reported",
        "ambiguity": "low",
        "human_review_required": False,
        **FLAGS,
    },
    {
        "canonical_field": "capex_proxy",
        "primary_labels": "取得不動產、廠房及設備",
        "secondary_labels": "購置不動產、廠房及設備; 取得不動產及設備",
        "policy": "diagnostic FCF proxy only; do not call exact free cash flow without human-approved label basket",
        "ambiguity": "medium",
        "human_review_required": True,
        **FLAGS,
    },
    {
        "canonical_field": "inventory",
        "primary_labels": "存貨",
        "secondary_labels": "",
        "policy": "use balance-sheet ending balance row; not cash-flow inventory change row for inventory_risk stock measure",
        "ambiguity": "low",
        "human_review_required": False,
        **FLAGS,
    },
    {
        "canonical_field": "receivables_basket",
        "primary_labels": "應收帳款淨額; 應收票據淨額; 其他應收款淨額",
        "secondary_labels": "應收帳款－關係人淨額; 其他應收款－關係人淨額",
        "policy": "requires policy choice: trade-only vs broad receivables basket; keep components separate until approved",
        "ambiguity": "medium",
        "human_review_required": True,
        **FLAGS,
    },
]

blocked = [
    {
        "prerequisite": "MOPS_disclosure_datetime_asof_join",
        "status": "blocked_exact_partial_route_found",
        "evidence": "t163sb01 official announcement route returns announcement text but no precise filing/disclosure datetime",
        "impact": "full PIT ingest still blocked; cannot use quarter end or query time as available_date",
        "next_action": "Strategy/Core decide whether to accept conservative filing-deadline proxy for diagnostic only, or require exact filing timestamp route",
        **FLAGS,
    },
    {
        "prerequisite": "full_universe_ingest_runner",
        "status": "blocked_by_asof_and_policy",
        "evidence": "direct payload replay and TPEx bounded samples passed, but no full-universe runner should be built until asof and label policy decisions pass",
        "impact": "do not start all-stock download",
        "next_action": "Core can design runner contract; Radar should not execute full sweep in this task",
        **FLAGS,
    },
    {
        "prerequisite": "label_taxonomy_policy",
        "status": "partial_policy_draft_available",
        "evidence": "label mapping policy produced; capex proxy and receivables basket require human policy approval",
        "impact": "OCF/investing/inventory can be narrower; FCF proxy/receivable risk not formal-ready",
        "next_action": "Strategy Center/Core policy decision",
        **FLAGS,
    },
    {
        "prerequisite": "legacy_ajax_security_block",
        "status": "blocked_do_not_use",
        "evidence": "prior legacy ajax routes security-blocked; SPA routes now preferred",
        "impact": "legacy routes not needed for t164 current path",
        "next_action": "do not bypass security block",
        **FLAGS,
    },
]

readiness = {
    "task_id": "TASK-BACKTEST-RADAR-VNEXT-LAYER1-T164-PAYLOAD-ASOF-TPEX-FOLLOWUP-001",
    "status": "payload_and_tpex_sample_unlocked_asof_exact_blocked",
    "diagnostic_only": True,
    "source": "MOPS official SPA API and public SPA asset inspection",
    "coverage": "bounded samples only: 1101 TWSE custom 115Q1, 6488/8299 TPEx latest 115Q1, t163sb01 announcement route samples",
    "direct_browser_equivalent_payload_replay": True,
    "tpex_sample_confirmation": True,
    "mops_disclosure_datetime_asof_join": False,
    "label_taxonomy_policy_ready_for_human_review": True,
    "ready_for_core_payload_replay_contract": True,
    "ready_for_core_t164_cashflow_inventory_receivable_full_ingest": False,
    "ready_for_core_rerun": False,
    "ready_for_experiments": False,
    "ready_for_formal": False,
    "ready_for_strategy_replay": False,
    "future_data_violation_count": 0,
    "future_data_violation_risk": "medium_until_exact_disclosure_datetime_joined",
    "blocked_reason": "direct payload and TPEx samples passed, but exact PIT asof disclosure datetime remains blocked; FCF proxy/receivable basket need policy approval",
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
    "ready_for_core_payload_replay_contract": True,
    "ready_for_core_t164_cashflow_inventory_receivable_full_ingest": False,
    "formal_model_changed": False,
    "trade_decision_changed": False,
    "active_in_trade_decision": False,
    "report_changed": False,
    "portfolio_replay_executed": False,
    "not_live_rule": True,
    "files": [
        "t164_browser_equivalent_payload_capture.csv",
        "t164_direct_replay_feasibility_ledger.csv",
        "mops_disclosure_asof_source_route.csv",
        "t164_tpex_bounded_sample_confirmation.csv",
        "t164_label_taxonomy_policy.csv",
        "blocked_prerequisites_ledger.csv",
        "readiness_for_core_t164_cashflow_inventory_receivable_full_ingest.json",
        "manifest.json",
        "final_summary_zh.md",
    ],
}

write_csv("t164_browser_equivalent_payload_capture.csv", payload_capture)
write_csv("t164_direct_replay_feasibility_ledger.csv", direct_replay)
write_csv("mops_disclosure_asof_source_route.csv", asof_route)
write_csv("t164_tpex_bounded_sample_confirmation.csv", tpex_samples)
write_csv("t164_label_taxonomy_policy.csv", label_policy)
write_csv("blocked_prerequisites_ledger.csv", blocked)
write_json("readiness_for_core_t164_cashflow_inventory_receivable_full_ingest.json", readiness)
write_json("manifest.json", manifest)

summary = """# Layer1 t164 payload / asof / TPEx follow-up

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
"""
(OUT / "final_summary_zh.md").write_text(summary, encoding="utf-8")

print(f"wrote package to {OUT}")
