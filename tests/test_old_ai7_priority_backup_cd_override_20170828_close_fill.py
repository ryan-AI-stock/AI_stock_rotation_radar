import tempfile
import unittest
from pathlib import Path

import pandas as pd

from scripts.run_old_ai7_priority_backup_cd_override_20170828_close_fill import load_authority


class OldAi7PriorityBackupCdOverride20170828CloseFillTest(unittest.TestCase):
    def test_authority_requires_exact_00631l_date(self):
        with tempfile.TemporaryDirectory() as temp:
            path = Path(temp) / "authority.csv"
            pd.DataFrame([{"ticker": "00631L", "date": "2017-08-28"}]).to_csv(path, index=False)
            self.assertEqual(len(load_authority(path)), 1)


if __name__ == "__main__":
    unittest.main()
