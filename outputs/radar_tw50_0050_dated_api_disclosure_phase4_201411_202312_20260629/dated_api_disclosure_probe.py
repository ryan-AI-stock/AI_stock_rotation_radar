from __future__ import annotations

import csv
import hashlib
import html
import json
import re
import time
from pathlib import Path
from urllib.parse import quote

import requests

OUT = Path("outputs/radar_tw50_0050_dated_api_disclosure_phase4_201411_202312_20260629")
PREV = Path("outputs/radar_tw50_0050_archived_html_crawler_201411_202312_20260629")
PREV_RAW = PREV / "raw_sources"
RAW = OUT / "raw_sources"
RAW.mkdir(parents=True, exist_ok=True)

TARGETS = [
    {"period": "2014Q4", "target_date": "2014-12-31", "stamp": "20141231", "from": "201410", "to": "201501"},
    {"period": "2016Q1", "target_date": "2016-03-31", "stamp": "20160331", "from": "201601", "to": "201604"},
    {"period": "2021Q4", "target_date": "2021-12-31", "stamp": "20211231", "from": "202110", "to": "202201"},
    {"period": "2023Q4", "target_date": "2023-12-31", "stamp": "20231231", "from": "202310", "to": "202401"},
]

HEADERS = {
    "User-Agent": "Mozilla/5.0 RadarDataDatedApiProbe/1.0",
    "Accept": "application/json,text/html,application/xml,text/csv,application/pdf,*/*",
}

# Explicit bounded disclosure/API routes. Some are expected to fail; the point is
# reproducible evidence and a clear next route, not silent source_pending.
SOURCE_ROUTES = [
    ("yuanta_etfapi_product_0050", "api_payload", "https://etfapi.yuantaetfs.com/api/ETF/GetETFInfo?fundid=0050"),
    ("yuanta_etfapi_ratio_0050", "api_payload", "https://etfapi.yuantaetfs.com/api/ETF/GetHoldStock?fundid=0050"),
    ("yuanta_etfapi_pcf_0050", "api_payload", "https://etfapi.yuantaetfs.com/api/ETF/GetPCF?fundid=0050"),
    ("yuanta_etfapi_file_downloads", "api_payload", "https://etfapi.yuantaetfs.com/api/ETF/GetFileDownload?fundid=0050"),
    ("yuanta_etfapi_product_list", "api_payload", "https://etfapi.yuantaetfs.com/api/ETF/GetETFList"),
    ("yuanta_current_ratio_page", "html_payload", "https://www.yuantaetfs.com/product/detail/0050/ratio"),
    ("yuanta_current_download_page", "html_payload", "https://www.yuantaetfs.com/product/detail/0050/download"),
    ("sitca_fund_query_home", "disclosure", "https://www.sitca.org.tw/ROC/Industry/IN2421.aspx"),
    ("sitca_etf_home", "disclosure", "https://www.sitca.org.tw/ROC/ETF/"),
    ("mops_home_fund_keyword", "disclosure", "https://mops.twse.com.tw/mops/web/index"),
    ("twse_etf_home", "twse_index_proxy_candidate", "https://www.twse.com.tw/zh/ETF/list"),
    ("taiwan_index_home", "twse_index_proxy_candidate", "https://www.taiwanindex.com.tw/index/index/TW50"),
]


def now() -> str:
    return time.strftime("%Y-%m-%dT%H:%M:%S+08:00")


def safe(text: str, limit: int = 160) -> str:
    return re.sub(r"[^A-Za-z0-9_.-]+", "_", text).strip("_")[:limit] or "item"


def write_csv(path: Path, rows: list[dict], fields: list[str]) -> None:
    with path.open("w", newline="", encoding="utf-8") as fh:
        writer = csv.DictWriter(fh, fieldnames=fields, extrasaction="ignore")
        writer.writeheader()
        writer.writerows(rows)


def sha256(body: bytes) -> str:
    return hashlib.sha256(body).hexdigest()


