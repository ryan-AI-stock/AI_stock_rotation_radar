from __future__ import annotations

import argparse
import json
from datetime import date as calendar_date, timedelta
from pathlib import Path

from r1.config import R1Config
from r1.consensus import consensus_actionable, load_consensus_csv, load_consensus_evidence
from r1.providers import MissingConsensusProvider


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
    market_by_ticker = {row["ticker"]: row for row in market["rows"]}
    fiscal_year = int(date[:4]) + 1
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
            "next_year_eps": record.mean_eps if record else None,
            "analyst_count": record.analyst_count if record else None,
            "consensus_status": "READY" if consensus_ready else (record.status if record else "DATA_MISSING"),
            "consensus_quality": record.quality if record else "LOW",
            "consensus_allowed": consensus_ready,
            **revision,
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
    payload = {
        "model": "R1", "date": date, "snapshot_policy": "append_only",
        "rows": rows, "future_data_violation_count": 0,
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
    args = parser.parse_args()
    print(build_weekly_snapshot(date=args.date, config_path=args.config, market_path=args.market,
                                daily_source_root=args.daily_source_root, output_root=args.output_root,
                                week_final_confirmed=args.week_final_confirmed,
                                consensus_path=args.consensus,
                                consensus_evidence_path=args.consensus_evidence,
                                consensus_history_root=args.consensus_history_root))


if __name__ == "__main__":
    main()
