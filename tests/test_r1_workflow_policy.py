import unittest
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]


class R1WorkflowPolicyTest(unittest.TestCase):
    def test_daily_uses_shared_rules_and_no_sheet_publish(self):
        workflow = (ROOT / ".github/workflows/r1-daily.yml").read_text(encoding="utf-8")
        self.assertIn("AI_stock_schedule_rules/schedule_rules.json", workflow)
        self.assertIn("r1.market_snapshot", workflow)
        self.assertIn("--retry-incomplete", workflow)
        self.assertNotIn("spreadsheet-id", workflow)

    def test_weekly_requires_week_final_confirmation(self):
        workflow = (ROOT / ".github/workflows/r1-weekly.yml").read_text(encoding="utf-8")
        self.assertIn("--profile weekly", workflow)
        self.assertIn("--week-final-confirmed", workflow)
        self.assertIn("r1.weekly_snapshot", workflow)
        self.assertIn('0 11-15 * * *', workflow)


if __name__ == "__main__":
    unittest.main()
