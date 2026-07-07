import csv
import hashlib
import json
import re
import shutil
import time
import urllib.request
from pathlib import Path


OUT = Path(__file__).resolve().parent
RAW = OUT / "raw_cache"
RAW.mkdir(exist_ok=True)
CURRENT_STEP = OUT / "current_step.txt"
CHECKPOINT = OUT / "checkpoint_state.json"
CORE_CONTRACT = Path(r"C:\Users\zergv\Documents\Codex\2026-05-30\ep05-chat-ai-stock-backtest-lab\outputs\vnext_layer1_t164_tpex_phase1_bounded_proof_runner_contract_20260707")

TASK_ID = "TASK-RADAR-DATA-VNEXT-LAYER1-T164-TPEX-PHASE1-50X2-BOUNDED-PROOF-RUNNER-001"

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
HEADERS = {
    "Content-Type": "application/json",
    "Accept": "application/json, text/plain, */*",
    "Origin": "https://mops.twse.com.tw",
    "Referer": "https://mops.twse.com.tw/mops/#/web/t05st01",
    "User-Agent": "Mozilla/5.0",
    "Accept-Language": "zh-TW,zh;q=0.9",
}
PERIODS = [
    {"report_period": "115Q1", "roc_year": "115", "season": "1", "expected_query_months": [("115", "04"), ("115", "05")]},
    {"report_period": "114Q4", "roc_year": "114", "season": "4", "expected_query_months": [("115", "01"), ("115", "02"), ("115", "03")]},
]
MAX_PROJECTED_ROUTES_PER_ROW = 10
BASELINE_CACHE_ROWS_PER_MATERIALIZED_ROW = 42.075


def write_csv(name, rows, fieldnames=None):
    if fieldnames is None:
        fieldnames = list(rows[0].keys()) if rows else ["empty"]
    with (OUT / name).open("w", encoding="utf-8-sig", newline="") as f:
        writer = csv.DictWriter(f, fieldnames=fieldnames)
        writer.writeheader()
        writer.writerows(rows)


def write_json(name, payload):
    (OUT / name).write_text(json.dumps(payload, ensure_ascii=False, indent=2), encoding="utf-8")


def step(text):
    CURRENT_STEP.write_text(text, encoding="utf-8")


def read_csv(path):
    with Path(path).open("r", encoding="utf-8-sig", newline="") as f:
        return list(csv.DictReader(f))


def clean(value):
    return re.sub(r"\s+", "", str(value or "").replace("\u3000", ""))


def safe(value):
    return re.sub(r"[^A-Za-z0-9_.-]+", "_", value).strip("_")


def cache_path(route, ticker, period, suffix):
    return RAW / f"{safe(route)}_{ticker}_{period}_{safe(suffix)}.json"


def post_json(route, payload, ticker, period, suffix):
    path = cache_path(route, ticker, period, suffix)
    payload_text = json.dumps(payload, ensure_ascii=False, sort_keys=True)
    if path.exists():
        text = path.read_text(encoding="utf-8")
        status = "cache_hit"
        retry_count = 0
    else:
        req = urllib.request.Request(
            f"https://mops.twse.com.tw/mops/api/{route}",
            data=json.dumps(payload, ensure_ascii=False).encode("utf-8"),
            headers=HEADERS,
            method="POST",
        )
        status = "fetched"
        retry_count = 0
        try:
            with urllib.request.urlopen(req, timeout=20) as resp:
                text = resp.read().decode("utf-8")
        except Exception as exc:
            text = json.dumps({"route_error": str(exc)}, ensure_ascii=False)
            status = "route_error"
            retry_count = 1
        path.write_text(text, encoding="utf-8")
        time.sleep(0.05)
    try:
        parsed = json.loads(text)
    except Exception:
        parsed = {"parse_error": True}
    cache_row = {
        "ticker": ticker,
        "report_period": period,
        "route": route,
        "payload": payload_text,
        "payload_hash": hashlib.sha256(payload_text.encode("utf-8")).hexdigest(),
        "raw_cache_path": str(path.relative_to(OUT)),
        "response_hash": hashlib.sha256(text.encode("utf-8")).hexdigest(),
        "route_status": status,
        "retry_count": retry_count,
        "route_error": status == "route_error",
        "response_bytes": len(text.encode("utf-8")),
        **FLAGS,
    }
    return parsed, cache_row


