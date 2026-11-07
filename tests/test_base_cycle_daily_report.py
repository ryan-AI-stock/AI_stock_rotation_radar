import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

import pandas as pd

from rotation_radar.base_cycle_daily_report import load_state, render_html, update_state
from rotation_radar.base_cycle_daily_report import load_official_prices_and_turnover, ReportDataNotReady


class BaseCycleDailyReportTests(unittest.TestCase):
    def test_partial_exchange_response_is_checkpointed_but_not_treated_as_complete(self):
        with tempfile.TemporaryDirectory() as folder:
            cache = Path(folder)
            row = dict(date='2026-09-14', ticker='2344', name='Winbond', market='TWSE', close=160, turnover_value=1000)
            with patch('rotation_radar.base_cycle_daily_report.pd.read_csv', return_value=pd.DataFrame([row])), patch('rotation_radar.base_cycle_daily_report.fetch_price', return_value=([row], [{'market': 'TWSE', 'status': 'accepted'}, {'market': 'TPEx', 'status': 'blocked'}])):
                with self.assertRaisesRegex(ReportDataNotReady, 'exchanges incomplete'):
                    load_official_prices_and_turnover(source_repo=cache, target=pd.Timestamp('2026-09-14'), current=pd.DataFrame(), source_cache=cache, offline=False)
            saved = pd.read_csv(cache / 'official_recent_full_market.csv.gz', dtype={'ticker': str})
            self.assertEqual(set(saved.market), {'TWSE'})

    def test_retry_fetches_only_exchange_missing_from_partial_target_cache(self):
        with tempfile.TemporaryDirectory() as folder:
            cache = Path(folder)
            cached_path = cache / 'official_recent_full_market.csv.gz'
            twse = dict(date='2026-09-14', ticker='2344', name='Winbond', market='TWSE', close=160, turnover_value=1000)
            tpex = dict(date='2026-09-14', ticker='5351', name='Etron', market='TPEx', close=106, turnover_value=900)
            pd.DataFrame([twse]).to_csv(cached_path, index=False, compression='gzip')
            static = pd.DataFrame([dict(twse, date='2026-09-13')])
            original_read_csv = pd.read_csv

            def read_csv(path, *args, **kwargs):
                if str(path).endswith('current_layer0_official_turnover_daily.csv.gz'):
                    return static.copy()
                return original_read_csv(path, *args, **kwargs)

            manifest = [{'market': 'TPEx', 'status': 'accepted'}]
            with patch('rotation_radar.base_cycle_daily_report.pd.read_csv', side_effect=read_csv), patch(
                'rotation_radar.base_cycle_daily_report.fetch_price', return_value=([tpex], manifest)
            ) as fetch:
                display, _ = load_official_prices_and_turnover(
                    source_repo=cache, target=pd.Timestamp('2026-09-14'), current=pd.DataFrame(),
                    source_cache=cache, offline=False,
                )
            self.assertEqual(fetch.call_args.kwargs['markets'], {'TPEx'})
            self.assertEqual(set(display.ticker), {'2344', '5351'})

    def test_partial_target_cache_is_refetched(self):
        with tempfile.TemporaryDirectory() as folder:
            cache = Path(folder)
            (cache / 'official_recent_full_market.csv.gz').touch()
            row = dict(date='2026-09-14', ticker='2344', name='Winbond', market='TWSE', close=160, turnover_value=1000)
            missing = dict(row, ticker='5351', market='TPEx', close=106)
            with patch('rotation_radar.base_cycle_daily_report.pd.read_csv', return_value=pd.DataFrame([row])), patch('rotation_radar.base_cycle_daily_report.fetch_price', return_value=([row, missing], [{'market': m, 'status': 'accepted'} for m in ['TWSE', 'TPEx']])) as fetch:
                display, _ = load_official_prices_and_turnover(source_repo=cache, target=pd.Timestamp('2026-09-14'), current=pd.DataFrame(), source_cache=cache, offline=False)
            self.assertEqual(fetch.call_count, 1)
            self.assertEqual(set(display.ticker), {'2344', '5351'})

    def test_official_display_preserves_price_lineage(self):
        with tempfile.TemporaryDirectory() as folder:
            cache = Path(folder)
            (cache / 'official_recent_full_market.csv.gz').touch()
            row = {'date': '2026-09-07', 'ticker': '2327', 'name': '國巨',
                   'market': 'TWSE', 'close': 589, 'turnover_value': 1000,
                   'source_hash': 'a' * 64, 'source_url': 'official'}
            with patch('rotation_radar.base_cycle_daily_report.pd.read_csv', return_value=pd.DataFrame([row])):
                display, _ = load_official_prices_and_turnover(source_repo=cache,
                    target=pd.Timestamp('2026-09-07'), current=pd.DataFrame(), source_cache=cache, offline=True)
            self.assertEqual(display.iloc[0].source_hash, 'a' * 64)
            self.assertEqual(display.iloc[0].source_url, 'official')

    def top10(self, tickers):
        return pd.DataFrame([
            {
                "final_rank": index + 1,
                "ticker": ticker,
                "name": f"Name {ticker}",
                "display_close": 50.0 + index,
                "normalized_position": float(index),
                "range_pct": 30.0,
                "window_low": 40.0,
                "window_high": 70.0,
            }
            for index, ticker in enumerate(tickers)
        ])

    def test_only_first_top3_appearance_is_new(self):
        state = load_state(Path("does-not-exist.json"))
        state, first_new, _ = update_state(
            state,
            report_date="2026-07-22",
            top10=self.top10(["A", "B", "C", "D"]),
            raw_close_map={"A": 50, "B": 100, "C": 150, "D": 80},
            trading_dates=["2026-07-22"],
        )
        self.assertEqual([item["ticker"] for item in first_new], ["A", "B", "C"])
        state, second_new, registry = update_state(
            state,
            report_date="2026-07-23",
            top10=self.top10(["A", "E", "F", "B"]),
            raw_close_map={"A": 55, "B": 90, "C": 165, "E": 70, "F": 90},
            trading_dates=["2026-07-22", "2026-07-23"],
        )
        self.assertEqual([item["ticker"] for item in second_new], ["E", "F"])
        a = next(item for item in registry if item["ticker"] == "A")
        self.assertEqual(a["elapsed_trading_days"], 2)
        self.assertAlmostEqual(a["return_pct"], 10.0)

    def test_rerun_same_date_keeps_new_top3_section(self):
        state = load_state(Path("does-not-exist.json"))
        top = self.top10(["A", "B", "C"])
        state, _, _ = update_state(state, report_date="2026-07-22", top10=top, raw_close_map={"A": 50, "B": 100, "C": 150}, trading_dates=["2026-07-22"])
        state, new, _ = update_state(state, report_date="2026-07-22", top10=top, raw_close_map={"A": 50, "B": 100, "C": 150}, trading_dates=["2026-07-22"])
        self.assertEqual({item["ticker"] for item in new}, {"A", "B", "C"})

    def test_html_has_three_sections(self):
        html = render_html(pd.Timestamp("2026-07-22"), pd.Timestamp("2026-07-16"), self.top10(["A", "B", "C"]), [], [])
        self.assertIn("第一部分｜今日前十名", html)
        self.assertIn("第二部分｜今日首次進入前三名", html)
        self.assertIn("第三部分｜歷來前三名總追蹤", html)


if __name__ == "__main__":
    unittest.main()
