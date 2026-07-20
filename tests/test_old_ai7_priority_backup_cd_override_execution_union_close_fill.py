import tempfile
import unittest
from pathlib import Path

import pandas as pd

from scripts.run_old_ai7_priority_backup_cd_override_execution_union_close_fill import load_authority


class OldAi7PriorityBackupCdOverrideExecutionUnionCloseFillTest(unittest.TestCase):
    def test_authority_requires_2228_rows_and_one_duplicate(self):
        with tempfile.TemporaryDirectory() as temp:
            path = Path(temp) / "authority.csv"
            dates = pd.date_range("2015-01-01", periods=2227, freq="B").strftime("%Y-%m-%d").tolist()
            pd.DataFrame({"ticker": ["00631L"] * 2228, "date": dates + [dates[0]]}).to_csv(path, index=False)
            authority, duplicates = load_authority(path)
            self.assertEqual(len(authority), 2227)
            self.assertEqual(len(duplicates), 2)


if __name__ == "__main__":
    unittest.main()
