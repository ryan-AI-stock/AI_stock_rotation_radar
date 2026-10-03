import unittest

from r1.overheat import assess_overheat
from r1.price_eps import percentile_rank, price_eps_gap
from r1.scoring import action


class R1PriceOverheatTest(unittest.TestCase):
    def test_earnings_leading_price_is_visible(self):
        result = price_eps_gap(price_change=0.08, eps_revision=0.18)
        self.assertAlmostEqual(result.earnings_minus_price, 0.10)
        self.assertEqual(result.state, "EARNINGS_LEADS_PRICE")

    def test_price_leading_earnings_is_valuation_expansion(self):
        result = price_eps_gap(price_change=0.24, eps_revision=0.03)
        self.assertEqual(result.state, "PRICE_LEADS_EARNINGS")

    def test_positive_and_negative_divergence_are_explicit(self):
        self.assertEqual(price_eps_gap(price_change=-.10, eps_revision=.10).state, "POSITIVE_DIVERGENCE")
        self.assertEqual(price_eps_gap(price_change=.20, eps_revision=-.05).state, "NEGATIVE_DIVERGENCE")

    def test_percentile_uses_only_supplied_history(self):
        self.assertEqual(percentile_rank([1, 2, 3, 4], 3), 0.75)
        self.assertIsNone(percentile_rank([], 3))

    def test_overheat_requires_joint_evidence(self):
        high = assess_overheat(bias60_percentile=.97, forward_pe_percentile=.96,
                               eps_revision_4w=.02, eps_revision_12w=.05, high_percentile=.95)
        self.assertEqual(high.risk, "HIGH")
        self.assertTrue(high.add_blocked)
        not_high = assess_overheat(bias60_percentile=.97, forward_pe_percentile=.50,
                                   eps_revision_4w=.08, eps_revision_12w=.05, high_percentile=.95)
        self.assertEqual(not_high.risk, "LOW")

    def test_unapproved_action_thresholds_can_only_watch(self):
        decision = action(total_score=99, core_lock=False, consensus_allowed=True, eps_revision=.2,
                          base_upside=.8, overheat_high=False, thesis_broken=False,
                          rotation_advantage=.5)
        self.assertEqual(decision, ("WATCH", "ACTION_THRESHOLDS_NOT_APPROVED"))


if __name__ == "__main__":
    unittest.main()
