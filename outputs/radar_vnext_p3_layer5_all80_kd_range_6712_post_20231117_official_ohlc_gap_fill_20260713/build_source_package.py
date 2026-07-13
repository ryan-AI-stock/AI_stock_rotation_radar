from __future__ import annotations

import csv
import hashlib
import json
from datetime import datetime, timezone
from pathlib import Path
from urllib.request import Request, urlopen


TASK_ID = (
    "TASK-RADAR-DATA-VNEXT-P3-LAYER5-ALL80-KD-RANGE-"
    "6712-POST-20231117-OFFICIAL-OHLC-GAP-FILL-001"
)
OUT = Path(__file__).resolve().parent
CORE = Path(
    r"C:\Users\zergv\Documents\Codex\2026-05-30\ep05-chat-ai-stock-backtest-lab"
    r"\outputs\vnext_p3_layer5_all80_KD_range_eligibility_self_range_timing_stage_A_contract_20260713"
)
BLOCKED_INPUT = CORE / "p3_all80_KD_range_execution_blocked_ledger.csv"

TICKER = "6712"
NAME = "長聖"
MARKET = "TPEx"
DECISION_DATE = "2023-11-17"
SOURCE_URL = (
    "https://www.tpex.org.tw/www/zh-tw/afterTrading/tradingStock"
    "?code=6712&date=2023/11/01&response=json"
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


def number(value: str) -> float:
    return float(value.replace(",", ""))


def integer(value: str) -> int:
    return int(value.replace(",", ""))


def read_input_blockers() -> list[dict[str, str]]:
    with BLOCKED_INPUT.open("r", encoding="utf-8-sig", newline="") as handle:
        rows = list(csv.DictReader(handle))
    target = [
        row
        for row in rows
        if row["decision_date"] == DECISION_DATE and row["signal_target"] == TICKER
    ]
    assert len(target) == 8, f"Expected 8 frozen-platform blockers, got {len(target)}"
    return target


def fetch_official_month() -> tuple[bytes, str]:
    request = Request(SOURCE_URL, headers={"User-Agent": "Mozilla/5.0"})
    with urlopen(request, timeout=30) as response:
        status = getattr(response, "status", 200)
        assert status == 200, f"Unexpected HTTP status: {status}"
        return response.read(), str(status)


def main() -> None:
    OUT.mkdir(parents=True, exist_ok=True)
    raw_dir = OUT / "raw_audit_samples"
    raw_dir.mkdir(exist_ok=True)
    generated_at = datetime.now(timezone.utc).replace(microsecond=0).isoformat()
    input_blockers = read_input_blockers()

    raw_bytes, http_status = fetch_official_month()
    raw_path = raw_dir / "TPEx_6712_2023-11.json"
    raw_path.write_bytes(raw_bytes)
    raw_hash = sha256_bytes(raw_bytes)
    payload = json.loads(raw_bytes.decode("utf-8-sig"))

    assert payload["stat"] == "ok"
    assert str(payload["code"]) == TICKER
    assert payload["name"] == NAME
    tables = payload["tables"]
    assert len(tables) == 1
    table = tables[0]
    assert table["fields"][:7] == [
        "日 期", "成交仟股", "成交仟元", "開盤", "最高", "最低", "收盤"
    ]

    official_rows: list[dict[str, object]] = []
    for source_row in table["data"]:
        official_rows.append(
            {
                "date": roc_date_to_iso(source_row[0]),
                "ticker": TICKER,
                "name": NAME,
                "market": MARKET,
                "open": number(source_row[3]),
                "high": number(source_row[4]),
                "low": number(source_row[5]),
                "close": number(source_row[6]),
                "volume": integer(source_row[1]) * 1000,
                "turnover_value": integer(source_row[2]) * 1000,
                "source_route": "TPEx_afterTrading_tradingStock_selected_ticker_month",
                "source_url": SOURCE_URL,
                "source_quality": "official_exact_unadjusted_execution_ohlcv",
                "adjustment_policy": "official_raw_unadjusted_execution_price",
            }
        )

    official_rows.sort(key=lambda row: str(row["date"]))
    after_decision = [row for row in official_rows if str(row["date"]) > DECISION_DATE]
    assert after_decision, "No official trading row after decision date"
    selected = after_decision[0]
    exact_execution_date = str(selected["date"])
    assert exact_execution_date == "2023-11-20"

    all_rows_path = OUT / "p3_all80_KD_range_6712_202311_official_unadjusted_ohlcv_rows.csv"
    row_fields = [
        "date", "ticker", "name", "market", "open", "high", "low", "close",
        "volume", "turnover_value", "source_route", "source_url", "source_quality",
        "adjustment_policy",
    ]
    write_csv(all_rows_path, official_rows, row_fields)

    filled_path = OUT / "p3_all80_KD_range_6712_post_20231117_official_ohlc_filled_rows.csv"
    filled = {
        "decision_date": DECISION_DATE,
        "exact_execution_date": exact_execution_date,
        "ticker": TICKER,
        "name": NAME,
        "market": MARKET,
        "role": "cash_to_stock_entry_execution",
        "frozen_platform_count_affected": len(input_blockers),
        "open": selected["open"],
        "high": selected["high"],
        "low": selected["low"],
        "close": selected["close"],
        "volume": selected["volume"],
        "turnover_value": selected["turnover_value"],
        "official_first_ticker_trading_day_after_decision": True,
        "source_quality": selected["source_quality"],
        "source_route": selected["source_route"],
        "source_url": SOURCE_URL,
        "raw_response_sha256": raw_hash,
        "raw_cache_path": str(raw_path.relative_to(OUT)),
        "adjusted_or_substitute_used": False,
        "accepted_for_core_execution_absorption": True,
        "accepted_for_formal": False,
        "future_data_violation_count": 0,
    }
    filled_fields = list(filled)
    write_csv(filled_path, [filled], filled_fields)

    manifest_path = OUT / "p3_all80_KD_range_6712_official_ohlc_source_manifest.csv"
    manifest_row = {
        "ticker": TICKER,
        "query_month": "2023-11",
        "decision_date": DECISION_DATE,
        "exact_execution_date": exact_execution_date,
        "route": selected["source_route"],
        "source_url": SOURCE_URL,
        "http_status": http_status,
        "official_response_stat": payload["stat"],
        "official_response_row_count": len(official_rows),
        "raw_cache_path": str(raw_path.relative_to(OUT)),
        "raw_response_bytes": len(raw_bytes),
        "raw_response_sha256": raw_hash,
        "retrieved_at_utc": generated_at,
        "market_available_at_policy": (
            "official EOD execution row; not available to the 2023-11-17 decision and "
            "used only as realized first-post-decision execution price"
        ),
        "retrieval_time_used_as_market_date": False,
        "future_data_violation_count": 0,
    }
    write_csv(manifest_path, [manifest_row], list(manifest_row))

    blocked_path = OUT / "p3_all80_KD_range_6712_official_ohlc_blocked_ledger.csv"
    write_csv(
        blocked_path,
        [],
        [
            "decision_date", "ticker", "required_role", "blocked_reason",
            "attempted_route", "future_data_violation_count",
        ],
    )

    audit_path = OUT / "p3_all80_KD_range_6712_official_ohlc_future_data_audit.csv"
    audit_rows = [
        {
            "audit_item": "first_post_decision_ticker_trading_day",
            "status": "pass",
            "detail": (
                "Full official 2023-11 ticker-month sequence was sorted; first row after "
                "2023-11-17 is 2023-11-20."
            ),
            "future_data_violation_count": 0,
        },
        {
            "audit_item": "execution_only_usage",
            "status": "pass",
            "detail": (
                "2023-11-20 official raw OHLC is a realized execution row and is not used "
                "as a 2023-11-17 decision feature."
            ),
            "future_data_violation_count": 0,
        },
        {
            "audit_item": "no_price_substitution",
            "status": "pass",
            "detail": "No neighbor, last-price, adjusted-analysis, or benchmark substitution.",
            "future_data_violation_count": 0,
        },
        {
            "audit_item": "retrieval_metadata",
            "status": "pass",
            "detail": "Retrieval timestamp is metadata only and is not the market date.",
            "future_data_violation_count": 0,
        },
    ]
    write_csv(
        audit_path,
        audit_rows,
        ["audit_item", "status", "detail", "future_data_violation_count"],
    )

    readiness_path = OUT / "readiness_for_core_p3_all80_KD_range_6712_execution_absorption.json"
    readiness = {
        "task_id": TASK_ID,
        "status": "exact_first_post_decision_official_raw_execution_ohlc_ready",
        "input_platform_blocker_rows": len(input_blockers),
        "unique_exact_execution_legs": 1,
        "filled_rows": 1,
        "blocked_rows": 0,
        "ticker": TICKER,
        "decision_date": DECISION_DATE,
        "exact_execution_date": exact_execution_date,
        "official_unadjusted_ohlc_ready": True,
        "first_post_decision_ticker_trading_day_verified": True,
        "ready_for_core_p3_all80_KD_range_6712_execution_absorption": True,
        "ready_for_experiments": False,
        "future_data_violation_count": 0,
        **FLAGS,
    }
    write_json(readiness_path, readiness)

    summary_path = OUT / "final_summary_zh.md"
    summary_path.write_text(
        "# P3 all80 KD-range 6712 execution OHLC 補件\n\n"
        "- Core 的 8 個 frozen platform blocker 實質共用同一筆 execution leg。\n"
        "- TPEx 官方 2023 年 11 月個股日成交序列確認：2023-11-17 後第一個 6712 實際交易日為 2023-11-20。\n"
        "- 6712 長聖 2023-11-20：open 195.5、high 196.5、low 194.0、close 195.0。\n"
        "- 成交量 260,000 股；成交金額 50,863,000 元。\n"
        "- 未使用鄰日、last price、adjusted analysis 或 benchmark 替代。\n"
        "- ready_for_core_p3_all80_KD_range_6712_execution_absorption=true。\n"
        "- ready_for_experiments=false；由 Core 吸收後重鏈 Stage A。\n"
        "- future_data_violation_count=0。\n",
        encoding="utf-8",
    )

    current_step_path = OUT / "current_step.txt"
    current_step_path.write_text("completed_ready_for_core_absorption\n", encoding="utf-8")

    artifacts = [
        all_rows_path,
        filled_path,
        manifest_path,
        blocked_path,
        audit_path,
        readiness_path,
        summary_path,
        current_step_path,
        raw_path,
        Path(__file__).resolve(),
    ]
    package_manifest = {
        "task_id": TASK_ID,
        "generated_at_utc": generated_at,
        "source_route_scope": "one TPEx ticker-month",
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
    write_json(OUT / "manifest.json", package_manifest)


if __name__ == "__main__":
    main()
