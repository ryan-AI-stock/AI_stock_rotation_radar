import json
import tempfile
import unittest
from pathlib import Path

from r1.weekly_snapshot import build_weekly_snapshot


ROOT = Path(__file__).resolve().parents[1]


class R1WeeklySnapshotTest(unittest.TestCase):
    def test_snapshot_blocks_actions_without_consensus(self):
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            output = build_weekly_snapshot(
                date="2026-10-01", config_path=ROOT / "config/r1.json",
                market_path=ROOT / "data/r1/daily_market_20261001.json",
                daily_source_root=root / "daily", output_root=root / "weekly", week_final_confirmed=True,
            )
            payload = json.loads(output.read_text(encoding="utf-8"))
            self.assertEqual(len(payload["rows"]), 14)
            self.assertEqual(next(row for row in payload["rows"] if row["ticker"] == "2330")["action"], "CORE")
            self.assertTrue(all(row["action"] == "DATA_MISSING" for row in payload["rows"] if row["ticker"] != "2330"))
            self.assertTrue(all(row["chip_data_status"] == "DATA_MISSING" for row in payload["rows"]))

    def test_snapshot_is_append_only(self):
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            kwargs = dict(date="2026-10-01", config_path=ROOT / "config/r1.json",
                          market_path=ROOT / "data/r1/daily_market_20261001.json",
                          daily_source_root=root / "daily", output_root=root / "weekly", week_final_confirmed=True)
            first = build_weekly_snapshot(**kwargs)
            first.write_text("{}", encoding="utf-8")
            with self.assertRaises(FileExistsError):
                build_weekly_snapshot(**kwargs)

    def test_verified_consensus_enters_snapshot_as_watch_only(self):
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            output = build_weekly_snapshot(
                date="2026-10-01", config_path=ROOT / "config/r1.json",
                market_path=ROOT / "data/r1/daily_market_20261001.json",
                daily_source_root=root / "daily", output_root=root / "weekly", week_final_confirmed=True,
                consensus_path=ROOT / "data/r1/consensus/consensus.csv",
                consensus_evidence_path=ROOT / "data/r1/consensus/evidence.csv",
            )
            payload = json.loads(output.read_text(encoding="utf-8"))
            mediatek = next(row for row in payload["rows"] if row["ticker"] == "2454")
            self.assertEqual(mediatek["next_year_eps"], 141.32)
            self.assertTrue(mediatek["consensus_allowed"])
            self.assertEqual(mediatek["action"], "WATCH")
            self.assertEqual(mediatek["action_reason"], "ACTION_THRESHOLDS_NOT_APPROVED")

    def test_unconfirmed_midweek_snapshot_is_rejected(self):
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            with self.assertRaisesRegex(ValueError, "week_final_confirmed"):
                build_weekly_snapshot(date="2026-10-01", config_path=ROOT / "config/r1.json",
                                      market_path=ROOT / "data/r1/daily_market_20261001.json",
                                      daily_source_root=root / "daily", output_root=root / "weekly")


if __name__ == "__main__":
    unittest.main()
