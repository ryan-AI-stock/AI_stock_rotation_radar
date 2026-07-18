import tempfile
import unittest
from pathlib import Path

import pandas as pd

from scripts.run_weekly_ai_diffusion_switch_deferred_6669_close_fill import (
    EXPECTED_DATES,
    exact_rows_from_checkpoint,
    load_authority,
)


class WeeklyAiDiffusionSwitchDeferred6669CloseFillTest(unittest.TestCase):
    def test_authority_scope_guard(self):
        with tempfile.TemporaryDirectory() as temp:
            path = Path(temp) / "authority.csv"
            pd.DataFrame({"ticker": ["6669"] * 4, "date": EXPECTED_DATES}).to_csv(path, index=False)
            authority = load_authority(path)
        self.assertEqual(authority["date"].tolist(), EXPECTED_DATES)

    def test_extract_exact_rows_only(self):
        item = {
            "source_url": "official",
            "source_hash": "abc",
            "retrieved_at": "now",
            "rows": [
                {"date": "2019-03-27", "close": 225.0},
                {"date": "2019-03-26", "close": 220.0},
            ],
        }
        rows = exact_rows_from_checkpoint(item, "6669", {"2019-03-27"}, "test")
        self.assertEqual(len(rows), 1)
        self.assertEqual(rows[0]["date"], "2019-03-27")
        self.assertEqual(rows[0]["close"], 225.0)


if __name__ == "__main__":
    unittest.main()
