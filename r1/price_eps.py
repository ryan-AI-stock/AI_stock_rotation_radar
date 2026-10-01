from __future__ import annotations

from dataclasses import dataclass


@dataclass(frozen=True)
class PriceEpsGap:
    price_change: float | None
    eps_revision: float | None
    earnings_minus_price: float | None
    state: str


def price_eps_gap(*, price_change: float | None, eps_revision: float | None) -> PriceEpsGap:
    """Compare like-for-like horizon changes; positive gap means earnings lead price."""
    if price_change is None or eps_revision is None:
        return PriceEpsGap(price_change, eps_revision, None, "DATA_MISSING")
    gap = eps_revision - price_change
    if gap > 0:
        state = "EARNINGS_CATCH_UP"
    elif gap < 0:
        state = "VALUATION_EXPANSION"
    else:
        state = "ALIGNED"
    return PriceEpsGap(price_change, eps_revision, gap, state)


def percentile_rank(history: list[float], current: float | None) -> float | None:
    """Return an empirical 0..1 percentile; callers control the PIT history window."""
    if current is None or not history:
        return None
    return sum(value <= current for value in history) / len(history)
