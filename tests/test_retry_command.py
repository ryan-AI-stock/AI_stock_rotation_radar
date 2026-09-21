import unittest
from unittest.mock import Mock
from rotation_radar.retry_command import run


class RetryCommandTests(unittest.TestCase):
    def test_recovers_readiness_failure(self):
        execute = Mock(side_effect=[75, 0])
        sleep = Mock()
        self.assertEqual(run(['test'], execute=execute, sleep=sleep), 0)
        self.assertEqual(execute.call_count, 2)
        sleep.assert_called_once_with(30)

    def test_exhausted_stays_failed(self):
        execute = Mock(return_value=75)
        self.assertEqual(run(['test'], execute=execute, sleep=Mock()), 75)
        self.assertEqual(execute.call_count, 3)

    def test_code_bug_not_retried(self):
        execute = Mock(return_value=1)
        self.assertEqual(run(['test'], execute=execute, sleep=Mock()), 1)
        execute.assert_called_once()
