import unittest

from r1.rotation import build_rotation_orders, compare_rotation_pair


class R1RotationTest(unittest.TestCase):
    def test_pairwise_comparison_is_visible_but_cannot_rotate_without_approved_threshold(self):
        source = {"ticker": "3037", "total_score": 70, "eps_revision_4w": .02,
                  "base_upside": .10, "price_eps_gap_4w": -.05}
        target = {"ticker": "2408", "total_score": 82, "eps_revision_4w": .12,
                  "base_upside": .30, "price_eps_gap_4w": .08}
        result = compare_rotation_pair(source=source, target=target)
        self.assertEqual(result.source_ticker, "3037")
        self.assertEqual(result.target_ticker, "2408")
        self.assertEqual(result.score_advantage, 12)
        self.assertAlmostEqual(result.eps_revision_4w_advantage, .10)
        self.assertEqual(result.decision, "WAIT")
        self.assertEqual(result.reason, "ROTATION_THRESHOLD_NOT_APPROVED")

    def test_pairwise_comparison_blocks_missing_data(self):
        result = compare_rotation_pair(
            source={"ticker": "3037", "total_score": None},
            target={"ticker": "2408", "total_score": 82},
        )
        self.assertEqual(result.decision, "DATA_MISSING")

    def test_weekly_rotation_is_capped_and_core_excluded(self):
        orders = build_rotation_orders(
            current_values={"2330": 5_000_000, "2327": 3_000_000, "2408": 0},
            target_weights={"2327": .4, "2408": .6}, managed_value=5_000_000,
            max_weekly_rotation=.10, core_locked={"2330"},
        )
        self.assertNotIn("2330", [row.ticker for row in orders])
        self.assertLessEqual(sum(max(0, row.suggested_transfer) for row in orders), 500_000.01)
        self.assertLessEqual(sum(max(0, -row.suggested_transfer) for row in orders), 500_000.01)

    def test_target_weights_must_be_complete(self):
        with self.assertRaisesRegex(ValueError, "sum to 1.0"):
            build_rotation_orders(current_values={}, target_weights={"2408": .9}, managed_value=1,
                                  max_weekly_rotation=.1, core_locked={"2330"})

    def test_core_cannot_enter_targets(self):
        with self.assertRaisesRegex(ValueError, "CORE_LOCK"):
            build_rotation_orders(current_values={}, target_weights={"2330": 1}, managed_value=1,
                                  max_weekly_rotation=.1, core_locked={"2330"})


if __name__ == "__main__":
    unittest.main()
