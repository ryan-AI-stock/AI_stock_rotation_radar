from __future__ import annotations

import csv
import json
import tempfile
import unittest
from pathlib import Path

from rotation_radar.formal_sources.backtest_factor_package import (
    GAP_FIELDS,
    build_backtest_factor_package,
)


class BacktestFactorPackageTests(unittest.TestCase):
    def test_builds_partial_package_and_blocks_valuation(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            for factor_id, source_mode in [
                ("institutional_flows", "institutional_flow_ready"),
                ("margin_short", "margin_short_ready"),
                ("day_trading", "day_trading_ready"),
            ]:
                _write_readiness(root / _readiness_name(factor_id), source_mode)
                _write_csv(root / _csv_name(factor_id), ["date", "ticker"], [{"date": "2024-01-02", "ticker": "2330.TW"}])
                _write_csv(root / _gap_name(factor_id), ["symbol", "ticker", "date", "missing_reason"], [])

            payload = build_backtest_factor_package(package_dir=root)

            self.assertFalse(payload["ready"])
            self.assertEqual(payload["source_mode"], "backtest_factor_package_partial")
            self.assertTrue(payload["factor_status"]["institutional_flows"]["ready"])
            self.assertFalse(payload["factor_status"]["valuation"]["ready"])
            self.assertEqual(payload["factor_status"]["valuation"]["source_mode"], "valuation_point_in_time_blocked")
            self.assertEqual(payload["active_in_trade_decision"], False)
            self.assertEqual(_read_header(root / "gap.csv"), GAP_FIELDS)
            self.assertIn("Do not use later manual snapshots", (root / "manifest.md").read_text(encoding="utf-8"))

    def test_marks_missing_source_as_blocked(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            payload = build_backtest_factor_package(package_dir=root)

            self.assertFalse(payload["factor_status"]["institutional_flows"]["ready"])
            self.assertEqual(payload["factor_status"]["institutional_flows"]["status"], "blocked")
            self.assertIn("institutional_flows", payload["blocking_issues"][0])


def _write_readiness(path: Path, source_mode: str) -> None:
    path.write_text(
        json.dumps(
            {
                "ready": True,
                "source_mode": source_mode,
                "start_date": "2024-01-02",
                "end_date": "2026-05-26",
                "coverage_ratio": 1.0,
                "stock_coverage_ratio": 1.0,
                "future_data_violation_count": 0,
                "stock_gap_count": 0,
                "blocking_issues": [],
                "warnings": [],
            },
            ensure_ascii=False,
        ),
        encoding="utf-8",
    )


def _csv_name(factor_id: str) -> str:
    return {
        "institutional_flows": "institutional_flows_daily_20240102_20260526.csv",
        "margin_short": "margin_short_daily_20240102_20260526.csv",
        "day_trading": "day_trading_daily_20240102_20260526.csv",
    }[factor_id]


def _readiness_name(factor_id: str) -> str:
    return _csv_name(factor_id).replace(".csv", "_readiness.json")


def _gap_name(factor_id: str) -> str:
    return _csv_name(factor_id).replace(".csv", "_gap.csv")


def _write_csv(path: Path, fieldnames: list[str], rows: list[dict[str, str]]) -> None:
    with path.open("w", encoding="utf-8-sig", newline="") as handle:
        writer = csv.DictWriter(handle, fieldnames=fieldnames)
        writer.writeheader()
        writer.writerows(rows)


def _read_header(path: Path) -> list[str]:
    with path.open("r", encoding="utf-8-sig", newline="") as handle:
        return next(csv.reader(handle))
