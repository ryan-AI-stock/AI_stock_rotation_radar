from __future__ import annotations

import hashlib
import json
from pathlib import Path

import tempfile
import unittest

from r1_v1.dedup import compare_events
from r1_v1.legacy_import import import_legacy
from r1_v1.llm_boundary import validate_llm_claim_payload
from r1_v1.pipeline import EvidencePipeline
from r1_v1.schema import EvidenceSource, Fact
from r1_v1.store import EvidenceStore


def source(sid="s1", available="2026-01-02", url="https://official.test/a",
           primary="primary-a"):
    return EvidenceSource(sid, "official", "Official", url, "2026-01-01",
                          available, "2026-01-03", "OFFICIAL", True, primary)


def fact(fid="f1", revision="r1", previous=None, value=100, kind="ACTUAL",
         available="2026-01-02", sid="s1"):
    return Fact(fid, "COMPANY", "2330", "monthly_revenue", value, "TWD", "2025-12",
                sid, "https://official.test/a", "2026-01-01", "2026-01-01",
                available, "2026-01-03", revision, True, "2026-01-03",
                kind, previous, "NATIVE")


def event_input(summary="TSMC raises capex", date="2026-01-01", numbers=None, product="3nm"):
    return {"event_type": "CAPEX_UP", "primary_entity": "2330", "related_entities": [],
            "event_date": date, "product": product, "customer": None,
            "numbers": numbers or ["50bn"], "normalized_summary": summary}


def claim_input(text="AI demand supports capex", direction="POSITIVE"):
    return {"claim_text": text, "claim_type": "FACTUAL_CLAIM", "direction": direction,
            "scope": "COMPANY", "time_horizon": "MEDIUM", "confidence": "HIGH"}


