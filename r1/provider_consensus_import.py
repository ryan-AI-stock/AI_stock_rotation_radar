from __future__ import annotations

import argparse
import csv
import json
from datetime import date
from pathlib import Path

from r1.config import R1Config


FIELDS = (
    "ticker", "fiscal_year", "mean_eps", "median_eps", "high_eps", "low_eps",
    "analyst_count", "source_name", "source_url", "source_family", "source_tier",
    "published_at", "available_at", "retrieved_at", "quality", "status",
)


def import_provider_consensus(*, input_path: str | Path, as_of_date: str,
                              config_path: str | Path = "config/r1.json",
                              output_consensus: str | Path,
                              output_evidence: str | Path) -> dict:
    """Validate a vendor-neutral PIT export and materialize R1 input files.

    This importer never infers timestamps or fills missing estimates.  It writes
    only rows that pass the declared PIT and universe checks.
    """
    as_of = date.fromisoformat(as_of_date)
    allowed = {security.ticker for security in R1Config.load(config_path).securities}
    accepted: list[dict[str, str]] = []
    rejected: list[dict[str, str]] = []
    seen: set[tuple[str, str, str, str]] = set()

    with Path(input_path).open(encoding="utf-8-sig", newline="") as handle:
        reader = csv.DictReader(handle)
        missing_headers = [field for field in FIELDS if field not in (reader.fieldnames or [])]
        if missing_headers:
            raise ValueError("missing_headers:" + ",".join(missing_headers))
        for line_no, row in enumerate(reader, start=2):
            try:
                missing = [field for field in FIELDS if not str(row.get(field, "")).strip()]
                if missing:
                    raise ValueError("missing:" + ",".join(missing))
                ticker = row["ticker"].strip()
                if ticker not in allowed:
                    raise ValueError("ticker_not_in_r1_universe")
                fiscal_year = int(row["fiscal_year"])
                analyst_count = int(row["analyst_count"])
                source_tier = int(row["source_tier"])
                if analyst_count < 1:
                    raise ValueError("analyst_count_below_one")
                if source_tier not in {1, 2, 3, 4}:
                    raise ValueError("invalid_source_tier")
                for field in ("mean_eps", "median_eps", "high_eps", "low_eps"):
                    float(row[field])
                available = date.fromisoformat(row["available_at"][:10])
                published = date.fromisoformat(row["published_at"][:10])
                retrieved = date.fromisoformat(row["retrieved_at"][:10])
                if available > as_of or published > as_of or retrieved > date.today():
                    raise ValueError("future_data")
                if available < published:
                    raise ValueError("available_before_published")
                quality = row["quality"].upper()
                status = row["status"].upper()
                if quality not in {"LOW", "MEDIUM", "HIGH"}:
                    raise ValueError("invalid_quality")
                if status not in {"READY", "PARTIAL", "EVIDENCE_ONLY"}:
                    raise ValueError("invalid_status")
                key = (ticker, str(fiscal_year), row["available_at"], row["source_family"])
                if key in seen:
                    raise ValueError("duplicate_observation")
                seen.add(key)
                accepted.append({**row, "ticker": ticker, "fiscal_year": str(fiscal_year),
                                 "analyst_count": str(analyst_count), "source_tier": str(source_tier),
                                 "quality": quality, "status": status})
            except (TypeError, ValueError) as exc:
                rejected.append({"line": str(line_no), "ticker": row.get("ticker", ""), "error": str(exc)})

    _write_consensus(output_consensus, accepted)
    _write_evidence(output_evidence, accepted)
    return {
        "as_of_date": as_of_date,
        "input_rows": len(accepted) + len(rejected),
        "accepted_rows": len(accepted),
        "rejected_rows": len(rejected),
        "accepted_tickers": sorted({row["ticker"] for row in accepted}),
        "rejected": rejected,
        "future_data_violation_count": sum(row["error"] == "future_data" for row in rejected),
        "formal_model_changed": False,
        "trade_decision_changed": False,
        "active_in_trade_decision": False,
        "report_changed": False,
    }


def _write_consensus(path: str | Path, rows: list[dict[str, str]]) -> None:
    fields = ("ticker", "fiscal_year", "mean_eps", "median_eps", "high_eps", "low_eps", "analyst_count",
              "source", "published_at", "available_at", "retrieved_at", "quality", "status")
    output = Path(path)
    output.parent.mkdir(parents=True, exist_ok=True)
    with output.open("w", encoding="utf-8", newline="") as handle:
        writer = csv.DictWriter(handle, fieldnames=fields)
        writer.writeheader()
        for row in rows:
            writer.writerow({**{field: row.get(field, "") for field in fields}, "source": row["source_name"]})


def _write_evidence(path: str | Path, rows: list[dict[str, str]]) -> None:
    fields = ("ticker", "fiscal_year", "source_url", "source_family", "source_tier", "available_at", "note")
    output = Path(path)
    output.parent.mkdir(parents=True, exist_ok=True)
    with output.open("w", encoding="utf-8", newline="") as handle:
        writer = csv.DictWriter(handle, fieldnames=fields)
        writer.writeheader()
        for row in rows:
            writer.writerow({**{field: row.get(field, "") for field in fields},
                             "note": f"provider import; quality={row['quality']}; status={row['status']}"})


def main() -> None:
    parser = argparse.ArgumentParser(description="Validate and normalize an R1 PIT consensus provider export.")
    parser.add_argument("--input", required=True)
    parser.add_argument("--as-of-date", required=True)
    parser.add_argument("--config", default="config/r1.json")
    parser.add_argument("--output-consensus", required=True)
    parser.add_argument("--output-evidence", required=True)
    args = parser.parse_args()
    print(json.dumps(import_provider_consensus(
        input_path=args.input, as_of_date=args.as_of_date, config_path=args.config,
        output_consensus=args.output_consensus, output_evidence=args.output_evidence,
    ), ensure_ascii=False))


if __name__ == "__main__":
    main()
