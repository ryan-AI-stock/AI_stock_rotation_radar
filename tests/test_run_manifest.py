from __future__ import annotations

import json
import tempfile
import unittest
from datetime import datetime
from pathlib import Path
from zoneinfo import ZoneInfo

from rotation_radar.run_manifest import build_daily_run_manifest, write_run_manifest


class RunManifestTests(unittest.TestCase):
    def test_build_daily_run_manifest_keeps_data_quality_status(self) -> None:
        manifest = build_daily_run_manifest(
            report_date="2026-06-04",
            quote_date="2026-06-04",
            quote_time="14:30:00",
            html_output="reports/latest.html",
            market_quotes_path="data/market_quotes.generated.csv",
            sector_metrics_path="data/sector_metrics.refreshed.csv",
            stock_metrics_path="data/stock_metrics.refreshed.csv",
            formal_candidates_path="data/formal_radar_candidates.latest.csv",
            price_history_path="data/price_history.csv",
            depth_refresh_status="skipped",
            price_refresh_status="attempted",
            candidate_symbol_count=3,
            warnings=["missing price snapshot files: processed_data/20260604"],
            generated_at=datetime(2026, 6, 5, 17, 0, tzinfo=ZoneInfo("Asia/Taipei")),
        )

        self.assertEqual(manifest["generated_at"], "2026-06-05T17:00:00+08:00")
        self.assertEqual(manifest["report_date"], "2026-06-04")
        self.assertEqual(manifest["quote_date"], "2026-06-04")
        self.assertEqual(manifest["outputs"]["html"], "reports/latest.html")
        self.assertEqual(manifest["outputs"]["formal_candidates"], "data/formal_radar_candidates.latest.csv")
        self.assertEqual(manifest["refresh_status"]["depth"], "skipped")
        self.assertEqual(manifest["refresh_status"]["candidate_symbol_count"], 3)
        self.assertEqual(manifest["warnings"], ["missing price snapshot files: processed_data/20260604"])

    def test_write_run_manifest_creates_parent_directory_and_json(self) -> None:
        with tempfile.TemporaryDirectory() as temp_dir:
            output = Path(temp_dir) / "reports" / "latest_manifest.json"

            written = write_run_manifest(output, {"quote_date": "2026-06-04", "warnings": []})

            self.assertEqual(written, output)
            self.assertEqual(json.loads(output.read_text(encoding="utf-8")), {"quote_date": "2026-06-04", "warnings": []})


if __name__ == "__main__":
    unittest.main()
