from __future__ import annotations

import tempfile,unittest
from dataclasses import replace
from pathlib import Path

from r1_v1.reasoning_engine import (apply_counter_evidence,assess_thesis_update,
    disconfirmation_pass,expectation_analysis,generate_competing_hypotheses,initial_thesis,
    reasoning_snapshot)
from r1_v1.reasoning_llm_boundary import validate_reasoning_llm_payload
from r1_v1.reasoning_store import ReasoningStore
from r1_v1.pipeline import EvidencePipeline
from r1_v1.schema import EvidenceSource
from r1_v1.store import EvidenceStore


def context():
    return {"snapshot_id":"ctx1","date":"2026-10-22","evaluation_time":"2026-10-22",
        "ticker":"3081","theme_id":"cpo","primary_context":"MIXED","secondary_context":"THEME",
        "possible_mispricing_candidate":True,"supporting_evidence":["e1"],"contradicting_evidence":[],
        "unknowns":["20D_history"],"market_context":{"market_state":"RISK_OFF"},
        "theme_context":{"theme_context_state":"SELL_OFF"},
        "company_context":{"company_negative_event_count":0,"company_context_state":"UNDERPERFORMING"},
        "valuation_context":{"valuation_state":"NORMAL"},"flow_context":{"flow_state":"DISTRIBUTING"}}


class ReasoningEngineTests(unittest.TestCase):
    def setUp(self):self.t=tempfile.TemporaryDirectory();self.root=Path(self.t.name)
    def tearDown(self):self.t.cleanup()
    def thesis(self):return initial_thesis("3081","CPO","光互連瓶頸","2026-10-22",["e1"],["customer_confirmation"])

    def test_same_evidence_not_duplicated(self):
        h=generate_competing_hypotheses(context())[0]
        h2=apply_counter_evidence(h,["c1","c1"])
        self.assertEqual(h2.contradicting_evidence_ids,["c1"])

    def test_counter_evidence_lowers_confidence(self):
        h=replace(generate_competing_hypotheses(context())[0],confidence="HIGH")
        self.assertEqual(apply_counter_evidence(h,["c1"]).confidence,"LOW")

    def test_critical_counter_rejects_hypothesis(self):
        h=generate_competing_hypotheses(context())[0]
        self.assertEqual(apply_counter_evidence(h,["c1"],critical=True).status,"REJECTED")

    def test_missing_data_remains_unknown(self):
        e=expectation_analysis("x",None,None,1,[],"d")
        self.assertEqual(e.difference,"UNKNOWN");self.assertTrue(e.unknowns)

    def test_single_day_price_cannot_break_thesis(self):
        updated=assess_thesis_update(self.thesis(),[{"kind":"PRICE_ONLY","stance":"CONTRADICTS","critical":True,"evidence_id":"p","lineage":"p"}],"d")
        self.assertEqual(updated.status,"UNCHANGED");self.assertEqual(updated.thesis_version,1)

    def test_single_news_cannot_break_thesis(self):
        updated=assess_thesis_update(self.thesis(),[{"kind":"NEWS","stance":"CONTRADICTS","critical":False,"evidence_id":"n","lineage":"one"}],"d")
        self.assertEqual(updated.status,"UNCHANGED")

    def test_same_lineage_not_independent(self):
        ev=[{"kind":"NEWS","stance":"SUPPORTS","evidence_id":str(i),"lineage":"same"} for i in range(3)]
        self.assertEqual(assess_thesis_update(self.thesis(),ev,"d").status,"UNCHANGED")

    def test_hypothesis_can_remain_unresolved(self):
        self.assertTrue(all(h.status=="UNRESOLVED" for h in generate_competing_hypotheses(context())))

    def test_thesis_versions_are_append_only(self):
        s=ReasoningStore(self.root);t1=self.thesis();s.append("theses",t1)
        t2=assess_thesis_update(t1,[{"kind":"OFFICIAL","stance":"SUPPORTS","evidence_id":"a","lineage":"a"},{"kind":"CUSTOMER","stance":"SUPPORTS","evidence_id":"b","lineage":"b"}],"2026-11-01")
        s.append("theses",t2);self.assertEqual(len(s.rows("theses")),2);self.assertEqual(t2.thesis_version,2)

    def test_reasoning_snapshot_append_only(self):
        s=ReasoningStore(self.root);t=self.thesis();hs=generate_competing_hypotheses(context());d=disconfirmation_pass(hs[0],context())
        snap=reasoning_snapshot("d","3081",context(),t,hs,d)
        self.assertTrue(s.append("reasoning_history",snap));self.assertFalse(s.append("reasoning_history",snap))

    def test_llm_claim_without_source_rejected(self):
        with self.assertRaisesRegex(ValueError,"trace_missing"):validate_reasoning_llm_payload({"candidate_hypotheses":[]})

    def test_future_data_still_rejected(self):
        store=EvidenceStore(self.root/"e");pipe=EvidencePipeline(store,"2026-01-01")
        src=EvidenceSource("s","f","n","https://x","2026-01-02","2026-01-02","2026-01-03","OFFICIAL",True)
        self.assertFalse(pipe.add_source(src))

    def test_phase1_phase2_lineage_unchanged(self):
        paths=[Path("data/r1_v1/sources.jsonl"),Path("data/r1_v1/context_history.jsonl")]
        before=[p.read_bytes() for p in paths];generate_competing_hypotheses(context())
        self.assertEqual(before,[p.read_bytes() for p in paths])

    def test_trade_output_forbidden(self):
        with self.assertRaisesRegex(ValueError,"forbidden"):validate_reasoning_llm_payload({"buy":"x","traceable_evidence_ids":["e"]})


if __name__=="__main__":unittest.main()
