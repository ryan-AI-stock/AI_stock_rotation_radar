from __future__ import annotations

import csv
import json
import tempfile
import unittest
from pathlib import Path

from rotation_radar.formal_sources.pool2_tw50_readiness import (
    EXACT_TW50_FIELDS,
    POOL2_PROXY_FIELDS,
    build_pool2_tw50_readiness,
)


class Pool2Tw50ReadinessTests(unittest.TestCase):
    def test_builds_blocked_handoff_without_proxy_or_exact_rows(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            core_dir = root / "core"
            core_dir.mkdir()
            _write_rows(
                core_dir / "tw50_constituent_coverage_summary.csv",
                [
                    {
                        "period": "2022",
                        "start": "2022-01-03",
                        "end": "2022-12-30",
                        "checked_dates": "260",
                        "ready_dates": "0",
                        "gap_dates": "260",
                        "coverage_ratio": "0.0",
                        "minimum_active_count": "45",
                        "min_active_count": "0",
                        "max_active_count": "0",
                        "first_ready_date": "",
                        "last_ready_date": "",
                    }
                ],
            )
            (core_dir / "metadata.json").write_text(
                json.dumps(
                    {
                        "source_row_count": 50,
                        "source_effective_min": "2025-06-23",
                        "source_effective_max": "2025-06-23",
                    }
                ),
                encoding="utf-8",
            )
            intake = root / "intake.json"
            intake.write_text(
                json.dumps(
                    {
                        "status": "blocked_waiting_user_files",
                        "pdf_dir": "manual_pdfs",
                        "pdfs_found": 0,
                        "valid_pdf_header_count": 0,
                        "missing_priority_one_files": ["yuanta_0050_monthly_202201.pdf"],
                    }
                ),
                encoding="utf-8",
            )
            checklist = root / "checklist.csv"
            _write_rows(
                checklist,
                [
                    {
                        "period_id": "2022-01",
                        "period_type": "monthly",
                        "target_snapshot_date": "2022-01-31",
                        "priority": "1",
                        "preferred_source": "yuanta_0050_monthly_report",
                        "expected_filename": "yuanta_0050_monthly_202201.pdf",
                        "source_status": "source_pending",
                    }
                ],
            )

            readiness = build_pool2_tw50_readiness(
                output_dir=root / "out",
                core_coverage_dir=core_dir,
                intake_readiness_path=intake,
                phase3_checklist_path=checklist,
                phase4_search_readiness_path=root / "missing_phase4.json",
            )

            self.assertEqual(readiness["status"], "blocked_waiting_user_files")
            self.assertFalse(readiness["ready"])
            self.assertFalse(readiness["exact_tw50_official_constituents_ready"])
            self.assertFalse(readiness["yuanta_0050_holdings_proxy_ready"])
            self.assertEqual(readiness["future_data_violation_count"], 0)
            self.assertEqual(readiness["missing_manual_source_count"], 1)
            self.assertEqual(_header(root / "out" / "0050_holdings_proxy_rows.csv"), POOL2_PROXY_FIELDS)
            self.assertEqual(_header(root / "out" / "tw50_constituents_pit_candidate.csv"), EXACT_TW50_FIELDS)
            self.assertIn("Core must not treat Yuanta holdings proxy rows", (root / "out" / "manifest.md").read_text())


def _write_rows(path: Path, rows: list[dict[str, str]]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("w", encoding="utf-8-sig", newline="") as handle:
        writer = csv.DictWriter(handle, fieldnames=list(rows[0]))
        writer.writeheader()
        writer.writerows(rows)


def _header(path: Path) -> list[str]:
    with path.open("r", encoding="utf-8-sig", newline="") as handle:
        return next(csv.reader(handle))
