import json
import tempfile
import unittest
from pathlib import Path

import pandas as pd

from rotation_radar.v4d_top1_daily_report import (
    gate_plan,
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
        self.assertEqual(state["daily_marks"]["2026-07-27"]["d_index"], 0)
        self.assertEqual(state["daily_marks"]["2026-07-27"]["model_td"], 1)
        self.assertLess(
            state["daily_marks"]["2026-07-27"]["after_cost_return_pct"], 0
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
        self.assertIn("TD1", html)
        self.assertIn("V4-D完整監控計畫", html)
        self.assertIn("after-cost 未達 +5%", html)
        self.assertNotIn("今日前十名", html)
        self.assertNotIn("前三名", html)

    def test_pending_execution_text_uses_state_dates(self):
        state = self.state()
        state["signal_date"] = "2026-07-27"
        state["execution_date"] = "2026-07-28"

        html = render_html(pd.Timestamp("2026-07-27"), state, [])

        self.assertIn("2026-07-28 執行買入並計為TD1", html)
        self.assertIn(
            "2026-07-28 執行買入後，才建立TD1第一筆正式交易紀錄",
            html,
        )
        self.assertIn("2026-07-27 收盤後的結果", html)
        self.assertNotIn("7/27依官方收盤建立TD1", html)

    def test_gate_plan_uses_entry_day_as_td1(self):
        plan = gate_plan(self.state(), closed_dates=set())
        self.assertEqual(plan[0]["range"], "07/27～07/31")
        self.assertEqual(plan[0]["day"], "TD1～TD5")
        self.assertEqual(plan[3]["range"], "08/13")
        self.assertEqual(plan[5]["range"], "08/25")

    def test_first_five_day_loss_creates_next_day_sell(self):
        state = self.state()
        closes = [100.0, 99.0, 98.0, 97.0, 94.0]
        dates = pd.bdate_range("2026-07-27", periods=5)
        prior = 100.0
        for day, close in zip(dates, closes):
            state = update_state(
                state,
                mark_date=day.strftime("%Y-%m-%d"),
                close=close,
                prior_close=prior,
                closed_dates=set(),
            )
            prior = close
        self.assertEqual(state["status"], "pending_sell")
        self.assertEqual(
            state["pending_exit"]["reason"], "TD1～5 after-cost 虧損達5%"
        )
        self.assertEqual(state["pending_exit"]["execution_date"], "2026-08-03")

    def test_state_requires_complete_seed(self):
        with tempfile.TemporaryDirectory() as folder:
            path = Path(folder) / "state.json"
            path.write_text(json.dumps({"ticker": "2351"}), encoding="utf-8")
            with self.assertRaises(RuntimeError):
                load_state(path)


if __name__ == "__main__":
    unittest.main()
