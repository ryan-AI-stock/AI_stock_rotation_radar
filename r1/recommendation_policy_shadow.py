from __future__ import annotations

import argparse
import json
from pathlib import Path
from typing import Any

from .recommendations import build_recommendations


# One-factor neighbours around the approved conservative baseline.  This is a
# forward diagnostic, not a parameter search and never changes the Dashboard.
PROFILES = (
    ("baseline", 10.0, 40.0, 50.0),
    ("gap_08", 8.0, 40.0, 50.0),
    ("gap_12", 12.0, 40.0, 50.0),
    ("weak_35", 10.0, 35.0, 50.0),
    ("weak_45", 10.0, 45.0, 50.0),
    ("healthy_45", 10.0, 40.0, 45.0),
    ("healthy_55", 10.0, 40.0, 55.0),
)


def build_shadow(*, as_of_date: str, v05: dict[str, Any], actual: dict[str, Any],
                 themes: dict[str, Any], existing: dict[str, Any] | None = None) -> dict[str, Any]:
    candidates = [{
        "ticker": str(row.get("ticker", "")).zfill(4),
        "company": row.get("company", ""),
        "score": row.get("v05_total_score"),
        "target_upside": None,
        "price_chip_risk": row.get("price_chip_risk"),
        "theme_momentum_and_catalyst": row.get("theme_momentum_and_catalyst"),
        "official_negative_flags": row.get("official_negative_flags", []),
        "overlay_missing_components": row.get("v05_target_overlay_missing_components", []),
        "reason": row.get("v05_reason", ""),
    } for row in v05.get("rows", [])]
    held = {
        str(row.get("ticker", "")).zfill(4) for row in actual.get("positions", [])
        if float(row.get("shares") or 0) > 0
    }
    targets = {str(value).zfill(4) for value in themes.get("target_portfolio_6m", [])}
    rows = [row for row in (existing or {}).get("rows", []) if row.get("date") != as_of_date]
    for profile, gap, weak, healthy in PROFILES:
        decisions = build_recommendations(
            date=as_of_date, candidates=candidates, held_tickers=held,
            target_tickers=targets, minimum_score_advantage=gap,
            incumbent_weak_threshold=weak, challenger_healthy_threshold=healthy,
        )
        actionable = [row for row in decisions if row.get("action") == "REVIEW_SWITCH_IN"]
        rows.append({
            "date": as_of_date,
            "profile": profile,
            "minimum_score_advantage": gap,
            "incumbent_weak_threshold": weak,
            "challenger_healthy_threshold": healthy,
            "decision_count": len(actionable),
            "decision_signature": sorted(
                f"{row.get('source_ticker')}->{row.get('target_ticker')}" for row in actionable
            ),
            "status": "SHADOW_ONLY",
        })
    rows.sort(key=lambda row: (row["date"], row["profile"]))
    return {
        "model": "R1 recommendation policy forward shadow",
        "as_of_date": as_of_date,
        "profiles": len(PROFILES),
        "minimum_evaluation_days": 60,
        "selection_policy": "do not select a winner before 60 Taiwan trading-day observations; prefer stable neighbourhood, not maximum return",
        "rows": rows,
        "formal_model_changed": False,
        "trade_decision_changed": False,
        "active_in_trade_decision": False,
        "report_changed": False,
    }


def main() -> None:
    parser = argparse.ArgumentParser(description="Append R1 recommendation threshold shadow observations.")
    parser.add_argument("--date", required=True)
    parser.add_argument("--v05", default="data/r1/v05/latest.json")
    parser.add_argument("--actual", default="data/r1/actual_account_state.json")
    parser.add_argument("--themes", default="config/r1_v02_themes.json")
    parser.add_argument("--output", default="data/r1/recommendation_policy_shadow.json")
    args = parser.parse_args()
    output = Path(args.output)
    existing = json.loads(output.read_text(encoding="utf-8")) if output.exists() else {}
    payload = build_shadow(
        as_of_date=args.date,
        v05=json.loads(Path(args.v05).read_text(encoding="utf-8")),
        actual=json.loads(Path(args.actual).read_text(encoding="utf-8")),
        themes=json.loads(Path(args.themes).read_text(encoding="utf-8")),
        existing=existing,
    )
    output.parent.mkdir(parents=True, exist_ok=True)
    output.write_text(json.dumps(payload, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    print(json.dumps({"date": args.date, "profiles": payload["profiles"]}, ensure_ascii=False))


if __name__ == "__main__":
    main()
