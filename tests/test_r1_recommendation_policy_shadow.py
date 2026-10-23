import unittest

from r1.recommendation_policy_shadow import PROFILES, build_shadow


class R1RecommendationPolicyShadowTest(unittest.TestCase):
    def test_records_fixed_profiles_without_changing_trade_policy(self):
        v05 = {"rows": [
            {"ticker": "2454", "v05_total_score": 70, "price_chip_risk": 40,
             "theme_momentum_and_catalyst": 60, "official_negative_flags": []},
            {"ticker": "3081", "v05_total_score": 79, "price_chip_risk": 60,
             "theme_momentum_and_catalyst": 60, "official_negative_flags": []},
        ]}
        result = build_shadow(
            as_of_date="2026-10-22", v05=v05,
            actual={"positions": [{"ticker": "2454", "shares": 1}]},
            themes={"target_portfolio_6m": ["2454", "3081"]},
        )
        self.assertEqual(len(result["rows"]), len(PROFILES))
        by_profile = {row["profile"]: row for row in result["rows"]}
        self.assertEqual(by_profile["baseline"]["decision_count"], 0)
        self.assertEqual(by_profile["gap_08"]["decision_signature"], ["2454->3081"])
        self.assertFalse(result["trade_decision_changed"])

    def test_same_date_is_idempotently_replaced(self):
        existing = {"rows": [{"date": "2026-10-22", "profile": "stale"},
                              {"date": "2026-10-21", "profile": "baseline"}]}
        result = build_shadow(
            as_of_date="2026-10-22", v05={"rows": []}, actual={"positions": []},
            themes={"target_portfolio_6m": []}, existing=existing,
        )
        self.assertEqual(sum(row["date"] == "2026-10-22" for row in result["rows"]), len(PROFILES))
        self.assertEqual(sum(row["date"] == "2026-10-21" for row in result["rows"]), 1)


if __name__ == "__main__":
    unittest.main()
