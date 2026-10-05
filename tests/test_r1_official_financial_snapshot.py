import tempfile
import unittest
from pathlib import Path

from r1.official_financial_snapshot import build_snapshot


ROOT = Path(__file__).resolve().parents[1]


class R1OfficialFinancialSnapshotTest(unittest.TestCase):
    def test_exact_universe_and_missing_are_explicit(self):
        sample_income = [{"公司代號": "2330", "年度": "115", "季別": "2", "出表日期": "1151005",
                          "營業收入": "100", "本期淨利（淨損）": "20", "基本每股盈餘（元）": "2"}]
        sample_balance = [{"公司代號": "2330", "年度": "115", "季別": "2", "出表日期": "1151005",
                           "資產總計": "200", "負債總計": "80", "權益總計": "120"}]
        with tempfile.TemporaryDirectory() as directory:
            payload = build_snapshot(
                as_of_date="2026-10-05", theme_path=ROOT / "config/r1_v02_themes.json",
                output_path=Path(directory) / "out.json",
                payloads={"TWSE_income": sample_income, "TWSE_balance": sample_balance,
                          "TPEx_income": [], "TPEx_balance": []},
            )
        self.assertEqual(payload["requested_ticker_count"], 50)
        self.assertEqual(payload["actual_ticker_count"], 1)
        self.assertEqual(next(row for row in payload["rows"] if row["ticker"] == "2330")["eps"], 2)
        self.assertTrue(payload["gaps"])


if __name__ == "__main__":
    unittest.main()
