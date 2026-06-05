from __future__ import annotations

import csv
import tempfile
import unittest
from pathlib import Path

from rotation_radar.data_loader import load_sector_metrics
from rotation_radar.scoring import build_results, select_top_sector_names
from rotation_radar.stock_screener import build_market_stock_candidates, export_hot_sector_symbols


SECTOR_FIELDS = (
    "name",
    "theme",
    "capital_inflow_rank",
    "turnover_share_change",
    "capital_share",
    "capital_share_prev",
    "turnover_value",
    "turnover_value_prev",
    "momentum_20d",
    "strong_stock_ratio",
    "industry_trend",
    "overseas_signal",
    "pe_percentile",
    "risk_heat",
    "catalysts",
    "risks",
)


class SectorSelectionTests(unittest.TestCase):
    def test_report_and_top_sector_selection_share_final_composite_ranking(self) -> None:
        with tempfile.TemporaryDirectory() as temp_dir:
            sector_path = Path(temp_dir) / "sectors.csv"
            self._write_sectors(sector_path)

            sectors = load_sector_metrics(sector_path)
            report_results, _ = build_results(sectors, [])

            self.assertEqual(
                select_top_sector_names(sectors, limit=3),
                tuple(result.metrics.name for result in report_results[:3]),
            )
            self.assertEqual(select_top_sector_names(sectors, limit=3), ("綜合強勢", "均衡題材", "資金強但高風險"))

    def test_candidate_and_hot_symbol_outputs_use_final_composite_top_sectors(self) -> None:
        with tempfile.TemporaryDirectory() as temp_dir:
            root = Path(temp_dir)
            sector_path = root / "sectors.csv"
            quote_path = root / "quotes.csv"
            hot_path = root / "hot.csv"
            candidate_path = root / "candidates.csv"
            self._write_sectors(sector_path)
            self._write_quotes(quote_path)

            export_hot_sector_symbols(quote_path, sector_path, hot_path)
            build_market_stock_candidates(quote_path, root / "missing-base.csv", sector_path, candidate_path)

            self.assertEqual(self._read_sectors(hot_path), {"綜合強勢", "均衡題材", "資金強但高風險"})
            self.assertEqual(self._read_sectors(candidate_path), {"綜合強勢", "均衡題材", "資金強但高風險"})

    @staticmethod
    def _write_sectors(path: Path) -> None:
        rows = [
            _sector_row("只看資金會入選", 95, 20, 10, 10, 10, 20, 100, 95),
            _sector_row("資金強但高風險", 90, 75, 65, 70, 65, 70, 60, 65),
            _sector_row("均衡題材", 70, 75, 80, 80, 80, 80, 45, 35),
            _sector_row("綜合強勢", 55, 80, 95, 95, 95, 95, 45, 15),
        ]
        with path.open("w", encoding="utf-8-sig", newline="") as handle:
            writer = csv.DictWriter(handle, fieldnames=SECTOR_FIELDS)
            writer.writeheader()
            writer.writerows(rows)

    @staticmethod
    def _write_quotes(path: Path) -> None:
        fieldnames = ("sector", "symbol", "name", "market", "price", "amount_million", "change_pct")
        rows = [
            {
                "sector": sector,
                "symbol": str(index),
                "name": f"股票{index}",
                "market": "TWSE",
                "price": "100",
                "amount_million": "1000",
                "change_pct": "1",
            }
            for index, sector in enumerate(("只看資金會入選", "資金強但高風險", "均衡題材", "綜合強勢"), start=1)
        ]
        with path.open("w", encoding="utf-8-sig", newline="") as handle:
            writer = csv.DictWriter(handle, fieldnames=fieldnames)
            writer.writeheader()
            writer.writerows(rows)

    @staticmethod
    def _read_sectors(path: Path) -> set[str]:
        with path.open("r", encoding="utf-8-sig", newline="") as handle:
            return {row["sector"] for row in csv.DictReader(handle)}


def _sector_row(
    name: str,
    capital: float,
    turnover: float,
    momentum: float,
    strong_ratio: float,
    trend: float,
    overseas: float,
    pe_percentile: float,
    risk_heat: float,
) -> dict[str, str]:
    return {
        "name": name,
        "theme": name,
        "capital_inflow_rank": str(capital),
        "turnover_share_change": str(turnover),
        "capital_share": "10",
        "capital_share_prev": "9",
        "turnover_value": "1000",
        "turnover_value_prev": "900",
        "momentum_20d": str(momentum),
        "strong_stock_ratio": str(strong_ratio),
        "industry_trend": str(trend),
        "overseas_signal": str(overseas),
        "pe_percentile": str(pe_percentile),
        "risk_heat": str(risk_heat),
        "catalysts": "測試",
        "risks": "測試",
    }


if __name__ == "__main__":
    unittest.main()
