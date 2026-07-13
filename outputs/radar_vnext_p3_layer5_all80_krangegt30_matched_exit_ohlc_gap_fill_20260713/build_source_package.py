from __future__ import annotations

import csv
import hashlib
import json
from datetime import datetime, timezone
from pathlib import Path
from urllib.request import Request, urlopen


TASK_ID = "TASK-RADAR-DATA-VNEXT-P3-LAYER5-ALL80-KRANGEGT30-MATCHED-EXIT-OHLC-GAP-FILL-001"
OUT = Path(__file__).resolve().parent
CORE = Path(
    r"C:\Users\zergv\Documents\Codex\2026-05-30\ep05-chat-ai-stock-backtest-lab"
    r"\outputs\vnext_p3_layer5_all80_self_range_KrangeGT30_matched_exit_contract_20260713"
)
AUTHORITY = CORE / "p3_all80_KrangeGT30_official_execution_gap_unique_legs.csv"

TICKER_MASTER = {
    "1101": ("台泥", "TWSE"),
    "1102": ("亞泥", "TWSE"),
    "1319": ("東陽", "TWSE"),
    "1808": ("潤隆", "TWSE"),
    "2014": ("中鴻", "TWSE"),
    "2540": ("愛山林", "TWSE"),
    "4919": ("新唐", "TWSE"),
    "6451": ("訊芯-KY", "TWSE"),
    "6757": ("台灣虎航", "TWSE"),
    "8089": ("康全電訊", "TPEx"),
    "9921": ("巨大", "TWSE"),
}

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


def read_csv(path: Path) -> list[dict[str, str]]:
    with path.open("r", encoding="utf-8-sig", newline="") as handle:
        return list(csv.DictReader(handle))


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


def source_url(ticker: str, market: str, target_date: str) -> str:
    year, month, _ = target_date.split("-")
    if market == "TWSE":
        return (
            "https://www.twse.com.tw/rwd/zh/afterTrading/STOCK_DAY"
            f"?date={year}{month}01&stockNo={ticker}&response=json"
        )
    return (
        "https://www.tpex.org.tw/www/zh-tw/afterTrading/tradingStock"
        f"?code={ticker}&date={year}/{month}/01&response=json"
    )


def fetch(url: str) -> tuple[bytes, int]:
    request = Request(url, headers={"User-Agent": "Mozilla/5.0"})
    with urlopen(request, timeout=30) as response:
        return response.read(), int(getattr(response, "status", 200))


def parse_twse(payload: dict[str, object], ticker: str, name: str, url: str) -> list[dict[str, object]]:
    if str(payload.get("stat", "")).upper() != "OK":
        return []
    fields = payload.get("fields", [])
    assert fields[:7] == ["日期", "成交股數", "成交金額", "開盤價", "最高價", "最低價", "收盤價"]
    rows = []
    for source_row in payload.get("data", []):
        rows.append(
            {
                "date": roc_date_to_iso(source_row[0]),
                "ticker": ticker,
                "name": name,
                "market": "TWSE",
                "open": numeric(source_row[3]),
                "high": numeric(source_row[4]),
                "low": numeric(source_row[5]),
                "close": numeric(source_row[6]),
                "volume": integer(source_row[1]),
                "turnover_value": integer(source_row[2]),
                "source_route": "TWSE_STOCK_DAY_selected_ticker_month",
                "source_url": url,
                "source_quality": "official_exact_unadjusted_execution_ohlcv",
                "adjustment_policy": "official_raw_unadjusted_execution_price",
            }
        )
    return rows


