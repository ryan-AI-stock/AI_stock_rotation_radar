import unittest
from types import SimpleNamespace
from unittest.mock import patch
from urllib.error import URLError

from rotation_radar.disposition_gate import _fetch_json


class TransportTests(unittest.TestCase):
    def test_tls_fallback_preserves_endpoint_and_verification(self):
        with patch('rotation_radar.disposition_gate.urlopen', side_effect=URLError('certificate')), patch('rotation_radar.disposition_gate.subprocess.run', return_value=SimpleNamespace(stdout=b'{"tables": []}')) as run:
            self.assertEqual(_fetch_json('https://official.test', {'date': '2026/09/14'}), {'tables': []})
        command = run.call_args.args[0]
        self.assertEqual(command[-1], 'https://official.test')
        self.assertNotIn('--insecure', command)
        self.assertNotIn('-k', command)
        self.assertIn('date=2026%2F09%2F14', command)
        self.assertEqual(run.call_args.kwargs['timeout'], 145)

