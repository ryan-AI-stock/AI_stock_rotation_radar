from __future__ import annotations

import argparse
import json
from datetime import date
from pathlib import Path
from typing import Any

from r1.catalyst_evidence import load_catalyst_evidence
from r1.config import R1Config


def _active_events(*, as_of_date: str, evidence_path: str | Path,
                   event_policy: dict[str, Any]) -> tuple[list, list[dict[str, str]]]:
    events, rejected = load_catalyst_evidence(evidence_path, as_of_date=as_of_date)
    current = date.fromisoformat(as_of_date)
    active = []
    for event in events:
        policy = event_policy.get(event.event_type)
        if not policy:
            continue
        age_days = (current - date.fromisoformat(event.event_date)).days
        if 0 <= age_days <= int(policy["expiry_weeks"]) * 7:
            active.append(event)
    return active, rejected


def build_context_layer(*, as_of_date: str, config_path: str | Path,
                        catalyst_evidence_path: str | Path,
                        negative_path: str | Path, market_path: str | Path,
                        monthly_revenue_path: str | Path,
                        transition_path: str | Path) -> dict[str, Any]:
    """Translate verified events and current context into advisory-only states.

    This layer never changes the R1 score or emits a trade.  It makes the
    evidence-to-judgement path explicit and auditable for the human decision.
    """
    config = R1Config.load(config_path)
    events, rejected = _active_events(
        as_of_date=as_of_date, evidence_path=catalyst_evidence_path,
        event_policy=config.score_policy["catalyst"]["event_policy"],
    )
    negative = json.loads(Path(negative_path).read_text(encoding="utf-8"))
    market = json.loads(Path(market_path).read_text(encoding="utf-8"))
    monthly = json.loads(Path(monthly_revenue_path).read_text(encoding="utf-8"))
    transition = json.loads(Path(transition_path).read_text(encoding="utf-8")) \
        if Path(transition_path).exists() else {}
    for label, payload in (("negative", negative), ("market", market), ("monthly", monthly)):
        payload_date = payload.get("date") or payload.get("as_of_date")
        if not payload_date:
            raise ValueError(f"context layer {label} has no source date")
        if payload_date > as_of_date:
            raise ValueError(f"context layer {label} uses future data: {payload_date} > {as_of_date}")
        # Price context must describe this trading session.  Weekly/quarterly
        # fundamental evidence remains valid until its next scheduled refresh.
        if label == "market" and payload_date != as_of_date:
            raise ValueError(f"context layer market date mismatch: {payload_date} != {as_of_date}")

    market_rows = {str(row.get("ticker", "")).zfill(4): row for row in market.get("rows", [])}
    monthly_rows = {str(row.get("ticker", "")).zfill(4): row for row in monthly.get("rows", [])}
    official_negative: dict[str, list[dict[str, Any]]] = {}
    for row in negative.get("rows", []):
        official_negative.setdefault(str(row.get("ticker", "")).zfill(4), []).append(row)
    by_ticker: dict[str, list] = {}
    for event in events:
        by_ticker.setdefault(event.ticker, []).append(event)

    broad_selloff = bool(
        transition.get("date") == as_of_date and transition.get("triggered")
        and transition.get("session_complete")
    )
    rows = []
    for security in config.securities:
        ticker = security.ticker
        ticker_events = by_ticker.get(ticker, [])
        positive = [event for event in ticker_events if event.impact_direction == "UP"]
        negative_events = [event for event in ticker_events if event.impact_direction == "DOWN"]
        positive_families = {event.source_family for event in positive}
        negative_families = {event.source_family for event in negative_events}
        positive_confirmed = len(positive_families) >= 2 and any(event.source_tier <= 2 for event in positive)
        negative_confirmed = len(negative_families) >= 2 and any(event.source_tier <= 2 for event in negative_events)
        official_flags = official_negative.get(ticker, [])
        revenue_accelerating = monthly_rows.get(ticker, {}).get("state") == "ACCELERATING"
        market_row = market_rows.get(ticker, {})
        price_weak = any(
            isinstance(market_row.get(field), (int, float)) and float(market_row[field]) < 0
            for field in ("daily_return", "return_1w", "return_1m")
        )

        if official_flags and negative_confirmed:
            state, posture = "THESIS_RISK_CONFIRMED", "PRIORITIZE_REPLACEMENT_REVIEW"
        elif official_flags:
            state, posture = "FUNDAMENTAL_RISK_REVIEW", "HOLD_OR_REDUCE_REVIEW"
        elif positive_confirmed and negative_confirmed:
            state, posture = "MIXED_EVIDENCE", "HOLD_AND_WAIT_FOR_CONFIRMATION"
        elif negative_confirmed and price_weak and not broad_selloff:
            state, posture = "MARKET_CONFIRMED_NEGATIVE", "RISK_REVIEW_NO_AUTO_SELL"
        elif broad_selloff and price_weak:
            state, posture = "MARKET_WIDE_SELLOFF", "PULLBACK_WATCH_NO_AUTO_BUY"
        elif positive_confirmed and revenue_accelerating:
            state, posture = "POSITIVE_FUNDAMENTAL_CONFIRMED", "ACCUMULATION_CANDIDATE_REVIEW"
        elif positive_confirmed:
            state, posture = "POSITIVE_EVENT_WATCH", "WATCH_FOR_FUNDAMENTAL_CONFIRMATION"
        else:
            state, posture = "NO_CONTEXT_CHANGE", "KEEP_EXISTING_PLAN"

        rows.append({
            "ticker": ticker, "company": security.company,
            "context_state": state, "advisory_posture": posture,
            "broad_selloff": broad_selloff, "price_weak": price_weak,
            "monthly_revenue_state": monthly_rows.get(ticker, {}).get("state", "DATA_MISSING"),
            "positive_event_count": len(positive), "negative_event_count": len(negative_events),
            "positive_source_families": sorted(positive_families),
            "negative_source_families": sorted(negative_families),
            "official_negative_event_types": sorted({row["event_type"] for row in official_flags}),
            "evidence_urls": sorted({event.source_url for event in ticker_events}
                                    | {row["source_url"] for row in official_flags}),
        })
    return {
        "model": "R1", "layer": "context_event_v0.1", "date": as_of_date,
        "status": "READY", "rows": rows,
        "broad_selloff": broad_selloff,
        "rejected_evidence": rejected,
        "pit_future_rows_excluded": sum(item.get("error") == "future_data" for item in rejected),
        "future_data_violation_count": 0,
        "decision_boundary": "report-only; no score change; no automatic trade",
        "formal_model_changed": False, "trade_decision_changed": False,
        "active_in_trade_decision": False, "report_changed": True,
    }


