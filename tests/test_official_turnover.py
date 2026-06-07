from __future__ import annotations

import csv
import json
import tempfile
import unittest
from pathlib import Path

from rotation_radar.formal_sources.official_turnover import (
    build_official_turnover_dataset,
    parse_month_payload,
    validate_official_turnover,
)


class OfficialTurnoverTests(unittest.TestCase):
    def test_parses_twse_turnover_as_twd(self) -> None:
        rows = parse_month_payload(
            payload={
                "stat": "OK",
                "fields": ["日期", "成交股數", "成交金額"],
                "data": [["110/12/01", "30,119,408", "18,021,861,252"]],
            },
            exchange="TWSE",
            symbol="2330",
            source_url="https://example.test/twse",
            ingested_at="2026-06-07T00:00:00+00:00",
            start=_date("2021-12-01"),
            end=_date("2021-12-31"),
        )

        self.assertEqual(rows[0]["official_turnover_value"], "18021861252")
        self.assertEqual(rows[0]["source"], "twse_stock_day")

    def test_parses_tpex_turnover_thousand_ntd_as_twd(self) -> None:
        rows = parse_month_payload(
            payload={
                "stat": "ok",
                "tables": [
                    {
                        "fields": ["日 期", "成交仟股", "成交仟元"],
                        "data": [["110/12/01", "1,434", "24,302"]],
                    }
                ],
            },
            exchange="TPEx",
            symbol="1815",
            source_url="https://example.test/tpex",
            ingested_at="2026-06-07T00:00:00+00:00",
            start=_date("2021-12-01"),
            end=_date("2021-12-31"),
        )

        self.assertEqual(rows[0]["official_turnover_value"], "24302000")
        self.assertEqual(rows[0]["source"], "tpex_trading_stock")

    def test_builds_dataset_and_readiness_from_fake_sources(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            formal = root / "formal_universe.csv"
            market = root / "market_universe.csv"
            _write_csv(formal, ["symbol", "name"], [{"symbol": "2330", "name": "台積電"}, {"symbol": "1815", "name": "富喬"}])
            _write_csv(market, ["market", "symbol", "name"], [{"market": "TWSE", "symbol": "2330", "name": "台積電"}, {"market": "TPEx", "symbol": "1815", "name": "富喬"}])

            result = build_official_turnover_dataset(
                formal_universe_path=formal,
                market_universe_path=market,
                output_path=root / "official.csv",
                gap_report_path=root / "gap.csv",
                readiness_output_path=root / "ready.json",
                start_date="2021-12-01",
                end_date="2021-12-02",
                fetcher=_fake_fetcher,
                raw_cache_dir=None,
            )

            self.assertTrue(result.readiness["ready"])
            self.assertEqual(result.readiness["official_turnover_row_count"], 4)
            self.assertEqual(result.readiness["coverage_ratio"], 1.0)
            with result.turnover_path.open(encoding="utf-8-sig", newline="") as handle:
                rows = list(csv.DictReader(handle))
            self.assertEqual({row["source"] for row in rows}, {"twse_stock_day", "tpex_trading_stock"})

    def test_validator_recomputes_readiness_without_network(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            formal = root / "formal_universe.csv"
            market = root / "market_universe.csv"
            turnover = root / "official.csv"
            readiness = root / "ready.json"
            _write_csv(
                formal,
                ["symbol", "name"],
                [{"symbol": "2330", "name": "台積電"}],
            )
            _write_csv(
                market,
                ["market", "symbol", "name"],
                [{"market": "TWSE", "symbol": "2330", "name": "台積電"}],
            )
            _write_csv(
                turnover,
                ["symbol", "date", "official_turnover_value", "exchange", "source", "source_url", "ingested_at"],
                [
                    {
                        "symbol": "2330",
                        "date": "2021-12-01",
                        "official_turnover_value": "18021861252",
                        "exchange": "TWSE",
                        "source": "twse_stock_day",
                        "source_url": "https://example.test/twse",
                        "ingested_at": "2026-06-07T00:00:00+00:00",
                    }
                ],
            )

            payload = validate_official_turnover(
                turnover_file=turnover,
                formal_universe_path=formal,
                market_universe_path=market,
                start_date="2021-12-01",
                end_date="2021-12-01",
                output_path=readiness,
            )

            self.assertTrue(payload["ready"])
            self.assertEqual(json.loads(readiness.read_text(encoding="utf-8"))["source_mode"], "official_exchange_turnover")

    def test_readiness_allows_partial_source_with_gap_report_above_threshold(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            formal = root / "formal_universe.csv"
            market = root / "market_universe.csv"
            turnover = root / "official.csv"
            readiness = root / "ready.json"
            gap = root / "gap.csv"
            _write_csv(formal, ["symbol", "name"], [{"symbol": "2330", "name": "台積電"}])
            _write_csv(market, ["market", "symbol", "name"], [{"market": "TWSE", "symbol": "2330", "name": "台積電"}])
            rows = []
            from datetime import date, timedelta

            current = date(2021, 12, 1)
            while current <= date(2022, 3, 31):
                for symbol in ("2330", "2303"):
                    if symbol == "2330" and current.isoformat() == "2022-03-31":
                        continue
                    rows.append(
                        {
                            "symbol": symbol,
                            "date": current.isoformat(),
                            "official_turnover_value": "1000",
                            "exchange": "TWSE",
                            "source": "twse_stock_day",
                            "source_url": "https://example.test/twse",
                            "ingested_at": "2026-06-07T00:00:00+00:00",
                        }
                    )
                current += timedelta(days=1)
            _write_csv(
                turnover,
                ["symbol", "date", "official_turnover_value", "exchange", "source", "source_url", "ingested_at"],
                rows,
            )

            payload = validate_official_turnover(
                turnover_file=turnover,
                formal_universe_path=formal,
                market_universe_path=market,
                start_date="2021-12-01",
                end_date="2022-03-31",
                output_path=readiness,
                gap_report_path=gap,
            )

            self.assertTrue(payload["ready"])
            self.assertEqual(payload["source_mode"], "official_partial_with_gap_report")
            self.assertEqual(payload["missing_official_turnover_on_exchange_trading_day_count"], 1)
            self.assertEqual(payload["blocking_issues"], [])


def _fake_fetcher(url: str) -> dict:
    if "twse" in url:
        return {
            "stat": "OK",
            "fields": ["日期", "成交股數", "成交金額"],
            "data": [
                ["110/12/01", "1", "10,000"],
                ["110/12/02", "1", "20,000"],
            ],
        }
    return {
        "stat": "ok",
        "tables": [
            {
                "fields": ["日 期", "成交仟股", "成交仟元"],
                "data": [
                    ["110/12/01", "1", "30"],
                    ["110/12/02", "1", "40"],
                ],
            }
        ],
    }


def _write_csv(path: Path, fieldnames: list[str], rows: list[dict[str, str]]) -> None:
    with path.open("w", encoding="utf-8-sig", newline="") as handle:
        writer = csv.DictWriter(handle, fieldnames=fieldnames)
        writer.writeheader()
        writer.writerows(rows)


def _date(value: str):
    from datetime import datetime

    return datetime.strptime(value, "%Y-%m-%d").date()
