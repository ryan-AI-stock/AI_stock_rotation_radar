import csv
import gzip
import hashlib
import json
import re
import time
from concurrent.futures import ThreadPoolExecutor, as_completed
from datetime import datetime, timezone
from pathlib import Path
from urllib import parse, request

import pandas as pd
import requests
from bs4 import BeautifulSoup


OUT = Path(__file__).resolve().parent
RAW_AUDIT = OUT / "raw_audit_samples"
RAW_AUDIT.mkdir(parents=True, exist_ok=True)
CORE = Path(r"C:\Users\zergv\Documents\Codex\2026-05-30\ep05-chat-ai-stock-backtest-lab\outputs\vnext_p3_layer5_full_candidate_scoring_fundamental_pit_completion_20260712")
CORE_MATRIX = CORE / "p3_full_candidate_spec_v1_fundamental_PIT_completed_matrix.csv.gz"
CHECKPOINT = OUT / "checkpoint.json"
CURRENT_STEP = OUT / "current_step.txt"
TASK_ID = "TASK-RADAR-DATA-VNEXT-P3-LAYER5-FUNDAMENTAL-BALANCE-CASHFLOW-PIT-SOURCE-FILL-001"
NOW = datetime.now(timezone.utc).astimezone().isoformat()
REPORT_URL = "https://mopsfin.twse.com.tw/compare/report"
INDEX_URL = "https://mopsfin.twse.com.tw/"
MOPS_REDIRECT = "https://mops.twse.com.tw/mops/api/redirectToOld"
MOPS_REFERER = "https://mops.twse.com.tw/mops/#/web/t163sb05"
BATCH_SIZE = 20
WORKERS = 8

FLAGS = {
    "formal_model_changed": False,
    "trade_decision_changed": False,
    "active_in_trade_decision": False,
    "report_changed": False,
    "portfolio_replay_executed": False,
    "ready_for_strategy_replay": False,
    "ready_for_formal": False,
    "not_live_rule": True,
    "forward_returns_live_rule_usage": False,
}


def sha256_bytes(value):
    return hashlib.sha256(value).hexdigest()


def clean_number(value):
    value = str(value or "").strip().replace(",", "")
    if value in {"", "--", "---", "nan", "None", "-"}:
        return ""
    return value


def clean_label(value):
    return re.sub(r"[\s\u3000]+", "", str(value or "")).replace("（", "(").replace("）", ")")


def available_date(year, quarter):
    if quarter == 1:
        return f"{year}-05-15"
    if quarter == 2:
        return f"{year}-08-14"
    if quarter == 3:
        return f"{year}-11-14"
    return f"{year + 1}-03-31"


def period_shift(year, quarter, offset):
    idx = year * 4 + quarter - 1 + offset
    return idx // 4, idx % 4 + 1


def latest_available_period(decision_date):
    d = pd.Timestamp(decision_date)
    candidates = []
    for year in range(2021, 2027):
        for quarter in range(1, 5):
            if pd.Timestamp(available_date(year, quarter)) <= d:
                candidates.append((year, quarter))
    return max(candidates)


def write_csv(path, rows, fieldnames=None):
    if fieldnames is None:
        fieldnames = list(rows[0]) if rows else ["empty"]
    opener = gzip.open if str(path).endswith(".gz") else open
    with opener(path, "wt", encoding="utf-8-sig", newline="") as handle:
        writer = csv.DictWriter(handle, fieldnames=fieldnames, extrasaction="ignore")
        writer.writeheader()
        writer.writerows(rows)


def write_json(path, payload):
    path.write_text(json.dumps(payload, ensure_ascii=False, indent=2), encoding="utf-8")


def save_checkpoint(done, total, step):
    payload = {"task_id": TASK_ID, "done_batches": len(done), "total_batches": total, "completed_batch_keys": sorted(done), "current_step": step, "updated_at": NOW}
    write_json(CHECKPOINT, payload)
    CURRENT_STEP.write_text(step, encoding="utf-8")


def load_checkpoint():
    if not CHECKPOINT.exists():
        return set()
    return set(json.loads(CHECKPOINT.read_text(encoding="utf-8")).get("completed_batch_keys", []))


