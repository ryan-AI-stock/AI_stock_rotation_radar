import csv
import json
import unittest
from pathlib import Path
from tempfile import TemporaryDirectory

from r1.evidence_readiness import materialize


class R1EvidenceReadinessTest(unittest.TestCase):
    def test_missing_files_block_every_ticker(self):
        with TemporaryDirectory() as folder:
            result = materialize(config_path="config/r1.json", consensus_path=Path(folder) / "none.csv",
                                 catalyst_path=Path(folder) / "none2.csv", as_of_date="2026-10-01")
        self.assertEqual(result["requested_ticker_count"], 14)
        self.assertEqual(result["trade_ready_count"], 0)
        self.assertFalse(result["active_in_trade_decision"])


if __name__ == "__main__":
    unittest.main()
