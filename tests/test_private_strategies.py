from __future__ import annotations

import json
import unittest
from datetime import date, timedelta
from pathlib import Path
from tempfile import TemporaryDirectory

from rotation_radar.private_strategies import (
    PRIVATE_STRATEGY_STATE_VERSION,
    STRATEGIES,
    build_private_strategy_checkpoints,
    required_private_strategy_symbols,
)
from rotation_radar.models import Report
from rotation_radar.report import render_private_signal_report


class PrivateStrategiesTest(unittest.TestCase):
    def test_required_symbols_cover_both_strategies(self) -> None:
        symbols = required_private_strategy_symbols()
        self.assertIn("00631L", symbols)
        self.assertIn("2330", symbols)
        self.assertIn("6669", symbols)
        self.assertNotIn("2891", symbols)
        self.assertEqual(len(STRATEGIES), 2)
        defensive = STRATEGIES[0]
        self.assertEqual(
            (defensive.entry_ma, defensive.entry_slope, defensive.exit_ma, defensive.exit_slope, defensive.cooldown),
            (4, 7, 10, 20, 7),
        )
        self.assertEqual(
            defensive.mode_label,
            "MA4＋近7日上漲買入／MA10＋近20日下跌賣出／CD7",
        )

    def test_rising_series_builds_ranked_entry_candidate(self) -> None:
        history = {}
        for index, symbol in enumerate(required_private_strategy_symbols()):
            history[symbol] = _rows(100 + index, step=0.5 + index / 100)
        with TemporaryDirectory() as temp:
            state_path = Path(temp) / "state.json"
            checkpoints = build_private_strategy_checkpoints(
                history,
                report_date="2026-07-20",
                next_execution_date="2026-07-21",
                state_path=state_path,
                **_calendar(),
            )
            self.assertEqual(len(checkpoints), 2)
            self.assertTrue(all(item["candidate_count"] > 0 for item in checkpoints))
            self.assertTrue(all(item["today_action"] == "buy_next_day" for item in checkpoints))
            self.assertEqual(checkpoints[0]["cooldown_next_tradable_date"], "2026-07-30")
            self.assertEqual(checkpoints[0]["cooldown_remaining_trading_days"], 7)
            self.assertEqual(checkpoints[0]["cooldown_start_signal_role"], "buy")
            self.assertEqual(checkpoints[0]["cooldown_status"], "locked")
            html = render_private_signal_report(
                Report(
                    title="Radar",
                    generated_at="2026-07-20",
                    market_view="private",
                    sector_results=[],
                    stock_results=[],
                    private_strategies=checkpoints,
                )
            )
            self.assertIn("進場區塊", html)
            self.assertIn("出場區塊", html)
            self.assertIn("下次可交易日期＝2026/7/30", html)
            self.assertIn("近7日價格漲跌", html)
            self.assertIn("今日收盤相對 6 個交易日前；通過：上漲", html)
            self.assertIn("近20日價格漲跌", html)
            self.assertNotIn("進場斜率", html)
            self.assertNotIn("出場斜率", html)
            persisted = json.loads(state_path.read_text(encoding="utf-8"))
            self.assertEqual(len(persisted), 2)

    def test_old_forced_buy_state_is_reset_by_signal_required_version(self) -> None:
        history = {
            symbol: _rows(140, step=-0.5)
            for symbol in required_private_strategy_symbols()
        }
        with TemporaryDirectory() as temp:
            state_path = Path(temp) / "state.json"
            state_path.write_text(
                json.dumps(
                    {
                        "00631l_buy_and_hold": {
                            "pending_action": {
                                "role": "buy",
                                "ticker": "00631L",
                                "decision_date": "2026-07-20",
                                "execution_date": "2026-07-21",
                            }
                        },
                        "00631l_ma4_s7_cd7": {
                            "last_processed_date": "2026-07-20",
                            "pending_action": {
                                "role": "buy",
                                "ticker": "00631L",
                                "decision_date": "2026-07-20",
                                "execution_date": "2026-07-21",
                            },
                        }
                    }
                ),
                encoding="utf-8",
            )
            checkpoints = build_private_strategy_checkpoints(
                history,
                report_date="2026-07-20",
                next_execution_date="2026-07-21",
                state_path=state_path,
                **_calendar(),
            )
            defensive = checkpoints[0]
            self.assertEqual(defensive["today_action"], "stay_flat")
            persisted = json.loads(state_path.read_text(encoding="utf-8"))
            self.assertEqual(persisted["00631l_ma4_s7_cd7"]["pending_action"], {})
            self.assertIn("state_version", persisted["00631l_ma4_s7_cd7"])
            self.assertNotIn("00631l_buy_and_hold", persisted)

    def test_activation_date_keeps_all_models_flat_before_monday(self) -> None:
        history = {
            symbol: _rows(100, step=0.5)
            for symbol in required_private_strategy_symbols()
        }
        with TemporaryDirectory() as temp:
            checkpoints = build_private_strategy_checkpoints(
                history,
                report_date="2026-07-17",
                next_execution_date="2026-07-20",
                state_path=Path(temp) / "state.json",
                **_calendar(),
            )
            self.assertTrue(all(item["today_action"] == "stay_flat" for item in checkpoints))
            self.assertTrue(all(not item["held_ticker"] for item in checkpoints))
            self.assertTrue(all(item["data_ready_count"] == item["pool_size"] for item in checkpoints))
            self.assertTrue(all(item["focus_metrics"].get("ready") for item in checkpoints))
            self.assertTrue(all(item["signal_ticker"] for item in checkpoints))

    def test_held_stock_exit_respects_cooldown(self) -> None:
        spec = STRATEGIES[1]
        history = {symbol: _rows(140, step=-0.6) for symbol in spec.symbols}
        with TemporaryDirectory() as temp:
            state_path = Path(temp) / "state.json"
            state_path.write_text(
                json.dumps(
                    {
                        spec.strategy_id: {
                            "state_version": PRIVATE_STRATEGY_STATE_VERSION,
                            "activation_date": "2026-07-01",
                            "last_processed_date": "2026-07-01",
                            "held_ticker": "2330",
                            "buy_date": "2026-07-01",
                            "last_sold_ticker": "",
                            "pending_action": {},
                        }
                    }
                ),
                encoding="utf-8",
            )
            checkpoints = build_private_strategy_checkpoints(
                history,
                report_date="2026-07-17",
                next_execution_date="2026-07-20",
                state_path=state_path,
                **_calendar(),
            )
            checkpoint = next(
                item for item in checkpoints if item["strategy_id"] == spec.strategy_id
            )
            self.assertEqual(checkpoint["today_action"], "sell_next_day")
            self.assertEqual(checkpoint["cooldown_start_signal_role"], "sell")


def _calendar() -> dict[str, set[date]]:
    open_dates: set[date] = set()
    cursor = date(2026, 6, 1)
    end = date(2026, 9, 1)
    while cursor <= end:
        if cursor.weekday() < 5:
            open_dates.add(cursor)
        cursor += timedelta(days=1)
    return {"open_dates": open_dates, "closed_dates": set()}


def _rows(start: float, *, step: float) -> list[dict[str, float | str]]:
    cursor = date(2026, 6, 1)
    rows = []
    value = start
    while len(rows) < 35:
        if cursor.weekday() < 5:
            rows.append(
                {
                    "date": cursor.isoformat(),
                    "open": value,
                    "high": value,
                    "low": value,
                    "close": value,
                }
            )
            value += step
        cursor += timedelta(days=1)
    return rows
