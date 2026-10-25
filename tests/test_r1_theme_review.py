import json
import tempfile
import unittest
from pathlib import Path

from r1.theme_review import publish_review


class R1ThemeReviewPublishTest(unittest.TestCase):
    def test_not_due_review_does_not_replace_quarterly_snapshot(self):
        with tempfile.TemporaryDirectory() as folder:
            root = Path(folder)
            output = root / "latest.json"
            state = root / "state.json"
            output.write_text('{"date":"2026-10-16"}', encoding="utf-8")
            state.write_text('{"last_quarterly_review":"2026-10-16"}', encoding="utf-8")
            result = publish_review(
                payload={"date": "2026-10-23", "status": "READY", "version": "v1",
                         "cadence": {"quarterly_leader_review_due": False}},
                output_path=output, state_path=state,
            )
            self.assertFalse(result["published"])
            self.assertEqual(json.loads(output.read_text(encoding="utf-8"))["date"], "2026-10-16")

    def test_incomplete_due_review_preserves_last_complete_snapshot(self):
        with tempfile.TemporaryDirectory() as folder:
            root = Path(folder)
            output = root / "latest.json"
            state = root / "state.json"
            output.write_text('{"date":"2026-10-16"}', encoding="utf-8")
            result = publish_review(
                payload={"date": "2026-11-16", "status": "DATA_MISSING", "version": "v1",
                         "cadence": {"quarterly_leader_review_due": True}},
                output_path=output, state_path=state,
            )
            self.assertFalse(result["published"])
            self.assertEqual(json.loads(output.read_text(encoding="utf-8"))["date"], "2026-10-16")

    def test_complete_due_review_updates_snapshot_and_state(self):
        with tempfile.TemporaryDirectory() as folder:
            root = Path(folder)
            output = root / "latest.json"
            state = root / "state.json"
            state.write_text('{"last_membership_review":"2026-10-05"}', encoding="utf-8")
            payload = {"date": "2026-11-16", "status": "READY", "version": "v1",
                       "cadence": {"quarterly_leader_review_due": True}}
            result = publish_review(payload=payload, output_path=output, state_path=state)
            self.assertTrue(result["published"])
            self.assertEqual(json.loads(output.read_text(encoding="utf-8"))["date"], "2026-11-16")
            saved_state = json.loads(state.read_text(encoding="utf-8"))
            self.assertEqual(saved_state["last_quarterly_review"], "2026-11-16")
            self.assertEqual(saved_state["last_membership_review"], "2026-10-05")


if __name__ == "__main__":
    unittest.main()
