import json
import tempfile
import unittest
from pathlib import Path

import pandas as pd

from rotation_radar.v4d_top1_daily_report import (
    load_state,
    render_html,
    tracking_rows,
    update_state,
)


class V4DTop1DailyReportTests(unittest.TestCase):
    def state(self):
        return {
            "ticker": "2351",
            "name": "順德",
            "signal_date": "2026-07-24",
            "signal_close": 161.0,
            "execution_date": "2026-07-27",
            "entry_close": None,
            "status": "pending_execution_close",
            "daily_marks": {},
        }

    def test_execution_day_sets_entry_close(self):
        state = update_state(
            self.state(),
            mark_date="2026-07-27",
            close=165.0,
            prior_close=161.0,
        )
        self.assertEqual(state["status"], "holding")
        self.assertEqual(state["entry_close"], 165.0)
        self.assertAlmostEqual(
            state["daily_marks"]["2026-07-27"]["daily_return_pct"],
            2.4844720497,
        )
        self.assertEqual(
            state["daily_marks"]["2026-07-27"]["cumulative_return_pct"], 0.0
        )

    def test_mark_before_execution_does_not_create_trade(self):
        state = update_state(
            self.state(),
            mark_date="2026-07-24",
            close=161.0,
            prior_close=168.0,
        )
        self.assertIsNone(state["entry_close"])
        self.assertEqual(state["daily_marks"], {})

    def test_html_contains_only_top1_structure(self):
        state = update_state(
            self.state(),
            mark_date="2026-07-27",
            close=165.0,
            prior_close=161.0,
        )
        html = render_html(
            pd.Timestamp("2026-07-27"), state, tracking_rows(state)
        )
        self.assertIn("正式模型唯一 Top1", html)
        self.assertIn("2351 順德", html)
        self.assertNotIn("今日前十名", html)
        self.assertNotIn("前三名", html)

    def test_state_requires_complete_seed(self):
        with tempfile.TemporaryDirectory() as folder:
            path = Path(folder) / "state.json"
            path.write_text(json.dumps({"ticker": "2351"}), encoding="utf-8")
            with self.assertRaises(RuntimeError):
                load_state(path)


if __name__ == "__main__":
    unittest.main()