def parse_tpex(payload: dict[str, object], ticker: str, name: str, url: str) -> list[dict[str, object]]:
    if str(payload.get("stat", "")).lower() != "ok":
        return []
    assert str(payload.get("code")) == ticker
    tables = payload.get("tables", [])
    assert len(tables) == 1
    table = tables[0]
    assert table["fields"][:7] == ["日 期", "成交仟股", "成交仟元", "開盤", "最高", "最低", "收盤"]
    rows = []
    for source_row in table.get("data", []):
        rows.append(
            {
                "date": roc_date_to_iso(source_row[0]),
                "ticker": ticker,
                "name": name,
                "market": "TPEx",
                "open": numeric(source_row[3]),
                "high": numeric(source_row[4]),
                "low": numeric(source_row[5]),
                "close": numeric(source_row[6]),
                "volume": integer(source_row[1]) * 1000,
                "turnover_value": integer(source_row[2]) * 1000,
                "source_route": "TPEx_afterTrading_tradingStock_selected_ticker_month",
                "source_url": url,
                "source_quality": "official_exact_unadjusted_execution_ohlcv",
                "adjustment_policy": "official_raw_unadjusted_execution_price",
            }
        )
    return rows


def main() -> None:
    OUT.mkdir(parents=True, exist_ok=True)
    raw_dir = OUT / "raw_audit_samples"
    raw_dir.mkdir(exist_ok=True)
    generated_at = datetime.now(timezone.utc).replace(microsecond=0).isoformat()

    authority = read_csv(AUTHORITY)
    assert len(authority) == 11, f"Expected 11 exact legs, got {len(authority)}"
    assert {row["ticker"] for row in authority} == set(TICKER_MASTER)

    filled_rows: list[dict[str, object]] = []
    blocked_rows: list[dict[str, object]] = []
    manifest_rows: list[dict[str, object]] = []
    all_official_rows: list[dict[str, object]] = []

    for leg in authority:
        ticker = leg["ticker"]
        decision_date = leg["signal_decision_date"]
        target_date = leg["requested_first_post_signal_ticker_trading_date"]
        name, market = TICKER_MASTER[ticker]
        url = source_url(ticker, market, target_date)
        year_month = target_date[:7]
        raw_path = raw_dir / f"{market}_{ticker}_{year_month}.json"
        route_status = "source_gap"
        error = ""
        response_stat = ""
        month_rows: list[dict[str, object]] = []
        raw_hash = ""
        raw_size = 0
        http_status: int | str = ""

        try:
            raw_bytes, http_status = fetch(url)
            raw_path.write_bytes(raw_bytes)
            raw_hash = sha256_bytes(raw_bytes)
            raw_size = len(raw_bytes)
            payload = json.loads(raw_bytes.decode("utf-8-sig"))
            response_stat = str(payload.get("stat", ""))
            if market == "TWSE":
                month_rows = parse_twse(payload, ticker, name, url)
            else:
                month_rows = parse_tpex(payload, ticker, name, url)
            month_rows.sort(key=lambda row: str(row["date"]))
            all_official_rows.extend(month_rows)
            exact = [row for row in month_rows if row["date"] == target_date]
            after_decision = [row for row in month_rows if str(row["date"]) > decision_date]
            first_after = str(after_decision[0]["date"]) if after_decision else ""

            if len(exact) == 1 and first_after == target_date:
                source_row = exact[0]
                route_status = "accepted"
                filled_rows.append(
                    {
                        "ticker": ticker,
                        "name": name,
                        "market": market,
                        "signal_role": leg["signal_role"],
                        "signal_decision_date": decision_date,
                        "exact_execution_date": target_date,
                        "first_post_signal_ticker_trading_date_verified": True,
                        "open": source_row["open"],
                        "high": source_row["high"],
                        "low": source_row["low"],
                        "close": source_row["close"],
                        "volume": source_row["volume"],
                        "turnover_value": source_row["turnover_value"],
                        "source_quality": source_row["source_quality"],
                        "source_route": source_row["source_route"],
                        "source_url": url,
                        "raw_response_sha256": raw_hash,
                        "raw_cache_path": str(raw_path.relative_to(OUT)),
                        "affected_event_platform_rows": int(leg["affected_event_platform_rows"]),
                        "leg_status": "accepted",
                        "adjusted_or_substitute_used": False,
                        "future_data_violation_count": 0,
                    }
                )
            elif not exact:
                route_status = "official_no_row"
                blocked_rows.append(
                    {
                        "ticker": ticker,
                        "market": market,
                        "signal_role": leg["signal_role"],
                        "signal_decision_date": decision_date,
                        "requested_execution_date": target_date,
                        "leg_status": "official_no_row",
                        "blocked_reason": "official_month_response_has_no_exact_ticker_date_row",
                        "first_official_row_after_signal": first_after,
                        "source_url": url,
                        "raw_response_sha256": raw_hash,
                        "future_data_violation_count": 0,
                    }
                )
            else:
                route_status = "source_gap"
                blocked_rows.append(
                    {
                        "ticker": ticker,
                        "market": market,
                        "signal_role": leg["signal_role"],
                        "signal_decision_date": decision_date,
                        "requested_execution_date": target_date,
                        "leg_status": "source_gap",
                        "blocked_reason": "requested_date_is_not_first_official_ticker_trading_day_after_signal",
                        "first_official_row_after_signal": first_after,
                        "source_url": url,
                        "raw_response_sha256": raw_hash,
                        "future_data_violation_count": 0,
                    }
                )
        except Exception as exc:  # Preserve exact bounded route failure evidence.
            error = f"{type(exc).__name__}: {exc}"
            blocked_rows.append(
                {
                    "ticker": ticker,
                    "market": market,
                    "signal_role": leg["signal_role"],
                    "signal_decision_date": decision_date,
                    "requested_execution_date": target_date,
                    "leg_status": "source_gap",
                    "blocked_reason": error,
                    "first_official_row_after_signal": "",
                    "source_url": url,
                    "raw_response_sha256": raw_hash,
                    "future_data_violation_count": 0,
                }
            )

        manifest_rows.append(
            {
                "ticker": ticker,
                "name": name,
                "market": market,
                "query_month": year_month,
                "requested_execution_date": target_date,
                "route": (
                    "TWSE_STOCK_DAY_selected_ticker_month"
                    if market == "TWSE"
                    else "TPEx_afterTrading_tradingStock_selected_ticker_month"
                ),
                "source_url": url,
                "http_status": http_status,
                "official_response_stat": response_stat,
                "official_response_row_count": len(month_rows),
                "route_status": route_status,
                "route_error": error,
                "raw_cache_path": str(raw_path.relative_to(OUT)) if raw_path.exists() else "",
                "raw_response_bytes": raw_size,
                "raw_response_sha256": raw_hash,
                "retrieved_at_utc": generated_at,
                "retrieval_time_used_as_market_date": False,
                "future_data_violation_count": 0,
            }
        )

    filled_fields = [
        "ticker", "name", "market", "signal_role", "signal_decision_date",
        "exact_execution_date", "first_post_signal_ticker_trading_date_verified",
        "open", "high", "low", "close", "volume", "turnover_value",
        "source_quality", "source_route", "source_url", "raw_response_sha256",
        "raw_cache_path", "affected_event_platform_rows", "leg_status",
        "adjusted_or_substitute_used", "future_data_violation_count",
    ]
    filled_path = OUT / "p3_all80_KrangeGT30_matched_exit_official_ohlc_filled_legs.csv"
    write_csv(filled_path, filled_rows, filled_fields)

    blocked_fields = [
        "ticker", "market", "signal_role", "signal_decision_date",
        "requested_execution_date", "leg_status", "blocked_reason",
        "first_official_row_after_signal", "source_url", "raw_response_sha256",
        "future_data_violation_count",
    ]
    blocked_path = OUT / "p3_all80_KrangeGT30_matched_exit_official_ohlc_blocked_ledger.csv"
    write_csv(blocked_path, blocked_rows, blocked_fields)

    manifest_fields = [
        "ticker", "name", "market", "query_month", "requested_execution_date",
        "route", "source_url", "http_status", "official_response_stat",
        "official_response_row_count", "route_status", "route_error",
        "raw_cache_path", "raw_response_bytes", "raw_response_sha256",
        "retrieved_at_utc", "retrieval_time_used_as_market_date",
        "future_data_violation_count",
    ]
    source_manifest_path = OUT / "p3_all80_KrangeGT30_matched_exit_official_ohlc_source_manifest.csv"
    write_csv(source_manifest_path, manifest_rows, manifest_fields)

    all_rows_path = OUT / "p3_all80_KrangeGT30_matched_exit_official_unadjusted_ohlcv_month_rows.csv"
    all_row_fields = [
        "date", "ticker", "name", "market", "open", "high", "low", "close",
        "volume", "turnover_value", "source_route", "source_url", "source_quality",
        "adjustment_policy",
    ]
    write_csv(all_rows_path, all_official_rows, all_row_fields)

    accepted = sum(row["leg_status"] == "accepted" for row in filled_rows)
    official_no_row = sum(row["leg_status"] == "official_no_row" for row in blocked_rows)
    source_gap = sum(row["leg_status"] == "source_gap" for row in blocked_rows)
    audit_path = OUT / "p3_all80_KrangeGT30_matched_exit_official_ohlc_future_data_audit.csv"
    audit_rows = [
        {
            "audit_item": "exact_ticker_date_only",
            "status": "pass" if accepted == 11 else "partial",
            "detail": f"accepted={accepted}; official_no_row={official_no_row}; source_gap={source_gap}",
            "future_data_violation_count": 0,
        },
        {
            "audit_item": "first_post_signal_ticker_trading_day",
            "status": "pass" if accepted == 11 else "partial",
            "detail": "Each accepted leg matches the first official ticker trading row after its signal date.",
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
            "detail": "Only 11 authority legs queried; no performance or P3-2 outcome read.",
            "future_data_violation_count": 0,
        },
    ]
    write_csv(
        audit_path,
        audit_rows,
        ["audit_item", "status", "detail", "future_data_violation_count"],
    )

    readiness_path = OUT / "readiness_for_core_p3_all80_KrangeGT30_matched_exit_ohlc_absorption.json"
    readiness = {
        "task_id": TASK_ID,
        "status": (
            "all_exact_official_raw_execution_legs_ready_for_core_absorption"
            if accepted == 11
            else "partial_exact_execution_source_package_with_explicit_blockers"
        ),
        "input_unique_legs": len(authority),
        "accepted_legs": accepted,
        "official_no_row_legs": official_no_row,
        "source_gap_legs": source_gap,
        "blocked_legs": len(blocked_rows),
        "affected_event_platform_rows": sum(int(row["affected_event_platform_rows"]) for row in authority),
        "official_unadjusted_ohlc_ready_share": accepted / len(authority),
        "ready_for_core_p3_all80_KrangeGT30_matched_exit_ohlc_absorption": accepted > 0,
        "ready_for_core_full_rechain": accepted == 11,
        "ready_for_experiments": False,
        "p3_2_outcome_read": False,
        "future_data_violation_count": 0,
        **FLAGS,
    }
    write_json(readiness_path, readiness)

    summary_path = OUT / "final_summary_zh.md"
    summary_path.write_text(
        "# P3 all80 KRangeGT30 matched-exit execution OHLC 補件\n\n"
        f"- authority exact legs：{len(authority)}。\n"
        f"- accepted：{accepted}；official_no_row：{official_no_row}；source_gap：{source_gap}。\n"
        f"- 受影響 frozen event/platform rows：{readiness['affected_event_platform_rows']}。\n"
        "- 每筆 accepted leg 均由 TWSE/TPEx selected ticker-month 官方序列核對 exact date 與 first-post-signal 順序。\n"
        "- 未使用鄰日、last price、adjusted analysis 或 benchmark 替代。\n"
        f"- ready_for_core_full_rechain={str(accepted == 11).lower()}。\n"
        "- ready_for_experiments=false；由 Core 吸收後重鏈。\n"
        "- future_data_violation_count=0。\n",
        encoding="utf-8",
    )

    current_step_path = OUT / "current_step.txt"
    current_step_path.write_text("completed_ready_for_core_absorption\n", encoding="utf-8")

    artifacts = [
        filled_path,
        blocked_path,
        source_manifest_path,
        all_rows_path,
        audit_path,
        readiness_path,
        summary_path,
        current_step_path,
        Path(__file__).resolve(),
        *sorted(raw_dir.glob("*.json")),
    ]
    manifest = {
        "task_id": TASK_ID,
        "generated_at_utc": generated_at,
        "source_scope": "11 exact ticker-month official routes",
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
