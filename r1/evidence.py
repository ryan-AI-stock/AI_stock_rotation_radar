from __future__ import annotations

from dataclasses import dataclass
from datetime import date


VALID_EVENT_TYPES = {
    "DESIGN_WIN", "CUSTOMER_PREPAY", "LONG_TERM_AGREEMENT", "STRATEGIC_INVESTMENT",
    "CAPACITY_EXPANSION", "CAPACITY_TIGHTNESS", "PRICE_INCREASE", "ASP_INCREASE",
    "MASS_PRODUCTION", "QUALIFICATION", "TAPE_OUT", "NEW_PRODUCT", "CAPEX_UP", "CAPEX_DOWN",
    "GUIDANCE_UP", "GUIDANCE_DOWN", "COMPETITOR_EXPANSION", "SUPPLY_SHORTAGE",
    "SUPPLY_NORMALIZATION", "CUSTOMER_LOSS", "DELAY", "NEGATIVE",
}
VALID_STAGES = {"THESIS", "QUALIFICATION", "SAMPLE", "TAPE_OUT", "SMALL_VOLUME", "MASS_PRODUCTION", "FINANCIAL_PROOF"}


@dataclass(frozen=True)
class CatalystEvent:
    event_date: str
    ticker: str
    event_type: str
    impact_score: float
    confidence: float
    expiry_weeks: int
    source_tier: int
    source_url: str

    def score_at(self, as_of_date: str) -> float:
        if self.event_type not in VALID_EVENT_TYPES:
            raise ValueError(f"unknown event type: {self.event_type}")
        if self.source_tier not in {1, 2, 3, 4}:
            raise ValueError("source tier must be 1-4")
        if self.source_tier == 4:
            return 0.0
        age_days = (date.fromisoformat(as_of_date) - date.fromisoformat(self.event_date)).days
        if age_days < 0:
            raise ValueError("future catalyst event rejected")
        lifespan = max(1, self.expiry_weeks * 7)
        decay = max(0.0, 1.0 - age_days / lifespan)
        tier_weight = {1: 1.0, 2: 0.8, 3: 0.5}[self.source_tier]
        return self.impact_score * self.confidence * decay * tier_weight


def discovery_eligible(evidence: list[dict]) -> bool:
    independent = {row.get("source_url") for row in evidence if row.get("source_url")}
    authoritative = any(int(row.get("source_tier", 9)) <= 2 for row in evidence)
    return len(independent) >= 2 and authoritative
