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


TASK_ID = "TASK-RADAR-DATA-DYNAMIC-POOL1-ALL-LISTED-LIQUID-UNIVERSE-FULL-SWEEP-20260703"
OUTPUT_DIR = Path(__file__).resolve().parent
SHARD_DIR = OUTPUT_DIR / "shards"
RAW_DIR = OUTPUT_DIR / "raw_sources"
UPSTREAM_OUTPUT = OUTPUT_DIR.parent / "radar_dynamic_pool1_all_listed_liquid_universe_pit_daily_20260703"

MARKETS = ("TWSE", "TPEx")
START_DATE = "2015-01-01"
DEFAULT_END_DATE = "2026-07-03"

LIQUIDITY_FIELDS = [
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
ATTEMPT_FIELDS = [
    "run_id",
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
    "blocked_row_count",
    "retrieved_path",
    "error",
    "attempted_at",
]


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="Run Dynamic Pool1 all-listed liquid universe full daily sweep.")
    parser.add_argument("--start-date", default=START_DATE)
    parser.add_argument("--end-date", default="auto", help="YYYY-MM-DD or auto. auto probes latest available at/before 2026-07-03.")
    parser.add_argument("--markets", default=",".join(MARKETS))
    parser.add_argument("--sleep-seconds", type=float, default=0.08)
    parser.add_argument("--retry-wait-seconds", type=float, default=8.0)
    parser.add_argument("--max-attempts", type=int, default=0, help="Bound a run while preserving resume checkpoint.")
    parser.add_argument("--save-raw", action="store_true", help="Save raw JSON to raw_sources/. Ignored by git.")
    parser.add_argument("--rebuild-only", action="store_true", help="Rebuild summaries from existing attempts/shards without network calls.")
    return parser.parse_args()