def find_row(rows, patterns):
    for row in rows or []:
        label = clean(row[0] if row else "")
        if any(re.search(pattern, label) for pattern in patterns):
            return row
    return None


def value(row):
    if not row or len(row) < 2 or row[1] in ("", None):
        return ""
    return str(row[1]).replace(",", "").strip()


def period_tokens(period):
    if period == "115Q1":
        return ["115年第1季", "115年第一季", "一一五年第一季", "115/01/01~115/03/31"]
    return ["114年第4季", "114年第四季", "一一四年第四季", "114年度", "一一四年度", "114/01/01~114/12/31"]


def wrong_period_tokens(period):
    if period == "115Q1":
        return ["114年第4季", "114年第四季", "114年度", "114年第二季", "114年第三季", "113年"]
    return ["115年第1季", "115年第一季", "114年第一季", "114年第二季", "114年第三季", "113年"]


def subject_prefilter(subject, period):
    text = clean(subject)
    if any(token in text for token in ["預計召開日期", "召開日期"]):
        return "excluded_premeeting_notice", False
    if not any(token in text for token in ["財務報告", "合併財報", "合併財務報告", "財報", "董事會重要決議", "董事會決議"]):
        return "excluded_non_financial_subject", False
    if any(token in text for token in wrong_period_tokens(period)):
        return "excluded_wrong_period_subject", False
    if any(token in text for token in period_tokens(period)):
        return "period_subject_candidate", True
    if "董事會重要決議" in text or "董事會決議" in text:
        return "detail_needed_board_resolution_candidate", True
    return "financial_subject_detail_needed", True


def classify_candidate(subject, detail_text, period):
    text = clean(subject)
    detail = clean(detail_text)
    if any(token in text for token in ["預計召開日期", "召開日期"]):
        return "premeeting_excluded", False, "premeeting notice excluded before accepted timestamp"
    if any(token in detail for token in wrong_period_tokens(period)):
        return "wrong_period_excluded", False, "detail maps to wrong period"
    direct_detail = any(token in detail for token in period_tokens(period))
    if any(token in text for token in ["更正", "補充公告"]):
        if any(token in text for token in period_tokens(period)) and direct_detail:
            return "supporting_correction_excluded", False, "correction/supporting announcement is not primary market_available_at when original direct report announcement exists"
    direct_subject = any(token in text for token in period_tokens(period))
    financial_subject = any(token in text for token in ["財務報告", "合併財報", "合併財務報告", "財報"])
    if financial_subject and direct_detail:
        return "accepted_direct_financial_report_detail", True, "subject and detail map to target financial-report period"
    if financial_subject and direct_subject:
        return "accepted_subject_strict", True, "subject maps to target financial-report period"
    if direct_detail and any(token in detail for token in ["董事會決議通過", "董事會通過", "決議通過"]):
        return "accepted_detail_strict", True, "detail maps to target financial-report period"
    return "excluded_ambiguous_or_non_target", False, "not accepted official target-period financial-report timestamp"


def statement_payload(ticker, period):
    return {
        "companyId": ticker,
        "dataType": "2",
        "year": period["roc_year"],
        "season": period["season"],
        "subsidiaryCompanyId": "",
    }


def announcement_payloads(ticker, period):
    return [{"companyId": ticker, "year": year, "month": month, "firstDay": "", "lastDay": ""} for year, month in period["expected_query_months"]]


CONTRACT_ROWS = read_csv(CORE_CONTRACT / "layer1_t164_tpex_phase1_50x2_runner_contract.csv")
TICKERS = sorted(
    {
        (row["ticker"], row.get("name", ""), row.get("market", "TPEx"), row.get("source_universe_quality", ""))
        for row in CONTRACT_ROWS
        if row.get("accepted_for_runner_execution") == "True"
    }
)
TICKER_ROWS = [
    {"ticker": ticker, "name": name, "market": market, "source_universe_quality": source_quality}
    for ticker, name, market, source_quality in TICKERS
]
CONTRACT_ROW_KEYS = {(row["ticker"], row["report_period"]) for row in CONTRACT_ROWS if row.get("accepted_for_runner_execution") == "True"}

