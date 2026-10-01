from __future__ import annotations

from abc import ABC, abstractmethod
import csv
from collections.abc import Iterable
from dataclasses import dataclass
from pathlib import Path


@dataclass(frozen=True)
class ConsensusRecord:
    ticker: str
    fiscal_year: int
    mean_eps: float | None
    median_eps: float | None
    high_eps: float | None
    low_eps: float | None
    analyst_count: int | None
    source: str
    published_at: str | None
    available_at: str
    retrieved_at: str
    quality: str
    status: str


class ConsensusProvider(ABC):
    @abstractmethod
    def fetch(self, tickers: Iterable[str], as_of_date: str) -> list[ConsensusRecord]:
        """Return PIT records only; unavailable values remain None, never zero."""
        raise NotImplementedError


class MissingConsensusProvider(ConsensusProvider):
    """Safe default until a licensed or user-supplied provider is configured."""

    def fetch(self, tickers: Iterable[str], as_of_date: str) -> list[ConsensusRecord]:
        return [
            ConsensusRecord(
                ticker=ticker,
                fiscal_year=0,
                mean_eps=None,
                median_eps=None,
                high_eps=None,
                low_eps=None,
                analyst_count=None,
                source="UNCONFIGURED",
                published_at=None,
                available_at=f"{as_of_date}T00:00:00+08:00",
                retrieved_at=f"{as_of_date}T00:00:00+08:00",
                quality="LOW",
                status="DATA_MISSING",
            )
            for ticker in tickers
        ]


class CsvConsensusProvider(ConsensusProvider):
    """Import licensed or public-source records without inventing consensus."""

    def __init__(self, path: str | Path) -> None:
        self.path = Path(path)

    def fetch(self, tickers: Iterable[str], as_of_date: str) -> list[ConsensusRecord]:
        wanted = set(tickers)
        latest: dict[tuple[str, int], ConsensusRecord] = {}
        if not self.path.exists():
            return MissingConsensusProvider().fetch(sorted(wanted), as_of_date)
        with self.path.open(encoding="utf-8-sig", newline="") as handle:
            for row in csv.DictReader(handle):
                ticker = str(row.get("ticker", "")).zfill(4)
                available_at = row.get("available_at", "")
                if ticker not in wanted or not available_at or available_at[:10] > as_of_date:
                    continue
                fiscal_year = int(row["fiscal_year"])
                record = ConsensusRecord(
                    ticker=ticker, fiscal_year=fiscal_year,
                    mean_eps=_float(row.get("mean_eps")), median_eps=_float(row.get("median_eps")),
                    high_eps=_float(row.get("high_eps")), low_eps=_float(row.get("low_eps")),
                    analyst_count=_int(row.get("analyst_count")), source=row.get("source", ""),
                    published_at=row.get("published_at") or None, available_at=available_at,
                    retrieved_at=row.get("retrieved_at", ""), quality=row.get("quality", "LOW"),
                    status=row.get("status", "DATA_MISSING"),
                )
                key = (ticker, fiscal_year)
                if key not in latest or record.available_at > latest[key].available_at:
                    latest[key] = record
        return sorted(latest.values(), key=lambda row: (row.ticker, row.fiscal_year))


def _float(value: str | None) -> float | None:
    return None if value in {None, "", "NA", "NULL"} else float(value)


def _int(value: str | None) -> int | None:
    return None if value in {None, "", "NA", "NULL"} else int(value)
