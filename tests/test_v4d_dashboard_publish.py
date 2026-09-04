from __future__ import annotations

import unittest

import pandas as pd

from rotation_radar.v4d_dashboard_publish import (
    MODEL_LOGIC,
    build_dashboard_values,
    build_signal_rows,
    build_trade_rows,
    model_logic_format_requests,
)


class V4dDashboardPublishTest(unittest.TestCase):
    def test_dashboard_row_32_contains_frozen_v4d_logic(self) -> None:
        values = build_dashboard_values([], {"cash": 7_000_000, "transactions": []})
        self.assertEqual(values[31], [MODEL_LOGIC, ""])
        self.assertIn("止跌轉強證據至少2／3", MODEL_LOGIC)
        self.assertIn("TD55起", MODEL_LOGIC)
        self.assertIn("每月底", MODEL_LOGIC)

    def test_model_logic_format_targets_only_a32_b32(self) -> None:
        requests = model_logic_format_requests(123)
        logic_range = requests[0]["unmergeCells"]["range"]
        self.assertEqual(logic_range, {
            "sheetId": 123, "startRowIndex": 31, "endRowIndex": 32,
            "startColumnIndex": 0, "endColumnIndex": 2,
        })
        self.assertEqual(requests[1]["mergeCells"]["range"], logic_range)
        self.assertEqual(requests[2]["repeatCell"]["cell"]["userEnteredFormat"], {
            "wrapStrategy": "WRAP", "horizontalAlignment": "LEFT", "verticalAlignment": "TOP",
        })
        self.assertGreaterEqual(requests[3]["updateDimensionProperties"]["properties"]["pixelSize"], 600)

    def test_signal_rows_preserve_original_top3_and_mark_final_selection(self) -> None:
        frame = pd.DataFrame([
            {"signal_date": "2026-08-11", "candidate_rank": 1, "ticker": "1216", "name": "統一", "industry_name": "食品工業", "signal_close": 80, "turnover_rank_20d": 10, "turnover_data_completeness": 1, "rank_le280_days_in_prior20": 20, "return_60d": .1, "pre_pullback_20d_strength": .1, "pos20": 10, "pos40": 20, "pos61": 30, "pos61_bucket": 3, "turnup_evidence": 2, "bias60_history_percentile": 50, "bias60_risk_tier": 0, "volatility_percentile": .2, "top30_minimum_pass": True},
            {"signal_date": "2026-08-11", "candidate_rank": 2, "ticker": "2357", "name": "華碩", "industry_name": "電腦及週邊設備業", "signal_close": 839, "turnover_rank_20d": 20, "turnover_data_completeness": 1, "rank_le280_days_in_prior20": 20, "return_60d": .2, "pre_pullback_20d_strength": .2, "pos20": 20, "pos40": 30, "pos61": 40, "pos61_bucket": 4, "turnup_evidence": 2, "bias60_history_percentile": 60, "bias60_risk_tier": 0, "volatility_percentile": .3, "top30_minimum_pass": True},
        ])
        rows = build_signal_rows(frame, {"ticker": "2357", "candidate_rank": 2, "execution_date": "2026-08-12", "status": "signal_only"})
        self.assertEqual(len(rows), 2)
        self.assertIn("排除產業", rows[0][7])
        self.assertTrue(rows[1][6])
        self.assertEqual(rows[1][8], "2026-08-12")

    def test_trade_rows_include_transactions_and_daily_marks(self) -> None:
        state = {
            "cash": 100,
            "transactions": [{"trade_date": "2026-08-05", "action": "buy", "ticker": "3413", "name": "京鼎", "execution_price": 321.5, "shares": 10, "gross_amount": 3215, "transaction_cost": 5, "cash_after": 100, "signal_date": "2026-08-04", "reason": "Top1"}],
            "position": {"ticker": "3413", "name": "京鼎", "shares": 10, "signal_date": "2026-08-04", "daily_marks": {"2026-08-05": {"close": 321.5, "model_td": 1, "daily_return_pct": 0, "cumulative_return_pct": 0, "after_cost_return_pct": -0.1, "peak_after_cost_return_pct": -0.1, "trailing_drawdown_pct": 0}}},
        }
        rows = build_trade_rows(state)
        self.assertEqual([row[1] for row in rows], ["成交", "每日持有"])
        self.assertEqual(rows[1][13], 1)

    def test_dashboard_displays_next_withdrawal_estimate(self) -> None:
        state = {
            "cash": 100, "transactions": [],
            "withdrawal_schedule": {"amount": 75000, "start_date": "2026-09-09", "processed_scheduled_dates": []},
            "position": {"ticker": "2330", "name": "台積電", "shares": 1000, "daily_marks": {"2026-09-08": {"close": 100, "model_td": 1}}},
        }
        values = dict(build_dashboard_values([], state))
        self.assertEqual(values["下次提領排定日"], "2026-09-09")
        self.assertEqual(values["預計賣出股數"], 750)


if __name__ == "__main__":
    unittest.main()
