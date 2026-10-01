from __future__ import annotations

from abc import ABC, abstractmethod
from collections.abc import Iterable
from dataclasses import dataclass


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
