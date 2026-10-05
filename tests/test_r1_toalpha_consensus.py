import tempfile
import unittest
from pathlib import Path

from r1.toalpha_consensus import (
    _prune_progress, _upsert_missing, parse_eps_page, parse_estimates_page, required_fiscal_years,
)


HTML = '''<b>2026-10-02</b><span>資料日期</span>
<h2>前瞻估值</h2><tbody>
<tr><td class="txt"><b>2026<!-- -->E</b></td><td><b>10.5</b></td><td>+20%</td><td><b>12</b></td><td>1</td><td>8</td><td>20%</td><td>12.0<!-- --> / <!-- -->8.0</td></tr>
<tr><td class="txt"><b>2027E</b></td><td><b>14.0</b></td><td>+33%</td><td><b>9</b></td><td>1</td><td>6</td><td>30%</td><td>17.0 / 11.0</td></tr>
</tbody>'''

EPS_HTML = '''<b>2026-10-02</b><span>資料日期</span><tbody>
<tr class="fcrow"><td><b>2028</b><small> 預估<!-- --> 2 家</small></td><td><b>49.65</b></td></tr>
</tbody>'''


class ToAlphaConsensusTest(unittest.TestCase):
    def test_current_and_next_year_are_required_but_second_forward_year_is_optional(self):
        self.assertEqual(required_fiscal_years("2026-10-02"), {"2026", "2027"})

    def test_checkpoint_is_pruned_to_current_universe(self):
        progress = _prune_progress({
            "completed": {"2330": {}, "2303": {}},
            "failed": {"2408": {}, "3081": {}},
        }, ["2330", "2408"])
        self.assertEqual(set(progress["completed"]), {"2330"})
        self.assertEqual(set(progress["failed"]), {"2408"})

    def test_parse_labelled_table(self):
        rows = parse_estimates_page(HTML, ticker="2330", retrieved_at="2026-10-04")
        self.assertEqual([(row["fiscal_year"], row["mean_eps"], row["analyst_count"]) for row in rows],
                         [("2026", "10.5", "8"), ("2027", "14.0", "6")])
        self.assertEqual(rows[0]["available_at"], "2026-10-02")

    def test_new_observation_does_not_overwrite_history(self):
        with tempfile.TemporaryDirectory() as folder:
            consensus = Path(folder) / "consensus.csv"
            evidence = Path(folder) / "evidence.csv"
            consensus.write_text(
                "ticker,fiscal_year,mean_eps,median_eps,high_eps,low_eps,analyst_count,source,published_at,available_at,retrieved_at,quality,status\n"
                "2330,2027,99,99,,,2,existing,2026-01-01,2026-01-01,2026-01-01,MEDIUM,READY\n",
                encoding="utf-8",
            )
            progress = {"completed": {"2330": {"url": "https://example", "rows": parse_estimates_page(
                HTML, ticker="2330", retrieved_at="2026-10-04")}}}
            _upsert_missing(progress, consensus, evidence)
            text = consensus.read_text(encoding="utf-8")
            self.assertIn("2330,2027,99", text)
            self.assertIn("2330,2027,14.0", text)
            self.assertIn("2330,2026,10.5", text)

    def test_parse_low_coverage_eps_fallback(self):
        rows = parse_eps_page(EPS_HTML, ticker="2344", retrieved_at="2026-10-04")
        self.assertEqual(rows[0]["fiscal_year"], "2028")
        self.assertEqual(rows[0]["mean_eps"], "49.65")
        self.assertEqual(rows[0]["analyst_count"], "2")


if __name__ == "__main__":
    unittest.main()
