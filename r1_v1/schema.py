from __future__ import annotations

from dataclasses import asdict, dataclass, field
from datetime import datetime
from typing import Any


SOURCE_CLASSES = {
    "OFFICIAL", "EXCHANGE_MOPS", "CUSTOMER_OFFICIAL", "TIER1_NEWS",
    "INDUSTRY_RESEARCH", "BROKER_RESEARCH", "GENERAL_MEDIA", "SOCIAL", "RUMOR",
}
FACT_KINDS = {"ACTUAL", "FORECAST", "CONSENSUS", "OPINION", "RESEARCH_ESTIMATE"}
CLAIM_TYPES = {"FACTUAL_CLAIM", "FORECAST", "INTERPRETATION", "CAUSAL_CLAIM", "OPINION", "RUMOR"}
SCOPES = {"MARKET", "THEME", "COMPANY", "PRODUCT", "SUPPLY_CHAIN"}
HORIZONS = {"NOISE", "SHORT", "MEDIUM", "STRUCTURAL"}
DIRECTIONS = {"POSITIVE", "NEGATIVE", "MIXED", "UNKNOWN"}
LINK_STANCES = {"SUPPORTS", "CONTRADICTS"}


def _iso(value: str) -> datetime:
    return datetime.fromisoformat(str(value).replace("Z", "+00:00"))


def _pit(published_at: str | None, available_at: str, retrieved_at: str) -> None:
    available, retrieved = _iso(available_at), _iso(retrieved_at)
    if available > retrieved:
        raise ValueError("available_at_after_retrieved_at")
    if published_at and _iso(published_at) > available:
        raise ValueError("published_at_after_available_at")


@dataclass(frozen=True)
class EvidenceSource:
    source_id: str
    source_family: str
    source_name: str
    source_url: str
    published_at: str | None
    available_at: str
    retrieved_at: str
    reliability_class: str
    pit_valid: bool
    primary_source_id: str | None = None

    def validate(self) -> None:
        if self.reliability_class not in SOURCE_CLASSES:
            raise ValueError("unknown_reliability_class")
        _pit(self.published_at, self.available_at, self.retrieved_at)
        if not self.source_id or not self.source_url or not self.source_family:
            raise ValueError("source_identity_missing")


@dataclass(frozen=True)
class Fact:
    fact_id: str
    entity_type: str
    entity_id: str
    metric: str
    value: Any
    unit: str | None
    period: str | None
    source_id: str
    source_url: str
    source_date: str
    published_at: str | None
    available_at: str
    retrieved_at: str
    revision_id: str
    pit_valid: bool
    created_at: str
    fact_kind: str = "ACTUAL"
    previous_revision_id: str | None = None
    migration_status: str = "NATIVE"

    def validate(self) -> None:
        if self.fact_kind not in FACT_KINDS:
            raise ValueError("unknown_fact_kind")
        _pit(self.published_at, self.available_at, self.retrieved_at)
        if self.value is None:
            raise ValueError("fact_value_missing")
        forbidden = ("應該買", "應該賣", "看好", "看壞", "可能漲", "利多", "利空")
        if any(token in self.metric for token in forbidden):
            raise ValueError("opinion_forbidden_in_fact_metric")


@dataclass(frozen=True)
class Event:
    event_id: str
    canonical_event_id: str
    event_fingerprint: str
    event_type: str
    primary_entity: str
    related_entities: list[str]
    first_seen: str
    last_seen: str
    event_date: str
    published_at: str | None
    available_at: str
    status: str
    primary_source_id: str
    created_at: str
    updated_at: str
    product: str | None = None
    customer: str | None = None
    numbers: list[str] = field(default_factory=list)
    normalized_summary: str = ""


@dataclass(frozen=True)
class Claim:
    claim_id: str
    event_id: str
    claim_text: str
    claim_type: str
    direction: str
    scope: str
    time_horizon: str
    confidence: str
    status: str
    created_at: str
    updated_at: str
    traceable_source_id: str

    def validate(self) -> None:
        if self.claim_type not in CLAIM_TYPES:
            raise ValueError("unknown_claim_type")
        if self.direction not in DIRECTIONS or self.scope not in SCOPES or self.time_horizon not in HORIZONS:
            raise ValueError("claim_taxonomy_invalid")
        if self.confidence not in {"LOW", "MEDIUM", "HIGH"}:
            raise ValueError("claim_confidence_invalid")
        if not self.traceable_source_id:
            raise ValueError("llm_or_claim_source_missing")


@dataclass(frozen=True)
class EventClaimLink:
    event_id: str
    claim_id: str
    created_at: str


@dataclass(frozen=True)
class ClaimEvidenceLink:
    claim_id: str
    source_id: str
    stance: str
    primary_lineage_id: str
    created_at: str

    def validate(self) -> None:
        if self.stance not in LINK_STANCES:
            raise ValueError("claim_evidence_stance_invalid")


def record_dict(record: Any) -> dict[str, Any]:
    return asdict(record)
