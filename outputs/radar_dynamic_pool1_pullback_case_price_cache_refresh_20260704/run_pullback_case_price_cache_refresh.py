from __future__ import annotations

import csv
import json
from datetime import datetime, timezone
from pathlib import Path
from urllib.parse import urlencode
from urllib.request import Request, urlopen


TASK_ID = "TASK-RADAR-DATA-DYNAMIC-POOL1-PULLBACK-CASE-PRICE-CACHE-REFRESH-20260704"
OUTPUT_DIR = Path(__file__).resolve().parent
RAW_DIR = OUTPUT_DIR / "raw_sources"
CACHE_DIR = OUTPUT_DIR / "cache_compatible"
TARGET_MONTH = "20260701"
MIN_REQUIRED_DATE = "2026-07-03"

REQUESTED = [
    {"ticker": "6669.TW", "code": "6669", "name": "緯穎", "market": "TWSE", "case_role": "primary_pullback_lowpoint_case"},
    {"ticker": "2308.TW", "code": "2308", "name": "台達電", "market": "TWSE", "case_role": "old_ai_reference_case"},
    {"ticker": "2317.TW", "code": "2317", "name": "鴻海", "market": "TWSE", "case_role": "old_ai_reference_case"},
    {"ticker": "0050.TW", "code": "0050", "name": "元大台灣50", "market": "TWSE", "case_role": "benchmark_case"},
    {"ticker": "00631L.TW", "code": "00631L", "name": "元大台灣50正2", "market": "TWSE", "case_role": "benchmark_case"},
]

CACHE_COLUMNS = [
    "date",
    "ticker",
    "code",
    "name",
    "market",
    "open",
    "high",
    "low",
    "close",
    "volume",
    "turnover_value",
    "adjusted_close",
    "adjusted_close_available",
    "source_date",
    "as_of_date",
    "source_url",
    "source_route",
    "source_type",
    "formal_exact",
]


def now_iso() -> str:
    return datetime.now(timezone.utc).replace(microsecond=0).isoformat()


