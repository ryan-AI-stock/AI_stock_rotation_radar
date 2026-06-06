from __future__ import annotations

import unittest
from contextlib import contextmanager
from datetime import date, datetime
from io import StringIO
from unittest.mock import patch

from rotation_radar.schedule_gate import fetch_twse_calendar, is_trading_day, target_report_date


class ScheduleGateTests(unittest.TestCase):
    def test_target_report_date_waits_until_after_15_taipei_time(self) -> None:
        self.assertEqual(target_report_date(datetime(2026, 6, 5, 14, 59), set(), set()), date(2026, 6, 4))
        self.assertEqual(target_report_date(datetime(2026, 6, 5, 15, 0), set(), set()), date(2026, 6, 5))

    def test_target_report_date_skips_weekends_and_closed_dates(self) -> None:
        closed_dates = {date(2026, 6, 5)}

        self.assertEqual(target_report_date(datetime(2026, 6, 8, 14, 59), set(), closed_dates), date(2026, 6, 4))

    def test_open_dates_override_weekend_rule(self) -> None:
        make_up_trading_day = date(2026, 6, 6)

        self.assertTrue(is_trading_day(make_up_trading_day, {make_up_trading_day}, set()))

    def test_fetch_twse_calendar_falls_back_when_api_returns_invalid_json(self) -> None:
        with patch("rotation_radar.schedule_gate.urlopen", return_value=_response("not json")):
            open_dates, closed_dates = fetch_twse_calendar()

        self.assertEqual(open_dates, set())
        self.assertEqual(closed_dates, set())

    def test_fetch_twse_calendar_falls_back_when_payload_has_no_closed_dates(self) -> None:
        with patch("rotation_radar.schedule_gate.urlopen", return_value=_response("[]")):
            open_dates, closed_dates = fetch_twse_calendar()

        self.assertEqual(open_dates, set())
        self.assertEqual(closed_dates, set())


@contextmanager
def _response(text: str):
    yield StringIO(text)


if __name__ == "__main__":
    unittest.main()
