from __future__ import annotations

import argparse
from datetime import date, timedelta
import json
from pathlib import Path
from typing import Any

from .theme_policy import load_themes
from .valuation import load_valuation_reference


CORE_WEIGHTS = {
    "structural_bottleneck": 0.25,
    "revenue_earnings_realization": 0.25,
    "theme_momentum_and_catalyst": 0.15,
    "relative_valuation": 0.15,
    "price_chip_risk": 0.20,
}

TARGET_OVERLAY_WEIGHTS = {
    "consensus_target_upside": 2 / 3,
    "target_revision_and_breadth": 1 / 3,
}


def _percentile_scores(values: dict[str, float]) -> dict[str, float]:
    ordered = sorted((value, ticker) for ticker, value in values.items())
    if not ordered:
        return {}
    if len(ordered) == 1:
        return {ordered[0][1]: 50.0}
    return {
        ticker: round(index / (len(ordered) - 1) * 100, 6)
        for index, (_, ticker) in enumerate(ordered)
    }


def _upside_score(upside: float, floor: float = -0.20, cap: float = 0.80) -> float:
    bounded = min(max(float(upside), floor), cap)
    return round((bounded - floor) / (cap - floor) * 100, 6)


def _relative_valuation_score(percentile: float | None) -> float | None:
    """Convert a stock's PIT five-year valuation percentile into a safety score.

    R1 v0.6 deliberately keeps analyst target prices and EPS forecasts out of
    the public-data core.  A lower own-history valuation percentile therefore
    receives the higher score.  Missing history stays missing.
    """
    if percentile is None:
        return None
    value = float(percentile)
    if not 0.0 <= value <= 1.0:
        return None
    return round((1.0 - value) * 100.0, 6)


def _revision_breadth_score(current: dict[str, Any], prior: dict[str, Any] | None) -> float | None:
    if not current.get("scoreable") or not prior or not prior.get("scoreable"):
        return None
    current_target = current.get("consensus_target_price")
    prior_target = prior.get("consensus_target_price")
    if not current_target or not prior_target:
        return None
    revision = float(current_target) / float(prior_target) - 1
    revision_score = _upside_score(revision, floor=-0.20, cap=0.20)
    breadth_score = min(float(current.get("institution_count") or 0) / 5.0, 1.0) * 100
    return round((revision_score + breadth_score) / 2, 6)


