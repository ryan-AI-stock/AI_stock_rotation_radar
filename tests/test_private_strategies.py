from __future__ import annotations

import json
import unittest
from datetime import date, timedelta
from pathlib import Path
from tempfile import TemporaryDirectory

from rotation_radar.private_strategies import (
    STRATEGIES,
    build_private_strategy_checkpoints,
    required_private_strategy_symbols,
)


class PrivateStrategiesTest(unittest.TestCase):
    def test_required_symbols_cover_all_three_strategies(self) -> None:
        symbols = required_private_strategy_symbols()
        self.assertIn("00631L", symbols)
        self.assertIn("2330", symbols)
        self.assertIn("6669", symbols)
        self.assertIn("2891", symbols)
        self.assertEqual(len(STRATEGIES), 3)

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
            )
            self.assertEqual(len(checkpoints), 3)
            self.assertTrue(all(item["candidate_count"] > 0 for item in checkpoints))
            self.assertTrue(all(item["today_action"] == "buy_next_day" for item in checkpoints))
            persisted = json.loads(state_path.read_text(encoding="utf-8"))
            self.assertEqual(len(persisted), 3)

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
            )
            checkpoint = next(
                item for item in checkpoints if item["strategy_id"] == spec.strategy_id
            )
            self.assertEqual(checkpoint["today_action"], "sell_next_day")


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
