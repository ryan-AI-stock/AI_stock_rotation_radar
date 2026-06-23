from __future__ import annotations

import csv
import tempfile
import unittest
from pathlib import Path

from rotation_radar.formal_sources.pool3_radar_readiness import build_pool3_radar_readiness
from rotation_radar.formal_sources.theme_membership_evidence_v2 import EVIDENCE_FIELDS


class Pool3RadarReadinessTests(unittest.TestCase):
    def test_builds_partial_readiness_with_accepted_evidence_and_price_gaps(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            theme_map = root / "theme_map.csv"
            formal = root / "formal_universe.csv"
            memory = root / "memory.csv"
            ledger = root / "ledger.csv"
            readiness = root / "v2.json"
            cache = root / "cache"
            output = root / "out"
            cache.mkdir()
            _write_csv(theme_map, ["theme", "symbol", "name", "role", "conviction", "primary"], [
                {"theme": "記憶體", "symbol": "2337", "name": "旺宏", "role": "NOR Flash", "conviction": "high", "primary": "yes"},
                {"theme": "PCB/載板", "symbol": "2313", "name": "華通", "role": "PCB", "conviction": "high", "primary": "yes"},
            ])
            _write_csv(formal, ["symbol", "name", "theme", "role", "formal_ohlcv_available", "formal_status"], [
                {"symbol": "2337", "name": "旺宏", "theme": "記憶體", "role": "NOR Flash", "formal_ohlcv_available": "true", "formal_status": "blocked"},
                {"symbol": "2313", "name": "華通", "theme": "PCB/載板", "role": "PCB", "formal_ohlcv_available": "true", "formal_status": "blocked"},
            ])
            _write_csv(memory, ["symbol", "name", "theme", "effective_start", "effective_end", "source_date", "source_type", "source_url", "confidence", "notes"], [
                {"symbol": "2337", "name": "旺宏", "theme": "記憶體", "effective_start": "2022-05-04", "effective_end": "", "source_date": "2022-05-04", "source_type": "company_annual_report", "source_url": "https://example.com/report.pdf", "confidence": "high", "notes": "dated source"},
            ])
            _write_csv(ledger, EVIDENCE_FIELDS, [])
            readiness.write_text("{}", encoding="utf-8")
            _write_price(cache / "2337_TW.csv", "2020-01-02", "2026-05-26")

            payload = build_pool3_radar_readiness(
                output_dir=output,
                theme_map_path=theme_map,
                formal_universe_path=formal,
                memory_v1_path=memory,
                v2_ledger_path=ledger,
                v2_readiness_path=readiness,
                price_cache_dir=cache,
                update_v2_live_files=True,
            )

            self.assertFalse(payload["formal_top3_ready"])
            self.assertFalse(payload["theme_membership_v2_ready"])
            self.assertEqual(payload["accepted_evidence_row_count"], 1)
            self.assertEqual(payload["blocked_membership_symbol_count"], 1)
            self.assertGreater(len(_read_rows(output / "skipped_members_report.csv")), 0)
            self.assertIn("evidence_queue_phase2_partial", readiness.read_text(encoding="utf-8"))
            self.assertEqual(len(_read_rows(ledger)), 1)


def _write_csv(path: Path, fieldnames: list[str], rows: list[dict[str, str]]) -> None:
    with path.open("w", encoding="utf-8-sig", newline="") as handle:
        writer = csv.DictWriter(handle, fieldnames=fieldnames)
        writer.writeheader()
        writer.writerows(rows)


def _write_price(path: Path, start: str, end: str) -> None:
    _write_csv(path, ["date", "open", "high", "low", "close", "volume"], [
        {"date": start, "open": "10", "high": "10", "low": "10", "close": "10", "volume": "1000"},
        {"date": end, "open": "20", "high": "20", "low": "20", "close": "20", "volume": "1000"},
    ])


def _read_rows(path: Path) -> list[dict[str, str]]:
    with path.open("r", encoding="utf-8-sig", newline="") as handle:
        return list(csv.DictReader(handle))
