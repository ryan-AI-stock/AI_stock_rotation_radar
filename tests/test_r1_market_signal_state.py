import unittest

from r1.market_signal_state import confirm_eps_trend, eps_state, flow_state, valuation_state


class R1MarketSignalStateTest(unittest.TestCase):
    def test_eps_direction_is_sign_based(self):
        self.assertEqual(eps_state(.01), "REVISING_UP")
        self.assertEqual(eps_state(0), "STABLE")
        self.assertEqual(eps_state(-.01), "REVISING_DOWN")
        self.assertEqual(eps_state(None), "DATA_MISSING")

    def test_uptrend_requires_multiple_weekly_observations(self):
        self.assertEqual(confirm_eps_trend(["REVISING_UP"]).stage, "EARLY_SIGNAL")
        self.assertEqual(confirm_eps_trend(["REVISING_UP"] * 2).stage, "CONFIRMING")
        confirmed = confirm_eps_trend(["REVISING_UP"] * 4)
        self.assertEqual((confirmed.stage, confirmed.confidence), ("CONFIRMED", "HIGH"))

    def test_downtrend_is_deteriorating_but_confidence_uses_duration(self):
        early = confirm_eps_trend(["REVISING_DOWN"])
        mature = confirm_eps_trend(["REVISING_DOWN"] * 4)
        self.assertEqual((early.stage, early.confidence), ("DETERIORATING", "LOW"))
        self.assertEqual((mature.stage, mature.confidence), ("DETERIORATING", "HIGH"))

    def test_missing_observations_do_not_fake_continuity(self):
        result = confirm_eps_trend(["DATA_MISSING"])
        self.assertEqual((result.stage, result.consecutive_weeks), ("WAIT", 0))

    def test_flow_requires_consistent_5d_and_20d_direction(self):
        self.assertEqual(flow_state(10, 30), "ACCUMULATING")
        self.assertEqual(flow_state(-10, -30), "DISTRIBUTING")
        self.assertEqual(flow_state(10, -30), "NEUTRAL")
        self.assertEqual(flow_state(None, 30), "DATA_MISSING")

    def test_valuation_uses_change_not_only_current_level(self):
        self.assertEqual(
            valuation_state(forward_pe_change=-.1, base_upside_change=.2), "CHEAPENING"
        )
        self.assertEqual(
            valuation_state(forward_pe_change=.1, base_upside_change=-.2), "EXPANDING"
        )
        self.assertEqual(
            valuation_state(forward_pe_change=.1, base_upside_change=.1), "FAIR"
        )


if __name__ == "__main__":
    unittest.main()
