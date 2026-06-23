from __future__ import annotations

import csv
import tempfile
import unittest
from pathlib import Path

from rotation_radar.formal_sources.pool2_tw50_public_source_search import (
    SOURCE_AUDIT_FIELDS,
    build_pool2_tw50_public_source_search,
    parse_tip_technical_notice_html,
    tip_notice_to_audit_row,
)


class Pool2Tw50PublicSourceSearchTests(unittest.TestCase):
    def test_parses_tip_nuxt_notice_rows(self) -> None:
        html = (
            '<script>window.__NUXT__=(function(a,b,c,d,e){return '
            '{fetch:{"x":{pagination:{data:[{category:d,title:"臺灣證券交易所與富時國際有限公司合編之臺灣指數系列成分股變動",'
            'url:"https:\\u002F\\u002Fbackend.taiwanindex.com.tw\\u002Fapi\\u002FdownloadFile\\u002FTechnicalNotices\\u002F1276\\u002Ftw",'
            'publish_date:e}],links:{}}}}}}(false,null,0,"其他","2026\\u002F06\\u002F18"));</script><script src="/_nuxt/x.js">'
        )

        rows = parse_tip_technical_notice_html(html)
        self.assertEqual(len(rows), 1)
        self.assertEqual(rows[0]["publish_date"], "2026/06/18")
        self.assertEqual(rows[0]["url"], "https://backend.taiwanindex.com.tw/api/downloadFile/TechnicalNotices/1276/tw")

        audit = tip_notice_to_audit_row(rows[0])
        self.assertEqual(audit["source_id"], "tip_1276_tw")
        self.assertEqual(audit["exact_or_proxy"], "exact_candidate")

    def test_exact_candidate_stays_not_ready_until_parsed(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            metadata = root / "metadata.csv"
            _write_rows(
                metadata,
                [
                    {
                        "source_id": "tip_1262_tw",
                        "source_url": "https://backend.taiwanindex.com.tw/api/downloadFile/TechnicalNotices/1262/tw",
                        "download_status": "metadata_found",
                        "http_status": "200",
                        "date_covered": "2026-06-05",
                        "publish_date": "2026/06/05",
                        "source_title": "臺灣證券交易所與富時國際有限公司合編之臺灣指數系列及臺灣高股息指數成分股定期審核結果",
                        "source_type": "taiwanindex_technical_notice",
                        "exact_or_proxy": "",
                        "license_or_usage_note": "official public technical notice",
                        "parse_status": "parse_pending",
                        "future_data_violation_check": "requires_notice_parse",
                        "notes": "Official exact candidate; rows not accepted until PDF is parsed.",
                    }
                ],
            )

            readiness = build_pool2_tw50_public_source_search(
                output_dir=root / "out",
                source_metadata_path=metadata,
            )

            self.assertEqual(readiness["status"], "partial_exact_public_sources_found_parse_pending")
            self.assertFalse(readiness["ready"])
            self.assertFalse(readiness["public_source_exhausted"])
            self.assertEqual(readiness["exact_candidate_count"], 1)
            self.assertEqual(readiness["accepted_rows"], 0)
            self.assertIn("exact_candidate", (root / "out" / "source_search_audit.csv").read_text(encoding="utf-8-sig"))

    def test_proxy_candidate_does_not_become_exact_ready(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            metadata = root / "metadata.csv"
            _write_rows(
                metadata,
                [
                    {
                        "source_id": "yuanta_current_monthly",
                        "source_url": "https://www.yuantafunds.com/fund/download/1066元大台灣卓越50基金月報.pdf",
                        "source_title": "元大台灣卓越50基金月報",
                        "source_type": "yuanta_monthly_report",
                    }
                ],
            )

            readiness = build_pool2_tw50_public_source_search(
                output_dir=root / "out",
                source_metadata_path=metadata,
            )

            self.assertEqual(readiness["status"], "partial_proxy_public_sources_found_parse_pending")
            self.assertFalse(readiness["ready"])
            self.assertEqual(readiness["exact_candidate_count"], 0)
            self.assertEqual(readiness["proxy_candidate_count"], 1)

    def test_no_candidates_marks_public_source_exhausted(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            metadata = root / "metadata.csv"
            _write_rows(
                metadata,
                [
                    {
                        "source_id": "unrelated_notice",
                        "source_url": "https://example.com/notice.pdf",
                        "source_title": "Unrelated Index Review Result",
                        "source_type": "public_web_search",
                    }
                ],
            )

            readiness = build_pool2_tw50_public_source_search(
                output_dir=root / "out",
                source_metadata_path=metadata,
            )

            self.assertEqual(readiness["status"], "blocked_public_source_exhausted")
            self.assertTrue(readiness["public_source_exhausted"])
            self.assertEqual(readiness["exact_candidate_count"], 0)
            self.assertEqual(readiness["proxy_candidate_count"], 0)


def _write_rows(path: Path, rows: list[dict[str, str]]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    fieldnames = SOURCE_AUDIT_FIELDS
    with path.open("w", encoding="utf-8-sig", newline="") as handle:
        writer = csv.DictWriter(handle, fieldnames=fieldnames)
        writer.writeheader()
        for row in rows:
            writer.writerow({field: row.get(field, "") for field in fieldnames})
