from __future__ import annotations

import csv
import unittest
from pathlib import Path
from tempfile import TemporaryDirectory

from rotation_radar.radar_snapshot import build_radar_snapshots


class RadarSnapshotTests(unittest.TestCase):
    def test_builds_fail_closed_snapshots_without_future_window_leakage(self) -> None:
        with TemporaryDirectory() as temp_dir:
            root = Path(temp_dir)
            processed_root = root / "processed"
            output_dir = root / "history"
            _write_theme_history(root / "theme_history.csv")
            _write_theme_map(root / "theme_map.csv")
            _write_stock_metrics(root / "stock_metrics.csv")
            _write_stock_metrics(root / "baseline_stock_metrics.csv")
            _write_prices(processed_root / "20260603", "2330", "台積電", 600, 1_000_000_000)
            _write_prices(processed_root / "20260604", "2330", "台積電", 606, 2_000_000_000)

            result = build_radar_snapshots(
                processed_root=processed_root,
                theme_history_path=root / "theme_history.csv",
                theme_map_path=root / "theme_map.csv",
                stock_metrics_path=root / "stock_metrics.csv",
                output_dir=output_dir,
                days=2,
                baseline_stock_metrics_path=root / "baseline_stock_metrics.csv",
            )

            self.assertEqual([path.name for path in result.paths], ["radar_snapshot_20260603.csv", "radar_snapshot_20260604.csv"])
            first = _read_single_row(output_dir / "radar_snapshot_20260603.csv")
            second = _read_single_row(output_dir / "radar_snapshot_20260604.csv")
            self.assertEqual(first["fundamental_pass"], "true")
            self.assertEqual(first["fundamental_data_status"], "ok")
            self.assertEqual(first["fundamental_source_date"], "2026-06-03")
            self.assertEqual(first["bucket"], "theme_leader")
            self.assertEqual(second["fundamental_pass"], "true")
            self.assertEqual(second["fundamental_data_status"], "ok")
            self.assertEqual(second["fundamental_source_date"], "2026-06-04")
            self.assertEqual(first["capital_share_5d_change"], "0.0")
            self.assertEqual(second["capital_share_5d_change"], "2.0")
            self.assertEqual(second["stock_turnover_share_in_theme"], "100.0")
            self.assertTrue((output_dir / "fundamental_snapshot_20260603.csv").exists())
            self.assertTrue((output_dir / "fundamental_snapshot_20260604.csv").exists())


def _write_theme_history(path: Path) -> None:
    with path.open("w", encoding="utf-8-sig", newline="") as handle:
        writer = csv.DictWriter(
            handle,
            fieldnames=["date", "theme", "rank", "capital_share", "turnover_value", "strong_stock_ratio", "risk_heat"],
        )
        writer.writeheader()
        writer.writerow(
            {
                "date": "2026-06-03",
                "theme": "先進製程",
                "rank": 1,
                "capital_share": 10,
                "turnover_value": 1000,
                "strong_stock_ratio": 60,
                "risk_heat": 30,
            }
        )
        writer.writerow(
            {
                "date": "2026-06-04",
                "theme": "先進製程",
                "rank": 1,
                "capital_share": 12,
                "turnover_value": 1200,
                "strong_stock_ratio": 70,
                "risk_heat": 35,
            }
        )


def _write_theme_map(path: Path) -> None:
    with path.open("w", encoding="utf-8-sig", newline="") as handle:
        writer = csv.DictWriter(handle, fieldnames=["theme", "symbol", "name"])
        writer.writeheader()
        writer.writerow({"theme": "先進製程", "symbol": "2330", "name": "台積電"})


def _write_stock_metrics(path: Path) -> None:
    with path.open("w", encoding="utf-8-sig", newline="") as handle:
        writer = csv.DictWriter(
            handle,
            fieldnames=["symbol", "foreign_5d", "trust_5d", "margin_change_5d", "pe", "revenue_yoy", "revenue_mom", "risk_reason"],
        )
        writer.writeheader()
        writer.writerow(
            {
                "symbol": "2330",
                "foreign_5d": "1000",
                "trust_5d": "200",
                "margin_change_5d": "-10",
                "pe": "20",
                "revenue_yoy": "10",
                "revenue_mom": "-5",
                "risk_reason": "",
            }
        )


def _write_prices(path: Path, symbol: str, name: str, close: int, amount: int) -> None:
    path.mkdir(parents=True, exist_ok=True)
    with (path / "twse_prices_table1.csv").open("w", encoding="utf-8-sig", newline="") as handle:
        writer = csv.DictWriter(handle, fieldnames=["證券代號", "證券名稱", "收盤價", "成交金額"])
        writer.writeheader()
        writer.writerow({"證券代號": symbol, "證券名稱": name, "收盤價": close, "成交金額": amount})


def _read_single_row(path: Path) -> dict[str, str]:
    with path.open("r", encoding="utf-8-sig", newline="") as handle:
        return next(csv.DictReader(handle))


if __name__ == "__main__":
    unittest.main()
