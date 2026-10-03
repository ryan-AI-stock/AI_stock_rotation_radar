import unittest

from r1.portfolio_policy import natural_convergence


class R1PortfolioPolicyTest(unittest.TestCase):
    def test_above_five_does_not_force_sale(self):
        result = natural_convergence(
            holding_count=7, max_holdings=5, core_lock=False,
            source_deteriorating=False, replacement_confirmed=True,
            rotation_advantage=20, minimum_advantage=10,
        )
        self.assertEqual(result.action, "KEEP")

    def test_requires_deterioration_confirmed_replacement_and_advantage(self):
        result = natural_convergence(
            holding_count=7, max_holdings=5, core_lock=False,
            source_deteriorating=True, replacement_confirmed=True,
            rotation_advantage=20, minimum_advantage=10,
        )
        self.assertEqual(result.action, "TRIM_1")

    def test_unapproved_threshold_can_only_wait(self):
        result = natural_convergence(
            holding_count=7, max_holdings=5, core_lock=False,
            source_deteriorating=True, replacement_confirmed=True,
            rotation_advantage=20, minimum_advantage=None,
        )
        self.assertEqual(result.action, "WAIT")


if __name__ == "__main__":
    unittest.main()
