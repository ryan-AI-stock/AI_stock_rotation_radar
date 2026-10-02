from __future__ import annotations

from dataclasses import dataclass
from datetime import date
import csv
from pathlib import Path

from r1.evidence import VALID_STAGES


@dataclass(frozen=True)
class BottleneckEvidence:
    ticker: str
    category: str
    stage: str
    thesis: str
    source_url: str
    source_family: str
    source_tier: int
    available_at: str


def load_bottleneck_evidence(path: str | Path, *, as_of_date: str) -> tuple[list[BottleneckEvidence], list[dict[str, str]]]:
    accepted: list[BottleneckEvidence] = []
    rejected: list[dict[str, str]] = []
    with Path(path).open(encoding="utf-8-sig", newline="") as handle:
        for line_no, row in enumerate(csv.DictReader(handle), start=2):
            try:
                required = ("ticker", "category", "stage", "thesis", "source_url", "source_family",
                            "source_tier", "published_at", "available_at", "retrieved_at", "evidence_status")
                missing = [key for key in required if not str(row.get(key, "")).strip()]
                if missing:
                    raise ValueError("missing:" + ",".join(missing))
                if row["stage"] not in VALID_STAGES:
                    raise ValueError("invalid_stage")
                if row["evidence_status"] != "VERIFIED":
                    raise ValueError("evidence_not_verified")
                tier = int(row["source_tier"])
                if tier not in {1, 2, 3, 4}:
                    raise ValueError("source_tier must be 1-4")
                if date.fromisoformat(row["available_at"][:10]) > date.fromisoformat(as_of_date):
                    raise ValueError("future_data")
                accepted.append(BottleneckEvidence(
                    ticker=row["ticker"].strip().zfill(4), category=row["category"].strip(),
                    stage=row["stage"].strip(), thesis=row["thesis"].strip(),
                    source_url=row["source_url"].strip(), source_family=row["source_family"].strip(),
                    source_tier=tier, available_at=row["available_at"][:10],
                ))
            except (KeyError, TypeError, ValueError) as exc:
                rejected.append({"line": str(line_no), "ticker": row.get("ticker", ""), "error": str(exc)})
    return accepted, rejected


def evidence_ready(rows: list[BottleneckEvidence], *, ticker: str) -> bool:
    ticker_rows = [row for row in rows if row.ticker == ticker]
    families = {row.source_family for row in ticker_rows}
    return len(families) >= 2 and any(row.source_tier <= 2 for row in ticker_rows)