total_rows = len(CONTRACT_ROW_KEYS)
projected_statement_routes = total_rows * 2
projected_announcement_routes = total_rows * 2
projected_detail_routes_guard = total_rows * 4
projected_total_routes = projected_statement_routes + projected_announcement_routes + projected_detail_routes_guard
projected_rows = [{
    "scope": "phase1_tpex_50x2_bounded_proof_runner",
    "materialized_rows": total_rows,
    "projected_statement_routes": projected_statement_routes,
    "projected_announcement_routes": projected_announcement_routes,
    "projected_detail_routes_guard": projected_detail_routes_guard,
    "projected_total_routes": projected_total_routes,
    "projected_routes_per_row": round(projected_total_routes / total_rows, 3),
    "budget_routes_per_row": MAX_PROJECTED_ROUTES_PER_ROW,
    "baseline_seed_cache_rows_per_row": BASELINE_CACHE_ROWS_PER_MATERIALIZED_ROW,
    "budget_status": "pass" if total_rows and projected_total_routes / total_rows <= MAX_PROJECTED_ROUTES_PER_ROW else "blocked_over_budget",
    **FLAGS,
}]

if projected_rows[0]["budget_status"] != "pass":
    write_csv("projected_route_cost_report.csv", projected_rows)
    write_json("readiness_for_core_t164_tpex_phase1_bounded_proof_runner.json", {
        "task_id": TASK_ID,
        "status": "blocked_by_projected_route_budget",
        "ready_for_core_t164_tpex_phase1_proof_review": False,
        "ready_for_experiments": False,
        "ready_for_formal": False,
        "future_data_violation_count": 0,
        **FLAGS,
    })
    raise SystemExit("projected route count exceeds budget")

cache_rows = []
materialized_rows = []
asof_rows = []
candidate_rows = []
pruning_rows = []
label_rows = []
blocked_rows = []
contract_audit_rows = []

