import unittest

from r1.required_data import RequiredDataError, enforce_required_data, required_data_gaps


class R1RequiredDataTest(unittest.TestCase):
    def test_reports_ticker_and_exact_missing_fields(self):
        rows = [{"ticker": "2408", "eps_revision_4w": None, "base_upside": 0.2}]
        self.assertEqual(
            required_data_gaps(rows, ("eps_revision_4w", "base_upside")),
            [{"ticker": "2408", "missing_fields": ["eps_revision_4w"]}],
        )
        with self.assertRaisesRegex(RequiredDataError, "2408:eps_revision_4w"):
            enforce_required_data(
                rows, ("eps_revision_4w", "base_upside"),
                date="2026-10-02", context="weekly_decision",
            )

    def test_complete_rows_pass(self):
        enforce_required_data(
            [{"ticker": "2408", "eps_revision_4w": 0.1}],
            ("eps_revision_4w",), date="2026-10-02", context="weekly_decision",
        )


if __name__ == "__main__":
    unittest.main()
