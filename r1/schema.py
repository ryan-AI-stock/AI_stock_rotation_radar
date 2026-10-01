from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime
from typing import Any


PIT_FIELDS = ("source", "as_of_date", "published_at", "available_at", "retrieved_at", "quality")
CONSENSUS_STATUSES = {"AVAILABLE", "DATA_MISSING", "SOURCE_LOW_CONFIDENCE"}


@dataclass(frozen=True)
class DataLineage:
    source: str
    as_of_date: str
    published_at: str | None
    available_at: str
    retrieved_at: str
    quality: str


def validate_lineage(row: dict[str, Any]) -> None:
    missing = [field for field in PIT_FIELDS if field not in row]
    if missing:
        raise ValueError(f"missing PIT lineage fields: {missing}")
    available = _time(row["available_at"])
    retrieved = _time(row["retrieved_at"])
    if available > retrieved:
        raise ValueError("available_at cannot be after retrieved_at")
    if row.get("published_at") and _time(row["published_at"]) > available:
        raise ValueError("published_at cannot be after available_at")


def consensus_allows_action(row: dict[str, Any]) -> bool:
    """R1 must not issue ADD/TRIM/EXIT without usable consensus evidence."""
    if row.get("status") != "AVAILABLE":
        return False
    if row.get("quality") not in {"HIGH", "MEDIUM"}:
        return False
    if not row.get("analyst_count") or int(row["analyst_count"]) < 2:
        return False
    return row.get("mean_eps") is not None and bool(row.get("fiscal_year"))


def _time(value: str) -> datetime:
    return datetime.fromisoformat(str(value).replace("Z", "+00:00"))
