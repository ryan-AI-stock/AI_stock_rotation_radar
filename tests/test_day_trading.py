from __future__ import annotations

import csv
import tempfile
import unittest
from datetime import date
from pathlib import Path

from rotation_radar.formal_sources.chip_flow_overlay import TARGET_UNIVERSE
from rotation_radar.formal_sources.day_trading import (
    DAY_TRADING_FIELDS,
    build_day_trading_dataset,
    parse_twse_day_trading_payload,
    parse_twse_stock_day_volumes,
    validate_day_trading_dataset,
)


class DayTradingTests(unittest.TestCase):
    def test_parses_twse_day_trading_target_rows_with_stock_day_denominator(self) -> None:
        rows = parse_twse_day_trading_payload(
            payload=_day_payload([["2330", "台積電", "", "20,000", "1,000,000", "1,001,000"]]),
            trade_date=date(2021, 12, 1),
            source_url="https://example.test/day",
            volume_by_symbol={"2330": 100000},
        )

        self.assertEqual(len(rows), 1)
        self.assertEqual(rows[0]["symbol"], "2330")
        self.assertEqual(rows[0]["day_trading_total_volume"], "20000")
        self.assertEqual(rows[0]["total_trading_volume"], "100000")
        self.assertEqual(rows[0]["day_trading_volume_ratio"], "20.0000")
        self.assertEqual(rows[0]["day_trading_buy_volume"], "")
        self.assertEqual(rows[0]["day_trading_sell_volume"], "")

    def test_parses_stock_day_total_volume(self) -> None:
        rows = parse_twse_stock_day_volumes(
            payload={"stat": "OK", "fields": ["日期", "成交股數", "成交金額"], "data": [["110/12/01", "100,000", "1,000"]]},
            symbol="2330",
        )

        self.assertEqual(rows[("2330", "2021-12-01")], 100000)

    def test_builds_ready_package_from_fake_twse_sources(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            dates = root / "turnover.csv"
            _write_csv(
                dates,
                ["symbol", "date", "official_turnover_value", "exchange", "source", "source_url", "ingested_at"],
                [
                    {"symbol": "2308", "date": "2021-12-01", "official_turnover_value": "1", "exchange": "TWSE", "source": "x", "source_url": "u", "ingested_at": "t"},
                    {"symbol": "2308", "date": "2021-12-02", "official_turnover_value": "1", "exchange": "TWSE", "source": "x", "source_url": "u", "ingested_at": "t"},
                    {"symbol": "2308", "date": "2021-12-03", "official_turnover_value": "1", "exchange": "TWSE", "source": "x", "source_url": "u", "ingested_at": "t"},
                    {"symbol": "2308", "date": "2021-12-06", "official_turnover_value": "1", "exchange": "TWSE", "source": "x", "source_url": "u", "ingested_at": "t"},
                    {"symbol": "2308", "date": "2021-12-07", "official_turnover_value": "1", "exchange": "TWSE", "source": "x", "source_url": "u", "ingested_at": "t"},
                ],
            )

            result = build_day_trading_dataset(
                output_path=root / "day.csv",
                gap_report_path=root / "gap.csv",
                readiness_output_path=root / "ready.json",
                trading_dates_source=dates,
                start_date="2021-12-01",
                end_date="2021-12-07",
                raw_day_trading_cache_dir=None,
                raw_volume_cache_dir=None,
                fetcher=_fake_fetcher,
            )

            self.assertTrue(result.readiness["ready"])
            self.assertEqual(result.readiness["source_mode"], "day_trading_ready")
            self.assertEqual(result.readiness["day_trading_row_count"], 45)
            self.assertEqual(result.readiness["coverage_ratio"], 1.0)
            self.assertEqual(result.readiness["stock_coverage_ratio"], 1.0)
            self.assertEqual(_read_header(root / "day.csv"), DAY_TRADING_FIELDS)

    def test_validator_blocks_when_stock_coverage_is_below_threshold(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            dates = root / "turnover.csv"
            day = root / "day.csv"
            _write_csv(
                dates,
                ["symbol", "date", "official_turnover_value", "exchange", "source", "source_url", "ingested_at"],
                [{"symbol": "2308", "date": "2021-12-01", "official_turnover_value": "1", "exchange": "TWSE", "source": "x", "source_url": "u", "ingested_at": "t"}],
            )
            _write_csv(day, DAY_TRADING_FIELDS, [])

            readiness = validate_day_trading_dataset(
                input_path=day,
                gap_report_path=root / "gap.csv",
                readiness_output_path=root / "ready.json",
                trading_dates_source=dates,
                start_date="2021-12-01",
                end_date="2021-12-01",
            )

            self.assertFalse(readiness["ready"])
            self.assertEqual(readiness["source_mode"], "day_trading_blocked")
            self.assertGreater(readiness["stock_gap_count"], 0)


def _fake_fetcher(url: str) -> dict:
    if "STOCK_DAY" in url:
        return {"stat": "OK", "fields": ["日期", "成交股數", "成交金額"], "data": [["110/12/01", "100,000", "1,000"], ["110/12/02", "100,000", "1,000"], ["110/12/03", "100,000", "1,000"], ["110/12/06", "100,000", "1,000"], ["110/12/07", "100,000", "1,000"]]}
    return _day_payload([[symbol, name, "", "20,000", "1,000,000", "1,001,000"] for symbol, _, name in TARGET_UNIVERSE])


def _day_payload(rows: list[list[str]]) -> dict:
    return {
        "stat": "OK",
        "date": "20211201",
        "tables": [
            {
                "title": "110年12月01日 當日沖銷交易標的及成交量值",
                "fields": ["證券代號", "證券名稱", "暫停現股賣出後現款買進當沖註記", "當日沖銷交易成交股數", "當日沖銷交易買進成交金額", "當日沖銷交易賣出成交金額"],
                "data": rows,
            }
        ],
    }


def _write_csv(path: Path, fieldnames: list[str], rows: list[dict[str, str]]) -> None:
    with path.open("w", encoding="utf-8-sig", newline="") as handle:
        writer = csv.DictWriter(handle, fieldnames=fieldnames)
        writer.writeheader()
        writer.writerows(rows)


def _read_header(path: Path) -> list[str]:
    with path.open("r", encoding="utf-8-sig", newline="") as handle:
        return next(csv.reader(handle))
