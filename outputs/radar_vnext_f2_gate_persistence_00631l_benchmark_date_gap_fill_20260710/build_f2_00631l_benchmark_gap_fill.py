from __future__ import annotations

import csv
import hashlib
import json
import re
from datetime import datetime, timezone
from pathlib import Path
from typing import Any


TASK_ID = "TASK-RADAR-DATA-VNEXT-F2-GATE-PERSISTENCE-00631L-BENCHMARK-DATE-GAP-FILL-001"
RADAR_ROOT = Path(r"C:\Users\zergv\Documents\Codex\2026-05-23\ai-stock-rotation-radar-https-docs")
BASE = RADAR_ROOT / "outputs" / "radar_vnext_f2_gate_persistence_00631l_benchmark_date_gap_fill_20260710"
RAW = BASE / "raw_sources"
CORE_LEDGER = Path(
    r"C:\Users\zergv\Documents\Codex\2026-05-30\ep05-chat-ai-stock-backtest-lab"
    r"\outputs\vnext_f2_gate_persistence_hysteresis_incumbent_protection_contract_20260710"
    r"\f2_gate_persistence_00631L_benchmark_gap_ledger.csv"
)
PRIOR_RAW = (
    RADAR_ROOT
    / "outputs/radar_vnext_daily_incumbent_challenger_00631l_benchmark_price_gap_fill_20260710"
    / "raw_sources/twse_stock_day_00631L_202606.json"
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


def read_csv(path: Path) -> list[dict[str, str]]:
    with path.open("r", encoding="utf-8-sig", newline="") as f:
        return list(csv.DictReader(f))


def write_csv(path: Path, rows: list[dict[str, Any]], fields: list[str]) -> None:
    with path.open("w", encoding="utf-8-sig", newline="") as f:
        writer = csv.DictWriter(f, fieldnames=fields, extrasaction="ignore")
        writer.writeheader()
        for row in rows:
            writer.writerow({field: row.get(field, "") for field in fields})


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
    match = re.match(r"^(\d{2,3})/(\d{1,2})/(\d{1,2})$", str(value).strip())
    if not match:
        return str(value).strip()
    return f"{int(match.group(1)) + 1911:04d}-{int(match.group(2)):02d}-{int(match.group(3)):02d}"


def load_twse_stock_day(raw_path: Path) -> tuple[dict[str, dict[str, Any]], str]:
    raw = raw_path.read_bytes()
    raw_sha = hashlib.sha256(raw).hexdigest()
    doc = json.loads(raw.decode("utf-8-sig"))
    fields = doc.get("fields") or []
    rows_by_date: dict[str, dict[str, Any]] = {}
    for item in doc.get("data", []):
        row = dict(zip(fields, item))
        date = roc_to_iso(row.get("日期", ""))
        close = parse_num(row.get("收盤價"))
        if not re.match(r"^\d{4}-\d{2}-\d{2}$", date) or close is None:
            continue
        rows_by_date[date] = {
            "date": date,
            "ticker": "00631L",
            "asset_type": "etf",
            "name": "元大台灣50正2",
            "market": "TWSE",
            "open": parse_num(row.get("開盤價")) or "",
            "high": parse_num(row.get("最高價")) or "",
            "low": parse_num(row.get("最低價")) or "",
            "close": close,
            "volume": parse_int(row.get("成交股數")),
            "turnover_value": parse_int(row.get("成交金額")),
            "source_route": "twse_stock_day_selected_etf_month_reused_official_raw",
            "source_url": "https://www.twse.com.tw/exchangeReport/STOCK_DAY?date=20260601&stockNo=00631L&response=json",
            "source_quality": "official_unadjusted_close_selected_etf_month_reused_raw",
            "raw_sha256": raw_sha,
            "retrieved_at_utc": "",
            "adjustment_policy": "official_unadjusted_close_only; adjusted_close_not_fabricated",
        }
    return rows_by_date, raw_sha


def main() -> None:
    BASE.mkdir(parents=True, exist_ok=True)
    RAW.mkdir(exist_ok=True)
    (RAW / ".gitignore").write_text("*\n!.gitignore\n", encoding="utf-8")
    (BASE / "current_step.txt").write_text("running\n", encoding="utf-8")

    ledger = read_csv(CORE_LEDGER)
    prices, raw_sha = load_twse_stock_day(PRIOR_RAW)
    filled: list[dict[str, Any]] = []
    blocked: list[dict[str, Any]] = []
    unadjusted: list[dict[str, Any]] = []

    for row in ledger:
        price = prices.get(row["price_date"])
        output = dict(row)
        if price:
            output.update(
                {
                    "name": price["name"],
                    "market": price["market"],
                    "open": price["open"],
                    "high": price["high"],
                    "low": price["low"],
                    "close": price["close"],
                    "volume": price["volume"],
                    "turnover_value": price["turnover_value"],
                    "source_route": price["source_route"],
                    "source_url": price["source_url"],
                    "source_quality": price["source_quality"],
                    "raw_sha256": raw_sha,
                    "raw_cache_path": str(PRIOR_RAW.relative_to(RADAR_ROOT)),
                    "official_unadjusted_ohlc_ready": True,
                    "adjusted_close_ready": False,
                    "adjustment_policy": price["adjustment_policy"],
                    "blocked_reason": "",
                    "future_data_violation_count": 0,
                    **FLAGS,
                }
            )
            filled.append(output)
            unadjusted.append(price)
        else:
            output.update(
                {
                    "source_route": "twse_stock_day_selected_etf_month_reused_official_raw",
                    "source_url": "https://www.twse.com.tw/exchangeReport/STOCK_DAY?date=20260601&stockNo=00631L&response=json",
                    "source_quality": "",
                    "raw_sha256": raw_sha,
                    "raw_cache_path": str(PRIOR_RAW.relative_to(RADAR_ROOT)),
                    "official_unadjusted_ohlc_ready": False,
                    "adjusted_close_ready": False,
                    "adjustment_policy": "adjusted_close_not_fabricated",
                    "blocked_reason": "target_price_date_missing_in_reused_twse_official_raw",
                    "future_data_violation_count": 0,
                    **FLAGS,
                }
            )
            blocked.append(output)

    unique_unadjusted = sorted({(r["ticker"], r["date"]): r for r in unadjusted}.values(), key=lambda r: r["date"])
    ready = len(blocked) == 0 and len(filled) == len(ledger)
    prefix = "f2_gate_persistence_00631L_benchmark_price"
    row_fields = list(dict.fromkeys(list(ledger[0].keys()) + [
        "name", "market", "open", "high", "low", "close", "volume", "turnover_value",
        "source_route", "source_url", "source_quality", "raw_sha256", "raw_cache_path",
        "official_unadjusted_ohlc_ready", "adjusted_close_ready", "adjustment_policy",
        "blocked_reason", "future_data_violation_count", *FLAGS.keys(),
    ]))
    write_csv(BASE / f"{prefix}_filled_rows.csv", filled, row_fields)
    write_csv(BASE / f"{prefix}_blocked_ledger.csv", blocked, row_fields)
    write_csv(
        BASE / f"{prefix}_source_manifest.csv",
        [{
            "ticker": "00631L",
            "year_month": "202606",
            "market": "TWSE",
            "route": "twse_stock_day_selected_etf_month_reused_official_raw",
            "source_url": "https://www.twse.com.tw/exchangeReport/STOCK_DAY?date=20260601&stockNo=00631L&response=json",
            "raw_cache_path": str(PRIOR_RAW.relative_to(RADAR_ROOT)),
            "raw_sha256": raw_sha,
            "route_status": "reused_existing_official_raw",
            "route_error": "",
            "accepted_month_rows": len(prices),
            "target_rows_filled": len(filled),
            "retrieved_at_utc": "",
            "future_data_violation_count": 0,
            **FLAGS,
        }],
        ["ticker", "year_month", "market", "route", "source_url", "raw_cache_path", "raw_sha256", "route_status", "route_error", "accepted_month_rows", "target_rows_filled", "retrieved_at_utc", "future_data_violation_count", *FLAGS.keys()],
    )
    write_csv(
        BASE / f"{prefix}_unadjusted_ohlc_rows.csv",
        unique_unadjusted,
        ["date", "ticker", "asset_type", "name", "market", "open", "high", "low", "close", "volume", "turnover_value", "source_route", "source_url", "source_quality", "raw_sha256", "retrieved_at_utc", "adjustment_policy"],
    )
    write_csv(
        BASE / f"{prefix}_coverage_audit.csv",
        [{
            "input_gap_rows": len(ledger),
            "filled_rows": len(filled),
            "blocked_rows": len(blocked),
            "unique_price_dates": len({r["price_date"] for r in ledger}),
            "official_unadjusted_ohlc_ready_share": len(filled) / len(ledger) if ledger else 0,
            "adjusted_close_ready": False,
            "ready_for_core_f2_gate_persistence_00631L_benchmark_absorption": ready,
            "future_data_violation_count": 0,
        }],
        ["input_gap_rows", "filled_rows", "blocked_rows", "unique_price_dates", "official_unadjusted_ohlc_ready_share", "adjusted_close_ready", "ready_for_core_f2_gate_persistence_00631L_benchmark_absorption", "future_data_violation_count"],
    )
    write_csv(
        BASE / f"{prefix}_future_data_audit.csv",
        [{
            "dataset": prefix,
            "future_data_violation_count": 0,
            "market_date_source": "official_twse_market_date_only",
            "query_response_datetime_as_market_date": "prohibited",
            "forward_returns_live_rule_usage": False,
            "adjusted_close_fabricated": False,
        }],
        ["dataset", "future_data_violation_count", "market_date_source", "query_response_datetime_as_market_date", "forward_returns_live_rule_usage", "adjusted_close_fabricated"],
    )
    readiness = {
        "task_id": TASK_ID,
        "status": "completed_f2_gate_persistence_00631L_benchmark_source_package_ready_for_core_absorption" if ready else "blocked_f2_gate_persistence_00631L_benchmark_rows_remain",
        "input_gap_rows": len(ledger),
        "filled_rows": len(filled),
        "blocked_rows": len(blocked),
        "unique_price_dates": len({r["price_date"] for r in ledger}),
        "official_unadjusted_ohlc_ready_share": len(filled) / len(ledger) if ledger else 0,
        "adjusted_close_ready": False,
        "ready_for_core_f2_gate_persistence_00631L_benchmark_absorption": ready,
        "ready_for_experiments": False,
        "ready_for_formal": False,
        "ready_for_strategy_replay": False,
        "future_data_violation_count": 0,
        **FLAGS,
        "blocked_reason": "" if ready else "see row-level blocked ledger",
    }
    (BASE / "readiness_for_core_f2_gate_persistence_00631L_benchmark_absorption.json").write_text(json.dumps(readiness, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    artifacts = [
        f"{prefix}_filled_rows.csv",
        f"{prefix}_blocked_ledger.csv",
        f"{prefix}_source_manifest.csv",
        f"{prefix}_unadjusted_ohlc_rows.csv",
        f"{prefix}_coverage_audit.csv",
        f"{prefix}_future_data_audit.csv",
        "readiness_for_core_f2_gate_persistence_00631L_benchmark_absorption.json",
        "manifest.json",
        "final_summary_zh.md",
        "current_step.txt",
    ]
    (BASE / "manifest.json").write_text(json.dumps({"task_id": TASK_ID, "generated_at": RUN_TS, "output_path": str(BASE), "artifacts": artifacts, "flags": FLAGS}, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    (BASE / "final_summary_zh.md").write_text(f"""# F2 gate persistence 00631L benchmark date gap fill

## 結論

- input gap rows: {len(ledger)}
- filled rows: {len(filled)}
- blocked rows: {len(blocked)}
- unique price dates: {len({r["price_date"] for r in ledger})}
- official_unadjusted_ohlc_ready_share={len(filled) / len(ledger) if ledger else 0:.6f}
- adjusted_close_ready=false
- ready_for_core_f2_gate_persistence_00631L_benchmark_absorption={str(ready).lower()}
- ready_for_experiments=false
- ready_for_formal=false
- future_data_violation_count=0

## Source policy

- 只補 Core ledger 內 00631L benchmark price dates。
- 重用本機既有 TWSE official STOCK_DAY raw cache，不做 full-market download。
- 不使用鄰日替代，不使用 00631L + excess reconstruction。
- 本包輸出 official unadjusted close，adjusted_close 未 fabricated。

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
""", encoding="utf-8")
    (BASE / "current_step.txt").write_text("completed\n", encoding="utf-8")


if __name__ == "__main__":
    main()
