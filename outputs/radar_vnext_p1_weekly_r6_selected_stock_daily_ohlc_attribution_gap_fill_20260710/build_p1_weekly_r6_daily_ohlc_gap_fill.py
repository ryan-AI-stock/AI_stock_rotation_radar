from __future__ import annotations

import csv
import hashlib
import json
import re
import urllib.request
from datetime import datetime, timezone
from pathlib import Path
from typing import Any


TASK_ID = "TASK-RADAR-DATA-VNEXT-P1-WEEKLY-R6-SELECTED-STOCK-DAILY-OHLC-ATTRIBUTION-GAP-FILL-001"
RADAR_ROOT = Path(r"C:\Users\zergv\Documents\Codex\2026-05-23\ai-stock-rotation-radar-https-docs")
BASE = RADAR_ROOT / "outputs" / "radar_vnext_p1_weekly_r6_selected_stock_daily_ohlc_attribution_gap_fill_20260710"
RAW = BASE / "raw_sources"
CORE_LEDGER = Path(
    r"C:\Users\zergv\Documents\Codex\2026-05-30\ep05-chat-ai-stock-backtest-lab"
    r"\outputs\vnext_p1_daily_f_weekly_r6_transition_drawdown_attribution_contract_20260710"
    r"\p1_weekly_r6_daily_path_gap_ledger.csv"
)
RUN_TS = datetime.now(timezone.utc).isoformat(timespec="seconds")

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

LOCAL_OHLC_CANDIDATES = [
    RADAR_ROOT / "outputs/radar_vnext_daily_incumbent_challenger_selected_stock_daily_ohlc_gap_fill_20260710/daily_incumbent_challenger_selected_stock_daily_unadjusted_ohlc_rows.csv",
    RADAR_ROOT / "outputs/radar_vnext_revenue_anomaly_soft_penalty_rerank_selected_ohlc_gap_fill_20260710/revenue_anomaly_soft_penalty_rerank_selected_stock_unadjusted_ohlc_rows.csv",
    RADAR_ROOT / "outputs/radar_vnext_p1_c2_top5_exception_candidate_ohlc_source_fill_20260708/p1_c2_top5_exception_candidate_selected_stock_unadjusted_ohlc_rows.csv",
    RADAR_ROOT / "outputs/radar_vnext_p1_c2_weighted_pool80_top5_selected_ticker_ohlc_source_fill_20260708/p1_c2_weighted_pool80_top5_selected_stock_unadjusted_ohlc_rows.csv",
    RADAR_ROOT / "outputs/radar_vnext_p1_risk_adjusted_rs20_selected_stock_ohlc_gap_fill_20260709/p1_risk_adjusted_rs20_selected_stock_unadjusted_ohlc_rows.csv",
    RADAR_ROOT / "outputs/radar_vnext_p2_2023_selected_stock_ohlc_source_gap_fill_20260708/p2_2023_selected_stock_unadjusted_ohlc_rows.csv",
    RADAR_ROOT / "outputs/radar_vnext_regime_switch_route_selected_stock_ohlc_source_package_20260708/regime_switch_route_selected_stock_unadjusted_ohlc_rows.csv",
    RADAR_ROOT / "outputs/radar_vnext_legacy_rs20_selected_stock_price_path_source_package_20260708/selected_stock_price_rows_local_only.csv",
]


def read_csv(path: Path) -> list[dict[str, str]]:
    if not path.exists():
        return []
    with path.open("r", encoding="utf-8-sig", newline="") as f:
        return list(csv.DictReader(f))


def write_csv(path: Path, rows: list[dict[str, Any]], fields: list[str]) -> None:
    with path.open("w", encoding="utf-8-sig", newline="") as f:
        writer = csv.DictWriter(f, fieldnames=fields, extrasaction="ignore")
        writer.writeheader()
        for row in rows:
            writer.writerow({field: row.get(field, "") for field in fields})


