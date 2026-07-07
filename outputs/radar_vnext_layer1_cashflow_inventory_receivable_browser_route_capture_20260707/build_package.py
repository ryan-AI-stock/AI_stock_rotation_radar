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
    path = OUT / name
    with path.open("w", encoding="utf-8-sig", newline="") as f:
        writer = csv.DictWriter(f, fieldnames=list(rows[0].keys()))
        writer.writeheader()
        writer.writerows(rows)


def write_json(name, data):
    (OUT / name).write_text(json.dumps(data, ensure_ascii=False, indent=2), encoding="utf-8")


browser_route_capture_ledger = [
    {
        "route_id": "mops_spa_t164sb05_cashflow_latest_ui",
        "source": "MOPS 新版 SPA 現金流量表",
        "page_url": "https://mops.twse.com.tw/mops/#/web/t164sb05",
        "endpoint_candidate": "https://mops.twse.com.tw/mops/api/t164sb05",
        "method": "POST",
        "sanitized_payload_contract": "latest UI search: companyId + dataType=最新; custom route asset indicates companyId,dataType,year(民國年),season,subsidiaryCompanyId when applicable",
        "sample_scope": "bounded browser UI sample: 1101 latest",
        "capture_result": "rendered_table_success",
        "response_schema": "rendered HTML table from SPA result; asset parser expects JSON result.titles + result.reportList",
        "cookie_or_session_saved": False,
        "source_quality": "higher_quality_diagnostic_ui_rendered_sample",
        "accepted_for_formal": False,
        "human_review_required": True,
        **FLAGS,
    },
    {
        "route_id": "mops_spa_t164sb03_balance_sheet_latest_ui",
        "source": "MOPS 新版 SPA 合併資產負債表",
        "page_url": "https://mops.twse.com.tw/mops/#/web/t164sb03",
        "endpoint_candidate": "https://mops.twse.com.tw/mops/api/t164sb03",
        "method": "POST",
        "sanitized_payload_contract": "latest UI search: companyId + dataType=最新; same SPA input contract as t164sb05",
        "sample_scope": "bounded browser UI sample: 1101 latest",
        "capture_result": "rendered_table_success",
        "response_schema": "rendered HTML table from SPA result; asset parser expects JSON result.titles + result.reportList",
        "cookie_or_session_saved": False,
        "source_quality": "higher_quality_diagnostic_ui_rendered_sample",
        "accepted_for_formal": False,
        "human_review_required": True,
        **FLAGS,
    },
    {
        "route_id": "mops_spa_direct_api_without_browser_context",
        "source": "MOPS 新版 SPA API direct POST",
        "page_url": "https://mops.twse.com.tw/mops/api/t164sb05",
        "endpoint_candidate": "https://mops.twse.com.tw/mops/api/t164sb05",
        "method": "POST",
        "sanitized_payload_contract": '{"companyId":"1101","dataType":"1"} and {"companyId":"1101","dataType":"2","year":"113","season":"4"}',
        "sample_scope": "bounded direct POST check only",
        "capture_result": "blocked_code_500_parameter_exception_without_full_browser_context",
        "response_schema": "JSON code/message/result/datetime, result=null",
        "cookie_or_session_saved": False,
        "source_quality": "blocked_attempt_evidence",
        "accepted_for_formal": False,
        "human_review_required": True,
        **FLAGS,
    },
    {
        "route_id": "legacy_ajax_t05st39_t05st33_t05st31",
        "source": "MOPS legacy ajax routes from prior bounded attempts",
        "page_url": "https://mops.twse.com.tw/mops/web/ajax_t05st39 / ajax_t05st33 / ajax_t05st31",
        "endpoint_candidate": "legacy ajax redirect/security protected",
        "method": "POST",
        "sanitized_payload_contract": "prior bounded route attempt; no sensitive session captured",
        "sample_scope": "prior attempt evidence carried forward",
        "capture_result": "blocked_security_page",
        "response_schema": "HTML security block, not parseable statement table",
        "cookie_or_session_saved": False,
        "source_quality": "blocked_attempt_evidence",
        "accepted_for_formal": False,
        "human_review_required": True,
        **FLAGS,
    },
]

cashflow_route_payload_response_sample = [
    {
        "ticker": "1101",
        "market_sample_role": "TWSE sample",
        "route_id": "mops_spa_t164sb05_cashflow_latest_ui",
        "period_label": "民國115年第1季",
        "unit": "新台幣仟元",
        "header_current_period": "115年01月01日至115年03月31日",
        "header_comparator_period": "114年01月01日至114年03月31日",
        "operating_cash_flow_label": "營業活動之淨現金流入（流出）",
        "operating_cash_flow_current": "3358179",
        "operating_cash_flow_comparator": "6829705",
        "investing_cash_flow_label": "投資活動之淨現金流入（流出）",
        "investing_cash_flow_current": "4029757",
        "investing_cash_flow_comparator": "-13158475",
        "capex_proxy_label": "取得不動產、廠房及設備",
        "capex_proxy_current": "-8613010",
        "capex_proxy_comparator": "-8619515",
        "inventory_change_label": "存貨（增加）減少",
        "inventory_change_current": "-1769478",
        "receivable_change_label": "應收帳款（增加）減少",
        "receivable_change_current": "-416639",
        "schema_status": "rendered_table_parseable",
        "source_quality": "higher_quality_diagnostic_sample",
        "accepted_for_formal": False,
        "human_review_required": True,
        **FLAGS,
    }
]