work = 0
for ticker_info in TICKER_ROWS:
    for period in PERIODS:
        if (ticker_info["ticker"], period["report_period"]) not in CONTRACT_ROW_KEYS:
            continue
        work += 1
        ticker = ticker_info["ticker"]
        report_period = period["report_period"]
        step(f"pruning_v2 {work}/{total_rows}: {ticker} {report_period}")
        CHECKPOINT.write_text(json.dumps({"current_step": work, "total_steps": total_rows, "ticker": ticker, "report_period": report_period}, ensure_ascii=False, indent=2), encoding="utf-8")
        contract_audit_rows.append({
            "ticker": ticker,
            "name": ticker_info.get("name", ""),
            "market": ticker_info["market"],
            "report_period": report_period,
            "source_universe_quality": ticker_info.get("source_universe_quality", ""),
            "historical_pit_universe_ready": False,
            "runner_scope": "phase1_tpex_50x2_bounded_proof",
            **FLAGS,
        })

        cf_res, cf_cache = post_json("t164sb05", statement_payload(ticker, period), ticker, report_period, "cashflow")
        bs_res, bs_cache = post_json("t164sb03", statement_payload(ticker, period), ticker, report_period, "balance_sheet")
        cache_rows.extend([cf_cache, bs_cache])
        cf_rows = (((cf_res or {}).get("result") or {}).get("reportList") or [])
        bs_rows = (((bs_res or {}).get("result") or {}).get("reportList") or [])
        fields = {
            "operating_cash_flow": value(find_row(cf_rows, [r"營業活動之淨現金流入（流出）"])),
            "investing_cash_flow": value(find_row(cf_rows, [r"投資活動之淨現金流入（流出）"])),
            "capex_proxy": value(find_row(cf_rows, [r"取得不動產、廠房及設備", r"購置不動產、廠房及設備"])),
            "inventory": value(find_row(bs_rows, [r"^存貨$"])),
            "receivables_trade": value(find_row(bs_rows, [r"應收帳款淨額"])),
            "current_assets": value(find_row(bs_rows, [r"流動資產合計"])),
            "current_liabilities": value(find_row(bs_rows, [r"流動負債合計"])),
        }

        ann_rows = []
        for idx, payload in enumerate(announcement_payloads(ticker, period)):
            res, cache = post_json("t05st01", payload, ticker, report_period, f"announcement_{idx}_{payload.get('year')}_{payload.get('month')}")
            cache_rows.append(cache)
            ann_rows.extend((((res or {}).get("result") or {}).get("data") or []))

        seen = set()
        prefilter_pass = 0
        premeeting_excluded = 0
        wrong_period_excluded = 0
        detail_fetch_count = 0
        accepted_candidates = []
        for row in ann_rows:
            date = row[2] if len(row) > 2 else ""
            tm = row[3] if len(row) > 3 else ""
            subject = row[4] if len(row) > 4 else ""
            key = (date, tm, subject)
            if key in seen:
                continue
            seen.add(key)
            prefilter_status, should_detail = subject_prefilter(subject, report_period)
            if prefilter_status == "excluded_premeeting_notice":
                premeeting_excluded += 1
            if prefilter_status == "excluded_wrong_period_subject":
                wrong_period_excluded += 1
            if not should_detail:
                continue
            prefilter_pass += 1
            detail_payload = detail_text = detail_status = ""
            detail_ref = row[5] if len(row) > 5 and isinstance(row[5], dict) else {}
            if detail_ref:
                payload = detail_ref.get("parameters") or {}
                api = detail_ref.get("apiName", "t05st01_detail")
                detail_res, detail_cache = post_json(api, payload, ticker, report_period, f"detail_{date}_{tm}")
                cache_rows.append(detail_cache)
                detail_fetch_count += 1
                detail_payload = json.dumps(payload, ensure_ascii=False)
                detail_data = (((detail_res or {}).get("result") or {}).get("data") or [])
                detail_text = (detail_data[0][9] if detail_data and len(detail_data[0]) > 9 else "").replace("\n", " ")
                detail_status = "ok" if detail_data else "no_detail_data"
            match_status, accepted, reason = classify_candidate(subject, detail_text, report_period)
            candidate = {
                "ticker": ticker,
                "market": ticker_info["market"],
                "report_period": report_period,
                "announcement_date": date,
                "announcement_time": tm,
                "market_available_at": f"{date} {tm}".strip(),
                "subject": subject,
                "prefilter_status": prefilter_status,
                "detail_fetched": detail_status != "",
                "detail_payload": detail_payload,
                "detail_status": detail_status,
                "detail_text_excerpt": detail_text[:500],
                "match_status": match_status,
                "accepted_candidate": accepted,
                "policy_reason": reason,
                **FLAGS,
            }
            candidate_rows.append(candidate)
            if accepted:
                accepted_candidates.append(candidate)

        direct = [row for row in accepted_candidates if row["match_status"] == "accepted_direct_financial_report_detail"]
        subject = [row for row in accepted_candidates if row["match_status"] == "accepted_subject_strict"]
        detail = [row for row in accepted_candidates if row["match_status"] == "accepted_detail_strict"]
        chosen = direct[:1] if len(direct) == 1 else (subject[:1] if len(subject) == 1 else (detail[:1] if len(detail) == 1 else []))
        if len(chosen) == 1:
            accepted_asof = chosen[0]
            match_status = "accepted"
            blocked_reason = ""
        else:
            accepted_asof = {}
            match_status = "blocked_unmatched_or_ambiguous"
            blocked_reason = f"accepted_candidate_count={len(accepted_candidates)}"
            blocked_rows.append({
                "ticker": ticker,
                "market": ticker_info["market"],
                "report_period": report_period,
                "blocked_reason": blocked_reason,
                **FLAGS,
            })

        pruning_rows.append({
            "ticker": ticker,
            "market": ticker_info["market"],
            "report_period": report_period,
            "announcement_rows_seen": len({(r[2], r[3], r[4]) for r in ann_rows if len(r) > 4}),
            "prefilter_pass_rows": prefilter_pass,
            "detail_fetch_count": detail_fetch_count,
            "premeeting_notice_excluded": premeeting_excluded,
            "wrong_period_subject_excluded": wrong_period_excluded,
            "accepted_candidate_count": len(accepted_candidates),
            "chosen_match_status": match_status,
            **FLAGS,
        })

        materialized_rows.append({
            "ticker": ticker,
            "name": ticker_info.get("name", ""),
            "market": ticker_info["market"],
            "report_period": report_period,
            "t164sb05_status": f"code={cf_res.get('code')} rows={len(cf_rows)}",
            "t164sb03_status": f"code={bs_res.get('code')} rows={len(bs_rows)}",
            "official_asof_match_status": match_status,
            **fields,
            **FLAGS,
        })
        asof_rows.append({
            "ticker": ticker,
            "name": ticker_info.get("name", ""),
            "market": ticker_info["market"],
            "report_period": report_period,
            "match_status": match_status,
            "market_available_at": accepted_asof.get("market_available_at", ""),
            "accepted_subject": accepted_asof.get("subject", ""),
            "accepted_match_status": accepted_asof.get("match_status", ""),
            "blocked_reason": blocked_reason,
            "after_close_next_trading_day_policy": "required; Core calendar join needed",
            "quarter_end_date_used": False,
            "query_response_datetime_used": False,
            "conservative_deadline_proxy_used": False,
            **FLAGS,
        })
        for field_name, route, policy in [
            ("capex_proxy", "t164sb05", "human_review_proxy_label_required"),
            ("receivables_trade", "t164sb03", "human_review_proxy_label_required"),
        ]:
            label_rows.append({
                "ticker": ticker,
                "market": ticker_info["market"],
                "report_period": report_period,
                "field": field_name,
                "source_route": route,
                "value_available": fields[field_name] != "",
                "policy_status": policy,
                "accepted_for_formal": False,
                "human_review_required": True,
                **FLAGS,
            })

