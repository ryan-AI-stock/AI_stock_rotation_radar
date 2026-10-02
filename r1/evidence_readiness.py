from __future__ import annotations

import argparse
import json
from pathlib import Path

from r1.config import R1Config
from r1.catalyst_evidence import evidence_ready, load_catalyst_evidence
from r1.consensus import consensus_actionable, load_consensus_csv, load_consensus_evidence
from r1.evidence import load_catalyst_csv


def materialize(*, config_path: str | Path, consensus_path: str | Path,
                catalyst_path: str | Path, as_of_date: str,
                consensus_evidence_path: str | Path = "data/r1/consensus/evidence.csv",
                bottleneck_path: str | Path = "data/r1/bottleneck_map.json",
                catalyst_evidence_path: str | Path = "data/r1/catalyst_events/evidence.csv") -> dict:
    config = R1Config.load(config_path)
    consensus_file = Path(consensus_path)
    catalyst_file = Path(catalyst_path)
    consensus = load_consensus_csv(consensus_file, as_of_date=as_of_date) if consensus_file.exists() else None
    support_file = Path(consensus_evidence_path)
    support, support_rejected = load_consensus_evidence(support_file, as_of_date=as_of_date) if support_file.exists() else ([], [])
    catalysts, catalyst_rejected = load_catalyst_csv(catalyst_file, as_of_date=as_of_date) if catalyst_file.exists() else ([], [])
    catalyst_evidence_file = Path(catalyst_evidence_path)
    catalyst_evidence, catalyst_evidence_rejected = load_catalyst_evidence(
        catalyst_evidence_file, as_of_date=as_of_date
    ) if catalyst_evidence_file.exists() else ([], [])
    bottleneck_file = Path(bottleneck_path)
    bottleneck_payload = json.loads(bottleneck_file.read_text(encoding="utf-8")) if bottleneck_file.exists() else {"rows": []}
    bottleneck_by_ticker = {str(row.get("ticker", "")).zfill(4): row for row in bottleneck_payload.get("rows", [])}
    fiscal_year = int(as_of_date[:4]) + 1
    rows = []
    for security in config.securities:
        consensus_ready = bool(consensus and consensus_actionable(
            consensus.records, ticker=security.ticker, fiscal_year=fiscal_year, evidence=support))
        ticker_events = [row for row in catalysts if row.event.ticker == security.ticker]
        catalyst_score_ready = len({row.source_family for row in ticker_events}) >= 2 and any(
            row.event.source_tier <= 2 for row in ticker_events)
        catalyst_ready = evidence_ready(catalyst_evidence, ticker=security.ticker)
        bottleneck_ready = bottleneck_by_ticker.get(security.ticker, {}).get("evidence_status") == "VERIFIED"
        # These components need historical PIT series and an approved calibration contract.
        valuation_ready = False
        price_chip_ready = False
        component_score_ready = consensus_ready and catalyst_score_ready and bottleneck_ready and valuation_ready and price_chip_ready
        trade_ready = component_score_ready and config.action_policy_approved
        blocked_reasons = []
        if not consensus_ready:
            blocked_reasons.append("CONSENSUS_NOT_READY")
        if not catalyst_ready:
            blocked_reasons.append("CATALYST_EVIDENCE_NOT_READY")
        if not bottleneck_ready:
            blocked_reasons.append("BOTTLENECK_EVIDENCE_NOT_READY")
        if not valuation_ready:
            blocked_reasons.append("VALUATION_HISTORY_NOT_READY")
        if not price_chip_ready:
            blocked_reasons.append("PRICE_CHIP_HISTORY_NOT_READY")
        if not config.action_policy_approved:
            blocked_reasons.append("ACTION_POLICY_NOT_APPROVED")
        rows.append({
            "ticker": security.ticker,
            "consensus_ready": consensus_ready,
            "catalyst_ready": catalyst_ready,
            "catalyst_score_ready": catalyst_score_ready,
            "bottleneck_ready": bottleneck_ready,
            "valuation_ready": valuation_ready,
            "price_chip_ready": price_chip_ready,
            "component_score_ready": component_score_ready,
            "trade_ready": trade_ready,
            "blocked_reasons": blocked_reasons,
        })
    return {
        "model": "R1", "as_of_date": as_of_date, "fiscal_year": fiscal_year,
        "requested_ticker_count": len(rows),
        "consensus_ready_count": sum(row["consensus_ready"] for row in rows),
        "catalyst_ready_count": sum(row["catalyst_ready"] for row in rows),
        "catalyst_score_ready_count": sum(row["catalyst_score_ready"] for row in rows),
        "bottleneck_ready_count": sum(row["bottleneck_ready"] for row in rows),
        "component_score_ready_count": sum(row["component_score_ready"] for row in rows),
        "trade_ready_count": sum(row["trade_ready"] for row in rows),
        "action_policy_approved": config.action_policy_approved,
        "consensus_rejected": list(consensus.rejected) if consensus else [{"error": "file_missing"}],
        "consensus_evidence_rejected": support_rejected if support_file.exists() else [{"error": "file_missing"}],
        "catalyst_rejected": catalyst_rejected if catalyst_file.exists() else [{"error": "file_missing"}],
        "catalyst_evidence_rejected": catalyst_evidence_rejected if catalyst_evidence_file.exists() else [{"error": "file_missing"}],
        "rows": rows,
        "formal_model_changed": False, "trade_decision_changed": False,
        "active_in_trade_decision": False, "report_changed": False,
    }


def main() -> None:
    parser = argparse.ArgumentParser(description="Materialize R1 evidence readiness without inventing scores.")
    parser.add_argument("--date", required=True)
    parser.add_argument("--config", default="config/r1.json")
    parser.add_argument("--consensus", default="data/r1/consensus/consensus.csv")
    parser.add_argument("--catalysts", default="data/r1/catalyst_events/events.csv")
    parser.add_argument("--catalyst-evidence", default="data/r1/catalyst_events/evidence.csv")
    parser.add_argument("--consensus-evidence", default="data/r1/consensus/evidence.csv")
    parser.add_argument("--output", default="data/r1/evidence_readiness.json")
    args = parser.parse_args()
    payload = materialize(config_path=args.config, consensus_path=args.consensus,
                          catalyst_path=args.catalysts, as_of_date=args.date,
                          consensus_evidence_path=args.consensus_evidence,
                          catalyst_evidence_path=args.catalyst_evidence)
    output = Path(args.output)
    output.parent.mkdir(parents=True, exist_ok=True)
    output.write_text(json.dumps(payload, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    print(output)


if __name__ == "__main__":
    main()
