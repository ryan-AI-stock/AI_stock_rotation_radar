from __future__ import annotations

from dataclasses import asdict
from datetime import datetime
from typing import Any

from .dedup import compare_events, event_fingerprint
from .ids import normalize_text, stable_id
from .schema import (Claim, ClaimEvidenceLink, Event, EventClaimLink, EvidenceSource,
                     Fact, record_dict)
from .store import EvidenceStore, now_iso


def _dt(value: str) -> datetime:
    return datetime.fromisoformat(str(value).replace("Z", "+00:00"))


class EvidencePipeline:
    def __init__(self, store: EvidenceStore, evaluation_time: str, actor: str = "r1_v1_pipeline"):
        self.store, self.evaluation_time, self.actor = store, evaluation_time, actor

    def _pit_ok(self, available_at: str, payload: dict[str, Any], source_ref: str | None) -> bool:
        if _dt(available_at) > _dt(self.evaluation_time):
            self.store.reject(reason="FUTURE_DATA_VIOLATION", payload=payload,
                              actor=self.actor, source_reference=source_ref)
            return False
        return True

    def add_source(self, source: EvidenceSource) -> bool:
        source.validate()
        if not self._pit_ok(source.available_at, record_dict(source), source.source_url):
            return False
        added = self.store.append("sources", source)
        if added:
            self.store.audit(action="CREATE", entity_type="SOURCE", entity_id=source.source_id,
                             actor=self.actor, reason="PIT_VALID_SOURCE", source_reference=source.source_url,
                             new_value=record_dict(source))
        return added

    def add_fact(self, fact: Fact) -> bool:
        fact.validate()
        if not self._pit_ok(fact.available_at, record_dict(fact), fact.source_url):
            return False
        if not any(s["source_id"] == fact.source_id for s in self.store.rows("sources")):
            self.store.reject(reason="UNKNOWN_SOURCE", payload=record_dict(fact), actor=self.actor,
                              source_reference=fact.source_url)
            return False
        added = self.store.append("facts", fact)
        if added:
            self.store.audit(action="CREATE_REVISION" if fact.previous_revision_id else "CREATE",
                             entity_type="FACT", entity_id=fact.fact_id, actor=self.actor,
                             reason="APPEND_ONLY_FACT", source_reference=fact.source_url,
                             old_value=fact.previous_revision_id, new_value=record_dict(fact))
        return added

    def add_event_claim(self, *, source: EvidenceSource, event_input: dict[str, Any],
                        claim_input: dict[str, Any], stance: str = "SUPPORTS",
                        migration_status: str = "NATIVE") -> tuple[str | None, str | None, str]:
        self.add_source(source)
        if not self._pit_ok(source.available_at, event_input, source.source_url):
            return None, None, "REJECTED"
        created_at = now_iso()
        fingerprint = event_fingerprint(entity=event_input["primary_entity"],
            event_type=event_input["event_type"], event_date=event_input["event_date"],
            product=event_input.get("product"), customer=event_input.get("customer"),
            numbers=event_input.get("numbers"))
        observation_id = stable_id("event", source.source_id, fingerprint,
                                   event_input.get("normalized_summary", ""))
        candidate = {**event_input, "event_fingerprint": fingerprint,
                     "primary_lineage_id": source.primary_source_id or source.source_id}
        canonical_id, status, best = stable_id("canonical", fingerprint), "ACTIVE", None
        for existing in self.store.rows("events"):
            decision = compare_events(candidate, {**existing,
                "primary_lineage_id": existing.get("primary_source_id")})
            if decision["decision"] in {"MERGE", "POSSIBLE_DUPLICATE"}:
                best = (existing, decision)
                if decision["decision"] == "MERGE":
                    canonical_id = existing["canonical_event_id"]
                else:
                    status = "POSSIBLE_DUPLICATE"
                break
        event = Event(event_id=observation_id, canonical_event_id=canonical_id,
            event_fingerprint=fingerprint, event_type=event_input["event_type"],
            primary_entity=event_input["primary_entity"],
            related_entities=list(event_input.get("related_entities") or []),
            first_seen=source.available_at, last_seen=source.available_at,
            event_date=event_input["event_date"], published_at=source.published_at,
            available_at=source.available_at, status=status,
            primary_source_id=source.primary_source_id or source.source_id,
            created_at=created_at, updated_at=created_at,
            product=event_input.get("product"), customer=event_input.get("customer"),
            numbers=list(event_input.get("numbers") or []),
            normalized_summary=normalize_text(event_input.get("normalized_summary", "")))
        self.store.append("events", event)
        self.store.audit(action="CREATE", entity_type="EVENT", entity_id=event.event_id,
                         actor=self.actor, reason=f"EVENT_{status}_{migration_status}",
                         source_reference=source.source_url, new_value=record_dict(event))
        if best:
            existing, decision = best
            decision_id = stable_id("dedup", event.event_id, existing["event_id"], decision)
            self.store.append("dedup_decisions", {"decision_id": decision_id,
                "left_event_id": event.event_id, "right_event_id": existing["event_id"],
                **decision, "created_at": created_at})
            self.store.audit(action=decision["decision"], entity_type="EVENT",
                entity_id=event.event_id, actor=self.actor,
                reason="DETERMINISTIC_EVENT_DEDUP", source_reference=source.source_url,
                old_value=existing["event_id"], new_value=decision)
        claim_id = stable_id("claim", event.event_id, claim_input["claim_text"],
                             claim_input["claim_type"], source.source_id)
        claim = Claim(claim_id=claim_id, event_id=event.event_id,
            claim_text=claim_input["claim_text"], claim_type=claim_input["claim_type"],
            direction=claim_input.get("direction", "UNKNOWN"),
            scope=claim_input.get("scope", "COMPANY"),
            time_horizon=claim_input.get("time_horizon", "MEDIUM"),
            confidence=claim_input.get("confidence", "MEDIUM"),
            status=claim_input.get("status", "ACTIVE"), created_at=created_at,
            updated_at=created_at, traceable_source_id=source.source_id)
        claim.validate()
        self.store.append("claims", claim)
        self.store.append("event_claim_links", {**asdict(EventClaimLink(event.event_id, claim.claim_id, created_at)),
                                                 "link_id": stable_id("ecl", event.event_id, claim.claim_id)})
        link = ClaimEvidenceLink(claim.claim_id, source.source_id, stance,
                                 source.primary_source_id or source.source_id, created_at)
        link.validate()
        self.store.append("claim_evidence_links", {**asdict(link),
            "link_id": stable_id("cel", claim.claim_id, source.source_id, stance)})
        self.store.audit(action="CREATE", entity_type="CLAIM", entity_id=claim.claim_id,
                         actor=self.actor, reason=f"TRACEABLE_CLAIM_{migration_status}",
                         source_reference=source.source_url, new_value=record_dict(claim))
        return event.event_id, claim.claim_id, status