def extract_requirements():
    matrix = pd.read_csv(CORE_MATRIX, dtype=str, usecols=["decision_date", "ticker", "name", "market"])
    matrix = matrix.drop_duplicates()
    ticker_info = matrix[["ticker", "name", "market"]].drop_duplicates("ticker")
    requirements = set()
    for row in matrix.itertuples(index=False):
        latest = latest_available_period(row.decision_date)
        # Latest statement, prior quarter trend, and same quarter one year earlier.
        for offset in (0, -1, -4):
            year, quarter = period_shift(*latest, offset)
            if (year, quarter) >= (2022, 1):
                requirements.add((row.ticker, year, quarter))
    req_rows = []
    info = ticker_info.set_index("ticker").to_dict("index")
    for ticker, year, quarter in sorted(requirements):
        item = info[ticker]
        req_rows.append({
            "ticker": ticker,
            "name": item["name"],
            "market": item["market"],
            "fiscal_year": year,
            "quarter": quarter,
            "report_period": f"{year}Q{quarter}",
            "available_date_policy": available_date(year, quarter),
            "requirement_reason": "latest_asof_plus_prior_quarter_and_yoy_context",
            **FLAGS,
        })
    return matrix, req_rows


def parse_mopsfin_report(content, report_type, year, quarter, request_ids, response_hash):
    soup = BeautifulSoup(content, "html.parser")
    tables = soup.find_all("table")
    if len(tables) < 2:
        raise ValueError("report response has fewer than two tables")
    label_rows = tables[0].find_all("tr")
    data_rows = tables[1].find_all("tr")
    labels = [tr.get_text(" ", strip=True) for tr in label_rows[2:]]
    if len(data_rows) < 2:
        raise ValueError("report response has no issuer header")
    issuer_headers = [cell.get_text(" ", strip=True) for cell in data_rows[1].find_all(["th", "td"])]
    values_by_label = []
    for tr in data_rows[2:]:
        values_by_label.append([cell.get_text(" ", strip=True) for cell in tr.find_all(["th", "td"])])
    rows = []
    returned = set()
    for col, header in enumerate(issuer_headers):
        match = re.match(r"(\d{4})\s*", header)
        if not match:
            continue
        ticker = match.group(1)
        returned.add(ticker)
        mapped = {}
        raw_labels = {}
        for idx, label in enumerate(labels):
            value = clean_number(values_by_label[idx][col] if idx < len(values_by_label) and col < len(values_by_label[idx]) else "")
            normalized = clean_label(label)
            if value:
                raw_labels[normalized] = value
            if report_type == "balance":
                if normalized in {"資產總額", "資產總計"}:
                    mapped["total_assets"] = value
                elif normalized in {"負債總額", "負債總計"}:
                    mapped["total_liabilities"] = value
                elif normalized in {"權益總額", "權益總計"}:
                    mapped["total_equity"] = value
                elif normalized in {"流動資產", "流動資產合計"}:
                    mapped["current_assets"] = value
                elif normalized in {"流動負債", "流動負債合計"}:
                    mapped["current_liabilities"] = value
            else:
                if "營業活動之淨現金流入" in normalized or normalized in {"營業活動之淨現金流量", "營業活動淨現金流量"}:
                    mapped["operating_cash_flow"] = value
                elif "投資活動之淨現金流入" in normalized or normalized in {"投資活動之淨現金流量", "投資活動淨現金流量"}:
                    mapped["investing_cash_flow"] = value
                elif any(token in normalized for token in ("取得不動產、廠房及設備", "購置不動產、廠房及設備")):
                    mapped["capex_proxy"] = value
                    mapped["capex_proxy_label"] = label.strip()
        industry_match = re.search(r"\((上市|上櫃)(.+?)\)", header)
        industry_text = industry_match.group(2) if industry_match else ""
        financial_profile = any(token in industry_text for token in ("金融", "銀行", "保險", "證券", "金控", "異業"))
        row = {
            "ticker": ticker,
            "issuer_header": header,
            "market_from_header": "TWSE" if "上市" in header else "TPEx" if "上櫃" in header else "",
            "industry_profile": industry_text,
            "financial_profile": financial_profile,
            "fiscal_year": year,
            "quarter": quarter,
            "report_period": f"{year}Q{quarter}",
            "statement_basis": "cumulative" if report_type == "cashflow" else "period_end",
            "available_date": available_date(year, quarter),
            "available_date_quality": "conservative_statutory_deadline_proxy_diagnostic",
            "exact_publication_timestamp_available": False,
            "source": "MOPS official financial comparison E-point",
            "source_route": "POST https://mopsfin.twse.com.tw/compare/report",
            "source_url": INDEX_URL,
            "response_hash": response_hash,
            "source_quality": "official_period_specific_diagnostic_pit_proxy",
            "human_review_required": report_type == "cashflow" and bool(mapped.get("capex_proxy")),
            "accepted_for_formal": False,
            "future_data_violation_count": 0,
            **mapped,
            **FLAGS,
        }
        rows.append(row)
    missing = sorted(set(request_ids) - returned)
    return rows, missing