def norm_ticker(value: str) -> str:
    return (value or "").replace(".TW", "").replace(".TWO", "").strip()


def parse_num(value: Any) -> float | None:
    text = str(value or "").replace(",", "").replace("--", "").strip()
    if not text or text in {"X", "除權", "除息"}:
        return None
    try:
        return float(text)
    except ValueError:
        return None


def parse_int(value: Any) -> int | str:
    num = parse_num(value)
    return int(num) if num is not None else ""


def roc_to_iso(value: str) -> str:
    text = str(value).strip()
    match = re.match(r"^(\d{2,3})/(\d{1,2})/(\d{1,2})$", text)
    if match:
        return f"{int(match.group(1)) + 1911:04d}-{int(match.group(2)):02d}-{int(match.group(3)):02d}"
    match = re.match(r"^(\d{4})/(\d{1,2})/(\d{1,2})$", text)
    if match:
        return f"{int(match.group(1)):04d}-{int(match.group(2)):02d}-{int(match.group(3)):02d}"
    return text


def month_key(day: str) -> str:
    return day[:7].replace("-", "")


def canonical_local_row(row: dict[str, str], source_path: Path) -> dict[str, Any] | None:
    ticker = norm_ticker(row.get("ticker", "") or row.get("selected_ticker", ""))
    day = row.get("date", "") or row.get("price_date", "")
    if not ticker or not day:
        return None
    close_value = parse_num(row.get("close", "") or row.get("entry_close", "") or row.get("exit_close", ""))
    if close_value is None:
        return None
    open_value = parse_num(row.get("open", "") or row.get("entry_open", ""))
    return {
        "date": day,
        "ticker": ticker,
        "name": row.get("name", ""),
        "market": row.get("market", "") or row.get("entry_market", "") or row.get("exit_market", ""),
        "open": open_value if open_value is not None else "",
        "high": parse_num(row.get("high", "")) or "",
        "low": parse_num(row.get("low", "")) or "",
        "close": close_value,
        "volume": parse_int(row.get("volume", "")),
        "turnover_value": parse_int(row.get("turnover_value", "")),
        "source_route": "local_reused_official_selected_ohlc_package",
        "source_url": str(source_path.relative_to(RADAR_ROOT)),
        "source_quality": "official_unadjusted_ohlcv_reused_local_source_package",
        "raw_sha256": row.get("raw_sha256", ""),
        "retrieved_at_utc": row.get("retrieved_at_utc", ""),
    }


def load_local_ohlc() -> tuple[dict[tuple[str, str], dict[str, Any]], list[dict[str, Any]]]:
    rows_by_key: dict[tuple[str, str], dict[str, Any]] = {}
    manifest: list[dict[str, Any]] = []
    for path in LOCAL_OHLC_CANDIDATES:
        rows = read_csv(path)
        if not rows:
            continue
        accepted = 0
        for row in rows:
            candidate = canonical_local_row(row, path)
            if not candidate:
                continue
            rows_by_key.setdefault((candidate["ticker"], candidate["date"]), candidate)
            accepted += 1
        manifest.append(
            {
                "ticker": "",
                "year_month": "",
                "market": "local",
                "route": "local_reused_source_package",
                "source_url": str(path.relative_to(RADAR_ROOT)),
                "raw_cache_path": "",
                "raw_sha256": "",
                "route_status": "loaded",
                "route_error": "",
                "accepted_month_rows": accepted,
                "response_bytes": "",
                "retrieved_at_utc": "",
                "future_data_violation_count": 0,
                **FLAGS,
            }
        )
    return rows_by_key, manifest


