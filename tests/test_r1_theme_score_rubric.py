import json
import tempfile
import unittest
from pathlib import Path

from r1.theme_score_rubric import load_and_validate


ROOT = Path(__file__).resolve().parents[1]


class R1ThemeScoreRubricTest(unittest.TestCase):
    def test_canonical_rubric_is_valid(self):
        payload = load_and_validate(ROOT / "config/r1_v03_score_rubric.json")
        self.assertEqual(len(payload["quarterly"]), 5)
        self.assertEqual(len(payload["daily"]), 5)

    def test_missing_values_cannot_be_reweighted(self):
        payload = json.loads((ROOT / "config/r1_v03_score_rubric.json").read_text(encoding="utf-8"))
        payload["principles"]["missing_value"] = "REWEIGHT"
        with tempfile.TemporaryDirectory() as directory:
            path = Path(directory) / "rubric.json"
            path.write_text(json.dumps(payload), encoding="utf-8")
            with self.assertRaisesRegex(ValueError, "remain NA"):
                load_and_validate(path)

    def test_weight_drift_is_rejected(self):
        payload = json.loads((ROOT / "config/r1_v03_score_rubric.json").read_text(encoding="utf-8"))
        payload["daily"]["structural_leader"]["weight"] = 0.31
        with tempfile.TemporaryDirectory() as directory:
            path = Path(directory) / "rubric.json"
            path.write_text(json.dumps(payload), encoding="utf-8")
            with self.assertRaisesRegex(ValueError, "canonical weights"):
                load_and_validate(path)


if __name__ == "__main__":
    unittest.main()
