from __future__ import annotations

import csv
import json
import tempfile
import unittest
from pathlib import Path

from rotation_radar.formal_sources.chip_flow_overlay import (
    GAP_FIELDS,
    INSTITUTIONAL_FIELDS,
    TARGET_UNIVERSE,
    build_chip_flow_overlay_package,
    validate_chip_flow_overlay_package,
)


class ChipFlowOverlayTests(unittest.TestCase):
    def test_builds_overlay_blocked_package_when_raw_sources_are_absent(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            output = Path(tmp) / "package"

            readiness = build_chip_flow_overlay_package(output_dir=output)

            self.assertFalse(readiness["ready"])
            self.assertEqual(readiness["source_mode"], "overlay_blocked")
            self.assertEqual(readiness["symbol_count"], len(TARGET_UNIVERSE))
            self.assertEqual(readiness["trading_day_count"], 507)
            self.assertEqual(readiness["missing_symbol_date_count"], len(TARGET_UNIVERSE) * 507)
            self.assertEqual(readiness["future_data_violation_count"], 0)
            self.assertFalse(readiness["feature_score_ready"])
            self.assertEqual(readiness["institutional_flow_coverage_ratio"], 0.0)
            self.assertIn("institutional_flows_daily_not_ingested", readiness["blocking_issues"])
            self.assertEqual(
                _read_header(output / "institutional_flows_daily_2021_2023.csv"),
                INSTITUTIONAL_FIELDS,
            )
            self.assertEqual(
                _read_header(output / "chip_flow_overlay_gap_report.csv"),
                GAP_FIELDS,
            )
            self.assertGreater(
                len(_read_rows(output / "chip_flow_overlay_gap_report.csv")),
                len(TARGET_UNIVERSE),
            )

    def test_validator_accepts_overlay_blocked_package(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            output = Path(tmp) / "package"
            build_chip_flow_overlay_package(output_dir=output)

            readiness = validate_chip_flow_overlay_package(output_dir=output)

            self.assertFalse(readiness["ready"])
            self.assertEqual(readiness["source_mode"], "overlay_blocked")

    def test_validator_rejects_bad_source_mode(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            output = Path(tmp) / "package"
            build_chip_flow_overlay_package(output_dir=output)
            readiness_path = output / "chip_flow_overlay_readiness.json"
            readiness = json.loads(readiness_path.read_text(encoding="utf-8"))
            readiness["source_mode"] = "unknown"
            readiness_path.write_text(json.dumps(readiness, ensure_ascii=False), encoding="utf-8")

            with self.assertRaises(ValueError):
                validate_chip_flow_overlay_package(output_dir=output)


def _read_header(path: Path) -> list[str]:
    with path.open("r", encoding="utf-8-sig", newline="") as handle:
        return next(csv.reader(handle))


def _read_rows(path: Path) -> list[dict[str, str]]:
    with path.open("r", encoding="utf-8-sig", newline="") as handle:
        return list(csv.DictReader(handle))
