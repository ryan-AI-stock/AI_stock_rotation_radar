from __future__ import annotations

import unittest

from r1.monthly_revenue import acceleration_state, conservative_available_date, parse_html, released_periods


class R1MonthlyRevenueTest(unittest.TestCase):
    def test_parser_uses_prior_year_revenue_column_and_cross_checks_yoy(self) -> None:
        html = """
        <table><tr><td>2330</td><td>台積電</td><td>100,000</td><td>90,000</td>
        <td>80,000</td><td>11.11</td><td>25.00</td></tr></table>
        """
        rows = parse_html(html, period="2026-09", market="TWSE", source_url="https://example.test")
        self.assertEqual(rows[0]["revenue_twd"], 100_000_000)
        self.assertEqual(rows[0]["prior_year_revenue_twd"], 80_000_000)
        self.assertEqual(rows[0]["yoy"], .25)
        self.assertEqual(rows[0]["derived_yoy"], .25)

    def test_parser_rejects_internally_inconsistent_yoy(self) -> None:
        html = """
        <table><tr><td>2330</td><td>台積電</td><td>100,000</td><td>90,000</td>
        <td>80,000</td><td>11.11</td><td>99.00</td></tr></table>
        """
        self.assertEqual(parse_html(
            html, period="2026-09", market="TWSE", source_url="https://example.test",
        ), [])

    def test_released_periods_respects_conservative_pit_date(self) -> None:
        self.assertEqual(released_periods("2026-10-07"), ["2026-06", "2026-07", "2026-08"])
        self.assertEqual(released_periods("2026-10-12"), ["2026-07", "2026-08", "2026-09"])

    def test_weekend_available_date_moves_forward(self) -> None:
        self.assertEqual(conservative_available_date("2026-09").isoformat(), "2026-10-12")

    def test_acceleration_requires_three_increasing_positive_latest_yoy(self) -> None:
        rows = [
            {"revenue_year_month": "2026-06", "yoy": -0.05},
            {"revenue_year_month": "2026-07", "yoy": 0.02},
            {"revenue_year_month": "2026-08", "yoy": 0.12},
        ]
        self.assertEqual(acceleration_state(rows)[0], "ACCELERATING")

    def test_missing_month_is_not_neutral(self) -> None:
        self.assertEqual(acceleration_state([
            {"revenue_year_month": "2026-07", "yoy": 0.02},
            {"revenue_year_month": "2026-08", "yoy": 0.12},
        ])[0], "DATA_MISSING")


if __name__ == "__main__":
    unittest.main()
