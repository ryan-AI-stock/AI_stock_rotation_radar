from __future__ import annotations

import csv
import hashlib
import json
import sys
import time
from dataclasses import dataclass
from datetime import date, datetime
from pathlib import Path
from typing import Any
from urllib.error import HTTPError, URLError
from urllib.parse import urlencode
from urllib.request import Request, urlopen


OUTPUT_DIR = Path(__file__).resolve().parent
RAW_DIR = OUTPUT_DIR / "raw_sources"
CACHE_DIR = OUTPUT_DIR / "cache_compatible"


@dataclass(frozen=True)
class TargetTicker:
    ticker: str
    stock_no: str
    name: str
    required_start: date
    required_end: date
    first_anchor_month: str
    last_anchor_month: str
    notes: str


TARGETS = [
    TargetTicker(
        "2311.TW",
        "2311",
        "日月光",
        date(2014, 11, 28),
        date(2018, 3, 31),
        "2014-11",
        "2018-03",
        "Delisted after ASE/SPIL holding-company transition; no substitution to 3711.TW used.",
    ),
    TargetTicker(
        "2823.TW",
        "2823",
        "中壽",
        date(2016, 11, 30),
        date(2020, 8, 31),
        "2016-11",
        "2020-08",
        "Historical ticker; no substitution used.",
    ),
    TargetTicker(
        "2888.TW",
        "2888",
        "新光金",
        date(2019, 9, 27),
        date(2020, 8, 31),
        "2019-09",
        "2020-08",
        "Historical ticker; no substitution used.",
    ),
    TargetTicker(
        "3474.TW",
        "3474",
        "華亞科",
        date(2014, 11, 28),
        date(2016, 10, 31),
        "2014-11",
        "2016-10",
        "Delisted/merged memory-company ticker; no substitution used.",
    ),
]


SOURCE = "twse_stock_day"
USER_AGENT = "Mozilla/5.0 (compatible; CodexRadarData/1.0; price-coverage-audit)"


def month_starts(start: date, end: date) -> list[date]:
    cursor = date(start.year, start.month, 1)
    last = date(end.year, end.month, 1)
    months: list[date] = []
    while cursor <= last:
        months.append(cursor)
        year = cursor.year + (1 if cursor.month == 12 else 0)
        month = 1 if cursor.month == 12 else cursor.month + 1
        cursor = date(year, month, 1)
    return months


def roc_to_iso(value: str) -> str:
    parts = value.strip().split("/")
    if len(parts) != 3:
        raise ValueError(f"unexpected ROC date: {value!r}")
    year = int(parts[0]) + 1911
    return f"{year:04d}-{int(parts[1]):02d}-{int(parts[2]):02d}"


def parse_number(value: str) -> float | None:
    normalized = value.strip().replace(",", "")
    if not normalized or normalized in {"--", "---", "X", "除權息"}:
        return None
    return float(normalized)


def parse_int(value: str) -> int | None:
    number = parse_number(value)
    if number is None:
        return None
    return int(number)


def sha256_file(path: Path) -> str:
    h = hashlib.sha256()
    with path.open("rb") as fh:
        for chunk in iter(lambda: fh.read(1024 * 1024), b""):
            h.update(chunk)
    return h.hexdigest()


