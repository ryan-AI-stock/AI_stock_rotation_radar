import tempfile
import unittest
from pathlib import Path

import pandas as pd

from scripts.run_strict_ai_diffusion_bear_cash_close_fill import EXPECTED_DATES, exact_rows, load_authority


class StrictAiDiffusionBearCashCloseFillTest(unittest.TestCase):
    def test_authority_scope_guard(self):
        with tempfile.TemporaryDirectory() as temp:
            path = Path(temp) / "authority.csv"
            pd.DataFrame({"ticker": ["00631L"] * 3, "date": EXPECTED_DATES}).to_csv(path, index=False)
            authority = load_authority(path)
        self.assertEqual(authority["date"].tolist(), EXPECTED_DATES)

    def test_exact_rows_filters_month_payload(self):
        rows = exact_rows({"rows": [{"date": "2022-07-11", "close": 30.5}, {"date": "2022-07-12", "close": 31.0}]}, {"2022-07-11"}, "test")
        self.assertEqual(rows, [{"ticker": "00631L", "date": "2022-07-11", "market": "TWSE", "close": 30.5, "source_quality": "official_twse_selected_ticker_month_close_only", "adjustment_policy": "official_unadjusted_execution_close_only", "source_url": "", "source_hash": "", "retrieved_at": "", "source_reuse": "test", "future_data_violation_count": 0}])


if __name__ == "__main__": unittest.main()