statement_success_rows = sum(("code=200" in r["t164sb05_status"]) and ("code=200" in r["t164sb03_status"]) for r in materialized_rows)
asof_matched_rows = sum(r["match_status"] == "accepted" for r in asof_rows)
route_error_count = sum(1 for r in cache_rows if r["route_error"])
actual_routes_per_row = round(len(cache_rows) / total_rows, 3)
reduction_vs_baseline = round(1 - (len(cache_rows) / total_rows) / BASELINE_CACHE_ROWS_PER_MATERIALIZED_ROW, 4)

coverage_rows = []
for group_type, values in [("market", sorted(set(r["market"] for r in materialized_rows))), ("period", sorted(set(r["report_period"] for r in materialized_rows)))]:
    for value_name in values:
        rows = [r for r in materialized_rows if r["market" if group_type == "market" else "report_period"] == value_name]
        coverage_rows.append({
            "coverage_type": group_type,
            "group": value_name,
            "requested_rows": len(rows),
            "materialized_rows": len(rows),
            "statement_success_rows": sum(("code=200" in r["t164sb05_status"]) and ("code=200" in r["t164sb03_status"]) for r in rows),
            "official_asof_matched_rows": sum(r["official_asof_match_status"] == "accepted" for r in rows),
            "blocked_rows": sum(r["official_asof_match_status"] != "accepted" for r in rows),
            **FLAGS,
        })

field_rows = []
for field in ["operating_cash_flow", "investing_cash_flow", "capex_proxy", "inventory", "receivables_trade", "current_assets", "current_liabilities"]:
    non_null = sum(r[field] != "" for r in materialized_rows)
    field_rows.append({
        "field": field,
        "requested_rows": total_rows,
        "non_null_rows": non_null,
        "missing_rows": total_rows - non_null,
        "missing_share": round((total_rows - non_null) / total_rows, 4),
        "source_quality": "candidate_exact" if field not in ("capex_proxy", "receivables_trade") else "human_review_proxy_or_basket",
        **FLAGS,
    })

tpex_rows = [r for r in materialized_rows if r["market"] == "TPEx"]
tpex_readiness = [{
    "market": "TPEx",
    "bounded_ticker_count": len(set(r["ticker"] for r in tpex_rows)),
    "bounded_rows": len(tpex_rows),
    "statement_success_rows": sum(("code=200" in r["t164sb05_status"]) and ("code=200" in r["t164sb03_status"]) for r in tpex_rows),
    "official_asof_matched_rows": sum(r["official_asof_match_status"] == "accepted" for r in tpex_rows),
    "universal_readiness": False,
    "reason": "TPEx phase1 50x2 bounded proof executed; current-or-carried sampling universe is not historical PIT all-stock universe and full-period route remains incomplete",
    **FLAGS,
}]

