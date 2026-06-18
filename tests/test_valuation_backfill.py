from __future__ import annotations

import csv
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

from rotation_radar.valuation_backfill import backfill_stock_valuations


class ValuationBackfillTests(unittest.TestCase):
    def test_backfills_missing_pe_and_sector_range(self) -> None:
        with tempfile.TemporaryDirectory() as temp_dir:
            root = Path(temp_dir)
            stock_metrics = root / "stock_metrics.csv"
            market_quotes = root / "theme_quotes.csv"
            output = root / "output.csv"
            _write_csv(
                stock_metrics,
                _stock_fields(),
                [
                    _stock_row("2408", "南亞科", pe="39.1", close="437"),
                    _stock_row("3006", "晶豪科", pe="0", close="225"),
                ],
            )
            _write_csv(
                market_quotes,
                ("symbol", "market"),
                [
                    {"symbol": "2408", "market": "TWSE"},
                    {"symbol": "3006", "market": "TWSE"},
                ],
            )

            with patch(
                "rotation_radar.valuation_backfill.fetch_exchange_pe_ratios",
                return_value={"3006": 18.5},
            ):
                result = backfill_stock_valuations(stock_metrics, market_quotes, output, report_date="2026-06-17")

            rows = {row["symbol"]: row for row in _read_csv(output)}
            self.assertEqual(result.filled_pe_count, 1)
            self.assertEqual(rows["3006"]["pe"], "18.5")
            self.assertEqual(rows["3006"]["sector_pe_low"], "18.5")
            self.assertEqual(rows["3006"]["sector_pe_avg"], "28.8")
            self.assertEqual(rows["3006"]["sector_pe_high"], "39.1")
            self.assertNotIn("本益比、法人籌碼", rows["3006"]["risk_reason"])
            self.assertNotEqual(rows["3006"]["fair_value_avg"], "0")

    def test_keeps_missing_pe_when_exchange_has_no_value(self) -> None:
        with tempfile.TemporaryDirectory() as temp_dir:
            root = Path(temp_dir)
            stock_metrics = root / "stock_metrics.csv"
            market_quotes = root / "theme_quotes.csv"
            output = root / "output.csv"
            _write_csv(stock_metrics, _stock_fields(), [_stock_row("3006", "晶豪科", pe="0", close="225")])
            _write_csv(market_quotes, ("symbol", "market"), [{"symbol": "3006", "market": "TWSE"}])

            with patch("rotation_radar.valuation_backfill.fetch_exchange_pe_ratios", return_value={}):
                result = backfill_stock_valuations(stock_metrics, market_quotes, output, report_date="2026-06-17")

            rows = {row["symbol"]: row for row in _read_csv(output)}
            self.assertEqual(result.filled_pe_count, 0)
            self.assertEqual(result.missing_pe_symbols, ("3006",))
            self.assertEqual(rows["3006"]["pe"], "0")


def _write_csv(path: Path, fieldnames, rows: list[dict[str, str]]) -> None:
    with path.open("w", encoding="utf-8-sig", newline="") as handle:
        writer = csv.DictWriter(handle, fieldnames=fieldnames)
        writer.writeheader()
        writer.writerows(rows)


def _read_csv(path: Path) -> list[dict[str, str]]:
    with path.open("r", encoding="utf-8-sig", newline="") as handle:
        return [dict(row) for row in csv.DictReader(handle)]


def _stock_fields() -> tuple[str, ...]:
    return (
        "symbol",
        "name",
        "sector",
        "close",
        "pullback_quality",
        "chip_cleanliness",
        "foreign_5d",
        "trust_5d",
        "margin_change_5d",
        "pe",
        "sector_pe_low",
        "sector_pe_avg",
        "sector_pe_high",
        "fair_value_low",
        "fair_value_avg",
        "fair_value_high",
        "revenue_yoy",
        "revenue_mom",
        "technical_setup",
        "liquidity",
        "risk_heat",
        "thesis",
        "risk_reason",
    )


def _stock_row(symbol: str, name: str, *, pe: str, close: str) -> dict[str, str]:
    return {
        "symbol": symbol,
        "name": name,
        "sector": "記憶體",
        "close": close,
        "pullback_quality": "70",
        "chip_cleanliness": "50",
        "foreign_5d": "0",
        "trust_5d": "0",
        "margin_change_5d": "0",
        "pe": pe,
        "sector_pe_low": "0",
        "sector_pe_avg": "0",
        "sector_pe_high": "0",
        "fair_value_low": "0",
        "fair_value_avg": "0",
        "fair_value_high": "0",
        "revenue_yoy": "0",
        "revenue_mom": "0",
        "technical_setup": "70",
        "liquidity": "80",
        "risk_heat": "50",
        "thesis": "測試",
        "risk_reason": "本益比、法人籌碼與融資資料尚未接入全市場資料源，先列為初篩候選。",
    }


if __name__ == "__main__":
    unittest.main()
