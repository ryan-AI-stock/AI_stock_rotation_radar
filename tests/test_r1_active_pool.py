from __future__ import annotations

import unittest

from r1.active_pool import (
    catch_up_state, dispersion_state, earnings_visibility, estimate_dispersion, risk_gate,
)


POLICY = {
    "estimate_dispersion": {"minimum_analyst_count": 3, "medium": 0.20, "high": 0.35},
    "earnings_revision": {"flat_band": 0.02, "fail_4w": -0.10, "fail_12w": -0.15},
    "valuation": {"extreme_percentile": 0.95},
}


class R1ActivePoolTest(unittest.TestCase):
    def test_estimate_dispersion_requires_coverage(self) -> None:
        value, status = estimate_dispersion(
            high=12, median=10, low=8, analyst_count=2, minimum_analyst_count=3,
        )
        self.assertIsNone(value)
        self.assertEqual(status, "LOW_CONFIDENCE")

    def test_dispersion_state(self) -> None:
        self.assertEqual(dispersion_state(0.10, medium=0.20, high=0.35), "LOW")
        self.assertEqual(dispersion_state(0.40, medium=0.20, high=0.35), "HIGH")

    def test_earnings_visibility_does_not_use_missing_revision_as_neutral(self) -> None:
        state, reasons = earnings_visibility({
            "consensus_allowed": True, "analyst_count": 8,
            "forward_eps_high": 12, "forward_eps_median": 10, "forward_eps_low": 9,
            "eps_revision_4w": None, "eps_revision_12w": None,
        }, POLICY)
        self.assertEqual(state, "DATA_MISSING")
        self.assertIn("EPS_REVISION_4W_12W_NOT_MATURE", reasons)

    def test_positive_catch_up_uses_matched_horizons(self) -> None:
        state, details = catch_up_state({
            "return_1w": -0.03, "return_1m": 0.05, "return_3m": 0.20,
            "eps_revision_1w": 0.02, "eps_revision_4w": 0.10, "eps_revision_12w": 0.15,
        })
        self.assertEqual(state, "POSITIVE_DIVERGENCE")
        self.assertAlmostEqual(details["4w"]["price_eps_gap"], 0.05)

    def test_risk_gate_never_treats_missing_earnings_as_pass(self) -> None:
        state, reasons = risk_gate({}, earnings_state="DATA_MISSING", policy=POLICY)
        self.assertEqual(state, "DATA_MISSING")
        self.assertEqual(reasons, ["EARNINGS_VISIBILITY_NOT_READY"])

    def test_risk_gate_never_treats_missing_financials_as_pass(self) -> None:
        state, reasons = risk_gate({}, earnings_state="MEDIUM", policy=POLICY,
                                   financial_status="DATA_MISSING")
        self.assertEqual(state, "DATA_MISSING")
        self.assertEqual(reasons, ["OFFICIAL_FINANCIALS_NOT_READY"])

    def test_risk_gate_fails_major_downrevision(self) -> None:
        state, reasons = risk_gate({"eps_revision_4w": -0.11, "eps_revision_12w": -0.03},
                                   earnings_state="MEDIUM", policy=POLICY)
        self.assertEqual(state, "FAIL")
        self.assertIn("EPS_4W_MAJOR_DOWNREVISION", reasons)


if __name__ == "__main__":
    unittest.main()