def build_v05_rank(*, as_of_date: str, weekly: dict[str, Any], target_prices: dict[str, Any],
                   monthly_revenue: dict[str, Any] | None = None,
                   prior_target_prices: dict[str, Any] | None = None,
                   theme_review: dict[str, Any] | None = None,
                   valuation_reference: dict[str, dict[str, Any]] | None = None,
                   allowed_tickers: set[str] | None = None) -> dict[str, Any]:
    if target_prices.get("date", as_of_date) > as_of_date:
        target_prices = {"rows": []}
    if (theme_review or {}).get("date", as_of_date) > as_of_date:
        theme_review = {"themes": []}
    weekly_rows = {
        str(row.get("ticker", "")).zfill(4): row
        for row in weekly.get("rows", [])
        if allowed_tickers is None or str(row.get("ticker", "")).zfill(4) in allowed_tickers
    }
    targets = {str(row.get("ticker", "")).zfill(4): row for row in target_prices.get("rows", [])}
    priors = {
        str(row.get("ticker", "")).zfill(4): row
        for row in (prior_target_prices or {}).get("rows", [])
    }
    quarterly_rows: dict[str, dict[str, Any]] = {}
    for theme in (theme_review or {}).get("themes", []):
        for row in theme.get("ranked", []):
            ticker = str(row.get("ticker", "")).zfill(4)
            previous = quarterly_rows.get(ticker)
            if previous is None or float(row.get("bottleneck_directness") or -1) > float(
                    previous.get("bottleneck_directness") or -1):
                quarterly_rows[ticker] = row
    revenue_rows = {
        str(row.get("ticker", "")).zfill(4): row
        for row in (monthly_revenue or {}).get("rows", [])
    }
    revenue_yoy = {}
    for ticker, row in revenue_rows.items():
        observations = row.get("observations") or []
        latest_yoy = observations[-1].get("yoy") if observations else None
        if latest_yoy is not None:
            revenue_yoy[ticker] = float(latest_yoy)
    revenue_percentiles = _percentile_scores(revenue_yoy)
    rows = []
    for ticker, weekly_row in sorted(weekly_rows.items()):
        target = targets.get(ticker, {})
        quarterly = quarterly_rows.get(ticker, {})
        valuation_row = (valuation_reference or {}).get(ticker, {})
        # The free-data core must not fall back to analyst Forward PE when the
        # official own-history valuation series is absent.
        valuation_percentile = valuation_row.get("five_year_percentile")
        valuation_metric = valuation_row.get("valuation_metric")
        realization = None
        if ticker in revenue_percentiles and quarterly.get("financial_earnings_quality") is not None:
            realization = round(
                (revenue_percentiles[ticker] + float(quarterly["financial_earnings_quality"])) / 2, 6
            )
        components = {
            "structural_bottleneck": (
                quarterly.get("bottleneck_directness")
                if quarterly.get("bottleneck_directness") is not None
                else weekly_row.get("bottleneck_score")
            ),
            "revenue_earnings_realization": realization,
            "consensus_target_upside": (
                _upside_score(target["consensus_upside"])
                if target.get("scoreable") and target.get("consensus_upside") is not None else None
            ),
            "target_revision_and_breadth": _revision_breadth_score(target, priors.get(ticker)),
            "theme_momentum_and_catalyst": weekly_row.get("catalyst_score"),
            "relative_valuation": _relative_valuation_score(
                valuation_percentile
            ),
            # Daily current-risk ranking must not wait for 4W/12W EPS-history
            # confirmation.  Keep price_chip_score as a historical diagnostic,
            # while market_risk_score supplies today's observable price/chip risk.
            "price_chip_risk": (
                weekly_row.get("market_risk_score")
                if weekly_row.get("market_risk_score") is not None
                else weekly_row.get("price_chip_score")
            ),
        }
        missing = [name for name in CORE_WEIGHTS if components.get(name) is None]
        overlay_missing = [name for name in TARGET_OVERLAY_WEIGHTS if components.get(name) is None]
        total = None if missing else round(
            sum(float(components[name]) * CORE_WEIGHTS[name] for name in CORE_WEIGHTS), 6
        )
        target_overlay = None if overlay_missing else round(sum(
            float(components[name]) * TARGET_OVERLAY_WEIGHTS[name]
            for name in TARGET_OVERLAY_WEIGHTS
        ), 6)
        observed_weight = round(sum(
            CORE_WEIGHTS[name] for name in CORE_WEIGHTS if components.get(name) is not None
        ), 6)
        observed_points = round(
            sum(float(components[name]) * CORE_WEIGHTS[name]
                for name in CORE_WEIGHTS if components.get(name) is not None), 6
        )
        reference_score = None if observed_weight == 0 else round(observed_points / observed_weight, 6)
        rows.append({
            "date": as_of_date,
            "ticker": ticker,
            "company": weekly_row.get("company", ""),
            **components,
            "relative_valuation_metric": valuation_metric,
            "v05_total_score": total,
            "v05_target_overlay_score": target_overlay,
            "v05_target_overlay_status": "READY" if target_overlay is not None else "DATA_MISSING",
            "v05_target_overlay_missing_components": overlay_missing,
            "v05_observed_points": observed_points,
            "v05_observed_max_points": round(observed_weight * 100, 6),
            "v05_observed_weight": observed_weight,
            "v05_reference_score": reference_score,
            "v05_reference_coverage": observed_weight,
            "v05_status": "READY" if total is not None else "DATA_MISSING",
            "v05_missing_components": missing,
            "v05_reason": (
                "公開資料核心五構面完整；法人目標價僅作信心加減項；不是成交指令"
                if total is not None else "缺少：" + "、".join(missing)
            ),
        })
    return {
        "model": "R1 v0.6 public-core",
        "date": as_of_date,
        "status": "challenger_report_only",
        "rows": rows,
        "requested_ticker_count": len(rows),
        "ready_ticker_count": sum(row["v05_status"] == "READY" for row in rows),
        "missing_value_policy": "NA blocks the five-component public core without zero fill; target-price fields are a separate confidence overlay and never fabricate missing institutions",
        "core_weights": CORE_WEIGHTS,
        "target_overlay_weights": TARGET_OVERLAY_WEIGHTS,
        "realization_policy": "official monthly-revenue YoY cross-section plus latest PIT official financial-quality score; analyst EPS is not substituted for realized earnings",
        "price_chip_policy": "explicit free-data weights: overheat safety 50%, institutional flow 33.33%, leverage structure 16.67%; all three required; 4W/12W EPS-price history is confidence-only",
        "future_data_violation_count": 0,
        "formal_model_changed": False,
        "trade_decision_changed": False,
        "active_in_trade_decision": False,
        "report_changed": True,
    }


