from __future__ import annotations

import argparse
import json
from dataclasses import dataclass
from pathlib import Path
from statistics import median


@dataclass(frozen=True)
class TransitionPolicy:
    """Research-only broad-selloff transition layer for R1.

    It never changes the long-hold target list and never emits an automatic
    order.  Intraday observations are watch signals; only an after-close
    snapshot may become READY_FOR_RYAN_REVIEW.
    """

    index_return_trigger: float = -0.015
    negative_breadth_trigger: float = 0.70
    universe_median_trigger: float = -0.015
    minimum_coverage: float = 0.90


def assess_selloff(
    rows: list[dict],
    *,
    taiex_return: float | None,
    session_complete: bool,
    expected_count: int,
    policy: TransitionPolicy = TransitionPolicy(),
) -> dict:
    usable = [float(row["return"]) for row in rows if row.get("return") is not None]
    coverage = len(usable) / expected_count if expected_count else 0.0
    negative_share = sum(value < 0 for value in usable) / len(usable) if usable else None
    universe_median = median(usable) if usable else None
    coverage_ready = coverage >= policy.minimum_coverage
    index_shock = taiex_return is not None and taiex_return <= policy.index_return_trigger
    breadth_shock = (
        negative_share is not None
        and universe_median is not None
        and negative_share >= policy.negative_breadth_trigger
        and universe_median <= policy.universe_median_trigger
    )
    triggered = coverage_ready and (index_shock or breadth_shock)
    if not coverage_ready:
        status = "DATA_MISSING"
    elif triggered and session_complete:
        status = "READY_FOR_RYAN_REVIEW"
    elif triggered:
        status = "INTRADAY_WATCH_ONLY"
    else:
        status = "NOT_TRIGGERED"
    return {
        "status": status,
        "triggered": triggered,
        "session_complete": session_complete,
        "coverage": coverage,
        "negative_share": negative_share,
        "universe_median_return": universe_median,
        "taiex_return": taiex_return,
        "automatic_trade_allowed": False,
        "formal_model_changed": False,
        "trade_decision_changed": False,
        "active_in_trade_decision": False,
        "report_changed": False,
    }


def classify_candidate(row: dict, *, target_tickers: set[str]) -> dict:
    """Separate a discounted candidate from an unverified falling knife."""
    ticker = str(row.get("ticker", "")).zfill(4)
    missing = [
        field for field in ("risk_gate", "financial_status", "catalyst_state")
        if row.get(field) in {None, "", "DATA_MISSING"}
    ]
    if missing:
        state = "DATA_NOT_READY"
    elif row.get("risk_gate") == "FAIL" or row.get("financial_status") != "READY":
        state = "BLOCKED"
    elif row.get("catalyst_state") != "POSITIVE":
        state = "WATCH_ONLY"
    else:
        state = "ELIGIBLE_FOR_RYAN_REVIEW"
    return {
        "ticker": ticker,
        "is_long_term_target": ticker in target_tickers,
        "state": state,
        "missing_fields": missing,
        "automatic_trade_allowed": False,
    }


def materialize(*, market_path: str | Path, output_path: str | Path) -> dict:
    market = json.loads(Path(market_path).read_text(encoding="utf-8"))
    result = assess_selloff(
        [{"return": row.get("daily_return")} for row in market.get("rows", [])],
        taiex_return=None,
        session_complete=True,
        expected_count=int(market.get("requested_ticker_count", 0)),
    )
    payload = {
        "model": "R1",
        "layer": "broad_selloff_transition_v0.1",
        "date": market.get("date"),
        **result,
        "note": "after-close pool breadth only; index input is not yet part of the official daily snapshot",
    }
    target = Path(output_path)
    target.parent.mkdir(parents=True, exist_ok=True)
    target.write_text(json.dumps(payload, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    return payload


def main() -> None:
    parser = argparse.ArgumentParser(description="Materialize R1 research-only broad-selloff layer.")
    parser.add_argument("--market", default="data/r1/daily_market_latest.json")
    parser.add_argument("--output", default="data/r1/transition/latest.json")
    args = parser.parse_args()
    payload = materialize(market_path=args.market, output_path=args.output)
    print(json.dumps({"date": payload["date"], "status": payload["status"]}, ensure_ascii=False))


if __name__ == "__main__":
    main()
