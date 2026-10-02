from __future__ import annotations

from dataclasses import dataclass
from datetime import date
import csv
from pathlib import Path

from r1.evidence import VALID_EVENT_TYPES


@dataclass(frozen=True)
class CatalystEvidence:
    event_date: str
    ticker: str
    event_type: str
    description: str
    source_url: str
    source_family: str
    source_tier: int
    impact_direction: str
    affected_bottleneck: str
    available_at: str


def load_catalyst_evidence(path: str | Path, *, as_of_date: str) -> tuple[list[CatalystEvidence], list[dict[str, str]]]:
    """Load verified event evidence without inventing impact or confidence scores."""
    accepted: list[CatalystEvidence] = []
    rejected: list[dict[str, str]] = []
    with Path(path).open(encoding="utf-8-sig", newline="") as handle:
        for line_no, row in enumerate(csv.DictReader(handle), start=2):
            try:
                required = (
                    "event_date", "ticker", "event_type", "description", "source_url",
                    "source_family", "source_tier", "impact_direction", "affected_bottleneck",
                    "published_at", "available_at", "retrieved_at", "evidence_status",
                )
                missing = [key for key in required if not str(row.get(key, "")).strip()]
                if missing:
                    raise ValueError("missing:" + ",".join(missing))
                if row["event_type"] not in VALID_EVENT_TYPES:
                    raise ValueError("unknown_event_type")
                if row["evidence_status"] != "VERIFIED":
                    raise ValueError("evidence_not_verified")
                tier = int(row["source_tier"])
                if tier not in {1, 2, 3, 4}:
                    raise ValueError("source_tier must be 1-4")
                if date.fromisoformat(row["available_at"][:10]) > date.fromisoformat(as_of_date):
                    raise ValueError("future_data")
                accepted.append(CatalystEvidence(
                    event_date=row["event_date"][:10], ticker=row["ticker"].strip().zfill(4),
                    event_type=row["event_type"].strip(), description=row["description"].strip(),
                    source_url=row["source_url"].strip(), source_family=row["source_family"].strip(),
                    source_tier=tier, impact_direction=row["impact_direction"].strip(),
                    affected_bottleneck=row["affected_bottleneck"].strip(),
                    available_at=row["available_at"][:10],
                ))
            except (KeyError, TypeError, ValueError) as exc:
                rejected.append({"line": str(line_no), "ticker": row.get("ticker", ""), "error": str(exc)})
    return accepted, rejected


def evidence_ready(rows: list[CatalystEvidence], *, ticker: str) -> bool:
    ticker_rows = [row for row in rows if row.ticker == ticker]
    families = {row.source_family for row in ticker_rows}
    return len(families) >= 2 and any(row.source_tier <= 2 for row in ticker_rows)