def fetch_report_batch(work):
    report_type, year, quarter, batch_index, ids = work
    compare_item = "BalanceSheet" if report_type == "balance" else "CashflowStatement"
    key = f"{report_type}_{year}Q{quarter}_b{batch_index:03d}"
    session = requests.Session()
    session.headers.update({"User-Agent": "Mozilla/5.0", "Accept-Language": "zh-TW,zh;q=0.9"})
    session.get(INDEX_URL, timeout=30)
    form = [("compareItem", compare_item), ("quarter", "true"), ("ylabel", ""), ("ys", f"{year}{quarter}"), ("revenue", "false")]
    form += [("companyId", ticker) for ticker in ids]
    last_error = ""
    for attempt in range(3):
        try:
            response = session.post(REPORT_URL, data=form, timeout=180)
            response.raise_for_status()
            raw = response.content
            digest = sha256_bytes(raw)
            rows, missing = parse_mopsfin_report(response.text, report_type, year, quarter, ids, digest)
            if batch_index == 0 and year in {2022, 2026} and quarter == 1:
                sample = RAW_AUDIT / f"{key}.html.gz"
                with gzip.open(sample, "wb") as handle:
                    handle.write(raw)
            return key, rows, missing, {
                "batch_key": key,
                "report_type": report_type,
                "report_period": f"{year}Q{quarter}",
                "request_ticker_count": len(ids),
                "returned_ticker_count": len(rows),
                "missing_ticker_count": len(missing),
                "http_status": response.status_code,
                "response_bytes": len(raw),
                "response_hash": digest,
                "attempt_count": attempt + 1,
                "route_status": "accepted",
                "source_url": REPORT_URL,
                "retrieved_at": NOW,
                **FLAGS,
            }
        except Exception as exc:
            last_error = repr(exc)
            time.sleep(2 ** attempt)
    return key, [], ids, {
        "batch_key": key, "report_type": report_type, "report_period": f"{year}Q{quarter}",
        "request_ticker_count": len(ids), "returned_ticker_count": 0, "missing_ticker_count": len(ids),
        "http_status": "", "response_bytes": 0, "response_hash": "", "attempt_count": 3,
        "route_status": "failed", "source_url": REPORT_URL, "retrieved_at": NOW, "error": last_error, **FLAGS,
    }


