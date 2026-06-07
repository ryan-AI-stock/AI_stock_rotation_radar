from __future__ import annotations

import unittest
from contextlib import contextmanager
from datetime import date, datetime
from io import StringIO
from pathlib import Path
from unittest.mock import patch

from rotation_radar.schedule_gate import evaluate_schedule_gate, fetch_twse_calendar, is_trading_day


class ScheduleGateTests(unittest.TestCase):
    def test_daily_gate_waits_until_after_15_taipei_time(self) -> None:
        before_15 = evaluate_schedule_gate(datetime(2026, 6, 5, 14, 59), set(), set())
        after_15 = evaluate_schedule_gate(datetime(2026, 6, 5, 15, 0), set(), set())

        self.assertFalse(before_15.should_run)
        self.assertEqual(before_15.reason, "before_15_taipei")
        self.assertTrue(after_15.should_run)
        self.assertEqual(after_15.target_date, date(2026, 6, 5))

    def test_daily_gate_skips_weekends_and_closed_dates(self) -> None:
        closed_dates = {date(2026, 6, 5)}

        closed = evaluate_schedule_gate(datetime(2026, 6, 5, 15, 0), set(), closed_dates)
        weekend = evaluate_schedule_gate(datetime(2026, 6, 6, 15, 0), set(), set())

        self.assertFalse(closed.should_run)
        self.assertEqual(closed.reason, "not_trading_day")
        self.assertFalse(weekend.should_run)
        self.assertEqual(weekend.reason, "not_trading_day")

    def test_open_dates_override_weekend_rule(self) -> None:
        make_up_trading_day = date(2026, 6, 6)

        self.assertTrue(is_trading_day(make_up_trading_day, {make_up_trading_day}, set()))

    def test_fetch_twse_calendar_falls_back_when_api_returns_invalid_json(self) -> None:
        with patch("rotation_radar.schedule_gate.urlopen", return_value=_response("not json")):
            open_dates, closed_dates = fetch_twse_calendar()

        self.assertEqual(open_dates, set())
        self.assertIsNone(closed_dates)

    def test_fetch_twse_calendar_falls_back_when_payload_has_no_closed_dates(self) -> None:
        with patch("rotation_radar.schedule_gate.urlopen", return_value=_response("[]")):
            open_dates, closed_dates = fetch_twse_calendar()

        self.assertEqual(open_dates, set())
        self.assertIsNone(closed_dates)

    def test_daily_gate_skips_without_failure_when_calendar_is_unavailable(self) -> None:
        decision = evaluate_schedule_gate(datetime(2026, 6, 5, 15, 0), set(), None)

        self.assertFalse(decision.should_run)
        self.assertEqual(decision.reason, "calendar_unavailable")

    def test_workflow_manual_report_date_override_sets_should_run(self) -> None:
        workflow = Path(".github/workflows/generate-report.yml").read_text(encoding="utf-8")

        self.assertIn("echo \"should_run=true\"", workflow)
        self.assertIn("if: steps.report-date.outputs.should_run == 'true'", workflow)


@contextmanager
def _response(text: str):
    yield StringIO(text)


if __name__ == "__main__":
    unittest.main()
