from __future__ import annotations

import csv
import json
import unittest
from pathlib import Path
from tempfile import TemporaryDirectory

from rotation_radar.historical_replay import build_historical_replay_snapshots


class HistoricalReplayTests(unittest.TestCase):
    def test_builds_replay_snapshots_with_manifest_and_fail_closed_fundamentals(self) -> None:
        with TemporaryDirectory() as temp_dir:
            root = Path(temp_dir)
            cache_dir = root / "cache"
            output_dir = root / "history_replay"
            _write_theme_map(root / "theme_map.csv")
            _write_stock_metrics(root / "stock_metrics.csv")
            _write_price_cache(cache_dir / "1111_TW.csv", "100", "1000000", "101", "1200000")
            _write_price_cache(cache_dir / "2222_TW.csv", "50", "2000000", "49", "1800000")

            result = build_historical_replay_snapshots(
                price_cache_dir=cache_dir,
                theme_map_path=root / "theme_map.csv",
                stock_metrics_path=root / "stock_metrics.csv",
                output_dir=output_dir,
                start_date="2022-01-03",
                end_date="2022-01-04",
            )

            self.assertEqual([path.name for path in result.paths], ["radar_snapshot_20220103.csv", "radar_snapshot_20220104.csv"])
            rows = _read_rows(output_dir / "radar_snapshot_20220104.csv")
            self.assertEqual({row["symbol"] for row in rows}, {"1111", "2222"})
            good = next(row for row in rows if row["symbol"] == "1111")
            missing = next(row for row in rows if row["symbol"] == "2222")
            self.assertEqual(good["fundamental_pass"], "true")
            self.assertEqual(good["fundamental_source_date"], "2022-01-03")
            self.assertEqual(missing["fundamental_pass"], "false")
            self.assertEqual(missing["fundamental_data_status"], "missing_fundamental_data")
            self.assertTrue(result.manifest_path.exists())
            self.assertTrue(result.coverage_path.exists())
            self.assertTrue(result.backtest_grade_manifest_path.exists())
            self.assertTrue(result.backtest_grade_readiness_path.exists())
            self.assertTrue(result.backtest_grade_daily_coverage_path.exists())

            manifest = json.loads(result.manifest_path.read_text(encoding="utf-8"))
            self.assertEqual(manifest["dataset_type"], "historical_replay")
            self.assertEqual(manifest["turnover_method"], "approximate_close_times_volume_million")
            self.assertEqual(manifest["covered_symbol_count"], 2)
            self.assertEqual(manifest["missing_symbol_count"], 1)
            self.assertIn("3333", manifest["missing_symbols"])

            backtest_manifest = json.loads(result.backtest_grade_manifest_path.read_text(encoding="utf-8"))
            self.assertEqual(backtest_manifest["dataset_type"], "historical_backtest_grade_replay")
            self.assertEqual(backtest_manifest["dataset_mode"], "backtest_grade_limited_replay")
            self.assertEqual(backtest_manifest["fundamental_mode"], "limited_baseline_seed_carry_forward")
            self.assertEqual(backtest_manifest["theme_membership_mode"], "current_static_map")
            self.assertEqual(backtest_manifest["turnover_mode"], "approximate_close_times_volume")
            self.assertFalse(backtest_manifest["readiness_summary"]["ready_for_formal_strategy_conclusion"])

            readiness = json.loads(result.backtest_grade_readiness_path.read_text(encoding="utf-8"))
            self.assertTrue(readiness["ready_for_backtest_lab_ingestion"])
            self.assertEqual(readiness["readiness_status"], "ready_with_limitations")
            self.assertEqual(readiness["required_columns_missing_count"], 0)
            self.assertEqual(readiness["future_fundamental_violation_count"], 0)
            self.assertIn("2222", readiness["missing_fundamental_symbols"])

            coverage_rows = _read_rows(result.backtest_grade_daily_coverage_path)
            self.assertEqual(len(coverage_rows), 2)
            self.assertEqual(coverage_rows[0]["theme_count"], "1")
            self.assertEqual(coverage_rows[0]["stock_count"], "2")


def _write_theme_map(path: Path) -> None:
    with path.open("w", encoding="utf-8-sig", newline="") as handle:
        writer = csv.DictWriter(handle, fieldnames=["theme", "symbol", "name"])
        writer.writeheader()
        writer.writerow({"theme": "Theme A", "symbol": "1111", "name": "Alpha"})
        writer.writerow({"theme": "Theme A", "symbol": "2222", "name": "Beta"})
        writer.writerow({"theme": "Theme B", "symbol": "3333", "name": "Gamma"})


def _write_stock_metrics(path: Path) -> None:
    with path.open("w", encoding="utf-8-sig", newline="") as handle:
        writer = csv.DictWriter(
            handle,
            fieldnames=["symbol", "name", "pe", "revenue_yoy", "revenue_mom", "foreign_5d", "trust_5d", "margin_change_5d", "risk_reason"],
        )
        writer.writeheader()
        writer.writerow(
            {
                "symbol": "1111",
                "name": "Alpha",
                "pe": "20",
                "revenue_yoy": "10",
                "revenue_mom": "-5",
                "foreign_5d": "100",
                "trust_5d": "50",
                "margin_change_5d": "-1",
                "risk_reason": "",
            }
        )


def _write_price_cache(path: Path, close_1: str, volume_1: str, close_2: str, volume_2: str) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("w", encoding="utf-8-sig", newline="") as handle:
        writer = csv.DictWriter(handle, fieldnames=["date", "open", "high", "low", "close", "adj_close", "volume", "dividend", "stock_split"])
        writer.writeheader()
        writer.writerow({"date": "2022-01-03", "open": close_1, "high": close_1, "low": close_1, "close": close_1, "adj_close": close_1, "volume": volume_1, "dividend": "0", "stock_split": "0"})
        writer.writerow({"date": "2022-01-04", "open": close_2, "high": close_2, "low": close_2, "close": close_2, "adj_close": close_2, "volume": volume_2, "dividend": "0", "stock_split": "0"})


def _read_rows(path: Path) -> list[dict[str, str]]:
    with path.open("r", encoding="utf-8-sig", newline="") as handle:
        return list(csv.DictReader(handle))


if __name__ == "__main__":
    unittest.main()
