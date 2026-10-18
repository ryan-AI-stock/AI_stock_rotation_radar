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
                "market_risk_score": None,
            }]},
            target_prices={"rows": []},
            monthly_revenue={"rows": [{"ticker": "2330", "observations": [{"yoy": .2}]}]},
            theme_review={"themes": [{"ranked": [{
                "ticker": "2330", "bottleneck_directness": 90,
                "financial_earnings_quality": 80,
            }]}]},
        )
        row = result["rows"][0]
        self.assertIsNone(row["v05_total_score"])
        self.assertIn("price_chip_risk", row["v05_missing_components"])
        self.assertNotIn("consensus_target_upside", row["v05_missing_components"])
        self.assertIn("consensus_target_upside", row["v05_target_overlay_missing_components"])
        self.assertGreater(row["v05_observed_points"], 0)
        self.assertLess(row["v05_observed_max_points"], 100)
        self.assertIsNotNone(row["v05_reference_score"])
        self.assertAlmostEqual(row["v05_reference_coverage"], row["v05_observed_max_points"] / 100)

    def test_complete_components_produce_weighted_score(self) -> None:
        weekly = {"rows": [
            {"ticker": "2330", "company": "台積電", "next_year_eps_growth": .1,
             "bottleneck_score": 80, "catalyst_score": 60, "valuation_score": 70,
             "price_chip_score": None, "market_risk_score": 90},
            {"ticker": "2454", "company": "聯發科", "next_year_eps_growth": .2,
             "bottleneck_score": 90, "catalyst_score": 70, "valuation_score": 80,
             "price_chip_score": None, "market_risk_score": 60},
        ]}
        current = {"rows": [{"ticker": "2454", "scoreable": True,
                              "consensus_upside": .4, "consensus_target_price": 140,
                              "institution_count": 4}]}
        prior = {"rows": [{"ticker": "2454", "scoreable": True,
                            "consensus_target_price": 100, "institution_count": 3}]}
        result = build_v05_rank(as_of_date="2026-10-08", weekly=weekly,
                                target_prices=current, prior_target_prices=prior,
                                monthly_revenue={"rows": [
                                    {"ticker": "2330", "observations": [{"yoy": .05}]},
                                    {"ticker": "2454", "observations": [{"yoy": .30}]},
                                ]}, theme_review={"themes": [{"ranked": [
                                    {"ticker": "2330", "bottleneck_directness": 80,
                                     "financial_earnings_quality": 40},
                                    {"ticker": "2454", "bottleneck_directness": 90,
                                     "financial_earnings_quality": 100},
                                ]}]})
        row = next(item for item in result["rows"] if item["ticker"] == "2454")
        self.assertEqual(row["v05_status"], "READY")
        self.assertIsNotNone(row["v05_total_score"])
        self.assertEqual(row["revenue_earnings_realization"], 100.0)

    def test_public_core_is_ready_without_target_price_overlay(self) -> None:
        result = build_v05_rank(
            as_of_date="2026-10-08",
            weekly={"rows": [{
                "ticker": "2308", "company": "台達電", "bottleneck_score": 90,
                "catalyst_score": 80, "valuation_score": 70, "market_risk_score": 60,
            }]},
            target_prices={"rows": []},
            monthly_revenue={"rows": [{"ticker": "2308", "observations": [{"yoy": .2}]}]},
            theme_review={"themes": [{"ranked": [{
                "ticker": "2308", "bottleneck_directness": 90,
                "financial_earnings_quality": 80,
            }]}]},
        )
        row = result["rows"][0]
        self.assertEqual(row["v05_status"], "READY")
        self.assertIsNotNone(row["v05_total_score"])
        self.assertIsNone(row["v05_target_overlay_score"])
        self.assertEqual(row["v05_target_overlay_status"], "DATA_MISSING")

    def test_formal_universe_excludes_discovery_rows(self) -> None:
        result = build_v05_rank(
            as_of_date="2026-10-08",
            weekly={"rows": [
                {"ticker": "2330", "company": "台積電"},
                {"ticker": "3008", "company": "大立光"},
            ]},
            target_prices={"rows": []},
            allowed_tickers={"2330"},
        )
        self.assertEqual(result["requested_ticker_count"], 1)
        self.assertEqual(result["rows"][0]["ticker"], "2330")

    def test_future_dated_target_and_quarterly_review_are_not_used(self) -> None:
        result = build_v05_rank(
            as_of_date="2026-10-08",
            weekly={"rows": [{"ticker": "2330", "bottleneck_score": 40}]},
            target_prices={"date": "2026-10-09", "rows": [{
                "ticker": "2330", "scoreable": True, "consensus_upside": .8,
            }]},
            theme_review={"date": "2026-10-09", "themes": [{"ranked": [{
                "ticker": "2330", "bottleneck_directness": 100,
                "financial_earnings_quality": 100,
            }]}]},
        )
        row = result["rows"][0]
        self.assertEqual(row["structural_bottleneck"], 40)
        self.assertIsNone(row["consensus_target_upside"])


if __name__ == "__main__":
    unittest.main()
