from __future__ import annotations

import unittest

from r1.investing_target_prices import _reusable_consensus, parse_ratings, resolve_equity_path


class InvestingTargetPriceTests(unittest.TestCase):
    def test_resolves_exact_taiwan_ticker(self) -> None:
        html = """
        <a class="js-inner-all-results-quote-item row" href="/equities/not-it">
          <span class="second">ABC</span></a>
        <a class="js-inner-all-results-quote-item row" href="/equities/delta-electron">
          <span class="second">2308</span></a>
        """
        self.assertEqual(resolve_equity_path(html, ticker="2308"), "/equities/delta-electron")

    def test_parses_identifiable_target_rows(self) -> None:
        html = """
        <table><tbody><tr>
          <td><div>Nomura/Instinet</div></td><td></td><td>買入</td>
          <td>2,650.00</td><td>+34.86%</td><td>2,800.00</td><td>維持</td>
          <td>2026年07月31日</td>
        </tr></tbody></table>
        """
        rows = parse_ratings(
            html, ticker="2308", source_url="https://example.test", retrieved_at="2026-10-12",
        )
        self.assertEqual(len(rows), 1)
        self.assertEqual(rows[0]["institution"], "Nomura/Instinet")
        self.assertEqual(rows[0]["target_price"], "2650")
        self.assertEqual(rows[0]["available_at"], "2026-07-31")

    def test_irrelevant_tables_do_not_create_target_rows(self) -> None:
        html = "<table><tbody><tr><td>Revenue</td><td>1</td><td>2</td><td>not-price</td>" \
               "<td>5</td><td>6</td><td>7</td><td>2026年07月31日</td></tr></tbody></table>"
        self.assertEqual(parse_ratings(
            html, ticker="2308", source_url="https://example.test", retrieved_at="2026-10-12",
        ), [])

    def test_reuses_three_recent_institutions_to_preserve_request_capacity(self) -> None:
        rows = [{
            "ticker": "2308", "institution": institution, "target_price": "2500",
            "available_at": "2026-10-01", "retrieved_at": "2026-10-10",
        } for institution in ("A", "B", "C")]
        self.assertTrue(_reusable_consensus(
            rows, ticker="2308", retrieved_at="2026-10-17",
        ))
        self.assertFalse(_reusable_consensus(
            rows, ticker="2308", retrieved_at="2026-11-08",
        ))


if __name__ == "__main__":
    unittest.main()