class EvidenceFoundationTests(unittest.TestCase):
 def setUp(self):
    self._temp = tempfile.TemporaryDirectory()
    self.tmp_path = Path(self._temp.name)

 def tearDown(self):
    self._temp.cleanup()

 def test_pit_valid_record_is_accepted(self):
    tmp_path = self.tmp_path
    store = EvidenceStore(tmp_path); pipe = EvidencePipeline(store, "2026-01-10")
    assert pipe.add_source(source())
    assert pipe.add_fact(fact())
    assert len(store.rows("facts")) == 1


 def test_future_data_is_rejected_and_audited(self):
    tmp_path = self.tmp_path
    store = EvidenceStore(tmp_path); pipe = EvidencePipeline(store, "2026-01-01")
    assert not pipe.add_source(source(available="2026-01-02"))
    assert store.rows("rejections")[0]["reason"] == "FUTURE_DATA_VIOLATION"
    assert store.rows("audit_log")[0]["action"] == "REJECT"


 def test_fact_revisions_are_both_preserved(self):
    tmp_path = self.tmp_path
    store = EvidenceStore(tmp_path); pipe = EvidencePipeline(store, "2026-01-10")
    pipe.add_source(source())
    assert pipe.add_fact(fact())
    assert pipe.add_fact(fact("f2", "r2", "r1", 110))
    assert [row["value"] for row in store.rows("facts")] == [100, 110]


 def test_same_event_from_different_media_is_deduplicated(self):
    tmp_path = self.tmp_path
    store = EvidenceStore(tmp_path); pipe = EvidencePipeline(store, "2026-01-10")
    e1, _, _ = pipe.add_event_claim(source=source(), event_input=event_input(), claim_input=claim_input())
    e2, _, status = pipe.add_event_claim(source=source("s2", url="https://news.test/a", primary="primary-b"),
        event_input=event_input(summary="TSMC capex raised for 3nm AI", date="2026-01-02"),
        claim_input=claim_input("3nm AI demand supports raised capex"))
    events = store.rows("events")
    assert e1 != e2 and events[0]["canonical_event_id"] == events[1]["canonical_event_id"]
    assert status == "ACTIVE"


 def test_different_events_are_not_merged(self):
    left = {**event_input(), "primary_lineage_id": "a"}
    right = {**event_input(date="2026-03-01"), "event_type": "GUIDANCE_DOWN", "primary_lineage_id": "b"}
    assert compare_events(left, right)["decision"] == "DISTINCT"

 def test_same_entity_and_type_far_apart_are_distinct(self):
    left = {**event_input(date="2026-01-01"), "primary_lineage_id": "a"}
    right = {**event_input(date="2026-04-01"), "primary_lineage_id": "a"}
    assert compare_events(left, right)["decision"] == "DISTINCT"


 def test_possible_duplicate_is_retained_separately(self):
    tmp_path = self.tmp_path
    store = EvidenceStore(tmp_path); pipe = EvidencePipeline(store, "2026-01-10")
    first = event_input(); first["numbers"] = []
    pipe.add_event_claim(source=source(), event_input=first, claim_input=claim_input())
    second = event_input(summary="capex expansion", product=None); second["numbers"] = []
    _, _, status = pipe.add_event_claim(source=source("s2", url="https://news.test/b", primary="b"),
        event_input=second, claim_input=claim_input())
    assert status == "POSSIBLE_DUPLICATE"
    assert len(store.canonical_events()) == 2


 def test_actual_and_forecast_are_separate_fact_kinds(self):
    tmp_path = self.tmp_path
    store = EvidenceStore(tmp_path); pipe = EvidencePipeline(store, "2026-01-10")
    pipe.add_source(source())
    pipe.add_fact(fact())
    pipe.add_fact(fact("f2", "r2", value=120, kind="FORECAST"))
    assert {r["fact_kind"] for r in store.rows("facts")} == {"ACTUAL", "FORECAST"}


 def test_supporting_and_contradicting_evidence_can_coexist(self):
    tmp_path = self.tmp_path
    store = EvidenceStore(tmp_path); pipe = EvidencePipeline(store, "2026-01-10")
    _, claim_id, _ = pipe.add_event_claim(source=source(), event_input=event_input(), claim_input=claim_input())
    store.append("claim_evidence_links", {"link_id": "contra", "claim_id": claim_id,
        "source_id": "s2", "stance": "CONTRADICTS", "primary_lineage_id": "primary-b",
        "created_at": "2026-01-03"})
    assert {r["stance"] for r in store.rows("claim_evidence_links")} == {"SUPPORTS", "CONTRADICTS"}


 def test_same_primary_lineage_counts_once(self):
    tmp_path = self.tmp_path
    store = EvidenceStore(tmp_path)
    for idx in range(2):
        store.append("claim_evidence_links", {"link_id": f"l{idx}", "claim_id": "c1",
            "source_id": f"s{idx}", "stance": "SUPPORTS", "primary_lineage_id": "same-primary",
            "created_at": "2026-01-03"})
    assert store.independent_evidence_count("c1", "SUPPORTS") == 1


 def test_missing_value_is_not_coerced_to_zero(self):
    tmp_path = self.tmp_path
    store = EvidenceStore(tmp_path); pipe = EvidencePipeline(store, "2026-01-10")
    pipe.add_source(source())
    with self.assertRaisesRegex(ValueError, "fact_value_missing"):
        pipe.add_fact(fact(value=None))
    assert not store.rows("facts")


 def test_audit_records_source_fact_event_claim_and_rejection(self):
    tmp_path = self.tmp_path
    store = EvidenceStore(tmp_path); pipe = EvidencePipeline(store, "2026-01-10")
    pipe.add_source(source()); pipe.add_fact(fact())
    pipe.add_event_claim(source=source(), event_input=event_input(), claim_input=claim_input())
    pipe._pit_ok("2027-01-01", {"x": 1}, "future")
    actions = {(r["action"], r["entity_type"]) for r in store.rows("audit_log")}
    assert {("CREATE", "SOURCE"), ("CREATE", "FACT"), ("CREATE", "EVENT"),
            ("CREATE", "CLAIM"), ("REJECT", "REJECTION")} <= actions


 def test_llm_boundary_disallows_fact_or_trade_creation(self):
    with self.assertRaisesRegex(ValueError, "forbidden"):
        validate_llm_claim_payload({"fact": 1})
    with self.assertRaisesRegex(ValueError, "forbidden"):
        validate_llm_claim_payload({"recommendation": "BUY"})


 def test_legacy_shadow_import_does_not_mutate_source_files(self):
    tmp_path = self.tmp_path
    repo = tmp_path / "repo"
    (repo / "data/r1/catalyst_events").mkdir(parents=True)
    (repo / "data/r1/monthly_revenue").mkdir(parents=True)
    (repo / "data/r1/consensus").mkdir(parents=True)
    catalyst = repo / "data/r1/catalyst_events/evidence.csv"
    catalyst.write_text("event_date,ticker,event_type,description,source_url,source_family,source_tier,impact_direction,affected_bottleneck,published_at,available_at,retrieved_at,evidence_status\n2026-01-01,2330,CAPEX_UP,capex up,https://official.test/a,tsmc_ir,1,UP,compute,2026-01-01,2026-01-01,2026-01-02,VERIFIED\n", encoding="utf-8")
    before = hashlib.sha256(catalyst.read_bytes()).hexdigest()
    import_legacy(repo, tmp_path / "shadow", "2026-01-10")
    assert hashlib.sha256(catalyst.read_bytes()).hexdigest() == before
    assert json.loads((tmp_path / "shadow/evidence_monitor/latest.json").read_text(encoding="utf-8"))["status"] == "RESEARCH_DEBUG_ONLY"


if __name__ == "__main__":
    unittest.main()
