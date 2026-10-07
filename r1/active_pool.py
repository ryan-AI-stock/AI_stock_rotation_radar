from __future__ import annotations

import argparse
import json
from datetime import date
from pathlib import Path

from r1.bottleneck_evidence import load_bottleneck_evidence
from r1.catalyst_evidence import load_catalyst_evidence
from r1.price_eps import price_eps_gap
from r1.theme_policy import load_themes


ORDER = {"HIGH": 3, "MEDIUM": 2, "LOW": 1, "DATA_MISSING": 0}
RISK_ORDER = {"PASS": 3, "CAUTION": 2, "DATA_MISSING": 1, "FAIL": 0}
CATCH_UP_ORDER = {
    "POSITIVE_DIVERGENCE": 4, "EARNINGS_LEADS_PRICE": 3, "ALIGNED": 2,
    "INCONCLUSIVE": 1, "DATA_MISSING": 0, "PRICE_LEADS_EARNINGS": -1,
    "NEGATIVE_DIVERGENCE": -2,
}


def estimate_dispersion(*, high: float | None, median: float | None, low: float | None,
                        analyst_count: int | None, minimum_analyst_count: int) -> tuple[float | None, str]:
    if high is None or median in {None, 0} or low is None or analyst_count is None:
        return None, "DATA_MISSING"
    if analyst_count < minimum_analyst_count:
        return None, "LOW_CONFIDENCE"
    return (high - low) / abs(median), "READY"


def dispersion_state(value: float | None, *, medium: float, high: float) -> str:
    if value is None:
        return "DATA_MISSING"
    if value >= high:
        return "HIGH"
    if value >= medium:
        return "MEDIUM"
    return "LOW"


def earnings_visibility(row: dict, policy: dict) -> tuple[str, list[str]]:
    reasons: list[str] = []
    if not row.get("consensus_allowed"):
        return "DATA_MISSING", ["CONSENSUS_NOT_ACTIONABLE"]
    analyst_count = _int(row.get("analyst_count"))
    dispersion, status = estimate_dispersion(
        high=_float(row.get("forward_eps_high")), median=_float(row.get("forward_eps_median")),
        low=_float(row.get("forward_eps_low")), analyst_count=analyst_count,
        minimum_analyst_count=int(policy["estimate_dispersion"]["minimum_analyst_count"]),
    )
    if status != "READY":
        reasons.append("ESTIMATE_DISPERSION_" + status)
    r4 = _float(row.get("eps_revision_4w"))
    r12 = _float(row.get("eps_revision_12w"))
    if r4 is None or r12 is None:
        reasons.append("EPS_REVISION_4W_12W_NOT_MATURE")
        return "DATA_MISSING", reasons
    flat = float(policy["earnings_revision"]["flat_band"])
    if r4 < -flat and r12 < -flat:
        return "LOW", reasons + ["EPS_REVISION_DOWN"]
    dstate = dispersion_state(
        dispersion, medium=float(policy["estimate_dispersion"]["medium"]),
        high=float(policy["estimate_dispersion"]["high"]),
    )
    if r4 > flat and r12 > flat and dstate == "LOW":
        return "HIGH", reasons
    return "MEDIUM", reasons


def catalyst_state(rows: list, *, as_of_date: str, window_days: int) -> tuple[str, int, list[str]]:
    asof = date.fromisoformat(as_of_date)
    recent = [row for row in rows if 0 <= (asof - date.fromisoformat(row.available_at)).days <= window_days]
    if not recent:
        return "DATA_MISSING", 0, ["NO_VERIFIED_EVENT_IN_WINDOW"]
    directions = {row.impact_direction.upper() for row in recent}
    families = {row.source_family for row in recent}
    if "DOWN" in directions and "UP" not in directions:
        state = "NEGATIVE"
    elif "UP" in directions and "DOWN" not in directions:
        state = "POSITIVE"
    else:
        state = "MIXED"
    confidence = "HIGH" if len(families) >= 2 and any(row.source_tier == 1 for row in recent) else "MEDIUM"
    return state, len(recent), [f"CONFIDENCE_{confidence}"]


def bottleneck_scarcity(rows: list, policy: dict) -> tuple[str, list[str]]:
    if not rows:
        return "DATA_MISSING", ["NO_VERIFIED_BOTTLENECK_EVIDENCE"]
    stages = [policy["bottleneck_stage"].get(row.stage, "DATA_MISSING") for row in rows]
    state = max(stages, key=lambda value: ORDER[value])
    families = {row.source_family for row in rows}
    if len(families) < 2 or not any(row.source_tier <= 2 for row in rows):
        return "DATA_MISSING", ["INDEPENDENT_SOURCE_GATE_NOT_MET"]
    return state, [f"EVIDENCE_FAMILIES_{len(families)}"]


