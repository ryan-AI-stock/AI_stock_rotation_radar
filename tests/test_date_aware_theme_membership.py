from __future__ import annotations

import csv
import json
import tempfile
import unittest
from pathlib import Path

from rotation_radar.formal_sources.date_aware_theme_membership import (
    MEMBERSHIP_FIELDS,
    ensure_membership_file,
    validate_date_aware_theme_membership,
)


class DateAwareThemeMembershipTests(unittest.TestCase):
    def test_empty_membership_blocks_current_static_map(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            formal = root / "formal.csv"
            theme_map = root / "theme_map.csv"
            membership = root / "date_aware.csv"
            gap = root / "gap.csv"
            readiness = root / "ready.json"
            _write_csv(
                formal,
                ["symbol", "name", "theme"],
                [{"symbol": "2408", "name": "南亞科", "theme": "記憶體"}],
            )
            _write_csv(
                theme_map,
                ["theme", "symbol", "name", "role", "conviction", "primary"],
                [{"theme": "記憶體", "symbol": "2408", "name": "南亞科", "role": "DRAM", "conviction": "high", "primary": "yes"}],
            )
            ensure_membership_file(membership)

            payload = validate_date_aware_theme_membership(
                membership_file=membership,
                formal_universe_path=formal,
                theme_map_path=theme_map,
                gap_report_path=gap,
                output_path=readiness,
            )

            self.assertFalse(payload["ready"])
            self.assertEqual(payload["source_mode"], "current_static_map_blocked")
            self.assertEqual(payload["coverage_ratio"], 0.0)
            self.assertEqual(payload["static_only_count"], 1)
            with gap.open(encoding="utf-8-sig", newline="") as handle:
                rows = list(csv.DictReader(handle))
            self.assertEqual(rows[0]["missing_reason"], "current_static_map_only")
            self.assertEqual(json.loads(readiness.read_text(encoding="utf-8"))["date_aware_row_count"], 0)

    def test_static_source_rows_are_excluded(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            formal = root / "formal.csv"
            membership = root / "date_aware.csv"
            gap = root / "gap.csv"
            readiness = root / "ready.json"
            _write_csv(formal, ["symbol", "name", "theme"], [{"symbol": "2408", "name": "南亞科", "theme": "記憶體"}])
            _write_csv(
                membership,
                MEMBERSHIP_FIELDS,
                [
                    {
                        "symbol": "2408",
                        "name": "南亞科",
                        "theme": "記憶體",
                        "effective_start": "2021-12-01",
                        "effective_end": "",
                        "source_date": "2021-12-01",
                        "source_type": "current_static_map",
                        "source_url": "data/theme_map.csv",
                        "confidence": "high",
                        "notes": "not acceptable",
                    }
                ],
            )

            payload = validate_date_aware_theme_membership(
                membership_file=membership,
                formal_universe_path=formal,
                gap_report_path=gap,
                output_path=readiness,
            )

            self.assertEqual(payload["source_mode"], "current_static_map_blocked")
            self.assertEqual(payload["invalid_row_count"], 1)
            self.assertIn("invalid_membership_rows_excluded", payload["blocking_issues"])

    def test_valid_evidence_rows_create_partial_mode(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            formal = root / "formal.csv"
            membership = root / "date_aware.csv"
            gap = root / "gap.csv"
            readiness = root / "ready.json"
            _write_csv(
                formal,
                ["symbol", "name", "theme"],
                [
                    {"symbol": "2408", "name": "南亞科", "theme": "記憶體"},
                    {"symbol": "3037", "name": "欣興", "theme": "PCB/載板"},
                ],
            )
            _write_csv(
                membership,
                MEMBERSHIP_FIELDS,
                [
                    {
                        "symbol": "2408",
                        "name": "南亞科",
                        "theme": "記憶體",
                        "effective_start": "2021-12-01",
                        "effective_end": "",
                        "source_date": "2021-12-01",
                        "source_type": "curated_research_note",
                        "source_url": "https://example.test/evidence",
                        "confidence": "medium",
                        "notes": "dated evidence",
                    }
                ],
            )

            payload = validate_date_aware_theme_membership(
                membership_file=membership,
                formal_universe_path=formal,
                gap_report_path=gap,
                output_path=readiness,
            )

            self.assertTrue(payload["ready"])
            self.assertEqual(payload["source_mode"], "date_aware_partial")
            self.assertEqual(payload["coverage_ratio"], 0.5)
            self.assertEqual(payload["medium_confidence_count"], 1)
            self.assertEqual(payload["static_only_count"], 1)

    def test_theme_filter_limits_formal_target_scope(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            formal = root / "formal.csv"
            membership = root / "date_aware.csv"
            gap = root / "gap.csv"
            readiness = root / "ready.json"
            _write_csv(
                formal,
                ["symbol", "name", "theme"],
                [
                    {"symbol": "2408", "name": "南亞科", "theme": "記憶體"},
                    {"symbol": "3037", "name": "欣興", "theme": "PCB/載板"},
                ],
            )
            _write_csv(
                membership,
                MEMBERSHIP_FIELDS,
                [
                    {
                        "symbol": "2408",
                        "name": "南亞科",
                        "theme": "記憶體",
                        "effective_start": "2021-10-08",
                        "effective_end": "",
                        "source_date": "2021-10-08",
                        "source_type": "dated_news_article",
                        "source_url": "https://example.test/memory-evidence",
                        "confidence": "medium",
                        "notes": "dated memory evidence",
                    },
                    {
                        "symbol": "3037",
                        "name": "欣興",
                        "theme": "PCB/載板",
                        "effective_start": "2021-10-08",
                        "effective_end": "",
                        "source_date": "2021-10-08",
                        "source_type": "dated_news_article",
                        "source_url": "https://example.test/pcb-evidence",
                        "confidence": "medium",
                        "notes": "non-target theme evidence",
                    },
                ],
            )

            payload = validate_date_aware_theme_membership(
                membership_file=membership,
                formal_universe_path=formal,
                gap_report_path=gap,
                output_path=readiness,
                theme="記憶體",
            )

            self.assertTrue(payload["ready"])
            self.assertEqual(payload["theme"], "記憶體")
            self.assertEqual(payload["source_mode"], "date_aware")
            self.assertEqual(payload["target_symbol_count"], 1)
            self.assertEqual(payload["date_aware_row_count"], 1)
            self.assertEqual(payload["coverage_ratio"], 1.0)
            with gap.open(encoding="utf-8-sig", newline="") as handle:
                rows = list(csv.DictReader(handle))
            self.assertEqual(rows, [])

    def test_target_symbols_filter_limits_theme_scope(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            formal = root / "formal.csv"
            membership = root / "date_aware.csv"
            gap = root / "gap.csv"
            readiness = root / "ready.json"
            _write_csv(
                formal,
                ["symbol", "name", "theme"],
                [
                    {"symbol": "2408", "name": "南亞科", "theme": "記憶體"},
                    {"symbol": "6531", "name": "愛普*", "theme": "記憶體"},
                ],
            )
            _write_csv(
                membership,
                MEMBERSHIP_FIELDS,
                [
                    {
                        "symbol": "2408",
                        "name": "南亞科",
                        "theme": "記憶體",
                        "effective_start": "2021-10-08",
                        "effective_end": "",
                        "source_date": "2021-10-08",
                        "source_type": "dated_news_article",
                        "source_url": "https://example.test/memory-evidence",
                        "confidence": "medium",
                        "notes": "dated memory evidence",
                    }
                ],
            )

            payload = validate_date_aware_theme_membership(
                membership_file=membership,
                formal_universe_path=formal,
                gap_report_path=gap,
                output_path=readiness,
                theme="記憶體",
                target_symbols={"2408"},
            )

            self.assertEqual(payload["target_symbol_count"], 1)
            self.assertEqual(payload["source_mode"], "date_aware")
            self.assertEqual(payload["static_only_count"], 0)


def _write_csv(path: Path, fieldnames: list[str], rows: list[dict[str, str]]) -> None:
    with path.open("w", encoding="utf-8-sig", newline="") as handle:
        writer = csv.DictWriter(handle, fieldnames=fieldnames)
        writer.writeheader()
        writer.writerows(rows)
