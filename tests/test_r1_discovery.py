import unittest
from pathlib import Path
from tempfile import TemporaryDirectory

from r1.discovery import build_discovery_pool


HEADER = "discovery_date,ticker,company,bottleneck,reason,causal_chain,revenue_exposure,customer_evidence,financial_evidence,source_url,source_family,source_tier,published_at,available_at,retrieved_at,evidence_status\n"


class R1DiscoveryTest(unittest.TestCase):
    def _run(self, rows: str, as_of_date: str = "2026-10-03") -> dict:
        with TemporaryDirectory() as folder:
            path = Path(folder) / "evidence.csv"
            path.write_text(HEADER + rows, encoding="utf-8")
            return build_discovery_pool(path, as_of_date=as_of_date)

    def test_two_independent_sources_with_authority_are_review_ready_only(self):
        result = self._run(
            "2026-10-01,9999,測試公司,先進封裝,需求缺口,AI需求到營收,x,x,x,https://a,company,2,2026-10-01,2026-10-01,2026-10-02,VERIFIED\n"
            "2026-10-01,9999,測試公司,先進封裝,需求缺口,AI需求到營收,x,x,x,https://b,exchange,3,2026-10-01,2026-10-01,2026-10-02,VERIFIED\n"
        )
        candidate = result["candidates"][0]
        self.assertEqual(candidate["status"], "ELIGIBLE_FOR_RYAN_REVIEW")
        self.assertFalse(candidate["universe_admission"])
        self.assertFalse(result["formal_model_changed"])

    def test_same_source_family_keeps_evidence_gap(self):
        result = self._run(
            "2026-10-01,9999,測試公司,先進封裝,需求缺口,AI需求到營收,x,x,x,https://a,company,1,2026-10-01,2026-10-01,2026-10-02,VERIFIED\n"
            "2026-10-01,9999,測試公司,先進封裝,需求缺口,AI需求到營收,x,x,x,https://b,company,2,2026-10-01,2026-10-01,2026-10-02,VERIFIED\n"
        )
        self.assertEqual(result["candidates"][0]["status"], "DISCOVERY_POOL_EVIDENCE_GAP")

    def test_future_evidence_is_rejected(self):
        result = self._run(
            "2026-10-01,9999,測試公司,先進封裝,需求缺口,AI需求到營收,x,x,x,https://a,company,1,2026-10-01,2026-10-04,2026-10-04,VERIFIED\n"
        )
        self.assertEqual(result["candidates"], [])
        self.assertEqual(result["rejected_rows"][0]["error"], "future_data")

    def test_empty_template_produces_empty_review_pool(self):
        result = self._run("")
        self.assertEqual(result["candidates"], [])
        self.assertEqual(result["rejected_rows"], [])


if __name__ == "__main__":
    unittest.main()
