import unittest
from pathlib import Path

from r1.dashboard_payload import build_dashboard_payload
from r1.dashboard_schema import TAB_SCHEMAS, validate_tabs


ROOT = Path(__file__).resolve().parents[1]


class R1DashboardPayloadTest(unittest.TestCase):
    def test_exact_three_tabs_exist_and_validate(self):
        payload = build_dashboard_payload(config_path=ROOT / "config/r1.json",
                                          market_path=ROOT / "data/r1/daily_market_20261001.json")
        self.assertEqual(set(payload["tabs"]), set(TAB_SCHEMAS))
        validate_tabs(payload["tabs"])
        self.assertEqual(set(payload["tabs"]), {"R1 Dashboard", "R1每日訊號資料庫", "R1模擬交易紀錄"})
        self.assertEqual(len(payload["tabs"]["R1每日訊號資料庫"]), 15)
        self.assertEqual(len(payload["tabs"]["R1模擬交易紀錄"]), 1)
        dashboard = payload["tabs"]["R1 Dashboard"]
        self.assertIn("03｜市場正在告訴我們什麼", [row[0] for row in dashboard])
        self.assertIn("04｜產業瓶頸與催化狀態", [row[0] for row in dashboard])
        self.assertIn("05｜下一個動態觸發條件", [row[0] for row in dashboard])
        self.assertIn("等待跨週資料", [cell for row in dashboard for cell in row])
        readiness = {row[0]: row[1] for row in dashboard if len(row) >= 2 and row[0] in {
            "EPS共識", "EPS修正歷史", "催化證據", "瓶頸證據", "20日價量籌碼序列",
            "當日法人與融資", "五年估值定位"
        }}
        self.assertEqual(readiness["EPS共識"], "14/14")
        self.assertEqual(readiness["EPS修正歷史"], "0/14")
        self.assertEqual(readiness["催化證據"], "14/14")
        self.assertEqual(readiness["瓶頸證據"], "14/14")
        self.assertEqual(readiness["20日價量籌碼序列"], "14/14")
        self.assertIn("當日法人與融資", readiness)
        self.assertEqual(readiness["五年估值定位"], "14/14")

    def test_dashboard_cannot_claim_trade_ready(self):
        payload = build_dashboard_payload(config_path=ROOT / "config/r1.json",
                                          market_path=ROOT / "data/r1/daily_market_20261001.json")
        actions = payload["tabs"]["R1 Dashboard"]
        self.assertIn("尚未啟用", [cell for row in actions for cell in row])
        signals = payload["tabs"]["R1每日訊號資料庫"]
        self.assertEqual(next(row for row in signals if row[1] == "2330")[23], "CORE")

    def test_header_mismatch_is_rejected(self):
        tabs = {title: [list(headers)] for title, headers in TAB_SCHEMAS.items()}
        tabs["R1 Dashboard"] = [["R1研究版｜AI瓶頸預期差輪動"]]
        tabs["R1每日訊號資料庫"][0][0] = "wrong"
        with self.assertRaisesRegex(ValueError, "header mismatch"):
            validate_tabs(tabs)


if __name__ == "__main__":
    unittest.main()
