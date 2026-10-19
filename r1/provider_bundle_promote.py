from __future__ import annotations

import argparse
import csv
import json
from pathlib import Path

from r1.consensus import load_consensus_csv, load_consensus_evidence
from r1.target_price_consensus import build_snapshot, load_records


CONSENSUS_FIELDS = (
    "ticker", "fiscal_year", "mean_eps", "median_eps", "high_eps", "low_eps",
    "analyst_count", "source", "published_at", "available_at", "retrieved_at",
    "quality", "status",
)
CONSENSUS_EVIDENCE_FIELDS = (
    "ticker", "fiscal_year", "source_url", "source_family", "source_tier",
    "available_at", "note",
)
TARGET_FIELDS = (
    "ticker", "institution", "target_price", "horizon", "available_at",
    "source_url", "retrieved_at", "note",
)


def _read(path: str | Path | None) -> list[dict[str, str]]:
    if not path:
        return []
    source = Path(path)
    if not source.exists():
        raise FileNotFoundError(source)
    with source.open(encoding="utf-8-sig", newline="") as handle:
        return list(csv.DictReader(handle))


def _merge(current: list[dict[str, str]], incoming: list[dict[str, str]], *, keys: tuple[str, ...]) -> tuple[list[dict[str, str]], int]:
    merged = list(current)
    seen = {tuple(row.get(key, "") for key in keys) for row in current}
    added = 0
    for row in incoming:
        key = tuple(row.get(field, "") for field in keys)
        if key in seen:
            continue
        seen.add(key)
        merged.append(row)
        added += 1
    return merged, added


def _write(path: Path, fields: tuple[str, ...], rows: list[dict[str, str]]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("w", encoding="utf-8", newline="") as handle:
        writer = csv.DictWriter(handle, fieldnames=fields, lineterminator="\n")
        writer.writeheader()
        writer.writerows({field: row.get(field, "") for field in fields} for row in rows)


def audit_and_promote(*, as_of_date: str, market_path: str | Path,
                      consensus_path: str | Path, consensus_evidence_path: str | Path,
                      target_evidence_path: str | Path,
                      provider_consensus_path: str | Path | None = None,
                      provider_consensus_evidence_path: str | Path | None = None,
                      provider_target_evidence_path: str | Path | None = None,
                      apply: bool = False) -> dict:
    """Preview or apply already-normalized provider rows without overwriting history."""
    if not any((provider_consensus_path, provider_consensus_evidence_path, provider_target_evidence_path)):
        raise ValueError("at_least_one_provider_file_required")
    consensus_file = Path(consensus_path)
    consensus_evidence_file = Path(consensus_evidence_path)
    target_file = Path(target_evidence_path)
    incoming_consensus = _read(provider_consensus_path)
    incoming_consensus_evidence = _read(provider_consensus_evidence_path)
    incoming_target = _read(provider_target_evidence_path)

    merged_consensus, consensus_added = _merge(
        _read(consensus_file), incoming_consensus,
        keys=("ticker", "fiscal_year", "available_at", "source"),
    )
    merged_consensus_evidence, consensus_evidence_added = _merge(
        _read(consensus_evidence_file), incoming_consensus_evidence,
        keys=("ticker", "fiscal_year", "source_family", "available_at", "source_url"),
    )
    merged_target, target_added = _merge(
        _read(target_file), incoming_target,
        keys=("ticker", "institution", "available_at", "target_price"),
    )

    stage_root = target_file.parent / ".provider_stage"
    staged_consensus = stage_root / "consensus.csv"
    staged_consensus_evidence = stage_root / "consensus_evidence.csv"
    staged_target = stage_root / "target_evidence.csv"
    _write(staged_consensus, CONSENSUS_FIELDS, sorted(
        merged_consensus, key=lambda row: (row.get("ticker", ""), row.get("fiscal_year", ""), row.get("available_at", ""), row.get("source", ""))))
    _write(staged_consensus_evidence, CONSENSUS_EVIDENCE_FIELDS, sorted(
        merged_consensus_evidence, key=lambda row: (row.get("ticker", ""), row.get("fiscal_year", ""), row.get("available_at", ""), row.get("source_family", ""))))
    _write(staged_target, TARGET_FIELDS, sorted(
        merged_target, key=lambda row: (row.get("ticker", ""), row.get("available_at", ""), row.get("institution", ""), row.get("target_price", ""))))

    consensus_result = load_consensus_csv(staged_consensus, as_of_date=as_of_date)
    _, evidence_rejected = load_consensus_evidence(staged_consensus_evidence, as_of_date=as_of_date)
    market = json.loads(Path(market_path).read_text(encoding="utf-8"))
    tickers = [str(row.get("ticker", "")).zfill(4) for row in market.get("rows", [])]
    target_snapshot = build_snapshot(
        date=as_of_date, market=market, tickers=tickers, evidence_path=staged_target,
    )
    rejected = [*consensus_result.rejected, *evidence_rejected]
    if rejected:
        return {
            "as_of_date": as_of_date, "status": "BLOCKED", "applied": False,
            "rejected": rejected, "future_data_violation_count": sum(
                row.get("error") == "future_data" for row in rejected),
            "formal_model_changed": False, "trade_decision_changed": False,
            "active_in_trade_decision": False, "report_changed": False,
        }

    if apply:
        _write(consensus_file, CONSENSUS_FIELDS, merged_consensus)
        _write(consensus_evidence_file, CONSENSUS_EVIDENCE_FIELDS, merged_consensus_evidence)
        _write(target_file, TARGET_FIELDS, merged_target)
    return {
        "as_of_date": as_of_date, "status": "READY", "applied": apply,
        "consensus_rows_added": consensus_added,
        "consensus_evidence_rows_added": consensus_evidence_added,
        "target_rows_added": target_added,
        "target_ready_ticker_count_after": target_snapshot["ready_ticker_count"],
        "target_requested_ticker_count": target_snapshot["requested_ticker_count"],
        "future_data_violation_count": 0,
        "formal_model_changed": False,
        "trade_decision_changed": False,
        "active_in_trade_decision": False,
        "report_changed": apply,
    }


def main() -> None:
    parser = argparse.ArgumentParser(description="Audit or promote normalized R1 provider data.")
    parser.add_argument("--as-of-date", required=True)
    parser.add_argument("--market", default="data/r1/daily_market_latest.json")
    parser.add_argument("--consensus", default="data/r1/consensus/consensus.csv")
    parser.add_argument("--consensus-evidence", default="data/r1/consensus/evidence.csv")
    parser.add_argument("--target-evidence", default="data/r1/target_prices/evidence.csv")
    parser.add_argument("--provider-consensus")
    parser.add_argument("--provider-consensus-evidence")
    parser.add_argument("--provider-target-evidence")
    parser.add_argument("--apply", action="store_true")
    args = parser.parse_args()
    result = audit_and_promote(
        as_of_date=args.as_of_date, market_path=args.market,
        consensus_path=args.consensus, consensus_evidence_path=args.consensus_evidence,
        target_evidence_path=args.target_evidence,
        provider_consensus_path=args.provider_consensus,
        provider_consensus_evidence_path=args.provider_consensus_evidence,
        provider_target_evidence_path=args.provider_target_evidence, apply=args.apply,
    )
    print(json.dumps(result, ensure_ascii=False))
    if result["status"] != "READY":
        raise SystemExit(75)


if __name__ == "__main__":
    main()
