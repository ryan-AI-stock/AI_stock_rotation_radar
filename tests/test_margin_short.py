from __future__ import annotations

import csv
import tempfile
import unittest
from datetime import date
from pathlib import Path

from rotation_radar.formal_sources.chip_flow_overlay import TARGET_UNIVERSE
from rotation_radar.formal_sources.margin_short import (
    MARGIN_SHORT_FIELDS,
    build_margin_short_dataset,
    parse_twse_margin_csv,
    validate_margin_short_dataset,
)


class MarginShortTests(unittest.TestCase):
    def test_parses_twse_margin_target_rows(self) -> None:
        rows = parse_twse_margin_csv(
            payload=_csv_payload(
                [
                    {
                        "股票代號": "2330",
                        "股票名稱": "台積電",
                        "融資買進": "10",
                        "融資賣出": "4",
                        "融資現金償還": "",
                        "融資前日餘額": "100",
                        "融資今日餘額": "106",
                        "融資限額": "1,000",
                        "融券買進": "2",
                        "融券賣出": "5",
                        "融券現券償還": "1",
                        "融券前日餘額": "20",
                        "融券今日餘額": "22",
                        "融券限額": "1,000",
                        "資券互抵": "",
                        "註記": "",
                    },
                    _row("9999", "非目標"),
                ]
            ),
            trade_date=date(2021, 12, 1),
            source_url="https://example.test/margin",
        )

        self.assertEqual(len(rows), 1)
        self.assertEqual(rows[0]["symbol"], "2330")
        self.assertEqual(rows[0]["margin_balance_change"], "6")
        self.assertEqual(rows[0]["short_cover"], "3")
        self.assertEqual(rows[0]["short_balance_change"], "2")
        self.assertEqual(rows[0]["securities_lending_balance"], "")
        self.assertEqual(rows[0]["data_quality_status"], "official_twse_mi_margn_margin_short_lending_unavailable")

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
                    {"symbol": "2308", "date": "2021-12-08", "official_turnover_value": "1", "exchange": "TWSE", "source": "x", "source_url": "u", "ingested_at": "t"},
                ],
            )

            result = build_margin_short_dataset(
                output_path=root / "margin.csv",
                gap_report_path=root / "gap.csv",
                readiness_output_path=root / "ready.json",
                trading_dates_source=dates,
                start_date="2021-12-01",
                end_date="2021-12-08",
                raw_cache_dir=None,
                fetcher=_fake_fetcher,
            )

            self.assertTrue(result.readiness["ready"])
            self.assertEqual(result.readiness["source_mode"], "margin_short_ready")
            self.assertEqual(result.readiness["margin_short_row_count"], 54)
            self.assertEqual(result.readiness["coverage_ratio"], 1.0)
            self.assertEqual(result.readiness["stock_coverage_ratio"], 1.0)
            self.assertEqual(_read_header(root / "margin.csv"), MARGIN_SHORT_FIELDS)
            rows = _read_rows(root / "margin.csv")
            self.assertTrue(any(row["margin_balance_5d_change_pct"] for row in rows))

    def test_validator_blocks_when_stock_coverage_is_below_threshold(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            dates = root / "turnover.csv"
            margin = root / "margin.csv"
            _write_csv(
                dates,
                ["symbol", "date", "official_turnover_value", "exchange", "source", "source_url", "ingested_at"],
                [{"symbol": "2308", "date": "2021-12-01", "official_turnover_value": "1", "exchange": "TWSE", "source": "x", "source_url": "u", "ingested_at": "t"}],
            )
            _write_csv(margin, MARGIN_SHORT_FIELDS, [])

            readiness = validate_margin_short_dataset(
                input_path=margin,
                gap_report_path=root / "gap.csv",
                readiness_output_path=root / "ready.json",
                trading_dates_source=dates,
                start_date="2021-12-01",
                end_date="2021-12-01",
            )

            self.assertFalse(readiness["ready"])
            self.assertEqual(readiness["source_mode"], "margin_short_blocked")
            self.assertGreater(readiness["stock_gap_count"], 0)


def _fake_fetcher(url: str) -> str:
    return _csv_payload([_row(symbol, name) for symbol, _, name in TARGET_UNIVERSE])


def _row(symbol: str, name: str) -> dict[str, str]:
    return {
        "股票代號": symbol,
        "股票名稱": name,
        "融資買進": "10",
        "融資賣出": "4",
        "融資現金償還": "",
        "融資前日餘額": "100",
        "融資今日餘額": "106",
        "融資限額": "1000",
        "融券買進": "2",
        "融券賣出": "5",
        "融券現券償還": "1",
        "融券前日餘額": "20",
        "融券今日餘額": "22",
        "融券限額": "1000",
        "資券互抵": "",
        "註記": "",
    }


def _csv_payload(rows: list[dict[str, str]]) -> str:
    with tempfile.NamedTemporaryFile("w+", encoding="utf-8-sig", newline="", delete=False) as handle:
        writer = csv.DictWriter(handle, fieldnames=list(_row("0", "x").keys()))
        writer.writeheader()
        writer.writerows(rows)
        handle.seek(0)
        return handle.read()


def _write_csv(path: Path, fieldnames: list[str], rows: list[dict[str, str]]) -> None:
    with path.open("w", encoding="utf-8-sig", newline="") as handle:
        writer = csv.DictWriter(handle, fieldnames=fieldnames)
        writer.writeheader()
        writer.writerows(rows)


def _read_header(path: Path) -> list[str]:
    with path.open("r", encoding="utf-8-sig", newline="") as handle:
        return next(csv.reader(handle))


def _read_rows(path: Path) -> list[dict[str, str]]:
    with path.open("r", encoding="utf-8-sig", newline="") as handle:
        return list(csv.DictReader(handle))
