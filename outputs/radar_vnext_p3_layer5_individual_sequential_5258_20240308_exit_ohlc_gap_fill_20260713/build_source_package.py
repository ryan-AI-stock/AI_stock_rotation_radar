from __future__ import annotations

import csv
import hashlib
import json
from datetime import datetime, timezone
from pathlib import Path
from urllib.request import Request, urlopen


TASK_ID = "TASK-RADAR-DATA-VNEXT-P3-LAYER5-INDIVIDUAL-SEQUENTIAL-5258-20240308-EXIT-OHLC-GAP-FILL-001"
OUT = Path(__file__).resolve().parent
CORE = Path(
    r"C:\Users\zergv\Documents\Codex\2026-05-30\ep05-chat-ai-stock-backtest-lab"
    r"\outputs\vnext_p3_layer5_all80_individual_stock_sequential_confirmation_stage_A_contract_20260713"
)
GAP_LEDGER = CORE / "p3_individual_stock_sequential_execution_gap_ledger.csv"

TICKER = "5258"
NAME = "虹堡"
MARKET = "TWSE"
SIGNAL_DATE = "2024-03-07"
EXECUTION_DATE = "2024-03-08"
AFFECTED_ROWS = 4
SOURCE_URL = (
    "https://www.twse.com.tw/rwd/zh/afterTrading/STOCK_DAY"
    "?date=20240301&stockNo=5258&response=json"
)

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


def sha256_bytes(data: bytes) -> str:
    return hashlib.sha256(data).hexdigest()


