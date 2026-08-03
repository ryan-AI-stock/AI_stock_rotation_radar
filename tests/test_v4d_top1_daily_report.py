import json
import tempfile
import unittest
from pathlib import Path

import pandas as pd

from rotation_radar.v4d_top1_daily_report import (
    MEDIAN_ROUTE_CAGR,
    MEDIAN_ROUTE_DAILY_RATE,
    ReportDataNotReady,
    evaluate_ma120_market_monitor,
    gate_plan,
    load_state,
    require_current_top1_signal,
    research_refresh_decision,
    render_html,
    tracking_rows,
    update_state,
)
from rotation_radar.disposition_gate import evaluate_disposition_gate


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
        self.assertNotIn("V4-D完整監控計畫", html)
        self.assertEqual(
            html.count("模型尚未正式買入，此訊息流空。"),
            2,
        )
        self.assertNotIn("after-cost 未達 +5%", html)
        self.assertNotIn("今日前十名", html)
        self.assertNotIn("前三名", html)

    def test_paused_position_stream_keeps_signal_dates_only(self):
        state = self.state()
        state["signal_date"] = "2026-07-27"
        state["execution_date"] = "2026-07-28"

        html = render_html(pd.Timestamp("2026-07-27"), state, [])

        self.assertIn("2026-07-28", html)
        self.assertNotIn("執行買入並計為TD1", html)
        self.assertNotIn("建立TD1第一筆正式交易紀錄", html)
        self.assertIn("<td>2026-07-27</td>", html)
        self.assertNotIn("7/27依官方收盤建立TD1", html)

    def test_preview_compares_holding_with_median_annualized_path(self):
        state = update_state(
            self.state(),
            mark_date="2026-07-27",
            close=165.0,
            prior_close=161.0,
        )
        rows = tracking_rows(state)
        html = render_html(
            pd.Timestamp("2026-07-27"),
            state,
            rows,
            preview_assumed_holding=True,
        )

        self.assertIn("今日實際表現 vs 中位數年化線", html)
        self.assertIn("V4-D完整監控計畫", html)
        self.assertIn("12.52億元", html)
        self.assertIn(f"{MEDIAN_ROUTE_CAGR * 100:.2f}%", html)
        self.assertIn(f"{MEDIAN_ROUTE_DAILY_RATE * 100:.2f}%", html)
        self.assertEqual(rows[0]["benchmark_elapsed_td"], 0)
        self.assertAlmostEqual(rows[0]["benchmark_cumulative_pct"], 0.0)

        state = update_state(
            state,
            mark_date="2026-07-28",
            close=166.0,
            prior_close=165.0,
        )
        rows = tracking_rows(state)
        self.assertEqual(rows[-1]["benchmark_elapsed_td"], 1)
        self.assertAlmostEqual(
            rows[-1]["benchmark_cumulative_pct"],
            MEDIAN_ROUTE_DAILY_RATE * 100,
        )

    def test_gate_plan_uses_entry_day_as_td1(self):
        plan = gate_plan(self.state(), closed_dates=set())
        self.assertEqual(plan[0]["range"], "07/27～07/31")
        self.assertEqual(plan[0]["day"], "TD1～TD5")
        self.assertEqual(plan[3]["range"], "08/13")
        self.assertEqual(plan[5]["range"], "08/25")

    def test_ma120_monitor_recognizes_current_near_support_event(self):
        dates = pd.bdate_range("2026-01-01", periods=160)
        closes = [100.0] * 140 + [106.0] * 18 + [101.5, 101.4]
        monitor = evaluate_ma120_market_monitor(
            pd.DataFrame({"date": dates, "close": closes})
        )

        self.assertEqual(monitor["state"], "monitoring")
        self.assertTrue(monitor["near_ma120_pass"])
        self.assertGreaterEqual(monitor["prior20_max_vs_ma120_pct"], 4)
        self.assertGreaterEqual(monitor["close_vs_ma120_pct"], 0)
        self.assertLessEqual(monitor["close_vs_ma120_pct"], 2)
        self.assertEqual(monitor["days_without_new_low"], 0)

    def test_completed_ma120_event_does_not_persist_into_later_days(self):
        dates = pd.bdate_range("2026-01-01", periods=170)
        closes = (
            [100.0] * 140
            + [106.0] * 18
            + [101.5, 101.6, 101.7, 101.8]
            + [107.0]
            + [108.0] * 7
        )
        monitor = evaluate_ma120_market_monitor(
            pd.DataFrame({"date": dates, "close": closes})
        )

        self.assertEqual(monitor["state"], "idle")
        self.assertFalse(monitor["research_refresh_trigger"])

    def test_unactivated_refresh_is_research_only_and_preserves_winner(self):
        monitor = {"research_refresh_trigger": True}
        state = self.state()
        state["holding_ticker"] = "1101"
        state["daily_marks"] = {
            "2026-07-27": {"peak_after_cost_return_pct": 12.0}
        }
        self.assertIn(
            "保留強股",
            research_refresh_decision(monitor, state),
        )

        state["daily_marks"]["2026-07-27"][
            "peak_after_cost_return_pct"
        ] = 3.0
        self.assertIn(
            "研究版符合刷新條件",
            research_refresh_decision(monitor, state),
        )

    def test_html_adds_market_monitor_without_changing_formal_signal(self):
        monitor = {
            "state": "monitoring",
            "state_label": "半年線附近監測中，尚未止穩",
            "close": 39933.30,
            "ma60": 44056.07,
            "ma120": 39327.09,
            "close_vs_ma120_pct": 1.54,
            "prior20_max_vs_ma120_pct": 26.91,
            "near_ma120_pass": True,
            "days_without_new_low": 0,
            "ma60_reclaimed": False,
            "touch_date": "2026-07-29",
            "research_refresh_trigger": False,
        }
        html = render_html(
            pd.Timestamp("2026-07-30"),
            self.state(),
            [],
            market_monitor=monitor,
        )

        self.assertIn("大盤半年線監測", html)
        self.assertIn("半年線附近監測中，尚未止穩", html)
        self.assertIn("26.91%", html)
        self.assertIn("challenger研究資訊", html)
        self.assertIn("不改變正式V4-D", html)

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

    def test_stale_top1_signal_cannot_be_published_as_current(self):
        with self.assertRaises(ReportDataNotReady):
            require_current_top1_signal(
                self.state(),
                pd.Timestamp("2026-07-28"),
            )

        require_current_top1_signal(
            self.state(),
            pd.Timestamp("2026-07-24"),
        )

    def test_disposition_top1_is_blocked_without_fallback(self):
        gate = evaluate_disposition_gate(
            [
                {
                    "market": "TPEX",
                    "announce_date": pd.Timestamp("2026-08-02").date(),
                    "ticker": "6182",
                    "name": "合晶",
                    "start_date": pd.Timestamp("2026-08-03").date(),
                    "end_date": pd.Timestamp("2026-08-14").date(),
                    "detail": "處置期間",
                    "source_url": "official-test-source",
                }
            ],
            ticker="6182",
            signal_date=pd.Timestamp("2026-08-04").date(),
            execution_date=pd.Timestamp("2026-08-05").date(),
            as_of_date=pd.Timestamp("2026-08-04").date(),
        )

        self.assertTrue(gate["blocked"])
        self.assertEqual(gate["status"], "blocked_by_disposition")
        self.assertIn("空手", gate["message"])
        self.assertEqual(len(gate["events"]), 1)

        html = render_html(
            pd.Timestamp("2026-08-04"),
            self.state(),
            [],
            disposition_gate=gate,
        )
        self.assertIn("處置股交易可行性", html)
        self.assertIn("當日空手，不遞補Top2或Top3", html)
        self.assertIn("2026-08-03～2026-08-14", html)

    def test_non_disposition_top1_remains_executable(self):
        gate = evaluate_disposition_gate(
            [],
            ticker="2351",
            signal_date=pd.Timestamp("2026-08-04").date(),
            execution_date=pd.Timestamp("2026-08-05").date(),
            as_of_date=pd.Timestamp("2026-08-04").date(),
        )
        self.assertFalse(gate["blocked"])
        self.assertEqual(gate["status"], "executable")


if __name__ == "__main__":
    unittest.main()
