from __future__ import annotations

import csv
import json
import tempfile
import unittest
from pathlib import Path

from rotation_radar.formal_sources.point_in_time_revenue import (
    build_point_in_time_revenue_dataset,
    conservative_available_date_for_period,
    count_future_data_violations,
    parse_mops_revenue_html,
    periods_needed_for_snapshot_window,
    validate_point_in_time_revenue,
)


class PointInTimeRevenueTests(unittest.TestCase):
    def test_periods_include_prior_revenue_needed_for_first_snapshot(self) -> None:
        periods = periods_needed_for_snapshot_window(_date("2021-12-01"), _date("2023-12-31"))

        self.assertEqual(periods[0], "2021-10")
        self.assertEqual(periods[-1], "2023-11")

    def test_parses_mops_monthly_revenue_thousand_twd_as_twd(self) -> None:
        rows = parse_mops_revenue_html(
            html=_sample_mops_html(),
            period="2021-12",
            exchange="TWSE",
            source_url="https://example.test/mops",
            ingested_at="2026-06-07T00:00:00+00:00",
            symbol_lookup={
                "2330": _symbol("2330", "台積電", "TWSE"),
                "1815": _symbol("1815", "富喬", "TPEx"),
            },
        )

        self.assertEqual(len(rows), 1)
        self.assertEqual(rows[0]["symbol"], "2330")
        self.assertEqual(rows[0]["metric_name"], "monthly_revenue")
        self.assertEqual(rows[0]["metric_value"], "155382230000")
        self.assertEqual(rows[0]["available_date"], "2022-01-10")

    def test_available_date_is_after_period_end_and_weekend_adjusted(self) -> None:
        self.assertEqual(conservative_available_date_for_period("2021-12").isoformat(), "2022-01-10")
        self.assertEqual(conservative_available_date_for_period("2022-08").isoformat(), "2022-09-12")

    def test_future_data_violation_detects_same_month_availability(self) -> None:
        rows = [
            {
                "symbol": "2330",
                "period": "2021-12",
                "available_date": "2021-12-31",
            }
        ]

        self.assertEqual(count_future_data_violations(rows), 1)

    def test_builds_dataset_and_readiness_from_fake_sources(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            formal = root / "formal_universe.csv"
            market = root / "market_universe.csv"
            _write_csv(
                formal,
                ["symbol", "name"],
                [{"symbol": "2330", "name": "台積電"}, {"symbol": "1815", "name": "富喬"}],
            )
            _write_csv(
                market,
                ["market", "symbol", "name"],
                [{"market": "TWSE", "symbol": "2330", "name": "台積電"}, {"market": "TPEx", "symbol": "1815", "name": "富喬"}],
            )

            result = build_point_in_time_revenue_dataset(
                formal_universe_path=formal,
                market_universe_path=market,
                output_path=root / "revenue.csv",
                gap_report_path=root / "gap.csv",
                readiness_output_path=root / "ready.json",
                start_date="2021-12-01",
                end_date="2021-12-31",
                fetcher=_fake_fetcher,
                raw_cache_dir=None,
                sleep_seconds=0,
            )

            self.assertTrue(result.readiness["ready"])
            self.assertEqual(result.readiness["monthly_revenue_row_count"], 4)
            self.assertEqual(result.readiness["coverage_ratio"], 1.0)
            self.assertEqual(result.readiness["future_data_violation_count"], 0)
            with result.revenue_path.open(encoding="utf-8-sig", newline="") as handle:
                rows = list(csv.DictReader(handle))
            self.assertEqual({row["metric_value"] for row in rows}, {"155382230000", "12000000"})

    def test_validator_recomputes_readiness_without_network(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            formal = root / "formal_universe.csv"
            market = root / "market_universe.csv"
            revenue = root / "revenue.csv"
            readiness = root / "ready.json"
            _write_csv(formal, ["symbol", "name"], [{"symbol": "2330", "name": "台積電"}])
            _write_csv(market, ["market", "symbol", "name"], [{"market": "TWSE", "symbol": "2330", "name": "台積電"}])
            _write_csv(
                revenue,
                [
                    "symbol",
                    "name",
                    "metric_name",
                    "metric_value",
                    "period",
                    "announcement_date",
                    "available_date",
                    "source_type",
                    "source_url",
                    "ingested_at",
                ],
                [
                    _revenue_row("2330", "台積電", "2021-10"),
                    _revenue_row("2330", "台積電", "2021-11"),
                ],
            )

            payload = validate_point_in_time_revenue(
                revenue_file=revenue,
                formal_universe_path=formal,
                market_universe_path=market,
                start_date="2021-12-01",
                end_date="2021-12-31",
                output_path=readiness,
            )

            self.assertTrue(payload["ready"])
            self.assertEqual(json.loads(readiness.read_text(encoding="utf-8"))["source_mode"], "point_in_time_limited")


def _fake_fetcher(url: str) -> str:
    if "/sii/" in url:
        return _sample_mops_html(symbol="2330", name="台積電", revenue="155,382,230")
    return _sample_mops_html(symbol="1815", name="富喬", revenue="12,000")


def _sample_mops_html(symbol: str = "2330", name: str = "台積電", revenue: str = "155,382,230") -> str:
    return f"""
    <html><body>
    <font size='5'><b>上市公司110年12月份(累計與當月)營業收入統計表</b></font>
    <table>
      <tr><th>公司代號</th><th>公司名稱</th><th>當月營收</th><th>上月營收</th><th>去年當月營收</th></tr>
      <tr><td>{symbol}</td><td>{name}</td><td>{revenue}</td><td>1</td><td>1</td></tr>
      <tr><td>合計</td><td></td><td>0</td><td>0</td><td>0</td></tr>
    </table>
    </body></html>
    """


def _symbol(symbol: str, name: str, exchange: str):
    from rotation_radar.formal_sources.point_in_time_revenue import FormalSymbol

    return FormalSymbol(symbol=symbol, name=name, exchange=exchange)


def _revenue_row(symbol: str, name: str, period: str) -> dict[str, str]:
    available = conservative_available_date_for_period(period).isoformat()
    return {
        "symbol": symbol,
        "name": name,
        "metric_name": "monthly_revenue",
        "metric_value": "1000",
        "period": period,
        "announcement_date": available,
        "available_date": available,
        "source_type": "mops_monthly_revenue_static_html_conservative_available_date",
        "source_url": "https://example.test/mops",
        "ingested_at": "2026-06-07T00:00:00+00:00",
    }


def _write_csv(path: Path, fieldnames: list[str], rows: list[dict[str, str]]) -> None:
    with path.open("w", encoding="utf-8-sig", newline="") as handle:
        writer = csv.DictWriter(handle, fieldnames=fieldnames)
        writer.writeheader()
        writer.writerows(rows)


def _date(value: str):
    from datetime import datetime

    return datetime.strptime(value, "%Y-%m-%d").date()