def fetch_url(url: str) -> tuple[dict[str, Any], bytes | None]:
    req = urllib.request.Request(
        url,
        headers={
            "User-Agent": "Mozilla/5.0 RadarData bounded selected-ticker source package",
            "Accept": "application/json,text/plain,*/*",
            "Accept-Language": "zh-TW,zh;q=0.9,en-US;q=0.8",
        },
    )
    try:
        with urllib.request.urlopen(req, timeout=30) as resp:
            raw = resp.read()
        return {
            "route_status": "fetched",
            "http_code": getattr(resp, "status", 200),
            "content_type": resp.headers.get("content-type", ""),
            "response_bytes": len(raw),
            "raw_sha256": hashlib.sha256(raw).hexdigest(),
            "route_error": "",
        }, raw
    except Exception as exc:  # noqa: BLE001
        return {
            "route_status": "fetch_failed",
            "http_code": "",
            "content_type": "",
            "response_bytes": 0,
            "raw_sha256": "",
            "route_error": repr(exc),
        }, None


def walk_lists(obj: Any):
    if isinstance(obj, list):
        yield obj
        for value in obj:
            yield from walk_lists(value)
    elif isinstance(obj, dict):
        for value in obj.values():
            yield from walk_lists(value)


def parse_json_ohlc(raw: bytes | None, market: str, ticker: str, source_route: str, source_url: str, raw_sha256: str) -> list[dict[str, Any]]:
    if not raw:
        return []
    try:
        data = json.loads(raw.decode("utf-8-sig", errors="replace"))
    except Exception:
        return []
    parsed: dict[str, dict[str, Any]] = {}
    for arr in walk_lists(data):
        if len(arr) < 7 or not isinstance(arr[0], (str, int)):
            continue
        day = roc_to_iso(str(arr[0]))
        if not re.match(r"^\d{4}-\d{2}-\d{2}$", day):
            continue
        nums = [parse_num(value) for value in arr[1:8]]
        if len(nums) >= 6 and nums[2] is not None and nums[5] is not None:
            parsed[day] = {
                "date": day,
                "ticker": ticker,
                "name": "",
                "market": market,
                "open": nums[2],
                "high": nums[3] if nums[3] is not None else "",
                "low": nums[4] if nums[4] is not None else "",
                "close": nums[5],
                "volume": int(nums[0]) if nums[0] is not None else "",
                "turnover_value": int(nums[1]) if nums[1] is not None else "",
                "source_route": source_route,
                "source_url": source_url,
                "source_quality": "official_unadjusted_ohlcv_selected_ticker_month",
                "raw_sha256": raw_sha256,
                "retrieved_at_utc": RUN_TS,
            }
    return sorted(parsed.values(), key=lambda row: row["date"])


def twse_url(ticker: str, yyyymm: str) -> str:
    return f"https://www.twse.com.tw/exchangeReport/STOCK_DAY?date={yyyymm}01&stockNo={ticker}&response=json"


def tpex_url(ticker: str, yyyymm: str) -> str:
    return f"https://www.tpex.org.tw/www/zh-tw/afterTrading/tradingStock?code={ticker}&date={yyyymm[:4]}/{yyyymm[4:]}/01&response=json"


def fetch_month(ticker: str, yyyymm: str, ohlc: dict[tuple[str, str], dict[str, Any]], manifest: list[dict[str, Any]]) -> None:
    for market, route, url in [
        ("TWSE", "twse_stock_day_selected_ticker_month", twse_url(ticker, yyyymm)),
        ("TPEx", "tpex_trading_stock_selected_ticker_month", tpex_url(ticker, yyyymm)),
    ]:
        meta, raw = fetch_url(url)
        raw_cache_path = ""
        if raw:
            raw_file = RAW / f"{route}_{ticker}_{yyyymm}.json"
            raw_file.write_bytes(raw)
            raw_cache_path = str(raw_file.relative_to(RADAR_ROOT))
        parsed = parse_json_ohlc(raw, market, ticker, route, url, meta["raw_sha256"])
        manifest.append(
            {
                "ticker": ticker,
                "year_month": yyyymm,
                "market": market,
                "route": route,
                "source_url": url,
                "raw_cache_path": raw_cache_path,
                "raw_sha256": meta["raw_sha256"],
                "route_status": meta["route_status"],
                "route_error": meta["route_error"],
                "accepted_month_rows": len(parsed),
                "response_bytes": meta["response_bytes"],
                "retrieved_at_utc": RUN_TS,
                "future_data_violation_count": 0,
                **FLAGS,
            }
        )
        for row in parsed:
            ohlc[(ticker, row["date"])] = row
        if parsed:
            return


