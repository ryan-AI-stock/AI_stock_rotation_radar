from __future__ import annotations

import csv
import json
import tempfile
import unittest
from pathlib import Path

from rotation_radar.formal_sources.tw50_holdings_manual_intake import (
    INTAKE_STATUS_FIELDS,
    build_tw50_holdings_manual_intake,
)


class Tw50HoldingsManualIntakeTests(unittest.TestCase):
    def test_reports_missing_priority_one_files_without_formal_release(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            checklist = root / "checklist.csv"
            pdf_dir = root / "pdfs"
            output_dir = root / "out"
            _write_checklist(
                checklist,
                [
                    _row("2022-01", "monthly", "2022-01-31", "1", "yuanta_0050_monthly_202201.pdf"),
                    _row("2022-Q1", "quarterly", "2022-03-31", "1", "yuanta_domestic_holdings_2022Q1.pdf"),
                ],
            )

            readiness = build_tw50_holdings_manual_intake(
                checklist_path=checklist,
                pdf_dir=pdf_dir,
                output_dir=output_dir,
            )

            self.assertEqual(readiness["status"], "blocked_waiting_user_files")
            self.assertFalse(readiness["ready"])
            self.assertFalse(readiness["formal_ready"])
            self.assertTrue(readiness["is_proxy"])
            self.assertFalse(readiness["exact_tw50_official_constituents"])
            self.assertEqual(readiness["pdfs_found"], 0)
            self.assertEqual(readiness["historical_snapshot_rows"], 0)
            self.assertEqual(
                readiness["missing_priority_one_files"],
                ["yuanta_0050_monthly_202201.pdf", "yuanta_domestic_holdings_2022Q1.pdf"],
            )
            self.assertEqual(_read_header(output_dir / "manual_pdf_intake_status.csv"), INTAKE_STATUS_FIELDS)

    def test_detects_valid_pdf_header_but_still_keeps_formal_ready_false(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            checklist = root / "checklist.csv"
            pdf_dir = root / "pdfs"
            output_dir = root / "out"
            pdf_dir.mkdir()
            _write_checklist(
                checklist,
                [_row("2022-01", "monthly", "2022-01-31", "1", "yuanta_0050_monthly_202201.pdf")],
            )
            (pdf_dir / "yuanta_0050_monthly_202201.pdf").write_bytes(b"%PDF-1.7\n")

            readiness = build_tw50_holdings_manual_intake(
                checklist_path=checklist,
                pdf_dir=pdf_dir,
                output_dir=output_dir,
            )

            self.assertEqual(readiness["status"], "intake_ready_for_manual_review")
            self.assertFalse(readiness["ready"])
            self.assertFalse(readiness["formal_ready"])
            self.assertEqual(readiness["pdfs_found"], 1)
            self.assertEqual(readiness["valid_pdf_header_count"], 1)
            self.assertEqual(readiness["accepted_rows"], 0)
            self.assertEqual(readiness["historical_snapshot_rows"], 0)
            rows = _read_rows(output_dir / "manual_pdf_intake_status.csv")
            self.assertEqual(rows[0]["review_status"], "ready_for_parser_review")
            payload = json.loads((output_dir / "manual_pdf_intake_readiness.json").read_text(encoding="utf-8"))
            self.assertEqual(payload["source_mode"], "yuanta_0050_holdings_proxy")


def _row(period_id: str, period_type: str, snapshot_date: str, priority: str, filename: str) -> dict[str, str]:
    return {
        "period_id": period_id,
        "period_type": period_type,
        "target_snapshot_date": snapshot_date,
        "priority": priority,
        "expected_filename": filename,
    }


def _write_checklist(path: Path, rows: list[dict[str, str]]) -> None:
    with path.open("w", encoding="utf-8-sig", newline="") as handle:
        writer = csv.DictWriter(
            handle,
            fieldnames=["period_id", "period_type", "target_snapshot_date", "priority", "expected_filename"],
        )
        writer.writeheader()
        writer.writerows(rows)


def _read_header(path: Path) -> list[str]:
    with path.open("r", encoding="utf-8-sig", newline="") as handle:
        return next(csv.reader(handle))


def _read_rows(path: Path) -> list[dict[str, str]]:
    with path.open("r", encoding="utf-8-sig", newline="") as handle:
        return list(csv.DictReader(handle))