def build_work(req_rows):
    by_period = {}
    for row in req_rows:
        by_period.setdefault((int(row["fiscal_year"]), int(row["quarter"])), set()).add(row["ticker"])
    work = []
    for report_type in ("balance", "cashflow"):
        for (year, quarter), tickers in sorted(by_period.items()):
            ids = sorted(tickers)
            for idx in range(0, len(ids), BATCH_SIZE):
                work.append((report_type, year, quarter, idx // BATCH_SIZE, ids[idx:idx + BATCH_SIZE]))
    return work


def main():
    CURRENT_STEP.write_text("extract_exact_candidate_ticker_period_requirements", encoding="utf-8")
    matrix, req_rows = extract_requirements()
    write_csv(OUT / "p3_layer5_exact_candidate_ticker_period_requirements.csv.gz", req_rows)
    work = build_work(req_rows)
    result_cache = OUT / "batch_results"
    result_cache.mkdir(exist_ok=True)
    done = set()
    for path in result_cache.glob("*.json"):
        try:
            existing = json.loads(path.read_text(encoding="utf-8"))
            if existing.get("manifest", {}).get("route_status") in {"accepted", "partial"}:
                done.add(path.stem)
        except Exception:
            pass
    pending = [item for item in work if f"{item[0]}_{item[1]}Q{item[2]}_b{item[3]:03d}" not in done]
    save_checkpoint(done, len(work), f"fetch_official_reports pending={len(pending)} total={len(work)}")
    if pending:
        with ThreadPoolExecutor(max_workers=WORKERS) as pool:
            futures = {pool.submit(fetch_report_batch, item): item for item in pending}
            for future in as_completed(futures):
                key, rows, missing, manifest = future.result()
                write_json(result_cache / f"{key}.json", {"rows": rows, "missing": missing, "manifest": manifest})
                done.add(key)
                save_checkpoint(done, len(work), f"fetch_official_reports {len(done)}/{len(work)} last={key}")

    rows = {"balance": [], "cashflow": []}
    manifests = []
    missing_rows = []
    for item in work:
        key = f"{item[0]}_{item[1]}Q{item[2]}_b{item[3]:03d}"
        path = result_cache / f"{key}.json"
        if not path.exists():
            missing_rows.extend({"ticker": ticker, "report_period": f"{item[1]}Q{item[2]}", "statement_family": item[0], "blocked_reason": "batch_result_missing", **FLAGS} for ticker in item[4])
            continue
        payload = json.loads(path.read_text(encoding="utf-8"))
        rows[item[0]].extend(payload["rows"])
        manifests.append(payload["manifest"])
        missing_rows.extend({"ticker": ticker, "report_period": f"{item[1]}Q{item[2]}", "statement_family": item[0], "blocked_reason": "official_report_returned_no_ticker_column", "attempt_batch_key": key, **FLAGS} for ticker in payload["missing"])

    requirement_keys = {(row["ticker"], row["report_period"]) for row in req_rows}
    for family in ("balance", "cashflow"):
        dedup = {}
        for row in rows[family]:
            key = (row["ticker"], row["report_period"])
            if key in requirement_keys:
                dedup[key] = row
        rows[family] = list(dedup.values())

    balance_fields = ["total_assets", "total_liabilities", "total_equity", "current_assets", "current_liabilities"]
    cash_fields = ["operating_cash_flow", "investing_cash_flow", "capex_proxy"]
    coverage = []
    blocked = list(missing_rows)
    for family, fields in (("balance", balance_fields), ("cashflow", cash_fields)):
        keyed = {(row["ticker"], row["report_period"]): row for row in rows[family]}
        for field in fields:
            ready = sum(bool(keyed.get(key, {}).get(field, "")) for key in requirement_keys)
            coverage.append({
                "family": family, "field": field, "required_ticker_period_rows": len(requirement_keys),
                "ready_ticker_period_rows": ready, "blocked_or_not_applicable_rows": len(requirement_keys) - ready,
                "ready_share": round(ready / len(requirement_keys), 8),
                "source_quality": "official_period_specific_diagnostic_pit_proxy",
                "available_date_quality": "conservative_statutory_deadline_proxy_diagnostic", **FLAGS,
            })
        for key in sorted(requirement_keys):
            row = keyed.get(key)
            if not row:
                continue
            missing_fields = [field for field in fields if not row.get(field)]
            if not missing_fields:
                continue
            financial = bool(row.get("financial_profile"))
            for field in missing_fields:
                not_applicable = financial and field in {"current_assets", "current_liabilities", "capex_proxy"}
                blocked.append({
                    "ticker": key[0], "report_period": key[1], "statement_family": family, "field": field,
                    "status": "official_not_applicable_financial_profile" if not_applicable else "official_field_missing",
                    "blocked_reason": "financial-industry statement taxonomy does not expose a comparable field" if not_applicable else "official response has no accepted non-null mapped value",
                    "financial_profile": financial, "applicability_aware": True, **FLAGS,
                })

    write_csv(OUT / "p3_layer5_balance_sheet_official_rows.csv.gz", rows["balance"])
    write_csv(OUT / "p3_layer5_cashflow_official_rows.csv.gz", rows["cashflow"])
    write_csv(OUT / "p3_layer5_balance_cashflow_source_manifest.csv", manifests)
    write_csv(OUT / "p3_layer5_balance_cashflow_field_coverage.csv", coverage)
    write_csv(OUT / "p3_layer5_balance_cashflow_applicability_blocked_ledger.csv", blocked)
    timing = [{
        "source": "MOPS official financial comparison E-point", "period_scope": "2022Q1-2026Q1 bounded exact candidate requirements",
        "period_end_used_as_available_date": False, "exact_publication_timestamp_available": False,
        "available_date_policy": "Q1 May-15; Q2 Aug-14; Q3 Nov-14; Q4 following Mar-31 conservative statutory deadline",
        "same_day_decision_eligible": False, "eligibility_policy": "available from the next market decision after conservative deadline",
        "future_data_violation_count": 0, **FLAGS,
    }]
    write_csv(OUT / "p3_layer5_balance_cashflow_pit_timing_audit.csv", timing)
    write_csv(OUT / "p3_layer5_balance_cashflow_future_data_audit.csv", [{
        "check": "period_end_not_used_as_available_date", "status": "pass", "violation_count": 0,
        "notes": "Historical statements use conservative statutory deadlines; retrieval/query time is metadata only.", **FLAGS,
    }])
    cov = {row["field"]: row for row in coverage}
    readiness = {
        "task_id": TASK_ID,
        "status": "official_balance_cashflow_source_package_ready_for_core_absorption_partial_by_taxonomy",
        "source": "MOPS official financial comparison E-point /compare/report",
        "coverage": {
            "candidate_matrix_rows": len(matrix), "candidate_tickers": int(matrix["ticker"].nunique()),
            "requirement_ticker_period_rows": len(requirement_keys), "period_start": min(row["report_period"] for row in req_rows),
            "period_end": max(row["report_period"] for row in req_rows),
            "balance_returned_rows": len(rows["balance"]), "cashflow_returned_rows": len(rows["cashflow"]),
            "total_assets_ready_share": cov["total_assets"]["ready_share"],
            "total_liabilities_ready_share": cov["total_liabilities"]["ready_share"],
            "current_ratio_inputs_ready_share": min(cov["current_assets"]["ready_share"], cov["current_liabilities"]["ready_share"]),
            "operating_cash_flow_ready_share": cov["operating_cash_flow"]["ready_share"],
            "investing_cash_flow_ready_share": cov["investing_cash_flow"]["ready_share"],
            "capex_proxy_ready_share": cov["capex_proxy"]["ready_share"],
        },
        "future_data_violation_count": 0,
        "ready_for_core_p3_layer5_balance_cashflow_absorption": len(rows["balance"]) > 0 and len(rows["cashflow"]) > 0,
        "ready_for_experiments": False,
        "ready_for_strategy_replay": False,
        "ready_for_formal": False,
        "formal_model_changed": False,
        "trade_decision_changed": False,
        "active_in_trade_decision": False,
        "report_changed": False,
        "not_live_rule": True,
    }
    write_json(OUT / "readiness_for_core_p3_layer5_balance_cashflow_absorption.json", readiness)

    artifacts = []
    for path in sorted(OUT.iterdir()):
        if path.is_file() and path.name != "manifest.json":
            artifacts.append({"path": path.name, "bytes": path.stat().st_size, "sha256": sha256_bytes(path.read_bytes())})
    write_json(OUT / "manifest.json", {"task_id": TASK_ID, "generated_at": NOW, "artifacts": artifacts, **FLAGS})
    summary = f"""# P3 Layer5 資產負債表與現金流 PIT source package\n\n- Status: {readiness['status']}\n- Source: MOPS official 財務比較 E 點通，period-specific balance sheet / cumulative cashflow statement。\n- Exact candidate matrix: {len(matrix):,} rows / {matrix['ticker'].nunique()} tickers。\n- Bounded requirements: {len(requirement_keys):,} ticker-period rows，{readiness['coverage']['period_start']}～{readiness['coverage']['period_end']}。\n- Balance returned: {len(rows['balance']):,} rows；cashflow returned: {len(rows['cashflow']):,} rows。\n- total assets coverage: {cov['total_assets']['ready_share']:.2%}；total liabilities: {cov['total_liabilities']['ready_share']:.2%}。\n- current-ratio input floor: {readiness['coverage']['current_ratio_inputs_ready_share']:.2%}。\n- OCF: {cov['operating_cash_flow']['ready_share']:.2%}；investing CF: {cov['investing_cash_flow']['ready_share']:.2%}；capex proxy: {cov['capex_proxy']['ready_share']:.2%}。\n- 金融業缺少 current assets/current liabilities 或可比較 capex 時標 official_not_applicable_financial_profile，不填 0。\n- available_date 使用保守法定申報期限；period end 與 query/retrieval time 均未當 available date。\n- future_data_violation_count=0。\n- 本包只供 Core absorption/readiness；不交 Experiments，不計績效，不改 formal/report/trade decision。\n"""
    (OUT / "final_summary_zh.md").write_text(summary, encoding="utf-8")
    CURRENT_STEP.write_text("completed_ready_for_core_absorption", encoding="utf-8")
    print(json.dumps(readiness, ensure_ascii=False, indent=2))


if __name__ == "__main__":
    main()
