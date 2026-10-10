from __future__ import annotations

import argparse
from datetime import date, timedelta
import json
from pathlib import Path
from typing import Any


WEIGHTS = {
    "structural_bottleneck": 0.20,
    "revenue_earnings_realization": 0.20,
    "consensus_target_upside": 0.20,
    "target_revision_and_breadth": 0.10,
    "theme_momentum_and_catalyst": 0.10,
    "relative_valuation": 0.10,
    "price_chip_risk": 0.10,
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
                   prior_target_prices: dict[str, Any] | None = None) -> dict[str, Any]:
    weekly_rows = {str(row.get("ticker", "")).zfill(4): row for row in weekly.get("rows", [])}
    targets = {str(row.get("ticker", "")).zfill(4): row for row in target_prices.get("rows", [])}
    priors = {
        str(row.get("ticker", "")).zfill(4): row
        for row in (prior_target_prices or {}).get("rows", [])
    }
    growth_percentiles = _percentile_scores({
        ticker: float(row["next_year_eps_growth"])
        for ticker, row in weekly_rows.items() if row.get("next_year_eps_growth") is not None
    })
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
        realization = None
        if ticker in growth_percentiles and ticker in revenue_percentiles:
            realization = round((growth_percentiles[ticker] + revenue_percentiles[ticker]) / 2, 6)
        components = {
            "structural_bottleneck": weekly_row.get("bottleneck_score"),
            "revenue_earnings_realization": realization,
            "consensus_target_upside": (
                _upside_score(target["consensus_upside"])
                if target.get("scoreable") and target.get("consensus_upside") is not None else None
            ),
            "target_revision_and_breadth": _revision_breadth_score(target, priors.get(ticker)),
            "theme_momentum_and_catalyst": weekly_row.get("catalyst_score"),
            "relative_valuation": weekly_row.get("valuation_score"),
            "price_chip_risk": weekly_row.get("price_chip_score"),
        }
        missing = [name for name in WEIGHTS if components.get(name) is None]
        total = None if missing else round(sum(float(components[name]) * WEIGHTS[name] for name in WEIGHTS), 6)
        rows.append({
            "date": as_of_date,
            "ticker": ticker,
            "company": weekly_row.get("company", ""),
            **components,
            "v05_total_score": total,
            "v05_status": "READY" if total is not None else "DATA_MISSING",
            "v05_missing_components": missing,
            "v05_reason": (
                "七構面完整；僅供Ryan換倉比較，不是成交指令"
                if total is not None else "缺少：" + "、".join(missing)
            ),
        })
    return {
        "model": "R1 v0.5",
        "date": as_of_date,
        "status": "challenger_report_only",
        "rows": rows,
        "requested_ticker_count": len(rows),
        "ready_ticker_count": sum(row["v05_status"] == "READY" for row in rows),
        "missing_value_policy": "NA_BLOCKS_COMPONENT_NO_ZERO_NO_WEIGHT_REDISTRIBUTION",
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
    parser.add_argument("--output", default="data/r1/v05/latest.json")
    args = parser.parse_args()
    weekly = json.loads(_latest_weekly(Path(args.weekly_root), args.date).read_text(encoding="utf-8"))
    targets = json.loads(Path(args.target_prices).read_text(encoding="utf-8"))
    monthly_path = Path(args.monthly_revenue)
    monthly = json.loads(monthly_path.read_text(encoding="utf-8")) if monthly_path.exists() else {}
    if monthly.get("date", args.date) > args.date:
        monthly = {}
    prior = _prior_target_snapshot(Path(args.target_history), args.date)
    payload = build_v05_rank(as_of_date=args.date, weekly=weekly, target_prices=targets,
                             monthly_revenue=monthly,
                             prior_target_prices=prior)
    output = Path(args.output)
    output.parent.mkdir(parents=True, exist_ok=True)
    output.write_text(json.dumps(payload, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    print(json.dumps({"date": args.date, "ready": payload["ready_ticker_count"],
                      "requested": payload["requested_ticker_count"]}, ensure_ascii=False))


if __name__ == "__main__":
    main()
