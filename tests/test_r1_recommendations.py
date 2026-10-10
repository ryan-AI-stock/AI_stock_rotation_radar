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
        self.assertEqual(rows[0]["confidence"], "HIGH")


if __name__ == "__main__":
    unittest.main()
