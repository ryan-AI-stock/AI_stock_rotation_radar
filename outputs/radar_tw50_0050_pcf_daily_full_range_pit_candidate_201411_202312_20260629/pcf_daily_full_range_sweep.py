from __future__ import annotations

import argparse
import csv
import hashlib
import json
import shutil
import time
import urllib.parse
from concurrent.futures import ThreadPoolExecutor, as_completed
from dataclasses import dataclass
from datetime import date, datetime, timedelta
from pathlib import Path

import requests

OUT = Path(__file__).resolve().parent
REPO = OUT.parents[1]
RAW = OUT / "raw_sources"
CORE_CONTRACT = Path(r"C:\Users\zergv\Documents\Codex\2026-05-30\ep05-chat-ai-stock-backtest-lab\outputs\core_0050_pcf_daily_pit_contract_judgment_20260629")
PHASE8 = REPO / "outputs" / "radar_tw50_0050_formal_pit_source_phase8_201411_202312_20260629"

START_MONTH = "2014-11"
END_MONTH = "2023-12"
SOURCE_TYPE = "source_backed_manual_candidate"
FORMAL_EXACT = "false"
HEADERS = {
    "user-agent": "Mozilla/5.0 RadarDataFullRangePCF/1.0",
    "accept": "application/json,text/html,*/*",
}

FIELDS = {
    "full_range_daily_pcf_candidate.csv": [
        "month", "request_date", "holdings_date", "source_date", "ticker", "name", "ename",
        "weight", "weight_available", "units", "basket_shares", "cashinlieu", "minimum",
        "source_url", "raw_source_id", "source_type", "formal_exact", "row_count",
        "row_count_anomaly", "quarantined_day", "validation_decision", "rejection_reason",
    ],
    "validated_daily_pcf_candidate.csv": [
        "month", "request_date", "holdings_date", "source_date", "ticker", "name", "ename",
        "weight", "weight_available", "units", "basket_shares", "cashinlieu", "minimum",
        "source_url", "raw_source_id", "source_type", "formal_exact", "row_count",
        "row_count_anomaly", "membership_ready", "weighted_portfolio_ready",
        "validation_decision", "rejection_reason",
    ],
    "rejected_rows.csv": [
        "month", "request_date", "holdings_date", "source_url", "raw_source_id", "ticker",
        "name", "row_count", "validation_decision", "rejection_reason", "http_code", "error",
    ],
    "quarantined_days.csv": [
        "month", "holdings_date", "request_date", "row_count", "row_count_anomaly",
        "quarantined_day", "quarantine_reason", "source_url", "raw_source_id",
    ],
    "monthly_coverage_summary.csv": [
        "month", "calendar_days_swept", "request_attempts", "http_ok", "accepted_days",
        "validated_rows", "rejected_rows", "quarantined_days", "row_count_anomaly_days",
        "last_accepted_holdings_date", "monthly_anchor_row_count", "coverage_status",
        "formal_exact", "source_type", "notes",
    ],
    "missing_months.csv": [
        "month", "coverage_status", "request_attempts", "http_ok", "accepted_days",
        "rejected_rows", "quarantined_days", "last_error", "next_step",
    ],
    "source_request_attempts.csv": [
        "month", "request_date", "query_url", "method", "http_code", "content_type",
        "date_field_detected", "source_date", "holdings_date", "row_count",
        "row_count_anomaly", "quarantined_day", "acceptance_decision", "retrieved_path",
        "error", "elapsed_ms",
    ],
    "completed.csv": ["month", "status", "completed_at", "request_attempts", "accepted_days", "validated_rows", "notes"],
    "failed.csv": ["month", "status", "failed_at", "error", "next_step"],
    "run_log.csv": [
        "started_at", "finished_at", "status", "months_requested", "months_completed",
        "months_missing", "request_attempts", "validated_rows", "rejected_rows",
        "quarantined_days", "notes",
    ],
}


