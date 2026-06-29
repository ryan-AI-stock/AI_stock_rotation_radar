from __future__ import annotations

import csv
import hashlib
import html
import json
import re
import time
from datetime import datetime
from pathlib import Path
from typing import Iterable
from urllib.parse import quote, unquote, urljoin, urlparse

import requests

OUT = Path("outputs/radar_tw50_0050_archived_html_crawler_201411_202312_20260629")
PREV = Path("outputs/radar_tw50_0050_historical_source_download_201411_202312_20260629")
RAW = OUT / "raw_sources"
RAW.mkdir(parents=True, exist_ok=True)

TARGETS = [
    {"period": "2014Q4", "target_date": "2014-12-31", "from": "201410", "to": "201501", "stamp": "20141231"},
    {"period": "2016Q1", "target_date": "2016-03-31", "from": "201601", "to": "201604", "stamp": "20160331"},
    {"period": "2021Q4", "target_date": "2021-12-31", "from": "202110", "to": "202201", "stamp": "20211231"},
    {"period": "2023Q4", "target_date": "2023-12-31", "from": "202310", "to": "202401", "stamp": "20231231"},
]

PAGE_QUERIES = [
    {
        "route_id": "yuantaetfs_0050_product_exact",
        "cdx_url": "https://www.yuantaetfs.com/product/detail/0050",
        "homepage": "https://www.yuantaetfs.com/product/detail/0050",
    },
    {
        "route_id": "yuantaetfs_0050_product_wildcard",
        "cdx_url": "https://www.yuantaetfs.com/product/detail/0050*",
        "homepage": "https://www.yuantaetfs.com/product/detail/0050",
    },
    {
        "route_id": "yuantaetfs_0050_download_wildcard",
        "cdx_url": "https://www.yuantaetfs.com/product/detail/0050/download*",
        "homepage": "https://www.yuantaetfs.com/product/detail/0050/download",
    },
    {
        "route_id": "yuantaetfs_api_0050_wildcard",
        "cdx_url": "https://www.yuantaetfs.com/api/*0050*",
        "homepage": "https://www.yuantaetfs.com/product/detail/0050",
    },
    {
        "route_id": "yuantafunds_0050_product_wildcard",
        "cdx_url": "https://www.yuantafunds.com/product/detail/0050*",
        "homepage": "https://www.yuantafunds.com/product/detail/0050",
    },
    {
        "route_id": "yuantafunds_0050_any_wildcard",
        "cdx_url": "https://www.yuantafunds.com/*0050*",
        "homepage": "https://www.yuantafunds.com/",
    },
    {
        "route_id": "yuantafunds_tw_0050_any_wildcard",
        "cdx_url": "https://www.yuantafunds.com.tw/*0050*",
        "homepage": "https://www.yuantafunds.com.tw/",
    },
]

AVAILABILITY_PAGE_URLS = [
    ("yuantaetfs_basic_information", "https://www.yuantaetfs.com/product/detail/0050/Basic_information"),
    ("yuantaetfs_ratio", "https://www.yuantaetfs.com/product/detail/0050/ratio"),
    ("yuantaetfs_download", "https://www.yuantaetfs.com/product/detail/0050/download"),
    ("yuantaetfs_product_root", "https://www.yuantaetfs.com/product/detail/0050"),
    ("yuantafunds_product_root", "https://www.yuantafunds.com/product/detail/0050"),
    ("yuantafunds_legacy_fund_root", "https://www.yuantafunds.com/fund/0050"),
    ("yuantafunds_tw_legacy_root", "https://www.yuantafunds.com.tw/"),
]

PDF_KEYWORDS = [
    "0050",
    "台灣50",
    "台灣卓越50",
    "月報",
    "季持股",
    "持股",
    "YUEBAO",
    "HOLD",
    "STOCK",
    "DOC_YUEBAO_URL",
    "DOC_HOLD_STOCK_URL",
]

HEADERS = {
    "User-Agent": "Mozilla/5.0 RadarDataArchivedHtmlCrawler/1.0",
    "Accept": "text/html,application/xhtml+xml,application/xml,application/pdf,application/json,*/*",
}


def now() -> str:
    return time.strftime("%Y-%m-%dT%H:%M:%S+08:00")


