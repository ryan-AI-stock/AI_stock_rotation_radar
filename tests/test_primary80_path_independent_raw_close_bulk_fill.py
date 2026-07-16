from __future__ import annotations

import sys
import unittest
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "scripts"))

from run_p1_p2_primary80_path_independent_raw_close_bulk_fill import (
    official_no_session_proven,
    parse_market_close,
)


class Primary80PathIndependentRawCloseBulkFillTest(unittest.TestCase):
    def test_parses_close_only_from_market_table(self) -> None:
        schema_ok, values = parse_market_close({
            "tables": [{
                "fields": ["證券代號", "證券名稱", "收盤價", "成交股數"],
                "data": [["2330", "台積電", "1,045.00", "1"]],
            }]
        })

        self.assertTrue(schema_ok)
        self.assertEqual(values, {"2330": 1045.0})

    def test_valid_empty_response_remains_no_rows(self) -> None:
        schema_ok, values = parse_market_close({"stat": "OK", "tables": []})

        self.assertTrue(schema_ok)
        self.assertEqual(values, {})

    def test_http_200_no_data_with_second_market_no_rows_is_official_no_session(self) -> None:
        item = {
            "status": "temporary_source_gap",
            "error": "schema_not_ok",
            "http_status": 200,
            "source_hash": "abc",
        }

        self.assertTrue(official_no_session_proven(item, "official_valid_no_target_rows", "failed"))


if __name__ == "__main__":
    unittest.main()
