import unittest

from r1.providers import MissingConsensusProvider
from r1.schema import consensus_allows_action, validate_lineage


class R1SchemaTest(unittest.TestCase):
    def test_missing_consensus_never_allows_action(self):
        records = MissingConsensusProvider().fetch(["2330", "2408"], "2026-10-01")
        self.assertEqual(len(records), 2)
        self.assertTrue(all(record.mean_eps is None for record in records))
        self.assertTrue(all(not consensus_allows_action(record.__dict__) for record in records))

    def test_two_analyst_medium_quality_consensus_allows_action(self):
        row = {"status": "AVAILABLE", "quality": "MEDIUM", "analyst_count": 2,
               "mean_eps": 10.5, "fiscal_year": 2027}
        self.assertTrue(consensus_allows_action(row))

    def test_future_available_timestamp_is_rejected(self):
        row = {"source": "test", "as_of_date": "2026-10-01", "published_at": None,
               "available_at": "2026-10-02T00:00:00+08:00",
               "retrieved_at": "2026-10-01T23:00:00+08:00", "quality": "HIGH"}
        with self.assertRaisesRegex(ValueError, "available_at"):
            validate_lineage(row)


if __name__ == "__main__":
    unittest.main()
