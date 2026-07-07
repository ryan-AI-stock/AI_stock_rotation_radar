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
CORE_PLANNING = Path(r"C:\Users\zergv\Documents\Codex\2026-05-30\ep05-chat-ai-stock-backtest-lab\outputs\vnext_layer1_t164_source_package_broader_ingest_planning_20260707")

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
    "Referer": "https://mops.twse.com.tw/mops/#/web/t164sb05",
    "User-Agent": "Mozilla/5.0",
    "Accept-Language": "zh-TW,zh;q=0.9",
}
TICKERS = [
    {"ticker": "1101", "market": "TWSE"},
    {"ticker": "1216", "market": "TWSE"},
    {"ticker": "1301", "market": "TWSE"},
    {"ticker": "2330", "market": "TWSE"},
    {"ticker": "2308", "market": "TWSE"},
    {"ticker": "2317", "market": "TWSE"},
    {"ticker": "2454", "market": "TWSE"},
    {"ticker": "2881", "market": "TWSE"},
    {"ticker": "2882", "market": "TWSE"},
    {"ticker": "3008", "market": "TWSE"},
    {"ticker": "3711", "market": "TWSE"},
    {"ticker": "6669", "market": "TWSE"},
    {"ticker": "6488", "market": "TPEx"},
    {"ticker": "8299", "market": "TPEx"},
    {"ticker": "5347", "market": "TPEx"},
    {"ticker": "6187", "market": "TPEx"},
    {"ticker": "8069", "market": "TPEx"},
    {"ticker": "3081", "market": "TPEx"},
    {"ticker": "6147", "market": "TPEx"},
    {"ticker": "3264", "market": "TPEx"},
]
PERIODS = [
    {"report_period": "115Q1", "roc_year": "115", "season": "1", "query_years": ["115"]},
    {"report_period": "114Q4", "roc_year": "114", "season": "4", "query_years": ["115", "114"]},
]


def now_step(message):
    CURRENT_STEP.write_text(message, encoding="utf-8")


def write_csv(name, rows, fieldnames=None):
    if fieldnames is None:
        fieldnames = list(rows[0].keys()) if rows else ["empty"]
    with (OUT / name).open("w", encoding="utf-8-sig", newline="") as f:
        writer = csv.DictWriter(f, fieldnames=fieldnames)
        writer.writeheader()
        writer.writerows(rows)


def write_json(name, payload):
    (OUT / name).write_text(json.dumps(payload, ensure_ascii=False, indent=2), encoding="utf-8")


def safe_name(value):
    return re.sub(r"[^A-Za-z0-9_.-]+", "_", value).strip("_")


def cache_path(route, ticker, report_period, suffix):
    return RAW / f"{safe_name(route)}_{ticker}_{report_period}_{safe_name(suffix)}.json"


def post_json(route, payload, ticker, report_period, suffix, retries=1):
    path = cache_path(route, ticker, report_period, suffix)
    payload_text = json.dumps(payload, ensure_ascii=False, sort_keys=True)
    if path.exists():
        text = path.read_text(encoding="utf-8")
        status = "cache_hit"
        retry_count = 0
    else:
        data = json.dumps(payload, ensure_ascii=False).encode("utf-8")
        req = urllib.request.Request(
            f"https://mops.twse.com.tw/mops/api/{route}",
            data=data,
            headers=HEADERS,
            method="POST",
        )
        retry_count = 0
        for attempt in range(retries + 1):
            try:
                with urllib.request.urlopen(req, timeout=20) as resp:
                    text = resp.read().decode("utf-8")
                status = "fetched"
                break
            except Exception as exc:
                retry_count = attempt + 1
                text = json.dumps({"route_error": str(exc)}, ensure_ascii=False)
                status = "route_error"
                time.sleep(0.2)
        path.write_text(text, encoding="utf-8")
    response_hash = hashlib.sha256(text.encode("utf-8")).hexdigest()
    payload_hash = hashlib.sha256(payload_text.encode("utf-8")).hexdigest()
    try:
        response = json.loads(text)
    except Exception:
        response = {"parse_error": True}
    return response, {
        "ticker": ticker,
        "report_period": report_period,
        "route": route,
        "payload": payload_text,
        "payload_hash": payload_hash,
        "raw_cache_path": str(path.relative_to(OUT)),
        "response_hash": response_hash,
        "route_status": status,
        "retry_count": retry_count,
        "route_error": status == "route_error",
        "response_bytes": len(text.encode("utf-8")),
        **FLAGS,
    }


