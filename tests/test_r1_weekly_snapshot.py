import json
import tempfile
import unittest
from pathlib import Path

from r1.weekly_snapshot import build_weekly_snapshot


ROOT = Path(__file__).resolve().parents[1]


class R1WeeklySnapshotTest(unittest.TestCase):
    def _write_complete_chip_day(self, root: Path, target: str = "2026-10-01") -> None:
        daily = root / "daily"
        daily.mkdir(parents=True, exist_ok=True)
        config = json.loads((ROOT / "config/r1.json").read_text(encoding="utf-8"))
        daily.joinpath(f"{target}.json").write_text(json.dumps({
            "date": target,
            "price_rows": [],
            "chip_rows": [
                {"ticker": row["ticker"], "family": family}
                for row in config["securities"]
                for family in ("institutional", "margin_short")
            ],
        }), encoding="utf-8")

    def test_snapshot_blocks_actions_without_consensus(self):
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            self._write_complete_chip_day(root)
            output = build_weekly_snapshot(
                date="2026-10-01", config_path=ROOT / "config/r1.json",
                market_path=ROOT / "data/r1/daily_market_20261001.json",
                daily_source_root=root / "daily", output_root=root / "weekly", week_final_confirmed=True,
            )
            payload = json.loads(output.read_text(encoding="utf-8"))
            self.assertEqual(len(payload["rows"]), 14)
            self.assertEqual(next(row for row in payload["rows"] if row["ticker"] == "2330")["action"], "CORE")
            self.assertTrue(all(row["action"] == "DATA_MISSING" for row in payload["rows"] if row["ticker"] != "2330"))
            self.assertTrue(all(row["chip_data_status"] == "AVAILABLE" for row in payload["rows"]))

    def test_snapshot_is_append_only(self):
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            self._write_complete_chip_day(root)
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
            self._write_complete_chip_day(root)
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
            self.assertIsNone(mediatek["forward_pe_percentile_5y"])
            self.assertEqual(mediatek["action"], "WATCH")
            self.assertEqual(mediatek["action_reason"], "ACTION_THRESHOLDS_NOT_APPROVED")
            nanya = next(row for row in payload["rows"] if row["ticker"] == "2408")
            self.assertEqual(nanya["forward_pe_percentile_5y"], .29)
            self.assertEqual(nanya["forward_pe_median_5y"], 10.0)

    def test_unconfirmed_midweek_snapshot_is_rejected(self):
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            self._write_complete_chip_day(root)
            with self.assertRaisesRegex(ValueError, "week_final_confirmed"):
                build_weekly_snapshot(date="2026-10-01", config_path=ROOT / "config/r1.json",
                                      market_path=ROOT / "data/r1/daily_market_20261001.json",
                                      daily_source_root=root / "daily", output_root=root / "weekly")

    def test_snapshot_rejects_incomplete_exact_date_chip_data(self):
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            daily = root / "daily"
            daily.mkdir()
            daily.joinpath("2026-10-01.json").write_text(json.dumps({
                "date": "2026-10-01", "chip_rows": [
                    {"ticker": "2330", "family": "institutional"},
                ],
            }), encoding="utf-8")
            with self.assertRaisesRegex(ValueError, "exact-date institutional and margin"):
                build_weekly_snapshot(
                    date="2026-10-01", config_path=ROOT / "config/r1.json",
                    market_path=ROOT / "data/r1/daily_market_20261001.json",
                    daily_source_root=daily, output_root=root / "weekly", week_final_confirmed=True,
                )

    def test_revision_remains_missing_until_prior_snapshot_exists(self):
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            self._write_complete_chip_day(root)
            history = root / "history"
            history.mkdir()
            history.joinpath("2026-10-01.json").write_text(json.dumps({
                "rows": [{"ticker": "2408", "fiscal_year": 2027, "mean_eps": 100, "status": "READY"}],
            }), encoding="utf-8")
            output = build_weekly_snapshot(
                date="2026-10-01", config_path=ROOT / "config/r1.json",
                market_path=ROOT / "data/r1/daily_market_20261001.json",
                daily_source_root=root / "daily", output_root=root / "weekly", week_final_confirmed=True,
                consensus_path=ROOT / "data/r1/consensus/consensus.csv",
                consensus_evidence_path=ROOT / "data/r1/consensus/evidence.csv",
                consensus_history_root=history,
            )
            payload = json.loads(output.read_text(encoding="utf-8"))
            nanya = next(row for row in payload["rows"] if row["ticker"] == "2408")
            self.assertIsNone(nanya["eps_revision_1w"])
            self.assertIsNone(nanya["eps_revision_4w"])
            self.assertEqual(nanya["eps_history_current_date"], "2026-10-01")

    def test_revision_uses_latest_snapshot_on_or_before_horizon(self):
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            self._write_complete_chip_day(root)
            history = root / "history"
            history.mkdir()
            for snapshot_date, eps in (("2026-09-01", 100), ("2026-10-01", 120)):
                history.joinpath(f"{snapshot_date}.json").write_text(json.dumps({
                    "rows": [{"ticker": "2408", "fiscal_year": 2027, "mean_eps": eps, "status": "READY"}],
                }), encoding="utf-8")
            output = build_weekly_snapshot(
                date="2026-10-01", config_path=ROOT / "config/r1.json",
                market_path=ROOT / "data/r1/daily_market_20261001.json",
                daily_source_root=root / "daily", output_root=root / "weekly", week_final_confirmed=True,
                consensus_path=ROOT / "data/r1/consensus/consensus.csv",
                consensus_evidence_path=ROOT / "data/r1/consensus/evidence.csv",
                consensus_history_root=history,
            )
            payload = json.loads(output.read_text(encoding="utf-8"))
            nanya = next(row for row in payload["rows"] if row["ticker"] == "2408")
            self.assertAlmostEqual(nanya["eps_revision_4w"], 0.20)
            self.assertEqual(nanya["eps_revision_4w_base_date"], "2026-09-01")
            self.assertIsNone(nanya["eps_score"])


if __name__ == "__main__":
    unittest.main()
