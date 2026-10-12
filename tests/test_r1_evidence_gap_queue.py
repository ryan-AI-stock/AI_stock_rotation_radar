import csv
import unittest
from pathlib import Path
from tempfile import TemporaryDirectory

from r1.evidence_gap_queue import materialize


class R1EvidenceGapQueueTest(unittest.TestCase):
    def test_queue_reports_exact_missing_evidence_without_promoting_partial_rows(self):
        with TemporaryDirectory() as folder:
            root = Path(folder)
            catalyst = root / "catalyst.csv"
            bottleneck = root / "bottleneck.csv"
            with catalyst.open("w", encoding="utf-8", newline="") as handle:
                writer = csv.writer(handle)
                writer.writerow(("event_date", "ticker", "event_type", "description", "source_url",
                                 "source_family", "source_tier", "impact_direction", "affected_bottleneck",
                                 "published_at", "available_at", "retrieved_at", "evidence_status"))
                writer.writerow(("2026-09-01", "2454", "GUIDANCE_UP", "x", "https://a", "company", 1,
                                 "UP", "compute", "2026-09-01", "2026-09-01", "2026-10-01", "VERIFIED"))
            with bottleneck.open("w", encoding="utf-8", newline="") as handle:
                writer = csv.writer(handle)
                writer.writerow(("ticker", "category", "stage", "thesis", "source_url", "source_family",
                                 "source_tier", "published_at", "available_at", "retrieved_at", "evidence_status"))
                for family, tier in (("company", 1), ("industry", 2)):
                    writer.writerow(("2454", "compute", "MASS_PRODUCTION", "x", f"https://{family}", family,
                                     tier, "2026-09-01", "2026-09-01", "2026-10-01", "VERIFIED"))
            result = materialize(
                as_of_date="2026-10-01", config_path="config/r1.json",
                catalyst_path=catalyst, bottleneck_path=bottleneck,
                output_path=root / "queue.json",
            )
            row = next(item for item in result["rows"] if item["ticker"] == "2454")
            self.assertEqual(row["priority"], 0)
            self.assertEqual(row["missing"], ["CATALYST_EVIDENCE"])
            self.assertFalse(row["catalyst"]["ready"])
            self.assertTrue(row["bottleneck"]["ready"])
            self.assertEqual(result["future_data_violation_count"], 0)


if __name__ == "__main__":
    unittest.main()
