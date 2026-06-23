from __future__ import annotations

import argparse
import csv
import sys
import urllib.parse
import urllib.request
from pathlib import Path

from .pool2_tw50_public_source_search import (
    SEARCH_QUERY_FIELDS,
    SOURCE_AUDIT_FIELDS,
    TIP_RELEVANT_TITLE_MARKERS,
    parse_tip_technical_notice_html,
    tip_notice_to_audit_row,
)


DEFAULT_TIP_URL = "https://taiwanindex.com.tw/downloads/technical_notice?page={page}"
DEFAULT_YUANTA_MONTHLY_URL = "https://www.yuantafunds.com/fund/download/1066元大台灣卓越50基金月報.pdf"


def main() -> None:
    parser = argparse.ArgumentParser(description="Fetch public Pool2 TW50/0050 source metadata.")
    parser.add_argument("--output-metadata", required=True)
    parser.add_argument("--output-queries", required=True)
    parser.add_argument("--max-pages", type=int, default=123)
    parser.add_argument("--include-yuanta-current", action="store_true")
    parser.add_argument("--verify-downloads", action="store_true")
    args = parser.parse_args()

    metadata_rows = []
    total_rows = 0
    for page in range(1, args.max_pages + 1):
        html = _fetch_text(DEFAULT_TIP_URL.format(page=page))
        rows = parse_tip_technical_notice_html(html)
        total_rows += len(rows)
        for row in rows:
            if _is_relevant(row.get("title", "")):
                metadata_rows.append(tip_notice_to_audit_row(row))
        if page % 10 == 0:
            print(f"fetched TIP technical notice page {page}/{args.max_pages}", file=sys.stderr)

    if args.include_yuanta_current:
        metadata_rows.append(_yuanta_current_monthly_row())

    if args.verify_downloads:
        for row in metadata_rows:
            status, http_status = _verify_download(row["source_url"])
            row["download_status"] = status
            row["http_status"] = http_status

    query_rows = [
        {
            "query_or_source": "Taiwan Index technical notice public Nuxt pages",
            "source_url": "https://taiwanindex.com.tw/downloads/technical_notice",
            "search_status": "metadata_fetched",
            "result_count": str(total_rows),
            "exact_candidate_count": str(sum(row["exact_or_proxy"] == "exact_candidate" for row in metadata_rows)),
            "proxy_candidate_count": str(sum(row["exact_or_proxy"] == "proxy_candidate" for row in metadata_rows)),
            "failure_or_gap": "PDF parse not performed in fetch step; source rows remain parse_pending.",
        },
    ]
    if args.include_yuanta_current:
        query_rows.append(
            {
                "query_or_source": "Yuanta 0050 current monthly report fixed public URL",
                "source_url": DEFAULT_YUANTA_MONTHLY_URL,
                "search_status": "metadata_recorded",
                "result_count": "1",
                "exact_candidate_count": "0",
                "proxy_candidate_count": "1",
                "failure_or_gap": "Current monthly proxy only; historical archive still requires separate source acquisition.",
            }
        )

    _write_rows(Path(args.output_metadata), SOURCE_AUDIT_FIELDS, metadata_rows)
    _write_rows(Path(args.output_queries), SEARCH_QUERY_FIELDS, query_rows)
    print(f"metadata_rows={len(metadata_rows)} total_tip_rows={total_rows}")


def _is_relevant(title: str) -> bool:
    lower = title.lower()
    return any(marker.lower() in lower for marker in TIP_RELEVANT_TITLE_MARKERS)


def _fetch_text(url: str) -> str:
    request = urllib.request.Request(
        url,
        headers={
            "User-Agent": "Mozilla/5.0 (compatible; RotationRadarDataAudit/1.0)",
            "Accept-Language": "zh-TW,zh;q=0.9",
        },
    )
    with urllib.request.urlopen(request, timeout=30) as response:
        return response.read().decode("utf-8", errors="replace")


def _verify_download(url: str) -> tuple[str, str]:
    if not url:
        return "missing_url", ""
    safe_url = urllib.parse.quote(url, safe=":/?&=#%")
    request = urllib.request.Request(
        safe_url,
        headers={
            "User-Agent": "Mozilla/5.0 (compatible; RotationRadarDataAudit/1.0)",
            "Range": "bytes=0-15",
        },
    )
    try:
        with urllib.request.urlopen(request, timeout=30) as response:
            head = response.read(16)
            status = str(getattr(response, "status", ""))
            content_type = response.headers.get("Content-Type", "")
    except Exception as exc:  # noqa: BLE001 - status audit should capture remote failures.
        return f"download_failed:{type(exc).__name__}", ""
    if head.startswith(b"%PDF") or "pdf" in content_type.lower():
        return "http_pdf_verified", status
    return "http_non_pdf_or_unverified", status


def _yuanta_current_monthly_row() -> dict[str, str]:
    return {
        "source_id": "yuanta_0050_current_monthly_pdf",
        "source_url": DEFAULT_YUANTA_MONTHLY_URL,
        "download_status": "public_current_url_known",
        "http_status": "",
        "date_covered": "2026-05-31",
        "publish_date": "2026/05/31",
        "source_title": "元大台灣卓越50基金月報",
        "source_type": "yuanta_monthly_report",
        "exact_or_proxy": "proxy_candidate",
        "license_or_usage_note": "official Yuanta public current monthly PDF; verify historical archive and redistribution/license before publishing raw files",
        "parse_status": "current_top10_sample_only_in_phase2",
        "future_data_violation_check": "not_applicable",
        "notes": "Proxy candidate only; not exact TW50 official constituents and not historical coverage.",
    }


def _write_rows(path: Path, fieldnames: list[str], rows: list[dict[str, str]]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("w", encoding="utf-8-sig", newline="") as handle:
        writer = csv.DictWriter(handle, fieldnames=fieldnames)
        writer.writeheader()
        writer.writerows(rows)


if __name__ == "__main__":
    main()