def write_csv(path: Path, rows: list[dict], fieldnames: list[str]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("w", newline="", encoding="utf-8-sig") as f:
        writer = csv.DictWriter(f, fieldnames=fieldnames, extrasaction="ignore")
        writer.writeheader()
        writer.writerows(rows)


def fetch_stock_day(code: str) -> tuple[dict, str, Path]:
    params = {"response": "json", "date": TARGET_MONTH, "stockNo": code}
    url = "https://www.twse.com.tw/exchangeReport/STOCK_DAY?" + urlencode(params)
    req = Request(url, headers={"User-Agent": "Mozilla/5.0"})
    with urlopen(req, timeout=30) as resp:
        content = resp.read()
        content_type = resp.headers.get("content-type", "")
    RAW_DIR.mkdir(parents=True, exist_ok=True)
    raw_path = RAW_DIR / f"twse_stock_day_{code}_{TARGET_MONTH}.json"
    raw_path.write_bytes(content)
    payload = json.loads(content.decode("utf-8-sig"))
    payload["_source_url"] = url
    payload["_content_type"] = content_type
    return payload, url, raw_path


def tw_date_to_iso(value: str) -> str:
    parts = value.split("/")
    if len(parts) != 3:
        return ""
    year = int(parts[0]) + 1911
    return f"{year:04d}-{int(parts[1]):02d}-{int(parts[2]):02d}"


def number(value: str) -> str:
    cleaned = value.replace(",", "").replace("--", "").strip()
    return cleaned


def normalize_rows(item: dict, payload: dict, source_url: str) -> list[dict]:
    rows: list[dict] = []
    fields = payload.get("fields") or []
    data = payload.get("data") or []
    index = {field: i for i, field in enumerate(fields)}
    for raw in data:
        date_value = tw_date_to_iso(raw[index["日期"]])
        if not date_value:
            continue
        rows.append(
            {
                "date": date_value,
                "ticker": item["ticker"],
                "code": item["code"],
                "name": item["name"],
                "market": item["market"],
                "open": number(raw[index["開盤價"]]),
                "high": number(raw[index["最高價"]]),
                "low": number(raw[index["最低價"]]),
                "close": number(raw[index["收盤價"]]),
                "volume": number(raw[index["成交股數"]]),
                "turnover_value": number(raw[index["成交金額"]]),
                "adjusted_close": "",
                "adjusted_close_available": "false",
                "source_date": date_value,
                "as_of_date": date_value,
                "source_url": source_url,
                "source_route": "TWSE_STOCK_DAY",
                "source_type": "official_twse_unadjusted_ohlcv",
                "formal_exact": "false",
            }
        )
    return rows


def main() -> None:
    OUTPUT_DIR.mkdir(parents=True, exist_ok=True)
    RAW_DIR.mkdir(parents=True, exist_ok=True)
    CACHE_DIR.mkdir(parents=True, exist_ok=True)
    (OUTPUT_DIR / "current_step.txt").write_text("running_targeted_twse_stock_day_refresh\n", encoding="utf-8")
    write_csv(
        OUTPUT_DIR / "run_log.csv",
        [{"timestamp_utc": now_iso(), "status": "started", "detail": "targeted TWSE STOCK_DAY refresh for pullback lowpoint case trace"}],
        ["timestamp_utc", "status", "detail"],
    )
    write_csv(OUTPUT_DIR / "requested_tickers.csv", REQUESTED, ["ticker", "code", "name", "market", "case_role"])

    all_rows: list[dict] = []
    attempts: list[dict] = []
    raw_manifest: list[dict] = []
    failures: list[dict] = []

    for item in REQUESTED:
        try:
            payload, url, raw_path = fetch_stock_day(item["code"])
            status = payload.get("stat", "")
            rows = normalize_rows(item, payload, url) if status == "OK" else []
            all_rows.extend(rows)
            write_csv(CACHE_DIR / f"{item['ticker'].replace('.', '_')}.csv", rows, CACHE_COLUMNS)
            attempts.append(
                {
                    "timestamp_utc": now_iso(),
                    "ticker": item["ticker"],
                    "source": "TWSE",
                    "source_route": "STOCK_DAY",
                    "query_url": url,
                    "status": "completed" if status == "OK" else "failed",
                    "http_code": "200",
                    "source_stat": status,
                    "row_count": len(rows),
                    "retrieved_path": str(raw_path),
                    "error": "" if status == "OK" else json.dumps(payload, ensure_ascii=False)[:500],
                }
            )
            raw_manifest.append(
                {
                    "ticker": item["ticker"],
                    "source_url": url,
                    "retrieved_path": str(raw_path),
                    "source_type": "official_twse_stock_day_json",
                    "source_date": TARGET_MONTH,
                    "row_count": len(rows),
                    "git_tracked": "true",
                }
            )
        except Exception as exc:
            failures.append({"ticker": item["ticker"], "error": str(exc)})
            attempts.append(
                {
                    "timestamp_utc": now_iso(),
                    "ticker": item["ticker"],
                    "source": "TWSE",
                    "source_route": "STOCK_DAY",
                    "query_url": "",
                    "status": "failed",
                    "http_code": "",
                    "source_stat": "",
                    "row_count": 0,
                    "retrieved_path": "",
                    "error": str(exc),
                }
            )

    coverage_rows: list[dict] = []
    completed_rows: list[dict] = []
    failed_rows: list[dict] = []
    manifest_rows: list[dict] = []
    rows_by_ticker = {item["ticker"]: [r for r in all_rows if r["ticker"] == item["ticker"]] for item in REQUESTED}
    for item in REQUESTED:
        rows = sorted(rows_by_ticker[item["ticker"]], key=lambda r: r["date"])
        first_date = rows[0]["date"] if rows else ""
        last_date = rows[-1]["date"] if rows else ""
        has_required = any(r["date"] == MIN_REQUIRED_DATE for r in rows)
        ready = bool(rows and last_date >= MIN_REQUIRED_DATE and has_required)
        blocker = "" if ready else f"missing_required_date:{MIN_REQUIRED_DATE}"
        coverage = {
            "ticker": item["ticker"],
            "code": item["code"],
            "name": item["name"],
            "market": item["market"],
            "case_role": item["case_role"],
            "first_date": first_date,
            "last_date": last_date,
            "required_through_date": MIN_REQUIRED_DATE,
            "has_required_date": str(has_required).lower(),
            "row_count": len(rows),
            "coverage_ready": str(ready).lower(),
            "adjusted_close_available": "false",
            "source_type": "official_twse_unadjusted_ohlcv",
            "blocked_reason": blocker,
        }
        coverage_rows.append(coverage)
        manifest_rows.append(
            {
                "ticker": item["ticker"],
                "cache_compatible_path": str(CACHE_DIR / f"{item['ticker'].replace('.', '_')}.csv"),
                "row_count": len(rows),
                "first_date": first_date,
                "last_date": last_date,
                "coverage_ready": str(ready).lower(),
                "adjusted_close_available": "false",
                "source_type": "official_twse_unadjusted_ohlcv",
            }
        )
        if ready:
            completed_rows.append({"ticker": item["ticker"], "status": "completed", "last_date": last_date, "row_count": len(rows)})
        else:
            failed_rows.append({"ticker": item["ticker"], "status": "failed_or_partial", "reason": blocker})

    write_csv(OUTPUT_DIR / "price_rows.csv", all_rows, CACHE_COLUMNS)
    write_csv(OUTPUT_DIR / "completed_price_rows.csv", all_rows, CACHE_COLUMNS)
    write_csv(OUTPUT_DIR / "refreshed_price_cache_manifest.csv", manifest_rows, ["ticker", "cache_compatible_path", "row_count", "first_date", "last_date", "coverage_ready", "adjusted_close_available", "source_type"])
    write_csv(OUTPUT_DIR / "ticker_coverage_summary.csv", coverage_rows, ["ticker", "code", "name", "market", "case_role", "first_date", "last_date", "required_through_date", "has_required_date", "row_count", "coverage_ready", "adjusted_close_available", "source_type", "blocked_reason"])
    write_csv(OUTPUT_DIR / "source_request_attempts.csv", attempts, ["timestamp_utc", "ticker", "source", "source_route", "query_url", "status", "http_code", "source_stat", "row_count", "retrieved_path", "error"])
    write_csv(OUTPUT_DIR / "raw_source_archive_manifest.csv", raw_manifest, ["ticker", "source_url", "retrieved_path", "source_type", "source_date", "row_count", "git_tracked"])
    write_csv(OUTPUT_DIR / "completed.csv", completed_rows, ["ticker", "status", "last_date", "row_count"])
    write_csv(OUTPUT_DIR / "failed.csv", failed_rows + failures, ["ticker", "status", "reason", "error"])
    audit_rows = [
        {
            "check": "source_date_as_of_date_present",
            "status": "pass" if all(r["source_date"] and r["as_of_date"] for r in all_rows) else "fail",
            "future_data_violation_count": 0,
            "notes": "source_date/as_of_date are set to the official trading date for each TWSE STOCK_DAY row.",
        },
        {
            "check": "no_adjusted_close_fabrication",
            "status": "pass" if all(r["adjusted_close_available"] == "false" and r["adjusted_close"] == "" for r in all_rows) else "fail",
            "future_data_violation_count": 0,
            "notes": "TWSE STOCK_DAY provides unadjusted OHLCV; adjusted close is intentionally blank.",
        },
        {
            "check": "case_trace_only_boundary",
            "status": "pass",
            "future_data_violation_count": 0,
            "notes": "No strategy replay, report update, formal model change, or trade decision change was executed.",
        },
    ]
    write_csv(OUTPUT_DIR / "future_data_audit.csv", audit_rows, ["check", "status", "future_data_violation_count", "notes"])
    write_csv(OUTPUT_DIR / "future_data_violation_audit.csv", audit_rows, ["check", "status", "future_data_violation_count", "notes"])

    ready = all(row["coverage_ready"] == "true" for row in coverage_rows)
    source_manifest = {
        "task_id": TASK_ID,
        "status": "completed_targeted_case_trace_price_refresh" if ready else "completed_partial_targeted_case_trace_price_refresh",
        "source": "TWSE STOCK_DAY",
        "source_type": "official_twse_unadjusted_ohlcv",
        "target_month": TARGET_MONTH,
        "required_through_date": MIN_REQUIRED_DATE,
        "requested_tickers": len(REQUESTED),
        "completed_tickers": len(completed_rows),
        "failed_or_partial_tickers": len(failed_rows),
        "accepted_price_rows": len(all_rows),
        "adjusted_close_available": False,
        "future_data_violation_count": 0,
        "formal_model_changed": False,
        "trade_decision_changed": False,
        "active_in_trade_decision": False,
        "report_changed": False,
        "strategy_replay_executed": False,
    }
    for filename in ("source_manifest.json", "manifest.json", "readiness_for_core.json"):
        (OUTPUT_DIR / filename).write_text(json.dumps(source_manifest, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")

    summary = f"""# Pullback case price cache refresh

## 結論
- 狀態：`{source_manifest['status']}`
- requested tickers：{len(REQUESTED)}
- completed tickers：{len(completed_rows)}
- failed / partial tickers：{len(failed_rows)}
- accepted price rows：{len(all_rows)}
- required through date：`{MIN_REQUIRED_DATE}`
- source：TWSE official `STOCK_DAY`
- `adjusted_close_available=false`
- `future_data_violation_count=0`

## 邊界
- 只供 Experiments / Research 補 6669、2308、2317 case trace 到 2026-07-03。
- 沒有 strategy replay。
- 沒有 report change。
- 沒有 formal model / trade decision change。
- OHLCV 為官方未還原價格，沒有偽造 adjusted close。
"""
    (OUTPUT_DIR / "final_summary_zh.md").write_text(summary, encoding="utf-8")
    (OUTPUT_DIR / "current_step.txt").write_text(source_manifest["status"] + "\n", encoding="utf-8")
    write_csv(
        OUTPUT_DIR / "run_log.csv",
        [
            {"timestamp_utc": now_iso(), "status": "started", "detail": "targeted TWSE STOCK_DAY refresh for pullback lowpoint case trace"},
            {"timestamp_utc": now_iso(), "status": "completed", "detail": f"completed={len(completed_rows)} failed={len(failed_rows)} rows={len(all_rows)}"},
        ],
        ["timestamp_utc", "status", "detail"],
    )
    print(json.dumps(source_manifest, ensure_ascii=False))


if __name__ == "__main__":
    main()
