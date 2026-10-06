import json
import tempfile
import unittest
from pathlib import Path

from r1.consensus import load_consensus_csv
from r1.consensus_snapshot import build_consensus_snapshot


ROOT = Path(__file__).resolve().parents[1]


class R1ConsensusSnapshotTest(unittest.TestCase):
    def test_snapshot_records_only_actionable_observed_consensus(self):
        with tempfile.TemporaryDirectory() as directory:
            output = build_consensus_snapshot(
                date="2026-10-02",
                config_path=ROOT / "config/r1.json",
                consensus_path=ROOT / "data/r1/consensus/consensus.csv",
                consensus_evidence_path=ROOT / "data/r1/consensus/evidence.csv",
                output_root=directory,
            )
            payload = json.loads(output.read_text(encoding="utf-8"))
            self.assertEqual(payload["ready_count"], 41)
            self.assertEqual(payload["requested_record_count"], 162)
            self.assertEqual(payload["fiscal_years"], [2026, 2027, 2028])
            self.assertEqual(payload["snapshot_policy"], "append_only_source_available_at")
            rows = {row["ticker"]: row for row in payload["rows"] if row["fiscal_year"] == 2027}
            source = load_consensus_csv(ROOT / "data/r1/consensus/consensus.csv", as_of_date="2026-10-02")
            expected = {(row.ticker, row.fiscal_year): row for row in source.records}
            self.assertEqual(rows["2408"]["mean_eps"], expected[("2408", 2027)].mean_eps)
            self.assertEqual(rows["3363"]["status"], "READY")
            self.assertEqual(rows["3363"]["mean_eps"], expected[("3363", 2027)].mean_eps)
            far_rows = {row["ticker"]: row for row in payload["rows"] if row["fiscal_year"] == 2028}
            self.assertEqual(far_rows["3363"]["status"], "EVIDENCE_GAP")

    def test_snapshot_is_append_only(self):
        with tempfile.TemporaryDirectory() as directory:
            kwargs = dict(
                date="2026-10-02",
                config_path=ROOT / "config/r1.json",
                consensus_path=ROOT / "data/r1/consensus/consensus.csv",
                consensus_evidence_path=ROOT / "data/r1/consensus/evidence.csv",
                output_root=directory,
            )
            output = build_consensus_snapshot(**kwargs)
            output.write_text("{}", encoding="utf-8")
            with self.assertRaises(FileExistsError):
                build_consensus_snapshot(**kwargs)

    def test_valid_existing_snapshot_is_reused_even_if_sources_change(self):
        with tempfile.TemporaryDirectory() as directory:
            kwargs = dict(
                date="2026-10-02",
                config_path=ROOT / "config/r1.json",
                consensus_path=ROOT / "data/r1/consensus/consensus.csv",
                consensus_evidence_path=ROOT / "data/r1/consensus/evidence.csv",
                output_root=directory,
            )
            output = build_consensus_snapshot(**kwargs)
            original = output.read_text(encoding="utf-8")
            reused = build_consensus_snapshot(**kwargs)
            self.assertEqual(reused.read_text(encoding="utf-8"), original)


if __name__ == "__main__":
    unittest.main()