def write_csv(path: Path, rows: list[dict[str, Any]], fieldnames: list[str]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("w", newline="", encoding="utf-8-sig") as fh:
        writer = csv.DictWriter(fh, fieldnames=fieldnames, extrasaction="ignore")
        writer.writeheader()
        writer.writerows(rows)


def fetch_json(url: str, timeout: int = 20) -> tuple[int | None, str, bytes, str | None]:
    request = Request(url, headers={"User-Agent": USER_AGENT, "Accept": "application/json,text/plain,*/*"})
    try:
        with urlopen(request, timeout=timeout) as response:
            return response.status, response.headers.get("Content-Type", ""), response.read(), None
    except HTTPError as exc:
        return exc.code, exc.headers.get("Content-Type", ""), exc.read(), f"HTTPError: {exc}"
    except URLError as exc:
        return None, "", b"", f"URLError: {exc}"
    except TimeoutError as exc:
        return None, "", b"", f"TimeoutError: {exc}"


def twse_urls(stock_no: str, month: date) -> list[str]:
    params = urlencode({"date": f"{month:%Y%m}01", "stockNo": stock_no, "response": "json"})
    return [
        f"https://www.twse.com.tw/rwd/zh/afterTrading/STOCK_DAY?{params}",
        f"https://www.twse.com.tw/exchangeReport/STOCK_DAY?{params}",
    ]


def parse_twse_rows(payload: dict[str, Any], target: TargetTicker, url: str, raw_id: str) -> list[dict[str, Any]]:
    rows: list[dict[str, Any]] = []
    fields = [str(field) for field in payload.get("fields", [])]
    data = payload.get("data", [])
    if not isinstance(data, list):
        return rows
    index = {name: i for i, name in enumerate(fields)}

    def col(names: list[str]) -> int | None:
        for name in names:
            if name in index:
                return index[name]
        return None

    date_i = col(["日期"])
    volume_i = col(["成交股數"])
    open_i = col(["開盤價"])
    high_i = col(["最高價"])
    low_i = col(["最低價"])
    close_i = col(["收盤價"])
    if None in {date_i, volume_i, open_i, high_i, low_i, close_i}:
        return rows

    for raw_row in data:
        try:
            iso_date = roc_to_iso(str(raw_row[date_i]))
            trade_date = datetime.strptime(iso_date, "%Y-%m-%d").date()
            if trade_date < target.required_start or trade_date > target.required_end:
                continue
            rows.append(
                {
                    "ticker": target.ticker,
                    "stock_no": target.stock_no,
                    "name": target.name,
                    "date": iso_date,
                    "open": parse_number(str(raw_row[open_i])),
                    "high": parse_number(str(raw_row[high_i])),
                    "low": parse_number(str(raw_row[low_i])),
                    "close": parse_number(str(raw_row[close_i])),
                    "adj_close": "",
                    "volume": parse_int(str(raw_row[volume_i])),
                    "dividend": 0.0,
                    "stock_split": 0.0,
                    "adjusted_close_available": False,
                    "source": SOURCE,
                    "source_url": url,
                    "raw_source_id": raw_id,
                    "source_type": "official_twse_unadjusted_ohlcv",
                    "formal_exact": False,
                    "validation_decision": "accepted_candidate_unadjusted_ohlcv",
                    "rejection_reason": "",
                }
            )
        except (ValueError, TypeError):
            continue
    return rows


def main() -> int:
    RAW_DIR.mkdir(parents=True, exist_ok=True)
    CACHE_DIR.mkdir(parents=True, exist_ok=True)

    run_started = datetime.now().astimezone().isoformat(timespec="seconds")
    source_attempts: list[dict[str, Any]] = []
    raw_manifest: list[dict[str, Any]] = []
    candidate_rows: list[dict[str, Any]] = []
    run_log: list[dict[str, Any]] = []

    current_step_path = OUTPUT_DIR / "current_step.txt"
    current_step_path.write_text("starting\n", encoding="utf-8")

    for target in TARGETS:
        run_log.append(
            {
                "timestamp": datetime.now().astimezone().isoformat(timespec="seconds"),
                "step": f"start_{target.ticker}",
                "status": "running",
                "details": f"{target.required_start} to {target.required_end}",
            }
        )
        for month in month_starts(target.required_start, target.required_end):
            current_step_path.write_text(f"{target.ticker} {month:%Y-%m}\n", encoding="utf-8")
            month_rows: list[dict[str, Any]] = []
            for endpoint_index, url in enumerate(twse_urls(target.stock_no, month), start=1):
                source_id = f"{target.stock_no}_{month:%Y%m}_twse_stock_day_{endpoint_index}"
                raw_path = RAW_DIR / f"{source_id}.json"
                status_code, content_type, body, error = fetch_json(url)
                raw_path.write_bytes(body)
                body_hash = sha256_file(raw_path)
                raw_manifest.append(
                    {
                        "raw_source_id": source_id,
                        "ticker": target.ticker,
                        "source": SOURCE,
                        "url": url,
                        "retrieved_path": str(raw_path),
                        "content_type": content_type,
                        "http_code": status_code or "",
                        "sha256": body_hash,
                        "bytes": raw_path.stat().st_size,
                        "notes": f"target_month={month:%Y-%m}",
                    }
                )
                parsed: dict[str, Any] | None = None
                rows: list[dict[str, Any]] = []
                parse_error = ""
                if body and error is None:
                    try:
                        parsed = json.loads(body.decode("utf-8-sig"))
                        rows = parse_twse_rows(parsed, target, url, source_id)
                    except (json.JSONDecodeError, UnicodeDecodeError, ValueError) as exc:
                        parse_error = f"parse_error: {exc}"
                stat = parsed.get("stat") if isinstance(parsed, dict) else ""
                source_attempts.append(
                    {
                        "ticker": target.ticker,
                        "name": target.name,
                        "source": SOURCE,
                        "target_month": f"{month:%Y-%m}",
                        "query_url": url,
                        "method": "GET",
                        "http_code": status_code or "",
                        "content_type": content_type,
                        "status": "rows_found" if rows else ("http_or_parse_failed" if error or parse_error else "no_rows"),
                        "twse_stat": stat,
                        "row_count": len(rows),
                        "retrieved_path": str(raw_path),
                        "error": error or parse_error,
                    }
                )
                if rows:
                    month_rows = rows
                    break
                time.sleep(0.2)
            candidate_rows.extend(month_rows)

    candidate_rows.sort(key=lambda row: (row["ticker"], row["date"]))

    by_ticker: dict[str, list[dict[str, Any]]] = {target.ticker: [] for target in TARGETS}
    for row in candidate_rows:
        by_ticker[row["ticker"]].append(row)

    coverage_rows: list[dict[str, Any]] = []
    cache_manifest: list[dict[str, Any]] = []
    completed_rows: list[dict[str, Any]] = []
    failed_rows: list[dict[str, Any]] = []
    failed_tickers: list[dict[str, Any]] = []

    for target in TARGETS:
        rows = by_ticker[target.ticker]
        first_date = rows[0]["date"] if rows else ""
        last_date = rows[-1]["date"] if rows else ""
        start_month_has_rows = any(row["date"][:7] == target.required_start.strftime("%Y-%m") for row in rows)
        end_month_has_rows = any(row["date"][:7] == target.required_end.strftime("%Y-%m") for row in rows)
        first_ok = bool(rows) and first_date <= target.required_start.isoformat()
        end_ok = bool(rows) and end_month_has_rows
        coverage_status = "completed_candidate" if first_ok and end_ok else "partial_or_failed"
        missing_reason = ""
        if not rows:
            missing_reason = "no TWSE STOCK_DAY rows returned inside required range"
        elif not first_ok:
            missing_reason = f"first candidate date {first_date} is after required_start {target.required_start}"
        elif not end_ok:
            missing_reason = f"no candidate rows found in required end month {target.required_end:%Y-%m}"

        coverage = {
            "ticker": target.ticker,
            "name": target.name,
            "required_start": target.required_start.isoformat(),
            "required_end": target.required_end.isoformat(),
            "first_anchor_month": target.first_anchor_month,
            "last_anchor_month": target.last_anchor_month,
            "source": SOURCE if rows else "",
            "first_date": first_date,
            "last_date": last_date,
            "row_count": len(rows),
            "adjusted_close_available": False,
            "coverage_status": coverage_status,
            "range_coverage_decision": "covered_by_official_trading_days" if coverage_status == "completed_candidate" else "not_covered",
            "missing_or_limit_notes": missing_reason or "TWSE official daily rows cover start month through required end month; calendar non-trading dates are not synthesized.",
        }
        coverage_rows.append(coverage)

        if rows:
            cache_path = CACHE_DIR / f"{target.ticker.replace('.', '_')}.csv"
            cache_rows = [
                {
                    "date": row["date"],
                    "open": row["open"],
                    "high": row["high"],
                    "low": row["low"],
                    "close": row["close"],
                    "adj_close": row["adj_close"],
                    "volume": row["volume"],
                    "dividend": row["dividend"],
                    "stock_split": row["stock_split"],
                }
                for row in rows
            ]
            write_csv(
                cache_path,
                cache_rows,
                ["date", "open", "high", "low", "close", "adj_close", "volume", "dividend", "stock_split"],
            )
            cache_manifest.append(
                {
                    "ticker": target.ticker,
                    "cache_path": str(cache_path),
                    "schema": "date,open,high,low,close,adj_close,volume,dividend,stock_split",
                    "rows": len(rows),
                    "first_date": first_date,
                    "last_date": last_date,
                    "adjusted_close_available": False,
                    "source": SOURCE,
                    "sha256": sha256_file(cache_path),
                    "notes": "adj_close intentionally blank because TWSE STOCK_DAY provides unadjusted OHLCV only.",
                }
            )

        completion_record = {
            "ticker": target.ticker,
            "name": target.name,
            "status": coverage_status,
            "required_start": target.required_start.isoformat(),
            "required_end": target.required_end.isoformat(),
            "first_date": first_date,
            "last_date": last_date,
            "row_count": len(rows),
            "source": SOURCE if rows else "",
            "adjusted_close_available": False,
            "notes": coverage["missing_or_limit_notes"],
        }
        if coverage_status == "completed_candidate":
            completed_rows.append(completion_record)
        else:
            failed_rows.append(completion_record)
            failed_tickers.append(
                {
                    "ticker": target.ticker,
                    "name": target.name,
                    "required_start": target.required_start.isoformat(),
                    "required_end": target.required_end.isoformat(),
                    "failed_reason": missing_reason,
                    "attempted_sources": SOURCE,
                    "next_programmatic_source": "Try Yahoo Finance download endpoint or Stooq daily CSV for this historical ticker, then compare against TWSE rows.",
                }
            )

    corporate_action_rows = [
        {
            "ticker": target.ticker,
            "name": target.name,
            "corporate_action_mapping_used": False,
            "substitute_ticker": "",
            "mapping_status": "not_used",
            "notes": target.notes,
        }
        for target in TARGETS
    ]

    decision_rows = [
        {
            "source": SOURCE,
            "source_type": "official_twse_unadjusted_ohlcv",
            "accepted_as_price_candidate": True,
            "formal_exact": False,
            "adjusted_close_available": False,
            "decision": "Use as source-backed cache-compatible price candidate only; do not treat as adjusted total-return series.",
        }
    ]

    write_csv(
        OUTPUT_DIR / "source_attempts.csv",
        source_attempts,
        [
            "ticker",
            "name",
            "source",
            "target_month",
            "query_url",
            "method",
            "http_code",
            "content_type",
            "status",
            "twse_stat",
            "row_count",
            "retrieved_path",
            "error",
        ],
    )
    write_csv(
        OUTPUT_DIR / "raw_source_archive_manifest.csv",
        raw_manifest,
        ["raw_source_id", "ticker", "source", "url", "retrieved_path", "content_type", "http_code", "sha256", "bytes", "notes"],
    )
    write_csv(
        OUTPUT_DIR / "price_candidate_rows.csv",
        candidate_rows,
        [
            "ticker",
            "stock_no",
            "name",
            "date",
            "open",
            "high",
            "low",
            "close",
            "adj_close",
            "volume",
            "dividend",
            "stock_split",
            "adjusted_close_available",
            "source",
            "source_url",
            "raw_source_id",
            "source_type",
            "formal_exact",
            "validation_decision",
            "rejection_reason",
        ],
    )
    write_csv(
        OUTPUT_DIR / "coverage_by_ticker.csv",
        coverage_rows,
        [
            "ticker",
            "name",
            "required_start",
            "required_end",
            "first_anchor_month",
            "last_anchor_month",
            "source",
            "first_date",
            "last_date",
            "row_count",
            "adjusted_close_available",
            "coverage_status",
            "range_coverage_decision",
            "missing_or_limit_notes",
        ],
    )
    write_csv(
        OUTPUT_DIR / "cache_compatible_files_manifest.csv",
        cache_manifest,
        ["ticker", "cache_path", "schema", "rows", "first_date", "last_date", "adjusted_close_available", "source", "sha256", "notes"],
    )
    write_csv(
        OUTPUT_DIR / "corporate_action_mapping.csv",
        corporate_action_rows,
        ["ticker", "name", "corporate_action_mapping_used", "substitute_ticker", "mapping_status", "notes"],
    )
    write_csv(
        OUTPUT_DIR / "failed_tickers.csv",
        failed_tickers,
        ["ticker", "name", "required_start", "required_end", "failed_reason", "attempted_sources", "next_programmatic_source"],
    )
    write_csv(
        OUTPUT_DIR / "source_quality_decision.csv",
        decision_rows,
        ["source", "source_type", "accepted_as_price_candidate", "formal_exact", "adjusted_close_available", "decision"],
    )
    write_csv(
        OUTPUT_DIR / "completed.csv",
        completed_rows,
        ["ticker", "name", "status", "required_start", "required_end", "first_date", "last_date", "row_count", "source", "adjusted_close_available", "notes"],
    )
    write_csv(
        OUTPUT_DIR / "failed.csv",
        failed_rows,
        ["ticker", "name", "status", "required_start", "required_end", "first_date", "last_date", "row_count", "source", "adjusted_close_available", "notes"],
    )
    run_log.append(
        {
            "timestamp": datetime.now().astimezone().isoformat(timespec="seconds"),
            "step": "write_outputs",
            "status": "completed",
            "details": f"completed_tickers={len(completed_rows)} failed_tickers={len(failed_rows)} candidate_rows={len(candidate_rows)}",
        }
    )
    write_csv(OUTPUT_DIR / "run_log.csv", run_log, ["timestamp", "step", "status", "details"])

    manifest = {
        "task_id": "TASK-RADAR-DATA-0050-PIT-MISSING-PRICE-COVERAGE-4TICKERS-20260629",
        "status": "completed_candidate" if not failed_rows else "partial",
        "run_started_at": run_started,
        "run_finished_at": datetime.now().astimezone().isoformat(timespec="seconds"),
        "output_dir": str(OUTPUT_DIR),
        "source": SOURCE,
        "target_tickers": [target.ticker for target in TARGETS],
        "completed_tickers": [row["ticker"] for row in completed_rows],
        "failed_tickers": [row["ticker"] for row in failed_rows],
        "candidate_rows": len(candidate_rows),
        "source_attempts": len(source_attempts),
        "adjusted_close_available": False,
        "formal_exact": False,
        "formal_model_changed": False,
        "trade_decision_changed": False,
        "notes": "TWSE STOCK_DAY official OHLCV is unadjusted. No synthetic prices, forward-fill, or substitute tickers were used.",
    }
    (OUTPUT_DIR / "manifest.json").write_text(json.dumps(manifest, ensure_ascii=False, indent=2), encoding="utf-8")

    summary = [
        "# 0050 PIT universe 剩餘 4 檔歷史價格缺口補齊",
        "",
        f"- 狀態：{manifest['status']}",
        f"- 輸出：`{OUTPUT_DIR}`",
        f"- 來源：TWSE STOCK_DAY official daily OHLCV",
        f"- 完成檔數：{len(completed_rows)} / {len(TARGETS)}",
        f"- 候選價格列：{len(candidate_rows)}",
        f"- source attempts：{len(source_attempts)}",
        "- adjusted close：來源未提供，`adjusted_close_available=false`；未把 close 假造為 adj_close。",
        "- 邊界：`formal_model_changed=false`、`trade_decision_changed=false`、`formal_exact=false`。",
        "",
        "## Coverage",
        "",
        "| ticker | required range | candidate range | rows | status |",
        "|---|---:|---:|---:|---|",
    ]
    for row in coverage_rows:
        summary.append(
            f"| {row['ticker']} | {row['required_start']}~{row['required_end']} | {row['first_date']}~{row['last_date']} | {row['row_count']} | {row['coverage_status']} |"
        )
    summary.extend(
        [
            "",
            "## 使用限制",
            "",
            "- 本批資料是 source-backed price candidate package，可交 Core 更新 cache/coverage ledger。",
            "- TWSE `STOCK_DAY` 為未還原 OHLCV；若 Core 的正式績效需要 adjusted close，仍需 Core 判斷是否接受 unadjusted price candidate 或另接還原來源。",
            "- 未使用現行公司代號替代下市、合併或更名代號；`corporate_action_mapping.csv` 只記錄未替代的治理邊界。",
        ]
    )
    (OUTPUT_DIR / "final_summary_zh.md").write_text("\n".join(summary) + "\n", encoding="utf-8")
    current_step_path.write_text("completed\n", encoding="utf-8")
    print(json.dumps(manifest, ensure_ascii=False, indent=2))
    return 0 if not failed_rows else 2


if __name__ == "__main__":
    sys.exit(main())