@dataclass
class FetchResult:
    month: str
    request_date: str
    url: str
    http_code: str
    content_type: str
    body: bytes
    error: str
    elapsed_ms: int


def now() -> str:
    return time.strftime("%Y-%m-%dT%H:%M:%S+08:00")


def sha256(data: bytes) -> str:
    return hashlib.sha256(data).hexdigest()


def month_iter(start_month: str, end_month: str) -> list[str]:
    y, m = map(int, start_month.split("-"))
    ey, em = map(int, end_month.split("-"))
    out = []
    while (y, m) <= (ey, em):
        out.append(f"{y:04d}-{m:02d}")
        m += 1
        if m == 13:
            y += 1
            m = 1
    return out


def month_bounds(month: str) -> tuple[date, date]:
    y, m = map(int, month.split("-"))
    start = date(y, m, 1)
    if m == 12:
        end = date(y + 1, 1, 1) - timedelta(days=1)
    else:
        end = date(y, m + 1, 1) - timedelta(days=1)
    return start, end


def sweep_dates_for_month(month: str) -> list[date]:
    start, end = month_bounds(month)
    # Include a short lookback to capture first business-day PCF anndate.
    d = start - timedelta(days=7)
    dates = []
    while d <= end:
        dates.append(d)
        d += timedelta(days=1)
    return dates


def pcf_url(request_date: date) -> str:
    return "https://etfapi.yuantaetfs.com/ectranslation/api/bridge?" + urllib.parse.urlencode({
        "APIType": "ETFAPI",
        "CompanyName": "YUANTAFUNDS",
        "PageName": "/tradeInfo/pcf/0050",
        "DeviceId": "null",
        "FuncId": "PCF/Daily",
        "ticker": "0050",
        "ndate": request_date.strftime("%Y%m%d"),
    })


def decode(data: bytes) -> str:
    return data.decode("utf-8", errors="replace")


def normalize_date(value: object) -> str:
    text = str(value or "").strip().replace("/", "-")
    if len(text) >= 10 and text[:4].isdigit() and text[4] == "-" and text[7] == "-":
        return text[:10]
    if len(text) == 8 and text.startswith("20"):
        return f"{text[:4]}-{text[4:6]}-{text[6:8]}"
    return text


def date_in_month(date_value: str, month: str) -> bool:
    return date_value.startswith(f"{month}-")


def write_csv(path: Path, rows: list[dict], fields: list[str]) -> None:
    with path.open("w", newline="", encoding="utf-8") as fh:
        writer = csv.DictWriter(fh, fieldnames=fields, extrasaction="ignore")
        writer.writeheader()
        writer.writerows(rows)


def read_csv(path: Path) -> list[dict]:
    if not path.exists():
        return []
    with path.open("r", newline="", encoding="utf-8") as fh:
        return list(csv.DictReader(fh))


def save_all(state: dict) -> None:
    for filename, fields in FIELDS.items():
        write_csv(OUT / filename, state.get(filename, []), fields)
    manifest = {
        "task_id": "TASK-RADAR-DATA-TW50-0050-PCF-DAILY-FULL-RANGE-PIT-CANDIDATE-20260629",
        "output_dir": str(OUT),
        "core_contract_output": str(CORE_CONTRACT),
        "phase8_source_output": str(PHASE8),
        "generated_at": now(),
        "start_month": START_MONTH,
        "end_month": END_MONTH,
        "formal_exact": False,
        "source_type": SOURCE_TYPE,
        "formal_model_changed": False,
        "trade_decision_changed": False,
        "current_snapshot_used_as_historical": False,
        "covered_months": sum(1 for row in state["monthly_coverage_summary.csv"] if row["coverage_status"] == "covered"),
        "missing_months": sum(1 for row in state["monthly_coverage_summary.csv"] if row["coverage_status"] != "covered"),
        "validated_rows": len(state["validated_daily_pcf_candidate.csv"]),
        "rejected_rows": len(state["rejected_rows.csv"]),
        "quarantined_days": sum(1 for row in state["quarantined_days.csv"] if row["quarantined_day"] == "true"),
        "row_count_anomaly_days": len(state["quarantined_days.csv"]),
    }
    (OUT / "manifest.json").write_text(json.dumps(manifest, ensure_ascii=False, indent=2), encoding="utf-8")
    write_summary(state, manifest)


