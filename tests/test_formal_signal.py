from __future__ import annotations

import json
import unittest
from datetime import date, timedelta
from pathlib import Path
from tempfile import TemporaryDirectory

from rotation_radar.formal_signal import (
    build_formal_signal_checkpoint,
    validate_formal_signal_checkpoint,
)
from rotation_radar.models import Report
from rotation_radar.report import render_report


class FormalSignalTests(unittest.TestCase):
    def test_actual_and_model_execution_dates_may_match_with_distinct_lineage(self) -> None:
        checkpoint = {
            "actual_trade_date": "2026-07-16",
            "actual_trade_date_source": "user_actual_trade_override",
            "model_next_day_execution_date": "2026-07-16",
            "model_next_day_execution_date_source": "official_trading_calendar_after_report_close",
        }

        validate_formal_signal_checkpoint(checkpoint)

    def test_validator_rejects_mixed_date_lineage(self) -> None:
        checkpoint = {
            "actual_trade_date": "2026-07-16",
            "actual_trade_date_source": "official_trading_calendar_after_report_close",
            "model_next_day_execution_date": "2026-07-16",
            "model_next_day_execution_date_source": "official_trading_calendar_after_report_close",
        }

        with self.assertRaisesRegex(ValueError, "actual_trade_date"):
            validate_formal_signal_checkpoint(checkpoint)

    def test_cd7_counts_only_normal_trading_days(self) -> None:
        checkpoint = self._build(
            report_date="2026-07-15",
            closes=_rising_closes(),
            actual_trades=[_trade("2026-07-15", "buy")],
        )

        self.assertEqual(
            checkpoint["blocked_trading_dates"],
            [
                "2026-07-16",
                "2026-07-17",
                "2026-07-20",
                "2026-07-21",
                "2026-07-22",
                "2026-07-23",
                "2026-07-24",
            ],
        )
        self.assertEqual(checkpoint["next_tradable_date"], "2026-07-27")
        self.assertNotIn("2026-07-18", checkpoint["blocked_trading_dates"])
        self.assertNotIn("2026-07-19", checkpoint["blocked_trading_dates"])

    def test_emergency_closure_shifts_cd_unlock_date(self) -> None:
        checkpoint = self._build(
            report_date="2026-07-15",
            closes=_rising_closes(),
            actual_trades=[_trade("2026-07-15", "buy")],
            closed_dates={date(2026, 7, 16)},
        )

        self.assertNotIn("2026-07-16", checkpoint["blocked_trading_dates"])
        self.assertEqual(checkpoint["blocked_trading_dates"][-1], "2026-07-27")
        self.assertEqual(checkpoint["next_tradable_date"], "2026-07-28")

    def test_historical_emergency_closure_is_derived_and_persisted(self) -> None:
        checkpoint = self._build(
            report_date="2026-07-17",
            closes=_rising_closes(),
            actual_trades=[_trade("2026-07-15", "buy")],
            missing_price_dates={date(2026, 7, 16)},
            session_status_by_date={date(2026, 7, 16): "closed"},
        )

        self.assertEqual(checkpoint["derived_emergency_closed_dates"], ["2026-07-16"])
        self.assertEqual(checkpoint["historical_session_confirmation_status"], "ready")
        self.assertEqual(
            checkpoint["blocked_trading_dates"],
            [
                "2026-07-17",
                "2026-07-20",
                "2026-07-21",
                "2026-07-22",
                "2026-07-23",
                "2026-07-24",
                "2026-07-27",
            ],
        )
        self.assertEqual(checkpoint["next_tradable_date"], "2026-07-28")

    def test_derived_emergency_closure_is_reused_from_state(self) -> None:
        with TemporaryDirectory() as temp_dir:
            root = Path(temp_dir)
            override_path = root / "override.json"
            override_path.write_text(
                json.dumps({"actual_trades": [_trade("2026-07-15", "buy")]}),
                encoding="utf-8",
            )
            first_rows = [
                row for row in _price_rows("2026-07-17", _rising_closes()) if row["date"] != "2026-07-16"
            ]
            build_formal_signal_checkpoint(
                first_rows,
                report_date="2026-07-17",
                state_path=root / "state.json",
                override_path=override_path,
                checkpoint_path=root / "checkpoint.json",
                open_dates=set(),
                closed_dates=set(),
                session_status="open",
                session_status_by_date={date(2026, 7, 16): "closed"},
            )
            second_rows = [
                row for row in _price_rows("2026-07-20", _rising_closes()) if row["date"] != "2026-07-16"
            ]
            checkpoint = build_formal_signal_checkpoint(
                second_rows,
                report_date="2026-07-20",
                state_path=root / "state.json",
                override_path=override_path,
                checkpoint_path=root / "checkpoint.json",
                open_dates=set(),
                closed_dates=set(),
                session_status="open",
                session_status_by_date={},
            )

        self.assertIn("2026-07-16", checkpoint["persisted_emergency_closed_dates"])
        self.assertEqual(checkpoint["unresolved_historical_session_dates"], [])
        self.assertEqual(checkpoint["next_tradable_date"], "2026-07-28")

    def test_slope_windows_use_n_observations_not_n_lags(self) -> None:
        closes = [95.0] * 12 + [101.0, 99.0, 99.0, 99.0, 98.0, 99.0, 99.0, 100.0]
        checkpoint = self._build(
            report_date="2026-07-15",
            closes=closes,
            actual_trades=[],
        )

        self.assertEqual(checkpoint["schema_version"], 2)
        self.assertEqual(checkpoint["close_6_trading_days_ago"], 99.0)
        self.assertEqual(checkpoint["close_19_trading_days_ago"], 95.0)
        self.assertEqual(checkpoint["slope_7d_value"], 1.0)
        self.assertEqual(checkpoint["slope_20d_value"], 5.0)
        self.assertEqual(checkpoint["today_signal"], "entry")

    def test_scheduled_holiday_is_not_counted_as_cd_session(self) -> None:
        checkpoint = self._build(
            report_date="2026-07-15",
            closes=_rising_closes(),
            actual_trades=[_trade("2026-07-15", "buy")],
            closed_dates={date(2026, 7, 20)},
        )

        self.assertNotIn("2026-07-20", checkpoint["blocked_trading_dates"])
        self.assertEqual(checkpoint["next_tradable_date"], "2026-07-28")

    def test_unlock_uses_current_close_signal_without_carrying_old_signal(self) -> None:
        trades = [_trade("2026-07-15", "sell")]
        blocked = self._build(
            report_date="2026-07-16",
            closes=_rising_closes(),
            actual_trades=trades,
        )
        unlocked = self._build(
            report_date="2026-07-24",
            closes=[100.0] * 21,
            actual_trades=trades,
        )

        self.assertEqual(blocked["today_signal"], "entry")
        self.assertEqual(blocked["model_next_day_execution_action"], "cooldown_blocked_buy_00631L")
        self.assertEqual(unlocked["today_signal"], "none")
        self.assertEqual(unlocked["model_next_day_execution_action"], "stay_flat")
        self.assertIsNone(unlocked["pending_signal"])
        self.assertFalse(unlocked["signal_carry_forward_used"])

    def test_closed_market_produces_no_signal_action(self) -> None:
        checkpoint = self._build(
            report_date="2026-07-16",
            closes=_rising_closes(),
            actual_trades=[],
            session_status="closed",
            closed_dates={date(2026, 7, 16)},
        )

        self.assertEqual(checkpoint["model_next_day_execution_action"], "market_closed_no_signal")

    def test_report_renders_formal_mode_position_and_cd_calendar(self) -> None:
        formal_signal = self._build(
            report_date="2026-07-15",
            closes=_rising_closes(),
            actual_trades=[_trade("2026-07-15", "buy")],
        )
        html = render_report(
            Report(
                title="Radar",
                generated_at="2026-07-15 21:30",
                market_view="正式模式",
                sector_results=[],
                stock_results=[],
                formal_signal=formal_signal,
            )
        )

        self.assertIn("正式 0050 訊號 / 00631L 執行", html)
        self.assertIn("MA4＋7日正斜率買入／MA10＋20日負斜率賣出／CD7", html)
        self.assertIn("0050 今日收盤", html)
        self.assertIn("持有 00631L", html)
        self.assertIn("7/16、7/17、7/20、7/21、7/22、7/23、7/24", html)
        self.assertIn("2026-07-27", html)

    def test_report_marks_actual_buy_that_was_not_a_model_entry_signal(self) -> None:
        formal_signal = self._build(
            report_date="2026-07-15",
            closes=[100.0] * 20,
            actual_trades=[_trade("2026-07-15", "buy")],
        )
        html = render_report(
            Report(
                title="Radar",
                generated_at="2026-07-15 21:30",
                market_view="正式模式",
                sector_results=[],
                stock_results=[],
                formal_signal=formal_signal,
            )
        )

        self.assertEqual(formal_signal["today_signal"], "none")
        self.assertIn("本日實際買進；不是本日模型買訊", html)

    def _build(
        self,
        *,
        report_date: str,
        closes: list[float],
        actual_trades: list[dict],
        closed_dates: set[date] | None = None,
        session_status: str = "open",
        missing_price_dates: set[date] | None = None,
        session_status_by_date: dict[date, str] | None = None,
    ) -> dict:
        with TemporaryDirectory() as temp_dir:
            root = Path(temp_dir)
            override_path = root / "override.json"
            override_path.write_text(
                json.dumps({"actual_trades": actual_trades}),
                encoding="utf-8",
            )
            price_rows = [
                row
                for row in _price_rows(report_date, closes)
                if date.fromisoformat(str(row["date"])) not in set(missing_price_dates or set())
            ]
            return build_formal_signal_checkpoint(
                price_rows,
                report_date=report_date,
                state_path=root / "state.json",
                override_path=override_path,
                checkpoint_path=root / "checkpoint.json",
                open_dates=set(),
                closed_dates=set(closed_dates or set()),
                session_status=session_status,
                session_status_by_date=session_status_by_date,
            )


def _price_rows(report_date: str, closes: list[float]) -> list[dict[str, float | str]]:
    cursor = date.fromisoformat(report_date)
    dates: list[date] = []
    while len(dates) < len(closes):
        if cursor.weekday() < 5:
            dates.append(cursor)
        cursor -= timedelta(days=1)
    dates.reverse()
    return [{"date": trade_date.isoformat(), "close": close} for trade_date, close in zip(dates, closes)]


def _rising_closes() -> list[float]:
    return [100.0 + index for index in range(21)]


def _trade(trade_date: str, action: str) -> dict:
    return {
        "trade_date": trade_date,
        "action": action,
        "ticker": "00631L",
        "average_price": 37.265 if action == "buy" else None,
        "source": "user_actual_trade_override",
    }


if __name__ == "__main__":
    unittest.main()
