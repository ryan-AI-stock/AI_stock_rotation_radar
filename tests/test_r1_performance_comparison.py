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


if __name__ == "__main__":
    unittest.main()
