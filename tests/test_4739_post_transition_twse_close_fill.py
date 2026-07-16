from __future__ import annotations

import unittest

from scripts.run_4739_post_transition_twse_close_fill import is_proven_market_closed_checkpoint, parse_twse_close


class PostTransition4739CloseFillTests(unittest.TestCase):
    def test_parser_returns_only_exact_4739_close(self) -> None:
        payload = {
            "tables": [{
                "fields": ["證券代號", "證券名稱", "收盤價"],
                "data": [["1101", "台泥", "45.0"], ["4739", "康普", "123.5"]],
            }]
        }

        schema_ok, close = parse_twse_close(payload)

        self.assertTrue(schema_ok)
        self.assertEqual(close, 123.5)

    def test_parser_keeps_valid_no_target_separate(self) -> None:
        payload = {"fields": ["證券代號", "收盤價"], "data": [["1101", "45.0"]], "stat": "OK"}

        schema_ok, close = parse_twse_close(payload)

        self.assertTrue(schema_ok)
        self.assertIsNone(close)

    def test_market_closed_reuse_requires_official_classification_evidence(self) -> None:
        self.assertTrue(is_proven_market_closed_checkpoint({
            "status": "official_valid_no_target_rows",
            "classification_evidence": "twse_http_200_no_data_plus_tpex_no_rows",
        }))
        self.assertFalse(is_proven_market_closed_checkpoint({
            "status": "official_valid_no_target_rows",
            "classification_evidence": "",
        }))


if __name__ == "__main__":
    unittest.main()
