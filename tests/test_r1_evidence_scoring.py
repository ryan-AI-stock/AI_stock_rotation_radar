import unittest
from pathlib import Path
from tempfile import TemporaryDirectory

from r1.consensus import ConsensusEvidence, consensus_actionable, load_consensus_csv
from r1.evidence import CatalystEvent, discovery_eligible, load_catalyst_csv
from r1.scoring import action, score


WEIGHTS = {"eps_revision": .30, "forward_valuation": .25, "bottleneck": .20, "catalyst": .15, "price_chip": .10}


class R1EvidenceScoringTest(unittest.TestCase):
    def test_tier4_event_never_adds_score(self):
        event = CatalystEvent("2026-09-01", "2408", "SUPPLY_SHORTAGE", 100, 1, 12, 4, "forum")
        self.assertEqual(event.score_at("2026-10-01"), 0)

    def test_event_decays_and_rejects_future_use(self):
        event = CatalystEvent("2026-09-01", "2408", "ASP_INCREASE", 100, 1, 12, 1, "official")
        self.assertGreater(event.score_at("2026-09-08"), event.score_at("2026-10-01"))
        with self.assertRaisesRegex(ValueError, "future"):
            event.score_at("2026-08-31")

    def test_discovery_requires_two_sources_and_one_high_quality(self):
        self.assertTrue(discovery_eligible([{"source_url": "a", "source_tier": 1}, {"source_url": "b", "source_tier": 3}]))
        self.assertFalse(discovery_eligible([{"source_url": "a", "source_tier": 3}, {"source_url": "b", "source_tier": 3}]))

    def test_missing_component_blocks_score(self):
        result = score(components={"eps_revision": None, "forward_valuation": 70, "bottleneck": 70,
                                   "catalyst": 60, "price_chip": 50}, weights=WEIGHTS, consensus_allowed=False)
        self.assertIsNone(result.total_score)
        self.assertFalse(result.action_allowed)

    def test_core_lock_overrides_all_exit_logic(self):
        decision = action(total_score=1, core_lock=True, consensus_allowed=True, eps_revision=-1,
                          base_upside=-1, overheat_high=True, thesis_broken=True, rotation_advantage=-1)
        self.assertEqual(decision, ("CORE", "CORE_LOCK"))

    def test_catalyst_loader_rejects_future_available_data(self):
        with TemporaryDirectory() as folder:
            path = Path(folder) / "events.csv"
            path.write_text(
                "event_date,ticker,event_type,description,source_url,source_tier,impact_direction,impact_score,confidence,expiry_weeks,affected_bottleneck,published_at,available_at,retrieved_at\n"
                "2026-09-30,2408,SUPPLY_SHORTAGE,x,https://a,1,UP,80,0.8,12,memory,2026-09-30,2026-10-02,2026-10-02\n",
                encoding="utf-8",
            )
            accepted, rejected = load_catalyst_csv(path, as_of_date="2026-10-01")
            self.assertEqual(accepted, [])
            self.assertEqual(rejected[0]["error"], "future_data")

    def test_low_quality_consensus_is_evidence_only(self):
        with TemporaryDirectory() as folder:
            path = Path(folder) / "consensus.csv"
            path.write_text(
                "ticker,fiscal_year,mean_eps,median_eps,high_eps,low_eps,analyst_count,source,published_at,available_at,retrieved_at,quality,status\n"
                "2408,2027,10,,,,1,broker-a,2026-09-30,2026-09-30,2026-10-01,LOW,READY\n",
                encoding="utf-8",
            )
            result = load_consensus_csv(path, as_of_date="2026-10-01")
            self.assertEqual(result.records[0].status, "EVIDENCE_ONLY")
            self.assertFalse(consensus_actionable(result.records, ticker="2408", fiscal_year=2027))

    def test_ready_consensus_still_requires_two_source_families(self):
        evidence = [ConsensusEvidence("2408", 2027, "a", "same", 1, "2026-09-01"),
                    ConsensusEvidence("2408", 2027, "b", "same", 2, "2026-09-02")]
        self.assertFalse(consensus_actionable([], ticker="2408", fiscal_year=2027, evidence=evidence))


if __name__ == "__main__":
    unittest.main()
