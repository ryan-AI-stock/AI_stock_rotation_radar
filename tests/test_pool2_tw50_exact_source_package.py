import csv
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

from rotation_radar.formal_sources.build_pool2_tw50_exact_pit_source_package import build_package


class Pool2Tw50ExactSourcePackageTest(unittest.TestCase):
    def test_downloaded_notices_do_not_mark_formal_ready_without_baseline(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            manifest = root / "input.csv"
            with manifest.open("w", encoding="utf-8", newline="") as handle:
                writer = csv.DictWriter(
                    handle,
                    fieldnames=["source_id", "source_url", "source_title", "source_date", "filename"],
                )
                writer.writeheader()
                writer.writerow(
                    {
                        "source_id": "tip_569_tw",
                        "source_url": "https://example.test/tip_569_tw.pdf",
                        "source_title": "臺灣證券交易所與富時國際有限公司合編之臺灣指數系列及臺灣高股息指數成分股審核",
                        "source_date": "2022/03/05",
                        "filename": "tip_569_tw.pdf",
                    }
                )

            def fake_download(_url, local_path):
                local_path.write_bytes(b"%PDF-1.4\n")
                return {
                    "download_status": "downloaded",
                    "http_status": "200",
                    "content_type": "application/pdf",
                    "bytes": "9",
                    "parse_status": "ready_for_core_parser",
                }

            with patch(
                "rotation_radar.formal_sources.build_pool2_tw50_exact_pit_source_package._download_pdf",
                side_effect=fake_download,
            ):
                readiness = build_package(
                    input_manifest=manifest,
                    output_dir=root / "out",
                    sleep_seconds=0,
                )

            self.assertFalse(readiness["formal_ready"])
            self.assertFalse(readiness["accepted_for_core_validator"])
            self.assertEqual(readiness["downloaded_notice_count"], 1)
            self.assertEqual(readiness["baseline_snapshot_status"], "blocked_not_found")
            self.assertIn("official_baseline_snapshot", (root / "out" / "blocked_sources.csv").read_text())


if __name__ == "__main__":
    unittest.main()
