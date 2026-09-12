import unittest
import pandas as pd
from rotation_radar.c6_macro import evaluate
from rotation_radar.base_cycle_daily_report import ReportDataNotReady

class MacroTests(unittest.TestCase):
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
