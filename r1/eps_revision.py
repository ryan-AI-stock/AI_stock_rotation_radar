from __future__ import annotations

from datetime import date, timedelta

from r1.providers import ConsensusProvider, ConsensusRecord


def revision_features(
    provider: ConsensusProvider, *, ticker: str, fiscal_year: int, as_of_date: str,
) -> dict[str, float | int | str | None]:
    current_day = date.fromisoformat(as_of_date)
    current = _one(provider.fetch([ticker], as_of_date), ticker, fiscal_year)
    result: dict[str, float | int | str | None] = {
        "ticker": ticker, "fiscal_year": fiscal_year, "as_of_date": as_of_date,
        "mean_eps": current.mean_eps if current else None,
        "analyst_count": current.analyst_count if current else None,
        "quality": current.quality if current else "LOW",
        "status": current.status if current else "DATA_MISSING",
    }
    for label, days in (("1w", 7), ("4w", 28), ("12w", 84)):
        prior_date = (current_day - timedelta(days=days)).isoformat()
        prior = _one(provider.fetch([ticker], prior_date), ticker, fiscal_year)
        result[f"revision_{label}"] = _change(current.mean_eps if current else None, prior.mean_eps if prior else None)
    return result


def _one(rows: list[ConsensusRecord], ticker: str, fiscal_year: int) -> ConsensusRecord | None:
    return next((row for row in rows if row.ticker == ticker and row.fiscal_year == fiscal_year), None)


def _change(current: float | None, prior: float | None) -> float | None:
    if current is None or prior in {None, 0}:
        return None
    return current / prior - 1
