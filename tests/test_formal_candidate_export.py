from __future__ import annotations

import csv
import tempfile
import unittest
from pathlib import Path

from rotation_radar.formal_candidate_export import write_formal_radar_candidates
from rotation_radar.models import StockMetrics


class FormalCandidateExportTests(unittest.TestCase):
    def test_exports_actionable_candidates_as_selected_pool(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            path = Path(tmp) / "formal_radar_candidates.latest.csv"
            written = write_formal_radar_candidates(
                stocks=[
                    _stock("1111", "分類一", pullback=85, chip=80, technical=100, liquidity=100, risk_heat=45),
                    _stock("2222", "分類二", pullback=70, chip=56, technical=78, liquidity=100, risk_heat=53),
                ],
                output_path=path,
                report_date="2026-06-12",
            )

            rows = _read_csv(written)

        self.assertEqual(rows[0]["symbol"], "1111")
        self.assertEqual(rows[0]["bucket_key"], "actionable")
        self.assertEqual(rows[0]["selected_for_backtest_pool"], "true")
        self.assertEqual(rows[1]["selected_for_backtest_pool"], "false")
        self.assertEqual(rows[0]["report_date"], "2026-06-12")

    def test_falls_back_to_top_three_watch_candidates(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            path = Path(tmp) / "formal_radar_candidates.latest.csv"
            written = write_formal_radar_candidates(
                stocks=[
                    _stock("2368", "金像電", pullback=70, chip=56, technical=78, liquidity=100, risk_heat=53),
                    _stock("2408", "南亞科", pullback=69, chip=56, technical=78, liquidity=100, risk_heat=53),
                    _stock("3037", "欣興", pullback=68, chip=56, technical=78, liquidity=100, risk_heat=53),
                    _stock("9999", "排除", pullback=20, chip=20, technical=20, liquidity=20, risk_heat=90),
                ],
                output_path=path,
                report_date="2026-06-12",
            )

            rows = _read_csv(written)

        selected = [row for row in rows if row["selected_for_backtest_pool"] == "true"]
        self.assertEqual([row["symbol"] for row in selected], ["2368", "2408", "3037"])
        self.assertTrue(all(row["bucket_key"] == "watch" for row in selected))


def _stock(
    symbol: str,
    name: str,
    *,
    pullback: float,
    chip: float,
    technical: float,
    liquidity: float,
    risk_heat: float,
) -> StockMetrics:
    return StockMetrics(
        symbol=symbol,
        name=name,
        sector="記憶體",
        close=100,
        pullback_quality=pullback,
        chip_cleanliness=chip,
        foreign_5d=0,
        trust_5d=0,
        margin_change_5d=0,
        pe=0,
        sector_pe_low=0,
        sector_pe_avg=0,
        sector_pe_high=0,
        revenue_yoy=0,
        revenue_mom=0,
        technical_setup=technical,
        liquidity=liquidity,
        risk_heat=risk_heat,
        thesis="",
        risk_reason="",
    )


def _read_csv(path: Path) -> list[dict[str, str]]:
    with path.open("r", encoding="utf-8-sig", newline="") as handle:
        return list(csv.DictReader(handle))


if __name__ == "__main__":
    unittest.main()