balance_sheet_detail_payload_response_sample = [
    {
        "ticker": "1101",
        "market_sample_role": "TWSE sample",
        "route_id": "mops_spa_t164sb03_balance_sheet_latest_ui",
        "period_label": "民國115年第1季",
        "unit": "新台幣仟元",
        "header_current_date": "115年03月31日",
        "header_prior_quarter_date": "114年12月31日",
        "header_prior_year_date": "114年03月31日",
        "inventory_label": "存貨",
        "inventory_current": "20812552",
        "receivable_trade_label": "應收帳款淨額",
        "receivable_trade_current": "23524066",
        "notes_receivable_label": "應收票據淨額",
        "notes_receivable_current": "4085885",
        "other_receivable_label": "其他應收款淨額",
        "other_receivable_current": "4176862",
        "current_assets_label": "流動資產合計",
        "current_assets_current": "184722314",
        "current_liabilities_label": "流動負債合計",
        "current_liabilities_current": "82516661",
        "schema_status": "rendered_table_parseable",
        "source_quality": "higher_quality_diagnostic_sample",
        "accepted_for_formal": False,
        "human_review_required": True,
        **FLAGS,
    }
]

field_mapping = [
    {
        "field": "operating_cash_flow_quality",
        "source_route": "mops_spa_t164sb05_cashflow_latest_ui",
        "source_labels": "營業活動之淨現金流入（流出）; 營運產生之現金流入（流出）",
        "derivation_contract": "Core can map OCF / net_income or OCF / revenue after PIT statement contract; this package only verifies OCF label availability",
        "status": "sample_unlocked_not_full_contract",
        "exact_or_proxy": "PIT-ready route candidate, not full exact contract",
        "accepted_for_formal": False,
        "human_review_required": True,
        **FLAGS,
    },
    {
        "field": "free_cash_flow_quality",
        "source_route": "mops_spa_t164sb05_cashflow_latest_ui",
        "source_labels": "營業活動之淨現金流入（流出）; 取得不動產、廠房及設備",
        "derivation_contract": "diagnostic FCF proxy = OCF + capex row when capex outflow is negative; requires policy review because labels vary by company",
        "status": "sample_unlocked_proxy_policy_required",
        "exact_or_proxy": "proxy_requires_human_policy",
        "accepted_for_formal": False,
        "human_review_required": True,
        **FLAGS,
    },
    {
        "field": "inventory_risk",
        "source_route": "mops_spa_t164sb03_balance_sheet_latest_ui",
        "source_labels": "存貨; 流動資產合計",
        "derivation_contract": "inventory / current_assets or inventory growth after PIT statement panel is materialized",
        "status": "sample_unlocked_not_full_contract",
        "exact_or_proxy": "PIT-ready route candidate, not full exact contract",
        "accepted_for_formal": False,
        "human_review_required": True,
        **FLAGS,
    },
    {
        "field": "receivable_risk",
        "source_route": "mops_spa_t164sb03_balance_sheet_latest_ui",
        "source_labels": "應收票據淨額; 應收帳款淨額; 應收帳款－關係人淨額; 其他應收款淨額",
        "derivation_contract": "receivables basket / current_assets or receivables growth; requires taxonomy of receivable labels",
        "status": "sample_unlocked_not_full_contract",
        "exact_or_proxy": "PIT-ready route candidate, not full exact contract",
        "accepted_for_formal": False,
        "human_review_required": True,
        **FLAGS,
    },
]

pit_timing = [
    {
        "route_id": "mops_spa_t164sb05_cashflow_latest_ui",
        "period_observed": "民國115年第1季",
        "observed_current_date": "2026-07-07",
        "available_date_contract": "use MOPS disclosure/financial-report filing datetime for PIT asof; browser latest page alone is not enough for historical asof",
        "future_data_violation_risk": "medium_until_disclosure_datetime_joined",
        "future_data_violation_count": 0,
        "ready_for_core_ingest": False,
        **FLAGS,
    },
    {
        "route_id": "mops_spa_t164sb03_balance_sheet_latest_ui",
        "period_observed": "民國115年第1季",
        "observed_current_date": "2026-07-07",
        "available_date_contract": "use MOPS disclosure/financial-report filing datetime for PIT asof; browser latest page alone is not enough for historical asof",
        "future_data_violation_risk": "medium_until_disclosure_datetime_joined",
        "future_data_violation_count": 0,
        "ready_for_core_ingest": False,
        **FLAGS,
    },
]