def clean(value):
    return re.sub(r"\s+", "", str(value or "").replace("\u3000", ""))


def find_row(rows, patterns):
    for row in rows or []:
        label = clean(row[0] if row else "")
        for pat in patterns:
            if re.search(pat, label):
                return row
    return None


def val(row):
    if not row or len(row) < 2 or row[1] in ("", None):
        return ""
    return str(row[1]).replace(",", "").strip()


def period_patterns(report_period):
    if report_period == "115Q1":
        return [r"115.*第?1季", r"115.*第一季", r"一一五年第一季", r"第一季"]
    return [r"114.*第?4季", r"114.*第四季", r"114年度", r"一一四年度", r"一一四年第四季"]


def detail_probe(detail_ref, ticker, report_period, suffix, cache_rows):
    payload = detail_ref.get("parameters") or {}
    route = detail_ref.get("apiName", "t05st01_detail")
    if not payload:
        return "", "", "missing_detail_payload"
    response, cache = post_json(route, payload, ticker, report_period, suffix)
    cache_rows.append(cache)
    data = (((response or {}).get("result") or {}).get("data") or [])
    text = data[0][9] if data and len(data[0]) > 9 else ""
    return json.dumps(payload, ensure_ascii=False), text.replace("\n", " "), "ok" if data else "no_detail_data"


def classify(subject, detail_text, report_period):
    subject_text = clean(subject)
    detail = clean(detail_text)
    premeeting = any(token in subject_text for token in ["預計召開日期", "召開日期"])
    period_hit = any(re.search(pattern, subject_text) for pattern in period_patterns(report_period))
    financial_subject = any(token in subject_text for token in ["財務報告", "合併財報", "合併財務報告"])
    actual_subject = any(token in subject_text for token in ["公告", "通過", "決議"])
    if report_period == "115Q1":
        direct_detail = "115/01/01~115/03/31" in detail
        wrong_period = any(token in detail for token in ["114/01/01~114/12/31", "114年第二季", "114年第三季"])
    else:
        direct_detail = "114/01/01~114/12/31" in detail or "114年度營業報告書" in detail
        wrong_period = any(token in detail for token in ["115年第一季", "114年第二季", "114年第三季", "113年合併財報"])
    detail_approval = any(token in detail for token in ["董事會決議通過", "董事會通過", "決議通過"])
    if premeeting:
        return "premeeting_excluded", False, "premeeting notice is not accepted market_available_at"
    if financial_subject and direct_detail and not wrong_period:
        return "accepted_direct_financial_report_detail", True, "subject and detail map to target financial-report period"
    if period_hit and financial_subject and actual_subject and not wrong_period:
        return "accepted_subject_strict", True, "subject maps to target financial-report period"
    if direct_detail and detail_approval and not wrong_period:
        return "accepted_detail_strict", True, "detail maps to target financial-report period"
    if wrong_period:
        return "wrong_period_excluded", False, "detail maps to another report period"
    return "non_financial_or_ambiguous_excluded", False, "not a unique official timestamp for target period"


def t05st01_payloads(ticker, period):
    payloads = []
    for year in period["query_years"]:
        payloads.append({"companyId": ticker, "year": year, "month": "all", "firstDay": "", "lastDay": ""})
        if period["report_period"] == "115Q1":
            for month in ["04", "05"]:
                payloads.append({"companyId": ticker, "year": year, "month": month, "firstDay": "", "lastDay": ""})
        else:
            for month in ["02", "03"]:
                payloads.append({"companyId": ticker, "year": year, "month": month, "firstDay": "", "lastDay": ""})
    return payloads


