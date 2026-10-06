import json
import tempfile
import unittest
from pathlib import Path

from r1.valuation_snapshot import build_valuation_snapshot


ROOT = Path(__file__).resolve().parents[1]


class R1ValuationSnapshotTest(unittest.TestCase):
    def _market(self, root: Path, target: str = "2026-10-02") -> Path:
        payload = json.loads((ROOT / "data/r1/theme_daily_market_latest.json").read_text(encoding="utf-8"))
        payload["date"] = target
        path = root / "market.json"
        path.write_text(json.dumps(payload), encoding="utf-8")
        return path

    def test_materializes_only_actionable_consensus(self):
        with tempfile.TemporaryDirectory() as temp_dir:
            market = self._market(Path(temp_dir))
            output = build_valuation_snapshot(
                date="2026-10-02",
                config_path=ROOT / "config/r1.json",
                market_path=market,
                consensus_path=ROOT / "data/r1/consensus/consensus.csv",
                consensus_evidence_path=ROOT / "data/r1/consensus/evidence.csv",
                valuation_reference_path=ROOT / "data/r1/valuation_reference.csv",
                output_root=temp_dir,
            )
            payload = json.loads(output.read_text(encoding="utf-8"))
            self.assertEqual(payload["ready_count"], 12)
            self.assertFalse(payload["historical_percentile_ready"])
            rows = {row["ticker"]: row for row in payload["rows"]}
            self.assertAlmostEqual(rows["2330"]["forward_pe"], rows["2330"]["price"] / 142.33)
            self.assertEqual(payload["base_scenario_ready_count"], 12)
            self.assertEqual(payload["complete_scenario_ready_count"], 0)
            self.assertEqual(payload["scenario_gap"], "5Y_FORWARD_PE_LOW_HIGH_BANDS_MISSING")
            self.assertAlmostEqual(rows["2408"]["base_fair_value"], 93.24 * 10.0)
            self.assertAlmostEqual(rows["2408"]["base_upside"], 93.24 * 10.0 / rows["2408"]["price"] - 1)
            self.assertIsNone(rows["2408"]["bear_fair_value"])
            self.assertEqual(rows["2408"]["scenario_status"], "BASE_READY_PE_BANDS_MISSING")
            self.assertEqual(rows["2330"]["scenario_status"], "BASE_READY_PE_BANDS_MISSING")
            self.assertEqual(rows["2454"]["scenario_status"], "BASE_READY_PE_BANDS_MISSING")
            self.assertEqual(rows["3363"]["status"], "BASELINE_RECORDED")
            self.assertAlmostEqual(rows["3363"]["forward_pe"], rows["3363"]["price"] / 16.93)

    def test_rejects_market_date_mismatch(self):
        with tempfile.TemporaryDirectory() as temp_dir:
            market = self._market(Path(temp_dir), "2026-10-02")
            with self.assertRaisesRegex(ValueError, "market date mismatch"):
                build_valuation_snapshot(
                    date="2026-09-30",
                    config_path=ROOT / "config/r1.json",
                    market_path=market,
                    consensus_path=ROOT / "data/r1/consensus/consensus.csv",
                    consensus_evidence_path=ROOT / "data/r1/consensus/evidence.csv",
                    valuation_reference_path=ROOT / "data/r1/valuation_reference.csv",
                    output_root=temp_dir,
                )

    def test_valid_existing_snapshot_is_reused(self):
        with tempfile.TemporaryDirectory() as temp_dir:
            market = self._market(Path(temp_dir))
            kwargs = dict(
                date="2026-10-02", config_path=ROOT / "config/r1.json",
                market_path=market,
                consensus_path=ROOT / "data/r1/consensus/consensus.csv",
                consensus_evidence_path=ROOT / "data/r1/consensus/evidence.csv",
                valuation_reference_path=ROOT / "data/r1/valuation_reference.csv",
                output_root=temp_dir,
            )
            output = build_valuation_snapshot(**kwargs)
            original = output.read_text(encoding="utf-8")
            self.assertEqual(build_valuation_snapshot(**kwargs).read_text(encoding="utf-8"), original)

    def test_invalid_existing_snapshot_is_rejected(self):
        with tempfile.TemporaryDirectory() as temp_dir:
            market = self._market(Path(temp_dir))
            output = Path(temp_dir) / "2026-10-02.json"
            output.write_text("{}", encoding="utf-8")
            with self.assertRaises(FileExistsError):
                build_valuation_snapshot(
                    date="2026-10-02", config_path=ROOT / "config/r1.json",
                    market_path=market,
                    consensus_path=ROOT / "data/r1/consensus/consensus.csv",
                    consensus_evidence_path=ROOT / "data/r1/consensus/evidence.csv",
                    valuation_reference_path=ROOT / "data/r1/valuation_reference.csv",
                    output_root=temp_dir,
                )
