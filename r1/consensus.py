from __future__ import annotations

import csv
from dataclasses import dataclass
from datetime import date
from pathlib import Path

from r1.providers import ConsensusRecord


@dataclass(frozen=True)
class ConsensusLoadResult:
    records: tuple[ConsensusRecord, ...]
    rejected: tuple[dict[str, str], ...]


def load_consensus_csv(path: str | Path, *, as_of_date: str) -> ConsensusLoadResult:
    """Read public estimate evidence with strict PIT and quality gates."""
    records: list[ConsensusRecord] = []
    rejected: list[dict[str, str]] = []
    with Path(path).open(encoding="utf-8-sig", newline="") as handle:
        for line_no, row in enumerate(csv.DictReader(handle), start=2):
            try:
                required = ("ticker", "fiscal_year", "mean_eps", "analyst_count", "source",
                            "published_at", "available_at", "retrieved_at", "quality", "status")
                missing = [key for key in required if not str(row.get(key, "")).strip()]
                if missing:
                    raise ValueError("missing:" + ",".join(missing))
                if date.fromisoformat(row["available_at"][:10]) > date.fromisoformat(as_of_date):
                    raise ValueError("future_data")
                quality = row["quality"].upper()
                if quality not in {"LOW", "MEDIUM", "HIGH"}:
                    raise ValueError("invalid_quality")
                analyst_count = int(row["analyst_count"])
                status = row["status"].upper()
                # Public-source records are actionable only after independent corroboration.
                if quality == "LOW" or analyst_count < 2:
                    status = "EVIDENCE_ONLY"
                records.append(ConsensusRecord(
                    ticker=row["ticker"].strip(), fiscal_year=int(row["fiscal_year"]),
                    mean_eps=float(row["mean_eps"]), median_eps=_optional_float(row.get("median_eps")),
                    high_eps=_optional_float(row.get("high_eps")), low_eps=_optional_float(row.get("low_eps")),
                    analyst_count=analyst_count, source=row["source"], published_at=row["published_at"],
                    available_at=row["available_at"], retrieved_at=row["retrieved_at"],
                    quality=quality, status=status,
                ))
            except (KeyError, TypeError, ValueError) as exc:
                rejected.append({"line": str(line_no), "ticker": row.get("ticker", ""), "error": str(exc)})
    return ConsensusLoadResult(tuple(records), tuple(rejected))


def consensus_actionable(records: list[ConsensusRecord] | tuple[ConsensusRecord, ...], *, ticker: str,
                         fiscal_year: int) -> bool:
    rows = [row for row in records if row.ticker == ticker and row.fiscal_year == fiscal_year]
    return any(row.quality in {"MEDIUM", "HIGH"} and row.analyst_count >= 2 and row.status == "READY" for row in rows)


def _optional_float(value: str | None) -> float | None:
    return None if value in {None, "", "NA", "NULL"} else float(value)
