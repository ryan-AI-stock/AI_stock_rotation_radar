import unittest

from r1.recommendations import build_recommendations


class RecommendationTest(unittest.TestCase):
    def test_missing_inputs_returns_no_action(self):
        rows = build_recommendations(date="2026-10-10", candidates=[], held_tickers=set(), target_tickers=set())
        self.assertEqual(rows[0]["priority"], "NO_ACTION")

    def test_targets_rank_and_actual_holdings_are_skipped(self):
        rows = build_recommendations(date="2026-10-10", candidates=[
            {"ticker": "2454", "company": "聯發科", "score": 80, "target_upside": .2},
            {"ticker": "3081", "company": "聯亞", "score": 90, "target_upside": .4},
        ], held_tickers={"2454"}, target_tickers={"2454", "3081"})
        self.assertEqual(rows[0]["target_ticker"], "3081")
        self.assertEqual(rows[0]["source_ticker"], "2454")
        self.assertEqual(rows[0]["confidence"], "HIGH")

    def test_partial_evidence_is_observation_only(self):
        rows = build_recommendations(date="2026-10-10", candidates=[
            {"ticker": "2308", "company": "台達電", "score": None, "target_upside": None,
             "observed_points": 42, "observed_max_points": 60,
             "missing_components": ["consensus_target_upside"]},
        ], held_tickers=set(), target_tickers={"2308"})
        self.assertEqual(rows[0]["action"], "OBSERVE_ONLY")
        self.assertEqual(rows[0]["execution_status"], "只觀察，不執行")

    def test_public_core_can_rank_without_target_price_overlay(self):
        rows = build_recommendations(date="2026-10-10", candidates=[
            {"ticker": "2308", "company": "台達電", "score": 82,
             "target_upside": None,
             "overlay_missing_components": ["consensus_target_upside"]},
        ], held_tickers=set(), target_tickers={"2308"})
        self.assertEqual(rows[0]["action"], "REVIEW_SWITCH_IN")
        self.assertEqual(rows[0]["confidence"], "MEDIUM")
        self.assertIn("consensus_target_upside", rows[0]["blocking_gaps"])


if __name__ == "__main__":
    unittest.main()
