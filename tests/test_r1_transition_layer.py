from __future__ import annotations

import unittest

import pandas as pd

from r1.transition_layer import (
    assess_selloff, classify_candidate, select_transition_candidates, taiex_return_from_history,
)


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

    def test_taiex_return_requires_exact_target(self) -> None:
        history = pd.DataFrame({
            "date": ["2026-10-06", "2026-10-07"],
            "close": [100.0, 98.0],
        })
        self.assertAlmostEqual(taiex_return_from_history(history, target="2026-10-07"), -0.02)
        with self.assertRaisesRegex(ValueError, "exact target"):
            taiex_return_from_history(history, target="2026-10-08")

    def test_candidates_require_active_eligibility_and_negative_day(self) -> None:
        result = select_transition_candidates(
            market_rows=[
                {"ticker": "2454", "company": "聯發科", "daily_return": -0.03, "bias20": 0.04},
                {"ticker": "2408", "company": "南亞科", "daily_return": 0.02, "bias20": 0.01},
                {"ticker": "3081", "company": "聯亞", "daily_return": -0.05, "bias20": 0.08},
            ],
            active_pool_rows=[
                {"ticker": "2454", "active_pool_eligible": True},
                {"ticker": "2408", "active_pool_eligible": True},
                {"ticker": "3081", "active_pool_eligible": False},
            ],
            priority_by_ticker={"2454": 88, "2408": 90, "3081": 95},
            target_tickers={"2454", "2408", "3081"},
        )
        self.assertEqual([row["ticker"] for row in result], ["2454"])


if __name__ == "__main__":
    unittest.main()
