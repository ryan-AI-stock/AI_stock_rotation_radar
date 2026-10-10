from __future__ import annotations

import json
from pathlib import Path
from typing import Any


LINES = ("ACTUAL", "00631L_BUY_HOLD", "ORIGINAL_HOLD")


def build_comparison(*, date: str, market: dict[str, Any], benchmark_config: dict[str, Any],
                     actual_snapshot: dict[str, Any] | None = None) -> dict[str, Any]:
    """Build strict same-seed comparison rows; unresolved seed never becomes a return."""
    closes = {str(row["ticker"]).zfill(4): row.get("raw_close") for row in market.get("rows", [])}
    actual_snapshot = actual_snapshot or {}
    rows: list[dict[str, Any]] = []
    seed = benchmark_config.get("common_starting_nav")
    seed_ready = isinstance(seed, (int, float)) and seed > 0

    actual_nav = actual_snapshot.get("nav")
    actual_ready = seed_ready and isinstance(actual_nav, (int, float))
    rows.append(_row(date, "ACTUAL", actual_nav, seed, actual_ready,
                     "實際成交帳本與現金已對帳" if actual_ready else "實際交易／現金或共同起始NAV尚未完整對帳"))

    all_in = benchmark_config.get("benchmarks", {}).get(
        "00631l_buy_hold", benchmark_config.get("benchmark_00631l_all_in", {})
    )
    units = all_in.get("shares")
    cash = all_in.get("cash", 0)
    close = closes.get("00631")
    nav = units * close + cash if isinstance(units, (int, float)) and close is not None else None
    ready = seed_ready and nav is not None and all_in.get("status") == "READY"
    rows.append(_row(date, "00631L_BUY_HOLD", nav, seed, ready,
                     "00631L股數／起始餘現金已對帳" if ready else "8/5轉入00631L的精確股數與餘現金尚未對帳"))

    original = benchmark_config.get("benchmarks", {}).get(
        "original_hold", benchmark_config.get("benchmark_original_holdings", {})
    )
    positions = original.get("positions", original.get("known_positions", []))
    nav = 0.0
    complete = bool(positions)
    for position in positions:
        ticker = str(position.get("ticker", "")).replace("L", "").zfill(5 if str(position.get("ticker", "")).startswith("0") else 4)
        px = closes.get(ticker)
        shares = position.get("shares")
        if px is None or not isinstance(shares, (int, float)):
            complete = False
            break
        nav += shares * px
    if complete:
        nav += float(original.get("cash", 0) or 0)
    else:
        nav = None
    ready = seed_ready and complete and original.get("status") == "READY"
    rows.append(_row(date, "ORIGINAL_HOLD", nav, seed, ready,
                     "8/5原持股股數與餘現金已對帳" if ready else "8/5原持股或餘現金尚未完整對帳"))

    base = next((row["return_pct"] for row in rows if row["line"] == "00631L_BUY_HOLD"), None)
    for row in rows:
        row["excess_vs_00631l"] = (
            row["return_pct"] - base if row["return_pct"] is not None and base is not None else None
        )
    return {"date": date, "rows": rows, "comparison_ready": all(r["status"] == "READY" for r in rows)}


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