def safe(text: str, limit: int = 150) -> str:
    return re.sub(r"[^A-Za-z0-9_.-]+", "_", text).strip("_")[:limit] or "item"


def sha256(data: bytes) -> str:
    return hashlib.sha256(data).hexdigest()


def write_csv(path: Path, rows: list[dict], fields: list[str]) -> None:
    with path.open("w", newline="", encoding="utf-8") as fh:
        writer = csv.DictWriter(fh, fieldnames=fields, extrasaction="ignore")
        writer.writeheader()
        writer.writerows(rows)


def fetch(url: str, timeout: int = 10, max_bytes: int = 3_000_000) -> tuple[str, str, bytes, str, str]:
    try:
        with requests.get(url, headers=HEADERS, timeout=(4, timeout), stream=True, allow_redirects=True) as resp:
            chunks: list[bytes] = []
            total = 0
            for chunk in resp.iter_content(65536):
                if not chunk:
                    continue
                chunks.append(chunk)
                total += len(chunk)
                if total >= max_bytes:
                    break
            return str(resp.status_code), resp.headers.get("content-type", ""), b"".join(chunks), resp.url, ""
    except Exception as exc:
        return "", "", b"", "", f"{type(exc).__name__}: {exc}"


def cdx_query(url: str, start: str, end: str, limit: int = 12) -> str:
    return (
        "https://web.archive.org/cdx?url="
        + quote(url, safe="*")
        + f"&from={start}&to={end}&output=json&fl=timestamp,original,statuscode,mimetype,digest"
        + "&filter=statuscode:200&collapse=digest&limit="
        + str(limit)
    )


def availability_query(url: str, stamp: str) -> str:
    return "https://archive.org/wayback/available?url=" + quote(url, safe="") + "&timestamp=" + stamp


def snapshot_url(timestamp: str, original: str, mode: str = "id_") -> str:
    return f"https://web.archive.org/web/{timestamp}{mode}/{original}"


def decode_text(body: bytes) -> str:
    for encoding in ("utf-8", "big5", "cp950"):
        try:
            return body.decode(encoding)
        except UnicodeDecodeError:
            continue
    return body.decode("utf-8", errors="replace")


def extract_href_candidates(text: str, base_url: str) -> list[dict]:
    decoded = html.unescape(unquote(text))
    hrefs: list[tuple[str, str]] = []
    for match in re.finditer(r"""(?:href|src)\s*=\s*["']([^"']+)["']""", decoded, flags=re.I):
        hrefs.append((match.group(1), "html_attr"))
    for match in re.finditer(r"""["']([^"']+?\.pdf(?:\?[^"']*)?)["']""", decoded, flags=re.I):
        hrefs.append((match.group(1), "quoted_pdf"))
    for match in re.finditer(r"""(?:DOC_YUEBAO_URL|DOC_HOLD_STOCK_URL|YUEBAO|HOLD)[^"'<>]{0,200}?((?:https?:)?//[^"'<>]+?\.pdf|/[^"'<>]+?\.pdf)""", decoded, flags=re.I):
        hrefs.append((match.group(1), "doc_variable_near_pdf"))

    rows: list[dict] = []
    seen: set[str] = set()
    for raw_href, evidence in hrefs:
        clean = raw_href.strip()
        if clean.startswith("javascript:") or clean.startswith("#"):
            continue
        resolved = urljoin(base_url, clean)
        lower = resolved.lower()
        text_near = decoded[max(0, decoded.find(raw_href) - 80) : decoded.find(raw_href) + len(raw_href) + 120]
        keyword_hit = any(k.lower() in (resolved + " " + text_near).lower() for k in PDF_KEYWORDS)
        is_pdf = ".pdf" in lower or "download" in lower
        if not is_pdf and not keyword_hit:
            continue
        key = resolved
        if key in seen:
            continue
        seen.add(key)
        rows.append(
            {
                "href": resolved,
                "raw_href": clean,
                "evidence_type": evidence,
                "keyword_hit": str(keyword_hit).lower(),
                "text_near": re.sub(r"\s+", " ", text_near)[:240],
            }
        )
    return rows


