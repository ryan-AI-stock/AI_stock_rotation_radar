from __future__ import annotations

import csv
import tempfile
import unittest
from pathlib import Path

from rotation_radar.data_quality import load_quote_snapshot, normalize_quote_date, quote_date_mismatch_message


class DataQualityTests(unittest.TestCase):
    def test_normalize_quote_date_accepts_yyyymmdd_and_iso_dates(self) -> None:
        self.assertEqual(normalize_quote_date("20260604"), "2026-06-04")
        self.assertEqual(normalize_quote_date("2026-06-04"), "2026-06-04")
        self.assertEqual(normalize_quote_date(""), "")

    def test_load_quote_snapshot_returns_first_available_quote_metadata(self) -> None:
        with tempfile.TemporaryDirectory() as temp_dir:
            path = Path(temp_dir) / "quotes.csv"
            with path.open("w", encoding="utf-8-sig", newline="") as handle:
                writer = csv.DictWriter(handle, fieldnames=["symbol", "quote_date", "quote_time"])
                writer.writeheader()
                writer.writerow({"symbol": "2330", "quote_date": "20260604", "quote_time": "14:30:00"})
                writer.writerow({"symbol": "2454", "quote_date": "20260605", "quote_time": "14:30:00"})

            snapshot = load_quote_snapshot(path)

        self.assertEqual(snapshot.quote_date, "20260604")
        self.assertEqual(snapshot.quote_time, "14:30:00")
        self.assertEqual(snapshot.normalized_date, "2026-06-04")

    def test_load_quote_snapshot_handles_missing_or_empty_files(self) -> None:
        with tempfile.TemporaryDirectory() as temp_dir:
            missing_path = Path(temp_dir) / "missing.csv"
            empty_path = Path(temp_dir) / "empty.csv"
            empty_path.write_text("symbol,quote_date,quote_time\n", encoding="utf-8")

            self.assertEqual(load_quote_snapshot(missing_path).normalized_date, "")
            self.assertEqual(load_quote_snapshot(empty_path).normalized_date, "")

    def test_mismatch_message_keeps_github_retry_wording(self) -> None:
        snapshot = load_quote_snapshot(Path("not-found.csv"))

        self.assertEqual(
            quote_date_mismatch_message(snapshot, "2026-06-04"),
            "Latest market quote date missing does not match target report date 2026-06-04; retry later.",
        )


if __name__ == "__main__":
    unittest.main()
