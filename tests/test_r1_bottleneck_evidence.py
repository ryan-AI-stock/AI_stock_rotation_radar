import unittest
from pathlib import Path
from tempfile import TemporaryDirectory

from r1.bottleneck_evidence import evidence_ready, load_bottleneck_evidence


HEADER = ("ticker,category,stage,thesis,source_url,source_family,source_tier,"
          "published_at,available_at,retrieved_at,evidence_status\n")


class R1BottleneckEvidenceTest(unittest.TestCase):
    def test_two_verified_families_are_ready(self):
        with TemporaryDirectory() as folder:
            path = Path(folder) / "evidence.csv"
            path.write_text(
                HEADER
                + "2303,optical,MASS_PRODUCTION,x,https://a,official,1,2026-09-01,2026-09-01,2026-10-01,VERIFIED\n"
                + "2303,optical,FINANCIAL_PROOF,y,https://b,research,2,2026-09-02,2026-09-02,2026-10-01,VERIFIED\n",
                encoding="utf-8",
            )
            rows, rejected = load_bottleneck_evidence(path, as_of_date="2026-10-01")
            self.assertEqual(rejected, [])
            self.assertTrue(evidence_ready(rows, ticker="2303"))

    def test_same_family_is_not_ready(self):
        with TemporaryDirectory() as folder:
            path = Path(folder) / "evidence.csv"
            path.write_text(
                HEADER
                + "2303,optical,MASS_PRODUCTION,x,https://a,same,1,2026-09-01,2026-09-01,2026-10-01,VERIFIED\n"
                + "2303,optical,FINANCIAL_PROOF,y,https://b,same,2,2026-09-02,2026-09-02,2026-10-01,VERIFIED\n",
                encoding="utf-8",
            )
            rows, _ = load_bottleneck_evidence(path, as_of_date="2026-10-01")
            self.assertFalse(evidence_ready(rows, ticker="2303"))


if __name__ == "__main__":
    unittest.main()
