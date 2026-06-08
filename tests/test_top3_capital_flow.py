from __future__ import annotations

import csv
import json
import tempfile
import unittest
from pathlib import Path

from rotation_radar.formal_sources.top3_capital_flow import (
    CANDIDATE_FIELDS,
    DAILY_RANKING_FIELDS,
    GAP_FIELDS,
    SNAPSHOT_FIELDS,
    build_formal_top3_capital_flow_package,
    validate_top3_capital_flow_package,
)


class Top3CapitalFlowTests(unittest.TestCase):
    def test_builds_formal_blocked_package_when_theme_membership_is_blocked(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            output = root / "package"
            turnover = root / "turnover.csv"
            official_ready = root / "official.json"
            fundamental_ready = root / "fundamental.json"
            theme_ready = root / "theme.json"
            memory_ready = root / "memory.json"
            _write_csv(
                turnover,
                ["symbol", "date", "official_turnover_value", "exchange", "source", "source_url", "ingested_at"],
                [
                    {
                        "symbol": "2408",
                        "date": "2022-01-03",
                        "official_turnover_value": "1000",
                        "exchange": "TWSE",
                        "source": "twse_stock_day",
                        "source_url": "https://example.test",
                        "ingested_at": "2026-06-08T00:00:00+00:00",
                    },
                    {
                        "symbol": "2408",
                        "date": "2022-01-04",
                        "official_turnover_value": "2000",
                        "exchange": "TWSE",
                        "source": "twse_stock_day",
                        "source_url": "https://example.test",
                        "ingested_at": "2026-06-08T00:00:00+00:00",
                    },
                ],
            )
            official_ready.write_text(json.dumps({"coverage_ratio": 0.99}), encoding="utf-8")
            fundamental_ready.write_text(
                json.dumps({"coverage_ratio": 1.0, "future_data_violation_count": 0}),
                encoding="utf-8",
            )
            theme_ready.write_text(
                json.dumps({"coverage_ratio": 0.0, "source_mode": "current_static_map_blocked", "static_only_count": 69}),
                encoding="utf-8",
            )
            memory_ready.write_text(
                json.dumps({"coverage_ratio": 0.88888889, "source_mode": "date_aware_partial", "static_only_count": 1}),
                encoding="utf-8",
            )

            payload = build_formal_top3_capital_flow_package(
                output_dir=output,
                start_date="2022-01-03",
                end_date="2022-01-04",
                official_turnover_file=turnover,
                official_turnover_readiness=official_ready,
                fundamental_readiness=fundamental_ready,
                theme_membership_readiness=theme_ready,
                memory_theme_membership_readiness=memory_ready,
            )

            self.assertFalse(payload["ready"])
            self.assertEqual(payload["source_mode"], "formal_blocked")
            self.assertEqual(payload["trading_day_count"], 2)
            self.assertEqual(payload["missing_top3_theme_date_count"], 2)
            self.assertEqual(payload["future_data_violation_count"], 0)
            self.assertIn("date_aware_theme_membership_full_universe_blocked", payload["blocking_issues"])
            self.assertEqual(_read_header(output / "top3_theme_daily_ranking_2022_2023.csv"), DAILY_RANKING_FIELDS)
            self.assertEqual(_read_header(output / "top3_theme_stock_candidates_2022_2023.csv"), CANDIDATE_FIELDS)
            self.assertEqual(_read_header(output / "top3_capital_flow_snapshot_2022_2023.csv"), SNAPSHOT_FIELDS)
            self.assertEqual(_read_header(output / "top3_capital_flow_gap_report.csv"), GAP_FIELDS)

    def test_validator_accepts_formal_blocked_package_with_required_files(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            output = root / "package"
            turnover = root / "turnover.csv"
            official_ready = root / "official.json"
            fundamental_ready = root / "fundamental.json"
            theme_ready = root / "theme.json"
            memory_ready = root / "memory.json"
            _write_csv(turnover, ["symbol", "date"], [{"symbol": "2408", "date": "2022-01-03"}])
            official_ready.write_text(json.dumps({"coverage_ratio": 1.0}), encoding="utf-8")
            fundamental_ready.write_text(
                json.dumps({"coverage_ratio": 1.0, "future_data_violation_count": 0}),
                encoding="utf-8",
            )
            theme_ready.write_text(
                json.dumps({"coverage_ratio": 0.0, "source_mode": "current_static_map_blocked", "static_only_count": 1}),
                encoding="utf-8",
            )
            memory_ready.write_text(json.dumps({}), encoding="utf-8")
            build_formal_top3_capital_flow_package(
                output_dir=output,
                start_date="2022-01-03",
                end_date="2022-01-03",
                official_turnover_file=turnover,
                official_turnover_readiness=official_ready,
                fundamental_readiness=fundamental_ready,
                theme_membership_readiness=theme_ready,
                memory_theme_membership_readiness=memory_ready,
            )

            payload = validate_top3_capital_flow_package(output_dir=output)

            self.assertFalse(payload["ready"])
            self.assertEqual(payload["source_mode"], "formal_blocked")


def _write_csv(path: Path, fieldnames: list[str], rows: list[dict[str, str]]) -> None:
    with path.open("w", encoding="utf-8-sig", newline="") as handle:
        writer = csv.DictWriter(handle, fieldnames=fieldnames)
        writer.writeheader()
        writer.writerows(rows)


def _read_header(path: Path) -> list[str]:
    with path.open("r", encoding="utf-8-sig", newline="") as handle:
        return next(csv.reader(handle))
