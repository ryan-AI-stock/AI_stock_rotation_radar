from __future__ import annotations

import argparse
import json
from datetime import date as calendar_date, timedelta
from pathlib import Path

from r1.config import R1Config
from r1.consensus import consensus_actionable, load_consensus_csv, load_consensus_evidence
from r1.component_scores import (
    bottleneck_score, catalyst_score, eps_revision_composite, eps_revision_score,
    forward_valuation_score, percentile_score, price_chip_score,
)
from r1.providers import MissingConsensusProvider
from r1.price_eps import price_eps_gap
from r1.market_signal_state import confirm_eps_trend, eps_state, flow_state, valuation_state
from r1.required_data import enforce_required_data, required_data_gaps
from r1.staged_action import dynamic_triggers
from r1.bottleneck_evidence import evidence_ready as bottleneck_evidence_ready, load_bottleneck_evidence
from r1.catalyst_evidence import evidence_ready as catalyst_evidence_ready, load_catalyst_evidence
from r1.evidence import CatalystEvent
from r1.industry_state import STAGE_ORDER, bottleneck_state, catalyst_state
from r1.shadow_rotation import evaluate_shadow_rotation
from r1.valuation import load_valuation_reference, valuation_position, valuation_scenarios
from r1.scoring import score as total_model_score
from r1.toalpha_revision_history import latest_rows as latest_supplemental_revision_rows


def _consensus_history_features(
    root: str | Path, *, ticker: str, fiscal_year: int, as_of_date: str,
) -> dict[str, float | str | None]:
    snapshots = []
    for path in sorted(Path(root).glob("????-??-??.json")):
        if path.stem > as_of_date:
            continue
        payload = json.loads(path.read_text(encoding="utf-8"))
        row = next((item for item in payload.get("rows", [])
                    if item.get("ticker") == ticker and item.get("fiscal_year") == fiscal_year
                    and item.get("status") == "READY"), None)
        if row and row.get("mean_eps") not in {None, 0}:
            snapshots.append((path.stem, float(row["mean_eps"])))
    result: dict[str, float | str | None] = {
        "eps_history_current_date": snapshots[-1][0] if snapshots else None,
    }
    current = snapshots[-1][1] if snapshots else None
    current_day = calendar_date.fromisoformat(as_of_date)
    for label, days in (("1w", 7), ("4w", 28), ("12w", 84)):
        cutoff = (current_day - timedelta(days=days)).isoformat()
        prior = next(((snapshot_date, value) for snapshot_date, value in reversed(snapshots)
                      if snapshot_date <= cutoff), None)
        result[f"eps_revision_{label}"] = None if current is None or prior is None else current / prior[1] - 1
        result[f"eps_revision_{label}_base_date"] = prior[0] if prior else None
    return result


