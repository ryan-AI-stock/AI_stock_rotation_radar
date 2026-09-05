import copy
import unittest
from unittest.mock import Mock, patch
from rotation_radar import c6_actual_dashboard_publish as actual
from rotation_radar import sheets_retry


class ActualSignalsTests(unittest.TestCase):
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
