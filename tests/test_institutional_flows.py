from __future__ import annotations

import csv
import tempfile
import unittest
from datetime import date
from pathlib import Path

from rotation_radar.formal_sources.institutional_flows import (
    INSTITUTIONAL_FLOW_FIELDS,
    build_institutional_flows_dataset,
    parse_twse_t86_payload,
    validate_institutional_flows_dataset,
)


class InstitutionalFlowsTests(unittest.TestCase):
    def test_parses_twse_t86_target_rows_as_shares_only(self) -> None:
        rows = parse_twse_t86_payload(
            payload=_payload(
                [
                    ["2330", "台積電", "1,000", "300", "700", "0", "0", "0", "10", "2", "8", "5", "5", "0", "5", "0", "0", "0", "713"],
                    ["9999", "非目標", "1", "0", "1", "0", "0", "0", "0", "0", "0", "0", "0", "0", "0", "0", "0", "0", "1"],
                ]
            ),
            trade_date=date(2021, 12, 1),
            source_url="https://example.test/t86",
        )

        self.assertEqual(len(rows), 1)
        self.assertEqual(rows[0]["symbol"], "2330")
        self.assertEqual(rows[0]["foreign_net_buy_shares"], "700")
        self.assertEqual(rows[0]["investment_trust_net_buy_shares"], "8")
        self.assertEqual(rows[0]["dealer_net_buy_shares"], "5")
        self.assertEqual(rows[0]["foreign_net_buy_twd"], "")
        self.assertEqual(rows[0]["data_quality_status"], "official_twse_t86_shares_only_twd_unavailable")

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
                ],
            )

            result = build_institutional_flows_dataset(
                output_path=root / "flows.csv",
                gap_report_path=root / "gap.csv",
                readiness_output_path=root / "ready.json",
                trading_dates_source=dates,
                start_date="2021-12-01",
                end_date="2021-12-02",
                raw_cache_dir=None,
                fetcher=_fake_fetcher,
            )

            self.assertTrue(result.readiness["ready"])
            self.assertEqual(result.readiness["source_mode"], "institutional_flow_ready")
            self.assertEqual(result.readiness["institutional_flow_row_count"], 18)
            self.assertEqual(result.readiness["coverage_ratio"], 1.0)
            self.assertEqual(result.readiness["stock_coverage_ratio"], 1.0)
            self.assertEqual(_read_header(root / "flows.csv"), INSTITUTIONAL_FLOW_FIELDS)

    def test_validator_blocks_when_stock_coverage_is_below_threshold(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            dates = root / "turnover.csv"
            flows = root / "flows.csv"
            _write_csv(
                dates,
                ["symbol", "date", "official_turnover_value", "exchange", "source", "source_url", "ingested_at"],
                [{"symbol": "2308", "date": "2021-12-01", "official_turnover_value": "1", "exchange": "TWSE", "source": "x", "source_url": "u", "ingested_at": "t"}],
            )
            _write_csv(flows, INSTITUTIONAL_FLOW_FIELDS, [])

            readiness = validate_institutional_flows_dataset(
                input_path=flows,
                gap_report_path=root / "gap.csv",
                readiness_output_path=root / "ready.json",
                trading_dates_source=dates,
                start_date="2021-12-01",
                end_date="2021-12-01",
            )

            self.assertFalse(readiness["ready"])
            self.assertEqual(readiness["source_mode"], "institutional_flow_blocked")
            self.assertGreater(readiness["stock_gap_count"], 0)


def _fake_fetcher(url: str) -> dict:
    return _payload(
        [
            [symbol, name, "1,000", "300", "700", "0", "0", "0", "10", "2", "8", "5", "5", "0", "5", "0", "0", "0", "713"]
            for symbol, _, name in [
                ("0050", "0050.TW", "元大台灣50"),
                ("00631L", "00631L.TW", "元大台灣50正2"),
                ("2330", "2330.TW", "台積電"),
                ("2454", "2454.TW", "聯發科"),
                ("2308", "2308.TW", "台達電"),
                ("2317", "2317.TW", "鴻海"),
                ("2382", "2382.TW", "廣達"),
                ("3231", "3231.TW", "緯創"),
                ("6669", "6669.TW", "緯穎"),
            ]
        ]
    )


def _payload(rows: list[list[str]]) -> dict:
    return {
        "stat": "OK",
        "fields": [
            "證券代號",
            "證券名稱",
            "外陸資買進股數(不含外資自營商)",
            "外陸資賣出股數(不含外資自營商)",
            "外陸資買賣超股數(不含外資自營商)",
            "外資自營商買進股數",
            "外資自營商賣出股數",
            "外資自營商買賣超股數",
            "投信買進股數",
            "投信賣出股數",
            "投信買賣超股數",
            "自營商買賣超股數",
            "自營商買進股數(自行買賣)",
            "自營商賣出股數(自行買賣)",
            "自營商買賣超股數(自行買賣)",
            "自營商買進股數(避險)",
            "自營商賣出股數(避險)",
            "自營商買賣超股數(避險)",
            "三大法人買賣超股數",
        ],
        "data": rows,
    }


def _write_csv(path: Path, fieldnames: list[str], rows: list[dict[str, str]]) -> None:
    with path.open("w", encoding="utf-8-sig", newline="") as handle:
        writer = csv.DictWriter(handle, fieldnames=fieldnames)
        writer.writeheader()
        writer.writerows(rows)


def _read_header(path: Path) -> list[str]:
    with path.open("r", encoding="utf-8-sig", newline="") as handle:
        return next(csv.reader(handle))
