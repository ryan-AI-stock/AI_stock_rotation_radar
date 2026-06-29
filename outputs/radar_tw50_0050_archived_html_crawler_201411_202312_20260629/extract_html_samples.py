from __future__ import annotations

import csv
import json
import re
from datetime import datetime
from pathlib import Path

OUT = Path("outputs/radar_tw50_0050_archived_html_crawler_201411_202312_20260629")


def decode_text(body: bytes) -> str:
    return body.decode("utf-8", errors="replace")


def write_csv(path: Path, rows: list[dict], fields: list[str]) -> None:
    with path.open("w", newline="", encoding="utf-8") as fh:
        writer = csv.DictWriter(fh, fieldnames=fields, extrasaction="ignore")
        writer.writeheader()
        writer.writerows(rows)


def read_csv(path: Path) -> list[dict]:
    with path.open("r", newline="", encoding="utf-8") as fh:
        return list(csv.DictReader(fh))


def extract_html_holdings_rows(text: str) -> list[dict]:
    rows: list[dict] = []
    tr_blocks = re.findall(r'<div class="tr"[^>]*>(.*?)</div></div>', text, flags=re.I | re.S)
    for block in tr_blocks:
        values = [re.sub(r"<[^>]+>", "", v).strip() for v in re.findall(r"<span[^>]*>(.*?)</span>", block, flags=re.I | re.S)]
        values = [v for v in values if v and "商品" not in v]
        if len(values) < 4:
            continue
        ticker, name, _quantity, weight = values[:4]
        if not re.fullmatch(r"\d{4}", ticker):
            continue
        try:
            weight_num = float(weight.replace(",", ""))
        except ValueError:
            continue
        if not 0 < weight_num <= 100:
            continue
        rows.append({"ticker": ticker, "name": name, "weight": str(weight_num)})
    return rows


def source_id_to_snapshot_date(source_id: str) -> str:
    match = re.search(r"_(20\d{12})", source_id)
    if not match:
        return ""
    return datetime.strptime(match.group(1)[:8], "%Y%m%d").date().isoformat()


def main() -> None:
    raw_manifest = read_csv(OUT / "raw_source_archive_manifest.csv")
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
    parsed_rows: list[dict] = []
    accepted_rows: list[dict] = []
    seen_sample_keys: set[tuple[str, str, str]] = set()

    for source in raw_manifest:
        if source.get("source_type") != "download_candidate_non_pdf":
            continue
        raw_path = Path(source["raw_file_path"])
        if not raw_path.exists() or raw_path.suffix.lower() != ".html":
            continue
        lower_name = raw_path.name.lower()
        if not any(token in lower_name for token in ("ratio", "pcf", "tradeinfo")):
            continue
        rows = extract_html_holdings_rows(decode_text(raw_path.read_bytes()))
        if not rows:
            continue
        period = source["source_id"].split("_", 1)[0]
        snapshot_date = source_id_to_snapshot_date(source["source_id"])
        for row in rows[:20]:
            key = (period, source["source_id"], row["ticker"])
            if key in seen_sample_keys:
                continue
            seen_sample_keys.add(key)
            parsed_rows.append(
                {
                    "target_period": period,
                    "holdings_date": snapshot_date,
                    "source_id": source["source_id"],
                    "source_file": source["raw_file_path"],
                    "source_url": source["source_url_or_reference"],
                    "ticker": row["ticker"],
                    "name": row["name"],
                    "weight": row["weight"],
                    "source_type": "source_backed_manual_proxy",
                    "formal_exact": "false",
                    "evidence_quality": "html_table_sample_snapshot_date_not_target_date",
                    "parser_status": "html_holdings_table_sample_extracted",
                    "notes": "Extracted from archived Yuanta ratio/PCF HTML SSR table. Sample evidence only; snapshot date may differ from target period holdings date and is not accepted as PIT exact.",
                }
            )

    write_csv(OUT / "parsed_holdings_sample.csv", parsed_rows, sample_fields)
    write_csv(OUT / "accepted_historical_rows.csv", accepted_rows, sample_fields)

    missing = read_csv(OUT / "missing_periods.csv")
    for row in missing:
        period = row["period_id"]
        parsed_count = sum(1 for item in parsed_rows if item["target_period"] == period)
        row["parsed_sample_rows"] = str(parsed_count)
        row["accepted_rows"] = "0"
        if parsed_count:
            row["status"] = "parsed_sample_needs_review"
            row["blocker"] = "Archived Yuanta HTML contains holdings sample rows, but snapshots are closest-route evidence and not dated to the requested target period; accepted PIT rows remain zero."
        row["next_programmatic_attempt"] = "Query TWSE/Taiwan Index/issuer/regulator endpoints for dated holdings or monthly portfolio files; broaden Wayback to archived API JSON endpoints and sitemap pages, then require holdings_date match before acceptance."
    write_csv(OUT / "missing_periods.csv", missing, list(missing[0].keys()))

    manifest = json.loads((OUT / "manifest.json").read_text(encoding="utf-8"))
    manifest["parsed_holdings_sample_rows"] = len(parsed_rows)
    manifest["accepted_historical_rows"] = 0
    manifest["status"] = "completed_partial_samples_extracted_no_accepted_rows"
    manifest["html_table_sample_extracted"] = bool(parsed_rows)
    (OUT / "manifest.json").write_text(json.dumps(manifest, ensure_ascii=False, indent=2), encoding="utf-8")
    print(json.dumps({"parsed_holdings_sample_rows": len(parsed_rows), "accepted_historical_rows": 0}, ensure_ascii=False, indent=2))


if __name__ == "__main__":
    main()