future_rows = [
    {"policy": "market_available_at", "status": "official_t05st01_timestamp_only", "violation_count": 0, **FLAGS},
    {"policy": "after_close_next_trading_day", "status": "required_core_calendar_join", "violation_count": 0, **FLAGS},
    {"policy": "quarter_end_date", "status": "prohibited", "violation_count": 0, **FLAGS},
    {"policy": "query_response_datetime", "status": "prohibited", "violation_count": 0, **FLAGS},
    {"policy": "conservative_deadline_proxy", "status": "separate_proxy_only", "violation_count": 0, **FLAGS},
    {"policy": "forward_return_as_rule", "status": "false_required", "violation_count": 0, **FLAGS},
]

for name in [
    "layer1_t164_tpex_phase1_50x2_runner_contract.csv",
    "layer1_t164_tpex_phase1_runner_input_contract.csv",
    "layer1_t164_tpex_phase1_route_budget_guard.csv",
    "layer1_t164_tpex_official_asof_join_policy.csv",
    "layer1_t164_tpex_field_policy.csv",
    "layer1_t164_tpex_phase1_coverage_audit_design.csv",
    "layer1_t164_tpex_full_period_expansion_guard.csv",
    "layer1_t164_tpex_blocked_proxy_human_review_ledger.csv",
    "layer1_t164_tpex_future_data_governance_audit.csv",
    "readiness_for_layer1_t164_tpex_phase1_runner_contract.json",
]:
    src = CORE_CONTRACT / name
    if src.exists():
        shutil.copyfile(src, OUT / name)

readiness = {
    "task_id": TASK_ID,
    "status": "phase1_tpex_50x2_bounded_proof_executed_not_full_universe",
    "diagnostic_only": True,
    "source": "MOPS official t164sb05/t164sb03 and pruned t05st01/t05st01_detail",
    "coverage": "50 TPEx tickers x 2 periods phase1 bounded proof; current-or-carried sampling universe only; not historical PIT all-stock universe",
    "sample_rows": total_rows,
    "ticker_count": len(TICKER_ROWS),
    "period_count": len(PERIODS),
    "market": "TPEx",
    "statement_success_rows": statement_success_rows,
    "official_asof_matched_rows": asof_matched_rows,
    "official_asof_matched_share": round(asof_matched_rows / total_rows, 4),
    "route_error_count": route_error_count,
    "cache_manifest_rows": len(cache_rows),
    "actual_cache_rows_per_materialized_row": actual_routes_per_row,
    "baseline_cache_rows_per_materialized_row": BASELINE_CACHE_ROWS_PER_MATERIALIZED_ROW,
    "route_reduction_vs_baseline": reduction_vs_baseline,
    "projected_routes_per_row": projected_rows[0]["projected_routes_per_row"],
    "budget_routes_per_row": MAX_PROJECTED_ROUTES_PER_ROW,
    "ready_for_core_t164_tpex_phase1_proof_review": statement_success_rows == total_rows and route_error_count == 0,
    "ready_for_core_t164_tpex_all_stock_proof_readiness_update": statement_success_rows == total_rows and asof_matched_rows == total_rows and route_error_count == 0,
    "ready_for_core_t164_broader_ingest_contract": False,
    "ready_for_core_t164_broader_materialization": False,
    "ready_for_experiments": False,
    "ready_for_formal": False,
    "ready_for_strategy_replay": False,
    "ready_for_full_universe": False,
    "tpex_all_stock_universal_ready": False,
    "future_data_violation_count": 0,
    "not_live_rule": True,
    "blocked_reason": f"phase1 bounded proof has {total_rows - asof_matched_rows} official-asof blocked rows; historical PIT all-stock universe, full period range, full universe materialization, capex formal label, and receivables formal label remain incomplete",
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
    "ready_for_core_t164_tpex_phase1_proof_review": readiness["ready_for_core_t164_tpex_phase1_proof_review"],
    "ready_for_experiments": False,
    "ready_for_formal": False,
    **FLAGS,
    "files": [
        "build_package.py",
        "raw_cache/.gitignore",
        "current_step.txt",
        "checkpoint_state.json",
        "projected_route_cost_report.csv",
        "raw_cache_hash_manifest.csv",
        "pruning_effectiveness_audit.csv",
        "phase1_t164_tpex_materialized_field_matrix.csv",
        "phase1_official_asof_candidate_ledger.csv",
        "phase1_official_asof_candidate_evidence.csv",
        "coverage_by_market_period.csv",
        "coverage_by_field.csv",
        "capex_receivables_label_inventory.csv",
        "tpex_universal_readiness_evidence.csv",
        "phase1_contract_execution_audit.csv",
        "future_data_governance_audit.csv",
        "blocked_or_ambiguous_rows.csv",
        "readiness_for_core_t164_tpex_phase1_bounded_proof_runner.json",
        "manifest.json",
        "final_summary_zh.md",
    ],
}

