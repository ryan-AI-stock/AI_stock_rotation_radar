from __future__ import annotations

import unittest

from r1.v05_rank import build_v05_rank


class R1V05RankTest(unittest.TestCase):
    def test_missing_component_blocks_total_without_reweighting(self) -> None:
        result = build_v05_rank(
            as_of_date="2026-10-08",
            weekly={"rows": [{
                "ticker": "2330", "company": "台積電", "next_year_eps_growth": .3,
                "bottleneck_score": 90, "catalyst_score": 80,
                "valuation_score": 70, "price_chip_score": None,
            }]},
            target_prices={"rows": []},
        )
        row = result["rows"][0]
        self.assertIsNone(row["v05_total_score"])
        self.assertIn("price_chip_risk", row["v05_missing_components"])
        self.assertIn("consensus_target_upside", row["v05_missing_components"])

    def test_complete_components_produce_weighted_score(self) -> None:
        weekly = {"rows": [
            {"ticker": "2330", "company": "台積電", "next_year_eps_growth": .1,
             "bottleneck_score": 80, "catalyst_score": 60, "valuation_score": 70,
             "price_chip_score": 90},
            {"ticker": "2454", "company": "聯發科", "next_year_eps_growth": .2,
             "bottleneck_score": 90, "catalyst_score": 70, "valuation_score": 80,
             "price_chip_score": 60},
        ]}
        current = {"rows": [{"ticker": "2454", "scoreable": True,
                              "consensus_upside": .4, "consensus_target_price": 140,
                              "institution_count": 4}]}
        prior = {"rows": [{"ticker": "2454", "scoreable": True,
                            "consensus_target_price": 100, "institution_count": 3}]}
        result = build_v05_rank(as_of_date="2026-10-08", weekly=weekly,
                                target_prices=current, prior_target_prices=prior)
        row = next(item for item in result["rows"] if item["ticker"] == "2454")
        self.assertEqual(row["v05_status"], "READY")
        self.assertIsNotNone(row["v05_total_score"])
        self.assertEqual(row["revenue_earnings_realization"], 100.0)


if __name__ == "__main__":
    unittest.main()
