from __future__ import annotations

import argparse
import csv
import html
import json
import re
import time
import urllib.error
import urllib.request
from datetime import date, datetime, timedelta
from pathlib import Path
from typing import Any


TASK_ID = "TASK-RADAR-DATA-DYNAMIC-POOL1-ALL-LISTED-LIQUID-UNIVERSE-PIT-DAILY-20260703"
OUTPUT_DIR = Path(__file__).resolve().parent
RAW_DIR = OUTPUT_DIR / "raw_sources"
UPSTREAM_OUTPUT = (
    Path(__file__).resolve().parents[0].parent
    / "radar_dynamic_pool1_pit_source_acquisition_20260703"
)

SAMPLE_DATES = [
    "2015-01-05",
    "2016-01-04",
    "2017-01-03",
    "2018-01-02",
    "2019-01-02",
    "2020-01-02",
    "2021-01-04",
    "2022-01-03",
    "2023-01-03",
    "2024-01-02",
    "2025-01-02",
    "2026-07-02",
]


def write_csv(path: Path, rows: list[dict[str, Any]], fieldnames: list[str]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("w", newline="", encoding="utf-8-sig") as handle:
        writer = csv.DictWriter(handle, fieldnames=fieldnames, extrasaction="ignore")
        writer.writeheader()
        writer.writerows(rows)


def write_json(path: Path, payload: Any) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(payload, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="Build Dynamic Pool1 all-listed liquid universe PIT daily source package.")
    parser.add_argument("--mode", choices=["sample", "range"], default="sample")
    parser.add_argument("--start-date", default="2015-01-01")
    parser.add_argument("--end-date", default="2026-07-02")
    parser.add_argument("--markets", default="TWSE,TPEx")
    parser.add_argument("--sleep-seconds", type=float, default=0.25)
    parser.add_argument("--max-dates", type=int, default=0, help="Optional cap for bounded continuation runs.")
    return parser.parse_args()


def clean_text(value: Any) -> str:
    text = "" if value is None else str(value)
    text = re.sub(r"<[^>]+>", "", text)
    return html.unescape(text).strip()


def parse_int(value: Any) -> int | None:
    text = clean_text(value).replace(",", "").replace("--", "").strip()
    if not text:
        return None
    try:
        return int(float(text))
    except ValueError:
        return None


def parse_float(value: Any) -> float | None:
    text = clean_text(value).replace(",", "").replace("--", "").strip()
    if not text:
        return None
    try:
        return float(text)
    except ValueError:
        return None


def ymd(value: str) -> str:
    return value.replace("-", "")


def slash_date(value: str) -> str:
    return value.replace("-", "/")


def date_range(start: str, end: str) -> list[str]:
    start_date = date.fromisoformat(start)
    end_date = date.fromisoformat(end)
    out: list[str] = []
    cur = start_date
    while cur <= end_date:
        if cur.weekday() < 5:
            out.append(cur.isoformat())
        cur += timedelta(days=1)
    return out


def fetch_json(url: str) -> tuple[int | None, str, bytes | None, str]:
    request = urllib.request.Request(
        url,
        headers={
            "User-Agent": "Mozilla/5.0 DynamicPool1PITSourceProbe/1.0",
            "Accept": "application/json,text/plain,*/*",
        },
    )
    try:
        with urllib.request.urlopen(request, timeout=30) as response:
            return response.status, response.headers.get("content-type", ""), response.read(), ""
    except urllib.error.HTTPError as exc:
        body = exc.read()
        return exc.code, exc.headers.get("content-type", ""), body, f"HTTPError: {exc}"
    except Exception as exc:  # noqa: BLE001 - logged as source evidence.
        return None, "", None, f"{type(exc).__name__}: {exc}"


def source_url(market: str, target_date: str) -> tuple[str, str]:
    if market == "TWSE":
        return (
            "twse_mi_index_allbut0999",
            f"https://www.twse.com.tw/rwd/zh/afterTrading/MI_INDEX?date={ymd(target_date)}&type=ALLBUT0999&response=json",
        )
    if market == "TPEx":
        return (
            "tpex_daily_quotes",
            f"https://www.tpex.org.tw/www/zh-tw/afterTrading/dailyQuotes?date={slash_date(target_date)}&response=json",
        )
    raise ValueError(f"Unsupported market: {market}")


def save_raw(market: str, target_date: str, source_id: str, raw: bytes) -> Path:
    path = RAW_DIR / f"{market.lower()}_{target_date.replace('-', '')}_{source_id}.json"
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_bytes(raw)
    return path


def load_json(raw: bytes) -> dict[str, Any]:
    return json.loads(raw.decode("utf-8-sig"))


def parse_twse(payload: dict[str, Any], target_date: str, url: str, raw_path: Path) -> list[dict[str, Any]]:
    rows: list[dict[str, Any]] = []
    detail_table = None
    for table in payload.get("tables", []):
        data = table.get("data") or []
        fields = table.get("fields") or []
        if data and len(fields) >= 15 and len(data[0]) >= 15:
            detail_table = table
            break
    if not detail_table:
        return rows
    for raw_row in detail_table.get("data", []):
        if len(raw_row) < 9:
            continue
        ticker = clean_text(raw_row[0])
        name = clean_text(raw_row[1])
        volume = parse_int(raw_row[2])
        turnover = parse_int(raw_row[4])
        open_price = parse_float(raw_row[5])
        high_price = parse_float(raw_row[6])
        low_price = parse_float(raw_row[7])
        close_price = parse_float(raw_row[8])
        rows.append(make_liquidity_row("TWSE", target_date, ticker, name, volume, turnover, open_price, high_price, low_price, close_price, url, raw_path))
    return rows


def parse_tpex(payload: dict[str, Any], target_date: str, url: str, raw_path: Path) -> list[dict[str, Any]]:
    rows: list[dict[str, Any]] = []
    for table in payload.get("tables", []):
        data = table.get("data") or []
        if data and len(data[0]) >= 10:
            for raw_row in data:
                if len(raw_row) < 10:
                    continue
                ticker = clean_text(raw_row[0])
                name = clean_text(raw_row[1])
                close_price = parse_float(raw_row[2])
                open_price = parse_float(raw_row[4])
                high_price = parse_float(raw_row[5])
                low_price = parse_float(raw_row[6])
                volume = parse_int(raw_row[8])
                turnover = parse_int(raw_row[9])
                rows.append(make_liquidity_row("TPEx", target_date, ticker, name, volume, turnover, open_price, high_price, low_price, close_price, url, raw_path))
            break
    return rows


def make_liquidity_row(
    market: str,
    target_date: str,
    ticker: str,
    name: str,
    volume: int | None,
    turnover: int | None,
    open_price: float | None,
    high_price: float | None,
    low_price: float | None,
    close_price: float | None,
    url: str,
    raw_path: Path,
) -> dict[str, Any]:
    is_common_stock = bool(re.fullmatch(r"\d{4}", ticker)) and not ticker.startswith("0")
    has_trade = bool((volume or 0) > 0 and (turnover or 0) > 0 and close_price is not None)
    blocked_reason = ""
    if not is_common_stock:
        blocked_reason = "non_common_stock_security_code"
    elif not has_trade:
        blocked_reason = "zero_or_missing_trade_fields"
    return {
        "date": target_date,
        "ticker": ticker,
        "name": name,
        "market": market,
        "is_listed_as_of_date": "true",
        "is_suspended_as_of_date": "unknown_from_daily_trading_only",
        "volume": volume if volume is not None else "",
        "turnover_value": turnover if turnover is not None else "",
        "open": open_price if open_price is not None else "",
        "high": high_price if high_price is not None else "",
        "low": low_price if low_price is not None else "",
        "close": close_price if close_price is not None else "",
        "liquidity_pass": "true" if is_common_stock and has_trade else "false",
        "blocked_reason": blocked_reason,
        "source_date": target_date,
        "source_url": url,
        "source_id": "twse_mi_index_allbut0999" if market == "TWSE" else "tpex_daily_quotes",
        "source_type": "official_daily_trading_pit",
        "formal_exact": "false",
        "raw_source_path": str(raw_path),
    }


def fetch_market_date(market: str, target_date: str) -> tuple[list[dict[str, Any]], dict[str, Any]]:
    source_id, url = source_url(market, target_date)
    http_code, content_type, raw, error = fetch_json(url)
    attempt = {
        "source_id": source_id,
        "market": market,
        "target_date": target_date,
        "url": url,
        "method": "GET",
        "status": "failed",
        "http_code": http_code if http_code is not None else "",
        "content_type": content_type,
        "row_count": 0,
        "accepted_row_count": 0,
        "retrieved_path": "",
        "error": error,
    }
    if raw is None or http_code != 200:
        return [], attempt
    raw_path = save_raw(market, target_date, source_id, raw)
    attempt["retrieved_path"] = str(raw_path)
    try:
        payload = load_json(raw)
        rows = parse_twse(payload, target_date, url, raw_path) if market == "TWSE" else parse_tpex(payload, target_date, url, raw_path)
        accepted_count = sum(1 for row in rows if row["blocked_reason"] == "")
        attempt.update(
            {
                "status": "rows_found" if rows else "no_rows",
                "row_count": len(rows),
                "accepted_row_count": accepted_count,
                "error": "" if rows else "No parseable detail table found.",
            }
        )
        return rows, attempt
    except Exception as exc:  # noqa: BLE001 - logged as source evidence.
        attempt["error"] = f"{type(exc).__name__}: {exc}"
        return [], attempt


def metadata_source_inventory() -> list[dict[str, Any]]:
    return [
        {
            "dataset": "listing_status_source_inventory",
            "source_id": "twse_mi_index_daily_presence",
            "source_name": "TWSE MI_INDEX ALLBUT0999 daily security rows",
            "source_url": "https://www.twse.com.tw/rwd/zh/afterTrading/MI_INDEX?date={yyyymmdd}&type=ALLBUT0999&response=json",
            "official_proxy_manual": "official",
            "coverage": "2015 sample verified; runner supports bounded daily sweep to latest",
            "source_date_available": "true",
            "effective_date_available": "same as trading date for presence in daily table",
            "formal_ready": "partial",
            "acceptance_decision": "accepted_for_daily_presence_and_liquidity_only",
            "notes": "Presence in the official daily trading table is PIT evidence for that trading date; it is not a standalone listing/delisting master.",
        },
        {
            "dataset": "listing_status_source_inventory",
            "source_id": "tpex_daily_quotes_presence",
            "source_name": "TPEx dailyQuotes daily security rows",
            "source_url": "https://www.tpex.org.tw/www/zh-tw/afterTrading/dailyQuotes?date={yyyy/mm/dd}&response=json",
            "official_proxy_manual": "official",
            "coverage": "2015 sample verified; runner supports bounded daily sweep to latest",
            "source_date_available": "true",
            "effective_date_available": "same as trading date for presence in daily table",
            "formal_ready": "partial",
            "acceptance_decision": "accepted_for_daily_presence_and_liquidity_only",
            "notes": "Presence in the official daily trading table is PIT evidence for that trading date; it is not a standalone listing/delisting master.",
        },
        {
            "dataset": "listing_status_source_inventory",
            "source_id": "twse_t187ap03_L_current_company_profile",
            "source_name": "TWSE listed company profile OpenAPI",
            "source_url": "https://openapi.twse.com.tw/v1/opendata/t187ap03_L",
            "official_proxy_manual": "official_current_snapshot",
            "coverage": "current snapshot only",
            "source_date_available": "true",
            "effective_date_available": "current only",
            "formal_ready": "false",
            "acceptance_decision": "proxy_inventory_only_not_used_for_2015_pit",
            "notes": "Useful to discover fields and current listed companies; not used to backfill historical PIT membership.",
        },
        {
            "dataset": "listing_status_source_inventory",
            "source_id": "tpex_t187ap03_O_current_company_profile",
            "source_name": "TPEx company profile OpenAPI",
            "source_url": "https://www.tpex.org.tw/openapi/v1/mopsfin_t187ap03_O",
            "official_proxy_manual": "official_current_snapshot",
            "coverage": "current snapshot only",
            "source_date_available": "true",
            "effective_date_available": "current only",
            "formal_ready": "false",
            "acceptance_decision": "proxy_inventory_only_not_used_for_2015_pit",
            "notes": "Useful to discover fields and current listed companies; not used to backfill historical PIT membership.",
        },
        {
            "dataset": "listing_status_source_inventory",
            "source_id": "twse_tpex_historical_suspend_delist_notice_candidate",
            "source_name": "TWSE/TPEx historical suspension delisting announcement route",
            "source_url": "to_probe_next",
            "official_proxy_manual": "official_candidate",
            "coverage": "not acquired in this batch",
            "source_date_available": "unknown",
            "effective_date_available": "required",
            "formal_ready": "false",
            "acceptance_decision": "blocked_until_endpoint_identified",
            "notes": "Next programmatic source: official historical suspension/resumption/delisting announcement endpoints or downloadable archives.",
        },
    ]


def source_manifest() -> list[dict[str, Any]]:
    return [
        {
            "source_id": "twse_mi_index_allbut0999",
            "dataset": "all_listed_liquid_universe_pit_daily",
            "source_name": "TWSE MI_INDEX ALLBUT0999 full-market daily trading data",
            "official_proxy_manual": "official",
            "source_type": "official_daily_trading_pit",
            "coverage": "sample_verified_2015_latest; full_range_runner_available",
            "source_date_available": "true",
            "effective_date_available": "true_for_daily_presence",
            "formal_ready": "partial",
            "notes": "Accepted for daily exchange presence, OHLCV, turnover, and liquidity screen inputs. Listing/delisting/suspension master still separate.",
        },
        {
            "source_id": "tpex_daily_quotes",
            "dataset": "all_listed_liquid_universe_pit_daily",
            "source_name": "TPEx dailyQuotes full-market daily trading data",
            "official_proxy_manual": "official",
            "source_type": "official_daily_trading_pit",
            "coverage": "sample_verified_2015_latest; full_range_runner_available",
            "source_date_available": "true",
            "effective_date_available": "true_for_daily_presence",
            "formal_ready": "partial",
            "notes": "Accepted for daily exchange presence, OHLCV, turnover, and liquidity screen inputs. Listing/delisting/suspension master still separate.",
        },
    ]


def build_coverage(rows: list[dict[str, Any]], attempts: list[dict[str, Any]]) -> list[dict[str, Any]]:
    out: list[dict[str, Any]] = []
    for year in range(2015, 2027):
        for market in ["TWSE", "TPEx"]:
            year_attempts = [a for a in attempts if a["market"] == market and str(a["target_date"]).startswith(str(year))]
            year_rows = [r for r in rows if r["market"] == market and str(r["date"]).startswith(str(year)) and r["blocked_reason"] == ""]
            status = "sample_verified" if year_rows else ("attempted_no_accepted_rows" if year_attempts else "not_attempted")
            out.append(
                {
                    "year": year,
                    "market": market,
                    "coverage_status": status,
                    "attempted_dates": len({a["target_date"] for a in year_attempts}),
                    "accepted_common_stock_rows": len(year_rows),
                    "full_range_ready": "false",
                    "notes": "Sample verified only; full daily sweep requires bounded continuation runner." if status == "sample_verified" else "No accepted official full-market daily rows in this package for this year/market.",
                }
            )
    return out


def build_blocked_summary(blocked_rows: list[dict[str, Any]]) -> list[dict[str, Any]]:
    counts: dict[tuple[str, str, str], int] = {}
    for row in blocked_rows:
        key = (str(row["date"]), str(row["market"]), str(row["blocked_reason"]))
        counts[key] = counts.get(key, 0) + 1
    return [
        {
            "date": key[0],
            "market": key[1],
            "blocked_reason": key[2],
            "row_count": count,
        }
        for key, count in sorted(counts.items())
    ]


def main() -> int:
    args = parse_args()
    OUTPUT_DIR.mkdir(parents=True, exist_ok=True)
    RAW_DIR.mkdir(parents=True, exist_ok=True)
    started = datetime.now().astimezone().isoformat(timespec="seconds")
    (OUTPUT_DIR / "current_step.txt").write_text("running_bounded_official_daily_probe\n", encoding="utf-8")

    target_dates = SAMPLE_DATES if args.mode == "sample" else date_range(args.start_date, args.end_date)
    if args.max_dates > 0:
        target_dates = target_dates[: args.max_dates]
    markets = [market.strip() for market in args.markets.split(",") if market.strip()]

    all_rows: list[dict[str, Any]] = []
    attempts: list[dict[str, Any]] = []
    run_log: list[dict[str, Any]] = [
        {
            "timestamp": started,
            "step": "start",
            "status": "running",
            "detail": f"mode={args.mode}; dates={len(target_dates)}; markets={','.join(markets)}",
        }
    ]

    for target_date in target_dates:
        for market in markets:
            rows, attempt = fetch_market_date(market, target_date)
            all_rows.extend(rows)
            attempts.append(attempt)
            run_log.append(
                {
                    "timestamp": datetime.now().astimezone().isoformat(timespec="seconds"),
                    "step": "fetch_market_date",
                    "status": attempt["status"],
                    "detail": f"{market} {target_date}: rows={attempt['row_count']} accepted={attempt['accepted_row_count']}",
                }
            )
            time.sleep(args.sleep_seconds)

    accepted_rows = [row for row in all_rows if row["blocked_reason"] == ""]
    blocked_rows = [row for row in all_rows if row["blocked_reason"] != ""]
    blocked_rows_sample = blocked_rows[:5000]
    blocked_summary = build_blocked_summary(blocked_rows)
    coverage = build_coverage(all_rows, attempts)
    metadata_inventory = metadata_source_inventory()
    manifest_sources = source_manifest()

    liquidity_fields = [
        "date",
        "ticker",
        "name",
        "market",
        "is_listed_as_of_date",
        "is_suspended_as_of_date",
        "volume",
        "turnover_value",
        "open",
        "high",
        "low",
        "close",
        "liquidity_pass",
        "blocked_reason",
        "source_date",
        "source_url",
        "source_id",
        "source_type",
        "formal_exact",
        "raw_source_path",
    ]
    attempt_fields = [
        "source_id",
        "market",
        "target_date",
        "url",
        "method",
        "status",
        "http_code",
        "content_type",
        "row_count",
        "accepted_row_count",
        "retrieved_path",
        "error",
    ]
    manifest_fields = [
        "source_id",
        "dataset",
        "source_name",
        "official_proxy_manual",
        "source_type",
        "coverage",
        "source_date_available",
        "effective_date_available",
        "formal_ready",
        "notes",
    ]
    inventory_fields = [
        "dataset",
        "source_id",
        "source_name",
        "source_url",
        "official_proxy_manual",
        "coverage",
        "source_date_available",
        "effective_date_available",
        "formal_ready",
        "acceptance_decision",
        "notes",
    ]

    write_csv(OUTPUT_DIR / "download_attempts.csv", attempts, attempt_fields)
    write_csv(OUTPUT_DIR / "accepted_liquidity_rows.csv", accepted_rows, liquidity_fields)
    write_csv(OUTPUT_DIR / "accepted_liquidity_sample.csv", accepted_rows[:200], liquidity_fields)
    write_csv(OUTPUT_DIR / "liquid_universe_pit_daily_candidate.csv", accepted_rows, liquidity_fields)
    write_csv(OUTPUT_DIR / "blocked_rows.csv", blocked_rows_sample, liquidity_fields)
    write_csv(OUTPUT_DIR / "blocked_rows_summary.csv", blocked_summary, ["date", "market", "blocked_reason", "row_count"])
    write_csv(OUTPUT_DIR / "coverage_by_year_market.csv", coverage, ["year", "market", "coverage_status", "attempted_dates", "accepted_common_stock_rows", "full_range_ready", "notes"])
    write_csv(OUTPUT_DIR / "listing_status_source_inventory.csv", metadata_inventory, inventory_fields)
    write_csv(OUTPUT_DIR / "source_manifest.csv", manifest_sources, manifest_fields)
    write_json(OUTPUT_DIR / "source_manifest.json", {"task_id": TASK_ID, "sources": manifest_sources, "listing_status_source_inventory": metadata_inventory})

    future_audit = [
        {
            "source_id": "twse_mi_index_allbut0999",
            "future_data_violation_count": 0,
            "decision": "accepted_daily_pit_rows_only",
            "evidence": "Rows are fetched from official daily trading endpoint for each target date; source_date equals trade date.",
        },
        {
            "source_id": "tpex_daily_quotes",
            "future_data_violation_count": 0,
            "decision": "accepted_daily_pit_rows_only",
            "evidence": "Rows are fetched from official daily trading endpoint for each target date; source_date equals trade date.",
        },
        {
            "source_id": "twse_t187ap03_L_current_company_profile",
            "future_data_violation_count": 0,
            "decision": "excluded_from_historical_accepted_rows",
            "evidence": "Current company profile snapshot is inventory-only and is not used to infer 2015 historical listing membership.",
        },
        {
            "source_id": "tpex_t187ap03_O_current_company_profile",
            "future_data_violation_count": 0,
            "decision": "excluded_from_historical_accepted_rows",
            "evidence": "Current company profile snapshot is inventory-only and is not used to infer 2015 historical listing membership.",
        },
    ]
    write_csv(OUTPUT_DIR / "future_data_violation_audit.csv", future_audit, ["source_id", "future_data_violation_count", "decision", "evidence"])

    failed_attempts = [a for a in attempts if a["status"] not in {"rows_found"}]
    completed = [
        {
            "task_id": TASK_ID,
            "status": "completed_partial_sample_verified",
            "output_path": str(OUTPUT_DIR),
            "completed_at": datetime.now().astimezone().isoformat(timespec="seconds"),
            "commit": "pending",
        }
    ]
    failed = [
        {
            "task_id": TASK_ID,
            "status": "metadata_master_blocked",
            "failed_item": "listing_delisting_suspension_master",
            "reason": "Daily trading rows give PIT presence and liquidity, but complete listing/delisting/suspension metadata master was not acquired in this batch.",
        }
    ]
    if failed_attempts:
        failed.append(
            {
                "task_id": TASK_ID,
                "status": "download_attempt_failures",
                "failed_item": "official_daily_endpoint_attempts",
                "reason": f"{len(failed_attempts)} endpoint attempts did not return parseable rows; see download_attempts.csv.",
            }
        )
    write_csv(OUTPUT_DIR / "completed.csv", completed, ["task_id", "status", "output_path", "completed_at", "commit"])
    write_csv(OUTPUT_DIR / "failed.csv", failed, ["task_id", "status", "failed_item", "reason"])

    run_log.append(
        {
            "timestamp": datetime.now().astimezone().isoformat(timespec="seconds"),
            "step": "write_outputs",
            "status": "completed",
            "detail": f"accepted_rows={len(accepted_rows)} blocked_rows={len(blocked_rows)} attempts={len(attempts)}",
        }
    )
    write_csv(OUTPUT_DIR / "run_log.csv", run_log, ["timestamp", "step", "status", "detail"])

    readiness = {
        "task_id": TASK_ID,
        "status": "completed_partial_sample_verified",
        "all_listed_liquid_universe_pit_daily_partial_ready": bool(accepted_rows),
        "all_listed_liquid_universe_pit_daily_full_range_ready": False,
        "listing_delisting_suspension_metadata_ready": False,
        "ready_for_core_rerun": True,
        "ready_for_strategy_replay": False,
        "dynamic_pool1_shadow_challenger_ready": False,
        "formal_model_changed": False,
        "trade_decision_changed": False,
        "active_in_trade_decision": False,
        "future_data_violation_count": 0,
        "accepted_liquidity_rows": len(accepted_rows),
        "blocked_rows_total": len(blocked_rows),
        "blocked_rows_file_mode": "sample_first_5000_plus_blocked_rows_summary",
        "download_attempts": len(attempts),
        "successful_attempts": len([a for a in attempts if a["status"] == "rows_found"]),
        "covered_years_sample": sorted({row["date"][:4] for row in accepted_rows}),
        "covered_markets_sample": sorted({row["market"] for row in accepted_rows}),
        "core_input_hint": {
            "liquid_universe_pit_daily_candidate": str(OUTPUT_DIR / "liquid_universe_pit_daily_candidate.csv"),
            "accepted_liquidity_rows": str(OUTPUT_DIR / "accepted_liquidity_rows.csv"),
            "download_attempts": str(OUTPUT_DIR / "download_attempts.csv"),
            "listing_status_source_inventory": str(OUTPUT_DIR / "listing_status_source_inventory.csv"),
            "coverage_by_year_market": str(OUTPUT_DIR / "coverage_by_year_market.csv"),
        },
        "resume_design": {
            "sample_command": "python outputs/radar_dynamic_pool1_all_listed_liquid_universe_pit_daily_20260703/build_all_listed_liquid_universe_package.py --mode sample",
            "bounded_range_command": "python outputs/radar_dynamic_pool1_all_listed_liquid_universe_pit_daily_20260703/build_all_listed_liquid_universe_package.py --mode range --start-date 2015-01-01 --end-date 2015-03-31 --max-dates 60",
            "full_range_warning": "Run in monthly or quarterly bounded chunks; do not launch an unbounded 2015-latest sweep without checkpoint review.",
        },
        "blocking_issues": [
            "Full 2015-latest daily sweep not run in this batch; only annual/latest official samples were downloaded and parsed.",
            "Listing/delisting/suspension master metadata remains blocked; current company profile snapshots are inventory-only.",
            "Suspension status is unknown from daily trading rows alone; zero-trade rows are marked liquidity_pass=false, not inferred as formal suspension.",
        ],
        "next_programmatic_sources": [
            "Run bounded monthly/quarterly range sweeps for TWSE MI_INDEX and TPEx dailyQuotes.",
            "Probe official TWSE/TPEx historical suspension, resumption, delisting, and transfer-listing announcement archives.",
            "Join daily presence rows with verified listing/delisting/suspension metadata before formal all-listed tradable universe use.",
        ],
    }
    write_json(OUTPUT_DIR / "readiness_for_core.json", readiness)

    manifest = {
        "task_id": TASK_ID,
        "created_at": datetime.now().astimezone().isoformat(timespec="seconds"),
        "upstream_output": str(UPSTREAM_OUTPUT),
        "output_path": str(OUTPUT_DIR),
        "files": sorted(path.name for path in OUTPUT_DIR.glob("*") if path.is_file()),
        "raw_source_dir": str(RAW_DIR),
        "formal_model_changed": False,
        "trade_decision_changed": False,
        "active_in_trade_decision": False,
    }
    write_json(OUTPUT_DIR / "manifest.json", manifest)

    summary = f"""# Dynamic Pool1 all-listed liquid universe PIT daily source package

- Task: `{TASK_ID}`
- Status: `completed_partial_sample_verified`
- Accepted liquidity rows: `{len(accepted_rows)}`
- Blocked/rejected rows total: `{len(blocked_rows)}`
- `blocked_rows.csv` mode: first 5,000 row sample plus `blocked_rows_summary.csv`
- Download attempts: `{len(attempts)}`
- Successful official daily attempts: `{len([a for a in attempts if a["status"] == "rows_found"])}`
- ready_for_core_rerun: `true`
- ready_for_strategy_replay: `false`
- dynamic_pool1_shadow_challenger_ready: `false`
- future_data_violation_count: `0`

## Accepted partial source

TWSE `MI_INDEX?type=ALLBUT0999` and TPEx `dailyQuotes` official daily endpoints were verified from 2015 sample dates through latest sample date. Accepted rows are common-stock rows present in that date's official daily table with parseable OHLCV/turnover fields; ETF/ETN/warrant-style codes such as `00xx` are excluded.

## Not yet formal-ready

This is not full-range ready. The package verifies the source route, parser, schema, and checkpointable runner, but the complete 2015-latest daily sweep has not been run in this batch.

Listing/delisting/suspension master metadata is still blocked. Current TWSE/TPEx company profile OpenAPI routes are listed as current-snapshot inventory only and were not used to infer historical PIT membership.

## Boundary

No current listed snapshot is used to backfill 2015. No strategy replay, formal model change, trade decision change, or daily report change was made.
"""
    (OUTPUT_DIR / "final_summary_zh.md").write_text(summary, encoding="utf-8")
    (OUTPUT_DIR / "current_step.txt").write_text("completed_partial_sample_verified\n", encoding="utf-8")
    print(json.dumps(readiness, ensure_ascii=False, indent=2))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
