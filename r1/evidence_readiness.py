from __future__ import annotations

import argparse
import json
from pathlib import Path

from r1.config import R1Config
from r1.consensus import consensus_actionable, load_consensus_csv, load_consensus_evidence
from r1.evidence import load_catalyst_csv


def materialize(*, config_path: str | Path, consensus_path: str | Path,
                catalyst_path: str | Path, as_of_date: str,
                consensus_evidence_path: str | Path = "data/r1/consensus/evidence.csv") -> dict:
    config = R1Config.load(config_path)
    consensus_file = Path(consensus_path)
    catalyst_file = Path(catalyst_path)
    consensus = load_consensus_csv(consensus_file, as_of_date=as_of_date) if consensus_file.exists() else None
    support_file = Path(consensus_evidence_path)
    support, support_rejected = load_consensus_evidence(support_file, as_of_date=as_of_date) if support_file.exists() else ([], [])
    catalysts, catalyst_rejected = load_catalyst_csv(catalyst_file, as_of_date=as_of_date) if catalyst_file.exists() else ([], [])
    fiscal_year = int(as_of_date[:4]) + 1
    rows = []
    for security in config.securities:
        consensus_ready = bool(consensus and consensus_actionable(
            consensus.records, ticker=security.ticker, fiscal_year=fiscal_year, evidence=support))
        ticker_events = [row for row in catalysts if row.event.ticker == security.ticker]
        catalyst_ready = len({row.source_family for row in ticker_events}) >= 2 and any(
            row.event.source_tier <= 2 for row in ticker_events)
        rows.append({
            "ticker": security.ticker,
            "consensus_ready": consensus_ready,
            "catalyst_ready": catalyst_ready,
            "trade_ready": consensus_ready and catalyst_ready,
        })
    return {
        "model": "R1", "as_of_date": as_of_date, "fiscal_year": fiscal_year,
        "requested_ticker_count": len(rows),
        "consensus_ready_count": sum(row["consensus_ready"] for row in rows),
        "catalyst_ready_count": sum(row["catalyst_ready"] for row in rows),
        "trade_ready_count": sum(row["trade_ready"] for row in rows),
        "consensus_rejected": list(consensus.rejected) if consensus else [{"error": "file_missing"}],
        "consensus_evidence_rejected": support_rejected if support_file.exists() else [{"error": "file_missing"}],
        "catalyst_rejected": catalyst_rejected if catalyst_file.exists() else [{"error": "file_missing"}],
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
    parser.add_argument("--consensus-evidence", default="data/r1/consensus/evidence.csv")
    parser.add_argument("--output", default="data/r1/evidence_readiness.json")
    args = parser.parse_args()
    payload = materialize(config_path=args.config, consensus_path=args.consensus,
                          catalyst_path=args.catalysts, as_of_date=args.date,
                          consensus_evidence_path=args.consensus_evidence)
    output = Path(args.output)
    output.parent.mkdir(parents=True, exist_ok=True)
    output.write_text(json.dumps(payload, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    print(output)


if __name__ == "__main__":
    main()
