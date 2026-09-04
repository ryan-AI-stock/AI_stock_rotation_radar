import unittest

import pandas as pd

from rotation_radar.c6_daily_pipeline import advance_account, rank_score0


class C6DailyPipelineTests(unittest.TestCase):
    def test_score0_ranking_applies_gates_and_lexical_tiebreak(self):
        day = pd.Timestamp("2026-09-04")
        liquidity = pd.DataFrame([
            {"signal_date": day, "ticker": "3653", "liquidity_pass": True},
            {"signal_date": day, "ticker": "3324", "liquidity_pass": True},
            {"signal_date": day, "ticker": "2301", "liquidity_pass": True},
        ])
        features = pd.DataFrame([
            {"date": day, "ticker": "3653", "return_60d": .2, "bottom_score": 70, "launch_score": 80, "stock_rs20": .2, "sector_rs20": .1},
            {"date": day, "ticker": "3324", "return_60d": .2, "bottom_score": 70, "launch_score": 75, "stock_rs20": .1, "sector_rs20": .1},
            {"date": day, "ticker": "2301", "return_60d": .2, "bottom_score": 55, "launch_score": 90, "stock_rs20": .3, "sector_rs20": .2},
        ])
        revenue = pd.DataFrame([
            {"ticker": "3653", "monthly_revenue_yoy": .1},
            {"ticker": "3324", "monthly_revenue_yoy": .1},
            {"ticker": "2301", "monthly_revenue_yoy": .1},
        ])
        ranked = rank_score0(features, liquidity, {"3653", "3324", "2301"}, revenue, day)
        self.assertEqual(ranked.ticker.tolist(), ["3653", "3324"])
        self.assertEqual(ranked["rank"].tolist(), [1, 2])

    def test_three_slot_account_marks_positions_and_schedules_next_day_exit(self):
        day = pd.Timestamp("2026-09-04")
        payload = {
            "cash": 100,
            "slots": [{"slot_id": 1, "ticker": "3653", "shares": 10, "position_cost": 1000, "raw_close": 100}],
            "ledger_rows": [{
                "account_date": "2026-09-03", "event_sequence": 1, "slot_id": 1,
                "event_type": "buy", "ticker": "3653", "cash_after": 100,
            }],
        }
        official = pd.DataFrame([{"date": day, "ticker": "3653", "close": 85, "market": "TWSE"}])
        adjusted = pd.DataFrame([
            {"date": pd.Timestamp("2026-09-03"), "ticker": "3653", "adjusted_analysis_close": 100},
            {"date": day, "ticker": "3653", "adjusted_analysis_close": 85},
        ])
        slots, ledger, cash, blockers, pending = advance_account(
            payload, day, pd.DataFrame(columns=["ticker"]), official, adjusted
        )
        self.assertEqual(blockers, [])
        self.assertEqual(slots[0]["raw_close"], 85)
        self.assertEqual(ledger[-1]["event_type"], "daily_mark")
        self.assertEqual(pending[0]["action"], "sell")
        self.assertEqual(pending[0]["reason"], "hard_loss_guard")
        self.assertEqual(cash, 100)


if __name__ == "__main__":
    unittest.main()
