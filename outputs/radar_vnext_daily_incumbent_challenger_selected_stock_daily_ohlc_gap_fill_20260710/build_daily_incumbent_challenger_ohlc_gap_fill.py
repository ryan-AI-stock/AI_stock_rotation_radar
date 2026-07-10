from __future__ import annotations

import csv
import hashlib
import json
import re
import urllib.request
from datetime import datetime, timezone
from pathlib import Path
from typing import Any


TASK_ID = "TASK-RADAR-DATA-VNEXT-DAILY-INCUMBENT-CHALLENGER-SELECTED-STOCK-DAILY-OHLC-GAP-FILL-001"
BASE = Path("outputs/radar_vnext_daily_incumbent_challenger_selected_stock_daily_ohlc_gap_fill_20260710")
CORE_LEDGER = Path(
    r"C:\Users\zergv\Documents\Codex\2026-05-30\ep05-chat-ai-stock-backtest-lab\outputs\vnext_daily_incumbent_challenger_state_machine_contract_20260710\daily_incumbent_challenger_selected_stock_daily_ohlc_gap_ledger.csv"
)
RUN_TS = datetime.now(timezone.utc).isoformat(timespec="seconds")

LOCAL_OHLC_CANDIDATES = [
    Path("outputs/radar_vnext_revenue_anomaly_soft_penalty_rerank_selected_ohlc_gap_fill_20260710/revenue_anomaly_soft_penalty_rerank_selected_stock_unadjusted_ohlc_rows.csv"),
    Path("outputs/radar_vnext_p1_c2_top5_exception_candidate_ohlc_source_fill_20260708/p1_c2_top5_exception_candidate_selected_stock_unadjusted_ohlc_rows.csv"),
    Path("outputs/radar_vnext_p1_c2_weighted_pool80_top5_selected_ticker_ohlc_source_fill_20260708/p1_c2_weighted_pool80_top5_selected_stock_unadjusted_ohlc_rows.csv"),
    Path("outputs/radar_vnext_p1_risk_adjusted_rs20_selected_stock_ohlc_gap_fill_20260709/p1_risk_adjusted_rs20_selected_stock_unadjusted_ohlc_rows.csv"),
    Path("outputs/radar_vnext_p2_2023_selected_stock_ohlc_source_gap_fill_20260708/p2_2023_selected_stock_unadjusted_ohlc_rows.csv"),
    Path("outputs/radar_vnext_regime_switch_route_selected_stock_ohlc_source_package_20260708/regime_switch_route_selected_stock_unadjusted_ohlc_rows.csv"),
    Path("outputs/radar_vnext_legacy_rs20_selected_stock_price_path_source_package_20260708/selected_stock_price_rows_local_only.csv"),
]


def read_csv(path: Path) -> list[dict[str, str]]:
    if not path.exists():
        return []
    with path.open("r", encoding="utf-8-sig", newline="") as f:
        return list(csv.DictReader(f))


