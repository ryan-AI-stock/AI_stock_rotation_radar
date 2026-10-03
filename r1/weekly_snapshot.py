from __future__ import annotations

import argparse
import json
from datetime import date as calendar_date, timedelta
from pathlib import Path

from r1.config import R1Config
from r1.consensus import consensus_actionable, load_consensus_csv, load_consensus_evidence
from r1.component_scores import eps_revision_composite, eps_revision_score
from r1.providers import MissingConsensusProvider
from r1.price_eps import price_eps_gap
from r1.required_data import enforce_required_data, required_data_gaps
from r1.valuation import load_valuation_reference, valuation_position, valuation_scenarios


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
) -> Path:
    if not week_final_confirmed:
        raise ValueError("formal weekly snapshot requires week_final_confirmed=true")
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
    if consensus_path and Path(consensus_path).exists():
        consensus_result = load_consensus_csv(consensus_path, as_of_date=date)
        consensus = {row.ticker: row for row in consensus_result.records if row.fiscal_year == fiscal_year}
        evidence, _ = load_consensus_evidence(consensus_evidence_path, as_of_date=date) \
            if consensus_evidence_path and Path(consensus_evidence_path).exists() else ([], [])
    else:
        consensus = {row.ticker: row for row in MissingConsensusProvider().fetch(market_by_ticker, date)}
        evidence = []
    rows = []
    for security in config.securities:
        market_row = market_by_ticker[security.ticker]
        price_history = [row for payload in daily_payloads for row in payload.get("price_rows", [])
                         if row.get("ticker") == security.ticker]
        chip_today = [row for payload in daily_payloads if payload.get("date") == date
                      for row in payload.get("chip_rows", []) if row.get("ticker") == security.ticker]
        volumes = [float(row["volume"]) for row in price_history if row.get("volume") not in {None, ""}]
        latest_by_family = {row["family"]: row for row in chip_today}
        institution = latest_by_family.get("institutional", {})
        margin = latest_by_family.get("margin_short", {})
        record = consensus.get(security.ticker)
        consensus_ready = bool(record and consensus_actionable(
            tuple(consensus.values()), ticker=security.ticker, fiscal_year=fiscal_year, evidence=evidence))
        revision = _consensus_history_features(
            consensus_history_root, ticker=security.ticker, fiscal_year=fiscal_year, as_of_date=date,
        )
        next_year_eps = record.mean_eps if record else None
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
        rows.append({
            **market_row,
            "position_shares": security.shares,
            "core_lock": security.core_lock,
            "position_value": market_row["raw_close"] * security.shares if market_row["raw_close"] is not None else None,
            "volume": volumes[-1] if volumes else None,
            "avg_volume_20d": sum(volumes[-20:]) / 20 if len(volumes) >= 20 else None,
            "foreign_net": institution.get("foreign_net") or None,
            "trust_net": institution.get("trust_net") or None,
            "dealer_net": institution.get("dealer_net") or None,
            "margin_balance": margin.get("margin_balance") or None,
            "margin_change": margin.get("margin_change") or None,
            "chip_data_status": "AVAILABLE" if institution and margin else "DATA_MISSING",
            "next_year_eps": next_year_eps,
            "analyst_count": record.analyst_count if record else None,
            "consensus_status": "READY" if consensus_ready else (record.status if record else "DATA_MISSING"),
            "consensus_quality": record.quality if record else "LOW",
            "consensus_allowed": consensus_ready,
            **revision,
            "forward_pe": forward_pe,
            **valuation,
            **scenarios,
            "bear_pe": None,
            "base_pe": valuation["forward_pe_median_5y"],
            "bull_pe": None,
            "valuation_scenario_status": "BASE_READY_PE_BANDS_MISSING"
            if scenarios["base_fair_value"] is not None else "DATA_MISSING",
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
    payload = {
        "model": "R1", "date": date, "snapshot_policy": "append_only",
        "rows": rows, "future_data_violation_count": 0,
        "required_data_gap_count": len(decision_gaps),
        "required_data_gaps": decision_gaps,
        "required_data_enforced": config.action_policy_approved,
        "formal_model_changed": False, "trade_decision_changed": False,
        "active_in_trade_decision": False, "report_changed": False,
    }
    output = Path(output_root) / f"weekly_snapshot_{date}.json"
    output.parent.mkdir(parents=True, exist_ok=True)
    if output.exists():
        existing = json.loads(output.read_text(encoding="utf-8"))
        if existing != payload:
            raise FileExistsError(f"append-only snapshot already exists with different content: {output}")
        return output
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
    args = parser.parse_args()
    print(build_weekly_snapshot(date=args.date, config_path=args.config, market_path=args.market,
                                daily_source_root=args.daily_source_root, output_root=args.output_root,
                                week_final_confirmed=args.week_final_confirmed,
                                consensus_path=args.consensus,
                                consensus_evidence_path=args.consensus_evidence,
                                consensus_history_root=args.consensus_history_root,
                                valuation_reference_path=args.valuation_reference))


if __name__ == "__main__":
    main()
