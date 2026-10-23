import unittest

from r1.official_negative_evidence import build_official_negative_evidence


class R1OfficialNegativeEvidenceTest(unittest.TestCase):
    def test_joint_negative_conditions_emit_auditable_flags(self):
        payload = build_official_negative_evidence(
            as_of_date="2026-10-22",
            monthly_revenue={"rows": [{"ticker": "2330", "observations": [
                {"revenue_year_month": "2026-07", "yoy": -.01,
                 "available_date": "2026-08-10", "source_url": "m1"},
                {"revenue_year_month": "2026-08", "yoy": -.02,
                 "available_date": "2026-09-10", "source_url": "m2"},
                {"revenue_year_month": "2026-09", "yoy": -.03,
                 "available_date": "2026-10-12", "source_url": "m3"},
            ]}]},
            financial_quality={"as_of_date": "2026-10-16", "rows": [{
                "ticker": "2330", "status": "READY", "source_url": "f1",
                "metrics": {"revenue_yoy_pct": -2, "eps_yoy_pct": -3,
                            "gross_margin_change_pp": -1,
                            "operating_margin_change_pp": -2,
                            "operating_cash_flow": -100},
            }]},
        )
        self.assertEqual(payload["event_count"], 3)
        self.assertEqual(payload["future_data_violation_count"], 0)
        self.assertEqual({row["event_type"] for row in payload["rows"]}, {
            "MONTHLY_REVENUE_CONTRACTION", "FINANCIAL_EARNINGS_CONTRACTION",
            "FINANCIAL_CASH_MARGIN_STRESS",
        })

    def test_single_weak_value_does_not_invent_negative_event(self):
        payload = build_official_negative_evidence(
            as_of_date="2026-10-22",
            monthly_revenue={"rows": [{"ticker": "2330", "observations": [
                {"revenue_year_month": "2026-07", "yoy": .2,
                 "available_date": "2026-08-10", "source_url": "m1"},
                {"revenue_year_month": "2026-08", "yoy": .1,
                 "available_date": "2026-09-10", "source_url": "m2"},
                {"revenue_year_month": "2026-09", "yoy": -.01,
                 "available_date": "2026-10-12", "source_url": "m3"},
            ]}]}, financial_quality={"rows": []},
        )
        self.assertEqual(payload["event_count"], 0)


if __name__ == "__main__":
    unittest.main()
