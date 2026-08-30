import unittest

from rotation_radar.v4d_simulation_account import (
    DEFAULT_STATE,
    execute_due_withdrawal,
    second_wednesday,
    withdrawal_preview,
)


class V4DWithdrawalScheduleTests(unittest.TestCase):
    def _holding_state(self):
        state = dict(DEFAULT_STATE, cash=1_000.0, transactions=[])
        state["withdrawal_schedule"] = {
            "amount": 75_000.0,
            "start_date": "2026-09-09",
            "processed_scheduled_dates": [],
        }
        state["position"] = {
            "ticker": "2330", "name": "台積電", "shares": 1_000,
            "position_cost": 100_000.0, "buy_fee": 100.0, "daily_marks": {},
        }
        return state

    def test_second_wednesday_matches_taifex_pre_settlement_schedule(self):
        self.assertEqual(second_wednesday(2026, 9).isoformat(), "2026-09-09")
        self.assertEqual(second_wednesday(2026, 10).isoformat(), "2026-10-14")

    def test_due_withdrawal_sells_whole_shares_once(self):
        state = self._holding_state()
        event = execute_due_withdrawal(state, trade_date="2026-09-09", close=100.0)
        self.assertEqual(event["shares"], 750)
        self.assertEqual(event["scheduled_withdrawal_date"], "2026-09-09")
        self.assertFalse(event["withdrawal_deferred_from_closed_date"])
        self.assertEqual(state["position"]["shares"], 250)
        self.assertIsNone(execute_due_withdrawal(state, trade_date="2026-09-09", close=100.0))

    def test_market_closed_due_date_defers_to_next_actual_trading_day(self):
        state = self._holding_state()
        event = execute_due_withdrawal(state, trade_date="2026-09-10", close=100.0)
        self.assertTrue(event["withdrawal_deferred_from_closed_date"])
        self.assertEqual(event["scheduled_withdrawal_date"], "2026-09-09")
        self.assertEqual(event["trade_date"], "2026-09-10")

    def test_preview_uses_current_close_and_reports_cash_when_flat(self):
        state = self._holding_state()
        preview = withdrawal_preview(state, as_of_date="2026-09-08", close=120.0)
        self.assertEqual(preview["next_scheduled_date"], "2026-09-09")
        self.assertEqual(preview["planned_shares"], 625)
        state["position"] = None
        preview = withdrawal_preview(state, as_of_date="2026-09-08", close=None)
        self.assertEqual(preview["status"], "cash_withdrawal")
        self.assertEqual(preview["estimated_net_withdrawal"], 1_000.0)


if __name__ == "__main__":
    unittest.main()
