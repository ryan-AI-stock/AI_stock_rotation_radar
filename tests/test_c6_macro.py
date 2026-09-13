import unittest
import pandas as pd
import json
from pathlib import Path
from tempfile import TemporaryDirectory
from unittest.mock import patch
from rotation_radar.c6_macro import load_cbc
from rotation_radar.c6_daily_pipeline import fetch_c6_revenue_with_retry
from rotation_radar.public_sources import SourceFetchError
from rotation_radar.c6_macro import evaluate
from rotation_radar.base_cycle_daily_report import ReportDataNotReady

class MacroTests(unittest.TestCase):
    @patch('rotation_radar.c6_macro.time.sleep')
    @patch('rotation_radar.c6_macro.urlopen')
    def test_incomplete_cbc_cache_downloads_required_dates(self, fetch, sleep):
        target=pd.Timestamp('2026-09-11')
        with TemporaryDirectory() as folder:
            path=Path(folder)/'cbc-20260911.json'
            path.write_text(json.dumps([{'Date':'20260910','NTD_USD':'31'}]))
            raw=json.dumps([{'Date':'20260910','NTD_USD':'31'},{'Date':'20260911','NTD_USD':'32'}]).encode()
            fetch.return_value.__enter__.return_value.read.return_value=raw
            frame,_=load_cbc(folder,target,required_dates=['2026-09-10','2026-09-11'])
            self.assertEqual(len(frame),2);fetch.assert_called_once()
            load_cbc(folder,target);fetch.assert_called_once()
    @patch('rotation_radar.c6_macro.time.sleep')
    @patch('rotation_radar.c6_macro.urlopen',side_effect=OSError('502'))
    def test_cbc_retry_limit(self,fetch,sleep):
        with TemporaryDirectory() as folder:
            with self.assertRaises(ReportDataNotReady):load_cbc(folder,pd.Timestamp('2026-09-11'))
        self.assertEqual(fetch.call_count,3)
    @patch('rotation_radar.c6_daily_pipeline.time.sleep')
    @patch('rotation_radar.c6_daily_pipeline.fetch_mops_text')
    def test_revenue_recovers_and_is_bounded(self,fetch,sleep):
        fetch.side_effect=[SourceFetchError('502'),'valid']
        self.assertEqual(fetch_c6_revenue_with_retry('url'),'valid')
        fetch.reset_mock();fetch.side_effect=SourceFetchError('502')
        with self.assertRaises(ReportDataNotReady):fetch_c6_revenue_with_retry('url')
        self.assertEqual(fetch.call_count,3)
    def fixtures(self):
        dates=pd.bdate_range(end='2026-09-16',periods=90)
        target=pd.Timestamp('2026-09-11')
        adjusted=pd.DataFrame({'date':dates,'ticker':'0050','adjusted_analysis_close':[100+i*i*.01 for i in range(90)]})
        fx=pd.DataFrame({'date':dates,'ntd_per_usd':[30+i*.01 for i in range(90)]})
        return target,adjusted,fx,dates,pd.Timestamp('2026-09-16')
    def test_three_trading_days_and_all_high(self):
        result=evaluate(*self.fixtures())
        self.assertEqual(result['settlement_distance_td'],3)
        self.assertTrue(result['macro_triple'])
    def test_missing_fx_not_false(self):
        args=list(self.fixtures());args[2]=args[2][args[2].date.ne(args[0])]
        with self.assertRaises(ReportDataNotReady):evaluate(*args)
    def test_future_values_cannot_change_today(self):
        args=list(self.fixtures());expected=evaluate(*args)
        args[1].loc[args[1].date.gt(args[0]),'adjusted_analysis_close']=999999
        args[2].loc[args[2].date.gt(args[0]),'ntd_per_usd']=999
        self.assertEqual(evaluate(*args),expected)
    def test_outside_window_does_not_need_fx(self):
        args=list(self.fixtures());args[0]=pd.Timestamp('2026-09-10');args[2]=pd.DataFrame()
        self.assertFalse(evaluate(*args)['macro_triple'])
