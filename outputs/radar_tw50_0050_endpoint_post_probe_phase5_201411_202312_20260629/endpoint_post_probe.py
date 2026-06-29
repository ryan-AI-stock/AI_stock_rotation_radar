from __future__ import annotations

import csv
import hashlib
import html
import json
import re
import time
from pathlib import Path
from urllib.parse import parse_qsl, quote, urlencode, urljoin, urlparse

import requests

OUT = Path("outputs/radar_tw50_0050_endpoint_post_probe_phase5_201411_202312_20260629")
PHASE3 = Path("outputs/radar_tw50_0050_archived_html_crawler_201411_202312_20260629")
PHASE4 = Path("outputs/radar_tw50_0050_dated_api_disclosure_phase4_201411_202312_20260629")
RAW = OUT / "raw_sources"
RAW.mkdir(parents=True, exist_ok=True)

TARGETS = [
    {"period": "2014Q4", "target_date": "2014-12-31", "month": "201412", "roc_month": "10312", "stamp": "20141231"},
    {"period": "2016Q1", "target_date": "2016-03-31", "month": "201603", "roc_month": "10503", "stamp": "20160331"},
    {"period": "2021Q4", "target_date": "2021-12-31", "month": "202112", "roc_month": "11012", "stamp": "20211231"},
    {"period": "2023Q4", "target_date": "2023-12-31", "month": "202312", "roc_month": "11212", "stamp": "20231231"},
]

HEADERS = {
    "User-Agent": "Mozilla/5.0 RadarDataPhase5/1.0",
    "Accept": "application/json,text/html,application/xml,text/csv,*/*",
}

KNOWN_ENDPOINTS = [
    "https://etfapi.yuantaetfs.com/api/ETF/GetETFInfo",
    "https://etfapi.yuantaetfs.com/api/ETF/GetHoldStock",
    "https://etfapi.yuantaetfs.com/api/ETF/GetPCF",
    "https://etfapi.yuantaetfs.com/api/ETF/GetFileDownload",
    "https://etfapi.yuantaetfs.com/api/ETF/GetETFList",
    "https://api.yuantafunds.com/ECAPI/api/ETF/GetHoldStock",
    "https://api.yuantafunds.com/ECAPI/api/ETF/GetPCF",
    "https://api.yuantafunds.com/ECAPI/api/ETF/GetFileDownload",
]