def main() -> None:
    parser = argparse.ArgumentParser(description="Build R1 evidence-backed context judgement layer.")
    parser.add_argument("--date", required=True)
    parser.add_argument("--config", default="config/r1.json")
    parser.add_argument("--catalyst-evidence", default="data/r1/catalyst_events/evidence.csv")
    parser.add_argument("--negative", default="data/r1/official_negative_evidence.json")
    parser.add_argument("--market", default="data/r1/daily_market_latest.json")
    parser.add_argument("--monthly-revenue", default="data/r1/monthly_revenue/latest.json")
    parser.add_argument("--transition", default="data/r1/transition/latest.json")
    parser.add_argument("--output", default="data/r1/context_event_latest.json")
    args = parser.parse_args()
    payload = build_context_layer(
        as_of_date=args.date, config_path=args.config,
        catalyst_evidence_path=args.catalyst_evidence, negative_path=args.negative,
        market_path=args.market, monthly_revenue_path=args.monthly_revenue,
        transition_path=args.transition,
    )
    output = Path(args.output)
    output.parent.mkdir(parents=True, exist_ok=True)
    output.write_text(json.dumps(payload, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    print(json.dumps({"date": args.date, "rows": len(payload["rows"]), "status": payload["status"]}))


if __name__ == "__main__":
    main()
