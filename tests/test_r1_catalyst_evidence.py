import unittest
from pathlib import Path
from tempfile import TemporaryDirectory

from r1.catalyst_evidence import evidence_ready, load_catalyst_evidence


HEADER = ("event_date,ticker,event_type,description,source_url,source_family,source_tier,"
          "impact_direction,affected_bottleneck,published_at,available_at,retrieved_at,evidence_status\n")


class R1CatalystEvidenceTest(unittest.TestCase):
    def test_verified_independent_sources_are_ready_without_scores(self):
        with TemporaryDirectory() as folder:
            path = Path(folder) / "evidence.csv"
            path.write_text(
                HEADER
                + "2026-09-01,2303,MASS_PRODUCTION,x,https://a,official,1,UP,optical,2026-09-01,2026-09-01,2026-10-01,VERIFIED\n"
                + "2026-09-02,2303,CAPACITY_TIGHTNESS,y,https://b,research,2,UP,wafer,2026-09-02,2026-09-02,2026-10-01,VERIFIED\n",
                encoding="utf-8",
            )
            rows, rejected = load_catalyst_evidence(path, as_of_date="2026-10-01")
            self.assertEqual(rejected, [])
            self.assertTrue(evidence_ready(rows, ticker="2303"))

    def test_future_or_unverified_evidence_is_rejected(self):
        with TemporaryDirectory() as folder:
            path = Path(folder) / "evidence.csv"
            path.write_text(
                HEADER
                + "2026-10-02,2303,MASS_PRODUCTION,x,https://a,official,1,UP,optical,2026-10-02,2026-10-02,2026-10-02,VERIFIED\n"
                + "2026-09-01,2303,MASS_PRODUCTION,x,https://b,official,1,UP,optical,2026-09-01,2026-09-01,2026-10-01,NEEDS_REVIEW\n",
                encoding="utf-8",
            )
            rows, rejected = load_catalyst_evidence(path, as_of_date="2026-10-01")
            self.assertEqual(rows, [])
            self.assertEqual({row["error"] for row in rejected}, {"future_data", "evidence_not_verified"})


if __name__ == "__main__":
    unittest.main()
