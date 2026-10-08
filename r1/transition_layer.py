from __future__ import annotations

import argparse
import json
from dataclasses import dataclass
from pathlib import Path
from statistics import median

import pandas as pd

from rotation_radar.v4d_top1_daily_report import load_taiex_history


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


def select_transition_candidates(*, market_rows: list[dict], active_pool_rows: list[dict],
                                 priority_by_ticker: dict[str, float | None],
                                 target_tickers: set[str], limit: int = 3) -> list[dict]:
    market = {str(row.get("ticker", "")).zfill(4): row for row in market_rows}
    candidates = []
    for active in active_pool_rows:
        ticker = str(active.get("ticker", "")).zfill(4)
        price = market.get(ticker)
        if not active.get("active_pool_eligible") or not price:
            continue
        daily_return = price.get("daily_return")
        bias20 = price.get("bias20")
        priority = priority_by_ticker.get(ticker)
        if daily_return is None or bias20 is None or priority is None or float(daily_return) >= 0:
            continue
        candidates.append({
            "ticker": ticker,
            "company": price.get("company") or active.get("company"),
            "is_long_term_target": ticker in target_tickers,
            "priority_score": float(priority),
            "daily_return": float(daily_return),
            "bias20": float(bias20),
            "state": "ELIGIBLE_FOR_RYAN_REVIEW",
            "automatic_trade_allowed": False,
        })
    return sorted(
        candidates,
        key=lambda row: (-row["priority_score"], row["bias20"], row["daily_return"], row["ticker"]),
    )[:limit]


def taiex_return_from_history(history: pd.DataFrame, *, target: str) -> float:
    frame = history.copy()
    frame["date"] = pd.to_datetime(frame["date"])
    frame = frame.loc[frame["date"].le(pd.Timestamp(target))].sort_values("date")
    if len(frame) < 2 or frame.iloc[-1]["date"] != pd.Timestamp(target):
        raise ValueError("TAIEX exact target close and prior close are required")
    return float(frame.iloc[-1]["close"] / frame.iloc[-2]["close"] - 1)


def materialize(*, market_path: str | Path, output_path: str | Path,
                source_cache: str | Path = "data/current_base_cycle_source_cache",
                offline: bool = False,
                active_pool_path: str | Path = "data/r1/active_pool/latest.json",
                theme_review_path: str | Path = "data/r1/theme_reviews/latest.json",
                theme_path: str | Path = "config/r1_v02_themes.json") -> dict:
    market = json.loads(Path(market_path).read_text(encoding="utf-8"))
    target_date = str(market.get("date"))
    taiex_history = load_taiex_history(
        target=pd.Timestamp(target_date), source_cache=Path(source_cache), offline=offline,
    )
    taiex_return = taiex_return_from_history(taiex_history, target=target_date)
    result = assess_selloff(
        [{"return": row.get("daily_return")} for row in market.get("rows", [])],
        taiex_return=taiex_return,
        session_complete=True,
        expected_count=int(market.get("requested_ticker_count", 0)),
    )
    active_file = Path(active_pool_path)
    review_file = Path(theme_review_path)
    themes_file = Path(theme_path)
    active = json.loads(active_file.read_text(encoding="utf-8")) if active_file.exists() else {}
    review = json.loads(review_file.read_text(encoding="utf-8")) if review_file.exists() else {}
    theme_config = json.loads(themes_file.read_text(encoding="utf-8"))
    priority_by_ticker = {
        str(item.get("ticker", "")).zfill(4): item.get("priority_score")
        for theme in review.get("themes", []) for item in theme.get("top3", [])
    }
    active_date = active.get("date")
    active_fresh = bool(
        active_date and 0 <= (pd.Timestamp(target_date) - pd.Timestamp(active_date)).days <= 7
    )
    candidates = select_transition_candidates(
        market_rows=market.get("rows", []),
        active_pool_rows=active.get("rows", []) if active_fresh and result["triggered"] else [],
        priority_by_ticker=priority_by_ticker,
        target_tickers={str(ticker).zfill(4) for ticker in theme_config.get("target_portfolio_6m", [])},
    )
    if not result["triggered"]:
        candidate_status = "NOT_TRIGGERED"
    elif not active_fresh:
        candidate_status = "DATA_NOT_READY_ACTIVE_POOL_STALE_OR_MISSING"
    elif not candidates:
        candidate_status = "DATA_NOT_READY_OR_NO_ELIGIBLE_PULLBACK"
    else:
        candidate_status = "READY_FOR_RYAN_REVIEW"
    payload = {
        "model": "R1",
        "layer": "broad_selloff_transition_v0.1",
        "date": market.get("date"),
        **result,
        "candidate_status": candidate_status,
        "candidate_count": len(candidates),
        "candidates": candidates,
        "active_pool_as_of": active_date,
        "note": "after-close official TAIEX return plus R1-universe breadth; research-only",
    }
    target = Path(output_path)
    target.parent.mkdir(parents=True, exist_ok=True)
    target.write_text(json.dumps(payload, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    return payload


def main() -> None:
    parser = argparse.ArgumentParser(description="Materialize R1 research-only broad-selloff layer.")
    parser.add_argument("--market", default="data/r1/daily_market_latest.json")
    parser.add_argument("--output", default="data/r1/transition/latest.json")
    parser.add_argument("--source-cache", default="data/current_base_cycle_source_cache")
    parser.add_argument("--active-pool", default="data/r1/active_pool/latest.json")
    parser.add_argument("--theme-review", default="data/r1/theme_reviews/latest.json")
    parser.add_argument("--themes", default="config/r1_v02_themes.json")
    parser.add_argument("--offline", action="store_true")
    args = parser.parse_args()
    payload = materialize(
        market_path=args.market, output_path=args.output,
        source_cache=args.source_cache, offline=args.offline,
        active_pool_path=args.active_pool, theme_review_path=args.theme_review,
        theme_path=args.themes,
    )
    print(json.dumps({"date": payload["date"], "status": payload["status"]}, ensure_ascii=False))


if __name__ == "__main__":
    main()