def write_summary(state: dict, manifest: dict) -> None:
    monthly = state["monthly_coverage_summary.csv"]
    covered = [row for row in monthly if row["coverage_status"] == "covered"]
    missing = [row for row in monthly if row["coverage_status"] != "covered"]
    anomaly = [row for row in state["quarantined_days.csv"] if row["row_count_anomaly"] == "true"]
    quarantined = [row for row in state["quarantined_days.csv"] if row["quarantined_day"] == "true"]
    lines = [
        "# 0050 PCF/Daily full-range PIT candidate sweep",
        "",
        "## 結論",
        "",
        f"依 Core contract 完成 Yuanta PCF/Daily full-range sweep：`{START_MONTH}` 到 `{END_MONTH}`。",
        "",
        f"- Covered months: {len(covered)}/{len(monthly)}",
        f"- Missing months: {len(missing)}",
        f"- Validated daily rows: {len(state['validated_daily_pcf_candidate.csv'])}",
        f"- Rejected rows: {len(state['rejected_rows.csv'])}",
        f"- Row-count anomaly days: {len(anomaly)}",
        f"- Quarantined days: {len(quarantined)}",
        "",
        "本輸出是 full-range PIT candidate ledger，不是 formal exact PIT；`formal_exact=false`，`source_type=source_backed_manual_candidate`。",
        "",
        "## Monthly Coverage",
        "",
        "| metric | value |",
        "|---|---:|",
        f"| total months | {len(monthly)} |",
        f"| covered months | {len(covered)} |",
        f"| missing months | {len(missing)} |",
        f"| source request attempts | {len(state['source_request_attempts.csv'])} |",
        "",
        "## Core Handoff",
        "",
        "- `validated_daily_pcf_candidate.csv` is ready for Core monthly-anchor compression.",
        "- Monthly anchor rule: each month uses the last accepted `holdings_date` in `monthly_coverage_summary.csv`.",
        "- 51/52-row days are kept with `row_count_anomaly=true`; outside 49-52 are quarantined.",
        "- Weight fields come from Yuanta `FundWeights.StockWeights`; if blank, membership only.",
        "",
        "## Guardrails",
        "",
        "- `formal_model_changed=false`",
        "- `trade_decision_changed=false`",
        "- `formal_exact=false`",
        "- Taiwan Index/TWSE proxy rows are not included.",
        "- current/rolling/date-mismatched payloads are rejected.",
    ]
    if missing:
        lines.extend(["", "## Missing Months", ""])
        for row in missing[:30]:
            lines.append(f"- {row['month']}: {row['coverage_status']} ({row.get('last_error','')})")
    (OUT / "final_summary_zh.md").write_text("\n".join(lines) + "\n", encoding="utf-8")


def load_state() -> dict:
    return {filename: read_csv(OUT / filename) for filename in FIELDS}


def reset_output() -> None:
    for filename in list(FIELDS) + ["manifest.json", "final_summary_zh.md"]:
        path = OUT / filename
        if path.exists():
            path.unlink()
    if RAW.exists():
        shutil.rmtree(RAW)
    RAW.mkdir(parents=True, exist_ok=True)


def fetch_one(month: str, request_date: date) -> FetchResult:
    url = pcf_url(request_date)
    started = time.time()
    try:
        resp = requests.get(url, headers=HEADERS, timeout=15)
        return FetchResult(month, request_date.isoformat(), url, str(resp.status_code), resp.headers.get("content-type", ""), resp.content, "", int((time.time() - started) * 1000))
    except Exception as exc:
        return FetchResult(month, request_date.isoformat(), url, "", "", b"", f"{type(exc).__name__}: {exc}", int((time.time() - started) * 1000))


