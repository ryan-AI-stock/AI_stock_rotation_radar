import json
import tempfile
import unittest
from pathlib import Path

from r1.membership_review import build_membership_review


ROOT = Path(__file__).resolve().parents[1]


class R1MembershipReviewTest(unittest.TestCase):
    def test_review_is_periodic_and_never_changes_universe_automatically(self):
        with tempfile.TemporaryDirectory() as folder:
            root = Path(folder)
            evidence = root / "evidence.json"
            discovery = root / "discovery.json"
            state = root / "state.json"
            evidence.write_text(json.dumps({"rows": [{"ticker": "2327"}]}), encoding="utf-8")
            discovery.write_text(json.dumps({"candidates": [{
                "ticker": "9999", "company": "測試", "status": "ELIGIBLE_FOR_RYAN_REVIEW"
            }]}), encoding="utf-8")
            state.write_text(json.dumps({"last_membership_review": "2026-08-15"}), encoding="utf-8")
            result = build_membership_review(
                as_of_date="2027-04-01", theme_path=ROOT / "config/r1_v02_themes.json",
                evidence_path=evidence, discovery_path=discovery, state_path=state,
            )
        self.assertEqual(result["status"], "REVIEW_DUE")
        self.assertEqual(result["member_count"], 52)
        self.assertEqual(result["addition_candidates_for_ryan_review"][0]["ticker"], "9999")
        self.assertFalse(result["automatic_changes_applied"])

    def test_recent_review_is_not_due(self):
        with tempfile.TemporaryDirectory() as folder:
            root = Path(folder)
            for name, payload in (("evidence.json", {"rows": []}), ("discovery.json", {"candidates": []}),
                                  ("state.json", {"last_membership_review": "2026-10-05"})):
                (root / name).write_text(json.dumps(payload), encoding="utf-8")
            result = build_membership_review(
                as_of_date="2026-10-05", theme_path=ROOT / "config/r1_v02_themes.json",
                evidence_path=root / "evidence.json", discovery_path=root / "discovery.json",
                state_path=root / "state.json",
            )
        self.assertEqual(result["status"], "NOT_DUE")


if __name__ == "__main__":
    unittest.main()
