from __future__ import annotations
import tempfile,unittest
from dataclasses import asdict,replace

from r1_v1.learning_engine import build_change_proposals
from r1_v1.memory_engine import benchmark_registry,decision_snapshot,evaluate_review,scheduled_reviews
from r1_v1.opportunity_engine import compare_holding_to_challenger,research_state
from r1_v1.research_store import ResearchStore
from r1_v1.research_llm_boundary import validate_research_llm_payload

def bundle(ticker,thesis="UNCHANGED",eps=None,val=.5,rel=0,events=0,neg=0,flow="NEUTRAL",evidence=None):
    evidence=evidence or []
    context={"snapshot_id":"ctx"+ticker,"valuation_context":{"eps_revision":eps,"historical_percentile":val},
      "company_context":{"relative_to_theme":rel,"company_positive_event_count":events,"company_negative_event_count":neg},
      "market_context":{"market_state":"RISK_OFF"},"theme_context":{"theme_context_state":"STABLE"},"flow_context":{"flow_state":flow}}
    reasoning={"reasoning_id":"r"+ticker,"stock_id":ticker,"context_snapshot_id":"ctx"+ticker,"thesis_version":1,
      "thesis_state":thesis,"leading_hypothesis":"h","alternative_hypotheses":[],"supporting_evidence":evidence,"counter_evidence":[],
      "unknowns":[],"confidence":"MEDIUM","falsification_conditions":["x"],"next_observation":["y"]}
    return {"ticker":ticker,"context":context,"reasoning":reasoning,"structural_evidence_count":2,"earnings_visibility":None}

class Phase46Tests(unittest.TestCase):
    def test_pairwise_not_score(self):
        out=compare_holding_to_challenger("d",bundle("A"),bundle("B",rel=.1,events=2,evidence=["e"]))
        self.assertEqual((out.holding_stock_id,out.challenger_stock_id),("A","B"));self.assertFalse(hasattr(out,"score"))
    def test_missing_core_data_is_insufficient(self):
        self.assertEqual(compare_holding_to_challenger("d",bundle("A"),bundle("B")).opportunity_state,"DATA_INSUFFICIENT")
    def test_hysteresis_blocks_one_day_rotation(self):
        c=compare_holding_to_challenger("d",bundle("A"),bundle("B"))
        c=replace(c,opportunity_state="STRONG_ADVANTAGE")
        s=research_state("d","R1_RESEARCH_PORTFOLIO","A",c,[])
        self.assertEqual(s.state,"HOLD");self.assertEqual(s.candidate_state,"ROTATION_REVIEW")
    def test_hysteresis_allows_persistent_rotation(self):
        c=replace(compare_holding_to_challenger("d",bundle("A"),bundle("B")),opportunity_state="STRONG_ADVANTAGE")
        hist=[{"portfolio_id":"R1_RESEARCH_PORTFOLIO","stock_id":"A","state":"HOLD","candidate_state":"ROTATION_REVIEW","persistence_count":2}]
        self.assertEqual(research_state("d","R1_RESEARCH_PORTFOLIO","A",c,hist).state,"ROTATION_REVIEW")
    def test_actual_and_research_separated(self):
        c=compare_holding_to_challenger("d",bundle("A"),bundle("B"));hist=[]
        a=research_state("d","RYAN_ACTUAL_PORTFOLIO_VIEW","A",c,hist);r=research_state("d","R1_RESEARCH_PORTFOLIO","A",c,hist)
        self.assertNotEqual(a.state_id,r.state_id)
    def test_decision_snapshot_append_only(self):
        with tempfile.TemporaryDirectory() as d:
            s=ResearchStore(d);state=asdict(research_state("d","R1_RESEARCH_PORTFOLIO","A",None,[]));snap=decision_snapshot("d",bundle("A")["reasoning"],state)
            self.assertTrue(s.append("decision_snapshots",snap));self.assertFalse(s.append("decision_snapshots",snap))
    def test_reviews_are_5_20_60(self):
        state=asdict(research_state("2026-01-01","R1_RESEARCH_PORTFOLIO","A",None,[]));snap=decision_snapshot("2026-01-01",bundle("A")["reasoning"],state)
        self.assertEqual([x.horizon_td for x in scheduled_reviews(snap,["2026-01-02"]*1)],[5,20,60])
    def test_review_cannot_use_future_early(self):
        state=asdict(research_state("2026-01-01","R1_RESEARCH_PORTFOLIO","A",None,[]));snap=decision_snapshot("2026-01-01",bundle("A")["reasoning"],state)
        dates=[f"2026-02-{i:02d}" for i in range(1,29)]+[f"2026-03-{i:02d}" for i in range(1,32)]
        review=scheduled_reviews(snap,dates)[0]
        with self.assertRaisesRegex(ValueError,"before_due"):evaluate_review(review,"2026-01-03",True,True,.1,.05,["e"])
    def test_review_not_only_price(self):
        state=asdict(research_state("2026-01-01","R1_RESEARCH_PORTFOLIO","A",None,[]));snap=decision_snapshot("2026-01-01",bundle("A")["reasoning"],state)
        dates=[f"2026-02-{i:02d}" for i in range(1,25)];review=scheduled_reviews(snap,dates)[0]
        out=evaluate_review(review,review.due_date,False,True,.20,.01,["e"]);self.assertEqual(out.result,"THESIS_WRONG")
    def test_benchmark_registry_is_complete_and_separate(self):
        rows=benchmark_registry("d",{});self.assertEqual(len(rows),6)
        self.assertEqual({x.portfolio_kind for x in rows},{"BENCHMARK","RESEARCH","ACTUAL"})
    def test_learning_does_not_auto_apply(self):
        p=build_change_proposals([],"d")[0];self.assertFalse(p.auto_apply);self.assertEqual(p.status,"DATA_INSUFFICIENT")
    def test_recent_results_cannot_tune(self):
        reviews=[{"review_id":str(i),"result":"THESIS_WRONG","error_taxonomy":["THESIS_ERROR"],"reviewed_at":"d"} for i in range(20)]
        self.assertEqual(build_change_proposals(reviews,"d")[0].status,"DATA_INSUFFICIENT")
    def test_proposal_requires_validation(self):
        reviews=[{"review_id":str(i),"result":"THESIS_WRONG","error_taxonomy":["THESIS_ERROR"],"reviewed_at":f"d{i%5}"} for i in range(20)]
        p=build_change_proposals(reviews,"d")[0];self.assertEqual((p.historical_validation,p.out_of_sample_validation,p.stability_check),("REQUIRED","REQUIRED","REQUIRED"))
    def test_no_trade_flags(self):
        c=compare_holding_to_challenger("d",bundle("A"),bundle("B"));self.assertFalse(c.active_in_trade_decision);self.assertFalse(c.trade_decision_changed)
    def test_llm_cannot_create_untraced_fact_or_trade(self):
        with self.assertRaises(ValueError):validate_research_llm_payload({"action":"claim_extraction"})
        with self.assertRaises(ValueError):validate_research_llm_payload({"action":"reasoning_summary","source_ids":["e"],"trade_instruction":True})
    def test_llm_keeps_inference_separate(self):
        with self.assertRaises(ValueError):validate_research_llm_payload({"action":"causal_chain","source_ids":["e"],"classification":"INFERENCE","as_fact":True})

if __name__=="__main__":unittest.main()
