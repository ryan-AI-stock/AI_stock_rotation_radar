import json
import tempfile
import unittest
from pathlib import Path

from r1.config import R1Config


ROOT = Path(__file__).resolve().parents[1]


class R1ConfigTest(unittest.TestCase):
    def test_seed_config_preserves_contract(self):
        config = R1Config.load(ROOT / "config" / "r1.json")
        self.assertEqual(config.version, "r1-0.1.0")
        self.assertAlmostEqual(sum(config.weights.values()), 1.0)
        self.assertEqual(len(config.securities), 14)
        core = [security for security in config.securities if security.core_lock]
        self.assertEqual([security.ticker for security in core], ["2330"])
        self.assertEqual(core[0].shares, 2534)

    def test_invalid_weight_sum_is_rejected(self):
        payload = json.loads((ROOT / "config" / "r1.json").read_text(encoding="utf-8"))
        payload["weights"]["eps_revision"] = 0.31
        with tempfile.TemporaryDirectory() as directory:
            path = Path(directory) / "bad.json"
            path.write_text(json.dumps(payload, ensure_ascii=False), encoding="utf-8")
            with self.assertRaisesRegex(ValueError, "sum to 1.0"):
                R1Config.load(path)

    def test_non_2330_core_lock_is_rejected(self):
        payload = json.loads((ROOT / "config" / "r1.json").read_text(encoding="utf-8"))
        payload["securities"][1]["core_lock"] = True
        with tempfile.TemporaryDirectory() as directory:
            path = Path(directory) / "bad.json"
            path.write_text(json.dumps(payload, ensure_ascii=False), encoding="utf-8")
            with self.assertRaisesRegex(ValueError, "only for 2330"):
                R1Config.load(path)


if __name__ == "__main__":
    unittest.main()
