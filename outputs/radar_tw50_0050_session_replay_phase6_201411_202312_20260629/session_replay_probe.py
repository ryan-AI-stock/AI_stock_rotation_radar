from __future__ import annotations

import csv
import hashlib
import html
import json
import re
import time
from pathlib import Path
from urllib.parse import quote, urlencode, urljoin

import requests

OUT = Path("outputs/radar_tw50_0050_session_replay_phase6_201411_202312_20260629")
PHASE5 = Path("outputs/radar_tw50_0050_endpoint_post_probe_phase5_201411_202312_20260629")
RAW = OUT / "raw_sources"
RAW.mkdir(parents=True, exist_ok=True)

TARGETS = [
    {"period": "2014Q4", "target_date": "2014-12-31", "year": "2014", "month": "12", "roc_year": "103", "roc_month": "10312", "stamp": "20141231"},
    {"period": "2016Q1", "target_date": "2016-03-31", "year": "2016", "month": "03", "roc_year": "105", "roc_month": "10503", "stamp": "20160331"},
    {"period": "2021Q4", "target_date": "2021-12-31", "year": "2021", "month": "12", "roc_year": "110", "roc_month": "11012", "stamp": "20211231"},
    {"period": "2023Q4", "target_date": "2023-12-31", "year": "2023", "month": "12", "roc_year": "112", "roc_month": "11212", "stamp": "20231231"},
]

HEADERS = {
    "User-Agent": "Mozilla/5.0 RadarDataPhase6/1.0",
    "Accept": "text/html,application/json,application/javascript,*/*",
    "Referer": "https://www.sitca.org.tw/ROC/Industry/IN2421.aspx",
}

SITCA_URL = "https://www.sitca.org.tw/ROC/Industry/IN2421.aspx"


def now() -> str:
    return time.strftime("%Y-%m-%dT%H:%M:%S+08:00")


def safe(text: str, limit: int = 150) -> str:
    return re.sub(r"[^A-Za-z0-9_.-]+", "_", text).strip("_")[:limit] or "item"


def sha256(body: bytes) -> str:
    return hashlib.sha256(body).hexdigest()


def write_csv(path: Path, rows: list[dict], fields: list[str]) -> None:
    with path.open("w", newline="", encoding="utf-8") as fh:
        writer = csv.DictWriter(fh, fieldnames=fields, extrasaction="ignore")
        writer.writeheader()
        writer.writerows(rows)


def decode(body: bytes) -> str:
    return body.decode("utf-8", errors="replace")


def fetch(session: requests.Session, method: str, url: str, data: dict | None = None, timeout: int = 6, max_bytes: int = 2_000_000) -> tuple[str, str, bytes, str, str]:
    try:
        with session.request(method, url, headers=HEADERS, data=data, timeout=(4, timeout), stream=True, allow_redirects=True) as resp:
            chunks = []
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


def parse_inputs(text: str) -> list[dict]:
    rows = []
    for tag in re.findall(r"<input\b[^>]*>", text, flags=re.I):
        attrs = dict((m.group(1).lower(), html.unescape(m.group(2))) for m in re.finditer(r'([A-Za-z0-9_:-]+)=["\']([^"\']*)', tag))
        rows.append({"tag": "input", "type": attrs.get("type", ""), "name": attrs.get("name", ""), "id": attrs.get("id", ""), "value": attrs.get("value", "")[:240]})
    return rows


def parse_selects(text: str) -> list[dict]:
    rows = []
    for block in re.findall(r"<select\b.*?</select>", text, flags=re.I | re.S):
        name = re.search(r'name=["\']([^"\']+)', block, flags=re.I)
        sid = re.search(r'id=["\']([^"\']+)', block, flags=re.I)
        options = re.findall(r'<option[^>]*value=["\']?([^"\' >]*)["\']?[^>]*>(.*?)</option>', block, flags=re.I | re.S)
        sample = []
        for value, label in options[:20]:
            sample.append(f"{html.unescape(value)}:{re.sub(r'<[^>]+>', '', html.unescape(label)).strip()}")
        rows.append({"tag": "select", "type": "", "name": name.group(1) if name else "", "id": sid.group(1) if sid else "", "value": ";".join(sample)[:500]})
    return rows


