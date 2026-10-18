import csv
import json
import tempfile
import unittest
from pathlib import Path

from r1.theme_leader_priority_seed import REVIEWED_SCORES, _baseline_scores, materialize


class R1ThemeLeaderPrioritySeedTest(unittest.TestCase):
    def test_baseline_stage_mapping_is_conservative(self):
        self.assertEqual(_baseline_scores([{"stage": "THESIS"}]), {
            "bottleneck_directness": 25,
            "industry_technology_position": 50,
            "ai_revenue_realization": 25,
        })
        self.assertEqual(_baseline_scores([{"stage": "THESIS"}, {"stage": "FINANCIAL_PROOF"}])[
            "ai_revenue_realization"
        ], 75)

    def test_only_verified_independent_evidence_is_promoted(self):
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            evidence = root / "evidence.csv"
            fields = ["ticker", "claim", "source_url", "source_family", "source_date",
                      "available_at", "status"]
            with evidence.open("w", encoding="utf-8", newline="") as handle:
                writer = csv.DictWriter(handle, fieldnames=fields)
                writer.writeheader()
                for ticker in REVIEWED_SCORES:
                    for family in ("company_ir", "industry_research"):
                        writer.writerow({
                            "ticker": ticker, "claim": "verified", "source_url": "https://example.test",
                            "source_family": family, "source_date": "2026-10-01",
                            "available_at": "2026-10-01", "status": "VERIFIED",
                        })
            source = root / "source.json"
            source.write_text(json.dumps({"rows": []}), encoding="utf-8")
            result = materialize(evidence_path=evidence, source_path=source)
            payload = json.loads(source.read_text(encoding="utf-8"))
        self.assertEqual(result["updated_tickers"], sorted(REVIEWED_SCORES))
        self.assertEqual(len(payload["rows"]), len(REVIEWED_SCORES))
        self.assertTrue(all(len(row["evidence"]["bottleneck_directness"]["sources"]) == 2
                            for row in payload["rows"]))


if __name__ == "__main__":
    unittest.main()