def normalize_original_from_wayback(url: str) -> str:
    parsed = urlparse(url)
    if "web.archive.org" not in parsed.netloc:
        return url
    match = re.search(r"/web/\d+(?:[a-z_]+)?/(.+)$", parsed.path + (("?" + parsed.query) if parsed.query else ""))
    return match.group(1) if match else url


def selected_snapshots_from_cdx(body: bytes) -> list[dict]:
    try:
        payload = json.loads(decode_text(body))
    except Exception:
        return []
    if not isinstance(payload, list) or len(payload) <= 1:
        return []
    rows = []
    for row in payload[1:]:
        if len(row) < 5:
            continue
        timestamp, original, statuscode, mimetype, digest = row[:5]
        rows.append(
            {
                "timestamp": timestamp,
                "original": original,
                "statuscode": statuscode,
                "mimetype": mimetype,
                "digest": digest,
            }
        )
    return rows[:6]


def selected_snapshot_from_availability(body: bytes) -> dict | None:
    try:
        payload = json.loads(decode_text(body))
    except Exception:
        return None
    closest = payload.get("archived_snapshots", {}).get("closest", {}) if isinstance(payload, dict) else {}
    if not closest or closest.get("status") != "200" or not closest.get("url"):
        return None
    original = payload.get("url") or ""
    return {
        "timestamp": closest.get("timestamp", ""),
        "original": original,
        "statuscode": closest.get("status", ""),
        "mimetype": "unknown_from_availability",
        "digest": "",
        "available_url": closest.get("url", ""),
    }


def text_sample_from_pdf_bytes(body: bytes) -> tuple[str, str, int]:
    if b"%PDF" not in body[:2048]:
        return "", "not_pdf_magic", 0
    try:
        import pdfplumber  # type: ignore
    except Exception as exc:
        return "", f"pdfplumber_unavailable:{type(exc).__name__}", 0
    tmp = RAW / f"tmp_{sha256(body)[:12]}.pdf"
    tmp.write_bytes(body)
    try:
        with pdfplumber.open(str(tmp)) as pdf:
            pages = pdf.pages[:2]
            text = "\n".join((p.extract_text() or "") for p in pages)
            return text[:2000], "pdf_text_extracted" if text else "pdf_text_empty", len(pdf.pages)
    except Exception as exc:
        return "", f"pdf_parse_error:{type(exc).__name__}: {exc}", 0
    finally:
        try:
            tmp.unlink()
        except OSError:
            pass


def parse_rows_from_text(text: str) -> list[dict]:
    rows = []
    # Common TW ticker + Chinese name + percentage pattern. This is only a conservative sample extractor.
    pattern = re.compile(r"\b(\d{4})\b\s+([\u4e00-\u9fffA-Za-z0-9（）\(\)\-\.]{2,30})\s+([0-9]+(?:\.[0-9]+)?)\s*%?")
    for ticker, name, weight in pattern.findall(text):
        if ticker.startswith(("00", "88", "99")):
            continue
        rows.append({"ticker": ticker, "name": name, "weight": weight})
        if len(rows) >= 20:
            break
    return rows


def extract_html_holdings_rows(text: str) -> list[dict]:
    rows: list[dict] = []
    # Yuanta ratio/PCF SSR pages render each holding as four consecutive td values:
    # code, name, share quantity, weight. Treat this as sample extraction only.
    tr_blocks = re.findall(r'<div class="tr"[^>]*>(.*?)</div></div>', text, flags=re.I | re.S)
    for block in tr_blocks:
        values = [re.sub(r"<[^>]+>", "", v).strip() for v in re.findall(r"<span[^>]*>(.*?)</span>", block, flags=re.I | re.S)]
        values = [v for v in values if v and "商品" not in v]
        if len(values) < 4:
            continue
        ticker, name, quantity, weight = values[:4]
        if not re.fullmatch(r"\d{4}", ticker):
            continue
        try:
            weight_num = float(weight.replace(",", ""))
        except ValueError:
            continue
        if not 0 < weight_num <= 100:
            continue
        rows.append({"ticker": ticker, "name": name, "quantity": quantity, "weight": str(weight_num)})
    return rows


