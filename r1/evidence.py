from __future__ import annotations

from dataclasses import dataclass
from datetime import date
import csv
from pathlib import Path


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


@dataclass(frozen=True)
class CatalystRecord:
    event: CatalystEvent
    source_family: str
    description: str
    impact_direction: str
    affected_bottleneck: str
    published_at: str
    available_at: str
    retrieved_at: str


def load_catalyst_csv(path: str | Path, *, as_of_date: str) -> tuple[list[CatalystRecord], list[dict[str, str]]]:
    """Load point-in-time catalyst evidence without converting bad rows to zero."""
    accepted: list[CatalystRecord] = []
    rejected: list[dict[str, str]] = []
    with Path(path).open(encoding="utf-8-sig", newline="") as handle:
        for line_no, row in enumerate(csv.DictReader(handle), start=2):
            try:
                required = ("event_date", "ticker", "event_type", "source_url", "source_family", "source_tier",
                            "impact_score", "confidence", "expiry_weeks", "published_at",
                            "available_at", "retrieved_at")
                missing = [key for key in required if not str(row.get(key, "")).strip()]
                if missing:
                    raise ValueError("missing:" + ",".join(missing))
                if date.fromisoformat(row["available_at"][:10]) > date.fromisoformat(as_of_date):
                    raise ValueError("future_data")
                event = CatalystEvent(
                    event_date=row["event_date"][:10], ticker=row["ticker"].strip(),
                    event_type=row["event_type"].strip(), impact_score=float(row["impact_score"]),
                    confidence=float(row["confidence"]), expiry_weeks=int(row["expiry_weeks"]),
                    source_tier=int(row["source_tier"]), source_url=row["source_url"].strip(),
                )
                event.score_at(as_of_date)
                accepted.append(CatalystRecord(
                    event=event, source_family=row["source_family"].strip(),
                    description=row.get("description", "").strip(),
                    impact_direction=row.get("impact_direction", "").strip(),
                    affected_bottleneck=row.get("affected_bottleneck", "").strip(),
                    published_at=row["published_at"], available_at=row["available_at"],
                    retrieved_at=row["retrieved_at"],
                ))
            except (KeyError, TypeError, ValueError) as exc:
                rejected.append({"line": str(line_no), "ticker": row.get("ticker", ""), "error": str(exc)})
    return accepted, rejected


def discovery_eligible(evidence: list[dict]) -> bool:
    independent = {row.get("source_family") for row in evidence if row.get("source_family")}
    authoritative = any(int(row.get("source_tier", 9)) <= 2 for row in evidence)
    return len(independent) >= 2 and authoritative
