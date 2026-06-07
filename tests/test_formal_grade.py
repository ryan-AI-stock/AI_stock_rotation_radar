from __future__ import annotations

import csv
import json
import tempfile
from pathlib import Path
from unittest import TestCase

from rotation_radar.formal_grade import build_formal_grade_audit


class FormalGradeAuditTests(TestCase):
    def test_builds_blocked_formal_grade_audit_without_promoting_limited_replay(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            source = root / "backtest_grade"
            source.mkdir()
            theme_map = root / "theme_map.csv"
            output = root / "formal_grade"

            _write_csv(
                theme_map,
                ["theme", "symbol", "name", "role", "conviction", "primary"],
                [
                    {"theme": "記憶體", "symbol": "2408", "name": "南亞科", "role": "DRAM", "conviction": "high", "primary": "yes"},
                    {"theme": "記憶體", "symbol": "2344", "name": "華邦電", "role": "DRAM", "conviction": "high", "primary": "yes"},
                    {"theme": "PCB/載板", "symbol": "3037", "name": "欣興", "role": "載板", "conviction": "high", "primary": "yes"},
                ],
            )
            _write_csv(
                source / "historical_backtest_grade_daily_coverage.csv",
                ["date", "row_count", "fundamental_pass_rows"],
                [
                    {"date": "20211201", "row_count": "2", "fundamental_pass_rows": "1"},
                    {"date": "20211202", "row_count": "2", "fundamental_pass_rows": "1"},
                ],
            )
            _write_json(
                source / "historical_backtest_grade_manifest.json",
                {
                    "dataset_mode": "backtest_grade_limited_replay",
                    "snapshot_count": 2,
                },
            )
            _write_json(
                source / "historical_backtest_grade_readiness.json",
                {
                    "ready_for_backtest_lab_ingestion": True,
                    "ready_for_formal_strategy_conclusion": False,
                    "readiness_status": "ready_with_limitations",
                    "requested_start_date": "2021-12-01",
                    "requested_end_date": "2023-12-31",
                    "actual_start_date": "20211201",
                    "actual_end_date": "20211202",
                    "snapshot_count": 2,
                    "future_fundamental_violation_count": 0,
                    "missing_ohlcv_symbols": ["2344"],
                    "missing_fundamental_symbols": ["3037"],
                    "fundamental_mode": "limited_baseline_seed_carry_forward",
                    "theme_membership_mode": "current_static_map",
                    "turnover_mode": "approximate_close_times_volume",
                },
            )

            result = build_formal_grade_audit(
                source_dir=source,
                output_dir=output,
                theme_map_path=theme_map,
            )

            manifest = json.loads(result.manifest_path.read_text(encoding="utf-8"))
            readiness = json.loads(result.readiness_path.read_text(encoding="utf-8"))
            daily_rows = _read_csv(result.daily_coverage_path)
            formal_universe = _read_csv(result.formal_universe_path)
            unavailable = _read_csv(result.unavailable_items_path)

            self.assertEqual(manifest["dataset_type"], "historical_formal_grade_audit")
            self.assertEqual(manifest["dataset_mode"], "formal_grade_blocked")
            self.assertEqual(manifest["formal_snapshot_count"], 0)
            self.assertFalse(manifest["ready_for_formal_strategy_conclusion"])
            self.assertFalse(readiness["ready_for_formal_strategy_conclusion"])
            self.assertEqual(readiness["readiness_status"], "blocked_source_data_unavailable")
            self.assertTrue(readiness["acceptance_criteria"]["future_fundamental_violation_count_is_zero"])
            self.assertTrue(readiness["acceptance_criteria"]["formal_universe_missing_ohlcv_is_zero"])
            self.assertFalse(readiness["acceptance_criteria"]["fundamental_not_baseline_seed_carry_forward"])
            self.assertFalse(readiness["acceptance_criteria"]["theme_membership_not_current_static_map_only"])
            self.assertFalse(readiness["acceptance_criteria"]["turnover_not_close_times_volume_only"])
            self.assertEqual(len(daily_rows), 2)
            self.assertEqual(daily_rows[0]["formal_ready"], "false")
            self.assertEqual({row["symbol"] for row in formal_universe}, {"2408", "3037"})
            self.assertEqual(
                {row["item"] for row in unavailable},
                {"point_in_time_fundamentals", "date_aware_theme_membership", "official_exchange_turnover"},
            )


def _write_json(path: Path, data: dict[str, object]) -> None:
    path.write_text(json.dumps(data, ensure_ascii=False, indent=2), encoding="utf-8")


def _write_csv(path: Path, fieldnames: list[str], rows: list[dict[str, str]]) -> None:
    with path.open("w", encoding="utf-8-sig", newline="") as handle:
        writer = csv.DictWriter(handle, fieldnames=fieldnames)
        writer.writeheader()
        writer.writerows(rows)


def _read_csv(path: Path) -> list[dict[str, str]]:
    with path.open("r", encoding="utf-8-sig", newline="") as handle:
        return list(csv.DictReader(handle))