FORM_PAGES = [
    ("sitca_in2421", "https://www.sitca.org.tw/ROC/Industry/IN2421.aspx"),
    ("sitca_etf_root", "https://www.sitca.org.tw/ROC/ETF/"),
    ("mops_index", "https://mops.twse.com.tw/mops/web/index"),
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


def short_id(text: str) -> str:
    return hashlib.sha1(text.encode("utf-8", errors="ignore")).hexdigest()[:12]


def fetch(method: str, url: str, data: dict | None = None, timeout: int = 3, max_bytes: int = 1_000_000) -> tuple[str, str, bytes, str, str]:
    try:
        with requests.request(method, url, headers=HEADERS, data=data, timeout=(4, timeout), stream=True, allow_redirects=True) as resp:
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


def decode(body: bytes) -> str:
    return body.decode("utf-8", errors="replace")


def wayback_available(url: str, stamp: str) -> str:
    return "https://archive.org/wayback/available?url=" + quote(url, safe="") + "&timestamp=" + stamp


def wayback_direct(url: str, stamp: str) -> str:
    return f"https://web.archive.org/web/{stamp}id_/{url}"


def extract_nuxt_chunks() -> list[dict]:
    rows: dict[str, dict] = {}
    for root in [PHASE3 / "raw_sources", PHASE4 / "raw_sources"]:
        if not root.exists():
            continue
        for path in sorted(root.glob("*.html"))[:80]:
            text = html.unescape(path.read_text(encoding="utf-8", errors="replace")).replace("\\u002F", "/")
            timestamp = ""
            m_ts = re.search(r"_(20\d{12})", path.name)
            if m_ts:
                timestamp = m_ts.group(1)
            for match in re.finditer(r'(?:src|href)="([^"]*/_nuxt/[^"]+?\.js)"|["\'](/_nuxt/[^"\']+?\.js)["\']', text, flags=re.I):
                part = next(g for g in match.groups() if g)
                url = urljoin("https://www.yuantaetfs.com/", part)
                rows.setdefault(url, {"chunk_url": url, "source_file": str(path).replace("\\", "/"), "source_timestamp": timestamp})
    return list(rows.values())[:24]


def extract_api_urls_from_text(text: str) -> list[str]:
    text = html.unescape(text).replace("\\u002F", "/")
    urls = set()
    for match in re.finditer(r"https?://(?:etfapi\.yuantaetfs\.com|api\.yuantafunds\.com)[^\"'<>\\\s)]+", text, flags=re.I):
        urls.add(match.group(0).rstrip("),.;"))
    for match in re.finditer(r'["\'](/(?:api|ECAPI)/[^"\']{3,120})["\']', text, flags=re.I):
        urls.add(urljoin("https://etfapi.yuantaetfs.com/", match.group(1)))
    return sorted(urls)


def build_param_urls(base_url: str, target: dict) -> list[str]:
    parsed = urlparse(base_url)
    base_q = dict(parse_qsl(parsed.query))
    base = base_url.split("?", 1)[0]
    combos = [
        {"fundid": "0050"},
        {"fundId": "0050"},
        {"FundID": "0050"},
        {"fundid": "1066"},
        {"code": "0050"},
        {"fundid": "0050", "date": target["target_date"]},
        {"fundid": "0050", "DataDate": target["target_date"]},
        {"fundid": "0050", "month": target["month"]},
        {"fundid": "1066", "month": target["month"]},
    ]
    out = []
    for combo in combos:
        params = dict(base_q)
        params.update(combo)
        out.append(base + "?" + urlencode(params))
    return list(dict.fromkeys(out))[:3]


def detect_date(text: str, skip_wayback_metadata: bool) -> tuple[str, str]:
    if skip_wayback_metadata:
        return "", ""
    for key in ["DataDate", "dataDate", "Date", "date", "UpdateDate", "updateDate", "資料日期", "持股日期", "年月"]:
        m = re.search(rf"{re.escape(key)}[\"'\s:=：]{{1,12}}([0-9]{{4}}[-/]?[0-9]{{2}}[-/]?[0-9]{{2}}|[0-9]{{6}}|[0-9]{{8}}|[0-9]{{3}}/?[0-9]{{2}})", text)
        if m:
            return key, normalize_date(m.group(1))
    return "", ""


def normalize_date(raw: str) -> str:
    raw = raw.strip().replace("/", "-")
    if re.fullmatch(r"20\d{6}", raw):
        return f"{raw[:4]}-{raw[4:6]}-{raw[6:8]}"
    if re.fullmatch(r"20\d{4}", raw):
        return f"{raw[:4]}-{raw[4:6]}"
    if re.fullmatch(r"\d{3}-?\d{2}", raw):
        raw = raw.replace("-", "")
        return f"{int(raw[:3]) + 1911:04d}-{raw[3:5]}"
    if re.fullmatch(r"\d{3}-?\d{2}-?\d{2}", raw):
        raw = raw.replace("-", "")
        return f"{int(raw[:3]) + 1911:04d}-{raw[3:5]}-{raw[5:7]}"
    if re.fullmatch(r"20\d{2}-\d{2}-\d{2}", raw):
        return raw
    return raw


def target_date_match(holdings_date: str, target: dict) -> bool:
    return holdings_date in {target["target_date"], target["target_date"][:7], target["month"][:4] + "-" + target["month"][4:6]}


def parse_rows(text: str) -> list[dict]:
    rows: list[dict] = []
    for m in re.finditer(r'"(?:StockCode|Code|code|股票代號)"\s*:\s*"?(?P<ticker>\d{4})"?(?P<near>.{0,500})', text, flags=re.I | re.S):
        near = m.group("near")
        name = re.search(r'"(?:StockName|Name|name|股票名稱)"\s*:\s*"(?P<name>[^"]{1,30})"', near)
        weight = re.search(r'"(?:Weight|Ratio|ratio|Proportion|權重|持股比率)"\s*:\s*"?(?P<weight>[0-9]+(?:\.[0-9]+)?)', near, flags=re.I)
        if name:
            rows.append({"ticker": m.group("ticker"), "name": name.group("name"), "weight": weight.group("weight") if weight else ""})
    return rows[:80]


def extract_forms(page_id: str, page_url: str, text: str) -> list[dict]:
    forms = []
    for idx, block in enumerate(re.findall(r"<form\b.*?</form>", text, flags=re.I | re.S), 1):
        action = re.search(r'action=["\']([^"\']*)', block, flags=re.I)
        method = re.search(r'method=["\']([^"\']*)', block, flags=re.I)
        hidden = re.findall(r'<input[^>]+type=["\']hidden["\'][^>]*>', block, flags=re.I)
        fields = []
        for item in hidden[:30]:
            name = re.search(r'name=["\']([^"\']+)', item, flags=re.I)
            value = re.search(r'value=["\']([^"\']*)', item, flags=re.I)
            if name:
                fields.append(f"{name.group(1)}={value.group(1) if value else ''}")
        forms.append(
            {
                "form_id": f"{page_id}_form_{idx}",
                "page_url": page_url,
                "method": (method.group(1).upper() if method else "GET"),
                "action": urljoin(page_url, action.group(1) if action else page_url),
                "hidden_field_count": len(hidden),
                "hidden_fields_sample": ";".join(fields)[:500],
            }
        )
    return forms


def main() -> None:
    (OUT / "current_step.txt").write_text("running_endpoint_post_probe\n", encoding="utf-8")
    run_log = [{"timestamp": now(), "step": "start", "status": "running", "details": "phase5 endpoint/post probe started"}]
    nuxt_chunks = extract_nuxt_chunks()
    api_candidates = []
    api_attempts = []
    form_candidates = []
    post_attempts = []
    raw_manifest = []
    parsed = []
    accepted = []

    endpoint_urls = set(KNOWN_ENDPOINTS)
    for chunk in nuxt_chunks[:12]:
        for attempt_type, url in [("direct_chunk", chunk["chunk_url"]), ("wayback_chunk", wayback_direct(chunk["chunk_url"], chunk["source_timestamp"] or "20211231"))]:
            code, ctype, body, final_url, err = fetch("GET", url, timeout=3, max_bytes=1_000_000)
            retrieved = ""
            endpoint_count = 0
            if code == "200" and body:
                text = decode(body)
                endpoints = extract_api_urls_from_text(text)
                endpoint_count = len(endpoints)
                endpoint_urls.update(endpoints[:20])
                fname = safe(f"chunk_{attempt_type}_{Path(urlparse(url).path).name}") + ".js"
                path = RAW / fname
                path.write_bytes(body)
                retrieved = str(path).replace("\\", "/")
                raw_manifest.append({"source_id": safe(fname), "raw_file_path": retrieved, "source_url_or_reference": final_url or url, "document_date": "", "covered_effective_start": "", "covered_effective_end": "", "source_type": "nuxt_chunk", "archive_status": "downloaded", "checksum_sha256": sha256(body), "notes": f"endpoint_count={endpoint_count}"})
            row = dict(chunk)
            row.update({"attempt_type": attempt_type, "status": "error" if err else ("http_ok" if code == "200" else "http_non_ok"), "http_code": code, "content_type": ctype, "bytes": len(body), "endpoint_count": endpoint_count, "retrieved_path": retrieved, "error": err})
            nuxt_chunks.append(row) if False else None
            api_attempts.append({"source": "nuxt_chunk_fetch", "target_period": "all", "query_url": url, "attempt_type": attempt_type, "status": row["status"], "http_code": code, "content_type": ctype, "date_field_detected": "", "holdings_date": "", "row_count": endpoint_count, "retrieved_path": retrieved, "error": err, "notes": "chunk endpoint discovery"})

    for endpoint in sorted(endpoint_urls)[:26]:
        api_candidates.append({"endpoint_id": safe(endpoint), "endpoint_url": endpoint, "candidate_source": "known_or_extracted", "param_hypothesis": "fundid/fundId/FundID/code + date/month variants", "notes": ""})

    for target in TARGETS:
        for endpoint in sorted(endpoint_urls)[:6]:
            for query_url in build_param_urls(endpoint, target)[:2]:
                for attempt_type, url in [("direct_api_param", query_url), ("wayback_available_api_param", wayback_available(query_url, target["stamp"]))]:
                    code, ctype, body, final_url, err = fetch("GET", url, timeout=3, max_bytes=1_000_000)
                    text = decode(body) if body else ""
                    is_wayback_meta = attempt_type.startswith("wayback_available")
                    date_field, holdings_date = detect_date(text, skip_wayback_metadata=is_wayback_meta)
                    rows = parse_rows(text) if code == "200" and not is_wayback_meta else []
                    retrieved = ""
                    if code == "200" and body:
                        ext = ".json" if "json" in ctype.lower() or body[:1] in (b"{", b"[") else ".html"
                        path = RAW / (safe(f"{target['period']}_{attempt_type}_{short_id(endpoint + url)}") + ext)
                        path.write_bytes(body)
                        retrieved = str(path).replace("\\", "/")
                        raw_manifest.append({"source_id": safe(path.stem), "raw_file_path": retrieved, "source_url_or_reference": final_url or url, "document_date": holdings_date, "covered_effective_start": target["target_date"], "covered_effective_end": target["target_date"], "source_type": "api_endpoint_probe", "archive_status": "downloaded", "checksum_sha256": sha256(body), "notes": f"rows={len(rows)}; wayback_meta={is_wayback_meta}"})
                    status = "error" if err else ("http_ok" if code == "200" else "http_non_ok")
                    api_attempts.append({"source": safe(endpoint), "target_period": target["period"], "query_url": url, "attempt_type": attempt_type, "status": status, "http_code": code, "content_type": ctype, "date_field_detected": date_field, "holdings_date": holdings_date, "row_count": len(rows), "retrieved_path": retrieved, "error": err, "notes": "accepted only if date matches target"})
                    for item in rows[:20]:
                        parsed_row = {"target_period": target["period"], "holdings_date": holdings_date, "source_id": safe(endpoint), "source_file": retrieved, "source_url": final_url or url, "ticker": item["ticker"], "name": item["name"], "weight": item.get("weight", ""), "source_type": "source_backed_manual_proxy", "formal_exact": "false", "evidence_quality": "accepted_date_matched" if target_date_match(holdings_date, target) else "sample_only_date_mismatch_or_missing_date", "parser_status": "phase5_api_parser_extracted_rows", "notes": f"attempt_type={attempt_type}; date_field={date_field}"}
                        parsed.append(parsed_row)
                        if target_date_match(holdings_date, target):
                            accepted.append(parsed_row)

    for page_id, page_url in FORM_PAGES:
        code, ctype, body, final_url, err = fetch("GET", page_url, timeout=3, max_bytes=1_000_000)
        text = decode(body) if body else ""
        forms = extract_forms(page_id, page_url, text) if code == "200" else []
        form_candidates.extend(forms or [{"form_id": f"{page_id}_no_form", "page_url": page_url, "method": "GET", "action": page_url, "hidden_field_count": 0, "hidden_fields_sample": ""}])
        if code == "200" and body:
            path = RAW / (safe(f"{page_id}_form_page") + ".html")
            path.write_bytes(body)
            raw_manifest.append({"source_id": safe(path.stem), "raw_file_path": str(path).replace("\\", "/"), "source_url_or_reference": final_url or page_url, "document_date": "", "covered_effective_start": "", "covered_effective_end": "", "source_type": "form_page", "archive_status": "downloaded", "checksum_sha256": sha256(body), "notes": f"form_count={len(forms)}"})

    for target in TARGETS:
        for form in form_candidates[:4]:
            params_list = [
                {"code": "0050", "fundid": "1066", "month": target["month"]},
                {"stkno": "0050", "q_yyymm": target["roc_month"]},
                {"fundName": "元大台灣卓越50基金", "date": target["target_date"]},
                {"co_id": "0050", "yearmonth": target["month"]},
            ]
            for params in params_list[:1]:
                code, ctype, body, final_url, err = fetch("POST", form["action"], data=params, timeout=3, max_bytes=1_000_000)
                text = decode(body) if body else ""
                date_field, holdings_date = detect_date(text, skip_wayback_metadata=False)
                rows = parse_rows(text) if code == "200" else []
                retrieved = ""
                if code == "200" and body:
                    path = RAW / (safe(f"{target['period']}_{form['form_id']}_{len(post_attempts)}") + ".html")
                    path.write_bytes(body)
                    retrieved = str(path).replace("\\", "/")
                    raw_manifest.append({"source_id": safe(path.stem), "raw_file_path": retrieved, "source_url_or_reference": final_url or form["action"], "document_date": holdings_date, "covered_effective_start": target["target_date"], "covered_effective_end": target["target_date"], "source_type": "sitca_mops_post_probe", "archive_status": "downloaded", "checksum_sha256": sha256(body), "notes": f"params={params}; rows={len(rows)}"})
                post_attempts.append({"form_id": form["form_id"], "target_period": target["period"], "action": form["action"], "method": "POST", "params": json.dumps(params, ensure_ascii=False), "status": "error" if err else ("http_ok" if code == "200" else "http_non_ok"), "http_code": code, "content_type": ctype, "date_field_detected": date_field, "holdings_date": holdings_date, "row_count": len(rows), "retrieved_path": retrieved, "error": err, "notes": "accepted only if date matches target"})

    sample_fields = ["target_period", "holdings_date", "source_id", "source_file", "source_url", "ticker", "name", "weight", "source_type", "formal_exact", "evidence_quality", "parser_status", "notes"]
    write_csv(OUT / "nuxt_chunk_candidates.csv", nuxt_chunks, ["chunk_url", "source_file", "source_timestamp"])
    write_csv(OUT / "api_endpoint_candidates.csv", api_candidates, ["endpoint_id", "endpoint_url", "candidate_source", "param_hypothesis", "notes"])
    write_csv(OUT / "api_probe_attempts.csv", api_attempts, ["source", "target_period", "query_url", "attempt_type", "status", "http_code", "content_type", "date_field_detected", "holdings_date", "row_count", "retrieved_path", "error", "notes"])
    write_csv(OUT / "sitca_mops_form_candidates.csv", form_candidates, ["form_id", "page_url", "method", "action", "hidden_field_count", "hidden_fields_sample"])
    write_csv(OUT / "post_probe_attempts.csv", post_attempts, ["form_id", "target_period", "action", "method", "params", "status", "http_code", "content_type", "date_field_detected", "holdings_date", "row_count", "retrieved_path", "error", "notes"])
    write_csv(OUT / "raw_source_archive_manifest.csv", raw_manifest, ["source_id", "raw_file_path", "source_url_or_reference", "document_date", "covered_effective_start", "covered_effective_end", "source_type", "archive_status", "checksum_sha256", "notes"])
    write_csv(OUT / "parsed_holdings_sample.csv", parsed, sample_fields)
    write_csv(OUT / "accepted_historical_rows.csv", accepted, sample_fields)

    missing = []
    for target in TARGETS:
        pc = sum(1 for r in parsed if r["target_period"] == target["period"])
        ac = sum(1 for r in accepted if r["target_period"] == target["period"])
        missing.append({"period_id": target["period"], "target_date": target["target_date"], "nuxt_api_attempts": sum(1 for r in api_attempts if r["target_period"] in {target["period"], "all"}), "post_probe_attempts": sum(1 for r in post_attempts if r["target_period"] == target["period"]), "parsed_sample_rows": pc, "accepted_rows": ac, "status": "accepted" if ac else "missing_accepted_rows", "blocker": "No Nuxt/API endpoint or SITCA/MOPS POST response returned valid holdings rows with target source_date/holdings_date.", "next_programmatic_attempt": "Use browser/devtools or static JS beautification to identify exact ETF holdings endpoint and SITCA ASP.NET postback parameters; then replay with ViewState/session cookies by target month."})
    write_csv(OUT / "missing_periods.csv", missing, list(missing[0].keys()))
    quality = [
        {"source_family": "yuanta_nuxt_js_endpoint_reverse", "decision": "attempted_bounded_endpoint_reverse", "formal_exact": "false", "manual_proxy_allowed": "true_if_date_matched", "rationale": "Endpoints/params are usable only if response exposes target holdings_date/source_date and valid rows."},
        {"source_family": "sitca_mops_post_probe", "decision": "attempted_form_post_probe", "formal_exact": "false", "manual_proxy_allowed": "source_dependent", "rationale": "Form response must identify fund/date and holdings rows; landing/error pages are not accepted."},
        {"source_family": "wayback_availability_metadata", "decision": "not_accepted_as_source_date", "formal_exact": "false", "manual_proxy_allowed": "false", "rationale": "Wayback metadata timestamp is route evidence only, not holdings_date/source_date."},
    ]
    write_csv(OUT / "source_quality_decision.csv", quality, list(quality[0].keys()))
    completed = [{"item_id": "phase5_endpoint_post_probe", "completed_at": now(), "status": "completed_partial", "evidence": f"nuxt_chunks={len(nuxt_chunks)} endpoints={len(api_candidates)} api_attempts={len(api_attempts)} forms={len(form_candidates)} post_attempts={len(post_attempts)} accepted={len(accepted)}"}]
    write_csv(OUT / "completed.csv", completed, ["item_id", "completed_at", "status", "evidence"])
    write_csv(OUT / "failed.csv", [r for r in missing if r["accepted_rows"] == 0], list(missing[0].keys()))
    run_log = [{"timestamp": now(), "step": "finish", "status": "completed", "details": completed[0]["evidence"]}]
    write_csv(OUT / "run_log.csv", run_log, ["timestamp", "step", "status", "details"])
    manifest = {"schema_version": 1, "task_id": "TASK-RADAR-DATA-TW50-0050-ENDPOINT-POST-PROBE-PHASE5-20260629", "status": "completed_partial" if not accepted else "completed_with_accepted_rows", "created_at": now(), "previous_output_dir": str(PHASE4).replace("\\", "/"), "output_dir": str(OUT).replace("\\", "/"), "target_periods": [t["period"] for t in TARGETS], "nuxt_chunk_candidate_count": len(nuxt_chunks), "api_endpoint_candidate_count": len(api_candidates), "api_probe_attempt_count": len(api_attempts), "sitca_mops_form_candidate_count": len(form_candidates), "post_probe_attempt_count": len(post_attempts), "raw_source_count": len(raw_manifest), "parsed_holdings_sample_rows": len(parsed), "accepted_historical_rows": len(accepted), "formal_model_changed": False, "trade_decision_changed": False, "formal_exact": False, "current_snapshot_used_as_historical": False, "wayback_metadata_accepted_as_source_date": False, "future_data_violation_count": 0, "large_unbounded_crawl_started": False}
    (OUT / "manifest.json").write_text(json.dumps(manifest, ensure_ascii=False, indent=2), encoding="utf-8")
    (OUT / "current_step.txt").write_text("completed\n", encoding="utf-8")
    print(json.dumps(manifest, ensure_ascii=False, indent=2))


if __name__ == "__main__":
    main()
