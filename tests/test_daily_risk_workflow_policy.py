from __future__ import annotations

import unittest
from pathlib import Path


class DailyRiskWorkflowPolicyTests(unittest.TestCase):
    def test_scheduled_retry_and_deferred_source_policy_are_wired(self) -> None:
        workflow = Path(".github/workflows/daily-risk-features.yml").read_text(encoding="utf-8")

        self.assertIn('cron: "30 13 * * 1-5"', workflow)
        self.assertIn('cron: "0 15 * * 1-5"', workflow)
        self.assertIn("retry_groups_from_manifest", workflow)
        self.assertIn("steps.args.outputs.skip != 'true'", workflow)
        self.assertIn("Classify deferred official source", workflow)
        self.assertIn("::warning::", workflow)
        self.assertIn("Acquisition failed without a persisted manifest", workflow)


if __name__ == "__main__":
    unittest.main()
