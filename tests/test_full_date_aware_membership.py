from __future__ import annotations

import csv
import json
import tempfile
import unittest
from pathlib import Path

from rotation_radar.formal_sources.date_aware_theme_membership_full import (
    FULL_GAP_FIELDS,
    FULL_MEMBERSHIP_FIELDS,
    build_full_date_aware_membership,
    validate_full_date_aware_membership,
)


class FullDateAwareMembershipTests(unittest.TestCase):
    def test_builds_blocked_full_package_with_usable_evidence_and_gaps(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            formal = root / "formal.csv"
            market = root / "market.csv"
            evidence = root / "memory.csv"
            output = root / "full.csv"
            gap = root / "gap.csv"
            readiness = root / "readiness.json"
            _write_csv(
                formal,
                ["symbol", "name", "theme", "role"],
                [
                    {"symbol": "2408", "name": "南亞科", "theme": "記憶體", "role": "DRAM"},
                    {"symbol": "3037", "name": "欣興", "theme": "PCB/載板", "role": "ABF"},
                ],
            )
            _write_csv(
                market,
                ["market", "symbol", "name"],
                [
                    {"market": "TWSE", "symbol": "2408", "name": "南亞科"},
                    {"market": "TWSE", "symbol": "3037", "name": "欣興"},
                ],
            )
            _write_csv(
                evidence,
                ["symbol", "name", "theme", "effective_start", "effective_end", "source_date", "source_type", "source_url", "confidence", "notes"],
                [
                    {
                        "symbol": "2408",
                        "name": "南亞科",
                        "theme": "記憶體",
                        "effective_start": "2021-10-08",
                        "effective_end": "",
                        "source_date": "2021-10-08",
                        "source_type": "dated_news_article",
                        "source_url": "https://example.test/2408",
                        "confidence": "medium",
                        "notes": "dated evidence",
                    }
                ],
            )

            payload = build_full_date_aware_membership(
                output_path=output,
                gap_path=gap,
                readiness_path=readiness,
                formal_universe_path=formal,
                market_universe_path=market,
                source_files=[evidence],
                start_date="2022-01-03",
                end_date="2022-01-04",
            )

            self.assertFalse(payload["ready"])
            self.assertEqual(payload["source_mode"], "date_aware_full_blocked")
            self.assertEqual(payload["date_aware_row_count"], 1)
            self.assertEqual(payload["gap_symbol_count"], 1)
            self.assertEqual(_read_header(output), FULL_MEMBERSHIP_FIELDS)
            self.assertEqual(_read_header(gap), FULL_GAP_FIELDS)
            with output.open(encoding="utf-8-sig", newline="") as handle:
                rows = list(csv.DictReader(handle))
            self.assertEqual(rows[0]["ticker"], "2408.TW")
            self.assertEqual(rows[0]["usable_for_formal_top3"], "yes")

    def test_validator_rejects_static_source_rows(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            membership = root / "full.csv"
            gap = root / "gap.csv"
            readiness = root / "readiness.json"
            row = {field: "x" for field in FULL_MEMBERSHIP_FIELDS}
            row.update(
                {
                    "symbol": "2408",
                    "effective_start": "2021-01-01",
                    "source_date": "2021-01-01",
                    "source_type": "current_static_map",
                    "confidence": "high",
                    "usable_for_formal_top3": "yes",
                    "effective_end": "",
                }
            )
            _write_csv(membership, FULL_MEMBERSHIP_FIELDS, [row])
            _write_csv(gap, FULL_GAP_FIELDS, [])
            readiness.write_text(
                json.dumps(
                    {
                        "ready": False,
                        "source_mode": "date_aware_full_blocked",
                        "start_date": "2022-01-03",
                        "end_date": "2023-12-29",
                        "formal_universe_symbol_count": 1,
                        "date_aware_row_count": 1,
                        "gap_symbol_count": 0,
                        "coverage_ratio": 1.0,
                        "future_data_violation_count": 0,
                        "blocking_issues": ["test"],
                        "warnings": [],
                    }
                ),
                encoding="utf-8",
            )

            with self.assertRaisesRegex(ValueError, "static source"):
                validate_full_date_aware_membership(
                    membership_path=membership,
                    gap_path=gap,
                    readiness_path=readiness,
                )


def _write_csv(path: Path, fieldnames: list[str], rows: list[dict[str, str]]) -> None:
    with path.open("w", encoding="utf-8-sig", newline="") as handle:
        writer = csv.DictWriter(handle, fieldnames=fieldnames)
        writer.writeheader()
        writer.writerows(rows)


def _read_header(path: Path) -> list[str]:
    with path.open("r", encoding="utf-8-sig", newline="") as handle:
        return next(csv.reader(handle))