def parse_json(body: bytes) -> tuple[dict | None, str]:
    try:
        return json.loads(decode(body)), ""
    except Exception as exc:
        return None, f"{type(exc).__name__}: {exc}"


def raw_path_for(month: str, request_date: str, body: bytes) -> Path:
    path = RAW / f"pcf_daily_{month}_{request_date.replace('-', '')}_{sha256(body)[:10]}.json"
    path.write_bytes(body)
    return path


def validate_result(result: FetchResult, state: dict) -> dict:
    if result.body:
        raw_path = raw_path_for(result.month, result.request_date, result.body)
        raw_source_id = str(raw_path)
    else:
        raw_source_id = ""

    parsed, parse_error = parse_json(result.body) if result.body else (None, result.error or "empty_body")
    pcf = parsed.get("PCF", {}) if isinstance(parsed, dict) else {}
    anndate = normalize_date(pcf.get("anndate", ""))
    fund_comp = (((parsed or {}).get("InKind") or {}).get("FundComposition") or []) if isinstance(parsed, dict) else []
    weights = (((parsed or {}).get("FundWeights") or {}).get("StockWeights") or []) if isinstance(parsed, dict) else []
    weights_by_code = {str(row.get("code", "")).zfill(4): row for row in weights if row.get("code")}

    rows = []
    rejected = []
    if not date_in_month(anndate, result.month):
        reason = "date_missing_or_mismatch" if anndate else "missing_anndate"
        rejected.append({
            "month": result.month,
            "request_date": result.request_date,
            "holdings_date": anndate,
            "source_url": result.url,
            "raw_source_id": raw_source_id,
            "ticker": "",
            "name": "",
            "row_count": 0,
            "validation_decision": "rejected",
            "rejection_reason": reason,
            "http_code": result.http_code,
            "error": result.error or parse_error,
        })
        return {"holdings_date": anndate, "rows": [], "rejected": rejected, "row_count": 0, "decision": "rejected", "reason": reason, "raw_source_id": raw_source_id}

    for item in fund_comp:
        ticker = str(item.get("stkcd", "")).strip().zfill(4)
        name = str(item.get("name", "") or "").strip()
        if ticker == "1066" or not ticker or not ticker.isdigit() or len(ticker) != 4 or not name:
            rejected.append({
                "month": result.month,
                "request_date": result.request_date,
                "holdings_date": anndate,
                "source_url": result.url,
                "raw_source_id": raw_source_id,
                "ticker": ticker,
                "name": name,
                "row_count": "",
                "validation_decision": "rejected",
                "rejection_reason": "fund_id_empty_name_or_non_stock",
                "http_code": result.http_code,
                "error": "",
            })
            continue
        weight_row = weights_by_code.get(ticker, {})
        weight = weight_row.get("weights", "")
        units = weight_row.get("qty", "")
        rows.append({
            "month": result.month,
            "request_date": result.request_date,
            "holdings_date": anndate,
            "source_date": anndate,
            "ticker": ticker,
            "name": name,
            "ename": item.get("ename", "") or weight_row.get("ename", ""),
            "weight": weight,
            "weight_available": "true" if weight not in {"", None} else "false",
            "units": units,
            "basket_shares": item.get("qty", ""),
            "cashinlieu": item.get("cashinlieu", ""),
            "minimum": item.get("minimum", ""),
            "source_url": result.url,
            "raw_source_id": raw_source_id,
            "source_type": SOURCE_TYPE,
            "formal_exact": FORMAL_EXACT,
        })
    row_count = len(rows)
    row_count_anomaly = row_count != 50
    quarantined_day = row_count < 49 or row_count > 52
    decision = "quarantined_day" if quarantined_day else "accepted"
    reason = "row_count_outside_49_52" if quarantined_day else ""
    return {
        "holdings_date": anndate,
        "rows": rows,
        "rejected": rejected,
        "row_count": row_count,
        "row_count_anomaly": row_count_anomaly,
        "quarantined_day": quarantined_day,
        "decision": decision,
        "reason": reason,
        "raw_source_id": raw_source_id,
    }


