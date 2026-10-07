import unittest
from datetime import date
from pathlib import Path

from r1.theme_policy import cadence, leader_score, load_themes, priority_score, rank_theme, rotation_decision


ROOT = Path(__file__).resolve().parents[1]


class R1ThemePolicyTest(unittest.TestCase):
    def test_structural_theme_universe_allows_cross_theme_membership(self):
        themes = load_themes(ROOT / "config/r1_v02_themes.json")
        self.assertEqual(len(themes), 11)
        tickers = [member.ticker for theme in themes for member in theme.members]
        self.assertEqual(len(tickers), 55)
        self.assertEqual(len(set(tickers)), 52)
        self.assertIn("2376", tickers)
        self.assertIn("2327", tickers)
        self.assertIn("3081", tickers)
        self.assertTrue(all(3 <= len(theme.members) <= 8 for theme in themes))
        self.assertEqual(tickers.count("6442"), 2)
        self.assertNotIn("3008", tickers)
        self.assertNotIn("3406", tickers)

    def test_leader_requires_every_stable_component(self):
        complete = {field: 80 for field in (
            "bottleneck_directness", "industry_technology_position", "ai_revenue_realization",
            "financial_earnings_quality", "market_representation",
        )}
        self.assertEqual(leader_score(complete), 80)
        incomplete = dict(complete, market_representation=None)
        self.assertIsNone(leader_score(incomplete))

    def test_priority_score_uses_confirmed_weights_and_requires_all_fields(self):
        row = {
            "structural_leader": 100, "revenue_earnings_growth": 80,
            "self_historical_valuation": 70, "price_risk_safety": 60,
            "demand_order_catalyst": 50,
        }
        self.assertEqual(priority_score(row), 78)
        self.assertIsNone(priority_score(dict(row, self_historical_valuation=None)))

    def test_theme_top1_is_not_published_from_partial_membership(self):
        theme = load_themes(ROOT / "config/r1_v02_themes.json")[0]
        row = {"ticker": theme.members[0].ticker, **{field: 90 for field in (
            "bottleneck_directness", "industry_technology_position", "ai_revenue_realization",
            "financial_earnings_quality", "market_representation",
        )}}
        result = rank_theme(theme, [row])
        self.assertEqual(result["status"], "DATA_MISSING")
        self.assertIsNone(result["top1"])

    def test_cadence_follows_disclosure_and_membership_anchors(self):
        result = cadence(as_of=date(2026, 10, 5), last_quarterly_review=date(2026, 8, 15),
                         last_membership_review=date(2026, 8, 15))
        self.assertFalse(result["quarterly_leader_review_due"])
        self.assertFalse(result["semiannual_membership_review_due"])
        november = cadence(as_of=date(2026, 11, 16), last_quarterly_review=date(2026, 8, 15),
                           last_membership_review=date(2026, 8, 15))
        self.assertTrue(november["quarterly_leader_review_due"])
        self.assertFalse(november["semiannual_membership_review_due"])

    def test_rotation_requires_risk_theme_weakness_replacement_and_two_weeks(self):
        self.assertEqual(rotation_decision(
            emergency_thesis_break=False, holding_risk_high=True, theme_weak_confirmed=True,
            replacement_ready=True, replacement_advantage=12, confirmation_weeks=2,
        ), "ROTATE_NEXT_TRADING_DAY")
        self.assertEqual(rotation_decision(
            emergency_thesis_break=False, holding_risk_high=True, theme_weak_confirmed=True,
            replacement_ready=False, replacement_advantage=None, confirmation_weeks=3,
        ), "WATCH_NO_REPLACEMENT")
        self.assertEqual(rotation_decision(
            emergency_thesis_break=True, holding_risk_high=False, theme_weak_confirmed=False,
            replacement_ready=False, replacement_advantage=None, confirmation_weeks=0,
        ), "EMERGENCY_EXIT_TO_CASH")


if __name__ == "__main__":
    unittest.main()
