from __future__ import annotations

import csv
from dataclasses import dataclass
from pathlib import Path


@dataclass(frozen=True)
class QuoteSnapshot:
    quote_date: str = ""
    quote_time: str = ""

    @property
    def normalized_date(self) -> str:
        return normalize_quote_date(self.quote_date)


def load_quote_snapshot(path: str | Path) -> QuoteSnapshot:
    csv_path = Path(path)
    if not csv_path.exists():
        return QuoteSnapshot()
    with csv_path.open("r", encoding="utf-8-sig", newline="") as handle:
        for row in csv.DictReader(handle):
            quote_date = str(row.get("quote_date", "")).strip()
            quote_time = str(row.get("quote_time", "")).strip()
            if quote_date or quote_time:
                return QuoteSnapshot(quote_date=quote_date, quote_time=quote_time)
    return QuoteSnapshot()


def normalize_quote_date(raw: str) -> str:
    value = str(raw).strip()
    if len(value) == 8 and value.isdigit():
        return f"{value[:4]}-{value[4:6]}-{value[6:]}"
    return value


def quote_date_mismatch_message(snapshot: QuoteSnapshot, target_date: str) -> str:
    return (
        f"Latest market quote date {snapshot.normalized_date or 'missing'} "
        f"does not match target report date {target_date}; retry later."
    )