def process_month(month: str, state: dict, workers: int) -> None:
    step_path = OUT / "current_step.txt"
    step_path.write_text(f"running {month}\n", encoding="utf-8")
    dates = sweep_dates_for_month(month)
    results: list[FetchResult] = []
    with ThreadPoolExecutor(max_workers=workers) as executor:
        futures = [executor.submit(fetch_one, month, d) for d in dates]
        for fut in as_completed(futures):
            results.append(fut.result())
    results.sort(key=lambda r: r.request_date)

    month_full = []
    month_valid = []
    month_rejected = []
    month_quarantines = []
    attempts = []
    accepted_by_date: dict[str, list[dict]] = {}
    last_error = ""

    for result in results:
        validation = validate_result(result, state)
        row_count = validation.get("row_count", 0)
        anomaly = bool(validation.get("row_count_anomaly", False))
        quarantined = bool(validation.get("quarantined_day", False))
        decision = validation["decision"]
        attempts.append({
            "month": month,
            "request_date": result.request_date,
            "query_url": result.url,
            "method": "GET",
            "http_code": result.http_code,
            "content_type": result.content_type,
            "date_field_detected": "anndate" if validation.get("holdings_date") else "",
            "source_date": validation.get("holdings_date", ""),
            "holdings_date": validation.get("holdings_date", ""),
            "row_count": row_count,
            "row_count_anomaly": str(anomaly).lower(),
            "quarantined_day": str(quarantined).lower(),
            "acceptance_decision": decision,
            "retrieved_path": validation.get("raw_source_id", ""),
            "error": result.error or validation.get("reason", ""),
            "elapsed_ms": result.elapsed_ms,
        })
        if result.error:
            last_error = result.error
        month_rejected.extend(validation["rejected"])
        if anomaly or quarantined:
            month_quarantines.append({
                "month": month,
                "holdings_date": validation.get("holdings_date", ""),
                "request_date": result.request_date,
                "row_count": row_count,
                "row_count_anomaly": str(anomaly).lower(),
                "quarantined_day": str(quarantined).lower(),
                "quarantine_reason": validation.get("reason", "row_count_anomaly") or "row_count_anomaly",
                "source_url": result.url,
                "raw_source_id": validation.get("raw_source_id", ""),
            })
        for row in validation["rows"]:
            full_row = dict(row)
            full_row.update({
                "row_count": row_count,
                "row_count_anomaly": str(anomaly).lower(),
                "quarantined_day": str(quarantined).lower(),
                "validation_decision": decision,
                "rejection_reason": validation.get("reason", ""),
            })
            month_full.append(full_row)
            if not quarantined:
                valid_row = dict(full_row)
                valid_row.update({
                    "membership_ready": "true",
                    "weighted_portfolio_ready": "true" if valid_row.get("weight_available") == "true" else "false",
                })
                month_valid.append(valid_row)
                accepted_by_date.setdefault(row["holdings_date"], []).append(valid_row)

    accepted_days = sorted(accepted_by_date)
    last_anchor = accepted_days[-1] if accepted_days else ""
    monthly_anchor_count = len(accepted_by_date.get(last_anchor, [])) if last_anchor else 0
    coverage_status = "covered" if accepted_days else "missing"
    summary = {
        "month": month,
        "calendar_days_swept": len(dates),
        "request_attempts": len(attempts),
        "http_ok": sum(1 for row in attempts if row["http_code"] == "200"),
        "accepted_days": len(accepted_days),
        "validated_rows": len(month_valid),
        "rejected_rows": len(month_rejected),
        "quarantined_days": sum(1 for row in month_quarantines if row["quarantined_day"] == "true"),
        "row_count_anomaly_days": len(month_quarantines),
        "last_accepted_holdings_date": last_anchor,
        "monthly_anchor_row_count": monthly_anchor_count,
        "coverage_status": coverage_status,
        "formal_exact": FORMAL_EXACT,
        "source_type": SOURCE_TYPE,
        "notes": "ready_for_core_monthly_anchor_compression" if coverage_status == "covered" else "no_accepted_pcf_daily_rows",
    }

    state["full_range_daily_pcf_candidate.csv"].extend(month_full)
    state["validated_daily_pcf_candidate.csv"].extend(month_valid)
    state["rejected_rows.csv"].extend(month_rejected)
    state["quarantined_days.csv"].extend(month_quarantines)
    state["source_request_attempts.csv"].extend(attempts)
    state["monthly_coverage_summary.csv"].append(summary)
    if coverage_status == "missing":
        state["missing_months.csv"].append({
            "month": month,
            "coverage_status": coverage_status,
            "request_attempts": len(attempts),
            "http_ok": summary["http_ok"],
            "accepted_days": 0,
            "rejected_rows": len(month_rejected),
            "quarantined_days": summary["quarantined_days"],
            "last_error": last_error,
            "next_step": "rerun month; inspect request attempts and Yuanta PCF availability",
        })
        state["failed.csv"].append({
            "month": month,
            "status": "missing_accepted_rows",
            "failed_at": now(),
            "error": last_error or "no accepted PCF/Daily rows",
            "next_step": "rerun month or inspect endpoint availability",
        })
    else:
        state["completed.csv"].append({
            "month": month,
            "status": "completed",
            "completed_at": now(),
            "request_attempts": len(attempts),
            "accepted_days": len(accepted_days),
            "validated_rows": len(month_valid),
            "notes": f"last_anchor={last_anchor}; monthly_anchor_row_count={monthly_anchor_count}",
        })


