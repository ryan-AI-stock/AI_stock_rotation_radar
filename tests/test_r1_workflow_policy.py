import unittest
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]


class R1WorkflowPolicyTest(unittest.TestCase):
    def test_daily_uses_shared_rules_and_publishes_with_readback(self):
        workflow = (ROOT / ".github/workflows/r1-daily.yml").read_text(encoding="utf-8")
        self.assertIn("AI_stock_schedule_rules/schedule_rules.json", workflow)
        self.assertIn("r1.market_snapshot", workflow)
        self.assertIn("config/r1_v02_themes.json", workflow)
        self.assertIn("theme_daily_market_latest.json", workflow)
        self.assertIn("for attempt in 1 2 3", workflow)
        self.assertIn("--reuse-exact-complete", workflow)
        self.assertIn("if [ \"$attempt\" -eq 3 ]; then exit 75; fi", workflow)
        self.assertIn("--retry-incomplete", workflow)
        self.assertIn("--allow-chip-gaps", workflow)
        self.assertIn("group: r1-publication", workflow)
        self.assertIn("r1.dashboard_publish", workflow)
        self.assertIn("GOOGLE_OAUTH_REFRESH_TOKEN", workflow)
        self.assertIn("Sync latest main after concurrency wait", workflow)
        self.assertIn('15 9-15 * * 1-5', workflow)
        self.assertIn("repository: ryan-AI-stock/AI_stock_schedule_rules", workflow)
        self.assertIn("--profile daily --rules AI_stock_schedule_rules/schedule_rules.json", workflow)
        self.assertIn("Report R1 daily failure context", workflow)
        self.assertIn("Dashboard was not accepted as complete", workflow)

    def test_weekly_requires_week_final_confirmation(self):
        workflow = (ROOT / ".github/workflows/r1-weekly.yml").read_text(encoding="utf-8")
        self.assertIn("--profile weekly", workflow)
        self.assertIn("--week-final-confirmed", workflow)
        self.assertIn("r1.weekly_snapshot", workflow)
        self.assertIn("r1.discovery", workflow)
        self.assertIn("r1.theme_review", workflow)
        self.assertIn("for attempt in 1 2 3", workflow)
        self.assertIn("--reuse-exact-complete", workflow)
        self.assertIn("r1.dashboard_publish", workflow)
        self.assertIn("Sync latest main after concurrency wait", workflow)
        self.assertIn('15 11-15 * * *', workflow)
        self.assertIn("repository: ryan-AI-stock/AI_stock_schedule_rules", workflow)
        self.assertIn("--profile weekly --rules AI_stock_schedule_rules/schedule_rules.json", workflow)
        self.assertIn("Report R1 weekly failure context", workflow)
        self.assertIn("Weekly snapshot was not accepted as complete", workflow)
        self.assertNotIn("--allow-chip-gaps", workflow)
        self.assertNotIn("toalpha_consensus --require-complete", workflow)
        self.assertNotIn("toalpha_revision_history --require-complete", workflow)
        self.assertIn("group: r1-publication", workflow)


if __name__ == "__main__":
    unittest.main()