blocked = [
    {
        "field_or_route": "direct_api_replay_without_browser_context",
        "status": "blocked",
        "evidence": "direct POST to /mops/api/t164sb05 with minimal sanitized payload returned JSON code=500 message=傳入參數異常",
        "blocked_reason": "missing SPA/browser-equivalent request context or full payload transformation",
        "next_step": "Core/Data or Radar/Data parser should use browser-equivalent route capture or inspect SPA store payload transformation before full ingest",
        **FLAGS,
    },
    {
        "field_or_route": "TPEx multi-sample t164sb05/t164sb03",
        "status": "partial_blocked",
        "evidence": "browser route capture succeeded for TWSE 1101; repeated automated TPEx/company switch attempts were unstable in browser-control runtime",
        "blocked_reason": "bounded browser control instability, not evidence that official route lacks TPEx support",
        "next_step": "small follow-up TPEx sample with stable browser session or direct SPA payload once context issue is solved",
        **FLAGS,
    },
    {
        "field_or_route": "legacy_ajax_security_block",
        "status": "blocked",
        "evidence": "prior bounded POST attempts to t05st39/t05st33/t05st31 returned security block pages",
        "blocked_reason": "legacy ajax routes security protected; no bypass attempted",
        "next_step": "prefer MOPS SPA t164sb05/t164sb03 routes over legacy ajax",
        **FLAGS,
    },
]

readiness = {
    "task_id": "TASK-BACKTEST-RADAR-VNEXT-LAYER1-CASHFLOW-INVENTORY-RECEIVABLE-BROWSER-ROUTE-CAPTURE-001",
    "status": "partial_sample_unlocked_not_core_ingest_ready",
    "diagnostic_only": True,
    "source_package_type": "bounded_browser_route_capture",
    "source": "MOPS official website, bounded browser UI route capture plus public SPA asset inspection",
    "coverage": "bounded sample only: 1101 latest t164sb05 cashflow and 1101 latest t164sb03 balance sheet; direct API attempt evidence; prior legacy security blocker carried forward",
    "cashflow_route_sample_unlocked": True,
    "balance_sheet_inventory_receivable_sample_unlocked": True,
    "direct_api_replay_unlocked": False,
    "tpex_sample_completed": False,
    "ready_for_core_rerun": False,
    "ready_for_core_layer1_cashflow_inventory_receivable_ingest": False,
    "ready_for_core_parser_contract_design": True,
    "ready_for_experiments": False,
    "ready_for_formal": False,
    "ready_for_strategy_replay": False,
    "future_data_violation_count": 0,
    "future_data_violation_risk": "medium_until_mops_disclosure_datetime_joined",
    "blocked_reason": "sample route/schema unlocked, but full PIT ingest needs disclosure datetime join, stable direct/browser-equivalent payload capture, and TPEx sample confirmation",
    **FLAGS,
}

manifest = {
    "task_id": readiness["task_id"],
    "created_at": "2026-07-07",
    "source": "MOPS official website, bounded browser UI route capture plus public SPA asset inspection",
    "coverage": "bounded sample only: 1101 latest t164sb05 cashflow and 1101 latest t164sb03 balance sheet; direct API attempt evidence; prior legacy security blocker carried forward",
    "future_data_violation_count": 0,
    "ready_for_core_rerun": False,
    "ready_for_strategy_replay": False,
    "formal_model_changed": False,
    "trade_decision_changed": False,
    "active_in_trade_decision": False,
    "report_changed": False,
    "portfolio_replay_executed": False,
    "not_live_rule": True,
    "files": [
        "browser_route_capture_ledger.csv",
        "cashflow_route_payload_response_sample.csv",
        "balance_sheet_detail_payload_response_sample.csv",
        "field_mapping_cashflow_inventory_receivable.csv",
        "pit_timing_capture_audit.csv",
        "blocked_security_or_policy_ledger.csv",
        "readiness_for_core_layer1_cashflow_inventory_receivable_ingest.json",
        "manifest.json",
        "final_summary_zh.md",
    ],
}

write_csv("browser_route_capture_ledger.csv", browser_route_capture_ledger)
write_csv("cashflow_route_payload_response_sample.csv", cashflow_route_payload_response_sample)
write_csv("balance_sheet_detail_payload_response_sample.csv", balance_sheet_detail_payload_response_sample)
write_csv("field_mapping_cashflow_inventory_receivable.csv", field_mapping)
write_csv("pit_timing_capture_audit.csv", pit_timing)
write_csv("blocked_security_or_policy_ledger.csv", blocked)
write_json("readiness_for_core_layer1_cashflow_inventory_receivable_ingest.json", readiness)
write_json("manifest.json", manifest)

summary = """# Layer1 cash-flow / inventory / receivable browser route capture

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
"""
(OUT / "final_summary_zh.md").write_text(summary, encoding="utf-8")

print(f"wrote package to {OUT}")
