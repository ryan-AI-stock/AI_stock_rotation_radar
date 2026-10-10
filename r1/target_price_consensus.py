from __future__ import annotations

from dataclasses import dataclass
from datetime import date
from statistics import median


@dataclass(frozen=True)
class TargetPriceRecord:
    ticker: str
    institution: str
    target_price: float
    horizon: str
    available_at: str
    source_url: str


def build_consensus(*, records: list[TargetPriceRecord], ticker: str, current_price: float,
                    as_of_date: str, minimum_institutions: int = 3,
                    maximum_age_days: int = 90) -> dict:
    asof = date.fromisoformat(as_of_date)
    accepted: dict[str, TargetPriceRecord] = {}
    rejected: list[dict[str, str]] = []
    for row in records:
        if row.ticker != ticker:
            continue
        try:
            available = date.fromisoformat(row.available_at[:10])
            age = (asof - available).days
            if age < 0:
                raise ValueError("future_data")
            if age > maximum_age_days:
                raise ValueError("stale")
            if row.horizon.upper() != "12M":
                raise ValueError("horizon_not_12m")
            if not row.institution.strip() or not row.source_url.strip() or row.target_price <= 0:
                raise ValueError("identity_price_or_source_missing")
            previous = accepted.get(row.institution.strip())
            if previous is None or row.available_at > previous.available_at:
                accepted[row.institution.strip()] = row
        except ValueError as exc:
            rejected.append({"institution": row.institution, "error": str(exc)})
    values = [row.target_price for row in accepted.values()]
    ready = len(values) >= minimum_institutions and current_price > 0
    consensus = median(values) if values else None
    upside = consensus / current_price - 1 if ready else None
    dispersion = ((max(values) - min(values)) / consensus) if ready and consensus else None
    return {
        "ticker": ticker,
        "as_of_date": as_of_date,
        "institution_count": len(values),
        "consensus_target_price": consensus,
        "consensus_upside": upside,
        "dispersion": dispersion,
        "status": "READY" if ready else "DATA_MISSING",
        "scoreable": ready,
        "rejected": rejected,
        "source_policy": "12M median; independent identifiable institutions; PIT max 90 days",
    }
