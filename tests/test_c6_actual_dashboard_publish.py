import copy
import unittest
from unittest.mock import Mock, patch
from rotation_radar import c6_actual_dashboard_publish as actual
from rotation_radar import sheets_retry


class ActualSignalsTests(unittest.TestCase):
    def test_pending_cash_is_not_republished_as_current_nav(self):
        rows=[['資料狀態','ready'],['現金餘額',125708,'帳戶總資產（參考估值）',7000000],
              ['期初總資產',7676961.04,'相對期初本金損益（含提領）',-1]]
        ledger=[['header'],['2026-09-14',5,'實際成交（人工）','2344','華邦電','加碼',164.14,2000,328280,'','待確認']]
        result=actual.guard_unconfirmed_cash(rows,ledger)
        self.assertEqual(result[1][1],125708)
        self.assertEqual(result[1][3],'待現金與資金來源核對')
        self.assertEqual(result[2][3],'待資金來源核對')

    def test_manual_buy_has_entry_date_without_becoming_initial_registration(self):
        rows=[[],[]]+[[i,'未持有／預留位置'] for i in range(1,5)]+[[5,'2344 華邦電｜1000股',179.65,179650]]
        ledger=[['header'],['2026-09-10',5,'實際成交（人工）','2344','華邦電','買進']+['']*11+['實際買入日2026-09-10；含費']]
        prices=[dict(ticker='2344',date=d,close=p,source_hash='a'*64) for d,p in [('2026-09-10',179),('2026-09-11',171.5)]]
        payload=dict(ranking_snapshot_as_of='2026-09-11',market_rows=prices[1:],actual_holding_history=dict(end='2026-09-11',calendar_complete=True,trading_dates=['2026-09-10','2026-09-11'],official_rows=prices))
        observed=actual.daily_observation_rows(rows,payload,ledger)
        self.assertEqual(observed[0][14],2)
        self.assertEqual(observed[0][8],171500)
        self.assertEqual(ledger[1][2],'實際成交（人工）')

    def test_daily_rows_use_confirmed_entries_and_market_td(self):
        tickers = ['2327', '2376', '3037', '6488']
        rows = [[], []] + [[i, f'{t} 名稱｜10股', 100, 1000] for i, t in enumerate(tickers, 1)]
        ledger = [['header']] + [['2026-09-03', i, '期初持倉登錄', t] + [''] * 13
                                 + ['實際買入日2026-09-04；期初登錄'] for i, t in enumerate(tickers, 1)]
        prices = [{'ticker': t, 'date': d, 'close': p, 'source_hash': 'a' * 64}
                  for t in tickers for d, p in [('2026-09-04', 115), ('2026-09-07', 110)]]
        payload = {'ranking_snapshot_as_of': '2026-09-07',
                   'market_rows': [p for p in prices if p['date'] == '2026-09-07'],
                   'actual_holding_history': {'end': '2026-09-07', 'calendar_complete': True,
                       'trading_dates': ['2026-09-04', '2026-09-07'], 'official_rows': prices}}
        observations = actual.daily_observation_rows(rows, payload, ledger)
        self.assertEqual(observations[0][14], 2)
        self.assertIn('最高原始收盤115元', observations[0][17])
        self.assertIn('+20%後回撤12%待資料', observations[0][17])
        payload['actual_holding_history'].update(calendar_complete=False, calendar_loaded=True,
                                                 missing_session_dates=['2026-07-10'])
        self.assertEqual(actual.daily_observation_rows(rows, payload, ledger)[0][14], 2)
        payload['actual_holding_history']['missing_session_dates'] = ['2026-09-04']
        self.assertEqual(actual.daily_observation_rows(rows, payload, ledger)[0][14], '待完整交易日資料')
        payload['actual_holding_history']['end'] = '2026-09-08'
        self.assertEqual(actual.daily_observation_rows(rows, payload, ledger)[0][14], '待完整交易日資料')

    def test_observations_are_not_fills_and_do_not_claim_exit_readiness(self):
        rows = [[], []] + [[i, f'{ticker} 名稱｜10股', 100, 1000]
                           for i, ticker in enumerate(['2327', '2376', '3037', '6488'], 1)]
        payload = {'ranking_snapshot_as_of': '2026-09-07', 'market_rows': [
            {'ticker': ticker, 'date': '2026-09-07', 'close': 110, 'source_hash': 'a' * 64}
            for ticker in ['2327', '2376', '3037', '6488']]}
        observations = actual.daily_observation_rows(rows, payload)
        self.assertEqual(len(observations), 4)
        self.assertEqual(observations[0][8], 1100)
        self.assertAlmostEqual(observations[0][16], .1)
        self.assertEqual(observations[0][10:14], ['', '', '', ''])
        self.assertIn('非成交', observations[0][2])
        self.assertIn('完整退出條件待接通', observations[0][17])
        payload['market_rows'][0]['source_hash'] = 'nan'
        with self.assertRaises(ValueError):
            actual.daily_observation_rows(rows, payload)

    def test_quotes_require_exact_date_price_and_lineage(self):
        rows = [[], []] + [[1, f'{ticker} 名稱｜10股'] for ticker in ['2327', '2376', '3037', '6488']]
        value = actual.holding_quote_text(rows, {'ranking_snapshot_as_of': '2026-09-04', 'market_rows': [
            {'ticker': '2327', 'date': '2026-09-04', 'close': 100, 'source_hash': 'a' * 64},
            {'ticker': '2376', 'date': '2026-09-03', 'close': 101, 'source_hash': 'hash'},
            {'ticker': '3037', 'date': '2026-09-04', 'close': 102, 'source_hash': ''},
        ]})
        self.assertIn('2327：100', value)
        self.assertIn('2376：官方來源待補', value)
        self.assertIn('3037：官方來源待補', value)
        self.assertIn('6488：官方來源待補', value)

    def test_formulas_reference_database_not_simulation_account(self):
        formulas = str(actual.signal_formulas())
        self.assertIn('C6每日訊號資料庫', formulas)
        self.assertIn('無其他合格股票', formulas)
        self.assertNotIn('模擬交易', formulas)

    def test_wrong_source_date_fails_before_sheet_access(self):
        with patch.object(actual, 'SheetsClient') as client:
            with self.assertRaises(ValueError):
                actual.publish('actual', {'ranking_snapshot_as_of': '2026-09-04', 'snapshot_rows': []})
            client.assert_not_called()

    def test_missing_actual_ledger_rejected_before_writes(self):
        client = Mock()
        client.get.return_value = []
        with patch.object(actual, 'SheetsClient', return_value=client):
            with self.assertRaises(ValueError):
                actual.publish('wrong', {'ranking_snapshot_as_of': '2026-09-04', 'snapshot_rows': [
                    {'signal_date': '2026-09-04', 'rank': 1, 'ticker': '3653', 'name': '健策'}]})
        client.update.assert_not_called()
        client.clear.assert_not_called()


class RetryTests(unittest.TestCase):
    @patch.object(sheets_retry.time, 'sleep')
    def test_transient_error_then_success(self, sleep):
        method = Mock(side_effect=[Mock(status_code=503), Mock(status_code=200)])
        self.assertEqual(sheets_retry.request(method).status_code, 200)
        self.assertEqual(method.call_count, 2)

    @patch.object(sheets_retry.time, 'sleep')
    def test_retry_is_bounded(self, sleep):
        method = Mock(return_value=Mock(status_code=429))
        self.assertEqual(sheets_retry.request(method).status_code, 429)
        self.assertEqual(method.call_count, 3)

    @patch.object(sheets_retry.time, 'sleep')
    def test_auth_denial_not_retried(self, sleep):
        method = Mock(return_value=Mock(status_code=403))
        self.assertEqual(sheets_retry.request(method).status_code, 403)
        self.assertEqual(method.call_count, 1)
