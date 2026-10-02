import csv
import json
import unittest
from pathlib import Path
from tempfile import TemporaryDirectory

from r1.evidence_readiness import materialize


class R1EvidenceReadinessTest(unittest.TestCase):
    def test_missing_files_block_every_ticker(self):
        with TemporaryDirectory() as folder:
            result = materialize(config_path="config/r1.json", consensus_path=Path(folder) / "none.csv",
                                 catalyst_path=Path(folder) / "none2.csv", as_of_date="2026-10-01")
        self.assertEqual(result["requested_ticker_count"], 14)
        self.assertEqual(result["trade_ready_count"], 0)
        self.assertEqual(result["component_score_ready_count"], 0)
        self.assertFalse(result["action_policy_approved"])
        self.assertFalse(result["active_in_trade_decision"])

    def test_catalyst_requires_two_independent_source_families(self):
        with TemporaryDirectory() as folder:
            root = Path(folder)
            consensus = root / "consensus.csv"
            evidence = root / "evidence.csv"
            catalysts = root / "events.csv"
            consensus.write_text(
                "ticker,fiscal_year,mean_eps,median_eps,high_eps,low_eps,analyst_count,source,published_at,available_at,retrieved_at,quality,status\n"
                "2330,2027,100,100,,,10,x,2026-09-01,2026-09-01,2026-10-01,MEDIUM,READY\n",
                encoding="utf-8",
            )
            evidence.write_text(
                "ticker,fiscal_year,source_url,source_family,source_tier,available_at,note\n"
                "2330,2027,https://a,a,1,2026-09-01,x\n"
                "2330,2027,https://b,b,2,2026-09-01,x\n",
                encoding="utf-8",
            )
            header = ("event_date,ticker,event_type,description,source_url,source_family,source_tier,"
                      "impact_direction,impact_score,confidence,expiry_weeks,affected_bottleneck,"
                      "published_at,available_at,retrieved_at\n")
            catalysts.write_text(
                header
                + "2026-09-01,2330,CAPACITY_EXPANSION,x,https://a/1,same,1,UP,80,0.8,12,compute,2026-09-01,2026-09-01,2026-10-01\n"
                + "2026-09-02,2330,CAPACITY_TIGHTNESS,x,https://a/2,same,2,UP,80,0.8,12,compute,2026-09-02,2026-09-02,2026-10-01\n",
                encoding="utf-8",
            )
            result = materialize(
                config_path="config/r1.json", consensus_path=consensus,
                catalyst_path=catalysts, consensus_evidence_path=evidence,
                catalyst_evidence_path=root / "missing-catalyst-evidence.csv",
                as_of_date="2026-10-01",
            )
            row = next(item for item in result["rows"] if item["ticker"] == "2330")
            self.assertTrue(row["consensus_ready"])
            self.assertFalse(row["catalyst_ready"])


if __name__ == "__main__":
    unittest.main()
