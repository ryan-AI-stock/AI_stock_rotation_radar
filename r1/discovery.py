from __future__ import annotations

import argparse
import csv
from collections import defaultdict
from datetime import date
import json
from pathlib import Path

from r1.evidence import discovery_eligible


REQUIRED_FIELDS = (
    "discovery_date", "ticker", "company", "bottleneck", "reason", "causal_chain",
    "source_url", "source_family", "source_tier", "published_at", "available_at",
    "retrieved_at", "evidence_status",
)


def build_discovery_pool(path: str | Path, *, as_of_date: str) -> dict:
    cutoff = date.fromisoformat(as_of_date)
    accepted: list[dict] = []
    rejected: list[dict[str, str]] = []
    source_path = Path(path)

    if source_path.exists():
        with source_path.open(encoding="utf-8-sig", newline="") as handle:
            for line_no, row in enumerate(csv.DictReader(handle), start=2):
                try:
                    missing = [field for field in REQUIRED_FIELDS if not str(row.get(field, "")).strip()]
                    if missing:
                        raise ValueError("missing:" + ",".join(missing))
                    tier = int(row["source_tier"])
                    if tier not in {1, 2, 3, 4}:
                        raise ValueError("source_tier_must_be_1_to_4")
                    if row["evidence_status"].strip().upper() != "VERIFIED":
                        raise ValueError("evidence_not_verified")
                    if date.fromisoformat(row["available_at"][:10]) > cutoff:
                        raise ValueError("future_data")
                    if date.fromisoformat(row["discovery_date"][:10]) > cutoff:
                        raise ValueError("future_discovery_date")
                    clean = {key: str(value or "").strip() for key, value in row.items() if key}
                    clean["source_tier"] = tier
                    accepted.append(clean)
                except (TypeError, ValueError) as exc:
                    rejected.append({
                        "line": str(line_no),
                        "ticker": str(row.get("ticker", "")).strip(),
                        "error": str(exc),
                    })

    grouped: dict[str, list[dict]] = defaultdict(list)
    for row in accepted:
        grouped[row["ticker"]].append(row)

    candidates = []
    for ticker in sorted(grouped):
        evidence = grouped[ticker]
        eligible = discovery_eligible(evidence)
        first = evidence[0]
        candidates.append({
            "ticker": ticker,
            "company": first["company"],
            "bottleneck": first["bottleneck"],
            "reason": first["reason"],
            "causal_chain": first["causal_chain"],
            "status": "ELIGIBLE_FOR_RYAN_REVIEW" if eligible else "DISCOVERY_POOL_EVIDENCE_GAP",
            "independent_source_family_count": len({row["source_family"] for row in evidence}),
            "authoritative_source_present": any(row["source_tier"] <= 2 for row in evidence),
            "evidence_count": len(evidence),
            "evidence": evidence,
            "universe_admission": False,
        })

    return {
        "as_of_date": as_of_date,
        "status": "DISCOVERY_REVIEW_ONLY",
        "policy": "Ryan approval is required; discovery evidence never changes the R1 universe automatically.",
        "candidates": candidates,
        "rejected_rows": rejected,
        "formal_model_changed": False,
        "trade_decision_changed": False,
        "active_in_trade_decision": False,
        "report_changed": False,
    }


def main() -> None:
    parser = argparse.ArgumentParser(description="Build the evidence-gated R1 discovery review pool.")
    parser.add_argument("--date", required=True)
    parser.add_argument("--evidence", default="data/r1/discovery/evidence.csv")
    parser.add_argument("--output", default="data/r1/discovery_pool.json")
    args = parser.parse_args()
    payload = build_discovery_pool(args.evidence, as_of_date=args.date)
    output = Path(args.output)
    output.parent.mkdir(parents=True, exist_ok=True)
    output.write_text(json.dumps(payload, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    print(json.dumps({
        "as_of_date": args.date,
        "candidate_count": len(payload["candidates"]),
        "review_ready_count": sum(row["status"] == "ELIGIBLE_FOR_RYAN_REVIEW" for row in payload["candidates"]),
        "rejected_count": len(payload["rejected_rows"]),
        "output": str(output),
    }, ensure_ascii=False))


if __name__ == "__main__":
    main()