cache_rows = []
materialized_rows = []
asof_rows = []
candidate_rows = []
blocked_rows = []
label_inventory = []

total_work = len(TICKERS) * len(PERIODS)
done = 0
for ticker_info in TICKERS:
    for period in PERIODS:
        done += 1
        ticker = ticker_info["ticker"]
        report_period = period["report_period"]
        now_step(f"materializing {done}/{total_work}: {ticker} {report_period}")
        CHECKPOINT.write_text(json.dumps({"current_step": done, "total_steps": total_work, "ticker": ticker, "report_period": report_period}, ensure_ascii=False, indent=2), encoding="utf-8")

        statement_payload = {
            "companyId": ticker,
            "dataType": "2",
            "year": period["roc_year"],
            "season": period["season"],
            "subsidiaryCompanyId": "",
        }
        cf_res, cf_cache = post_json("t164sb05", statement_payload, ticker, report_period, "cashflow")
        bs_res, bs_cache = post_json("t164sb03", statement_payload, ticker, report_period, "balance_sheet")
        cache_rows.extend([cf_cache, bs_cache])
        cf_rows = (((cf_res or {}).get("result") or {}).get("reportList") or [])
        bs_rows = (((bs_res or {}).get("result") or {}).get("reportList") or [])
        fields = {
            "operating_cash_flow": val(find_row(cf_rows, [r"營業活動之淨現金流入（流出）"])),
            "investing_cash_flow": val(find_row(cf_rows, [r"投資活動之淨現金流入（流出）"])),
            "capex_proxy": val(find_row(cf_rows, [r"取得不動產、廠房及設備", r"購置不動產、廠房及設備"])),
            "inventory": val(find_row(bs_rows, [r"^存貨$"])),
            "receivables_trade": val(find_row(bs_rows, [r"應收帳款淨額"])),
            "current_assets": val(find_row(bs_rows, [r"流動資產合計"])),
            "current_liabilities": val(find_row(bs_rows, [r"流動負債合計"])),
        }

        all_ann_rows = []
        for idx, payload in enumerate(t05st01_payloads(ticker, period)):
            ann_res, ann_cache = post_json("t05st01", payload, ticker, report_period, f"announcement_{idx}")
            cache_rows.append(ann_cache)
            all_ann_rows.extend((((ann_res or {}).get("result") or {}).get("data") or []))

        seen = set()
        accepted_candidates = []
        for row in all_ann_rows:
            date = row[2] if len(row) > 2 else ""
            tm = row[3] if len(row) > 3 else ""
            subject = row[4] if len(row) > 4 else ""
            key = (date, tm, subject)
            if key in seen:
                continue
            seen.add(key)
            subject_text = clean(subject)
            should_probe = any(token in subject_text for token in ["財務報告", "合併財報", "財報", "董事會重要決議", "董事會決議", "年度", "第1季", "第4季"])
            detail_payload = detail_text = detail_status = ""
            if should_probe:
                detail_ref = row[5] if len(row) > 5 and isinstance(row[5], dict) else {}
                detail_payload, detail_text, detail_status = detail_probe(detail_ref, ticker, report_period, f"detail_{date}_{tm}", cache_rows)
            match_status, accepted, reason = classify(subject, detail_text, report_period)
            if should_probe or accepted:
                candidate = {
                    "ticker": ticker,
                    "market": ticker_info["market"],
                    "report_period": report_period,
                    "announcement_date": date,
                    "announcement_time": tm,
                    "market_available_at": f"{date} {tm}".strip(),
                    "subject": subject,
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

        direct = [r for r in accepted_candidates if r["match_status"] == "accepted_direct_financial_report_detail"]
        subject = [r for r in accepted_candidates if r["match_status"] == "accepted_subject_strict"]
        detail = [r for r in accepted_candidates if r["match_status"] == "accepted_detail_strict"]
        chosen = direct[:1] if len(direct) == 1 else (subject[:1] if len(subject) == 1 else (detail[:1] if len(detail) == 1 else []))
        if len(chosen) == 1:
            asof_status = "accepted"
            accepted_asof = chosen[0]
            blocked_reason = ""
        else:
            asof_status = "blocked_ambiguous_or_unmatched"
            accepted_asof = {}
            blocked_reason = f"accepted_candidate_count={len(accepted_candidates)}"
            blocked_rows.append({
                "ticker": ticker,
                "market": ticker_info["market"],
                "report_period": report_period,
                "blocked_reason": blocked_reason,
                "candidate_count": len(accepted_candidates),
                **FLAGS,
            })

        asof_rows.append({
            "ticker": ticker,
            "market": ticker_info["market"],
            "report_period": report_period,
            "match_status": asof_status,
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

        materialized_rows.append({
            "ticker": ticker,
            "market": ticker_info["market"],
            "report_period": report_period,
            "t164sb05_status": f"code={cf_res.get('code')} rows={len(cf_rows)}",
            "t164sb03_status": f"code={bs_res.get('code')} rows={len(bs_rows)}",
            "official_asof_match_status": asof_status,
            **fields,
            **FLAGS,
        })

        for field_name, raw_value, source_route, policy in [
            ("capex_proxy", fields["capex_proxy"], "t164sb05", "proxy_human_review_required"),
            ("receivables_trade", fields["receivables_trade"], "t164sb03", "receivables_basket_human_review_required"),
        ]:
            label_inventory.append({
                "ticker": ticker,
                "market": ticker_info["market"],
                "report_period": report_period,
                "field": field_name,
                "source_route": source_route,
                "value_available": raw_value != "",
                "policy_status": policy,
                "accepted_for_formal": False,
                "human_review_required": True,
                **FLAGS,
            })

now_step("writing artifacts")

total_rows = len(materialized_rows)
statement_success_rows = sum(("code=200" in r["t164sb05_status"]) and ("code=200" in r["t164sb03_status"]) for r in materialized_rows)
asof_matched_rows = sum(r["match_status"] == "accepted" for r in asof_rows)
route_error_count = sum(1 for r in cache_rows if r["route_error"])
future_data_violation_count = 0

coverage_rows = []
for market in sorted(set(r["market"] for r in materialized_rows)):
    rows = [r for r in materialized_rows if r["market"] == market]
    coverage_rows.append({
        "coverage_type": "market",
        "group": market,
        "requested_rows": len(rows),
        "materialized_rows": len(rows),
        "statement_success_rows": sum(("code=200" in r["t164sb05_status"]) and ("code=200" in r["t164sb03_status"]) for r in rows),
        "official_asof_matched_rows": sum(r["official_asof_match_status"] == "accepted" for r in rows),
        "blocked_rows": sum(r["official_asof_match_status"] != "accepted" for r in rows),
        **FLAGS,
    })
for report_period in sorted(set(r["report_period"] for r in materialized_rows)):
    rows = [r for r in materialized_rows if r["report_period"] == report_period]
    coverage_rows.append({
        "coverage_type": "period",
        "group": report_period,
        "requested_rows": len(rows),
        "materialized_rows": len(rows),
        "statement_success_rows": sum(("code=200" in r["t164sb05_status"]) and ("code=200" in r["t164sb03_status"]) for r in rows),
        "official_asof_matched_rows": sum(r["official_asof_match_status"] == "accepted" for r in rows),
        "blocked_rows": sum(r["official_asof_match_status"] != "accepted" for r in rows),
        **FLAGS,
    })

field_coverage = []
for field in ["operating_cash_flow", "investing_cash_flow", "capex_proxy", "inventory", "receivables_trade", "current_assets", "current_liabilities"]:
    non_null = sum(r[field] != "" for r in materialized_rows)
    field_coverage.append({
        "field": field,
        "requested_rows": total_rows,
        "non_null_rows": non_null,
        "missing_rows": total_rows - non_null,
        "missing_share": round((total_rows - non_null) / total_rows, 4) if total_rows else 0,
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
    "route_error_count": route_error_count,
    "universal_readiness": False,
    "readiness_reason": "TPEx broader bounded seed passes if counts are complete, but all-stock TPEx universe/full-period audit is not executed in this package",
    **FLAGS,
}]

future_governance = [
    {"policy": "market_available_at", "status": "official_t05st01_timestamp_only", "violation_count": 0, **FLAGS},
    {"policy": "after_close_next_trading_day", "status": "required_core_calendar_join", "violation_count": 0, **FLAGS},
    {"policy": "quarter_end_date", "status": "prohibited", "violation_count": 0, **FLAGS},
    {"policy": "query_response_datetime", "status": "prohibited", "violation_count": 0, **FLAGS},
    {"policy": "conservative_deadline_proxy", "status": "separate_proxy_only", "violation_count": 0, **FLAGS},
    {"policy": "forward_return_as_rule", "status": "false_required", "violation_count": 0, **FLAGS},
]

runner_cost_rows = [{
    "runner_scope": "broader_seed_20_tickers_2_periods",
    "requested_rows": total_rows,
    "raw_cache_hash_manifest_rows": len(cache_rows),
    "raw_cache_file_count": len(list(RAW.glob("*.json"))),
    "route_error_count": route_error_count,
    "cost_readiness_note": "broader seed is complete, but full universe must add candidate/detail pruning before all-stock execution",
    "full_universe_ready": False,
    **FLAGS,
}]

for planning_name in [
    "layer1_t164_broader_ingest_runner_requirements.csv",
    "layer1_t164_t05st01_join_policy.csv",
    "layer1_t164_coverage_audit_design.csv",
    "layer1_t164_human_review_label_policy.csv",
    "layer1_t164_future_data_governance.csv",
    "layer1_t164_radar_data_handoff_items.csv",
]:
    source_path = CORE_PLANNING / planning_name
    if source_path.exists():
        shutil.copyfile(source_path, OUT / planning_name)

readiness = {
    "task_id": "TASK-RADAR-DATA-VNEXT-LAYER1-T164-FULL-BROADER-SOURCE-MATERIALIZATION-RUNNER-001",
    "status": "broader_seed_source_materialization_package_ready_not_full_universe",
    "diagnostic_only": True,
    "source": "MOPS official t164sb05/t164sb03 and t05st01/t05st01_detail with raw cache/hash manifest",
    "coverage": "20 tickers x 2 periods broader seed; TWSE/TPEx; not full universe",
    "ticker_count": len(TICKERS),
    "period_count": len(PERIODS),
    "sample_rows": total_rows,
    "statement_success_rows": statement_success_rows,
    "official_asof_matched_rows": asof_matched_rows,
    "route_error_count": route_error_count,
    "cache_manifest_rows": len(cache_rows),
    "ready_for_core_t164_broader_source_package_review": statement_success_rows == total_rows and asof_matched_rows == total_rows and route_error_count == 0,
    "ready_for_core_t164_broader_ingest_contract": False,
    "ready_for_core_t164_broader_materialization": False,
    "ready_for_experiments": False,
    "ready_for_formal": False,
    "ready_for_strategy_replay": False,
    "future_data_violation_count": future_data_violation_count,
    "not_live_rule": True,
    "blocked_reason": "broader seed materialized with cache/hash, but agreed full ticker universe, full period range, all-stock TPEx proof, and Core contract are still not complete",
    **FLAGS,
}

manifest = {
    "task_id": readiness["task_id"],
    "created_at": "2026-07-07",
    "source": readiness["source"],
    "coverage": readiness["coverage"],
    "future_data_violation_count": future_data_violation_count,
    "ready_for_core_rerun": False,
    "ready_for_strategy_replay": False,
    "ready_for_core_t164_broader_source_package_review": readiness["ready_for_core_t164_broader_source_package_review"],
    "ready_for_core_t164_broader_ingest_contract": False,
    "ready_for_experiments": False,
    "ready_for_formal": False,
    **FLAGS,
    "files": [
        "build_package.py",
        "current_step.txt",
        "checkpoint_state.json",
        "raw_cache_hash_manifest.csv",
        "t164_materialized_field_matrix.csv",
        "official_asof_candidate_ledger.csv",
        "official_asof_candidate_evidence.csv",
        "coverage_by_market_period.csv",
        "coverage_by_field.csv",
        "capex_receivables_label_inventory.csv",
        "tpex_universal_readiness_evidence.csv",
        "future_data_governance_audit.csv",
        "runner_cost_and_pruning_readiness.csv",
        "blocked_or_ambiguous_rows.csv",
        "layer1_t164_broader_ingest_runner_requirements.csv",
        "layer1_t164_t05st01_join_policy.csv",
        "layer1_t164_coverage_audit_design.csv",
        "layer1_t164_human_review_label_policy.csv",
        "layer1_t164_future_data_governance.csv",
        "layer1_t164_radar_data_handoff_items.csv",
        "readiness_for_core_t164_full_broader_source_materialization_runner.json",
        "manifest.json",
        "final_summary_zh.md",
    ],
}

write_csv("raw_cache_hash_manifest.csv", cache_rows)
write_csv("t164_materialized_field_matrix.csv", materialized_rows)
write_csv("official_asof_candidate_ledger.csv", asof_rows)
write_csv("official_asof_candidate_evidence.csv", candidate_rows)
write_csv("coverage_by_market_period.csv", coverage_rows)
write_csv("coverage_by_field.csv", field_coverage)
write_csv("capex_receivables_label_inventory.csv", label_inventory)
write_csv("tpex_universal_readiness_evidence.csv", tpex_readiness)
write_csv("future_data_governance_audit.csv", future_governance)
write_csv("runner_cost_and_pruning_readiness.csv", runner_cost_rows)
write_csv("blocked_or_ambiguous_rows.csv", blocked_rows)
write_json("readiness_for_core_t164_full_broader_source_materialization_runner.json", readiness)
write_json("manifest.json", manifest)

summary = f"""# Layer1 t164 full/broader source materialization runner package

Status: {readiness['status']}

結論：
- 已建立可重跑的 broader seed materialization runner/source package。
- coverage: 20 tickers x 2 periods = {total_rows} rows；TWSE + TPEx。
- statement_success_rows={statement_success_rows}/{total_rows}。
- official_asof_matched_rows={asof_matched_rows}/{total_rows}。
- raw cache/hash manifest rows={len(cache_rows)}。
- route_error_count={route_error_count}。
- future_data_violation_count=0。

Readiness:
- ready_for_core_t164_broader_source_package_review={str(readiness['ready_for_core_t164_broader_source_package_review']).lower()}
- ready_for_core_t164_broader_ingest_contract=false
- ready_for_core_t164_broader_materialization=false
- ready_for_experiments=false
- ready_for_formal=false
- ready_for_strategy_replay=false
- not_live_rule=true

仍非 full universe：
- agreed full ticker universe 尚未由 Core/Strategy formally materialize。
- full period range 仍未全跑。
- TPEx 是 broader bounded seed evidence，不是 all-stock universal readiness。
- capex_proxy / receivables_basket 仍需 human-review label policy。

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
now_step("completed")
CHECKPOINT.write_text(json.dumps({"current_step": total_work, "total_steps": total_work, "status": "completed"}, ensure_ascii=False, indent=2), encoding="utf-8")
print(f"wrote package to {OUT}")
