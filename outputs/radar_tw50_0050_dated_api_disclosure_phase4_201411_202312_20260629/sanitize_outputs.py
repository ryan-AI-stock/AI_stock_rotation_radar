from __future__ import annotations

import csv
import json
from pathlib import Path

OUT = Path("outputs/radar_tw50_0050_dated_api_disclosure_phase4_201411_202312_20260629")


def read_csv(path: Path) -> list[dict]:
    with path.open("r", newline="", encoding="utf-8") as fh:
        return list(csv.DictReader(fh))


def write_csv(path: Path, rows: list[dict], fields: list[str]) -> None:
    with path.open("w", newline="", encoding="utf-8") as fh:
        writer = csv.DictWriter(fh, fieldnames=fields, extrasaction="ignore")
        writer.writeheader()
        writer.writerows(rows)


def valid_sample(row: dict) -> bool:
    name = row.get("name", "")
    weight = row.get("weight", "")
    if "endobj" in name.lower() or name.isdigit():
        return False
    try:
        weight_num = float(weight) if weight else 0.0
    except ValueError:
        return False
    return 0 < weight_num <= 100


def main() -> None:
    sample_fields = [
        "target_period",
        "holdings_date",
        "source_id",
        "source_file",
        "source_url",
        "ticker",
        "name",
        "weight",
        "source_type",
        "formal_exact",
        "evidence_quality",
        "parser_status",
        "notes",
    ]
    parsed = [row for row in read_csv(OUT / "parsed_holdings_sample.csv") if valid_sample(row)]
    accepted = [row for row in parsed if row.get("evidence_quality") == "accepted_date_matched"]
    write_csv(OUT / "parsed_holdings_sample.csv", parsed, sample_fields)
    write_csv(OUT / "accepted_historical_rows.csv", accepted, sample_fields)

    missing = read_csv(OUT / "missing_periods.csv")
    for row in missing:
        period = row["period_id"]
        parsed_count = sum(1 for item in parsed if item["target_period"] == period)
        accepted_count = sum(1 for item in accepted if item["target_period"] == period)
        row["parsed_sample_rows"] = str(parsed_count)
        row["accepted_rows"] = str(accepted_count)
        row["status"] = "accepted" if accepted_count else "missing_accepted_rows"
        row["blocker"] = "Dated API/disclosure probes did not return valid holdings rows with source_date/holdings_date equal to target period."
    write_csv(OUT / "missing_periods.csv", missing, list(missing[0].keys()))
    write_csv(OUT / "failed.csv", [row for row in missing if row["accepted_rows"] == "0"], list(missing[0].keys()))

    manifest = json.loads((OUT / "manifest.json").read_text(encoding="utf-8"))
    manifest["parsed_holdings_sample_rows"] = len(parsed)
    manifest["accepted_historical_rows"] = len(accepted)
    manifest["status"] = "completed_partial_no_valid_dated_rows"
    manifest["bogus_pdf_text_rows_removed"] = True
    (OUT / "manifest.json").write_text(json.dumps(manifest, ensure_ascii=False, indent=2), encoding="utf-8")

    completed = read_csv(OUT / "completed.csv")
    completed[0]["evidence"] = f"attempts={manifest['source_probe_attempt_count']} parsed={len(parsed)} accepted={len(accepted)}"
    write_csv(OUT / "completed.csv", completed, list(completed[0].keys()))
    print(json.dumps({"parsed_holdings_sample_rows": len(parsed), "accepted_historical_rows": len(accepted)}, ensure_ascii=False, indent=2))


if __name__ == "__main__":
    main()
