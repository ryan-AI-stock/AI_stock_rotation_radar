from __future__ import annotations

import argparse
import json
from pathlib import Path

from r1.config import R1Config
from r1.consensus import consensus_actionable, load_consensus_csv, load_consensus_evidence


def build_valuation_snapshot(
    *,
    date: str,
    config_path: str | Path,
    market_path: str | Path,
    consensus_path: str | Path,
    consensus_evidence_path: str | Path,
    output_root: str | Path,
) -> Path:
    config = R1Config.load(config_path)
    market = json.loads(Path(market_path).read_text(encoding="utf-8"))
    if market.get("date") != date:
        raise ValueError("valuation snapshot market date mismatch")
    if market.get("actual_ticker_count") != market.get("requested_ticker_count"):
        raise ValueError("valuation snapshot requires complete market coverage")

    fiscal_year = int(date[:4]) + 1
    consensus = load_consensus_csv(consensus_path, as_of_date=date)
    evidence, evidence_rejected = load_consensus_evidence(consensus_evidence_path, as_of_date=date)
    records = {(row.ticker, row.fiscal_year): row for row in consensus.records}
    market_by_ticker = {row["ticker"]: row for row in market["rows"]}
    rows = []
    for security in config.securities:
        record = records.get((security.ticker, fiscal_year))
        actionable = bool(record and consensus_actionable(
            consensus.records, ticker=security.ticker, fiscal_year=fiscal_year, evidence=evidence
        ))
        price = market_by_ticker[security.ticker].get("raw_close")
        forward_pe = None
        if actionable and price is not None and record.mean_eps not in {None, 0}:
            forward_pe = price / record.mean_eps
        rows.append({
            "date": date,
            "ticker": security.ticker,
            "company": security.company,
            "price": price,
            "fiscal_year": fiscal_year,
            "forward_eps_mean": record.mean_eps if actionable else None,
            "forward_eps_median": record.median_eps if actionable else None,
            "forward_eps_high": record.high_eps if actionable else None,
            "forward_eps_low": record.low_eps if actionable else None,
            "analyst_count": record.analyst_count if actionable else None,
            "forward_pe": forward_pe,
            "forward_pe_percentile": None,
            "consensus_source": record.source if actionable else None,
            "consensus_published_at": record.published_at if actionable else None,
            "consensus_available_at": record.available_at if actionable else None,
            "status": "BASELINE_RECORDED" if forward_pe is not None else "DATA_MISSING",
        })

    payload = {
        "model": "R1",
        "date": date,
        "fiscal_year": fiscal_year,
        "rows": rows,
        "ready_count": sum(row["status"] == "BASELINE_RECORDED" for row in rows),
        "requested_ticker_count": len(rows),
        "historical_percentile_ready": False,
        "consensus_rejected": list(consensus.rejected),
        "consensus_evidence_rejected": evidence_rejected,
        "future_data_violation_count": 0,
        "formal_model_changed": False,
        "trade_decision_changed": False,
        "active_in_trade_decision": False,
        "report_changed": False,
    }
    output = Path(output_root) / f"{date}.json"
    output.parent.mkdir(parents=True, exist_ok=True)
    if output.exists():
        existing = json.loads(output.read_text(encoding="utf-8"))
        if existing != payload:
            raise FileExistsError(f"append-only valuation snapshot already exists with different content: {output}")
        return output
    output.write_text(json.dumps(payload, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    return output


def main() -> None:
    parser = argparse.ArgumentParser(description="Append an R1 PIT forward-valuation baseline.")
    parser.add_argument("--date", required=True)
    parser.add_argument("--config", default="config/r1.json")
    parser.add_argument("--market", default="data/r1/daily_market_latest.json")
    parser.add_argument("--consensus", default="data/r1/consensus/consensus.csv")
    parser.add_argument("--consensus-evidence", default="data/r1/consensus/evidence.csv")
    parser.add_argument("--output-root", default="data/r1/valuation_history")
    args = parser.parse_args()
    print(build_valuation_snapshot(
        date=args.date,
        config_path=args.config,
        market_path=args.market,
        consensus_path=args.consensus,
        consensus_evidence_path=args.consensus_evidence,
        output_root=args.output_root,
    ))


if __name__ == "__main__":
    main()
