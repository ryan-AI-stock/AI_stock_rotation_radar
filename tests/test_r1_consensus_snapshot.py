import json
import tempfile
import unittest
from pathlib import Path

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
            self.assertEqual(payload["ready_count"], 14)
            self.assertEqual(payload["snapshot_policy"], "append_only_source_available_at")
            rows = {row["ticker"]: row for row in payload["rows"]}
            self.assertEqual(rows["2408"]["mean_eps"], 102.56)
            self.assertEqual(rows["3363"]["status"], "READY")
            self.assertEqual(rows["3363"]["mean_eps"], 16.93)

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


if __name__ == "__main__":
    unittest.main()