def fetch(url: str, timeout: int = 5, max_bytes: int = 2_000_000) -> tuple[str, str, bytes, str, str]:
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


def decode_text(body: bytes) -> str:
    return body.decode("utf-8", errors="replace")


def wayback_availability(url: str, stamp: str) -> str:
    return "https://archive.org/wayback/available?url=" + quote(url, safe="") + "&timestamp=" + stamp


def wayback_direct(url: str, stamp: str) -> str:
    return f"https://web.archive.org/web/{stamp}id_/{url}"


def wayback_cdx(url: str, start: str, end: str) -> str:
    return (
        "https://web.archive.org/cdx?url="
        + quote(url, safe="*")
        + f"&from={start}&to={end}&output=json&fl=timestamp,original,statuscode,mimetype,digest"
        + "&filter=statuscode:200&collapse=digest&limit=8"
    )


def closest_from_availability(body: bytes) -> tuple[str, str]:
    try:
        payload = json.loads(decode_text(body))
    except Exception:
        return "", ""
    closest = payload.get("archived_snapshots", {}).get("closest", {}) if isinstance(payload, dict) else {}
    return closest.get("timestamp", ""), closest.get("url", "")


def extract_routes_from_phase3_html() -> list[dict]:
    routes: dict[str, dict] = {}
    if not PREV_RAW.exists():
        return []
    for path in sorted(PREV_RAW.glob("*.html"))[:40]:
        text = html.unescape(path.read_text(encoding="utf-8", errors="replace")).replace("\\u002F", "/")
        for match in re.finditer(r"https?://(?:etfapi\.yuantaetfs\.com|api\.yuantafunds\.com)[^\"'<>\\\s]+", text, flags=re.I):
            url = match.group(0).rstrip("),.;")
            routes.setdefault(url, {"route_id": "phase3_extracted_api_url", "source_type": "api_payload", "url": url, "source_file": str(path).replace("\\", "/")})
        for match in re.finditer(r'"/_nuxt/([^"]+?\.js)"|src="/(_nuxt/[^"]+?\.js)"', text, flags=re.I):
            part = next(g for g in match.groups() if g)
            url = "https://www.yuantaetfs.com/" + part.lstrip("/")
            routes.setdefault(url, {"route_id": "phase3_extracted_nuxt_js", "source_type": "nuxt_payload", "url": url, "source_file": str(path).replace("\\", "/")})
    return list(routes.values())[:30]


def detect_date_fields(text: str) -> tuple[str, str]:
    keys = ["DataDate", "dataDate", "Date", "date", "UpdateDate", "updateDate", "NetAssetValueDate", "資料日期", "持股日期"]
    for key in keys:
        match = re.search(rf"{re.escape(key)}[\"'\s:=：]{{1,12}}([0-9]{{4}}[-/]?[0-9]{{2}}[-/]?[0-9]{{2}}|[0-9]{{8}}|[0-9]{{3}}/[0-9]{{2}}/[0-9]{{2}})", text)
        if match:
            return key, match.group(1)
    match = re.search(r"(20[0-3][0-9])[-/]?([01][0-9])[-/]?([0-3][0-9])", text)
    if match:
        return "generic_date_regex", "-".join(match.groups())
    return "", ""


def normalize_date(raw: str) -> str:
    raw = raw.strip()
    if re.fullmatch(r"20\d{6}", raw):
        return f"{raw[:4]}-{raw[4:6]}-{raw[6:8]}"
    if re.fullmatch(r"20\d{2}[-/]\d{2}[-/]\d{2}", raw):
        return raw.replace("/", "-")
    if re.fullmatch(r"\d{3}/\d{2}/\d{2}", raw):
        y, m, d = raw.split("/")
        return f"{int(y)+1911:04d}-{m}-{d}"
    return raw