def sha256_file(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as handle:
        for chunk in iter(lambda: handle.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


def write_csv(path: Path, rows: list[dict[str, object]], fields: list[str]) -> None:
    with path.open("w", encoding="utf-8-sig", newline="") as handle:
        writer = csv.DictWriter(handle, fieldnames=fields, extrasaction="ignore")
        writer.writeheader()
        writer.writerows(rows)


def write_json(path: Path, payload: dict[str, object]) -> None:
    path.write_text(json.dumps(payload, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")


def roc_date_to_iso(value: str) -> str:
    year, month, day = (int(part) for part in value.split("/"))
    return f"{year + 1911:04d}-{month:02d}-{day:02d}"


def numeric(value: str) -> float:
    return float(value.replace(",", ""))


def integer(value: str) -> int:
    return int(value.replace(",", ""))


def read_gap() -> dict[str, str]:
    with GAP_LEDGER.open("r", encoding="utf-8-sig", newline="") as handle:
        rows = list(csv.DictReader(handle))
    assert len(rows) == 1, f"Expected one execution gap, got {len(rows)}"
    row = rows[0]
    assert row["ticker"] == TICKER
    assert row["execution_role"] == "exit"
    assert row["signal_date"] == SIGNAL_DATE
    assert row["requested_execution_date"] == EXECUTION_DATE
    assert row["reason"] == "official_raw_execution_close_missing"
    return row


def fetch_official_month() -> tuple[bytes, int]:
    request = Request(SOURCE_URL, headers={"User-Agent": "Mozilla/5.0"})
    with urlopen(request, timeout=30) as response:
        return response.read(), int(getattr(response, "status", 200))


def main() -> None:
    OUT.mkdir(parents=True, exist_ok=True)
    raw_dir = OUT / "raw_audit_samples"
    raw_dir.mkdir(exist_ok=True)
    gap = read_gap()
    generated_at = datetime.now(timezone.utc).replace(microsecond=0).isoformat()

    raw_bytes, http_status = fetch_official_month()
    assert http_status == 200
    raw_path = raw_dir / "TWSE_5258_2024-03.json"
    raw_path.write_bytes(raw_bytes)
    raw_hash = sha256_bytes(raw_bytes)
    payload = json.loads(raw_bytes.decode("utf-8-sig"))
    assert str(payload.get("stat", "")).upper() == "OK"
    assert payload["fields"][:7] == [
        "日期", "成交股數", "成交金額", "開盤價", "最高價", "最低價", "收盤價"
    ]

    month_rows: list[dict[str, object]] = []
    for source_row in payload["data"]:
        month_rows.append(
            {
                "date": roc_date_to_iso(source_row[0]),
                "ticker": TICKER,
                "name": NAME,
                "market": MARKET,
                "open": numeric(source_row[3]),
                "high": numeric(source_row[4]),
                "low": numeric(source_row[5]),
                "close": numeric(source_row[6]),
                "volume": integer(source_row[1]),
                "turnover_value": integer(source_row[2]),
                "source_route": "TWSE_STOCK_DAY_selected_ticker_month",
                "source_url": SOURCE_URL,
                "source_quality": "official_exact_unadjusted_execution_ohlcv",
                "adjustment_policy": "official_raw_unadjusted_execution_price",
            }
        )
    month_rows.sort(key=lambda row: str(row["date"]))
    exact = [row for row in month_rows if row["date"] == EXECUTION_DATE]
    after_signal = [row for row in month_rows if str(row["date"]) > SIGNAL_DATE]
    assert len(exact) == 1
    assert after_signal and after_signal[0]["date"] == EXECUTION_DATE
    selected = exact[0]

    month_path = OUT / "p3_individual_sequential_5258_202403_official_unadjusted_ohlcv_rows.csv"
    month_fields = [
        "date", "ticker", "name", "market", "open", "high", "low", "close",
        "volume", "turnover_value", "source_route", "source_url", "source_quality",
        "adjustment_policy",
    ]
    write_csv(month_path, month_rows, month_fields)

    filled_path = OUT / "p3_individual_sequential_5258_20240308_exit_official_ohlc_filled_row.csv"
    filled = {
        "ticker": TICKER,
        "name": NAME,
        "market": MARKET,
        "execution_role": gap["execution_role"],
        "signal_date": SIGNAL_DATE,
        "exact_execution_date": EXECUTION_DATE,
        "first_post_signal_ticker_trading_date_verified": True,
        "open": selected["open"],
        "high": selected["high"],
        "low": selected["low"],
        "close": selected["close"],
        "volume": selected["volume"],
        "turnover_value": selected["turnover_value"],
        "source_quality": selected["source_quality"],
        "source_route": selected["source_route"],
        "source_url": SOURCE_URL,
        "raw_response_sha256": raw_hash,
        "raw_cache_path": str(raw_path.relative_to(OUT)),
        "affected_matched_event_platform_rows": AFFECTED_ROWS,
        "adjusted_or_substitute_used": False,
        "accepted_for_core_execution_absorption": True,
        "accepted_for_formal": False,
        "future_data_violation_count": 0,
    }
    write_csv(filled_path, [filled], list(filled))

    source_manifest_path = OUT / "p3_individual_sequential_5258_20240308_exit_official_ohlc_source_manifest.csv"
    source_manifest = {
        "ticker": TICKER,
        "query_month": "2024-03",
        "signal_date": SIGNAL_DATE,
        "exact_execution_date": EXECUTION_DATE,
        "route": selected["source_route"],
        "source_url": SOURCE_URL,
        "http_status": http_status,
        "official_response_stat": payload["stat"],
        "official_response_row_count": len(month_rows),
        "raw_cache_path": str(raw_path.relative_to(OUT)),
        "raw_response_bytes": len(raw_bytes),
        "raw_response_sha256": raw_hash,
        "retrieved_at_utc": generated_at,
        "market_available_at_policy": (
            "official EOD execution row; not available to the signal date and used only "
            "as realized first-post-signal exit execution price"
        ),
        "retrieval_time_used_as_market_date": False,
        "future_data_violation_count": 0,
    }
    write_csv(source_manifest_path, [source_manifest], list(source_manifest))

    blocked_path = OUT / "p3_individual_sequential_5258_20240308_exit_official_ohlc_blocked_ledger.csv"
    write_csv(
        blocked_path,
        [],
        [
            "ticker", "execution_role", "signal_date", "requested_execution_date",
            "blocked_reason", "attempted_route", "future_data_violation_count",
        ],
    )

    audit_path = OUT / "p3_individual_sequential_5258_20240308_exit_official_ohlc_future_data_audit.csv"
    audit_rows = [
        {
            "audit_item": "first_post_signal_ticker_trading_day",
            "status": "pass",
            "detail": "Full official 2024-03 sequence confirms 2024-03-08 is the first 5258 trading row after 2024-03-07.",
            "future_data_violation_count": 0,
        },
        {
            "audit_item": "execution_only_usage",
            "status": "pass",
            "detail": "2024-03-08 official raw OHLC is used only as realized exit execution price, not as a 2024-03-07 feature.",
            "future_data_violation_count": 0,
        },
        {
            "audit_item": "no_substitution",
            "status": "pass",
            "detail": "No neighbor, last-price, adjusted-analysis, or benchmark substitution.",
            "future_data_violation_count": 0,
        },
        {
            "audit_item": "scope_and_outcome_guard",
            "status": "pass",
            "detail": "One ticker-month only; no P3-2 outcome read and no performance calculation.",
            "future_data_violation_count": 0,
        },
    ]
    write_csv(
        audit_path,
        audit_rows,
        ["audit_item", "status", "detail", "future_data_violation_count"],
    )

    readiness_path = OUT / "readiness_for_core_p3_individual_sequential_5258_exit_ohlc_absorption.json"
    readiness = {
        "task_id": TASK_ID,
        "status": "exact_first_post_signal_official_raw_exit_ohlc_ready",
        "input_execution_gap_rows": 1,
        "filled_rows": 1,
        "blocked_rows": 0,
        "affected_matched_event_platform_rows": AFFECTED_ROWS,
        "official_unadjusted_ohlc_ready": True,
        "first_post_signal_ticker_trading_day_verified": True,
        "ready_for_core_p3_individual_sequential_5258_exit_ohlc_absorption": True,
        "ready_for_core_rechain": True,
        "ready_for_experiments": False,
        "represents_individual_stock_layer_stage": True,
        "performance_authorized": False,
        "P3_2_outcome_read": False,
        "future_data_violation_count": 0,
        **FLAGS,
    }
    write_json(readiness_path, readiness)

    summary_path = OUT / "final_summary_zh.md"
    summary_path.write_text(
        "# P3-1 individual sequential 5258 exit OHLC 補件\n\n"
        "- 唯一 execution gap 已由 TWSE selected ticker-month 官方資料補齊。\n"
        "- 2024-03-07 exit signal 後第一個 5258 實際交易日為 2024-03-08。\n"
        "- 5258 虹堡 2024-03-08：open 131、high 131、low 123、close 123。\n"
        "- 成交量 4,576,707 股；成交金額 575,492,261 元。\n"
        "- 影響 4 個 matched event-platform rows；blocked_rows=0。\n"
        "- 未使用鄰日、last price、adjusted analysis 或 benchmark 替代。\n"
        "- ready_for_core_rechain=true；ready_for_experiments=false。\n"
        "- future_data_violation_count=0。\n",
        encoding="utf-8",
    )

    current_step_path = OUT / "current_step.txt"
    current_step_path.write_text("completed_ready_for_core_absorption\n", encoding="utf-8")

    artifacts = [
        month_path,
        filled_path,
        source_manifest_path,
        blocked_path,
        audit_path,
        readiness_path,
        summary_path,
        current_step_path,
        raw_path,
        Path(__file__).resolve(),
    ]
    manifest = {
        "task_id": TASK_ID,
        "generated_at_utc": generated_at,
        "source_scope": "one TWSE ticker-month",
        "artifacts": [
            {
                "path": str(path.relative_to(OUT)),
                "size_bytes": path.stat().st_size,
                "sha256": sha256_file(path),
            }
            for path in artifacts
        ],
        "future_data_violation_count": 0,
        **FLAGS,
    }
    write_json(OUT / "manifest.json", manifest)


if __name__ == "__main__":
    main()
