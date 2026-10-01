import unittest

from r1.rotation import build_rotation_orders


class R1RotationTest(unittest.TestCase):
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
