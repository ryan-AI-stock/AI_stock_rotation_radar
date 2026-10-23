import unittest

from r1.recommendations import build_recommendations


class RecommendationTest(unittest.TestCase):
    def test_missing_inputs_returns_no_action(self):
        rows = build_recommendations(date="2026-10-10", candidates=[], held_tickers=set(), target_tickers=set())
        self.assertEqual(rows[0]["priority"], "NO_ACTION")

    def test_targets_rank_and_actual_holdings_are_skipped(self):
        rows = build_recommendations(date="2026-10-10", candidates=[
            {"ticker": "2454", "company": "聯發科", "score": 75, "target_upside": .2,
             "price_chip_risk": 35, "theme_momentum_and_catalyst": 55,
             "official_negative_flags": ["FINANCIAL_EARNINGS_CONTRACTION"]},
            {"ticker": "3081", "company": "聯亞", "score": 90, "target_upside": .4,
             "price_chip_risk": 60, "theme_momentum_and_catalyst": 65},
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
             "price_chip_risk": 60, "theme_momentum_and_catalyst": 60,
             "overlay_missing_components": ["consensus_target_upside"]},
        ], held_tickers=set(), target_tickers={"2308"})
        self.assertEqual(rows[0]["action"], "REVIEW_SWITCH_IN")
        self.assertEqual(rows[0]["confidence"], "MEDIUM")
        self.assertIn("consensus_target_upside", rows[0]["blocking_gaps"])

    def test_low_confidence_core_comparison_is_watch_only(self):
        rows = build_recommendations(date="2026-10-10", candidates=[
            {"ticker": "8299", "company": "群聯", "score": 82,
             "target_upside": None,
             "price_chip_risk": 60, "theme_momentum_and_catalyst": 60,
             "overlay_missing_components": ["consensus_target_upside"]},
            {"ticker": "2454", "company": "聯發科", "score": 70,
             "target_upside": None,
             "price_chip_risk": 35, "theme_momentum_and_catalyst": 55,
             "official_negative_flags": ["FINANCIAL_EARNINGS_CONTRACTION"],
             "overlay_missing_components": ["consensus_target_upside"]},
        ], held_tickers={"2454"}, target_tickers={"2454"})
        self.assertEqual(rows[0]["priority"], "WATCH1")
        self.assertEqual(rows[0]["action"], "OBSERVE_ONLY")
        self.assertEqual(rows[0]["execution_status"], "只觀察，不執行")

    def test_anonymous_target_is_disclosed_but_does_not_raise_confidence(self):
        rows = build_recommendations(date="2026-10-10", candidates=[
            {"ticker": "8299", "company": "群聯", "score": 82,
             "target_upside": None, "anonymous_target_upside": .25,
             "price_chip_risk": 60, "theme_momentum_and_catalyst": 60,
             "overlay_missing_components": ["consensus_target_upside"]},
            {"ticker": "2454", "company": "聯發科", "score": 70,
             "target_upside": None,
             "price_chip_risk": 35, "theme_momentum_and_catalyst": 55,
             "official_negative_flags": ["FINANCIAL_EARNINGS_CONTRACTION"],
             "overlay_missing_components": ["consensus_target_upside"]},
        ], held_tickers={"2454"}, target_tickers={"2454"})
        self.assertEqual(rows[0]["confidence"], "LOW")
        self.assertEqual(rows[0]["action"], "OBSERVE_ONLY")
        self.assertIn("匿名市場目標價中位上行+25.0%", rows[0]["reason"])
        self.assertIn("尚無具名三機構嚴格共識", rows[0]["reason"])

    def test_higher_score_does_not_rotate_a_healthy_incumbent(self):
        rows = build_recommendations(date="2026-10-10", candidates=[
            {"ticker": "2454", "company": "聯發科", "score": 70,
             "price_chip_risk": 55, "theme_momentum_and_catalyst": 55},
            {"ticker": "3081", "company": "聯亞", "score": 90,
             "price_chip_risk": 70, "theme_momentum_and_catalyst": 70},
        ], held_tickers={"2454"}, target_tickers={"2454", "3081"})
        self.assertEqual(rows[0]["priority"], "NO_ACTION")
        self.assertIn("不頻繁換倉", rows[0]["reason"])

    def test_impaired_incumbent_requires_ten_point_advantage(self):
        rows = build_recommendations(date="2026-10-10", candidates=[
            {"ticker": "2454", "company": "聯發科", "score": 70,
             "price_chip_risk": 35, "theme_momentum_and_catalyst": 55,
             "official_negative_flags": ["FINANCIAL_EARNINGS_CONTRACTION"]},
            {"ticker": "3081", "company": "聯亞", "score": 79,
             "price_chip_risk": 70, "theme_momentum_and_catalyst": 70},
        ], held_tickers={"2454"}, target_tickers={"2454", "3081"})
        self.assertEqual(rows[0]["priority"], "NO_ACTION")
        self.assertIn("至少高10分", rows[0]["reason"])

    def test_official_negative_flag_needs_independent_weakness_confirmation(self):
        rows = build_recommendations(date="2026-10-10", candidates=[
            {"ticker": "2454", "company": "聯發科", "score": 70,
             "target_upside": None,
             "price_chip_risk": 60, "theme_momentum_and_catalyst": 60,
             "official_negative_flags": ["REVENUE_AND_EPS_CONTRACTION"]},
            {"ticker": "3081", "company": "聯亞", "score": 82,
             "target_upside": None,
             "price_chip_risk": 70, "theme_momentum_and_catalyst": 70},
        ], held_tickers={"2454"}, target_tickers={"2454", "3081"})
        self.assertEqual(rows[0]["priority"], "NO_ACTION")

        rows = build_recommendations(date="2026-10-10", candidates=[
            {"ticker": "2454", "company": "聯發科", "score": 70,
             "target_upside": None,
             "price_chip_risk": 35, "theme_momentum_and_catalyst": 60,
             "official_negative_flags": ["REVENUE_AND_EPS_CONTRACTION"]},
            {"ticker": "3081", "company": "聯亞", "score": 82,
             "target_upside": None,
             "price_chip_risk": 70, "theme_momentum_and_catalyst": 70},
        ], held_tickers={"2454"}, target_tickers={"2454", "3081"})
        self.assertEqual(rows[0]["source_ticker"], "2454")
        self.assertEqual(rows[0]["target_ticker"], "3081")

    def test_official_negative_flag_blocks_challenger(self):
        rows = build_recommendations(date="2026-10-10", candidates=[
            {"ticker": "2454", "company": "聯發科", "score": 70,
             "price_chip_risk": 35, "theme_momentum_and_catalyst": 60},
            {"ticker": "3081", "company": "聯亞", "score": 90,
             "price_chip_risk": 70, "theme_momentum_and_catalyst": 70,
             "official_negative_flags": ["SUSTAINED_REVENUE_CONTRACTION"]},
        ], held_tickers={"2454"}, target_tickers={"2454", "3081"})
        self.assertEqual(rows[0]["priority"], "NO_ACTION")


if __name__ == "__main__":
    unittest.main()