def catch_up_state(row: dict) -> tuple[str, dict[str, dict]]:
    windows = {
        "1w": (row.get("return_1w"), row.get("eps_revision_1w")),
        "4w": (row.get("return_1m"), row.get("eps_revision_4w")),
        "12w": (row.get("return_3m"), row.get("eps_revision_12w")),
    }
    details = {}
    states = []
    for label, (price, eps) in windows.items():
        result = price_eps_gap(price_change=_float(price), eps_revision=_float(eps))
        details[label] = {
            "price_change": result.price_change, "eps_revision": result.eps_revision,
            "price_eps_gap": result.earnings_minus_price, "state": result.state,
        }
        states.append(result.state)
    usable = [state for state in states if state != "DATA_MISSING"]
    if not usable:
        return "DATA_MISSING", details
    return max(usable, key=lambda state: CATCH_UP_ORDER[state]), details


def risk_gate(row: dict, *, earnings_state: str, policy: dict,
              financial_status: str = "READY") -> tuple[str, list[str]]:
    reasons: list[str] = []
    r4 = _float(row.get("eps_revision_4w"))
    r12 = _float(row.get("eps_revision_12w"))
    valuation = _float(row.get("forward_pe_percentile_5y"))
    if r4 is not None and r4 <= float(policy["earnings_revision"]["fail_4w"]):
        reasons.append("EPS_4W_MAJOR_DOWNREVISION")
    if r12 is not None and r12 <= float(policy["earnings_revision"]["fail_12w"]):
        reasons.append("EPS_12W_MAJOR_DOWNREVISION")
    if valuation is not None and valuation >= float(policy["valuation"]["extreme_percentile"]) \
            and earnings_state == "LOW":
        reasons.append("EXTREME_VALUATION_WITH_LOW_VISIBILITY")
    if reasons:
        return "FAIL", reasons
    missing = []
    if earnings_state == "DATA_MISSING":
        missing.append("EARNINGS_VISIBILITY_NOT_READY")
    if financial_status != "READY":
        missing.append("OFFICIAL_FINANCIALS_NOT_READY")
    if missing:
        return "DATA_MISSING", missing
    caution = []
    if valuation is not None and valuation >= float(policy["valuation"]["extreme_percentile"]):
        caution.append("EXTREME_OWN_HISTORY_VALUATION")
    if earnings_state == "LOW":
        caution.append("LOW_EARNINGS_VISIBILITY")
    return ("CAUTION", caution) if caution else ("PASS", [])


