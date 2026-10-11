import unittest

from r1.performance_comparison import build_comparison


class PerformanceComparisonTest(unittest.TestCase):
    def test_missing_seed_blocks_all_returns(self):
        result = build_comparison(date="2026-10-10", market={"rows": []}, benchmark_config={"benchmarks": {}})
        self.assertFalse(result["comparison_ready"])
        self.assertTrue(all(row["return_pct"] is None for row in result["rows"]))

    def test_same_seed_calculates_three_lines(self):
        config = {"common_starting_nav": 1000, "benchmarks": {
            "00631l_buy_hold": {"status": "READY", "shares": 10, "cash": 0},
            "original_hold": {"status": "READY", "positions": [{"ticker": "2308", "shares": 5}], "cash": 0},
        }}
        market = {"rows": [{"ticker": "00631", "raw_close": 110}, {"ticker": "2308", "raw_close": 220}]}
        result = build_comparison(date="2026-10-10", market=market, benchmark_config=config,
                                  actual_snapshot={"nav": 1200})
        self.assertTrue(result["comparison_ready"])
        self.assertEqual([round(row["return_pct"], 2) for row in result["rows"]], [0.2, 0.1, 0.1])

    def test_actual_equity_is_exposed_without_publishing_return(self):
        result = build_comparison(
            date="2026-10-10", market={"rows": []}, benchmark_config={"common_starting_nav": 1000},
            actual_snapshot={"equity_market_value": 900, "nav": None},
        )
        actual = result["rows"][0]
        self.assertEqual(actual["equity_market_value"], 900)
        self.assertIsNone(actual["return_pct"])
        self.assertIn("已確認股票市值", actual["source_note"])

    def test_external_flows_raise_capital_and_add_same_benchmark_units(self):
        config = {
            "common_starting_nav": 1000,
            "external_cash_flows": [
                {"date": "2026-09-14", "amount": 100, "shares": 2, "cash_remainder": 4},
                {"date": "2026-09-24", "amount": 50, "shares": 1, "cash_remainder": 2},
            ],
            "benchmarks": {
                "00631l_buy_hold": {"status": "READY", "shares": 10, "cash": 0},
                "original_hold": {"status": "READY", "positions": [{"ticker": "2308", "shares": 5}], "cash": 0},
            },
        }
        market = {"rows": [{"ticker": "00631", "raw_close": 10}, {"ticker": "2308", "raw_close": 200}]}
        result = build_comparison(date="2026-09-20", market=market, benchmark_config=config)
        all_in, original = result["rows"][1:]
        self.assertEqual(all_in["starting_nav"], 1100)
        self.assertEqual(all_in["nav"], 124)
        self.assertEqual(original["nav"], 1024)
        self.assertEqual(all_in["external_cash_flow"], 100)


if __name__ == "__main__":
    unittest.main()
