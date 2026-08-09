import unittest

from rotation_radar.v4d_sheet_sync import _actual_round_row, _trade_rounds


class V4DSheetSyncTests(unittest.TestCase):
    def test_open_position_is_materialized_without_fake_sale(self):
        buy = {
            "action": "v4d_buy", "ticker": "3413", "name": "京鼎",
            "trade_date": "2026-08-05", "signal_date": "2026-08-04",
            "average_price": 325.17, "shares": 23000, "remaining_cash": 154298,
        }
        state = {
            "actual_trades": [buy],
            "position": {
                "ticker": "3413",
                "pending_exit": {
                    "decision_date": "2026-08-07",
                    "execution_date": "2026-08-10",
                    "reason": "TD1至TD5 after-cost虧損達-5%退出",
                },
            },
        }
        rounds = _trade_rounds(state)
        row = _actual_round_row(1, rounds[0], state)
        self.assertEqual(row[0], "實盤1")
        self.assertEqual(row[1], "持有中（已形成賣出訊號）")
        self.assertEqual(row[15], "")
        self.assertIn("預定2026-08-10執行", row[25])

    def test_completed_round_uses_actual_sell(self):
        state = {
            "actual_trades": [
                {"action": "v4d_buy", "ticker": "3413", "name": "京鼎", "trade_date": "2026-08-05", "signal_date": "2026-08-04", "average_price": 100, "shares": 1000},
                {"action": "v4d_sell", "ticker": "3413", "name": "京鼎", "trade_date": "2026-08-10", "average_price": 110, "shares": 1000, "note": "實際賣出"},
            ],
            "position": None,
        }
        row = _actual_round_row(1, _trade_rounds(state)[0], state)
        self.assertEqual(row[1], "已完成")
        self.assertEqual(row[6], 10000)
        self.assertEqual(row[7], 0.1)
        self.assertEqual(row[15], "2026-08-10")


if __name__ == "__main__":
    unittest.main()
