from __future__ import annotations

import json
import tempfile
import unittest
from dataclasses import asdict
from pathlib import Path

from r1_v1.context_engine import (attribute_context, build_company_context,
    build_flow_context, build_market_context, build_theme_context, build_valuation_context)
from r1_v1.context_llm_boundary import validate_context_narrative
from r1_v1.context_store import ContextHistoryStore
from r1_v1.dedup_stress import run_stress
from r1_v1.pipeline import EvidencePipeline
from r1_v1.schema import EvidenceSource
from r1_v1.store import EvidenceStore


class ContextEngineTests(unittest.TestCase):
    def setUp(self):
        self.temp=tempfile.TemporaryDirectory(); self.root=Path(self.temp.name)

    def tearDown(self): self.temp.cleanup()

    def market(self, **overrides):
        data={"return_1d":-.05,"return_5d":-.06,"return_20d":-.02,"breadth":.15,
              "turnover_ratio_20d":1.5,"up_count":100,"down_count":800}
        data.update(overrides); return build_market_context(data,"2026-10-22T13:30:00+08:00")

    def theme(self, market=None, returns=None):
        market=market or self.market(); returns=returns or [-.048,-.052,-.05,-.046]
        rows=[{"return_1d":x,"return_5d":-.06,"return_20d":-.02,"turnover_ratio_20d":1.4} for x in returns]
        return build_theme_context("cpo",rows,market)

    def contexts(self, stock=-.051, market=None, theme=None, events=None, valuation=None, flow=None):
        market=market or self.market(); theme=theme or self.theme(market)
        company=build_company_context("3081",{"return_1d":stock,"return_5d":-.06,"return_20d":-.02},market,theme,events or {})
        val=build_valuation_context("3081",valuation)
        flw=build_flow_context("3081",flow)
        return market,theme,company,val,flw

    def test_market_crash_synchronous_stock_move_is_market_context(self):
        args=self.contexts(); snap=attribute_context(date="2026-10-22",evaluation_time="2026-10-22",ticker="3081",theme_id="cpo",market=args[0],theme=args[1],company=args[2],valuation=args[3],flow=args[4])
        self.assertEqual(snap.primary_context,"MIXED"); self.assertEqual(snap.secondary_context,"THEME")
        self.assertEqual(snap.anomaly_type,"MARKET_DRIVEN_MOVE")

    def test_flat_market_whole_theme_down_is_theme_context(self):
        market=self.market(return_1d=0,return_5d=0,return_20d=.01,breadth=.52)
        theme=self.theme(market,[-.04,-.03,-.05,-.04])
        args=self.contexts(stock=-.04,market=market,theme=theme)
        snap=attribute_context(date="d",evaluation_time="d",ticker="x",theme_id="cpo",market=args[0],theme=args[1],company=args[2],valuation=args[3],flow=args[4])
        self.assertEqual(snap.primary_context,"THEME")

    def test_single_company_crash_with_negative_event_is_company_context(self):
        market=self.market(return_1d=0,return_5d=0,return_20d=.01,breadth=.55)
        theme=self.theme(market,[0,.002,-.001,.001])
        args=self.contexts(stock=-.12,market=market,theme=theme,events={"negative":1})
        self.assertEqual(args[2].company_context_state,"IDIOSYNCRATIC_STRESS")

    def test_price_up_with_extreme_self_valuation_is_valuation_context(self):
        val=build_valuation_context("2330",{"forward_pe":30,"historical_percentile":.95})
        self.assertEqual(val.valuation_state,"EXTREME")

    def test_foreign_selling_is_flow_context_not_sell(self):
        flow=build_flow_context("2330",{"foreign_flow":-10,"turnover":100,"turnover_ratio_20d":1.2})
        self.assertEqual(flow.flow_state,"DISTRIBUTING")
        self.assertNotIn("SELL", json.dumps(asdict(flow)))

    def test_market_and_theme_are_mixed_attribution(self):
        args=self.contexts(); snap=attribute_context(date="d",evaluation_time="d",ticker="x",theme_id="cpo",market=args[0],theme=args[1],company=args[2],valuation=args[3],flow=args[4])
        self.assertEqual(snap.primary_context,"MIXED")

    def test_insufficient_data_is_unknown(self):
        market=build_market_context({},"2026-10-22")
        theme=build_theme_context("cpo",[],market)
        company=build_company_context("x",{},market,theme)
        self.assertEqual(market.market_state,"UNKNOWN"); self.assertEqual(theme.theme_context_state,"UNKNOWN"); self.assertEqual(company.company_context_state,"UNKNOWN")

    def test_missing_data_is_not_zero(self):
        val=build_valuation_context("x",{})
        self.assertIsNone(val.forward_pe); self.assertIsNone(val.historical_percentile)

    def test_llm_cannot_emit_trade_instruction_or_override_number(self):
        with self.assertRaisesRegex(ValueError,"forbidden"):
            validate_context_narrative({"buy":"x","traceable_evidence_ids":["e1"]})
        with self.assertRaisesRegex(ValueError,"forbidden"):
            validate_context_narrative({"numeric_override":1,"traceable_evidence_ids":["e1"]})

    def test_context_snapshot_is_append_only(self):
        args=self.contexts(); snap=attribute_context(date="d",evaluation_time="d",ticker="x",theme_id="cpo",market=args[0],theme=args[1],company=args[2],valuation=args[3],flow=args[4])
        store=ContextHistoryStore(self.root/"history.jsonl")
        self.assertTrue(store.append(snap)); self.assertFalse(store.append(snap)); self.assertEqual(len(store.rows()),1)

    def test_pit_still_rejects_future_phase1_evidence(self):
        store=EvidenceStore(self.root/"evidence"); pipe=EvidencePipeline(store,"2026-01-01")
        src=EvidenceSource("s","f","n","https://x","2026-01-02","2026-01-02","2026-01-03","OFFICIAL",True)
        self.assertFalse(pipe.add_source(src)); self.assertEqual(store.rows("rejections")[0]["reason"],"FUTURE_DATA_VIOLATION")

    def test_phase1_lineage_is_not_mutated_by_context(self):
        path=Path("data/r1_v1/sources.jsonl"); before=path.read_bytes()
        self.contexts(); self.assertEqual(path.read_bytes(),before)

    def test_real_world_dedup_stress(self):
        result=run_stress("data/r1_v1/dedup_stress_cases.json",self.root/"stress")
        self.assertEqual(result["status"],"PASS")
        self.assertTrue(all(c["source_count"]==4 and c["canonical_event_count"]==1 and c["claim_count"]==4 for c in result["cases"]))

    def test_possible_mispricing_is_candidate_not_trade(self):
        market=self.market(); theme=self.theme(market,[-.07,-.065,-.075,-.07])
        args=self.contexts(stock=-.10,market=market,theme=theme,events={"negative":0})
        snap=attribute_context(date="d",evaluation_time="d",ticker="x",theme_id="cpo",market=args[0],theme=args[1],company=args[2],valuation=args[3],flow=args[4])
        self.assertTrue(snap.possible_mispricing_candidate)
        self.assertNotIn("BUY",json.dumps(asdict(snap)))


if __name__ == "__main__": unittest.main()
