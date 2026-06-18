from __future__ import annotations

import csv
import tempfile
import unittest
from pathlib import Path

from rotation_radar.quote_refresh import build_market_quotes_from_processed_prices


class ProcessedQuoteRefreshTests(unittest.TestCase):
    def test_builds_market_quotes_from_processed_twse_and_tpex_prices(self) -> None:
        with tempfile.TemporaryDirectory() as temp_dir:
            root = Path(temp_dir)
            processed = root / "processed" / "20260617"
            processed.mkdir(parents=True)
            sector_map = root / "sector_map.csv"
            output = root / "market_quotes.csv"
            _write_csv(
                sector_map,
                ("sector", "symbol", "name", "role", "overseas_reference", "market"),
                [
                    {"sector": "記憶體", "symbol": "3006", "name": "晶豪科", "role": "", "overseas_reference": "", "market": "TWSE"},
                    {"sector": "記憶體", "symbol": "3227", "name": "原相", "role": "", "overseas_reference": "", "market": "TPEx"},
                ],
            )
            _write_csv(
                processed / "twse_prices_table9.csv",
                ("證券代號", "證券名稱", "成交股數", "成交金額", "開盤價", "最高價", "最低價", "收盤價", "漲跌(+/-)", "漲跌價差"),
                [
                    {
                        "證券代號": "3006",
                        "證券名稱": "晶豪科",
                        "成交股數": "1000000",
                        "成交金額": "225000000",
                        "開盤價": "220",
                        "最高價": "230",
                        "最低價": "218",
                        "收盤價": "225",
                        "漲跌(+/-)": '<p style="color:red">+</p>',
                        "漲跌價差": "5",
                    }
                ],
            )
            _write_csv(
                processed / "tpex_prices_table1.csv",
                ("代號", "名稱", "收盤", "漲跌", "開盤", "最高", "最低", "成交股數", "成交金額(元)"),
                [
                    {
                        "代號": "3227",
                        "名稱": "原相",
                        "收盤": "150",
                        "漲跌": "-2",
                        "開盤": "153",
                        "最高": "154",
                        "最低": "149",
                        "成交股數": "2000000",
                        "成交金額(元)": "300000000",
                    }
                ],
            )

            build_market_quotes_from_processed_prices(
                processed_dir=processed,
                sector_map_path=sector_map,
                output_path=output,
                quote_date="20260617",
            )

            rows = {row["symbol"]: row for row in _read_csv(output)}
            self.assertEqual(rows["3006"]["quote_date"], "20260617")
            self.assertEqual(rows["3006"]["quote_time"], "close")
            self.assertEqual(rows["3006"]["price"], "225")
            self.assertEqual(rows["3006"]["previous_close"], "220")
            self.assertEqual(rows["3006"]["change_pct"], "2.27")
            self.assertEqual(rows["3227"]["previous_close"], "152")
            self.assertEqual(rows["3227"]["change_pct"], "-1.32")


def _write_csv(path: Path, fieldnames, rows: list[dict[str, str]]) -> None:
    with path.open("w", encoding="utf-8-sig", newline="") as handle:
        writer = csv.DictWriter(handle, fieldnames=fieldnames)
        writer.writeheader()
        writer.writerows(rows)


def _read_csv(path: Path) -> list[dict[str, str]]:
    with path.open("r", encoding="utf-8-sig", newline="") as handle:
        return [dict(row) for row in csv.DictReader(handle)]


if __name__ == "__main__":
    unittest.main()
