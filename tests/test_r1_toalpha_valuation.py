import unittest

from r1.toalpha_valuation import parse_valuation_page


HTML = '''<span class="kv"><b>2026-10-14</b><span>資料日期</span></span>
<table><tbody><tr><td>本益比</td><td><b>54.5x</b></td><td>range</td><td>73 / 100</td><td>46.3x</td></tr>
<tr><td><b>前瞻本益比(下年度共識 2027)</b><small>現價 ÷ 共識 EPS</small></td>
<td><b>21.2x</b></td><td>23.7x 54.4x</td><td><b>4</b><small> / 100</small></td>
<td>37.9x</td><td>chart</td></tr></tbody></table>'''


class ToAlphaValuationTest(unittest.TestCase):
    def test_parse_labelled_next_year_forward_pe_row(self):
        row = parse_valuation_page(
            HTML, ticker="3661", source_url="https://example", retrieved_at="2026-10-15",
        )
        self.assertEqual(row["data_date"], "2026-10-14")
        self.assertEqual(row["next_year_forward_pe"], "21.2")
        self.assertEqual(row["five_year_percentile"], "0.04")
        self.assertEqual(row["five_year_median_pe"], "37.9")

    def test_missing_label_is_not_inferred(self):
        with self.assertRaisesRegex(ValueError, "next_year_forward_pe_row_missing"):
            parse_valuation_page(
                '<b>2026-10-14</b><span>資料日期</span>', ticker="3661",
                source_url="https://example", retrieved_at="2026-10-15",
            )


if __name__ == "__main__":
    unittest.main()
