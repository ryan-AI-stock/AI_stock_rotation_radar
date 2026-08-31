import unittest

from scripts.run_c6_top3_risk_execution_union_close_fill import parse_month, route_url


class C6Top3RiskExecutionUnionCloseFillTests(unittest.TestCase):
    def test_twse_month_parser_reads_exact_close(self):
        payload = {"fields": ["日期", "收盤價"], "data": [["112/05/31", "66.1"]]}
        self.assertEqual(parse_month(payload, "2301", "TWSE"), {"2023-05-31": 66.1})

    def test_tpex_month_parser_reads_exact_close(self):
        payload = {"tables": [{"data": [["112/10/26", "", "", "", "", "", "104"]]}]}
        self.assertEqual(parse_month(payload, "3260", "TPEx"), {"2023-10-26": 104.0})

    def test_routes_are_selected_ticker_month_only(self):
        self.assertIn("stockNo=2301", route_url("2301", "TWSE", "2023-05"))
        self.assertIn("code=3260", route_url("3260", "TPEx", "2023-10"))


if __name__ == "__main__":
    unittest.main()