def write_csv(path: Path, rows: list[dict[str, Any]], fieldnames: list[str]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("w", newline="", encoding="utf-8-sig") as handle:
        writer = csv.DictWriter(handle, fieldnames=fieldnames, extrasaction="ignore")
        writer.writeheader()
        writer.writerows(rows)


def append_csv(path: Path, rows: list[dict[str, Any]], fieldnames: list[str]) -> None:
    if not rows:
        return
    path.parent.mkdir(parents=True, exist_ok=True)
    write_header = not path.exists() or path.stat().st_size == 0
    with path.open("a", newline="", encoding="utf-8-sig") as handle:
        writer = csv.DictWriter(handle, fieldnames=fieldnames, extrasaction="ignore")
        if write_header:
            writer.writeheader()
        writer.writerows(rows)


def write_json(path: Path, payload: Any) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(payload, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")


def read_csv(path: Path) -> list[dict[str, str]]:
    if not path.exists():
        return []
    with path.open("r", newline="", encoding="utf-8-sig") as handle:
        return list(csv.DictReader(handle))


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


def weekdays(start: str, end: str) -> list[str]:
    cur = date.fromisoformat(start)
    last = date.fromisoformat(end)
    out: list[str] = []
    while cur <= last:
        if cur.weekday() < 5:
            out.append(cur.isoformat())
        cur += timedelta(days=1)
    return out


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


def fetch_json(url: str, retry_wait_seconds: float = 8.0, max_retries: int = 3) -> tuple[int | None, str, bytes | None, str]:
    request = urllib.request.Request(
        url,
        headers={
            "User-Agent": "Mozilla/5.0 DynamicPool1FullSweep/1.0",
            "Accept": "application/json,text/plain,*/*",
        },
    )
    last_error = ""
    for attempt_index in range(max_retries + 1):
        try:
            with urllib.request.urlopen(request, timeout=35) as response:
                return response.status, response.headers.get("content-type", ""), response.read(), ""
        except urllib.error.HTTPError as exc:
            body = exc.read()
            last_error = f"HTTPError: {exc}"
            if exc.code in {307, 429, 503} and attempt_index < max_retries:
                time.sleep(retry_wait_seconds * (attempt_index + 1))
                continue
            return exc.code, exc.headers.get("content-type", ""), body, last_error
        except Exception as exc:  # noqa: BLE001 - captured in download_attempts.csv.
            last_error = f"{type(exc).__name__}: {exc}"
            if attempt_index < max_retries:
                time.sleep(retry_wait_seconds * (attempt_index + 1))
                continue
            return None, "", None, last_error
    return None, "", None, last_error


def is_common_stock(ticker: str) -> bool:
    return bool(re.fullmatch(r"\d{4}", ticker)) and not ticker.startswith("0")


def make_row(
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
    source_id: str,
    raw_path: str,
) -> dict[str, Any]:
    blocked_reason = ""
    if not is_common_stock(ticker):
        blocked_reason = "non_common_stock_security_code"
    elif not bool((volume or 0) > 0 and (turnover or 0) > 0 and close_price is not None):
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
        "liquidity_pass": "true" if not blocked_reason else "false",
        "blocked_reason": blocked_reason,
        "source_date": target_date,
        "source_url": url,
        "source_id": source_id,
        "source_type": "official_daily_trading_pit",
        "formal_exact": "false",
        "raw_source_path": raw_path,
    }


def parse_twse(payload: dict[str, Any], target_date: str, url: str, source_id: str, raw_path: str) -> list[dict[str, Any]]:
    detail_table = None
    for table in payload.get("tables", []):
        data = table.get("data") or []
        fields = table.get("fields") or []
        if data and len(fields) >= 15 and len(data[0]) >= 15:
            detail_table = table
            break
    if not detail_table:
        return []
    out: list[dict[str, Any]] = []
    for raw_row in detail_table.get("data", []):
        if len(raw_row) < 9:
            continue
        out.append(
            make_row(
                "TWSE",
                target_date,
                clean_text(raw_row[0]),
                clean_text(raw_row[1]),
                parse_int(raw_row[2]),
                parse_int(raw_row[4]),
                parse_float(raw_row[5]),
                parse_float(raw_row[6]),
                parse_float(raw_row[7]),
                parse_float(raw_row[8]),
                url,
                source_id,
                raw_path,
            )
        )
    return out


def parse_tpex(payload: dict[str, Any], target_date: str, url: str, source_id: str, raw_path: str) -> list[dict[str, Any]]:
    out: list[dict[str, Any]] = []
    for table in payload.get("tables", []):
        data = table.get("data") or []
        if data and len(data[0]) >= 10:
            for raw_row in data:
                if len(raw_row) < 10:
                    continue
                out.append(
                    make_row(
                        "TPEx",
                        target_date,
                        clean_text(raw_row[0]),
                        clean_text(raw_row[1]),
                        parse_int(raw_row[8]),
                        parse_int(raw_row[9]),
                        parse_float(raw_row[4]),
                        parse_float(raw_row[5]),
                        parse_float(raw_row[6]),
                        parse_float(raw_row[2]),
                        url,
                        source_id,
                        raw_path,
                    )
                )
            break
    return out


def save_raw(market: str, target_date: str, source_id: str, raw: bytes) -> str:
    path = RAW_DIR / f"{market.lower()}_{target_date.replace('-', '')}_{source_id}.json"
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_bytes(raw)
    return str(path)


def shard_path(target_date: str) -> Path:
    return SHARD_DIR / f"accepted_liquidity_rows_{target_date[:7].replace('-', '_')}.csv"


def completed_pairs() -> set[tuple[str, str]]:
    done: set[tuple[str, str]] = set()
    for row in read_csv(OUTPUT_DIR / "download_attempts.csv"):
        if row.get("status") in {"rows_found", "no_rows", "market_holiday_or_no_trading"}:
            done.add((row.get("market", ""), row.get("target_date", "")))
    return done


def fetch_market_date(market: str, target_date: str, run_id: str, save_raw_enabled: bool, retry_wait_seconds: float) -> dict[str, Any]:
    source_id, url = source_url(market, target_date)
    attempted_at = datetime.now().astimezone().isoformat(timespec="seconds")
    http_code, content_type, raw, error = fetch_json(url, retry_wait_seconds=retry_wait_seconds)
    attempt: dict[str, Any] = {
        "run_id": run_id,
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
        "blocked_row_count": 0,
        "retrieved_path": "",
        "error": error,
        "attempted_at": attempted_at,
    }
    if raw is None or http_code != 200:
        append_csv(OUTPUT_DIR / "download_attempts.csv", [attempt], ATTEMPT_FIELDS)
        return attempt
    raw_path = save_raw(market, target_date, source_id, raw) if save_raw_enabled else ""
    attempt["retrieved_path"] = raw_path
    try:
        payload = json.loads(raw.decode("utf-8-sig"))
        rows = parse_twse(payload, target_date, url, source_id, raw_path) if market == "TWSE" else parse_tpex(payload, target_date, url, source_id, raw_path)
        accepted = [row for row in rows if row["blocked_reason"] == ""]
        blocked = [row for row in rows if row["blocked_reason"] != ""]
        status = "rows_found" if rows else "market_holiday_or_no_trading"
        attempt.update(
            {
                "status": status,
                "row_count": len(rows),
                "accepted_row_count": len(accepted),
                "blocked_row_count": len(blocked),
                "error": "" if rows else "Official endpoint returned no parseable daily rows.",
            }
        )
        if accepted:
            append_csv(shard_path(target_date), accepted, LIQUIDITY_FIELDS)
        if blocked:
            append_blocked_summary(blocked)
    except Exception as exc:  # noqa: BLE001 - captured in download_attempts.csv.
        attempt["error"] = f"{type(exc).__name__}: {exc}"
    append_csv(OUTPUT_DIR / "download_attempts.csv", [attempt], ATTEMPT_FIELDS)
    return attempt


def append_blocked_summary(blocked_rows: list[dict[str, Any]]) -> None:
    counts: dict[tuple[str, str, str], int] = {}
    for row in blocked_rows:
        key = (str(row["date"]), str(row["market"]), str(row["blocked_reason"]))
        counts[key] = counts.get(key, 0) + 1
    rows = [
        {"date": key[0], "market": key[1], "blocked_reason": key[2], "row_count": value}
        for key, value in sorted(counts.items())
    ]
    append_csv(OUTPUT_DIR / "blocked_rows_summary.csv", rows, ["date", "market", "blocked_reason", "row_count"])


def has_rows_for(market: str, target_date: str) -> bool:
    source_id, url = source_url(market, target_date)
    http_code, _content_type, raw, _error = fetch_json(url)
    if raw is None or http_code != 200:
        return False
    try:
        payload = json.loads(raw.decode("utf-8-sig"))
        rows = parse_twse(payload, target_date, url, source_id, "") if market == "TWSE" else parse_tpex(payload, target_date, url, source_id, "")
        return any(row["blocked_reason"] == "" for row in rows)
    except Exception:
        return False


def resolve_end_date(value: str) -> str:
    if value != "auto":
        return value
    cur = date.fromisoformat(DEFAULT_END_DATE)
    for _ in range(14):
        if cur.weekday() < 5 and all(has_rows_for(market, cur.isoformat()) for market in MARKETS):
            return cur.isoformat()
        cur -= timedelta(days=1)
    return "2026-07-02"


def write_static_sources() -> None:
    source_manifest = [
        {
            "source_id": "twse_mi_index_allbut0999",
            "dataset": "all_listed_liquid_universe_pit_daily",
            "source_name": "TWSE MI_INDEX ALLBUT0999 full-market daily trading data",
            "official_proxy_manual": "official",
            "source_type": "official_daily_trading_pit",
            "coverage": "full sweep candidate; see coverage_by_year_market.csv",
            "source_date_available": "true",
            "effective_date_available": "true_for_daily_presence",
            "formal_ready": "candidate_not_exact",
            "notes": "Accepted for daily exchange presence, OHLCV, turnover, and liquidity screen inputs. Listing/delisting/suspension master remains separate.",
        },
        {
            "source_id": "tpex_daily_quotes",
            "dataset": "all_listed_liquid_universe_pit_daily",
            "source_name": "TPEx dailyQuotes full-market daily trading data",
            "official_proxy_manual": "official",
            "source_type": "official_daily_trading_pit",
            "coverage": "full sweep candidate; see coverage_by_year_market.csv",
            "source_date_available": "true",
            "effective_date_available": "true_for_daily_presence",
            "formal_ready": "candidate_not_exact",
            "notes": "Accepted for daily exchange presence, OHLCV, turnover, and liquidity screen inputs. Listing/delisting/suspension master remains separate.",
        },
    ]
    write_csv(
        OUTPUT_DIR / "source_manifest.csv",
        source_manifest,
        ["source_id", "dataset", "source_name", "official_proxy_manual", "source_type", "coverage", "source_date_available", "effective_date_available", "formal_ready", "notes"],
    )
    write_json(OUTPUT_DIR / "source_manifest.json", {"task_id": TASK_ID, "sources": source_manifest})
    listing_inventory = [
        {
            "source_id": "twse_mi_index_daily_presence",
            "official_proxy_manual": "official",
            "status": "accepted_for_daily_presence_and_liquidity_only",
            "notes": "Daily rows prove PIT presence in the trading table but are not a listing/delisting/suspension master.",
        },
        {
            "source_id": "tpex_daily_quotes_presence",
            "official_proxy_manual": "official",
            "status": "accepted_for_daily_presence_and_liquidity_only",
            "notes": "Daily rows prove PIT presence in the trading table but are not a listing/delisting/suspension master.",
        },
        {
            "source_id": "twse_tpex_current_company_profile",
            "official_proxy_manual": "official_current_snapshot",
            "status": "excluded_from_historical_pit_rows",
            "notes": "Current company profile snapshots are not used to infer 2015 historical membership.",
        },
    ]
    write_csv(OUTPUT_DIR / "listing_status_source_inventory.csv", listing_inventory, ["source_id", "official_proxy_manual", "status", "notes"])
    future_audit = [
        {
            "source_id": "twse_mi_index_allbut0999",
            "future_data_violation_count": 0,
            "decision": "accepted_daily_pit_rows_only",
            "evidence": "Rows are fetched by trade date from official daily endpoint; source_date equals target trading date.",
        },
        {
            "source_id": "tpex_daily_quotes",
            "future_data_violation_count": 0,
            "decision": "accepted_daily_pit_rows_only",
            "evidence": "Rows are fetched by trade date from official daily endpoint; source_date equals target trading date.",
        },
        {
            "source_id": "current_company_profile_snapshots",
            "future_data_violation_count": 0,
            "decision": "excluded",
            "evidence": "Current snapshots are documented only in listing_status_source_inventory and not used in accepted rows.",
        },
    ]
    write_csv(OUTPUT_DIR / "future_data_violation_audit.csv", future_audit, ["source_id", "future_data_violation_count", "decision", "evidence"])


def rebuild_summaries(start_date: str, end_date: str) -> dict[str, Any]:
    attempts = read_csv(OUTPUT_DIR / "download_attempts.csv")
    latest_attempt_by_pair: dict[tuple[str, str], dict[str, str]] = {}
    for row in attempts:
        latest_attempt_by_pair[(row.get("market", ""), row.get("target_date", ""))] = row
    latest_attempts = list(latest_attempt_by_pair.values())
    shard_rows: list[dict[str, Any]] = []
    for path in sorted(SHARD_DIR.glob("accepted_liquidity_rows_*.csv")):
        rows = read_csv(path)
        if not rows:
            continue
        first_date = min(row["date"] for row in rows)
        last_date = max(row["date"] for row in rows)
        shard_rows.append(
            {
                "shard_file": str(path),
                "row_count": len(rows),
                "first_date": first_date,
                "last_date": last_date,
                "markets": ";".join(sorted({row["market"] for row in rows})),
                "ticker_count": len({row["ticker"] for row in rows}),
                "git_tracked": "false",
            }
        )
    write_csv(OUTPUT_DIR / "accepted_liquidity_shard_manifest.csv", shard_rows, ["shard_file", "row_count", "first_date", "last_date", "markets", "ticker_count", "git_tracked"])

    expected_pairs = {(market, day) for day in weekdays(start_date, end_date) for market in MARKETS}
    completed = {(row.get("market", ""), row.get("target_date", "")) for row in latest_attempts if row.get("status") in {"rows_found", "market_holiday_or_no_trading"}}
    failed = [row for row in latest_attempts if row.get("status") not in {"rows_found", "market_holiday_or_no_trading"}]
    missing_pairs = sorted(expected_pairs - completed)

    progress_rows: list[dict[str, Any]] = []
    for year in range(date.fromisoformat(start_date).year, date.fromisoformat(end_date).year + 1):
        for market in MARKETS:
            year_pairs = {(m, d) for (m, d) in expected_pairs if m == market and d.startswith(str(year))}
            year_attempts = [row for row in latest_attempts if row.get("market") == market and row.get("target_date", "").startswith(str(year))]
            ok = [row for row in year_attempts if row.get("status") == "rows_found"]
            no_rows = [row for row in year_attempts if row.get("status") == "market_holiday_or_no_trading"]
            year_missing = year_pairs - {(row.get("market", ""), row.get("target_date", "")) for row in year_attempts if row.get("status") in {"rows_found", "market_holiday_or_no_trading"}}
            accepted_count = sum(int(row.get("accepted_row_count") or 0) for row in year_attempts)
            progress_rows.append(
                {
                    "year": year,
                    "market": market,
                    "expected_weekday_attempts": len(year_pairs),
                    "attempted": len(year_attempts),
                    "rows_found_attempts": len(ok),
                    "no_rows_attempts": len(no_rows),
                    "failed_attempts": len([row for row in year_attempts if row.get("status") not in {"rows_found", "market_holiday_or_no_trading"}]),
                    "missing_attempts": len(year_missing),
                    "accepted_liquidity_rows": accepted_count,
                    "coverage_status": "complete" if not year_missing and not [row for row in year_attempts if row.get("status") not in {"rows_found", "market_holiday_or_no_trading"}] else "partial",
                }
            )
    write_csv(OUTPUT_DIR / "full_sweep_progress.csv", progress_rows, ["year", "market", "expected_weekday_attempts", "attempted", "rows_found_attempts", "no_rows_attempts", "failed_attempts", "missing_attempts", "accepted_liquidity_rows", "coverage_status"])
    write_csv(OUTPUT_DIR / "coverage_by_year_market.csv", progress_rows, ["year", "market", "expected_weekday_attempts", "attempted", "rows_found_attempts", "no_rows_attempts", "failed_attempts", "missing_attempts", "accepted_liquidity_rows", "coverage_status"])
    write_csv(OUTPUT_DIR / "failed.csv", failed, ATTEMPT_FIELDS)
    write_csv(
        OUTPUT_DIR / "missing_dates.csv",
        [{"market": market, "target_date": day} for market, day in missing_pairs],
        ["market", "target_date"],
    )

    total_expected = len(expected_pairs)
    total_completed = len(completed)
    total_accepted = sum(int(row.get("accepted_row_count") or 0) for row in latest_attempts)
    full_ready = total_completed == total_expected and not failed and total_accepted > 0
    return {
        "expected_attempts": total_expected,
        "completed_attempts": total_completed,
        "failed_attempts": len(failed),
        "missing_attempts": len(missing_pairs),
        "accepted_liquidity_rows": total_accepted,
        "shard_count": len(shard_rows),
        "full_ready": full_ready,
        "first_covered_date": min((row["first_date"] for row in shard_rows), default=""),
        "last_covered_date": max((row["last_date"] for row in shard_rows), default=""),
    }


def write_final_outputs(start_date: str, end_date: str, run_id: str) -> dict[str, Any]:
    write_static_sources()
    summary = rebuild_summaries(start_date, end_date)
    readiness = {
        "task_id": TASK_ID,
        "status": "completed_full_sweep_candidate" if summary["full_ready"] else "completed_partial_full_sweep_resume_ready",
        "covered_date_range": {"start": summary["first_covered_date"], "end": summary["last_covered_date"], "requested_start": start_date, "requested_end": end_date},
        "expected_attempts": summary["expected_attempts"],
        "completed_attempts": summary["completed_attempts"],
        "failed_attempts": summary["failed_attempts"],
        "missing_attempts": summary["missing_attempts"],
        "accepted_liquidity_rows": summary["accepted_liquidity_rows"],
        "accepted_shard_count": summary["shard_count"],
        "all_listed_liquid_universe_pit_daily_full_range_ready": summary["full_ready"],
        "listing_delisting_suspension_metadata_ready": False,
        "ready_for_core_rerun": True,
        "ready_for_strategy_replay": False,
        "dynamic_pool1_shadow_challenger_ready": False,
        "formal_model_changed": False,
        "trade_decision_changed": False,
        "active_in_trade_decision": False,
        "future_data_violation_count": 0,
        "large_local_outputs_not_git_tracked": ["shards/", "raw_sources/"],
        "core_input_hint": {
            "accepted_liquidity_shard_manifest": str(OUTPUT_DIR / "accepted_liquidity_shard_manifest.csv"),
            "download_attempts": str(OUTPUT_DIR / "download_attempts.csv"),
            "full_sweep_progress": str(OUTPUT_DIR / "full_sweep_progress.csv"),
            "coverage_by_year_market": str(OUTPUT_DIR / "coverage_by_year_market.csv"),
            "missing_dates": str(OUTPUT_DIR / "missing_dates.csv"),
        },
        "resume_command": f"python outputs/radar_dynamic_pool1_all_listed_liquid_universe_full_sweep_20260703/run_full_sweep.py --start-date {start_date} --end-date {end_date}",
        "next_blockers": [
            "Listing/delisting/suspension master metadata remains separate and is not solved by daily liquidity sweep.",
            "Current company profile snapshots remain excluded from historical PIT membership.",
        ],
    }
    write_json(OUTPUT_DIR / "readiness_for_core.json", readiness)
    manifest = {
        "task_id": TASK_ID,
        "run_id": run_id,
        "created_at": datetime.now().astimezone().isoformat(timespec="seconds"),
        "upstream_output": str(UPSTREAM_OUTPUT),
        "output_path": str(OUTPUT_DIR),
        "files": sorted(path.name for path in OUTPUT_DIR.glob("*") if path.is_file()),
        "local_shard_dir": str(SHARD_DIR),
        "raw_source_dir": str(RAW_DIR),
        "formal_model_changed": False,
        "trade_decision_changed": False,
        "active_in_trade_decision": False,
    }
    write_json(OUTPUT_DIR / "manifest.json", manifest)
    completed_status = "completed_full_sweep_candidate" if summary["full_ready"] else "completed_partial_full_sweep_resume_ready"
    write_csv(
        OUTPUT_DIR / "completed.csv",
        [
            {
                "task_id": TASK_ID,
                "status": completed_status,
                "output_path": str(OUTPUT_DIR),
                "completed_at": datetime.now().astimezone().isoformat(timespec="seconds"),
                "commit": "pending",
            }
        ],
        ["task_id", "status", "output_path", "completed_at", "commit"],
    )
    final = f"""# Dynamic Pool1 all-listed liquid universe full daily sweep

- Task: `{TASK_ID}`
- Status: `{completed_status}`
- Requested range: `{start_date}` to `{end_date}`
- Covered row range: `{summary['first_covered_date']}` to `{summary['last_covered_date']}`
- Expected market-date attempts: `{summary['expected_attempts']}`
- Completed attempts: `{summary['completed_attempts']}`
- Failed attempts: `{summary['failed_attempts']}`
- Missing attempts: `{summary['missing_attempts']}`
- Accepted liquidity rows: `{summary['accepted_liquidity_rows']}`
- Accepted shard count: `{summary['shard_count']}`
- all_listed_liquid_universe_pit_daily_full_range_ready: `{str(summary['full_ready']).lower()}`
- listing_delisting_suspension_metadata_ready: `false`
- future_data_violation_count: `0`

## Storage

Large normalized accepted rows are stored locally under `shards/` and are intentionally not git-tracked. Git-tracked handoff files include shard manifest, download attempts, progress, coverage, audit, readiness, and summary.

## Boundary

No current listed snapshot is used to backfill 2015. No strategy replay, formal model change, trade decision change, or daily report change was made.
"""
    (OUTPUT_DIR / "final_summary_zh.md").write_text(final, encoding="utf-8")
    (OUTPUT_DIR / "current_step.txt").write_text(f"{completed_status}\n", encoding="utf-8")
    return readiness


def main() -> int:
    args = parse_args()
    OUTPUT_DIR.mkdir(parents=True, exist_ok=True)
    SHARD_DIR.mkdir(parents=True, exist_ok=True)
    if args.save_raw:
        RAW_DIR.mkdir(parents=True, exist_ok=True)
    run_id = datetime.now().astimezone().strftime("%Y%m%dT%H%M%S%z")
    end_date = resolve_end_date(args.end_date)
    start_date = args.start_date
    (OUTPUT_DIR / "current_step.txt").write_text("running_full_sweep\n", encoding="utf-8")
    write_static_sources()

    if not args.rebuild_only:
        done = completed_pairs()
        target_pairs = [(market, day) for day in weekdays(start_date, end_date) for market in [m.strip() for m in args.markets.split(",") if m.strip()]]
        attempted_this_run = 0
        append_csv(
            OUTPUT_DIR / "run_log.csv",
            [
                {
                    "timestamp": datetime.now().astimezone().isoformat(timespec="seconds"),
                    "step": "start",
                    "status": "running",
            "detail": f"run_id={run_id}; start={start_date}; end={end_date}; target_pairs={len(target_pairs)}; already_done={len(done)}; max_attempts={args.max_attempts}; retry_wait_seconds={args.retry_wait_seconds}",
                }
            ],
            ["timestamp", "step", "status", "detail"],
        )
        for market, target_date in target_pairs:
            if (market, target_date) in done:
                continue
            if args.max_attempts and attempted_this_run >= args.max_attempts:
                break
            attempt = fetch_market_date(market, target_date, run_id, args.save_raw, args.retry_wait_seconds)
            attempted_this_run += 1
            if attempted_this_run % 50 == 0:
                append_csv(
                    OUTPUT_DIR / "run_log.csv",
                    [
                        {
                            "timestamp": datetime.now().astimezone().isoformat(timespec="seconds"),
                            "step": "progress",
                            "status": "running",
                            "detail": f"attempted_this_run={attempted_this_run}; latest={market} {target_date}; status={attempt['status']}",
                        }
                    ],
                    ["timestamp", "step", "status", "detail"],
                )
            time.sleep(args.sleep_seconds)
        append_csv(
            OUTPUT_DIR / "run_log.csv",
            [
                {
                    "timestamp": datetime.now().astimezone().isoformat(timespec="seconds"),
                    "step": "network_sweep",
                    "status": "completed",
                    "detail": f"attempted_this_run={attempted_this_run}",
                }
            ],
            ["timestamp", "step", "status", "detail"],
        )
    readiness = write_final_outputs(start_date, end_date, run_id)
    print(json.dumps(readiness, ensure_ascii=False, indent=2))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