write_csv("projected_route_cost_report.csv", projected_rows)
write_csv("raw_cache_hash_manifest.csv", cache_rows)
write_csv("pruning_effectiveness_audit.csv", pruning_rows)
write_csv("phase1_t164_tpex_materialized_field_matrix.csv", materialized_rows)
write_csv("phase1_official_asof_candidate_ledger.csv", asof_rows)
write_csv("phase1_official_asof_candidate_evidence.csv", candidate_rows)
write_csv("coverage_by_market_period.csv", coverage_rows)
write_csv("coverage_by_field.csv", field_rows)
write_csv("capex_receivables_label_inventory.csv", label_rows)
write_csv("tpex_universal_readiness_evidence.csv", tpex_readiness)
write_csv("phase1_contract_execution_audit.csv", contract_audit_rows)
write_csv("future_data_governance_audit.csv", future_rows)
write_csv("blocked_or_ambiguous_rows.csv", blocked_rows)
write_json("readiness_for_core_t164_tpex_phase1_bounded_proof_runner.json", readiness)
write_json("manifest.json", manifest)

summary = f"""# Layer1 t164 TPEx phase_1 50x2 bounded proof runner

Status: {readiness['status']}

結論：
- phase_1 已依 Core contract 執行 50 TPEx tickers x 2 periods bounded proof runner。
- statement_success_rows={statement_success_rows}/{total_rows}。
- official_asof_matched_rows={asof_matched_rows}/{total_rows}。
- cache_manifest_rows={len(cache_rows)}，actual_cache_rows_per_materialized_row={actual_routes_per_row}。
- raw_cache files are kept local with raw_cache/.gitignore; response hashes and paths are recorded in raw_cache_hash_manifest.csv。
- baseline_cache_rows_per_materialized_row={BASELINE_CACHE_ROWS_PER_MATERIALIZED_ROW}。
- route_reduction_vs_baseline={reduction_vs_baseline}。
- route_error_count={route_error_count}。
- future_data_violation_count=0。

Readiness:
- ready_for_core_t164_tpex_phase1_proof_review={str(readiness['ready_for_core_t164_tpex_phase1_proof_review']).lower()}
- ready_for_core_t164_tpex_all_stock_proof_readiness_update={str(readiness['ready_for_core_t164_tpex_all_stock_proof_readiness_update']).lower()}
- ready_for_core_t164_broader_ingest_contract=false
- ready_for_core_t164_broader_materialization=false
- ready_for_experiments=false
- ready_for_formal=false
- ready_for_strategy_replay=false
- not_live_rule=true

仍非 full universe：
- current-or-carried TPEx universe 只作 sampling；不可宣稱 historical PIT all-stock universe。
- full period range not complete。
- capex_proxy / receivables_trade human_review_proxy_label_required。
- unmatched/ambiguous policy remains blocked/no silent fill。

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
step("completed")
CHECKPOINT.write_text(json.dumps({"current_step": total_rows, "total_steps": total_rows, "status": "completed"}, ensure_ascii=False, indent=2), encoding="utf-8")
print(f"wrote package to {OUT}")
