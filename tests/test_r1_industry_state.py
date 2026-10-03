import unittest

from r1.industry_state import bottleneck_state, catalyst_state


class R1IndustryStateTest(unittest.TestCase):
    def test_bottleneck_compares_verified_stage(self):
        self.assertEqual(bottleneck_state("MASS_PRODUCTION", "QUALIFICATION"), "STRENGTHENING")
        self.assertEqual(bottleneck_state("QUALIFICATION", "MASS_PRODUCTION"), "EASING")
        self.assertEqual(bottleneck_state("MASS_PRODUCTION", None), "STABLE")

    def test_catalyst_requires_evidence_and_negative_wins(self):
        self.assertEqual(catalyst_state(directions=[], source_families=set()), "DATA_MISSING")
        self.assertEqual(catalyst_state(directions=["UP"], source_families={"ir"}), "NEW")
        self.assertEqual(catalyst_state(directions=["UP", "UP"], source_families={"ir", "research"}), "CONFIRMING")
        self.assertEqual(catalyst_state(directions=["UP", "DOWN"], source_families={"ir", "research"}), "NEGATIVE")


if __name__ == "__main__":
    unittest.main()