def base_post_fields(inventory: list[dict]) -> dict:
    fields = {}
    for row in inventory:
        if row["tag"] == "input" and row["name"]:
            fields[row["name"]] = row["value"]
    fields.setdefault("__EVENTTARGET", "")
    fields.setdefault("__EVENTARGUMENT", "")
    return fields


def candidate_controls(inventory: list[dict]) -> list[str]:
    controls = []
    for row in inventory:
        name = row.get("name", "")
        value = row.get("value", "")
        blob = (name + " " + value).lower()
        if row["tag"] == "select" or any(k in blob for k in ["year", "month", "fund", "company", "ddl", "drop", "ctl"]):
            if name:
                controls.append(name)
    return list(dict.fromkeys(controls))[:10]


def detect_date(text: str) -> tuple[str, str]:
    for key in ["DataDate", "date", "Date", "資料日期", "年月", "持股日期"]:
        m = re.search(rf"{re.escape(key)}[\"'\s:=：]{{1,12}}([0-9]{{4}}[-/]?[0-9]{{2}}[-/]?[0-9]{{2}}|[0-9]{{6}}|[0-9]{{3}}/?[0-9]{{2}})", text)
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
    if re.fullmatch(r"20\d{2}-\d{2}-\d{2}", raw):
        return raw
    return raw


def target_date_match(date_value: str, target: dict) -> bool:
    return date_value in {target["target_date"], target["target_date"][:7], f"{target['year']}-{target['month']}"}


def parse_rows(text: str) -> list[dict]:
    rows = []
    for m in re.finditer(r'"(?:StockCode|Code|code|股票代號)"\s*:\s*"?(?P<ticker>\d{4})"?(?P<near>.{0,500})', text, flags=re.I | re.S):
        near = m.group("near")
        name = re.search(r'"(?:StockName|Name|name|股票名稱)"\s*:\s*"(?P<name>[^"]{1,30})"', near)
        weight = re.search(r'"(?:Weight|Ratio|ratio|Proportion|權重|持股比率)"\s*:\s*"?(?P<weight>[0-9]+(?:\.[0-9]+)?)', near, flags=re.I)
        if name:
            rows.append({"ticker": m.group("ticker"), "name": name.group("name"), "weight": weight.group("weight") if weight else ""})
    return rows[:80]


def extract_nuxt_requests() -> list[dict]:
    rows = []
    for path in sorted((PHASE5 / "raw_sources").glob("chunk_*.js")):
        text = path.read_text(encoding="utf-8", errors="replace")
        for endpoint in sorted(set(re.findall(r"(?:https?:)?//(?:etfapi\.yuantaetfs\.com|api\.yuantafunds\.com)[^\"'\\\s)]+|/(?:api|ECAPI)/[A-Za-z0-9_./?-]+", text, flags=re.I))):
            idx = text.find(endpoint)
            snippet = text[max(0, idx - 350) : idx + len(endpoint) + 450]
            params = sorted(set(re.findall(r"(fundid|fundId|FundID|code|date|DataDate|month|ETFCode|FundCode|id)", snippet, flags=re.I)))
            rows.append({"source_file": str(path).replace("\\", "/"), "endpoint": endpoint, "params_detected": ";".join(params), "snippet": re.sub(r"\s+", " ", snippet)[:900]})
    dedup = {}
    for row in rows:
        dedup.setdefault((row["endpoint"], row["params_detected"]), row)
    return list(dedup.values())[:40]


