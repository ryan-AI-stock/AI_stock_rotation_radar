import unittest

from rotation_radar.v4d_actual_trade import DEFAULT_STATE, record_actual_trade


class V4DActualTradeTests(unittest.TestCase):
    def test_v4d_buy_creates_confirmed_actual_position(self):
        state = record_actual_trade(
            DEFAULT_STATE,
            action="v4d_buy",
            trade_date="2026-08-05",
            ticker="3413",
            name="京鼎",
            average_price=325.5,
            shares=1000,
            fee=464.0,
            signal_date="2026-08-04",
            signal_close=321.5,
        )

        self.assertEqual(state["position"]["ticker"], "3413")
        self.assertEqual(state["position"]["entry_close"], 325.5)
        self.assertEqual(state["position"]["shares"], 1000)
        self.assertTrue(state["position"]["actual_position_confirmed"])

    def test_legacy_sell_does_not_create_or_close_v4d_position(self):
        state = record_actual_trade(
            DEFAULT_STATE,
            action="legacy_sell",
            trade_date="2026-08-05",
            ticker="2317",
            name="鴻海",
            average_price=250.0,
            shares=6120,
            fee=7000.0,
        )

        self.assertIsNone(state["position"])
        self.assertEqual(len(state["actual_trades"]), 1)


if __name__ == "__main__":
    unittest.main()
