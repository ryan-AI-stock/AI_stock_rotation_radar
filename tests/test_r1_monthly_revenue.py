from __future__ import annotations

import unittest

from r1.monthly_revenue import acceleration_state, conservative_available_date, released_periods


class R1MonthlyRevenueTest(unittest.TestCase):
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
