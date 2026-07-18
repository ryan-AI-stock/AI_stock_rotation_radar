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
    def test_required_symbols_cover_both_pools(self) -> None:
        symbols = required_private_strategy_symbols()
        self.assertIn("2330", symbols)
        self.assertIn("6669", symbols)
        self.assertIn("2891", symbols)
        self.assertEqual(len(STRATEGIES), 2)

    def test_rising_series_builds_ranked_entry_candidate(self) -> None:
        history = {}
        for index, symbol in enumerate(required_private_strategy_symbols()):
            history[symbol] = _rows(100 + index, step=0.5 + index / 100)
        with TemporaryDirectory() as temp:
            state_path = Path(temp) / "state.json"
            checkpoints = build_private_strategy_checkpoints(
                history,
                report_date="2026-07-17",
                next_execution_date="2026-07-20",
                state_path=state_path,
            )
            self.assertEqual(len(checkpoints), 2)
            self.assertTrue(all(item["candidate_count"] > 0 for item in checkpoints))
            self.assertTrue(all(item["today_action"] == "buy_next_day" for item in checkpoints))
            persisted = json.loads(state_path.read_text(encoding="utf-8"))
            self.assertEqual(len(persisted), 2)

    def test_held_stock_exit_respects_cooldown(self) -> None:
        spec = STRATEGIES[0]
        history = {symbol: _rows(140, step=-0.6) for symbol in spec.symbols}
        with TemporaryDirectory() as temp:
            state_path = Path(temp) / "state.json"
            state_path.write_text(
                json.dumps(
                    {
                        spec.strategy_id: {
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
            checkpoint = build_private_strategy_checkpoints(
                history,
                report_date="2026-07-17",
                next_execution_date="2026-07-20",
                state_path=state_path,
            )[0]
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