def parse_holdings_rows_from_text(text: str) -> list[dict]:
    rows: list[dict] = []
    for match in re.finditer(r'"(?:StockCode|Code|code|股票代號)"\s*:\s*"?(?P<ticker>\d{4})"?(?P<near>.{0,500})', text, flags=re.I | re.S):
        ticker = match.group("ticker")
        near = match.group("near")
        name_match = re.search(r'"(?:StockName|Name|name|股票名稱)"\s*:\s*"(?P<name>[^"]{1,30})"', near)
        weight_match = re.search(r'"(?:Weight|Ratio|ratio|Proportion|權重|持股比率)"\s*:\s*"?(?P<weight>[0-9]+(?:\.[0-9]+)?)', near, flags=re.I)
        if name_match:
            rows.append({"ticker": ticker, "name": name_match.group("name"), "weight": weight_match.group("weight") if weight_match else ""})
    if rows:
        return rows[:80]
    for ticker, name, weight in re.findall(r"\b(\d{4})\b\s+([\u4e00-\u9fffA-Za-z0-9（）()\-\.]{2,30})\s+([0-9]+(?:\.[0-9]+)?)\s*%?", text):
        if ticker.startswith("00"):
            continue
        if "endobj" in name.lower() or name.isdigit() or not re.search(r"[\u4e00-\u9fffA-Za-z]", name):
            continue
        try:
            weight_num = float(weight)
        except ValueError:
            continue
        if not 0 < weight_num <= 100:
            continue
        rows.append({"ticker": ticker, "name": name, "weight": weight})
        if len(rows) >= 80:
            break
    return rows


def probe_one(period: dict, route_id: str, source_type: str, query_url: str, attempts: list[dict], payloads: list[dict], disclosures: list[dict], raw_manifest: list[dict], parsed: list[dict], accepted: list[dict]) -> None:
    probes = [
        ("direct", query_url),
        ("wayback_available", wayback_availability(query_url, period["stamp"])),
    ]
    for attempt_type, url in probes:
        code, ctype, body, final_url, err = fetch(url, timeout=5, max_bytes=2_000_000)
        status = "error" if err else ("http_ok" if code and int(code) < 400 else "http_non_ok")
        retrieved_path = ""
        date_field, raw_date = detect_date_fields(decode_text(body) if body else "")
        holdings_date = normalize_date(raw_date) if raw_date else ""
        rows = parse_holdings_rows_from_text(decode_text(body)) if body and code == "200" else []
        notes = ""
        if attempt_type == "wayback_available" and body:
            closest_ts, closest_url = closest_from_availability(body)
            notes = f"closest_timestamp={closest_ts}; closest_url={closest_url}"
        if body and code == "200" and (rows or "json" in ctype.lower() or "html" in ctype.lower() or "text" in ctype.lower()):
            ext = ".json" if "json" in ctype.lower() or body[:1] in (b"{", b"[") else ".html"
            fname = safe(f"{period['period']}_{route_id}_{attempt_type}") + ext
            path = RAW / fname
            path.write_bytes(body)
            retrieved_path = str(path).replace("\\", "/")
            raw_manifest.append(
                {
                    "source_id": safe(f"{period['period']}_{route_id}_{attempt_type}"),
                    "raw_file_path": retrieved_path,
                    "source_url_or_reference": final_url or url,
                    "document_date": holdings_date,
                    "covered_effective_start": period["target_date"],
                    "covered_effective_end": period["target_date"],
                    "source_type": source_type,
                    "archive_status": "downloaded_payload_candidate",
                    "checksum_sha256": sha256(body),
                    "notes": f"attempt_type={attempt_type}; content_type={ctype}; row_count={len(rows)}",
                }
            )
        row = {
            "source": route_id,
            "target_period": period["period"],
            "query_url": url,
            "attempt_type": attempt_type,
            "status": status,
            "http_code": code,
            "content_type": ctype,
            "date_field_detected": date_field,
            "holdings_date": holdings_date,
            "row_count": len(rows),
            "retrieved_path": retrieved_path,
            "error": err,
            "notes": notes,
        }
        attempts.append(row)
        candidate_row = {
            "source": route_id,
            "target_period": period["period"],
            "source_type": source_type,
            "query_url": url,
            "attempt_type": attempt_type,
            "holdings_date": holdings_date,
            "date_field_detected": date_field,
            "row_count": len(rows),
            "retrieved_path": retrieved_path,
            "acceptance_decision": "accepted" if holdings_date == period["target_date"] and rows else ("sample_only_date_mismatch" if rows else "not_parsed"),
            "notes": notes,
        }
        if source_type in ("api_payload", "nuxt_payload", "html_payload"):
            payloads.append(candidate_row)
        else:
            disclosures.append(candidate_row)
        if rows:
            for item in rows[:20]:
                parsed_row = {
                    "target_period": period["period"],
                    "holdings_date": holdings_date,
                    "source_id": route_id,
                    "source_file": retrieved_path,
                    "source_url": final_url or url,
                    "ticker": item["ticker"],
                    "name": item["name"],
                    "weight": item.get("weight", ""),
                    "source_type": "source_backed_manual_proxy",
                    "formal_exact": "false",
                    "evidence_quality": "accepted_date_matched" if holdings_date == period["target_date"] else "sample_only_date_mismatch_or_missing_date",
                    "parser_status": "dated_api_disclosure_parser_extracted_rows",
                    "notes": f"attempt_type={attempt_type}; date_field={date_field}; target_date={period['target_date']}",
                }
                parsed.append(parsed_row)
                if holdings_date == period["target_date"]:
                    accepted.append(parsed_row)


