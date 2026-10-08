from __future__ import annotations

import unittest

from r1.transition_layer import assess_selloff, classify_candidate


class R1TransitionLayerTest(unittest.TestCase):
    def test_normal_pullback_does_not_activate(self) -> None:
        result = assess_selloff(
            [{"return": -0.01}] * 6 + [{"return": 0.01}] * 4,
            taiex_return=-0.006, session_complete=False, expected_count=10,
        )
        self.assertEqual(result["status"], "NOT_TRIGGERED")
        self.assertFalse(result["triggered"])

    def test_broad_selloff_is_intraday_watch_only(self) -> None:
        result = assess_selloff(
            [{"return": -0.03}] * 8 + [{"return": 0.01}] * 2,
            taiex_return=-0.01, session_complete=False, expected_count=10,
        )
        self.assertEqual(result["status"], "INTRADAY_WATCH_ONLY")
        self.assertFalse(result["automatic_trade_allowed"])

    def test_after_close_trigger_still_requires_ryan_review(self) -> None:
        result = assess_selloff(
            [{"return": -0.02}] * 10,
            taiex_return=-0.02, session_complete=True, expected_count=10,
        )
        self.assertEqual(result["status"], "READY_FOR_RYAN_REVIEW")
        self.assertFalse(result["automatic_trade_allowed"])

    def test_missing_candidate_evidence_is_not_buyable(self) -> None:
        result = classify_candidate({
            "ticker": "3081", "risk_gate": "DATA_MISSING",
            "financial_status": "READY", "catalyst_state": "POSITIVE",
        }, target_tickers={"3081"})
        self.assertEqual(result["state"], "DATA_NOT_READY")
        self.assertTrue(result["is_long_term_target"])


if __name__ == "__main__":
    unittest.main()