def api_probe_urls(endpoint: str, target: dict) -> list[str]:
    endpoint = endpoint if endpoint.startswith("http") else urljoin("https://etfapi.yuantaetfs.com/", endpoint)
    base = endpoint.split("?", 1)[0]
    combos = [
        {"fundid": "0050", "date": target["target_date"]},
        {"fundid": "0050", "month": target["year"] + target["month"]},
        {"FundID": "1066", "DataDate": target["target_date"]},
        {"ETFCode": "0050", "YYYYMM": target["year"] + target["month"]},
    ]
    return [base + "?" + urlencode(c) for c in combos[:2]]


def main() -> None:
    (OUT / "current_step.txt").write_text("running_session_replay_phase6\n", encoding="utf-8")
    raw_manifest = []
    parsed = []
    accepted = []
    sitca_inventory = []
    sitca_attempts = []
    nuxt_extract = extract_nuxt_requests()
    api_attempts = []

    session = requests.Session()
    code, ctype, body, final_url, err = fetch(session, "GET", SITCA_URL, timeout=8, max_bytes=2_000_000)
    text = decode(body) if body else ""
    if code == "200" and body:
        path = RAW / "sitca_in2421_initial_get.html"
        path.write_bytes(body)
        raw_manifest.append({"source_id": "sitca_in2421_initial_get", "raw_file_path": str(path).replace("\\", "/"), "source_url_or_reference": final_url, "document_date": "", "covered_effective_start": "", "covered_effective_end": "", "source_type": "sitca_form_page", "archive_status": "downloaded", "checksum_sha256": sha256(body), "notes": f"cookies={session.cookies.get_dict()}"})
    sitca_inventory.extend(parse_inputs(text))
    sitca_inventory.extend(parse_selects(text))
    fields = base_post_fields(sitca_inventory)
    controls = candidate_controls(sitca_inventory)

    for target in TARGETS:
        # Stage 1: try likely cascade controls as event targets.
        replay_controls = ["__query_submit__"] + (controls or [""])[:3]
        for idx, control in enumerate(replay_controls):
            post = dict(fields)
            post["__EVENTTARGET"] = "" if control == "__query_submit__" else control
            post["__EVENTARGUMENT"] = ""
            post["ctl00$ContentPlaceHolder1$ddlQ_YEAR"] = target["year"]
            post["ctl00$ContentPlaceHolder1$ddlQ_MONTH"] = target["month"]
            post["ctl00$ContentPlaceHolder1$BtnQuery.x"] = "10"
            post["ctl00$ContentPlaceHolder1$BtnQuery.y"] = "10"
            for name in controls:
                lower = name.lower()
                if "year" in lower or "yy" in lower:
                    post[name] = target["year"]
                elif "month" in lower or "mm" in lower:
                    post[name] = target["month"]
                elif "fund" in lower or "company" in lower or "ddl" in lower:
                    post[name] = "1066"
            post.setdefault("fundid", "1066")
            post.setdefault("code", "0050")
            post.setdefault("month", target["year"] + target["month"])
            code, ctype, body, final_url, err = fetch(session, "POST", SITCA_URL, data=post, timeout=6, max_bytes=2_000_000)
            response_text = decode(body) if body else ""
            date_field, hdate = detect_date(response_text)
            rows = parse_rows(response_text)
            retrieved = ""
            if code == "200" and body:
                path = RAW / f"{target['period']}_sitca_postback_{idx}.html"
                path.write_bytes(body)
                retrieved = str(path).replace("\\", "/")
                raw_manifest.append({"source_id": safe(path.stem), "raw_file_path": retrieved, "source_url_or_reference": final_url, "document_date": hdate, "covered_effective_start": target["target_date"], "covered_effective_end": target["target_date"], "source_type": "sitca_session_postback", "archive_status": "downloaded", "checksum_sha256": sha256(body), "notes": f"eventtarget={control}; rows={len(rows)}"})
            sitca_attempts.append({"target_period": target["period"], "event_target": control, "control_values": json.dumps({k: post[k] for k in list(post.keys())[:20]}, ensure_ascii=False), "status": "error" if err else ("http_ok" if code == "200" else "http_non_ok"), "http_code": code, "content_type": ctype, "date_field_detected": date_field, "holdings_date": hdate, "row_count": len(rows), "retrieved_path": retrieved, "error": err, "notes": "session-aware postback with cookies and hidden fields"})

    for target in TARGETS:
        for row in nuxt_extract[:8]:
            for url in api_probe_urls(row["endpoint"], target)[:2]:
                session2 = requests.Session()
                code, ctype, body, final_url, err = fetch(session2, "GET", url, timeout=5, max_bytes=1_500_000)
                response_text = decode(body) if body else ""
                date_field, hdate = detect_date(response_text)
                rows = parse_rows(response_text)
                retrieved = ""
                if code == "200" and body:
                    ext = ".json" if "json" in ctype.lower() or body[:1] in (b"{", b"[") else ".html"
                    path = RAW / (safe(f"{target['period']}_exact_api_{len(api_attempts)}") + ext)
                    path.write_bytes(body)
                    retrieved = str(path).replace("\\", "/")
                    raw_manifest.append({"source_id": safe(path.stem), "raw_file_path": retrieved, "source_url_or_reference": final_url, "document_date": hdate, "covered_effective_start": target["target_date"], "covered_effective_end": target["target_date"], "source_type": "exact_api_probe", "archive_status": "downloaded", "checksum_sha256": sha256(body), "notes": f"rows={len(rows)}"})
                api_attempts.append({"target_period": target["period"], "endpoint": row["endpoint"], "params_detected": row["params_detected"], "query_url": url, "status": "error" if err else ("http_ok" if code == "200" else "http_non_ok"), "http_code": code, "content_type": ctype, "date_field_detected": date_field, "holdings_date": hdate, "row_count": len(rows), "retrieved_path": retrieved, "error": err, "notes": "exact params from static Nuxt extraction"})
                for item in rows[:20]:
                    parsed_row = {"target_period": target["period"], "holdings_date": hdate, "source_id": safe(row["endpoint"]), "source_file": retrieved, "source_url": final_url or url, "ticker": item["ticker"], "name": item["name"], "weight": item.get("weight", ""), "source_type": "source_backed_manual_proxy", "formal_exact": "false", "evidence_quality": "accepted_date_matched" if target_date_match(hdate, target) else "sample_only_date_mismatch_or_missing_date", "parser_status": "phase6_exact_api_parser_extracted_rows", "notes": f"date_field={date_field}"}
                    parsed.append(parsed_row)
                    if target_date_match(hdate, target):
                        accepted.append(parsed_row)

    sample_fields = ["target_period", "holdings_date", "source_id", "source_file", "source_url", "ticker", "name", "weight", "source_type", "formal_exact", "evidence_quality", "parser_status", "notes"]
    write_csv(OUT / "sitca_form_state_inventory.csv", sitca_inventory, ["tag", "type", "name", "id", "value"])
    write_csv(OUT / "sitca_postback_attempts.csv", sitca_attempts, ["target_period", "event_target", "control_values", "status", "http_code", "content_type", "date_field_detected", "holdings_date", "row_count", "retrieved_path", "error", "notes"])
    write_csv(OUT / "nuxt_request_extraction.csv", nuxt_extract, ["source_file", "endpoint", "params_detected", "snippet"])
    write_csv(OUT / "exact_api_probe_attempts.csv", api_attempts, ["target_period", "endpoint", "params_detected", "query_url", "status", "http_code", "content_type", "date_field_detected", "holdings_date", "row_count", "retrieved_path", "error", "notes"])
    write_csv(OUT / "raw_source_archive_manifest.csv", raw_manifest, ["source_id", "raw_file_path", "source_url_or_reference", "document_date", "covered_effective_start", "covered_effective_end", "source_type", "archive_status", "checksum_sha256", "notes"])
    write_csv(OUT / "parsed_holdings_sample.csv", parsed, sample_fields)
    write_csv(OUT / "accepted_historical_rows.csv", accepted, sample_fields)

    missing = []
    for target in TARGETS:
        pc = sum(1 for row in parsed if row["target_period"] == target["period"])
        ac = sum(1 for row in accepted if row["target_period"] == target["period"])
        missing.append({"period_id": target["period"], "target_date": target["target_date"], "sitca_postback_attempts": sum(1 for r in sitca_attempts if r["target_period"] == target["period"]), "exact_api_probe_attempts": sum(1 for r in api_attempts if r["target_period"] == target["period"]), "parsed_sample_rows": pc, "accepted_rows": ac, "status": "accepted" if ac else "missing_accepted_rows", "blocker": "No session-aware SITCA postback or exact API probe returned valid target-date holdings rows.", "next_programmatic_attempt": "Use browser automation/devtools to capture live XHR and ASP.NET control events, or inspect SITCA server-side endpoint/static downloads behind IN2421.aspx."})
    write_csv(OUT / "missing_periods.csv", missing, list(missing[0].keys()))
    quality = [
        {"source_family": "sitca_session_aspnet_postback", "decision": "attempted_session_replay", "formal_exact": "false", "manual_proxy_allowed": "true_if_date_matched", "rationale": "POST preserved cookies and hidden fields, but response must include target date and holdings rows to accept."},
        {"source_family": "nuxt_exact_request_static_extraction", "decision": "attempted_exact_param_probe", "formal_exact": "false", "manual_proxy_allowed": "true_if_date_matched", "rationale": "Static extraction can identify endpoints/params, but rows are accepted only with target source_date/holdings_date."},
        {"source_family": "aspnet_error_or_viewstate_pages", "decision": "not_accepted", "formal_exact": "false", "manual_proxy_allowed": "false", "rationale": "ASP.NET pages without holdings table rows are not evidence."},
    ]
    write_csv(OUT / "source_quality_decision.csv", quality, list(quality[0].keys()))
    completed = [{"item_id": "phase6_session_replay_exact_api", "completed_at": now(), "status": "completed_partial", "evidence": f"sitca_inventory={len(sitca_inventory)} sitca_attempts={len(sitca_attempts)} nuxt_extract={len(nuxt_extract)} api_attempts={len(api_attempts)} accepted={len(accepted)}"}]
    write_csv(OUT / "completed.csv", completed, ["item_id", "completed_at", "status", "evidence"])
    write_csv(OUT / "failed.csv", [r for r in missing if r["accepted_rows"] == 0], list(missing[0].keys()))
    write_csv(OUT / "run_log.csv", [{"timestamp": now(), "step": "finish", "status": "completed", "details": completed[0]["evidence"]}], ["timestamp", "step", "status", "details"])
    manifest = {"schema_version": 1, "task_id": "TASK-RADAR-DATA-TW50-0050-SESSION-REPLAY-PHASE6-20260629", "status": "completed_partial" if not accepted else "completed_with_accepted_rows", "created_at": now(), "previous_output_dir": str(PHASE5).replace("\\", "/"), "output_dir": str(OUT).replace("\\", "/"), "target_periods": [t["period"] for t in TARGETS], "sitca_form_state_inventory_rows": len(sitca_inventory), "sitca_postback_attempt_count": len(sitca_attempts), "nuxt_request_extraction_count": len(nuxt_extract), "exact_api_probe_attempt_count": len(api_attempts), "raw_source_count": len(raw_manifest), "parsed_holdings_sample_rows": len(parsed), "accepted_historical_rows": len(accepted), "formal_model_changed": False, "trade_decision_changed": False, "formal_exact": False, "current_snapshot_used_as_historical": False, "aspnet_error_page_accepted": False, "future_data_violation_count": 0, "large_unbounded_crawl_started": False}
    (OUT / "manifest.json").write_text(json.dumps(manifest, ensure_ascii=False, indent=2), encoding="utf-8")
    (OUT / "current_step.txt").write_text("completed\n", encoding="utf-8")
    print(json.dumps(manifest, ensure_ascii=False, indent=2))


if __name__ == "__main__":
    main()
