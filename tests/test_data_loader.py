from __future__ import annotations

import csv
import tempfile
import unittest
from pathlib import Path

from rotation_radar.data_loader import DataFormatError, load_dataset, load_sector_metrics


SECTOR_FIELDS = (
    "name",
    "theme",
    "capital_inflow_rank",
    "turnover_share_change",
    "momentum_20d",
    "strong_stock_ratio",
    "industry_trend",
    "overseas_signal",
    "pe_percentile",
    "risk_heat",
    "catalysts",
    "risks",
)

STOCK_FIELDS = (
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
    "revenue_yoy",
    "revenue_mom",
    "technical_setup",
    "liquidity",
    "risk_heat",
    "thesis",
    "risk_reason",
)


class DataLoaderTests(unittest.TestCase):
    def test_sector_metrics_require_expected_columns(self) -> None:
        with tempfile.TemporaryDirectory() as temp_dir:
            path = Path(temp_dir) / "sector_metrics.csv"
            _write_csv(path, ("name", "theme"), [{"name": "記憶體", "theme": "測試"}])

            with self.assertRaisesRegex(DataFormatError, "missing columns"):
                load_sector_metrics(path)

    def test_sector_metrics_reject_invalid_numeric_values(self) -> None:
        with tempfile.TemporaryDirectory() as temp_dir:
            path = Path(temp_dir) / "sector_metrics.csv"
            row = _sector_row()
            row["capital_inflow_rank"] = "not-a-number"
            _write_csv(path, SECTOR_FIELDS, [row])

            with self.assertRaisesRegex(DataFormatError, "Invalid numeric value"):
                load_sector_metrics(path)

    def test_dataset_rejects_stock_sector_not_in_sector_metrics(self) -> None:
        with tempfile.TemporaryDirectory() as temp_dir:
            root = Path(temp_dir)
            _write_csv(root / "sector_metrics.csv", SECTOR_FIELDS, [_sector_row(name="記憶體")])
            _write_csv(root / "stock_metrics.csv", STOCK_FIELDS, [_stock_row(sector="不存在題材")])

            with self.assertRaisesRegex(DataFormatError, "unknown sectors"):
                load_dataset(root)


def _write_csv(path: Path, fieldnames: tuple[str, ...], rows: list[dict[str, str]]) -> None:
    with path.open("w", encoding="utf-8-sig", newline="") as handle:
        writer = csv.DictWriter(handle, fieldnames=fieldnames)
        writer.writeheader()
        writer.writerows(rows)


def _sector_row(name: str = "記憶體") -> dict[str, str]:
    return {
        "name": name,
        "theme": "測試題材",
        "capital_inflow_rank": "90",
        "turnover_share_change": "80",
        "momentum_20d": "70",
        "strong_stock_ratio": "60",
        "industry_trend": "80",
        "overseas_signal": "75",
        "pe_percentile": "45",
        "risk_heat": "55",
        "catalysts": "測試",
        "risks": "測試",
    }


def _stock_row(sector: str = "記憶體") -> dict[str, str]:
    return {
        "symbol": "2408",
        "name": "測試股",
        "sector": sector,
        "close": "100",
        "pullback_quality": "70",
        "chip_cleanliness": "70",
        "foreign_5d": "0",
        "trust_5d": "0",
        "margin_change_5d": "0",
        "pe": "20",
        "sector_pe_low": "15",
        "sector_pe_avg": "25",
        "sector_pe_high": "35",
        "revenue_yoy": "0",
        "revenue_mom": "0",
        "technical_setup": "70",
        "liquidity": "70",
        "risk_heat": "50",
        "thesis": "測試",
        "risk_reason": "測試",
    }


if __name__ == "__main__":
    unittest.main()
