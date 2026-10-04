import tempfile
import unittest
from pathlib import Path

from r1.toalpha_revision_history import _upsert, latest_rows, parse_revision_panel


class R1ToAlphaRevisionHistoryTest(unittest.TestCase):
    def test_parser_extracts_source_reported_offsets(self):
        text = '''<b>2026-10-02</b><span>資料日期</span><h3><span>2026 EPS預估修正</span><a href="/stock/2330/estimates">more</a></h3>
        <div style="font-size:13px;font-weight:600;margin-bottom:4px">98.35</div>
        <div style="font-size:13px;font-weight:600;margin-bottom:4px">107.27</div>
        <div style="font-size:13px;font-weight:600;margin-bottom:4px">107.64</div>
        <div style="font-size:13px;font-weight:600;margin-bottom:4px">107.82</div>'''
        row = parse_revision_panel(text, ticker="2330")
        self.assertEqual(row["fiscal_year"], "2026")
        self.assertEqual(row["source_data_date"], "2026-10-02")
        self.assertAlmostEqual(float(row["revision_30d"]), 107.82 / 107.64 - 1)
        self.assertAlmostEqual(float(row["revision_90d"]), 107.82 / 98.35 - 1)

    def test_pit_filter_does_not_backdate_90d_value(self):
        with tempfile.TemporaryDirectory() as folder:
            path = Path(folder) / "history.csv"
            row = {
                "ticker": "2330", "fiscal_year": "2026", "source_data_date": "2026-10-02",
                "eps_90d": "98", "eps_60d": "100", "eps_30d": "105", "eps_current": "108",
                "revision_30d": ".028", "revision_90d": ".102", "source_url": "x",
                "available_at": "2026-10-02", "retrieved_at": "2026-10-04",
                "basis": "SOURCE_REPORTED_OFFSETS", "status": "SUPPLEMENTAL_NOT_TOTAL_SCORE",
            }
            _upsert(path, [row])
            self.assertEqual(latest_rows(path, as_of_date="2026-09-01"), {})
            self.assertIn("2330", latest_rows(path, as_of_date="2026-10-02"))
            older = dict(row, source_data_date="2026-09-26", available_at="2026-09-26")
            _upsert(path, [older, row])
            self.assertEqual(len(path.read_text(encoding="utf-8").splitlines()), 3)


if __name__ == "__main__":
    unittest.main()
