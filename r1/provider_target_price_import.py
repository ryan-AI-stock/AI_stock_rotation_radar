from __future__ import annotations

import argparse
import csv
import json
from datetime import date
from pathlib import Path

from r1.config import R1Config


FIELDS = (
    "ticker", "institution", "target_price", "horizon", "published_at",
    "available_at", "retrieved_at", "source_url", "source_family",
    "source_tier", "quality", "status",
)


def import_provider_target_prices(*, input_path: str | Path, as_of_date: str,
                                  config_path: str | Path = "config/r1.json",
                                  output_evidence: str | Path) -> dict:
    """Validate a vendor PIT export and write isolated R1 target-price evidence."""
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
                ticker = row["ticker"].strip().zfill(4)
                if ticker not in allowed:
                    raise ValueError("ticker_not_in_r1_universe")
                institution = row["institution"].strip()
                if not institution:
                    raise ValueError("institution_missing")
                target_price = float(row["target_price"])
                if target_price <= 0:
                    raise ValueError("target_price_not_positive")
                if row["horizon"].strip().upper() != "12M":
                    raise ValueError("horizon_not_12m")
                source_tier = int(row["source_tier"])
                if source_tier not in {1, 2, 3, 4}:
                    raise ValueError("invalid_source_tier")
                published = date.fromisoformat(row["published_at"][:10])
                available = date.fromisoformat(row["available_at"][:10])
                retrieved = date.fromisoformat(row["retrieved_at"][:10])
                if published > as_of or available > as_of or retrieved > date.today():
                    raise ValueError("future_data")
                if available < published:
                    raise ValueError("available_before_published")
                quality = row["quality"].upper()
                status = row["status"].upper()
                if quality not in {"LOW", "MEDIUM", "HIGH"}:
                    raise ValueError("invalid_quality")
                if status not in {"READY", "PARTIAL", "EVIDENCE_ONLY"}:
                    raise ValueError("invalid_status")
                key = (ticker, institution, row["available_at"], f"{target_price:g}")
                if key in seen:
                    raise ValueError("duplicate_observation")
                seen.add(key)
                accepted.append({
                    **row, "ticker": ticker, "institution": institution,
                    "target_price": f"{target_price:g}", "horizon": "12M",
                    "source_tier": str(source_tier), "quality": quality, "status": status,
                })
            except (TypeError, ValueError) as exc:
                rejected.append({"line": str(line_no), "ticker": row.get("ticker", ""), "error": str(exc)})

    fields = (
        "ticker", "institution", "target_price", "horizon", "available_at",
        "source_url", "retrieved_at", "note",
    )
    output = Path(output_evidence)
    output.parent.mkdir(parents=True, exist_ok=True)
    with output.open("w", encoding="utf-8", newline="") as handle:
        writer = csv.DictWriter(handle, fieldnames=fields, lineterminator="\n")
        writer.writeheader()
        for row in accepted:
            writer.writerow({
                **{field: row.get(field, "") for field in fields},
                "note": (
                    f"provider import; family={row['source_family']}; tier={row['source_tier']}; "
                    f"quality={row['quality']}; status={row['status']}"
                ),
            })
    return {
        "as_of_date": as_of_date,
        "input_rows": len(accepted) + len(rejected),
        "accepted_rows": len(accepted),
        "rejected_rows": len(rejected),
        "accepted_tickers": sorted({row["ticker"] for row in accepted}),
        "accepted_institution_count": len({row["institution"] for row in accepted}),
        "rejected": rejected,
        "future_data_violation_count": sum(row["error"] == "future_data" for row in rejected),
        "formal_model_changed": False,
        "trade_decision_changed": False,
        "active_in_trade_decision": False,
        "report_changed": False,
    }


def main() -> None:
    parser = argparse.ArgumentParser(description="Validate and normalize an R1 PIT target-price provider export.")
    parser.add_argument("--input", required=True)
    parser.add_argument("--as-of-date", required=True)
    parser.add_argument("--config", default="config/r1.json")
    parser.add_argument("--output-evidence", required=True)
    args = parser.parse_args()
    print(json.dumps(import_provider_target_prices(
        input_path=args.input, as_of_date=args.as_of_date, config_path=args.config,
        output_evidence=args.output_evidence,
    ), ensure_ascii=False))


if __name__ == "__main__":
    main()
