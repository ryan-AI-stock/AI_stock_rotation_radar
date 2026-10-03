import unittest
from pathlib import Path

from r1.component_scores import (
    bottleneck_score, catalyst_score, eps_revision_composite, eps_revision_score,
    forward_valuation_score, percentile_score, price_chip_score,
)
from r1.config import R1Config


POLICY = R1Config.load(Path(__file__).resolve().parents[1] / "config/r1.json").score_policy


class R1ComponentScoresTest(unittest.TestCase):
    def test_midrank_percentile_does_not_turn_all_ties_into_100(self):
        self.assertEqual(percentile_score([1, 1, 1], 1), 50)

    def test_eps_score_requires_all_three_pit_horizons(self):
        self.assertIsNone(eps_revision_composite(
            revision_1w=.01, revision_4w=.02, revision_12w=None, policy=POLICY["eps_revision"],
        ))

    def test_eps_direction_caps_and_floors_override_relative_rank(self):
        values = [-.10, -.05, .01]
        falling = eps_revision_score(
            revision_1w=0, revision_4w=-.02, revision_12w=-.03, eligible_composites=values,
            policy=POLICY["eps_revision"],
        )
        rising = eps_revision_score(
            revision_1w=.01, revision_4w=.01, revision_12w=.01, eligible_composites=values,
            policy=POLICY["eps_revision"],
        )
        self.assertLessEqual(falling, 30)
        self.assertGreaterEqual(rising, 55)

    def test_nonpositive_base_upside_caps_valuation_score(self):
        result = forward_valuation_score(
            own_forward_pe_percentile=.1, base_upside=0, next_year_eps_growth=.5,
            eligible_base_upside=[-.2, 0, .3], eligible_eps_growth=[0, .1, .5],
            policy=POLICY["forward_valuation"],
        )
        self.assertEqual(result, 35)

    def test_bottleneck_requires_verified_evidence_and_all_subscores(self):
        self.assertIsNone(bottleneck_score(
            stage="MASS_PRODUCTION", tightness_score=80, financial_proof_score=70, evidence_verified=False,
            policy=POLICY["bottleneck"],
        ))
        self.assertEqual(bottleneck_score(
            stage="MASS_PRODUCTION", tightness_score=80, financial_proof_score=70, evidence_verified=True,
            policy=POLICY["bottleneck"],
        ), 84)

    def test_catalyst_is_neutral_without_events_but_not_without_evidence(self):
        self.assertEqual(catalyst_score(
            positive_decayed_scores=[], negative_decayed_scores=[], evidence_ready=True,
            policy=POLICY["catalyst"],
        ), 50)
        self.assertIsNone(catalyst_score(
            positive_decayed_scores=[20], negative_decayed_scores=[], evidence_ready=False,
            policy=POLICY["catalyst"],
        ))

    def test_price_chip_uses_confirmed_subweights_and_keeps_missing_as_na(self):
        self.assertEqual(price_chip_score(
            earnings_vs_price_score=80, overheat_safety_score=60,
            institutional_score=50, leverage_structure_score=40,
            policy=POLICY["price_chip"],
        ), 64)
        self.assertIsNone(price_chip_score(
            earnings_vs_price_score=80, overheat_safety_score=None,
            institutional_score=50, leverage_structure_score=40,
            policy=POLICY["price_chip"],
        ))


if __name__ == "__main__":
    unittest.main()
