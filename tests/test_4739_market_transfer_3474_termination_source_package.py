from __future__ import annotations

import unittest
from pathlib import Path
from tempfile import TemporaryDirectory

from scripts.run_4739_market_transfer_3474_termination_source_package import (
    build_4739_patch,
    classify_case,
    read_csv,
    summarize_post_last,
    write_csv,
)


class MarketTransferTerminationSourcePackageTests(unittest.TestCase):
    def test_post_last_summary_keeps_market_transfer_separate_from_termination(self) -> None:
        rows = [
            {
                "ticker": "", "ticker_last": "4739", "decision_date": "2017-09-11",
                "last_official_raw_close_date": "2017-09-08", "variant_id": "A",
            },
            {
                "ticker": "", "ticker_last": "3474", "decision_date": "2016-12-07",
                "last_official_raw_close_date": "2016-11-29", "variant_id": "A",
            },
        ]
        summary = summarize_post_last(rows)

        self.assertEqual({row["ticker"] for row in summary}, {"3474", "4739"})
        self.assertEqual(classify_case("4739")[0], "market_transfer_same_ticker")
        self.assertEqual(classify_case("3474")[0], "true_termination_cash_share_swap")

    def test_4739_patch_requires_twse_exact_date_after_transfer(self) -> None:
        rows = [
            {"ticker": "4739", "date": "2017-09-07", "market": "TPEx", "close": "115"},
            {"ticker": "4739", "date": "2017-09-08", "market": "TWSE", "close": "122"},
            {"ticker": "4739", "date": "2017-09-11", "market": "TWSE", "close": "123"},
            {"ticker": "4739", "date": "2017-09-12", "market": "TPEx", "close": "999"},
        ]
        patch, missing, boundary = build_4739_patch({"2017-09-11", "2017-09-12"}, rows)

        self.assertEqual([(row["date"], row["close"]) for row in patch], [("2017-09-11", "123")])
        self.assertEqual([row["date"] for row in missing], ["2017-09-12"])
        self.assertEqual([(row["date"], row["market"]) for row in boundary], [
            ("2017-09-07", "TPEx"), ("2017-09-08", "TWSE")
        ])

    def test_write_csv_supports_plain_and_gzip_outputs(self) -> None:
        with TemporaryDirectory() as temp:
            for name in ("rows.csv", "rows.csv.gz"):
                path = Path(temp) / name
                write_csv(path, [{"ticker": "4739", "close": "123"}])
                self.assertEqual(read_csv(path), [{"ticker": "4739", "close": "123"}])


if __name__ == "__main__":
    unittest.main()