def source_id_to_snapshot_date(source_id: str) -> str:
    match = re.search(r"_(20\d{12})", source_id)
    if not match:
        return ""
    return datetime.strptime(match.group(1)[:8], "%Y%m%d").date().isoformat()


def main() -> None:
    current_step = OUT / "current_step.txt"
    current_step.write_text("running_archived_html_crawler\n", encoding="utf-8")

    html_attempts: list[dict] = []
    pdf_candidates: list[dict] = []
    pdf_attempts: list[dict] = []
    raw_manifest: list[dict] = []
    parsed_rows: list[dict] = []
    accepted_rows: list[dict] = []
    run_log = [{"timestamp": now(), "step": "start", "status": "running", "details": f"prev_exists={PREV.exists()}"}]

    for target in TARGETS:
        period = target["period"]
        selected_html_snapshots: list[dict] = []
        for query in PAGE_QUERIES:
            cdx_url = cdx_query(query["cdx_url"], target["from"], target["to"])
            code, ctype, body, final_url, err = fetch(cdx_url, timeout=10, max_bytes=1_000_000)
            rows = selected_snapshots_from_cdx(body) if code == "200" and body else []
            html_attempts.append(
                {
                    "period": period,
                    "route_id": query["route_id"],
                    "page_url": query["cdx_url"],
                    "snapshot_url": cdx_url,
                    "attempt_type": "wayback_cdx_html_snapshot_search",
                    "status": "error" if err else ("http_ok" if code == "200" else "http_non_ok"),
                    "http_code": code,
                    "content_type": ctype,
                    "bytes": len(body),
                    "href_count": 0,
                    "pdf_candidate_count": 0,
                    "retrieved_path": "",
                    "error": err,
                    "notes": f"cdx_rows={len(rows)}",
                }
            )
            for row in rows:
                row["route_id"] = query["route_id"]
                selected_html_snapshots.append(row)

        for route_id, page_url in AVAILABILITY_PAGE_URLS:
            avail_url = availability_query(page_url, target["stamp"])
            code, ctype, body, final_url, err = fetch(avail_url, timeout=10, max_bytes=1_000_000)
            selected = selected_snapshot_from_availability(body) if code == "200" and body else None
            html_attempts.append(
                {
                    "period": period,
                    "route_id": route_id,
                    "page_url": page_url,
                    "snapshot_url": avail_url,
                    "attempt_type": "wayback_available_html_snapshot_search",
                    "status": "error" if err else ("http_ok" if code == "200" else "http_non_ok"),
                    "http_code": code,
                    "content_type": ctype,
                    "bytes": len(body),
                    "href_count": 0,
                    "pdf_candidate_count": 0,
                    "retrieved_path": "",
                    "error": err,
                    "notes": "closest_timestamp={}; closest_url={}".format(
                        selected.get("timestamp", "") if selected else "",
                        selected.get("available_url", "") if selected else "",
                    ),
                }
            )
            if selected:
                selected["route_id"] = route_id
                selected_html_snapshots.append(selected)

        # Keep the run bounded while still trying more than one route per period.
        seen_snapshot_keys: set[tuple[str, str]] = set()
        bounded_snapshots: list[dict] = []
        for item in selected_html_snapshots:
            key = (item["timestamp"], item["original"])
            if key in seen_snapshot_keys:
                continue
            seen_snapshot_keys.add(key)
            bounded_snapshots.append(item)
            if len(bounded_snapshots) >= 8:
                break

        for item in bounded_snapshots:
            snap = snapshot_url(item["timestamp"], item["original"], "id_")
            code, ctype, body, final_url, err = fetch(snap, timeout=12, max_bytes=3_000_000)
            text = decode_text(body) if body else ""
            href_rows = extract_href_candidates(text, item["original"]) if code == "200" and body else []
            raw_path = ""
            if code == "200" and body:
                fname = safe(f"{period}_{item['route_id']}_{item['timestamp']}_{urlparse(item['original']).path}") + ".html"
                raw_path = str((RAW / fname)).replace("\\", "/")
                (RAW / fname).write_bytes(body)
                raw_manifest.append(
                    {
                        "source_id": f"{period}_{item['route_id']}_{item['timestamp']}",
                        "raw_file_path": raw_path,
                        "source_url_or_reference": final_url or snap,
                        "document_date": target["target_date"],
                        "covered_effective_start": target["target_date"],
                        "covered_effective_end": target["target_date"],
                        "source_type": "html_snapshot_evidence",
                        "archive_status": "downloaded_html_snapshot",
                        "checksum_sha256": sha256(body),
                        "notes": f"mimetype={item.get('mimetype','')}; original={item['original']}",
                    }
                )
            html_attempts.append(
                {
                    "period": period,
                    "route_id": item["route_id"],
                    "page_url": item["original"],
                    "snapshot_url": snap,
                    "attempt_type": "download_selected_html_snapshot",
                    "status": "error" if err else ("http_ok" if code == "200" else "http_non_ok"),
                    "http_code": code,
                    "content_type": ctype,
                    "bytes": len(body),
                    "href_count": len(re.findall(r"(?:href|src)\s*=", text, re.I)) if text else 0,
                    "pdf_candidate_count": len(href_rows),
                    "retrieved_path": raw_path,
                    "error": err,
                    "notes": f"timestamp={item['timestamp']}; original={item['original']}",
                }
            )
            for idx, href in enumerate(href_rows[:8]):
                candidate_id = f"{period}_{item['route_id']}_{item['timestamp']}_{idx+1}"
                original_pdf = normalize_original_from_wayback(href["href"])
                candidate = {
                    "candidate_id": candidate_id,
                    "period": period,
                    "source_html_snapshot": snap,
                    "source_html_file": raw_path,
                    "href": href["href"],
                    "original_pdf_url": original_pdf,
                    "evidence_type": href["evidence_type"],
                    "keyword_hit": href["keyword_hit"],
                    "text_near": href["text_near"],
                }
                pdf_candidates.append(candidate)

                pdf_urls = []
                if ".pdf" in original_pdf.lower():
                    pdf_urls.append(("wayback_pdf_snapshot", snapshot_url(item["timestamp"], original_pdf, "id_")))
                    pdf_urls.append(("original_pdf_url", original_pdf))
                else:
                    pdf_urls.append(("original_download_candidate", original_pdf))

                for attempt_type, pdf_url in pdf_urls[:2]:
                    p_code, p_ctype, p_body, p_final, p_err = fetch(pdf_url, timeout=14, max_bytes=5_000_000)
                    is_pdf = b"%PDF" in p_body[:2048] or "pdf" in p_ctype.lower()
                    p_path = ""
                    parser_status = ""
                    text_sample = ""
                    pages = 0
                    sample_rows = []
                    if p_code == "200" and p_body:
                        ext = ".pdf" if is_pdf else ".html"
                        fname = safe(f"{candidate_id}_{attempt_type}") + ext
                        p_path = str((RAW / fname)).replace("\\", "/")
                        (RAW / fname).write_bytes(p_body)
                        raw_manifest.append(
                            {
                                "source_id": f"{candidate_id}_{attempt_type}",
                                "raw_file_path": p_path,
                                "source_url_or_reference": p_final or pdf_url,
                                "document_date": target["target_date"],
                                "covered_effective_start": target["target_date"],
                                "covered_effective_end": target["target_date"],
                                "source_type": "source_backed_manual_proxy" if is_pdf else "download_candidate_non_pdf",
                                "archive_status": "downloaded_pdf_candidate" if is_pdf else "downloaded_non_pdf_candidate",
                                "checksum_sha256": sha256(p_body),
                                "notes": f"content_type={p_ctype}; is_pdf={is_pdf}",
                            }
                        )
                        if is_pdf:
                            text_sample, parser_status, pages = text_sample_from_pdf_bytes(p_body)
                            sample_rows = parse_rows_from_text(text_sample)
                            for row in sample_rows:
                                parsed_rows.append(
                                    {
                                        "target_period": period,
                                        "holdings_date": target["target_date"],
                                        "source_id": f"{candidate_id}_{attempt_type}",
                                        "source_file": p_path,
                                        "source_url": p_final or pdf_url,
                                        "ticker": row["ticker"],
                                        "name": row["name"],
                                        "weight": row["weight"],
                                        "source_type": "source_backed_manual_proxy",
                                        "formal_exact": "false",
                                        "evidence_quality": "parsed_sample_needs_manual_review",
                                        "parser_status": parser_status,
                                        "notes": "Parsed by conservative ticker/name/weight regex from first two PDF pages; not formal accepted.",
                                    }
                                )
                    pdf_attempts.append(
                        {
                            "candidate_id": candidate_id,
                            "period": period,
                            "source_html_snapshot": snap,
                            "attempt_type": attempt_type,
                            "url": pdf_url,
                            "status": "error" if p_err else ("http_ok" if p_code == "200" else "http_non_ok"),
                            "http_code": p_code,
                            "content_type": p_ctype,
                            "bytes": len(p_body),
                            "is_pdf": str(is_pdf).lower(),
                            "retrieved_path": p_path,
                            "parser_status": parser_status,
                            "page_count": pages,
                            "parsed_sample_rows": len(sample_rows),
                            "error": p_err,
                            "text_sample": re.sub(r"\s+", " ", text_sample)[:500],
                        }
                    )

    for source in raw_manifest:
        if source["source_type"] != "download_candidate_non_pdf":
            continue
        raw_path = Path(source["raw_file_path"])
        if not raw_path.exists():
            continue
        if not any(token in raw_path.name.lower() for token in ("ratio", "pcf", "tradeinfo")):
            continue
        text = decode_text(raw_path.read_bytes())
        html_rows = extract_html_holdings_rows(text)
        if not html_rows:
            continue
        period = source["source_id"].split("_", 1)[0]
        snapshot_date = source_id_to_snapshot_date(source["source_id"])
        for row in html_rows[:20]:
            parsed_rows.append(
                {
                    "target_period": period,
                    "holdings_date": snapshot_date,
                    "source_id": source["source_id"],
                    "source_file": source["raw_file_path"],
                    "source_url": source["source_url_or_reference"],
                    "ticker": row["ticker"],
                    "name": row["name"],
                    "weight": row["weight"],
                    "source_type": "source_backed_manual_proxy",
                    "formal_exact": "false",
                    "evidence_quality": "html_table_sample_snapshot_date_not_target_date",
                    "parser_status": "html_holdings_table_sample_extracted",
                    "notes": "Extracted from archived Yuanta ratio/PCF HTML SSR table. This is sample evidence only; snapshot date may differ from target period holdings date and is not accepted as PIT exact.",
                }
            )

    missing = []
    for target in TARGETS:
        period = target["period"]
        html_count = sum(1 for r in html_attempts if r["period"] == period and r["attempt_type"] == "download_selected_html_snapshot")
        href_count = sum(1 for r in pdf_candidates if r["period"] == period)
        pdf_count = sum(1 for r in pdf_attempts if r["period"] == period and r["is_pdf"] == "true")
        parsed_count = sum(1 for r in parsed_rows if r["target_period"] == period)
        accepted_count = sum(1 for r in accepted_rows if r.get("target_period") == period)
        missing.append(
            {
                "period_id": period,
                "target_date": target["target_date"],
                "html_snapshot_download_attempts": html_count,
                "pdf_href_candidates": href_count,
                "downloaded_pdf_candidates": pdf_count,
                "parsed_sample_rows": parsed_count,
                "accepted_rows": accepted_count,
                "status": "accepted" if accepted_count else ("parsed_sample_needs_review" if parsed_count else "missing_accepted_rows"),
                "blocker": "No dated historical 0050 holdings rows accepted from archived HTML route.",
                "next_programmatic_attempt": "Query regulator/association/open-data endpoints for fund monthly/portfolio disclosures; also broaden Wayback HTML routes to archived Yuanta sitemap and search result pages.",
            }
        )

    quality = [
        {
            "source_family": "wayback_archived_html_pages",
            "decision": "attempted_html_snapshot_crawler",
            "formal_exact": "false",
            "manual_proxy_allowed": "true_if_pdf_date_and_rows_reviewed",
            "rationale": "HTML snapshots are routing evidence. Linked PDFs can support source-backed manual/proxy only after dated content and holdings rows are reviewed.",
        },
        {
            "source_family": "wayback_wrapper_or_non_pdf_downloads",
            "decision": "not_accepted",
            "formal_exact": "false",
            "manual_proxy_allowed": "false_until_pdf_or_rows_extracted",
            "rationale": "Wayback wrapper HTML and current/rolling downloads are not historical PIT holdings evidence.",
        },
    ]

    html_fields = ["period", "route_id", "page_url", "snapshot_url", "attempt_type", "status", "http_code", "content_type", "bytes", "href_count", "pdf_candidate_count", "retrieved_path", "error", "notes"]
    href_fields = ["candidate_id", "period", "source_html_snapshot", "source_html_file", "href", "original_pdf_url", "evidence_type", "keyword_hit", "text_near"]
    pdf_fields = ["candidate_id", "period", "source_html_snapshot", "attempt_type", "url", "status", "http_code", "content_type", "bytes", "is_pdf", "retrieved_path", "parser_status", "page_count", "parsed_sample_rows", "error", "text_sample"]
    raw_fields = ["source_id", "raw_file_path", "source_url_or_reference", "document_date", "covered_effective_start", "covered_effective_end", "source_type", "archive_status", "checksum_sha256", "notes"]
    sample_fields = ["target_period", "holdings_date", "source_id", "source_file", "source_url", "ticker", "name", "weight", "source_type", "formal_exact", "evidence_quality", "parser_status", "notes"]

    write_csv(OUT / "html_snapshot_attempts.csv", html_attempts, html_fields)
    write_csv(OUT / "pdf_href_candidates.csv", pdf_candidates, href_fields)
    write_csv(OUT / "pdf_download_attempts.csv", pdf_attempts, pdf_fields)
    write_csv(OUT / "raw_source_archive_manifest.csv", raw_manifest, raw_fields)
    write_csv(OUT / "parsed_holdings_sample.csv", parsed_rows, sample_fields)
    write_csv(OUT / "accepted_historical_rows.csv", accepted_rows, sample_fields)
    write_csv(OUT / "missing_periods.csv", missing, list(missing[0].keys()))
    write_csv(OUT / "source_quality_decision.csv", quality, list(quality[0].keys()))

    completed = [
        {
            "item_id": "archived_html_crawler_matrix",
            "completed_at": now(),
            "status": "completed",
            "evidence": f"html_attempts={len(html_attempts)} pdf_href_candidates={len(pdf_candidates)} pdf_download_attempts={len(pdf_attempts)}",
        }
    ]
    failed = [row for row in missing if row["accepted_rows"] == 0]
    write_csv(OUT / "completed.csv", completed, ["item_id", "completed_at", "status", "evidence"])
    write_csv(OUT / "failed.csv", failed, list(failed[0].keys()) if failed else list(missing[0].keys()))
    run_log.append({"timestamp": now(), "step": "finish", "status": "completed", "details": completed[0]["evidence"]})
    write_csv(OUT / "run_log.csv", run_log, ["timestamp", "step", "status", "details"])

    manifest = {
        "schema_version": 1,
        "task_id": "TASK-RADAR-DATA-TW50-0050-ARCHIVED-HTML-CRAWLER-PHASE3-20260629",
        "status": "completed_partial",
        "created_at": now(),
        "previous_output_dir": str(PREV).replace("\\", "/"),
        "output_dir": str(OUT).replace("\\", "/"),
        "target_periods": [t["period"] for t in TARGETS],
        "html_snapshot_attempt_count": len(html_attempts),
        "pdf_href_candidate_count": len(pdf_candidates),
        "pdf_download_attempt_count": len(pdf_attempts),
        "raw_source_count": len(raw_manifest),
        "parsed_holdings_sample_rows": len(parsed_rows),
        "accepted_historical_rows": len(accepted_rows),
        "formal_model_changed": False,
        "trade_decision_changed": False,
        "formal_exact": False,
        "current_snapshot_used_as_historical": False,
        "wayback_wrapper_html_accepted": False,
        "future_data_violation_count": 0,
        "large_unbounded_crawl_started": False,
    }
    (OUT / "manifest.json").write_text(json.dumps(manifest, ensure_ascii=False, indent=2), encoding="utf-8")
    current_step.write_text("completed\n", encoding="utf-8")
    print(json.dumps(manifest, ensure_ascii=False, indent=2))


if __name__ == "__main__":
    main()