def build_weekly_snapshot(
    *, date: str, config_path: str | Path, market_path: str | Path,
    daily_source_root: str | Path, output_root: str | Path, week_final_confirmed: bool = False,
    consensus_path: str | Path | None = None, consensus_evidence_path: str | Path | None = None,
    consensus_history_root: str | Path = "data/r1/consensus_history",
    valuation_reference_path: str | Path = "data/r1/valuation_reference.csv",
    bottleneck_evidence_path: str | Path = "data/r1/bottleneck_evidence.csv",
    catalyst_evidence_path: str | Path = "data/r1/catalyst_events/evidence.csv",
    supplemental_revision_path: str | Path = "data/r1/consensus/current_year_revision_history.csv",
) -> Path:
    if not week_final_confirmed:
        raise ValueError("formal weekly snapshot requires week_final_confirmed=true")
    output = Path(output_root) / f"weekly_snapshot_{date}.json"
    if output.exists():
        existing = json.loads(output.read_text(encoding="utf-8"))
        if (
            existing.get("model") != "R1"
            or existing.get("date") != date
            or existing.get("snapshot_policy") != "append_only"
            or not isinstance(existing.get("rows"), list)
            or not existing["rows"]
            or existing.get("future_data_violation_count") != 0
        ):
            raise FileExistsError(f"invalid append-only weekly snapshot already exists: {output}")
        return output
    config = R1Config.load(config_path)
    market = json.loads(Path(market_path).read_text(encoding="utf-8"))
    if market.get("date") != date:
        raise ValueError("weekly snapshot market date mismatch")
    if market.get("actual_ticker_count") != market.get("requested_ticker_count"):
        raise ValueError("weekly snapshot requires complete market coverage")
    daily_paths = sorted(Path(daily_source_root).glob("????-??-??.json"))
    daily_payloads = [json.loads(path.read_text(encoding="utf-8")) for path in daily_paths if path.stem <= date]
    current_payload = next((payload for payload in daily_payloads if payload.get("date") == date), None)
    if current_payload is None:
        raise ValueError("weekly snapshot requires exact-date daily sources")
    current_families = {
        (str(row.get("ticker", "")).zfill(4), str(row.get("family", "")))
        for row in current_payload.get("chip_rows", [])
    }
    missing_chip = [
        security.ticker for security in config.securities
        if (security.ticker, "institutional") not in current_families
        or (security.ticker, "margin_short") not in current_families
    ]
    if missing_chip:
        raise ValueError(
            "weekly snapshot requires exact-date institutional and margin data: "
            + ",".join(missing_chip)
        )
    market_by_ticker = {row["ticker"]: row for row in market["rows"]}
    fiscal_year = int(date[:4]) + 1
    valuation_reference = load_valuation_reference(valuation_reference_path, as_of_date=date)
    bottleneck_evidence, _ = load_bottleneck_evidence(bottleneck_evidence_path, as_of_date=date)
    catalyst_evidence, _ = load_catalyst_evidence(catalyst_evidence_path, as_of_date=date)
    supplemental_revisions = latest_supplemental_revision_rows(
        supplemental_revision_path, as_of_date=date,
    )
    if consensus_path and Path(consensus_path).exists():
        consensus_result = load_consensus_csv(consensus_path, as_of_date=date)
        consensus = {(row.ticker, row.fiscal_year): row for row in consensus_result.records}
        evidence, _ = load_consensus_evidence(consensus_evidence_path, as_of_date=date) \
            if consensus_evidence_path and Path(consensus_evidence_path).exists() else ([], [])
    else:
        consensus = {(row.ticker, row.fiscal_year): row for row in MissingConsensusProvider().fetch(market_by_ticker, date)}
        evidence = []
    rows = []
    prior_eps_states: dict[str, list[str]] = {}
    prior_weekly_rows: dict[str, dict] = {}
    for prior_path in sorted(Path(output_root).glob("weekly_snapshot_????-??-??.json")):
        if prior_path.stem.rsplit("_", 1)[-1] >= date:
            continue
        prior_payload = json.loads(prior_path.read_text(encoding="utf-8"))
        for prior_row in prior_payload.get("rows", []):
            ticker = str(prior_row.get("ticker", "")).zfill(4)
            prior_weekly_rows[ticker] = prior_row
            state = prior_row.get("eps_state")
            if state:
                prior_eps_states.setdefault(ticker, []).append(state)
    for security in config.securities:
        market_row = market_by_ticker[security.ticker]
        supplemental_revision = supplemental_revisions.get(security.ticker, {})
        price_history = [row for payload in daily_payloads for row in payload.get("price_rows", [])
                         if row.get("ticker") == security.ticker]
        chip_today = [row for payload in daily_payloads if payload.get("date") == date
                      for row in payload.get("chip_rows", []) if row.get("ticker") == security.ticker]
        volumes = [float(row["volume"]) for row in price_history if row.get("volume") not in {None, ""}]
        latest_by_family = {row["family"]: row for row in chip_today}
        institution = latest_by_family.get("institutional", {})
        margin = latest_by_family.get("margin_short", {})
        ticker_chip_history = [
            row for payload in daily_payloads for row in payload.get("chip_rows", [])
            if row.get("ticker") == security.ticker and row.get("family") == "institutional"
        ]
        institutional_flows = [
            float(row.get("foreign_net") or 0) + float(row.get("trust_net") or 0)
            for row in ticker_chip_history
            if row.get("foreign_net") is not None and row.get("trust_net") is not None
        ]
        flow_5d = sum(institutional_flows[-5:]) if len(institutional_flows) >= 5 else None
        flow_20d = sum(institutional_flows[-20:]) if len(institutional_flows) >= 20 else None
        margin_history = [
            row for payload in daily_payloads for row in payload.get("chip_rows", [])
            if row.get("ticker") == security.ticker and row.get("family") == "margin_short"
            and row.get("margin_balance") not in {None, ""}
        ]
        margin_20d_change = None
        if len(margin_history) >= 20 and float(margin_history[-20]["margin_balance"]) != 0:
            margin_20d_change = (
                float(margin_history[-1]["margin_balance"]) / float(margin_history[-20]["margin_balance"]) - 1
            )
        current_record = consensus.get((security.ticker, int(date[:4])))
        record = consensus.get((security.ticker, fiscal_year))
        next_next_record = consensus.get((security.ticker, fiscal_year + 1))
        consensus_ready = bool(record and consensus_actionable(
            tuple(consensus.values()), ticker=security.ticker, fiscal_year=fiscal_year, evidence=evidence))
        current_consensus_ready = bool(current_record and consensus_actionable(
            tuple(consensus.values()), ticker=security.ticker, fiscal_year=int(date[:4]), evidence=evidence))
        next_next_consensus_ready = bool(next_next_record and consensus_actionable(
            tuple(consensus.values()), ticker=security.ticker, fiscal_year=fiscal_year + 1, evidence=evidence))
        revision = _consensus_history_features(
            consensus_history_root, ticker=security.ticker, fiscal_year=fiscal_year, as_of_date=date,
        )
        next_year_eps = record.mean_eps if record else None
        current_year_eps = current_record.mean_eps if current_consensus_ready else None
        next_next_year_eps = next_next_record.mean_eps if next_next_consensus_ready else None
        next_year_eps_growth = None if current_year_eps in {None, 0} or next_year_eps is None \
            else next_year_eps / current_year_eps - 1
        forward_pe = None if next_year_eps in {None, 0} or market_row["raw_close"] is None \
            else market_row["raw_close"] / next_year_eps
        valuation = valuation_position(
            forward_pe=forward_pe, reference=valuation_reference.get(security.ticker),
        )
        scenarios = valuation_scenarios(
            price=market_row["raw_close"],
            bear_eps=record.low_eps if consensus_ready else None,
            base_eps=record.mean_eps if consensus_ready else None,
            bull_eps=record.high_eps if consensus_ready else None,
            bear_pe=None,
            base_pe=valuation["forward_pe_median_5y"],
            bull_pe=None,
        )
        gap_1w = price_eps_gap(
            price_change=market_row["return_1w"], eps_revision=revision["eps_revision_1w"],
        )
        gap_4w = price_eps_gap(
            price_change=market_row["return_1m"], eps_revision=revision["eps_revision_4w"],
        )
        gap_12w = price_eps_gap(
            price_change=market_row["return_3m"], eps_revision=revision["eps_revision_12w"],
        )
        current_eps_state = eps_state(revision["eps_revision_4w"])
        eps_trend = confirm_eps_trend(prior_eps_states.get(security.ticker, []) + [current_eps_state])
        prior_row = prior_weekly_rows.get(security.ticker, {})
        prior_forward_pe = prior_row.get("forward_pe")
        prior_base_fair_value = prior_row.get("base_fair_value")
        prior_base_upside = prior_row.get("base_upside")
        forward_pe_change = None if forward_pe is None or prior_forward_pe in {None, 0} \
            else forward_pe / prior_forward_pe - 1
        base_fair_value_change = None if scenarios["base_fair_value"] is None or prior_base_fair_value in {None, 0} \
            else scenarios["base_fair_value"] / prior_base_fair_value - 1
        base_upside_change = None if scenarios["base_upside"] is None or prior_base_upside is None \
            else scenarios["base_upside"] - prior_base_upside
        ticker_bottlenecks = [row for row in bottleneck_evidence if row.ticker == security.ticker]
        current_bottleneck_stage = max(
            (row.stage for row in ticker_bottlenecks), key=lambda stage: STAGE_ORDER[stage], default=None,
        )
        current_bottleneck_state = bottleneck_state(
            current_bottleneck_stage, prior_row.get("bottleneck_stage"),
        )
        ticker_catalysts = [row for row in catalyst_evidence if row.ticker == security.ticker]
        current_catalyst_state = catalyst_state(
            directions=[row.impact_direction for row in ticker_catalysts],
            source_families={row.source_family for row in ticker_catalysts},
        )
        triggers = dynamic_triggers(
            eps_state=current_eps_state,
            valuation_state=valuation_state(
                forward_pe_change=forward_pe_change, base_upside_change=base_upside_change,
            ),
            flow_state=flow_state(flow_5d, flow_20d),
            bottleneck_state=current_bottleneck_state,
            catalyst_state=current_catalyst_state,
        )
        rows.append({
            **market_row,
            "current_year_eps_revision_30d": (
                float(supplemental_revision["revision_30d"]) if supplemental_revision else None
            ),
            "current_year_eps_revision_90d": (
                float(supplemental_revision["revision_90d"]) if supplemental_revision else None
            ),
            "current_year_eps_revision_status": (
                "SUPPLEMENTAL_NOT_TOTAL_SCORE" if supplemental_revision else "DATA_MISSING"
            ),
            "position_shares": security.shares,
            "core_lock": security.core_lock,
            "position_value": market_row["raw_close"] * security.shares if market_row["raw_close"] is not None else None,
            "volume": volumes[-1] if volumes else None,
            "avg_volume_20d": sum(volumes[-20:]) / 20 if len(volumes) >= 20 else None,
            "foreign_net": institution.get("foreign_net"),
            "trust_net": institution.get("trust_net"),
            "dealer_net": institution.get("dealer_net"),
            "margin_balance": margin.get("margin_balance"),
            "margin_change": margin.get("margin_change"),
            "institutional_flow_5d": flow_5d,
            "institutional_flow_20d": flow_20d,
            "institutional_flow_ratio_20d": None if flow_20d is None or len(volumes) < 20
            or sum(volumes[-20:]) == 0 else flow_20d / sum(volumes[-20:]),
            "margin_balance_change_20d": margin_20d_change,
            "flow_state": flow_state(flow_5d, flow_20d),
            "chip_data_status": "AVAILABLE" if institution and margin else "DATA_MISSING",
            "next_year_eps": next_year_eps,
            "current_year_eps": current_year_eps,
            "next_next_year_eps": next_next_year_eps,
            "next_year_eps_growth": next_year_eps_growth,
            "analyst_count": record.analyst_count if record else None,
            "consensus_status": "READY" if consensus_ready else (record.status if record else "DATA_MISSING"),
            "consensus_quality": record.quality if record else "LOW",
            "consensus_allowed": consensus_ready,
            **revision,
            "eps_state": current_eps_state,
            "signal_stage": eps_trend.stage,
            "trend_confidence": eps_trend.confidence,
            "eps_trend_consecutive_weeks": eps_trend.consecutive_weeks,
            "bottleneck_stage": current_bottleneck_stage,
            "bottleneck_state": current_bottleneck_state,
            "catalyst_state": current_catalyst_state,
            **triggers,
            "forward_pe": forward_pe,
            **valuation,
            **scenarios,
            "bear_pe": None,
            "base_pe": valuation["forward_pe_median_5y"],
            "bull_pe": None,
            "valuation_scenario_status": "BASE_READY_PE_BANDS_MISSING"
            if scenarios["base_fair_value"] is not None else "DATA_MISSING",
            "forward_pe_change_1w": forward_pe_change,
            "base_fair_value_change_1w": base_fair_value_change,
            "base_upside_change_1w": base_upside_change,
            "valuation_state": valuation_state(
                forward_pe_change=forward_pe_change, base_upside_change=base_upside_change,
            ),
            "price_eps_gap_1w": gap_1w.earnings_minus_price,
            "price_eps_state_1w": gap_1w.state,
            "price_eps_gap_4w": gap_4w.earnings_minus_price,
            "price_eps_state_4w": gap_4w.state,
            "price_eps_gap_12w": gap_12w.earnings_minus_price,
            "price_eps_state_12w": gap_12w.state,
            "eps_score": None,
            "valuation_score": None,
            "bottleneck_score": None,
            "catalyst_score": None,
            "price_chip_score": None,
            "bottleneck_tightness_score": None,
            "bottleneck_financial_proof_score": None,
            "catalyst_positive_decayed": None,
            "catalyst_negative_decayed": None,
            "earnings_vs_price_score": None,
            "overheat_safety_score": None,
            "institutional_score": None,
            "leverage_structure_score": None,
            "total_score": None,
            "action": "CORE" if security.core_lock else "WATCH" if consensus_ready else "DATA_MISSING",
            "action_reason": "CORE_LOCK" if security.core_lock else
                             "ACTION_THRESHOLDS_NOT_APPROVED" if consensus_ready else "EPS_CONSENSUS_NOT_READY",
            "target_weight": None,
            "suggested_transfer": None,
        })
    eligible_eps_composites = [
        composite for row in rows
        if (composite := eps_revision_composite(
            revision_1w=row["eps_revision_1w"], revision_4w=row["eps_revision_4w"],
            revision_12w=row["eps_revision_12w"], policy=config.score_policy["eps_revision"],
        )) is not None
    ]
    for row in rows:
        row["eps_score"] = eps_revision_score(
            revision_1w=row["eps_revision_1w"], revision_4w=row["eps_revision_4w"],
            revision_12w=row["eps_revision_12w"], eligible_composites=eligible_eps_composites,
            policy=config.score_policy["eps_revision"],
        )
    eligible_base_upside = [
        float(row["base_upside"]) for row in rows if row["base_upside"] is not None
    ]
    eligible_eps_growth = [
        float(row["next_year_eps_growth"]) for row in rows
        if row["next_year_eps_growth"] is not None
    ]
    for row in rows:
        row["valuation_score"] = forward_valuation_score(
            own_forward_pe_percentile=row["forward_pe_percentile_5y"],
            base_upside=row["base_upside"],
            next_year_eps_growth=row["next_year_eps_growth"],
            eligible_base_upside=eligible_base_upside,
            eligible_eps_growth=eligible_eps_growth,
            policy=config.score_policy["forward_valuation"],
        )
    bias20_values = [float(row["bias20"]) for row in rows if row.get("bias20") is not None]
    gap4w_values = [float(row["price_eps_gap_4w"]) for row in rows if row.get("price_eps_gap_4w") is not None]
    flow_ratio_values = [
        float(row["institutional_flow_ratio_20d"]) for row in rows
        if row.get("institutional_flow_ratio_20d") is not None
    ]
    margin_change_values = [
        float(row["margin_balance_change_20d"]) for row in rows
        if row.get("margin_balance_change_20d") is not None
    ]
    for row in rows:
        ticker_bottlenecks = [item for item in bottleneck_evidence if item.ticker == row["ticker"]]
        ticker_catalysts = [item for item in catalyst_evidence if item.ticker == row["ticker"]]
        stage = row.get("bottleneck_stage")
        bottleneck_policy = config.score_policy["bottleneck"]
        tightness_candidates = [
            float(bottleneck_policy["tightness_event_scores"][item.event_type])
            for item in ticker_catalysts
            if item.impact_direction == "UP"
            and item.event_type in bottleneck_policy["tightness_event_scores"]
        ]
        row["bottleneck_tightness_score"] = max(tightness_candidates, default=None)
        row["bottleneck_financial_proof_score"] = (
            float(bottleneck_policy["financial_proof_stage_scores"][stage]) if stage else None
        )
        row["bottleneck_score"] = None if stage is None else bottleneck_score(
            stage=stage,
            tightness_score=row["bottleneck_tightness_score"],
            financial_proof_score=row["bottleneck_financial_proof_score"],
            evidence_verified=bottleneck_evidence_ready(bottleneck_evidence, ticker=row["ticker"]),
            policy=bottleneck_policy,
        )
        positive_scores, negative_scores = [], []
        catalyst_policy = config.score_policy["catalyst"]
        for item in ticker_catalysts:
            event_policy = catalyst_policy["event_policy"].get(item.event_type)
            if event_policy is None:
                continue
            value = CatalystEvent(
                event_date=item.event_date, ticker=item.ticker, event_type=item.event_type,
                impact_score=float(event_policy["impact"]), confidence=1.0,
                expiry_weeks=int(event_policy["expiry_weeks"]), source_tier=item.source_tier,
                source_url=item.source_url,
            ).score_at(date)
            (positive_scores if item.impact_direction == "UP" else negative_scores).append(value)
        row["catalyst_positive_decayed"] = round(sum(positive_scores), 6)
        row["catalyst_negative_decayed"] = round(sum(negative_scores), 6)
        row["catalyst_score"] = catalyst_score(
            positive_decayed_scores=positive_scores, negative_decayed_scores=negative_scores,
            evidence_ready=catalyst_evidence_ready(catalyst_evidence, ticker=row["ticker"]),
            policy=catalyst_policy,
        )
        row["earnings_vs_price_score"] = percentile_score(gap4w_values, row.get("price_eps_gap_4w"))
        bias_rank = percentile_score(bias20_values, row.get("bias20"))
        pe_percentile = row.get("forward_pe_percentile_5y")
        row["overheat_safety_score"] = None if bias_rank is None or pe_percentile is None else round(
            ((100.0 - bias_rank) + (1.0 - float(pe_percentile)) * 100.0) / 2.0, 6,
        )
        row["institutional_score"] = percentile_score(
            flow_ratio_values, row.get("institutional_flow_ratio_20d"),
        )
        margin_rank = percentile_score(margin_change_values, row.get("margin_balance_change_20d"))
        row["leverage_structure_score"] = None if margin_rank is None else round(100.0 - margin_rank, 6)
        row["price_chip_score"] = price_chip_score(
            earnings_vs_price_score=row["earnings_vs_price_score"],
            overheat_safety_score=row["overheat_safety_score"],
            institutional_score=row["institutional_score"],
            leverage_structure_score=row["leverage_structure_score"],
            policy=config.score_policy["price_chip"],
        )
        total = total_model_score(
            components={
                "eps_revision": row["eps_score"], "forward_valuation": row["valuation_score"],
                "bottleneck": row["bottleneck_score"], "catalyst": row["catalyst_score"],
                "price_chip": row["price_chip_score"],
            },
            weights=config.weights, consensus_allowed=bool(row["consensus_allowed"]),
        )
        row["total_score"] = total.total_score
        row["score_status"] = total.reason
        row["score_missing_components"] = list(total.missing_components)
    decision_required_fields = (
        "eps_revision_1w", "eps_revision_4w", "eps_revision_12w",
        "forward_pe", "forward_pe_percentile_5y", "base_fair_value", "base_upside",
        "foreign_net", "trust_net", "margin_balance", "margin_change",
    )
    decision_gaps = required_data_gaps(rows, decision_required_fields)
    if config.action_policy_approved:
        enforce_required_data(
            rows, decision_required_fields, date=date, context="weekly_decision",
        )
    held_sources = [row for row in rows if row["position_shares"] > 0 and not row["core_lock"]]
    unheld_targets = [row for row in rows if row["position_shares"] == 0 and not row["core_lock"]]
    shadow_candidates = []
    shadow_blocked_pairs = 0
    for source in held_sources:
        for target in unheld_targets:
            candidate = evaluate_shadow_rotation(
                source=source, target=target, policy=config.rotation_policy,
                holding_count=sum(row["position_shares"] > 0 for row in rows),
            )
            if candidate["status"] == "DATA_MISSING":
                shadow_blocked_pairs += 1
            else:
                shadow_candidates.append(candidate)
    shadow_candidates.sort(key=lambda row: row.get("score_advantage", float("-inf")), reverse=True)
    payload = {
        "model": "R1", "date": date, "snapshot_policy": "append_only",
        "rows": rows, "future_data_violation_count": 0,
        "required_data_gap_count": len(decision_gaps),
        "required_data_gaps": decision_gaps,
        "required_data_enforced": config.action_policy_approved,
        "shadow_rotation_status": "READY" if shadow_candidates else "DATA_MISSING_COMPONENT_SCORES",
        "shadow_rotation_candidates": shadow_candidates,
        "shadow_rotation_blocked_pair_count": shadow_blocked_pairs,
        "shadow_only": True,
        "formal_model_changed": False, "trade_decision_changed": False,
        "active_in_trade_decision": False, "report_changed": False,
    }
    output.parent.mkdir(parents=True, exist_ok=True)
    output.write_text(json.dumps(payload, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    return output


def main() -> None:
    parser = argparse.ArgumentParser(description="Build an append-only R1 weekly snapshot.")
    parser.add_argument("--date", required=True)
    parser.add_argument("--config", default="config/r1.json")
    parser.add_argument("--market", required=True)
    parser.add_argument("--daily-source-root", default="data/r1/daily_sources")
    parser.add_argument("--output-root", default="data/r1/weekly")
    parser.add_argument("--week-final-confirmed", action="store_true")
    parser.add_argument("--consensus", default="data/r1/consensus/consensus.csv")
    parser.add_argument("--consensus-evidence", default="data/r1/consensus/evidence.csv")
    parser.add_argument("--consensus-history-root", default="data/r1/consensus_history")
    parser.add_argument("--valuation-reference", default="data/r1/valuation_reference.csv")
    parser.add_argument("--bottleneck-evidence", default="data/r1/bottleneck_evidence.csv")
    parser.add_argument("--catalyst-evidence", default="data/r1/catalyst_events/evidence.csv")
    parser.add_argument("--supplemental-revision", default="data/r1/consensus/current_year_revision_history.csv")
    args = parser.parse_args()
    print(build_weekly_snapshot(date=args.date, config_path=args.config, market_path=args.market,
                                daily_source_root=args.daily_source_root, output_root=args.output_root,
                                week_final_confirmed=args.week_final_confirmed,
                                consensus_path=args.consensus,
                                consensus_evidence_path=args.consensus_evidence,
                                consensus_history_root=args.consensus_history_root,
                                valuation_reference_path=args.valuation_reference,
                                bottleneck_evidence_path=args.bottleneck_evidence,
                                catalyst_evidence_path=args.catalyst_evidence,
                                supplemental_revision_path=args.supplemental_revision))


if __name__ == "__main__":
    main()
