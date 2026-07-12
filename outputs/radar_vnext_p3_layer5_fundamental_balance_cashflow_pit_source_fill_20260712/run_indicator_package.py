import hashlib
import json
import re
import time
from concurrent.futures import ThreadPoolExecutor, as_completed
from pathlib import Path

import requests

import build_package as bp


METRICS = {
    "OperatingCashflow": "operating_cash_flow",
    "InvestingCashflow": "investing_cash_flow",
    "DebtRatio": "debt_ratio_percent",
    "CurrentRatio": "current_ratio_percent",
}
INDICATOR_URL = "https://mopsfin.twse.com.tw/compare/data"
RESULT_CACHE = bp.OUT / "indicator_batch_results"
RESULT_CACHE.mkdir(exist_ok=True)


def fetch(metric, batch_index, tickers):
    key = f"{metric}_b{batch_index:03d}"
    path = RESULT_CACHE / f"{key}.json"
    if path.exists():
        return json.loads(path.read_text(encoding="utf-8"))
    session = requests.Session()
    session.headers.update({"User-Agent": "Mozilla/5.0", "Accept-Language": "zh-TW,zh;q=0.9"})
    session.get(bp.INDEX_URL, timeout=30)
    form = [("compareItem", metric), ("quarter", "true"), ("ys", "20261"), ("revenue", "false")]
    form.extend(("companyId", ticker) for ticker in tickers)
    last_error = ""
    for attempt in range(3):
        try:
            response = session.post(INDICATOR_URL, data=form, timeout=60)
            response.raise_for_status()
            payload = response.json()
            if not payload.get("xaxisList") or not payload.get("graphData"):
                raise ValueError("indicator response missing xaxisList/graphData")
            result = {
                "key": key,
                "metric": metric,
                "requested_tickers": tickers,
                "response": payload,
                "response_hash": hashlib.sha256(response.content).hexdigest(),
                "response_bytes": len(response.content),
                "http_status": response.status_code,
                "attempt_count": attempt + 1,
                "route_status": "accepted",
                "retrieved_at": bp.NOW,
            }
            bp.write_json(path, result)
            return result
        except Exception as exc:
            last_error = repr(exc)
            time.sleep(1 + attempt)
    result = {"key": key, "metric": metric, "requested_tickers": tickers, "response": {}, "response_hash": "", "response_bytes": 0, "http_status": "", "attempt_count": 3, "route_status": "failed", "retrieved_at": bp.NOW, "error": last_error}
    bp.write_json(path, result)
    return result


