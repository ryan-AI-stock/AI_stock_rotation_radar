from __future__ import annotations

import json
import math
from pathlib import Path
from typing import Any


LINES = ("ACTUAL", "00631L_BUY_HOLD")


def _benchmark_reconciliation_gaps(config: dict[str, Any], flows: list[dict[str, Any]]) -> list[str]:
    """Validate whole-share benchmark purchases when the cost inputs are available."""
    all_in = config.get("benchmarks", {}).get(
        "00631l_buy_hold", config.get("benchmark_00631l_all_in", {})
    )
    seed = config.get("common_starting_nav")
    slippage = all_in.get("buy_slippage_rate")
    fee = all_in.get("buy_fee_rate")
    gaps: list[str] = []
    if not all(isinstance(value, (int, float)) for value in (slippage, fee)):
        return gaps

    def validate(label: str, amount: Any, raw_close: Any, shares: Any, cash: Any) -> None:
        if not all(isinstance(value, (int, float)) for value in (amount, raw_close, shares, cash)):
            gaps.append(f"{label}:缺少金額、收盤價、股數或餘現金")
            return
        unit_cost = float(raw_close) * (1 + float(slippage)) * (1 + float(fee))
        expected_shares = math.floor(float(amount) / unit_cost)
        expected_cash = float(amount) - expected_shares * unit_cost
        if int(shares) != expected_shares or abs(float(cash) - expected_cash) > 0.02:
            gaps.append(
                f"{label}:應為{expected_shares}股、餘現金{expected_cash:.2f}，"
                f"實際填列{int(shares)}股、{float(cash):.2f}"
            )

    validate(
        "2026-08-05起始投入", seed, all_in.get("start_raw_close"),
        all_in.get("shares"), all_in.get("cash", 0),
    )
    for flow in flows:
        validate(
            str(flow.get("date", "日期不明")), flow.get("amount"), flow.get("official_raw_close"),
            flow.get("shares"), flow.get("cash_remainder", 0),
        )
    return gaps


def build_comparison(*, date: str, market: dict[str, Any], benchmark_config: dict[str, Any],
                     actual_snapshot: dict[str, Any] | None = None) -> dict[str, Any]:
    """Build strict same-seed comparison rows; unresolved seed never becomes a return."""
    closes = {str(row["ticker"]).zfill(4): row.get("raw_close") for row in market.get("rows", [])}
    actual_snapshot = actual_snapshot or {}
    rows: list[dict[str, Any]] = []
    seed = benchmark_config.get("common_starting_nav")
    seed_ready = isinstance(seed, (int, float)) and seed > 0
    flows = [
        flow for flow in benchmark_config.get("external_cash_flows", [])
        if str(flow.get("date", "")) <= date and isinstance(flow.get("amount"), (int, float))
    ]
    external_cash_flow = sum(float(flow["amount"]) for flow in flows)
    contributed_capital = float(seed) + external_cash_flow if seed_ready else seed
    added_shares = sum(int(flow.get("shares", 0)) for flow in flows)
    added_cash = sum(float(flow.get("cash_remainder", 0) or 0) for flow in flows)

    actual_nav = actual_snapshot.get("comparison_nav", actual_snapshot.get("nav"))
    actual_equity = actual_snapshot.get("comparison_equity_market_value", actual_snapshot.get("equity_market_value"))
    actual_ready = seed_ready and isinstance(actual_nav, (int, float))
    holding_gap = next((gap.get("amount") for gap in actual_snapshot.get("gaps", [])
                        if gap.get("reason") == "BROKER_TOTAL_EXCEEDS_VISIBLE_POSITION_DETAILS"), None)
    rows.append(_row(date, "ACTUAL", actual_nav, contributed_capital, actual_ready,
                     "實際成交帳本與現金已對帳" if actual_ready else
                     f"券商股票市值已確認；截圖可見持股明細仍差 {holding_gap:,.2f} 元，現金亦待對帳"
                     if isinstance(holding_gap, (int, float)) else
                     f"已確認股票市值 {actual_equity:,.1f} 元；現金與完整交易帳本尚待對帳"
                     if isinstance(actual_equity, (int, float)) else "實際交易／現金或共同起始NAV尚未完整對帳"))
    rows[-1]["equity_market_value"] = actual_equity
    rows[-1]["external_cash_flow"] = external_cash_flow

    all_in = benchmark_config.get("benchmarks", {}).get(
        "00631l_buy_hold", benchmark_config.get("benchmark_00631l_all_in", {})
    )
    reconciliation_gaps = _benchmark_reconciliation_gaps(benchmark_config, flows)
    units = all_in.get("shares")
    cash = all_in.get("cash", 0)
    if isinstance(units, (int, float)):
        units += added_shares
    cash = float(cash or 0) + added_cash
    close = closes.get("00631")
    nav = units * close + cash if isinstance(units, (int, float)) and close is not None else None
    ready = seed_ready and nav is not None and all_in.get("status") == "READY" and not reconciliation_gaps
    rows.append(_row(date, "00631L_BUY_HOLD", nav, contributed_capital, ready,
                     "00631L股數／起始餘現金已對帳" if ready else
                     "；".join(reconciliation_gaps) if reconciliation_gaps else
                     "8/5轉入00631L的精確股數與餘現金尚未對帳"))
    rows[-1]["external_cash_flow"] = external_cash_flow

    base = next((row["return_pct"] for row in rows if row["line"] == "00631L_BUY_HOLD"), None)
    for row in rows:
        row["excess_vs_00631l"] = (
            row["return_pct"] - base if row["return_pct"] is not None and base is not None else None
        )
    return {
        "date": date, "rows": rows,
        "comparison_ready": all(r["status"] == "READY" for r in rows),
        "benchmark_reconciliation_gaps": reconciliation_gaps,
    }


def _row(date: str, line: str, nav: Any, seed: Any, ready: bool, note: str) -> dict[str, Any]:
    return {
        "date": date, "line": line, "nav": nav, "starting_nav": seed,
        "external_cash_flow": None,
        "return_pct": (nav / seed - 1) if ready else None,
        "excess_vs_00631l": None, "status": "READY" if ready else "SEED_RECONCILIATION_REQUIRED",
        "source_note": note,
    }


def load_json(path: str | Path) -> dict[str, Any]:
    return json.loads(Path(path).read_text(encoding="utf-8"))
