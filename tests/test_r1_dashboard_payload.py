import unittest
from pathlib import Path

from r1.dashboard_payload import build_dashboard_payload
from r1.dashboard_schema import TAB_SCHEMAS, validate_tabs


ROOT = Path(__file__).resolve().parents[1]


class R1DashboardPayloadTest(unittest.TestCase):
    def test_all_13_tabs_exist_and_validate(self):
        payload = build_dashboard_payload(config_path=ROOT / "config/r1.json",
                                          market_path=ROOT / "data/r1/daily_market_20261001.json")
        self.assertEqual(set(payload["tabs"]), set(TAB_SCHEMAS))
        validate_tabs(payload["tabs"])
        self.assertEqual(len(payload["tabs"]["Portfolio"]), 15)

    def test_dashboard_cannot_claim_trade_ready(self):
        payload = build_dashboard_payload(config_path=ROOT / "config/r1.json",
                                          market_path=ROOT / "data/r1/daily_market_20261001.json")
        actions = payload["tabs"]["R1 Dashboard"]
        self.assertIn("BLOCKED", [row[3] for row in actions[1:]])
        portfolio = payload["tabs"]["Portfolio"]
        self.assertEqual(next(row for row in portfolio if row[0] == "2330")[8], "CORE")

    def test_header_mismatch_is_rejected(self):
        tabs = {title: [list(headers)] for title, headers in TAB_SCHEMAS.items()}
        tabs["Portfolio"][0][0] = "wrong"
        with self.assertRaisesRegex(ValueError, "header mismatch"):
            validate_tabs(tabs)


if __name__ == "__main__":
    unittest.main()
