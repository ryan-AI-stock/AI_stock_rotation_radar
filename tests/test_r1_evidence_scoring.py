import unittest

from r1.evidence import CatalystEvent, discovery_eligible
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


if __name__ == "__main__":
    unittest.main()
