from __future__ import annotations

import argparse
import json
from pathlib import Path

from r1.config import R1Config
from r1.consensus import consensus_actionable, load_consensus_csv, load_consensus_evidence


def build_consensus_snapshot(
    *, date: str, config_path: str | Path, consensus_path: str | Path,
    consensus_evidence_path: str | Path, output_root: str | Path,
) -> Path:
    """Persist the consensus that was actually observable on a weekly run date."""
    output = Path(output_root) / f"{date}.json"
    if output.exists():
        existing = json.loads(output.read_text(encoding="utf-8"))
        if (
            existing.get("model") != "R1"
            or existing.get("snapshot_date") != date
            or existing.get("snapshot_policy") != "append_only_source_available_at"
            or not isinstance(existing.get("rows"), list)
            or not existing["rows"]
            or existing.get("future_data_violation_count") != 0
        ):
            raise FileExistsError(f"invalid append-only consensus snapshot already exists: {output}")
        return output
    config = R1Config.load(config_path)
    result = load_consensus_csv(consensus_path, as_of_date=date)
    evidence, evidence_rejected = load_consensus_evidence(consensus_evidence_path, as_of_date=date)
    fiscal_year = int(date[:4]) + 1
    fiscal_years = (int(date[:4]), fiscal_year, fiscal_year + 1)
    records = {(row.ticker, row.fiscal_year): row for row in result.records}
    rows = []
    for security in config.securities:
      for target_year in fiscal_years:
        record = records.get((security.ticker, target_year))
        actionable = bool(record and consensus_actionable(
            result.records, ticker=security.ticker, fiscal_year=target_year, evidence=evidence,
        ))
        rows.append({
            "snapshot_date": date,
            "ticker": security.ticker,
            "company": security.company,
            "fiscal_year": target_year,
            "mean_eps": record.mean_eps if actionable else None,
            "median_eps": record.median_eps if actionable else None,
            "high_eps": record.high_eps if actionable else None,
            "low_eps": record.low_eps if actionable else None,
            "analyst_count": record.analyst_count if actionable else None,
            "source": record.source if actionable else None,
            "published_at": record.published_at if actionable else None,
            "available_at": record.available_at if actionable else None,
            "retrieved_at": record.retrieved_at if actionable else None,
            "quality": record.quality if actionable else "LOW",
            "status": "READY" if actionable else "EVIDENCE_GAP" if record else "DATA_MISSING",
            "observed_mean_eps": record.mean_eps if record else None,
            "observed_source": record.source if record else None,
        })
    payload = {
        "model": "R1",
        "snapshot_date": date,
        "fiscal_year": fiscal_year,
        "fiscal_years": list(fiscal_years),
        "snapshot_policy": "append_only_source_available_at",
        "rows": rows,
        "ready_count": sum(row["status"] == "READY" for row in rows),
        "requested_ticker_count": len(config.securities),
        "requested_security_count": len(config.securities),
        "requested_record_count": len(config.securities) * len(fiscal_years),
        "consensus_rejected": list(result.rejected),
        "consensus_evidence_rejected": evidence_rejected,
        "future_data_violation_count": 0,
        "formal_model_changed": False,
        "trade_decision_changed": False,
        "active_in_trade_decision": False,
        "report_changed": False,
    }
    output.parent.mkdir(parents=True, exist_ok=True)
    output.write_text(json.dumps(payload, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    return output


def main() -> None:
    parser = argparse.ArgumentParser(description="Append an observed R1 consensus snapshot.")
    parser.add_argument("--date", required=True)
    parser.add_argument("--config", default="config/r1.json")
    parser.add_argument("--consensus", default="data/r1/consensus/consensus.csv")
    parser.add_argument("--consensus-evidence", default="data/r1/consensus/evidence.csv")
    parser.add_argument("--output-root", default="data/r1/consensus_history")
    args = parser.parse_args()
    print(build_consensus_snapshot(
        date=args.date,
        config_path=args.config,
        consensus_path=args.consensus,
        consensus_evidence_path=args.consensus_evidence,
        output_root=args.output_root,
    ))


if __name__ == "__main__":
    main()