def materialize(*, as_of_date: str, theme_path: str | Path, weekly_path: str | Path,
                catalyst_path: str | Path, bottleneck_path: str | Path,
                policy_path: str | Path, output_path: str | Path,
                financial_path: str | Path | None = "data/r1/official_financial_latest.json") -> dict:
    policy = json.loads(Path(policy_path).read_text(encoding="utf-8"))
    themes = load_themes(theme_path)
    theme_names: dict[str, list[str]] = {}
    companies: dict[str, str] = {}
    for theme in themes:
        for member in theme.members:
            theme_names.setdefault(member.ticker, []).append(theme.name)
            companies[member.ticker] = member.company
    weekly = json.loads(Path(weekly_path).read_text(encoding="utf-8"))
    if weekly.get("date") != as_of_date:
        raise ValueError("active pool requires exact-date weekly snapshot")
    catalyst_rows, catalyst_rejected = load_catalyst_evidence(catalyst_path, as_of_date=as_of_date)
    bottleneck_rows, bottleneck_rejected = load_bottleneck_evidence(bottleneck_path, as_of_date=as_of_date)
    financial_rows: dict[str, dict] = {}
    if financial_path and Path(financial_path).exists():
        financial_payload = json.loads(Path(financial_path).read_text(encoding="utf-8"))
        financial_rows = {str(row.get("ticker", "")).zfill(4): row for row in financial_payload.get("rows", [])}
    weekly_rows = {str(row.get("ticker", "")).zfill(4): row for row in weekly.get("rows", [])}
    output_rows = []
    for ticker in sorted(theme_names):
        row = weekly_rows.get(ticker, {"ticker": ticker, "company": companies[ticker]})
        visibility, visibility_reasons = earnings_visibility(row, policy)
        catalysts = [item for item in catalyst_rows if item.ticker == ticker]
        catalyst, event_count, catalyst_reasons = catalyst_state(
            catalysts, as_of_date=as_of_date,
            window_days=int(policy["catalyst_window_calendar_days"]),
        )
        bottlenecks = [item for item in bottleneck_rows if item.ticker == ticker]
        scarcity, scarcity_reasons = bottleneck_scarcity(bottlenecks, policy)
        catchup, catchup_details = catch_up_state(row)
        financial_status = financial_rows.get(ticker, {}).get("status", "DATA_MISSING")
        gate, gate_reasons = risk_gate(
            row, earnings_state=visibility, policy=policy, financial_status=financial_status,
        )
        confidence_inputs = [visibility, scarcity, catchup, gate]
        confidence = "HIGH" if all(value not in {"DATA_MISSING", "LOW"} for value in confidence_inputs) \
            else "LOW_CONFIDENCE"
        eligible = (
            visibility in {"HIGH", "MEDIUM"}
            and scarcity in {"HIGH", "MEDIUM"}
            and catalyst == "POSITIVE"
            and catchup in {"POSITIVE_DIVERGENCE", "EARNINGS_LEADS_PRICE", "ALIGNED"}
            and gate in {"PASS", "CAUTION"}
            and confidence == "HIGH"
        )
        output_rows.append({
            "date": as_of_date, "ticker": ticker, "company": row.get("company"),
            "themes": theme_names.get(ticker, []), "active_pool_eligible": eligible,
            "active_pool_rank": None,
            "one_month_catalyst_state": catalyst, "recent_catalyst_event_count": event_count,
            "six_month_earnings_visibility": visibility,
            "bottleneck_scarcity": scarcity, "price_catch_up": catchup,
            "six_month_risk_gate": gate, "data_confidence": confidence,
            "weekly_snapshot_status": "READY" if ticker in weekly_rows else "DATA_MISSING",
            "official_financial_status": financial_status,
            "catch_up_details": catchup_details,
            "reasons": visibility_reasons + catalyst_reasons + scarcity_reasons + gate_reasons,
        })
    ranked = sorted(
        (row for row in output_rows if row["active_pool_eligible"]),
        key=lambda row: (
            -RISK_ORDER[row["six_month_risk_gate"]],
            -ORDER[row["six_month_earnings_visibility"]],
            -ORDER[row["bottleneck_scarcity"]],
            -CATCH_UP_ORDER[row["price_catch_up"]], row["ticker"],
        ),
    )
    maximum = int(policy["target_pool_size"]["maximum"])
    selected = ranked[:maximum]
    for index, row in enumerate(selected, start=1):
        row["active_pool_rank"] = index
    selected_tickers = {row["ticker"] for row in selected}
    payload = {
        "model": "R1", "version": policy["version"], "date": as_of_date,
        "structural_universe_count": len(theme_names),
        "weekly_snapshot_coverage": {"actual": len(weekly_rows), "requested": len(theme_names)},
        "official_financial_coverage": {
            "actual": sum(row.get("status") == "READY" for row in financial_rows.values()),
            "requested": len(theme_names),
        },
        "active_pool_target_minimum": int(policy["target_pool_size"]["minimum"]),
        "active_pool_target_maximum": maximum,
        "active_pool_count": len(selected),
        "active_pool_status": "READY" if len(selected) >= int(policy["target_pool_size"]["minimum"])
        else "BELOW_TARGET_DATA_OR_QUALITY_GATES",
        "rows": sorted(output_rows, key=lambda row: (row["ticker"] not in selected_tickers, row["active_pool_rank"] or 999, row["ticker"])),
        "catalyst_rejected": catalyst_rejected, "bottleneck_rejected": bottleneck_rejected,
        "missing_value_policy": policy["missing_value_policy"],
        "formal_model_changed": False, "trade_decision_changed": False,
        "active_in_trade_decision": False, "report_changed": False,
        "future_data_violation_count": 0,
    }
    target = Path(output_path)
    target.parent.mkdir(parents=True, exist_ok=True)
    target.write_text(json.dumps(payload, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    return payload


def _float(value: object) -> float | None:
    return None if value in {None, "", "NA", "NULL"} else float(value)


def _int(value: object) -> int | None:
    return None if value in {None, "", "NA", "NULL"} else int(value)


def main() -> None:
    parser = argparse.ArgumentParser(description="Materialize R1 v0.4 research-only 1-6M active pool.")
    parser.add_argument("--date", required=True)
    parser.add_argument("--themes", default="config/r1_v02_themes.json")
    parser.add_argument("--weekly", required=True)
    parser.add_argument("--catalysts", default="data/r1/catalyst_events/evidence.csv")
    parser.add_argument("--bottlenecks", default="data/r1/bottleneck_evidence.csv")
    parser.add_argument("--policy", default="config/r1_v04_active_pool.json")
    parser.add_argument("--financial", default="data/r1/official_financial_latest.json")
    parser.add_argument("--output", default="data/r1/active_pool/latest.json")
    args = parser.parse_args()
    payload = materialize(
        as_of_date=args.date, theme_path=args.themes, weekly_path=args.weekly,
        catalyst_path=args.catalysts, bottleneck_path=args.bottlenecks,
        policy_path=args.policy, output_path=args.output, financial_path=args.financial,
    )
    print(json.dumps({"date": payload["date"], "active_pool_count": payload["active_pool_count"],
                      "status": payload["active_pool_status"]}, ensure_ascii=False))


if __name__ == "__main__":
    main()