def main() -> None:
    (OUT / "current_step.txt").write_text("running_dated_api_disclosure_probe\n", encoding="utf-8")
    run_log = [{"timestamp": now(), "step": "start", "status": "running", "details": f"prev_exists={PREV.exists()}"}]
    attempts: list[dict] = []
    payloads: list[dict] = []
    disclosures: list[dict] = []
    raw_manifest: list[dict] = []
    parsed: list[dict] = []
    accepted: list[dict] = []

    extracted = extract_routes_from_phase3_html()
    route_rows = [{"route_id": rid, "source_type": stype, "url": url, "source_file": ""} for rid, stype, url in SOURCE_ROUTES]
    route_rows.extend(extracted)
    dedup: dict[str, dict] = {}
    for row in route_rows:
        dedup.setdefault(row["url"], row)
    route_rows = list(dedup.values())[:20]

    for period in TARGETS:
        # Keep bounded per target period; phase 4 evidence focuses on dated API/disclosure routes.
        for route in route_rows[:14]:
            probe_one(period, route["route_id"], route["source_type"], route["url"], attempts, payloads, disclosures, raw_manifest, parsed, accepted)

    sample_fields = ["target_period", "holdings_date", "source_id", "source_file", "source_url", "ticker", "name", "weight", "source_type", "formal_exact", "evidence_quality", "parser_status", "notes"]
    write_csv(OUT / "source_probe_attempts.csv", attempts, ["source", "target_period", "query_url", "attempt_type", "status", "http_code", "content_type", "date_field_detected", "holdings_date", "row_count", "retrieved_path", "error", "notes"])
    candidate_fields = ["source", "target_period", "source_type", "query_url", "attempt_type", "holdings_date", "date_field_detected", "row_count", "retrieved_path", "acceptance_decision", "notes"]
    write_csv(OUT / "api_payload_candidates.csv", payloads, candidate_fields)
    write_csv(OUT / "disclosure_candidates.csv", disclosures, candidate_fields)
    write_csv(OUT / "raw_source_archive_manifest.csv", raw_manifest, ["source_id", "raw_file_path", "source_url_or_reference", "document_date", "covered_effective_start", "covered_effective_end", "source_type", "archive_status", "checksum_sha256", "notes"])
    write_csv(OUT / "parsed_holdings_sample.csv", parsed, sample_fields)
    write_csv(OUT / "accepted_historical_rows.csv", accepted, sample_fields)

    missing = []
    for period in TARGETS:
        pc = sum(1 for row in parsed if row["target_period"] == period["period"])
        ac = sum(1 for row in accepted if row["target_period"] == period["period"])
        missing.append(
            {
                "period_id": period["period"],
                "target_date": period["target_date"],
                "source_probe_attempts": sum(1 for row in attempts if row["target_period"] == period["period"]),
                "api_payload_candidates": sum(1 for row in payloads if row["target_period"] == period["period"]),
                "disclosure_candidates": sum(1 for row in disclosures if row["target_period"] == period["period"]),
                "parsed_sample_rows": pc,
                "accepted_rows": ac,
                "status": "accepted" if ac else ("parsed_sample_needs_date_match" if pc else "missing_accepted_rows"),
                "blocker": "No payload/disclosure produced holdings rows with source_date/holdings_date equal to target period.",
                "next_programmatic_attempt": "Reverse engineer dated etfapi endpoints from Nuxt JS chunks, then query archived API JSON by snapshot timestamp; also probe SITCA monthly portfolio form POST parameters with fund id 1066/0050.",
            }
        )
    write_csv(OUT / "missing_periods.csv", missing, list(missing[0].keys()))
    quality = [
        {"source_family": "yuanta_etfapi_or_nuxt_payload", "decision": "attempted_dated_route_probe", "formal_exact": "false", "manual_proxy_allowed": "true_if_date_matched", "rationale": "Can support source-backed manual/proxy only when payload exposes holdings_date/source_date matching target period and holdings rows."},
        {"source_family": "sitca_mops_twse_taiwan_index", "decision": "attempted_disclosure_or_proxy_route_probe", "formal_exact": "false", "manual_proxy_allowed": "source_dependent", "rationale": "Regulator/disclosure routes may support accepted rows if date and fund identity are explicit; Taiwan Index constituents remain proxy unless tied to ETF holdings."},
        {"source_family": "date_mismatched_or_current_payload", "decision": "not_accepted", "formal_exact": "false", "manual_proxy_allowed": "sample_only", "rationale": "Rows without target holdings_date/source_date are parser samples only."},
    ]
    write_csv(OUT / "source_quality_decision.csv", quality, list(quality[0].keys()))
    completed = [{"item_id": "dated_api_disclosure_probe", "completed_at": now(), "status": "completed_partial", "evidence": f"attempts={len(attempts)} parsed={len(parsed)} accepted={len(accepted)}"}]
    write_csv(OUT / "completed.csv", completed, ["item_id", "completed_at", "status", "evidence"])
    write_csv(OUT / "failed.csv", [row for row in missing if row["accepted_rows"] == 0], list(missing[0].keys()))
    run_log.append({"timestamp": now(), "step": "finish", "status": "completed", "details": completed[0]["evidence"]})
    write_csv(OUT / "run_log.csv", run_log, ["timestamp", "step", "status", "details"])
    manifest = {
        "schema_version": 1,
        "task_id": "TASK-RADAR-DATA-TW50-0050-DATED-API-DISCLOSURE-PHASE4-20260629",
        "status": "completed_partial" if not accepted else "completed_with_accepted_rows",
        "created_at": now(),
        "previous_output_dir": str(PREV).replace("\\", "/"),
        "output_dir": str(OUT).replace("\\", "/"),
        "target_periods": [p["period"] for p in TARGETS],
        "source_probe_attempt_count": len(attempts),
        "api_payload_candidate_count": len(payloads),
        "disclosure_candidate_count": len(disclosures),
        "raw_source_count": len(raw_manifest),
        "parsed_holdings_sample_rows": len(parsed),
        "accepted_historical_rows": len(accepted),
        "formal_model_changed": False,
        "trade_decision_changed": False,
        "formal_exact": False,
        "current_snapshot_used_as_historical": False,
        "date_mismatched_payload_accepted": False,
        "future_data_violation_count": 0,
        "large_unbounded_crawl_started": False,
    }
    (OUT / "manifest.json").write_text(json.dumps(manifest, ensure_ascii=False, indent=2), encoding="utf-8")
    (OUT / "current_step.txt").write_text("completed\n", encoding="utf-8")
    print(json.dumps(manifest, ensure_ascii=False, indent=2))


if __name__ == "__main__":
    main()
