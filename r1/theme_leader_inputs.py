from __future__ import annotations

import argparse
import json
from pathlib import Path

from r1.theme_policy import LEADER_FIELDS, PRIORITY_FIELDS, leader_score, load_themes


ALL_FIELDS = (*LEADER_FIELDS, *PRIORITY_FIELDS)
EVIDENCE_FIELDS = ("source_url", "source_date", "available_at", "source_family", "evidence_note")


def materialize(*, as_of_date: str, theme_path: str | Path,
                source_path: str | Path, output_path: str | Path) -> dict:
    themes = load_themes(theme_path)
    members = {
        member.ticker: (member.company, theme.theme_id)
        for theme in themes for member in theme.members
    }
    source_file = Path(source_path)
    source_payload = json.loads(source_file.read_text(encoding="utf-8")) if source_file.exists() else {}
    source_rows = {
        str(row.get("ticker", "")).zfill(4): row for row in source_payload.get("rows", [])
    }
    extras = sorted(set(source_rows) - set(members))
    if extras:
        raise ValueError(f"theme leader input contains out-of-universe tickers: {extras}")

    rows = []
    rejected = []
    for ticker, (company, theme_id) in members.items():
        source = source_rows.get(ticker, {})
        evidence = source.get("evidence", {}) if isinstance(source.get("evidence"), dict) else {}
        row = {
            "ticker": ticker, "company": company, "theme_id": theme_id,
            "as_of_date": as_of_date, "evidence": evidence,
        }
        for field in ALL_FIELDS:
            value = source.get(field)
            if value is not None:
                value = float(value)
                if not 0 <= value <= 100:
                    raise ValueError(f"{ticker} {field} score must be within 0..100")
                proof = evidence.get(field)
                missing = [name for name in EVIDENCE_FIELDS if not isinstance(proof, dict) or not proof.get(name)]
                if missing:
                    raise ValueError(f"{ticker} {field} missing evidence fields: {missing}")
                if str(proof["available_at"]) > as_of_date:
                    raise ValueError(f"{ticker} {field} uses future evidence")
            row[field] = value
        structural = leader_score(row)
        if structural is not None:
            row["structural_leader"] = structural
        missing_fields = [field for field in ALL_FIELDS if row.get(field) is None]
        row["status"] = "READY" if not missing_fields else "DATA_MISSING"
        row["missing_fields"] = missing_fields
        if missing_fields:
            rejected.append({"ticker": ticker, "missing_fields": missing_fields})
        rows.append(row)

    payload = {
        "model": "R1", "version": "r1-theme-leader-input-v0.1", "as_of_date": as_of_date,
        "requested_ticker_count": len(members), "actual_ticker_count": len(rows),
        "complete_ticker_count": sum(row["status"] == "READY" for row in rows),
        "rows": rows, "data_gaps": rejected, "future_data_violation_count": 0,
        "formal_model_changed": False, "trade_decision_changed": False,
        "active_in_trade_decision": False, "report_changed": True,
    }
    output = Path(output_path)
    output.parent.mkdir(parents=True, exist_ok=True)
    output.write_text(json.dumps(payload, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    return payload


def main() -> None:
    parser = argparse.ArgumentParser(description="Materialize evidence-gated R1 theme leader inputs.")
    parser.add_argument("--date", required=True)
    parser.add_argument("--themes", default="config/r1_v02_themes.json")
    parser.add_argument("--source", default="data/r1/theme_leader_inputs/source.json")
    parser.add_argument("--output", default="data/r1/theme_leader_inputs/latest.json")
    args = parser.parse_args()
    payload = materialize(
        as_of_date=args.date, theme_path=args.themes,
        source_path=args.source, output_path=args.output,
    )
    print(json.dumps({
        "requested_ticker_count": payload["requested_ticker_count"],
        "complete_ticker_count": payload["complete_ticker_count"],
        "gap_count": len(payload["data_gaps"]),
    }, ensure_ascii=False))


if __name__ == "__main__":
    main()
