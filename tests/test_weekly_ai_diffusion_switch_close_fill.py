import tempfile
import unittest
from pathlib import Path

import pandas as pd

from scripts.run_weekly_ai_diffusion_switch_close_fill import (
    build_routes,
    load_authority,
    parse_twse_stock_day,
)


class WeeklyAiDiffusionSwitchCloseFillTest(unittest.TestCase):
    def test_parse_twse_stock_day(self):
        payload = {
            "stat": "OK",
            "fields": ["日期", "成交股數", "收盤價"],
            "data": [["113/01/29", "1,000", "201.50"]],
        }
        schema_ok, rows = parse_twse_stock_day(payload)
        self.assertTrue(schema_ok)
        self.assertEqual(rows, {"2024-01-29": 201.5})

    def test_parse_official_no_data(self):
        schema_ok, rows = parse_twse_stock_day({"stat": "很抱歉，沒有符合條件的資料!"})
        self.assertTrue(schema_ok)
        self.assertEqual(rows, {})

    def test_authority_scope_guard(self):
        rows = [
            {"ticker": "00631L", "date": f"2024-01-{day:02d}"}
            for day in range(1, 29)
        ] + [
            {"ticker": "00631L", "date": f"2024-02-{day:02d}"}
            for day in range(1, 21)
        ] + [
            {"ticker": "6669", "date": f"2021-01-{day:02d}"}
            for day in range(1, 8)
        ]
        with tempfile.TemporaryDirectory() as temp:
            path = Path(temp) / "authority.csv"
            pd.DataFrame(rows).to_csv(path, index=False)
            authority = load_authority(path)
        self.assertEqual(len(authority), 55)
        self.assertEqual(authority.groupby("ticker").size().to_dict(), {"00631L": 48, "6669": 7})

    def test_routes_skip_local_and_prelisting(self):
        authority = pd.DataFrame(
            [
                {"ticker": "00631L", "date": "2024-01-29"},
                {"ticker": "00631L", "date": "2024-02-15"},
                {"ticker": "6669", "date": "2018-02-08"},
                {"ticker": "6669", "date": "2019-04-02"},
            ]
        )
        routes = build_routes(authority, {("00631L", "2024-01-29")}, "2019-03-27")
        self.assertEqual(routes, [("00631L", "2024-02"), ("6669", "2019-04")])


if __name__ == "__main__":
    unittest.main()
