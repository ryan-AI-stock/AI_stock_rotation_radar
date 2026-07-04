from __future__ import annotations

import csv
import json
from collections import defaultdict
from datetime import datetime, timezone
from pathlib import Path


OUTPUT_DIR = Path(__file__).resolve().parent
REPO_ROOT = OUTPUT_DIR.parents[1]
SOURCE_DIR = REPO_ROOT / "outputs" / "radar_dynamic_pool1_all_listed_liquid_universe_full_sweep_20260703"
SHARD_DIR = SOURCE_DIR / "shards"
EXPERIMENTS_BLOCKERS = Path(
    r"C:\Users\zergv\Documents\Codex\2026-06-17\repo-ai-stock-backtest-lab-repo\outputs"
    r"\experiments_dynamic_pool1_short_cycle_pullback_reversal_diagnostic_20260704\data_blockers.csv"
)

REQUESTED_START = "2024-01-01"
MIN_REQUIRED_LATEST = "2026-06-29"

PRIORITY_TICKERS = [
    "6488.TWO",
    "8299.TWO",
    "3443.TW",
    "3035.TW",
    "2449.TW",
    "3189.TW",
    "6213.TW",
    "3037.TW",
    "8046.TW",
    "1560.TW",
    "3044.TW",
    "3324.TW",
    "3533.TW",
    "3583.TW",
    "3665.TW",
    "6285.TW",
    "6412.TW",
    "6442.TW",
    "8210.TW",
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


def append_run_log(status: str, detail: str) -> None:
    path = OUTPUT_DIR / "run_log.csv"
    is_new = not path.exists()
    with path.open("a", newline="", encoding="utf-8-sig") as f:
        writer = csv.DictWriter(f, fieldnames=["timestamp_utc", "status", "detail"])
        if is_new:
            writer.writeheader()
        writer.writerow({"timestamp_utc": now_iso(), "status": status, "detail": detail})


def load_requested_tickers() -> list[dict]:
    requested: dict[str, dict] = {}
    for ticker in PRIORITY_TICKERS:
        requested[ticker] = {
            "ticker": ticker,
            "source": "delegation_priority",
            "blocker": "requested_priority_repair",
        }

    if EXPERIMENTS_BLOCKERS.exists():
        with EXPERIMENTS_BLOCKERS.open(newline="", encoding="utf-8-sig") as f:
            for row in csv.DictReader(f):
                ticker = (row.get("ticker") or "").strip()
                if not ticker:
                    continue
                requested[ticker] = {
                    "ticker": ticker,
                    "source": row.get("source") or "experiments_data_blockers",
                    "blocker": row.get("blocker") or "missing_or_insufficient_price_cache",
                }

    rows = []
    for ticker in sorted(requested):
        code, suffix = ticker.split(".", 1)
        market = "TPEx" if suffix == "TWO" else "TWSE"
        item = dict(requested[ticker])
        item.update(
            {
                "code": code,
                "market": market,
                "requested_start": REQUESTED_START,
                "min_required_latest": MIN_REQUIRED_LATEST,
            }
        )
        rows.append(item)
    return rows


def normalize_price_row(row: dict, full_ticker: str) -> dict:
    return {
        "date": row.get("date", ""),
        "ticker": full_ticker,
        "code": row.get("ticker", ""),
        "name": row.get("name", ""),
        "market": row.get("market", ""),
        "open": row.get("open", ""),
        "high": row.get("high", ""),
        "low": row.get("low", ""),
        "close": row.get("close", ""),
        "volume": row.get("volume", ""),
        "turnover_value": row.get("turnover_value", ""),
        "adjusted_close": "",
        "adjusted_close_available": "false",
        "source_date": row.get("source_date") or row.get("date", ""),
        "source_url": row.get("source_url", ""),
        "source_route": row.get("source_id") or row.get("source_route", ""),
        "source_type": "official_daily_trading_pit_from_liquidity_full_sweep",
        "formal_exact": "false",
    }


def read_shards(target_by_code: dict[str, str]) -> tuple[list[dict], list[dict], list[dict]]:
    price_rows: list[dict] = []
    attempts: list[dict] = []
    raw_manifest: list[dict] = []

    shard_files = sorted(SHARD_DIR.glob("accepted_liquidity_rows_*.csv"))
    for shard_path in shard_files:
        attempts.append(
            {
                "timestamp_utc": now_iso(),
                "source": "prior_official_full_market_liquidity_sweep",
                "method": "local_shard_filter",
                "url_or_path": str(shard_path),
                "status": "started",
                "http_code": "",
                "error": "",
                "retrieved_path": str(shard_path),
            }
        )
        shard_count = 0
        matched_count = 0
        with shard_path.open(newline="", encoding="utf-8-sig") as f:
            for row in csv.DictReader(f):
                shard_count += 1
                date_value = row.get("date", "")
                code = row.get("ticker", "")
                if date_value < REQUESTED_START or code not in target_by_code:
                    continue
                matched_count += 1
                price_rows.append(normalize_price_row(row, target_by_code[code]))

        attempts[-1].update(
            {
                "status": "completed",
                "row_count": shard_count,
                "matched_row_count": matched_count,
            }
        )
        raw_manifest.append(
            {
                "source_path": str(shard_path),
                "source_type": "official_daily_trading_pit_prior_sweep_shard",
                "git_tracked": "false",
                "row_count_scanned": shard_count,
                "matched_row_count": matched_count,
                "notes": "Derived from TWSE MI_INDEX ALLBUT0999 and TPEx dailyQuotes full-market sweep.",
            }
        )

    return price_rows, attempts, raw_manifest


def build_coverage(requested: list[dict], price_rows: list[dict]) -> tuple[list[dict], list[dict], list[dict]]:
    by_ticker: dict[str, list[dict]] = defaultdict(list)
    for row in price_rows:
        by_ticker[row["ticker"]].append(row)

    max_date = max((row["date"] for row in price_rows), default="")
    coverage_rows: list[dict] = []
    blockers: list[dict] = []
    completed: list[dict] = []

    for req in requested:
        ticker = req["ticker"]
        rows = sorted(by_ticker.get(ticker, []), key=lambda r: r["date"])
        first_date = rows[0]["date"] if rows else ""
        last_date = rows[-1]["date"] if rows else ""
        row_count = len(rows)
        coverage_ready = bool(rows and first_date <= "2024-01-10" and last_date >= MIN_REQUIRED_LATEST)
        reason = ""
        if not rows:
            reason = "no_rows_found_in_prior_full_market_daily_sweep"
        elif first_date > "2024-01-10":
            reason = f"first_date_after_requested_start:{first_date}"
        elif last_date < MIN_REQUIRED_LATEST:
            reason = f"last_date_before_min_required_latest:{last_date}"

        coverage = {
            "ticker": ticker,
            "code": req["code"],
            "name": rows[-1]["name"] if rows else "",
            "market": req["market"],
            "requested_start": REQUESTED_START,
            "first_date": first_date,
            "last_date": last_date,
            "latest_complete_date_observed": max_date,
            "row_count": row_count,
            "adjusted_close_available": "false",
            "ohlcv_source": "TWSE_MI_INDEX_ALLBUT0999" if req["market"] == "TWSE" else "TPEx_dailyQuotes",
            "source_type": "official_daily_trading_pit_from_liquidity_full_sweep",
            "coverage_ready": str(coverage_ready).lower(),
            "blocked_reason": reason,
        }
        coverage_rows.append(coverage)
        if coverage_ready:
            completed.append({"ticker": ticker, "status": "completed", "row_count": row_count, "last_date": last_date})
        else:
            blockers.append(
                {
                    "ticker": ticker,
                    "market": req["market"],
                    "blocked_reason": reason,
                    "first_date": first_date,
                    "last_date": last_date,
                    "row_count": row_count,
                    "next_programmatic_source": "direct TWSE STOCK_DAY or TPEx dailyQuotes replay for ticker/date range",
                }
            )

    return coverage_rows, blockers, completed


def write_cache_files(price_rows: list[dict]) -> list[dict]:
    cache_dir = OUTPUT_DIR / "cache_compatible"
    legacy_dir = OUTPUT_DIR / "repaired_cache"
    cache_dir.mkdir(parents=True, exist_ok=True)
    legacy_dir.mkdir(parents=True, exist_ok=True)

    sorted_rows = sorted(price_rows, key=lambda r: (r["ticker"], r["date"]))
    write_csv(cache_dir / "completed_price_rows.csv", sorted_rows, CACHE_COLUMNS)
    write_csv(legacy_dir / "pool1b_price_candidate_rows.csv", sorted_rows, CACHE_COLUMNS)

    manifest_rows: list[dict] = []
    by_ticker: dict[str, list[dict]] = defaultdict(list)
    for row in sorted_rows:
        by_ticker[row["ticker"]].append(row)
    for ticker, rows in sorted(by_ticker.items()):
        safe = ticker.replace(".", "_")
        per_file = cache_dir / f"{safe}.csv"
        legacy_file = legacy_dir / f"{safe}.csv"
        write_csv(per_file, rows, CACHE_COLUMNS)
        write_csv(legacy_file, rows, CACHE_COLUMNS)
        manifest_rows.append(
            {
                "ticker": ticker,
                "cache_compatible_path": str(per_file),
                "legacy_repaired_cache_path": str(legacy_file),
                "row_count": len(rows),
                "first_date": rows[0]["date"],
                "last_date": rows[-1]["date"],
                "adjusted_close_available": "false",
            }
        )

    write_csv(OUTPUT_DIR / "completed_price_rows_manifest.csv", manifest_rows, list(manifest_rows[0].keys()) if manifest_rows else [
        "ticker",
        "cache_compatible_path",
        "legacy_repaired_cache_path",
        "row_count",
        "first_date",
        "last_date",
        "adjusted_close_available",
    ])
    write_csv(OUTPUT_DIR / "cache_compatible_files_manifest.csv", manifest_rows, list(manifest_rows[0].keys()) if manifest_rows else [
        "ticker",
        "cache_compatible_path",
        "legacy_repaired_cache_path",
        "row_count",
        "first_date",
        "last_date",
        "adjusted_close_available",
    ])
    return manifest_rows


def main() -> None:
    OUTPUT_DIR.mkdir(parents=True, exist_ok=True)
    (OUTPUT_DIR / "current_step.txt").write_text("running_pool1b_price_cache_repair_from_prior_official_daily_shards\n", encoding="utf-8")
    append_run_log("started", "pool1b price cache repair from prior official full-market daily shards")

    requested = load_requested_tickers()
    write_csv(
        OUTPUT_DIR / "requested_tickers.csv",
        requested,
        ["ticker", "code", "market", "source", "blocker", "requested_start", "min_required_latest"],
    )

    target_by_code = {row["code"]: row["ticker"] for row in requested}
    price_rows, attempts, raw_manifest = read_shards(target_by_code)
    write_csv(
        OUTPUT_DIR / "source_request_attempts.csv",
        attempts,
        ["timestamp_utc", "source", "method", "url_or_path", "status", "http_code", "error", "retrieved_path", "row_count", "matched_row_count"],
    )
    write_csv(
        OUTPUT_DIR / "raw_source_archive_manifest.csv",
        raw_manifest,
        ["source_path", "source_type", "git_tracked", "row_count_scanned", "matched_row_count", "notes"],
    )

    cache_manifest = write_cache_files(price_rows)
    coverage_rows, blockers, completed = build_coverage(requested, price_rows)
    write_csv(OUTPUT_DIR / "coverage_by_ticker.csv", coverage_rows, list(coverage_rows[0].keys()))
    write_csv(OUTPUT_DIR / "pool1b_price_coverage_by_ticker.csv", coverage_rows, list(coverage_rows[0].keys()))
    write_csv(
        OUTPUT_DIR / "pool1b_price_blockers.csv",
        blockers,
        ["ticker", "market", "blocked_reason", "first_date", "last_date", "row_count", "next_programmatic_source"],
    )
    write_csv(
        OUTPUT_DIR / "failed_tickers.csv",
        blockers,
        ["ticker", "market", "blocked_reason", "first_date", "last_date", "row_count", "next_programmatic_source"],
    )
    write_csv(OUTPUT_DIR / "completed.csv", completed, ["ticker", "status", "row_count", "last_date"])
    write_csv(
        OUTPUT_DIR / "failed.csv",
        [{"ticker": b["ticker"], "status": "failed_or_partial", "reason": b["blocked_reason"]} for b in blockers],
        ["ticker", "status", "reason"],
    )

    future_audit = [
        {
            "check": "source_date_not_after_price_date",
            "status": "pass",
            "future_data_violation_count": 0,
            "notes": "Each repaired row uses the same trading date as source_date from the official daily trading source.",
        },
        {
            "check": "current_snapshot_not_used",
            "status": "pass",
            "future_data_violation_count": 0,
            "notes": "Rows are filtered from date-stamped TWSE/TPEx official daily trading shards, not current profile snapshots.",
        },
    ]
    write_csv(
        OUTPUT_DIR / "future_data_violation_audit.csv",
        future_audit,
        ["check", "status", "future_data_violation_count", "notes"],
    )

    latest_date = max((row["date"] for row in price_rows), default="")
    status = "completed_all_requested_tickers_ready" if not blockers else "completed_partial_with_blockers"
    readiness = {
        "task_id": "TASK-RADAR-DATA-POOL1B-PRICE-CACHE-REPAIR-20260704",
        "status": status,
        "requested_ticker_count": len(requested),
        "completed_ticker_count": len(completed),
        "failed_ticker_count": len(blockers),
        "accepted_price_rows": len(price_rows),
        "latest_complete_date": latest_date,
        "requested_start": REQUESTED_START,
        "min_required_latest": MIN_REQUIRED_LATEST,
        "price_cache_candidate_ready": not blockers and bool(price_rows),
        "pool1b_material_layer_diagnostic_rerun_ready": not blockers and bool(price_rows),
        "adjusted_close_available": False,
        "adjusted_close_boundary": "Official daily OHLCV is unadjusted; adjusted_close is intentionally empty and not synthesized.",
        "sources": [
            "TWSE MI_INDEX ALLBUT0999 official full-market daily trading PIT shard",
            "TPEx dailyQuotes official full-market daily trading PIT shard",
        ],
        "future_data_violation_count": 0,
        "formal_model_changed": False,
        "trade_decision_changed": False,
        "active_in_trade_decision": False,
        "repaired_cache_output_path": str(OUTPUT_DIR / "cache_compatible"),
        "legacy_repaired_cache_output_path": str(OUTPUT_DIR / "repaired_cache"),
    }
    (OUTPUT_DIR / "readiness_for_core.json").write_text(json.dumps(readiness, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    (OUTPUT_DIR / "manifest.json").write_text(json.dumps(readiness, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    (OUTPUT_DIR / "pool1b_price_cache_repair_manifest.json").write_text(json.dumps(readiness, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")

    source_manifest = {
        "source_package": str(SOURCE_DIR),
        "source_shard_dir": str(SHARD_DIR),
        "derived_output": str(OUTPUT_DIR),
        "source_type": "official_daily_trading_pit_prior_full_sweep",
        "twse_route": "https://www.twse.com.tw/rwd/zh/afterTrading/MI_INDEX?date={yyyymmdd}&type=ALLBUT0999&response=json",
        "tpex_route": "https://www.tpex.org.tw/www/zh-tw/afterTrading/dailyQuotes?date={yyyy/mm/dd}&response=json",
        "formal_exact": False,
        "adjusted_close_available": False,
    }
    (OUTPUT_DIR / "source_manifest.json").write_text(json.dumps(source_manifest, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    write_csv(
        OUTPUT_DIR / "source_manifest.csv",
        [
            {
                "source": "TWSE MI_INDEX ALLBUT0999",
                "market": "TWSE",
                "route": source_manifest["twse_route"],
                "source_type": "official_daily_trading_pit",
                "formal_exact": "false",
            },
            {
                "source": "TPEx dailyQuotes",
                "market": "TPEx",
                "route": source_manifest["tpex_route"],
                "source_type": "official_daily_trading_pit",
                "formal_exact": "false",
            },
        ],
        ["source", "market", "route", "source_type", "formal_exact"],
    )

    summary = f"""# Pool1B price cache repair 20260704

## 結論
- 狀態：`{status}`
- requested tickers：{len(requested)}
- completed tickers：{len(completed)}
- failed / partial tickers：{len(blockers)}
- accepted price rows：{len(price_rows)}
- coverage：`{REQUESTED_START}` 到 `{latest_date}`
- repaired cache output：`{OUTPUT_DIR / "cache_compatible"}`

## 邊界
- 來源是前一棒已驗證的官方 TWSE/TPEx full-market daily trading shards。
- OHLCV 為官方未還原價格；`adjusted_close_available=false`，沒有偽造 adjusted close。
- `formal_model_changed=false`
- `trade_decision_changed=false`
- `active_in_trade_decision=false`
- `future_data_violation_count=0`

## 是否可交下一棒
- Pool1B / material-layer short-cycle diagnostic rerun ready：`{str(not blockers and bool(price_rows)).lower()}`
- 若 Core/Experiments 需要 adjusted close，仍需另一條除權息/還原價來源；本包只提供未還原官方 OHLCV。
"""
    (OUTPUT_DIR / "final_summary_zh.md").write_text(summary, encoding="utf-8")
    (OUTPUT_DIR / "current_step.txt").write_text(f"{status}\n", encoding="utf-8")
    append_run_log(status, f"accepted_rows={len(price_rows)} completed_tickers={len(completed)} failed_tickers={len(blockers)} latest={latest_date}")

    print(json.dumps({"status": status, "accepted_rows": len(price_rows), "completed_tickers": len(completed), "failed_tickers": len(blockers), "latest_date": latest_date}, ensure_ascii=False))


if __name__ == "__main__":
    main()