def remove_month_rows(state: dict, month: str) -> None:
    for filename in FIELDS:
        if filename == "run_log.csv":
            continue
        state[filename] = [row for row in state.get(filename, []) if row.get("month") != month]


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--start-month", default=START_MONTH)
    parser.add_argument("--end-month", default=END_MONTH)
    parser.add_argument("--max-months", type=int, default=0)
    parser.add_argument("--workers", type=int, default=6)
    parser.add_argument("--reset", action="store_true")
    parser.add_argument("--force", action="store_true")
    args = parser.parse_args()

    started = now()
    if args.reset:
        reset_output()
    state = load_state()
    months = month_iter(args.start_month, args.end_month)
    completed = {row["month"] for row in state["completed.csv"] if row.get("status") == "completed"}
    todo = [m for m in months if args.force or m not in completed]
    if args.max_months:
        todo = todo[: args.max_months]

    (OUT / "current_step.txt").write_text(f"starting months={len(todo)} range={args.start_month}..{args.end_month}\n", encoding="utf-8")
    for month in todo:
        if args.force:
            remove_month_rows(state, month)
        process_month(month, state, max(1, args.workers))
        save_all(state)

    summary = state["monthly_coverage_summary.csv"]
    state["run_log.csv"].append({
        "started_at": started,
        "finished_at": now(),
        "status": "completed" if not state["missing_months.csv"] else "completed_partial_with_missing_months",
        "months_requested": len(months),
        "months_completed": sum(1 for row in summary if row["coverage_status"] == "covered"),
        "months_missing": sum(1 for row in summary if row["coverage_status"] != "covered"),
        "request_attempts": len(state["source_request_attempts.csv"]),
        "validated_rows": len(state["validated_daily_pcf_candidate.csv"]),
        "rejected_rows": len(state["rejected_rows.csv"]),
        "quarantined_days": sum(1 for row in state["quarantined_days.csv"] if row["quarantined_day"] == "true"),
        "notes": f"core_contract={CORE_CONTRACT}; force={args.force}; reset={args.reset}",
    })
    save_all(state)
    (OUT / "current_step.txt").write_text("completed\n", encoding="utf-8")


if __name__ == "__main__":
    main()