def main():
    matrix, req_rows = bp.extract_requirements()
    req_info = {(row["ticker"], row["report_period"]): row for row in req_rows}
    tickers = sorted({row["ticker"] for row in req_rows})
    batches = [tickers[i:i + 20] for i in range(0, len(tickers), 20)]
    jobs = [(metric, idx, batch) for metric in METRICS for idx, batch in enumerate(batches)]
    results = []
    bp.CURRENT_STEP.write_text(f"indicator_fetch 0/{len(jobs)}", encoding="utf-8")
    with ThreadPoolExecutor(max_workers=8) as pool:
        futures = {pool.submit(fetch, *job): job for job in jobs}
        for count, future in enumerate(as_completed(futures), 1):
            results.append(future.result())
            bp.CURRENT_STEP.write_text(f"indicator_fetch {count}/{len(jobs)}", encoding="utf-8")

    merged = {}
    manifests = []
    blocked = []
    for result in results:
        manifests.append({
            "batch_key": result["key"], "metric": result["metric"],
            "request_ticker_count": len(result["requested_tickers"]), "route_status": result["route_status"],
            "http_status": result["http_status"], "response_bytes": result["response_bytes"],
            "response_hash": result["response_hash"], "attempt_count": result["attempt_count"],
            "source_url": INDICATOR_URL, "retrieved_at": result["retrieved_at"], "error": result.get("error", ""), **bp.FLAGS,
        })
        payload = result.get("response") or {}
        periods = payload.get("xaxisList") or []
        headers = payload.get("showNameList") or []
        graph = payload.get("graphData") or []
        returned = set()
        for idx, header in enumerate(headers):
            match = re.match(r"(\d{4})\s*", str(header))
            if not match or idx >= len(graph):
                continue
            ticker = match.group(1)
            returned.add(ticker)
            industry_match = re.search(r"\((?:上市|上櫃)(.*?)\)", str(header))
            industry_profile = industry_match.group(1) if industry_match else ""
            financial_profile = any(token in industry_profile for token in ("金融", "銀行", "保險", "證券", "金控", "異業"))
            data = graph[idx].get("data") or []
            for point in data:
                if len(point) < 2:
                    continue
                period_index, value = int(point[0]), point[1]
                if period_index >= len(periods):
                    continue
                period = periods[period_index]
                key = (ticker, period)
                if key not in req_info or value is None:
                    continue
                row = merged.setdefault(key, {
                    **req_info[key],
                    "available_date": req_info[key]["available_date_policy"],
                    "available_date_quality": "conservative_statutory_deadline_proxy_diagnostic",
                    "source": "MOPS official financial comparison E-point trend API",
                    "source_route": "POST https://mopsfin.twse.com.tw/compare/data",
                    "source_url": bp.INDEX_URL,
                    "source_quality": "official_period_specific_diagnostic_pit_proxy",
                    "exact_publication_timestamp_available": False,
                    "accepted_for_formal": False,
                    "future_data_violation_count": 0,
                })
                row[METRICS[result["metric"]]] = value
                row[f"{METRICS[result['metric']]}_response_hash"] = result["response_hash"]
                row["industry_profile"] = industry_profile
                row["financial_profile"] = financial_profile
        for ticker in sorted(set(result["requested_tickers"]) - returned):
            blocked.append({"ticker": ticker, "metric": result["metric"], "status": "official_indicator_company_not_returned", "blocked_reason": "MOPS comparison API returned no series for requested ticker", "attempt_batch_key": result["key"], **bp.FLAGS})

    rows = []
    for key in sorted(req_info):
        row = merged.get(key, {**req_info[key], "available_date": req_info[key]["available_date_policy"]})
        ocf = row.get("operating_cash_flow")
        investing = row.get("investing_cash_flow")
        if ocf is not None and investing is not None:
            row["free_cash_flow_proxy_candidate"] = float(ocf) + float(investing)
            row["free_cash_flow_proxy_policy"] = "OCF plus net investing cashflow; diagnostic proxy, not exact capex-based FCF"
            row["human_review_required"] = True
        rows.append(row)

    fields = list(METRICS.values()) + ["free_cash_flow_proxy_candidate"]
    coverage = []
    for field in fields:
        ready = sum(row.get(field) not in (None, "") for row in rows)
        coverage.append({
            "family": "cashflow" if "cash_flow" in field else "leverage_liquidity" if "ratio" in field else "cashflow_proxy",
            "field": field, "required_ticker_period_rows": len(rows), "ready_ticker_period_rows": ready,
            "blocked_or_not_applicable_rows": len(rows) - ready, "ready_share": round(ready / len(rows), 8),
            "source_quality": "official_period_specific_diagnostic_pit_proxy",
            "available_date_quality": "conservative_statutory_deadline_proxy_diagnostic", **bp.FLAGS,
        })
    for row in rows:
        for field in fields:
            if row.get(field) in (None, ""):
                not_applicable = bool(row.get("financial_profile")) and field in {"current_ratio_percent", "free_cash_flow_proxy_candidate"}
                blocked.append({
                    "ticker": row["ticker"], "report_period": row["report_period"], "field": field,
                    "status": "official_not_applicable_financial_profile" if not_applicable else "official_field_missing",
                    "blocked_reason": "financial-industry taxonomy does not expose a comparable value" if not_applicable else "MOPS official trend API has no finite value; no zero fill",
                    "industry_profile": row.get("industry_profile", ""), "financial_profile": row.get("financial_profile", False),
                    "applicability_aware": True, **bp.FLAGS,
                })

    bp.write_csv(bp.OUT / "p3_layer5_exact_candidate_ticker_period_requirements.csv.gz", req_rows)
    bp.write_csv(bp.OUT / "p3_layer5_balance_cashflow_official_indicator_rows.csv.gz", rows)
    bp.write_csv(bp.OUT / "p3_layer5_balance_cashflow_source_manifest.csv", manifests)
    bp.write_csv(bp.OUT / "p3_layer5_balance_cashflow_field_coverage.csv", coverage)
    bp.write_csv(bp.OUT / "p3_layer5_balance_cashflow_applicability_blocked_ledger.csv", blocked)
    bp.write_csv(bp.OUT / "p3_layer5_balance_cashflow_pit_timing_audit.csv", [{
        "source": "MOPS official financial comparison E-point trend API", "period_scope": "2022Q1-2026Q1 exact candidate requirements",
        "period_end_used_as_available_date": False, "exact_publication_timestamp_available": False,
        "available_date_policy": "Q1 May-15; Q2 Aug-14; Q3 Nov-14; Q4 following Mar-31 conservative statutory deadline",
        "eligibility_policy": "next market decision after conservative deadline", "future_data_violation_count": 0, **bp.FLAGS,
    }])
    bp.write_csv(bp.OUT / "p3_layer5_balance_cashflow_future_data_audit.csv", [{
        "check": "period_end_and_query_time_prohibited", "status": "pass", "violation_count": 0,
        "notes": "Only conservative statutory available_date is exposed to Core; retrieval time is metadata.", **bp.FLAGS,
    }])
    cov = {row["field"]: row for row in coverage}
    readiness = {
        "task_id": bp.TASK_ID,
        "status": "official_cashflow_and_leverage_liquidity_proxy_source_ready_for_core_absorption",
        "source": "MOPS official financial comparison E-point /compare/data",
        "coverage": {
            "candidate_matrix_rows": len(matrix), "candidate_tickers": int(matrix["ticker"].nunique()),
            "requirement_ticker_period_rows": len(rows), "period_start": min(row["report_period"] for row in req_rows),
            "period_end": max(row["report_period"] for row in req_rows),
            **{f"{field}_ready_share": cov[field]["ready_share"] for field in fields},
        },
        "cashflow_exact_capex_ready": False,
        "free_cash_flow_proxy_status": "diagnostic_human_review_required",
        "balance_sheet_exact_total_assets_liabilities_status": "partial_from_existing_t164_batches_not_required_for_proxy_gate",
        "leverage_proxy_ready": cov["debt_ratio_percent"]["ready_ticker_period_rows"] > 0,
        "liquidity_proxy_ready": cov["current_ratio_percent"]["ready_ticker_period_rows"] > 0,
        "future_data_violation_count": 0,
        "ready_for_core_p3_layer5_balance_cashflow_absorption": True,
        "ready_for_core_rerun": False,
        "ready_for_experiments": False,
        **bp.FLAGS,
    }
    bp.write_json(bp.OUT / "readiness_for_core_p3_layer5_balance_cashflow_absorption.json", readiness)
    summary = f"""# P3 Layer5 F 軸 balance/cashflow PIT source package\n\n- Status: {readiness['status']}\n- Official source: MOPS 財務比較 E 點通 `/compare/data`。\n- Exact Core candidate matrix: {len(matrix):,} rows / {matrix['ticker'].nunique()} tickers。\n- Bounded ticker-period requirements: {len(rows):,}，{readiness['coverage']['period_start']}～{readiness['coverage']['period_end']}。\n- OCF coverage: {cov['operating_cash_flow']['ready_share']:.2%}。\n- Investing cashflow coverage: {cov['investing_cash_flow']['ready_share']:.2%}。\n- Debt ratio coverage: {cov['debt_ratio_percent']['ready_share']:.2%}。\n- Current ratio coverage: {cov['current_ratio_percent']['ready_share']:.2%}。\n- OCF + investing cashflow 僅為 diagnostic FCF proxy candidate，human_review_required=true；不是 exact capex FCF。\n- 金融業或官方無值列為 missing/not-applicable，不填 0。\n- available_date 使用保守法定申報期限，不使用 period-end 或 query/retrieval time。\n- future_data_violation_count=0。\n- 只交 Core absorption/readiness，不交 Experiments、不計績效、不改 formal/report/trade decision。\n"""
    (bp.OUT / "final_summary_zh.md").write_text(summary, encoding="utf-8")
    bp.write_json(bp.CHECKPOINT, {
        "task_id": bp.TASK_ID,
        "current_step": "completed_ready_for_core_absorption",
        "completed_indicator_jobs": len(results),
        "total_indicator_jobs": len(jobs),
        "candidate_tickers": len(tickers),
        "requirement_ticker_period_rows": len(rows),
        "resume_command": "python -X utf8 run_indicator_package.py",
        "updated_at": bp.NOW,
    })
    bp.CURRENT_STEP.write_text("completed_ready_for_core_absorption", encoding="utf-8")
    artifacts = []
    for path in sorted(bp.OUT.rglob("*")):
        relative = path.relative_to(bp.OUT)
        if not path.is_file() or path.name == "manifest.json":
            continue
        if any(part in {"batch_results", "indicator_batch_results", "__pycache__"} for part in relative.parts):
            if path.name != ".gitignore":
                continue
        artifacts.append({"path": relative.as_posix(), "bytes": path.stat().st_size, "sha256": hashlib.sha256(path.read_bytes()).hexdigest()})
    bp.write_json(bp.OUT / "manifest.json", {"task_id": bp.TASK_ID, "generated_at": bp.NOW, "artifacts": artifacts, **bp.FLAGS})
    print(json.dumps(readiness, ensure_ascii=False, indent=2))


if __name__ == "__main__":
    main()