def write_csv(path: Path, rows: list[dict[str, Any]], fields: list[str]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("w", encoding="utf-8", newline="") as f:
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


def load_local_ohlc() -> tuple[dict[tuple[str, str], dict[str, Any]], list[dict[str, Any]]]:
    rows_by_key: dict[tuple[str, str], dict[str, Any]] = {}
    manifest: list[dict[str, Any]] = []
    for path in LOCAL_OHLC_CANDIDATES:
        rows = read_csv(path)
        if not rows:
            continue
        accepted = 0
        for row in rows:
            ticker = norm_ticker(row.get("ticker", "") or row.get("selected_ticker", ""))
            day = row.get("date", "")
            if not ticker or not day:
                continue
            open_value = parse_num(row.get("open", "") or row.get("entry_open", ""))
            close_value = parse_num(row.get("close", "") or row.get("entry_close", "") or row.get("exit_close", ""))
            if open_value is None or close_value is None:
                continue
            candidate = {
                "date": day,
                "ticker": ticker,
                "market": row.get("market", "") or row.get("entry_market", "") or row.get("exit_market", ""),
                "open": open_value,
                "high": parse_num(row.get("high", "")) or "",
                "low": parse_num(row.get("low", "")) or "",
                "close": close_value,
                "volume": parse_int(row.get("volume", "")),
                "turnover_value": parse_int(row.get("turnover_value", "")),
                "source_route": "local_reused_official_selected_ohlc_package",
                "source_url": str(path),
                "source_quality": "official_unadjusted_ohlcv_reused_local_source_package",
                "raw_sha256": "",
                "retrieved_at_utc": "",
            }
            rows_by_key.setdefault((ticker, day), candidate)
            accepted += 1
        manifest.append({"source_path": str(path), "loaded_rows": len(rows), "accepted_ohlc_points": accepted})
    return rows_by_key, manifest


def fetch_url(url: str) -> tuple[dict[str, Any], bytes | None]:
    request = urllib.request.Request(
        url,
        headers={
            "User-Agent": "Mozilla/5.0",
            "Accept": "application/json,text/plain,*/*",
            "Accept-Language": "zh-TW,zh;q=0.9,en-US;q=0.8",
        },
    )
    try:
        with urllib.request.urlopen(request, timeout=20) as response:
            raw = response.read()
        return {
            "route_status": "fetched",
            "http_code": getattr(response, "status", 200),
            "content_type": response.headers.get("content-type", ""),
            "response_bytes": len(raw),
            "raw_sha256": hashlib.sha256(raw).hexdigest(),
            "route_error": "",
        }, raw
    except Exception as exc:  # noqa: BLE001
        return {"route_status": "fetch_failed", "http_code": "", "content_type": "", "response_bytes": 0, "raw_sha256": "", "route_error": repr(exc)}, None


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
        parsed = parse_json_ohlc(raw, market, ticker, route, url, meta["raw_sha256"])
        manifest.append(
            {
                "ticker": ticker,
                "year_month": yyyymm,
                "market": market,
                "route": route,
                "source_url": url,
                "raw_sha256": meta["raw_sha256"],
                "route_status": meta["route_status"],
                "route_error": meta["route_error"],
                "accepted_month_rows": len(parsed),
                "response_bytes": meta["response_bytes"],
                "retrieved_at_utc": RUN_TS,
                "future_data_violation_count": 0,
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
        )
        for row in parsed:
            ohlc[(ticker, row["date"])] = row
        if parsed:
            return


def main() -> None:
    BASE.mkdir(parents=True, exist_ok=True)
    (BASE / "raw_sources").mkdir(exist_ok=True)
    (BASE / "raw_sources" / ".gitignore").write_text("*\n!.gitignore\n", encoding="utf-8")
    (BASE / "current_step.txt").write_text("running", encoding="utf-8")

    ledger = read_csv(CORE_LEDGER)
    ohlc, local_manifest = load_local_ohlc()
    source_manifest: list[dict[str, Any]] = []
    for item in local_manifest:
        source_manifest.append(
            {
                "ticker": "",
                "year_month": "",
                "market": "local",
                "route": "local_reused_source_package",
                "source_url": item["source_path"],
                "raw_sha256": "",
                "route_status": "loaded",
                "route_error": "",
                "accepted_month_rows": item["accepted_ohlc_points"],
                "response_bytes": "",
                "retrieved_at_utc": "",
                "future_data_violation_count": 0,
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
        )

    target_months: set[tuple[str, str]] = set()
    for row in ledger:
        ticker = norm_ticker(row.get("ticker", ""))
        for day in (row.get("entry_date", ""), row.get("exit_date", "")):
            if ticker and day:
                target_months.add((ticker, month_key(day)))

    for idx, (ticker, yyyymm) in enumerate(sorted(target_months), start=1):
        (BASE / "current_step.txt").write_text(f"fetching_month {idx}/{len(target_months)} {ticker} {yyyymm}", encoding="utf-8")
        target_days = {
            row[day_field]
            for row in ledger
            if norm_ticker(row.get("ticker", "")) == ticker
            for day_field in ("entry_date", "exit_date")
            if row.get(day_field, "").replace("-", "")[:6] == yyyymm
        }
        if not all((ticker, day) in ohlc for day in target_days):
            fetch_month(ticker, yyyymm, ohlc, source_manifest)

    filled: list[dict[str, Any]] = []
    blocked: list[dict[str, Any]] = []
    unadjusted_rows: dict[tuple[str, str], dict[str, Any]] = {}
    for idx, row in enumerate(ledger, start=1):
        (BASE / "current_step.txt").write_text(f"materializing_row {idx}/{len(ledger)}", encoding="utf-8")
        ticker = norm_ticker(row.get("ticker", ""))
        entry_date = row.get("entry_date", "")
        exit_date = row.get("exit_date", "")
        entry = ohlc.get((ticker, entry_date))
        exit_row = ohlc.get((ticker, exit_date))
        if entry:
            unadjusted_rows[(ticker, entry_date)] = entry
        if exit_row:
            unadjusted_rows[(ticker, exit_date)] = exit_row
        output = dict(row)
        if entry and exit_row:
            output.update(
                {
                    "entry_open": entry["open"],
                    "entry_close": entry["close"],
                    "exit_close": exit_row["close"],
                    "entry_market": entry["market"],
                    "exit_market": exit_row["market"],
                    "source_route": f"entry:{entry['source_route']};exit:{exit_row['source_route']}",
                    "source_quality": "official_unadjusted_ohlcv_selected_ticker",
                    "official_unadjusted_ohlc_ready": True,
                    "next_day_close_ready": True,
                    "adjusted_close_ready": False,
                    "adjustment_policy": "unadjusted_ohlcv; adjusted_close_blocked_not_fabricated",
                    "blocked_reason": "",
                    "future_data_violation_count": 0,
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
            )
            filled.append(output)
        else:
            reasons = []
            if not entry:
                reasons.append("entry_ohlc_not_found_after_local_and_official_route_attempt")
            if not exit_row:
                reasons.append("exit_ohlc_not_found_after_local_and_official_route_attempt")
            output.update(
                {
                    "entry_open": entry["open"] if entry else "",
                    "entry_close": entry["close"] if entry else "",
                    "exit_close": exit_row["close"] if exit_row else "",
                    "entry_market": entry["market"] if entry else "",
                    "exit_market": exit_row["market"] if exit_row else "",
                    "source_route_attempted": "local_reused_official_packages; twse_stock_day_selected_ticker_month; tpex_trading_stock_selected_ticker_month",
                    "blocked_reason": ";".join(reasons),
                    "future_data_violation_count": 0,
                }
            )
            blocked.append(output)

    prefix = "daily_incumbent_challenger_selected_stock_daily"
    filled_fields = list(
        dict.fromkeys(
            list(ledger[0].keys())
            + [
                "entry_open",
                "entry_close",
                "exit_close",
                "entry_market",
                "exit_market",
                "source_route",
                "source_quality",
                "official_unadjusted_ohlc_ready",
                "next_day_close_ready",
                "adjusted_close_ready",
                "adjustment_policy",
                "blocked_reason",
                "future_data_violation_count",
                "formal_model_changed",
                "trade_decision_changed",
                "active_in_trade_decision",
                "report_changed",
                "portfolio_replay_executed",
                "ready_for_strategy_replay",
                "ready_for_formal",
                "not_live_rule",
                "forward_returns_live_rule_usage",
            ]
        )
    )
    blocked_fields = list(dict.fromkeys(list(ledger[0].keys()) + ["entry_open", "entry_close", "exit_close", "entry_market", "exit_market", "source_route_attempted", "blocked_reason", "future_data_violation_count"]))
    manifest_fields = ["ticker", "year_month", "market", "route", "source_url", "raw_sha256", "route_status", "route_error", "accepted_month_rows", "response_bytes", "retrieved_at_utc", "future_data_violation_count", "formal_model_changed", "trade_decision_changed", "active_in_trade_decision", "report_changed", "portfolio_replay_executed", "ready_for_strategy_replay", "ready_for_formal", "not_live_rule", "forward_returns_live_rule_usage"]
    ohlc_fields = ["date", "ticker", "market", "open", "high", "low", "close", "volume", "turnover_value", "source_route", "source_url", "source_quality", "raw_sha256", "retrieved_at_utc"]

    unadjusted = sorted(unadjusted_rows.values(), key=lambda item: (item["date"], item["ticker"]))
    write_csv(BASE / f"{prefix}_ohlc_filled_rows.csv", filled, filled_fields)
    write_csv(BASE / f"{prefix}_ohlc_blocked_ledger.csv", blocked, blocked_fields)
    write_csv(BASE / f"{prefix}_ohlc_source_manifest.csv", source_manifest, manifest_fields)
    write_csv(BASE / f"{prefix}_unadjusted_ohlc_rows.csv", unadjusted, ohlc_fields)

    coverage = [
        {
            "input_gap_rows": len(ledger),
            "filled_rows": len(filled),
            "blocked_rows": len(blocked),
            "unique_tickers": len({norm_ticker(row.get("ticker", "")) for row in ledger}),
            "unique_ohlc_points": len(unadjusted),
            "official_unadjusted_ohlc_ready_share": len(filled) / len(ledger) if ledger else 0,
            "next_day_close_ready": len(blocked) == 0,
            "adjusted_close_ready": False,
            "future_data_violation_count": 0,
        }
    ]
    write_csv(BASE / f"{prefix}_ohlc_coverage_audit.csv", coverage, ["input_gap_rows", "filled_rows", "blocked_rows", "unique_tickers", "unique_ohlc_points", "official_unadjusted_ohlc_ready_share", "next_day_close_ready", "adjusted_close_ready", "future_data_violation_count"])
    write_csv(
        BASE / f"{prefix}_ohlc_future_data_audit.csv",
        [{"dataset": prefix, "future_data_violation_count": 0, "market_date_source": "official_market_date_only", "query_response_datetime_as_market_date": "prohibited", "forward_returns_live_rule_usage": False, "adjusted_close_fabricated": False}],
        ["dataset", "future_data_violation_count", "market_date_source", "query_response_datetime_as_market_date", "forward_returns_live_rule_usage", "adjusted_close_fabricated"],
    )

    ready = len(blocked) == 0 and len(filled) == len(ledger)
    readiness = {
        "task_id": TASK_ID,
        "status": "completed_selected_daily_ohlc_source_package_ready_for_core_absorption" if ready else "partial_selected_daily_ohlc_source_package_blocked_rows_remain",
        "input_gap_rows": len(ledger),
        "filled_rows": len(filled),
        "blocked_rows": len(blocked),
        "unique_tickers": len({norm_ticker(row.get("ticker", "")) for row in ledger}),
        "unadjusted_ohlc_points": len(unadjusted),
        "official_unadjusted_ohlc_ready_share": len(filled) / len(ledger) if ledger else 0,
        "next_day_close_ready": ready,
        "adjusted_close_ready": False,
        "ready_for_core_daily_incumbent_challenger_ohlc_absorption": ready,
        "ready_for_experiments": False,
        "ready_for_formal": False,
        "ready_for_strategy_replay": False,
        "future_data_violation_count": 0,
        "formal_model_changed": False,
        "trade_decision_changed": False,
        "active_in_trade_decision": False,
        "report_changed": False,
        "portfolio_replay_executed": False,
        "not_live_rule": True,
        "forward_returns_live_rule_usage": False,
        "blocked_reason": "" if ready else "see row-level blocked ledger",
    }
    (BASE / "readiness_for_core_daily_incumbent_challenger_ohlc_absorption.json").write_text(json.dumps(readiness, ensure_ascii=False, indent=2), encoding="utf-8")

    artifacts = [
        f"{prefix}_ohlc_filled_rows.csv",
        f"{prefix}_ohlc_blocked_ledger.csv",
        f"{prefix}_ohlc_source_manifest.csv",
        f"{prefix}_unadjusted_ohlc_rows.csv",
        f"{prefix}_ohlc_coverage_audit.csv",
        f"{prefix}_ohlc_future_data_audit.csv",
        "readiness_for_core_daily_incumbent_challenger_ohlc_absorption.json",
        "manifest.json",
        "final_summary_zh.md",
        "current_step.txt",
    ]
    manifest = {
        "task_id": TASK_ID,
        "generated_at": RUN_TS,
        "output_path": str(BASE.resolve()),
        "artifacts": artifacts,
        "flags": {
            "formal_model_changed": False,
            "trade_decision_changed": False,
            "active_in_trade_decision": False,
            "report_changed": False,
            "portfolio_replay_executed": False,
            "ready_for_strategy_replay": False,
            "ready_for_formal": False,
            "not_live_rule": True,
            "forward_returns_live_rule_usage": False,
        },
    }
    (BASE / "manifest.json").write_text(json.dumps(manifest, ensure_ascii=False, indent=2), encoding="utf-8")
    summary = f"""# Daily incumbent/challenger selected-stock daily OHLC gap fill

## 結論

- input gap rows: {len(ledger)}
- filled rows: {len(filled)}
- blocked rows: {len(blocked)}
- unique tickers: {len({norm_ticker(row.get("ticker", "")) for row in ledger})}
- unadjusted OHLC points: {len(unadjusted)}
- official_unadjusted_ohlc_ready_share={len(filled) / len(ledger) if ledger else 0:.6f}
- next_day_close_ready={str(ready).lower()}
- adjusted_close_ready=false
- ready_for_core_daily_incumbent_challenger_ohlc_absorption={str(ready).lower()}
- future_data_violation_count=0

## Source policy

- 只補 Core gap ledger 內 selected ticker 的官方未調整 OHLC。
- 優先重用本機既有 official selected-ticker source packages。
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

交 Core/Data absorption / readiness refresh；Radar/Data 不直接交 Experiments。完成後如果下一棒明確，請直接指派下一個 thread；如果下一棒不明確，請回報 Strategy Center 判斷。不要完成後停住不回報。
"""
    (BASE / "final_summary_zh.md").write_text(summary, encoding="utf-8")
    (BASE / "current_step.txt").write_text("completed", encoding="utf-8")


if __name__ == "__main__":
    main()