def _latest_weekly(root: Path, as_of_date: str) -> Path:
    files = sorted(path for path in root.glob("weekly_snapshot_????-??-??.json") if path.stem[-10:] <= as_of_date)
    if not files:
        raise FileNotFoundError("no R1 weekly snapshot on or before target date")
    return files[-1]


def _prior_target_snapshot(root: Path, as_of_date: str) -> dict[str, Any] | None:
    cutoff = (date.fromisoformat(as_of_date) - timedelta(days=28)).isoformat()
    files = sorted(path for path in root.glob("????-??-??.json") if path.stem <= cutoff)
    return json.loads(files[-1].read_text(encoding="utf-8")) if files else None


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--date", required=True)
    parser.add_argument("--weekly-root", default="data/r1/weekly")
    parser.add_argument("--target-prices", default="data/r1/target_prices/latest.json")
    parser.add_argument("--target-history", default="data/r1/target_prices/history")
    parser.add_argument("--monthly-revenue", default="data/r1/monthly_revenue/latest.json")
    parser.add_argument("--themes", default="config/r1_v02_themes.json")
    parser.add_argument("--theme-review", default="data/r1/theme_reviews/latest.json")
    parser.add_argument("--valuation-reference", default="data/r1/valuation_reference.csv")
    parser.add_argument("--output", default="data/r1/v05/latest.json")
    args = parser.parse_args()
    weekly = json.loads(_latest_weekly(Path(args.weekly_root), args.date).read_text(encoding="utf-8"))
    targets = json.loads(Path(args.target_prices).read_text(encoding="utf-8"))
    monthly_path = Path(args.monthly_revenue)
    monthly = json.loads(monthly_path.read_text(encoding="utf-8")) if monthly_path.exists() else {}
    if monthly.get("date", args.date) > args.date:
        monthly = {}
    prior = _prior_target_snapshot(Path(args.target_history), args.date)
    theme_review_path = Path(args.theme_review)
    theme_review = json.loads(theme_review_path.read_text(encoding="utf-8")) \
        if theme_review_path.exists() else {}
    allowed_tickers = {
        member.ticker
        for theme in load_themes(args.themes)
        for member in theme.members
    }
    payload = build_v05_rank(as_of_date=args.date, weekly=weekly, target_prices=targets,
                             monthly_revenue=monthly,
                             prior_target_prices=prior,
                             theme_review=theme_review,
                             valuation_reference=load_valuation_reference(
                                 args.valuation_reference, as_of_date=args.date,
                             ),
                             allowed_tickers=allowed_tickers)
    output = Path(args.output)
    output.parent.mkdir(parents=True, exist_ok=True)
    output.write_text(json.dumps(payload, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    print(json.dumps({"date": args.date, "ready": payload["ready_ticker_count"],
                      "requested": payload["requested_ticker_count"]}, ensure_ascii=False))


if __name__ == "__main__":
    main()
