import unittest

from r1.shadow_rotation import evaluate_shadow_rotation


POLICY = {"minimum_score_advantage": 10, "max_holdings": 5,
          "source_signal_stage": "DETERIORATING", "target_signal_stage": "CONFIRMED",
          "staged_transfer_fraction": .25, "max_weekly_rotation": .10}


class R1ShadowRotationTest(unittest.TestCase):
    def test_confirmed_pair_above_limit_enters_trim_1_shadow(self):
        source = {"ticker": "3037", "total_score": 70, "eps_revision_4w": -.02,
                  "base_upside": .05, "price_eps_gap_4w": -.10,
                  "signal_stage": "DETERIORATING", "core_lock": False}
        target = {"ticker": "2408", "total_score": 82, "eps_revision_4w": .12,
                  "base_upside": .30, "price_eps_gap_4w": .08,
                  "signal_stage": "CONFIRMED"}
        result = evaluate_shadow_rotation(source=source, target=target, policy=POLICY, holding_count=7)
        self.assertEqual(result["status"], "TRIM_1")
        self.assertTrue(result["shadow_only"])

    def test_missing_inputs_do_not_produce_rotation(self):
        result = evaluate_shadow_rotation(
            source={"ticker": "3037", "total_score": None},
            target={"ticker": "2408", "total_score": 82}, policy=POLICY, holding_count=7,
        )
        self.assertEqual(result["status"], "DATA_MISSING")


if __name__ == "__main__":
    unittest.main()
