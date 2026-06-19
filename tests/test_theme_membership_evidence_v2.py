from __future__ import annotations

import csv
import json
import tempfile
import unittest
from pathlib import Path

from rotation_radar.formal_sources.theme_membership_evidence_v2 import (
    EVIDENCE_FIELDS,
    QUEUE_FIELDS,
    build_theme_membership_evidence_v2,
    validate_theme_membership_evidence_v2,
)


class ThemeMembershipEvidenceV2Tests(unittest.TestCase):
    def test_builds_resumable_queue_and_draft_sample_without_formal_release(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            gap = root / "gap.csv"
            queue = root / "queue.csv"
            ledger = root / "ledger.csv"
            readiness = root / "readiness.json"
            formal_top3 = root / "top3.json"
            _write_csv(
                gap,
                ["symbol", "ticker", "exchange", "name", "theme", "role", "gap_reason", "required_evidence"],
                [
                    _gap("2368", "金像電", "PCB/載板", "AI 伺服器 PCB"),
                    _gap("2383", "台光電", "PCB/載板", "CCL"),
                    _gap("3081", "聯亞", "CPO/矽光子", "光通訊磊晶"),
                    _gap("2301", "光寶科", "AI伺服器/ODM", "伺服器電源"),
                    _gap("2308", "台達電", "電源/BBU", "伺服器電源"),
                    _gap("3443", "創意", "ASIC/IP", "ASIC 設計服務"),
                ],
            )
            formal_top3.write_text(json.dumps({"ready": False, "source_mode": "formal_blocked"}), encoding="utf-8")

            payload = build_theme_membership_evidence_v2(
                gap_path=gap,
                queue_path=queue,
                ledger_path=ledger,
                readiness_path=readiness,
                batch_size=3,
                sample_size=5,
            )

            self.assertFalse(payload["ready"])
            self.assertEqual(payload["source_mode"], "evidence_queue_phase1_partial")
            self.assertEqual(payload["formal_top3_status"], "formal_blocked")
            self.assertEqual(payload["queued_symbol_count"], 6)
            self.assertEqual(payload["sample_evidence_row_count"], 5)
            self.assertEqual(_read_header(queue), QUEUE_FIELDS)
            self.assertEqual(_read_header(ledger), EVIDENCE_FIELDS)

            queue_rows = _read_rows(queue)
            ledger_rows = _read_rows(ledger)
            self.assertEqual(queue_rows[0]["theme"], "PCB/載板")
            self.assertTrue(all(row["usable_for_formal_replay"] == "false" for row in ledger_rows))
            self.assertTrue(all(row["review_status"] == "draft" for row in ledger_rows))

            validated = validate_theme_membership_evidence_v2(
                queue_path=queue,
                ledger_path=ledger,
                readiness_path=readiness,
                formal_top3_readiness_path=formal_top3,
            )
            self.assertFalse(validated["ready"])

    def test_validator_rejects_usable_evidence_without_accepted_review(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            queue = root / "queue.csv"
            ledger = root / "ledger.csv"
            readiness = root / "readiness.json"
            formal_top3 = root / "top3.json"
            _write_csv(
                queue,
                QUEUE_FIELDS,
                [
                    {
                        field: "x"
                        for field in QUEUE_FIELDS
                    }
                    | {
                        "queue_id": "TMEMQ-V2-B01-2368-PCB",
                        "batch_id": "batch_01",
                        "priority": "1",
                        "collection_status": "queued",
                        "review_status": "draft",
                        "required_evidence": "dated source",
                    }
                ],
            )
            _write_csv(
                ledger,
                EVIDENCE_FIELDS,
                [
                    {
                        field: "x"
                        for field in EVIDENCE_FIELDS
                    }
                    | {
                        "evidence_id": "TMEM-V2-SAMPLE-2368-PCB-001",
                        "source_type": "mops_company_filing",
                        "confidence": "medium",
                        "review_status": "draft",
                        "usable_for_formal_replay": "true",
                    }
                ],
            )
            readiness.write_text(
                json.dumps(
                    {
                        "ready": False,
                        "source_mode": "evidence_queue_phase1_partial",
                        "formal_top3_status": "formal_blocked",
                        "usable_for_formal_replay_count": 0,
                    }
                ),
                encoding="utf-8",
            )
            formal_top3.write_text(json.dumps({"ready": False, "source_mode": "formal_blocked"}), encoding="utf-8")

            with self.assertRaisesRegex(ValueError, "usable evidence must be accepted"):
                validate_theme_membership_evidence_v2(
                    queue_path=queue,
                    ledger_path=ledger,
                    readiness_path=readiness,
                    formal_top3_readiness_path=formal_top3,
                )


def _gap(symbol: str, name: str, theme: str, role: str) -> dict[str, str]:
    return {
        "symbol": symbol,
        "ticker": f"{symbol}.TW",
        "exchange": "TWSE",
        "name": name,
        "theme": theme,
        "role": role,
        "gap_reason": "missing_date_aware_evidence",
        "required_evidence": "dated company filing, dated product/revenue note, dated research note, or archived radar theme definition with source_date <= first snapshot date used",
    }


def _write_csv(path: Path, fieldnames: list[str], rows: list[dict[str, str]]) -> None:
    with path.open("w", encoding="utf-8-sig", newline="") as handle:
        writer = csv.DictWriter(handle, fieldnames=fieldnames)
        writer.writeheader()
        writer.writerows(rows)


def _read_header(path: Path) -> list[str]:
    with path.open("r", encoding="utf-8-sig", newline="") as handle:
        return next(csv.reader(handle))


def _read_rows(path: Path) -> list[dict[str, str]]:
    with path.open("r", encoding="utf-8-sig", newline="") as handle:
        return list(csv.DictReader(handle))
