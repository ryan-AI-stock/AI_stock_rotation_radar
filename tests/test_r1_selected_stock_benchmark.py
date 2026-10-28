import unittest

from r1.selected_stock_benchmark import build_selected_stock_comparison


class SelectedStockBenchmarkTest(unittest.TestCase):
    def test_baseline_excludes_tsmc_and_00631l(self):
        actual = {"positions": [{"ticker": "2330", "market_value": 1000},
                                {"ticker": "00631L", "market_value": 200},
                                {"ticker": "3037", "market_value": 600},
                                {"ticker": "2408", "market_value": 400}]}
        payload, state = build_selected_stock_comparison(
            date="2026-10-28", actual_account=actual,
            benchmark_market={"rows": [{"ticker": "00631", "raw_close": 40}]})
        self.assertEqual(payload["actual_value"], 1000)
        self.assertEqual(payload["benchmark_value"], 1000)
        self.assertEqual(state["benchmark_units"], 25)

    def test_rotation_does_not_change_benchmark_units(self):
        state = {"baseline_date": "2026-10-28", "baseline_actual_value": 1000,
                 "baseline_00631l_close": 40, "benchmark_units": 25,
                 "applied_flow_ids": [], "excluded_tickers": ["2330", "00631L"]}
        payload, new_state = build_selected_stock_comparison(
            date="2026-10-29", actual_account={"positions": [{"ticker": "3037", "market_value": 1100}]},
            benchmark_market={"rows": [{"ticker": "00631", "raw_close": 42}]}, state=state)
        self.assertEqual(new_state["benchmark_units"], 25)
        self.assertEqual(payload["benchmark_value"], 1050)
        self.assertEqual(payload["difference_actual_minus_benchmark"], 50)

    def test_external_flow_adds_same_value_to_benchmark(self):
        state = {"baseline_date": "2026-10-28", "baseline_actual_value": 1000,
                 "baseline_00631l_close": 40, "benchmark_units": 25,
                 "applied_flow_ids": [], "excluded_tickers": ["2330", "00631L"]}
        ledger = {"selected_stock_benchmark_flows": [
            {"id": "cash-1", "date": "2026-10-29", "amount": 420, "official_00631l_close": 42}]}
        payload, new_state = build_selected_stock_comparison(
            date="2026-10-29", actual_account={"positions": [{"ticker": "3037", "market_value": 1420}]},
            benchmark_market={"rows": [{"ticker": "00631", "raw_close": 42}]},
            state=state, cash_ledger=ledger)
        self.assertEqual(new_state["benchmark_units"], 35)
        self.assertEqual(payload["benchmark_value"], 1470)
        self.assertEqual(payload["difference_actual_minus_benchmark"], -50)


if __name__ == "__main__":
    unittest.main()