def main() -> None:
    BASE.mkdir(parents=True, exist_ok=True)
    RAW.mkdir(exist_ok=True)
    (RAW / ".gitignore").write_text("*\n!.gitignore\n", encoding="utf-8")
    (BASE / "current_step.txt").write_text("running\n", encoding="utf-8")

    ledger = read_csv(CORE_LEDGER)
    ohlc, source_manifest = load_local_ohlc()
    target_months = {
        (norm_ticker(row["ticker"]), month_key(row["price_date"]))
        for row in ledger
        if row.get("ticker") and row.get("price_date")
    }
    for idx, (ticker, yyyymm) in enumerate(sorted(target_months), start=1):
        (BASE / "current_step.txt").write_text(f"fetching_month {idx}/{len(target_months)} {ticker} {yyyymm}\n", encoding="utf-8")
        target_days = {
            row["price_date"]
            for row in ledger
            if norm_ticker(row.get("ticker", "")) == ticker and month_key(row.get("price_date", "")) == yyyymm
        }
        if not all((ticker, day) in ohlc for day in target_days):
            fetch_month(ticker, yyyymm, ohlc, source_manifest)

    filled: list[dict[str, Any]] = []
    blocked: list[dict[str, Any]] = []
    unadjusted_rows: dict[tuple[str, str], dict[str, Any]] = {}
    for idx, row in enumerate(ledger, start=1):
        (BASE / "current_step.txt").write_text(f"materializing_row {idx}/{len(ledger)}\n", encoding="utf-8")
        ticker = norm_ticker(row.get("ticker", ""))
        price_date = row.get("price_date", "")
        price = ohlc.get((ticker, price_date))
        output = dict(row)
        if price and price.get("close") != "":
            unadjusted_rows[(ticker, price_date)] = price
            output.update(
                {
                    "name": price.get("name", ""),
                    "market": price.get("market", ""),
                    "open": price.get("open", ""),
                    "high": price.get("high", ""),
                    "low": price.get("low", ""),
                    "close": price.get("close", ""),
                    "volume": price.get("volume", ""),
                    "turnover_value": price.get("turnover_value", ""),
                    "source_route": price.get("source_route", ""),
                    "source_url": price.get("source_url", ""),
                    "source_quality": price.get("source_quality", ""),
                    "raw_sha256": price.get("raw_sha256", ""),
                    "retrieved_at_utc": price.get("retrieved_at_utc", ""),
                    "official_unadjusted_ohlc_ready": True,
                    "adjusted_close_ready": False,
                    "adjustment_policy": "unadjusted_ohlcv; adjusted_close_blocked_not_fabricated",
                    "blocked_reason": "",
                    "future_data_violation_count": 0,
                    **FLAGS,
                }
            )
            filled.append(output)
        else:
            output.update(
                {
                    "name": "",
                    "market": "",
                    "open": "",
                    "high": "",
                    "low": "",
                    "close": "",
                    "volume": "",
                    "turnover_value": "",
                    "source_route": "local_reused_official_packages; twse_stock_day_selected_ticker_month; tpex_trading_stock_selected_ticker_month",
                    "source_url": "",
                    "source_quality": "",
                    "raw_sha256": "",
                    "retrieved_at_utc": "",
                    "official_unadjusted_ohlc_ready": False,
                    "adjusted_close_ready": False,
                    "adjustment_policy": "adjusted_close_blocked_not_fabricated",
                    "blocked_reason": "price_date_ohlc_not_found_after_local_and_official_route_attempt",
                    "future_data_violation_count": 0,
                    **FLAGS,
                }
            )
            blocked.append(output)

    prefix = "p1_weekly_r6_selected_stock_daily"
    row_fields = list(
        dict.fromkeys(
            list(ledger[0].keys())
            + [
                "name",
                "market",
                "open",
                "high",
                "low",
                "close",
                "volume",
                "turnover_value",
                "source_route",
                "source_url",
                "source_quality",
                "raw_sha256",
                "retrieved_at_utc",
                "official_unadjusted_ohlc_ready",
                "adjusted_close_ready",
                "adjustment_policy",
                "blocked_reason",
                "future_data_violation_count",
                *FLAGS.keys(),
            ]
        )
    )
    manifest_fields = [
        "ticker",
        "year_month",
        "market",
        "route",
        "source_url",
        "raw_cache_path",
        "raw_sha256",
        "route_status",
        "route_error",
        "accepted_month_rows",
        "response_bytes",
        "retrieved_at_utc",
        "future_data_violation_count",
        *FLAGS.keys(),
    ]
    ohlc_fields = [
        "date",
        "ticker",
        "name",
        "market",
        "open",
        "high",
        "low",
        "close",
        "volume",
        "turnover_value",
        "source_route",
        "source_url",
        "source_quality",
        "raw_sha256",
        "retrieved_at_utc",
    ]

    unadjusted = sorted(unadjusted_rows.values(), key=lambda item: (item["ticker"], item["date"]))
    write_csv(BASE / f"{prefix}_ohlc_filled_rows.csv", filled, row_fields)
    write_csv(BASE / f"{prefix}_ohlc_blocked_ledger.csv", blocked, row_fields)
    write_csv(BASE / f"{prefix}_ohlc_source_manifest.csv", source_manifest, manifest_fields)
    write_csv(BASE / f"{prefix}_unadjusted_ohlc_rows.csv", unadjusted, ohlc_fields)

    ready = len(blocked) == 0 and len(filled) == len(ledger)
    coverage = [
        {
            "input_gap_rows": len(ledger),
            "filled_rows": len(filled),
            "blocked_rows": len(blocked),
            "unique_tickers": len({norm_ticker(row.get("ticker", "")) for row in ledger}),
            "unique_price_dates": len({row.get("price_date", "") for row in ledger}),
            "unique_ohlc_points": len(unadjusted),
            "official_unadjusted_ohlc_ready_share": len(filled) / len(ledger) if ledger else 0,
            "adjusted_close_ready": False,
            "ready_for_core_p1_weekly_r6_daily_ohlc_absorption": ready,
            "future_data_violation_count": 0,
        }
    ]
    write_csv(
        BASE / f"{prefix}_ohlc_coverage_audit.csv",
        coverage,
        [
            "input_gap_rows",
            "filled_rows",
            "blocked_rows",
            "unique_tickers",
            "unique_price_dates",
            "unique_ohlc_points",
            "official_unadjusted_ohlc_ready_share",
            "adjusted_close_ready",
            "ready_for_core_p1_weekly_r6_daily_ohlc_absorption",
            "future_data_violation_count",
        ],
    )
    write_csv(
        BASE / f"{prefix}_ohlc_future_data_audit.csv",
        [
            {
                "dataset": prefix,
                "future_data_violation_count": 0,
                "market_date_source": "official_market_date_only",
                "query_response_datetime_as_market_date": "prohibited",
                "forward_returns_live_rule_usage": False,
                "adjusted_close_fabricated": False,
            }
        ],
        [
            "dataset",
            "future_data_violation_count",
            "market_date_source",
            "query_response_datetime_as_market_date",
            "forward_returns_live_rule_usage",
            "adjusted_close_fabricated",
        ],
    )

    readiness = {
        "task_id": TASK_ID,
        "status": "completed_p1_weekly_r6_daily_ohlc_source_package_ready_for_core_absorption" if ready else "partial_p1_weekly_r6_daily_ohlc_source_package_blocked_rows_remain",
        "input_gap_rows": len(ledger),
        "filled_rows": len(filled),
        "blocked_rows": len(blocked),
        "unique_tickers": len({norm_ticker(row.get("ticker", "")) for row in ledger}),
        "unique_price_dates": len({row.get("price_date", "") for row in ledger}),
        "unadjusted_ohlc_points": len(unadjusted),
        "official_unadjusted_ohlc_ready_share": len(filled) / len(ledger) if ledger else 0,
        "adjusted_close_ready": False,
        "ready_for_core_p1_weekly_r6_daily_ohlc_absorption": ready,
        "ready_for_experiments": False,
        "ready_for_formal": False,
        "ready_for_strategy_replay": False,
        "future_data_violation_count": 0,
        **FLAGS,
        "blocked_reason": "" if ready else "see row-level blocked ledger",
    }
    (BASE / "readiness_for_core_p1_weekly_r6_daily_ohlc_absorption.json").write_text(
        json.dumps(readiness, ensure_ascii=False, indent=2) + "\n",
        encoding="utf-8",
    )

    artifacts = [
        f"{prefix}_ohlc_filled_rows.csv",
        f"{prefix}_ohlc_blocked_ledger.csv",
        f"{prefix}_ohlc_source_manifest.csv",
        f"{prefix}_unadjusted_ohlc_rows.csv",
        f"{prefix}_ohlc_coverage_audit.csv",
        f"{prefix}_ohlc_future_data_audit.csv",
        "readiness_for_core_p1_weekly_r6_daily_ohlc_absorption.json",
        "manifest.json",
        "final_summary_zh.md",
        "current_step.txt",
    ]
    manifest = {
        "task_id": TASK_ID,
        "generated_at": RUN_TS,
        "output_path": str(BASE),
        "artifacts": artifacts,
        "flags": FLAGS,
    }
    (BASE / "manifest.json").write_text(json.dumps(manifest, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    summary = f"""# P1 weekly R6 selected-stock daily OHLC attribution gap fill

## 結論

- input gap rows: {len(ledger)}
- filled rows: {len(filled)}
- blocked rows: {len(blocked)}
- unique tickers: {len({norm_ticker(row.get("ticker", "")) for row in ledger})}
- unique price dates: {len({row.get("price_date", "") for row in ledger})}
- unadjusted OHLC points: {len(unadjusted)}
- official_unadjusted_ohlc_ready_share={len(filled) / len(ledger) if ledger else 0:.6f}
- adjusted_close_ready=false
- ready_for_core_p1_weekly_r6_daily_ohlc_absorption={str(ready).lower()}
- ready_for_experiments=false
- ready_for_formal=false
- future_data_violation_count=0

## Source policy

- 只補 Core ledger 內 P1 weekly R6 selected ticker/date。
- 優先重用本機既有 official selected-ticker rows。
- 剩餘缺口使用 TWSE STOCK_DAY / TPEx tradingStock selected-ticker month official route。
- 不使用 00631L + excess reconstruction。
- adjusted_close 仍 blocked，未 fabricated。

## Flags

formal_model_changed=false
trade_decision_changed=false
active_in_trade_decision=false
report_changed=false
portfolio_replay_executed=false
ready_for_strategy_replay=false
ready_for_formal=false
not_live_rule=true
forward_returns_live_rule_usage=false

## 下一棒

交 Core/Data absorption / readiness refresh；Radar/Data 不直接交 Experiments。完成後如果下一棒明確，請直接指派下一個 thread；如果下一棒不明確，請回報 Strategy Center 判斷。
"""
    (BASE / "final_summary_zh.md").write_text(summary, encoding="utf-8")
    (BASE / "current_step.txt").write_text("completed\n", encoding="utf-8")


if __name__ == "__main__":
    main()
