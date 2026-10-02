import json
import tempfile
import unittest
from pathlib import Path

from r1.valuation_snapshot import build_valuation_snapshot


ROOT = Path(__file__).resolve().parents[1]


class R1ValuationSnapshotTest(unittest.TestCase):
    def test_materializes_only_actionable_consensus(self):
        with tempfile.TemporaryDirectory() as temp_dir:
            output = build_valuation_snapshot(
                date="2026-10-01",
                config_path=ROOT / "config/r1.json",
                market_path=ROOT / "data/r1/daily_market_20261001.json",
                consensus_path=ROOT / "data/r1/consensus/consensus.csv",
                consensus_evidence_path=ROOT / "data/r1/consensus/evidence.csv",
                output_root=temp_dir,
            )
            payload = json.loads(output.read_text(encoding="utf-8"))
            self.assertEqual(payload["ready_count"], 14)
            self.assertFalse(payload["historical_percentile_ready"])
            rows = {row["ticker"]: row for row in payload["rows"]}
            self.assertAlmostEqual(rows["2330"]["forward_pe"], 2510 / 142.33)
            self.assertEqual(rows["3363"]["status"], "BASELINE_RECORDED")
            self.assertAlmostEqual(rows["3363"]["forward_pe"], 641 / 16.93)

    def test_rejects_market_date_mismatch(self):
        with tempfile.TemporaryDirectory() as temp_dir:
            with self.assertRaisesRegex(ValueError, "market date mismatch"):
                build_valuation_snapshot(
                    date="2026-09-30",
                    config_path=ROOT / "config/r1.json",
                    market_path=ROOT / "data/r1/daily_market_20261001.json",
                    consensus_path=ROOT / "data/r1/consensus/consensus.csv",
                    consensus_evidence_path=ROOT / "data/r1/consensus/evidence.csv",
                    output_root=temp_dir,
                )
