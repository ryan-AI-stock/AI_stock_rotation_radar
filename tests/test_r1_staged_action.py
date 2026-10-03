import unittest

from r1.staged_action import dynamic_triggers, next_staged_action


class R1StagedActionTest(unittest.TestCase):
    def test_deterioration_reduces_in_stages(self):
        first = next_staged_action(prior_stage="KEEP", thesis_broken=False,
                                   deteriorating=True, target_confirmed=False, add_supported=False)
        second = next_staged_action(prior_stage=first.stage, thesis_broken=False,
                                    deteriorating=True, target_confirmed=False, add_supported=False)
        final = next_staged_action(prior_stage=second.stage, thesis_broken=False,
                                   deteriorating=True, target_confirmed=False, add_supported=False)
        self.assertEqual([first.stage, second.stage, final.stage], ["TRIM_1", "TRIM_2", "EXIT"])

    def test_addition_requires_confirmed_target_and_support(self):
        self.assertEqual(next_staged_action(
            prior_stage="WATCH", thesis_broken=False, deteriorating=False,
            target_confirmed=False, add_supported=True).stage, "WATCH")
        self.assertEqual(next_staged_action(
            prior_stage="WATCH", thesis_broken=False, deteriorating=False,
            target_confirmed=True, add_supported=True).stage, "ADD_1")

    def test_triggers_are_dynamic_state_context_not_fixed_prices(self):
        result = dynamic_triggers(eps_state="REVISING_UP", valuation_state="CHEAPENING",
                                  flow_state="ACCUMULATING", bottleneck_state="STABLE",
                                  catalyst_state="CONFIRMING")
        self.assertIn("EPS=REVISING_UP", result["current_trigger_inputs"])
        self.assertNotIn("元", result["next_add_trigger"])


if __name__ == "__main__":
    unittest.main()
