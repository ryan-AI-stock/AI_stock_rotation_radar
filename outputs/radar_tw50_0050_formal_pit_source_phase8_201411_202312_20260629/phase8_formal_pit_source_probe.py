from __future__ import annotations

import asyncio
import base64
import csv
import hashlib
import html
import json
import os
import re
import shutil
import subprocess
import time
import urllib.parse
from datetime import date, timedelta
from pathlib import Path

import requests
import websockets

OUT = Path(__file__).resolve().parent
REPO = OUT.parents[1]
PHASE7 = REPO / "outputs" / "radar_tw50_0050_browser_network_capture_phase7_201411_202312_20260629"
RAW = OUT / "raw_sources"
RAW.mkdir(parents=True, exist_ok=True)

TARGETS = [
    {"period": "2014Q4", "target_date": "2014-12-31", "year": "2014", "month": "12", "ndate": "20141231", "yyyymm": "201412"},
    {"period": "2016Q1", "target_date": "2016-03-31", "year": "2016", "month": "03", "ndate": "20160331", "yyyymm": "201603"},
    {"period": "2021Q4", "target_date": "2021-12-31", "year": "2021", "month": "12", "ndate": "20211231", "yyyymm": "202112"},
    {"period": "2023Q4", "target_date": "2023-12-31", "year": "2023", "month": "12", "ndate": "20231231", "yyyymm": "202312"},
]

CHROME_CANDIDATES = [
    r"C:\Program Files\Google\Chrome\Application\chrome.exe",
    r"C:\Program Files (x86)\Microsoft\Edge\Application\msedge.exe",
    r"C:\Program Files (x86)\Google\Chrome\Application\chrome.exe",
    r"C:\Program Files\Microsoft\Edge\Application\msedge.exe",
]

SITCA_URL = "https://www.sitca.org.tw/ROC/Industry/IN2421.aspx"
HEADERS = {
    "user-agent": "Mozilla/5.0 RadarDataPhase8/1.0",
    "accept": "text/html,application/json,*/*",
}

CSV_FIELDS = {
    "source_probe_attempts.csv": ["source", "source_family", "period", "query_url", "method", "params", "http_code", "content_type", "date_field_detected", "source_date", "holdings_date", "row_count", "acceptance_decision", "retrieved_path", "error", "notes"],
    "browser_capture_attempts.csv": ["source", "period", "mode", "method", "url", "http_code", "content_type", "post_body", "date_field_detected", "source_date", "holdings_date", "row_count", "acceptance_decision", "retrieved_path", "error", "notes"],
    "sitca_static_handler_candidates.csv": ["candidate_type", "page_url", "candidate_url", "method", "params_tested", "http_code", "content_type", "row_count", "acceptance_decision", "retrieved_path", "error", "notes"],
    "index_constituents_proxy_candidates.csv": ["source", "period", "query_url", "source_date", "effective_date", "ticker", "name", "weight", "proxy_type", "formal_exact", "evidence_quality", "retrieved_path", "notes"],
    "yuanta_legacy_source_candidates.csv": ["source", "period", "query_url", "method", "http_code", "content_type", "date_field_detected", "source_date", "holdings_date", "row_count", "acceptance_decision", "retrieved_path", "error", "notes"],
    "raw_source_archive_manifest.csv": ["source", "period", "url", "retrieved_path", "content_type", "http_status", "sha256", "bytes", "notes"],
    "parsed_holdings_sample.csv": ["period", "source", "source_date", "holdings_date", "ticker", "name", "weight", "source_type", "formal_exact", "evidence_quality", "parser_status", "notes"],
    "accepted_historical_rows.csv": ["period", "source", "source_date", "holdings_date", "ticker", "name", "weight", "source_type", "formal_exact", "evidence_quality", "matched_evidence"],
    "missing_periods.csv": ["period", "target_date", "source_probe_attempts", "browser_capture_attempts", "proxy_candidate_rows", "parsed_sample_rows", "accepted_rows", "status", "blocker", "next_programmatic_source"],
    "source_quality_decision.csv": ["source", "source_type", "formal_exact", "evidence_quality", "accepted_rows", "decision", "notes"],
    "completed.csv": ["step", "status", "completed_at", "notes"],
    "failed.csv": ["period", "step", "status", "error", "next_step"],
    "run_log.csv": ["started_at", "finished_at", "status", "source_probe_attempts", "browser_capture_attempts", "proxy_candidate_rows", "parsed_rows", "accepted_rows", "notes"],
}


def now() -> str:
    return time.strftime("%Y-%m-%dT%H:%M:%S+08:00")


def sha256(data: bytes) -> str:
    return hashlib.sha256(data).hexdigest()


def safe_name(text: str) -> str:
    return re.sub(r"[^A-Za-z0-9_.-]+", "_", text).strip("_")[:150] or "item"


def write_csv(name: str, rows: list[dict]) -> None:
    with (OUT / name).open("w", newline="", encoding="utf-8") as fh:
        writer = csv.DictWriter(fh, fieldnames=CSV_FIELDS[name], extrasaction="ignore")
        writer.writeheader()
        writer.writerows(rows)


def decode(data: bytes) -> str:
    for enc in ["utf-8", "big5", "cp950"]:
        try:
            return data.decode(enc)
        except UnicodeDecodeError:
            continue
    return data.decode("utf-8", errors="replace")


def save_raw(source: str, period: str, url: str, content_type: str, status: str | int, body: bytes, notes: str, raw_rows: list[dict]) -> Path:
    ext = "json" if "json" in (content_type or "").lower() else "csv" if "csv" in (content_type or "").lower() else "html"
    path = RAW / f"{safe_name(source)}_{safe_name(period)}_{len(raw_rows)}.{ext}"
    path.write_bytes(body)
    raw_rows.append({"source": source, "period": period, "url": url, "retrieved_path": str(path), "content_type": content_type, "http_status": status, "sha256": sha256(body), "bytes": len(body), "notes": notes})
    return path


def detect_date(text: str) -> tuple[str, str]:
    patterns = [
        ("anndate", r'"anndate"\s*:\s*"([^"]+)"'),
        ("DataDate", r'"DataDate"\s*:\s*"([^"]+)"'),
        ("date", r'"(?:date|Date|navDate|searchDate|資料日期|持股日期)"\s*[:：]?\s*"?(20\d{2}[-/]?\d{2}[-/]?\d{0,2})'),
        ("roc_label", r"(資料日期|持股日期|年月|日期)[^0-9]{0,12}([0-9]{3}[/-]?[0-9]{2}(?:[/-]?[0-9]{2})?)"),
        ("yyyymm", r"(20\d{2})[/-]?(0[1-9]|1[0-2])"),
    ]
    for field, pattern in patterns:
        match = re.search(pattern, text, flags=re.I)
        if match:
            return field, normalize_date(match.group(2) if field == "roc_label" else "".join(match.groups()))
    return "", ""


def normalize_date(raw: str) -> str:
    text = (raw or "").strip().replace("/", "-")
    if re.fullmatch(r"20\d{2}-\d{2}-\d{2}T.*", text):
        return text[:10]
    if re.fullmatch(r"20\d{6}", text):
        return f"{text[:4]}-{text[4:6]}-{text[6:8]}"
    if re.fullmatch(r"20\d{4}", text):
        return f"{text[:4]}-{text[4:6]}"
    if re.fullmatch(r"20\d{2}-\d{2}-\d{2}", text) or re.fullmatch(r"20\d{2}-\d{2}", text):
        return text
    if re.fullmatch(r"\d{3}-?\d{2}-?\d{0,2}", text):
        digits = text.replace("-", "")
        year = int(digits[:3]) + 1911
        if len(digits) >= 7:
            return f"{year:04d}-{digits[3:5]}-{digits[5:7]}"
        return f"{year:04d}-{digits[3:5]}"
    return text


def date_matches(date_value: str, target: dict) -> bool:
    target_month = f"{target['year']}-{target['month']}"
    return date_value in {target["target_date"], target_month} or date_value.startswith(f"{target_month}-")


def looks_like_holdings_context(text: str) -> bool:
    return bool(re.search(r"0050|元大|台灣卓越|臺灣卓越|卓越50|股票代號|持股|投資組合|基金名稱|持股比率|權重|成分股", text, re.I))


def parse_holdings_rows(text: str, limit: int = 100) -> list[dict]:
    rows: list[dict] = []
    seen: set[str] = set()
    for obj in re.findall(r"\{[^{}]{0,1000}\}", text):
        code = re.search(r'"(?:StockCode|stock_code|stk_cd|STK_CD|Code|code|股票代號|ticker)"\s*:\s*"?(?P<ticker>\d{4})"?', obj, flags=re.I)
        if not code:
            continue
        ticker = code.group("ticker")
        if ticker == "1066":
            continue
        if ticker in seen:
            continue
        name = re.search(r'"(?:StockName|stock_name|stk_nm|STK_NM|Name|name|股票名稱)"\s*:\s*"(?P<name>[^"]{1,50})"', obj, flags=re.I)
        weight = re.search(r'"(?:Weight|weight|ratio|Ratio|proportion|Proportion|持股比率|權重)"\s*:\s*"?(?P<weight>[0-9]+(?:\.[0-9]+)?)"?', obj, flags=re.I)
        rows.append({"ticker": ticker, "name": name.group("name") if name else "", "weight": weight.group("weight") if weight else ""})
        seen.add(ticker)
        if len(rows) >= limit:
            return rows
    # Conservative HTML table fallback: only when context terms exist.
    if looks_like_holdings_context(text):
        for match in re.finditer(r"(?:>|^)\s*(?P<ticker>\d{4})\s*(?:<|,|\s{2,})(?P<near>.{0,120})", re.sub(r"\s+", " ", text)):
            ticker = match.group("ticker")
            if ticker in seen:
                continue
            near = re.sub(r"<[^>]+>", " ", html.unescape(match.group("near"))).strip()
            name = re.split(r"\s{2,}|,|</td>", near)[0][:40]
            rows.append({"ticker": ticker, "name": name, "weight": ""})
            seen.add(ticker)
            if len(rows) >= limit:
                return rows
    return rows


def fetch(session: requests.Session, method: str, url: str, data: dict | None = None, timeout: int = 12) -> tuple[int | str, str, bytes, str]:
    try:
        resp = session.request(method, url, headers=HEADERS, data=data, timeout=timeout, allow_redirects=True)
        return resp.status_code, resp.headers.get("content-type", ""), resp.content[:2_500_000], ""
    except Exception as exc:
        return "", "", b"", f"{type(exc).__name__}: {exc}"


def base_probe_row(source: str, family: str, period: str, url: str, method: str, params: str, status: int | str, ctype: str, path: str, text: str, error: str, notes: str) -> dict:
    date_field, date_value = detect_date(text)
    rows = parse_holdings_rows(text)
    return {"source": source, "source_family": family, "period": period, "query_url": url, "method": method, "params": params, "http_code": status, "content_type": ctype, "date_field_detected": date_field, "source_date": date_value, "holdings_date": date_value, "row_count": len(rows), "acceptance_decision": "candidate_rows_need_target_date_match" if rows else "no_rows", "retrieved_path": path, "error": error, "notes": notes}


def parse_form_fields(text: str) -> dict:
    fields: dict[str, str] = {}
    for tag in re.findall(r"<input\b[^>]*>", text, flags=re.I):
        attrs = dict((m.group(1).lower(), html.unescape(m.group(2))) for m in re.finditer(r'([A-Za-z0-9_:$-]+)=["\']([^"\']*)', tag))
        if attrs.get("name"):
            fields[attrs["name"]] = attrs.get("value", "")
    return fields


def discover_sitca_static_handlers(session: requests.Session, raw_rows: list[dict], source_rows: list[dict], candidates: list[dict]) -> None:
    status, ctype, body, error = fetch(session, "GET", SITCA_URL)
    text = decode(body)
    path = save_raw("sitca_form_page_phase8", "all", SITCA_URL, ctype, status, body, "handler discovery source page", raw_rows) if body else ""
    source_rows.append(base_probe_row("SITCA IN2421 page", "sitca_static_handler_discovery", "all", SITCA_URL, "GET", "", status, ctype, str(path), text, error, "parse form/scripts/links for backend candidates"))
    urls = set()
    for attr in re.findall(r'(?:href|src|action)=["\']([^"\']+)["\']', text, flags=re.I):
        urls.add(urllib.parse.urljoin(SITCA_URL, html.unescape(attr)))
    stems = [
        "IN2421.aspx", "IN2421Print.aspx", "IN2421_Download.aspx", "IN2421_Download.ashx",
        "IN2421_Excel.aspx", "IN2421Excel.aspx", "IN2421CSV.aspx", "IN2421.ashx",
    ]
    for stem in stems:
        urls.add(urllib.parse.urljoin(SITCA_URL, stem))
    for candidate_url in sorted(urls):
        if "sitca.org.tw" not in candidate_url:
            continue
        tested = []
        for target in TARGETS[:2]:
            params = {"YEAR": target["year"], "MONTH": target["month"], "fund": "1066", "fundid": "1066", "code": "0050"}
            url = candidate_url + ("&" if "?" in candidate_url else "?") + urllib.parse.urlencode(params)
            status, ctype, body, error = fetch(session, "GET", url, timeout=8)
            text2 = decode(body)
            saved = save_raw("sitca_handler_candidate", target["period"], url, ctype, status, body, "bounded candidate handler probe", raw_rows) if body else ""
            row_count = len(parse_holdings_rows(text2)) if looks_like_holdings_context(text2) else 0
            decision = "candidate_rows_need_target_date_match" if row_count else "no_rows_or_not_holdings_handler"
            tested.append(f"{target['period']}:{status}:{row_count}")
            candidates.append({"candidate_type": "sitca_link_or_guessed_handler", "page_url": SITCA_URL, "candidate_url": url, "method": "GET", "params_tested": json.dumps(params, ensure_ascii=False), "http_code": status, "content_type": ctype, "row_count": row_count, "acceptance_decision": decision, "retrieved_path": str(saved), "error": error, "notes": "not accepted unless target-date holdings table is parsed"})
        if len(candidates) >= 40:
            break


def sitca_button_post_replay(session: requests.Session, raw_rows: list[dict], source_rows: list[dict], samples: list[dict], accepted: list[dict]) -> None:
    status, ctype, body, error = fetch(session, "GET", SITCA_URL)
    if not body:
        return
    form = parse_form_fields(decode(body))
    for target in TARGETS:
        data = dict(form)
        data["__EVENTTARGET"] = ""
        data["__EVENTARGUMENT"] = ""
        data["ctl00$ContentPlaceHolder1$ddlQ_YEAR"] = target["year"]
        data["ctl00$ContentPlaceHolder1$ddlQ_MONTH"] = target["month"]
        data["ctl00$ContentPlaceHolder1$BtnQuery.x"] = "15"
        data["ctl00$ContentPlaceHolder1$BtnQuery.y"] = "8"
        status2, ctype2, body2, error2 = fetch(session, "POST", SITCA_URL, data=data)
        text = decode(body2)
        saved = save_raw("sitca_button_post_replay_phase8", target["period"], SITCA_URL, ctype2, status2, body2, "full hidden fields + image button replay", raw_rows) if body2 else ""
        row = base_probe_row("SITCA IN2421 image-button replay", "sitca_button_post_replay", target["period"], SITCA_URL, "POST", "hidden_fields+year_month+BtnQuery.x/y", status2, ctype2, str(saved), text, error2, "requests replay of real image-submit path")
        if not looks_like_holdings_context(text):
            row["row_count"] = 0
            row["acceptance_decision"] = "response_not_holdings_context"
        source_rows.append(row)
        date_value = row["holdings_date"]
        rows = parse_holdings_rows(text) if looks_like_holdings_context(text) else []
        for parsed in rows:
            sample = {"period": target["period"], "source": SITCA_URL, "source_date": date_value, "holdings_date": date_value, "ticker": parsed["ticker"], "name": parsed["name"], "weight": parsed["weight"], "source_type": "sitca_button_post_replay", "formal_exact": "false", "evidence_quality": "target_date_matched" if date_matches(date_value, target) else "date_missing_or_mismatch", "parser_status": "parsed_from_html", "notes": "not accepted unless date matches target period and 0050 holdings context is present"}
            samples.append(sample)
            if parsed["name"] and date_matches(date_value, target):
                accepted.append({"period": target["period"], "source": SITCA_URL, "source_date": date_value, "holdings_date": date_value, "ticker": parsed["ticker"], "name": parsed["name"], "weight": parsed["weight"], "source_type": "source_backed_manual_candidate", "formal_exact": "false", "evidence_quality": "target_date_matched_sitca", "matched_evidence": f"{saved}#{parsed['ticker']}"})


def probe_yuanta_legacy(session: requests.Session, raw_rows: list[dict], source_rows: list[dict], legacy_rows: list[dict], samples: list[dict], accepted: list[dict]) -> None:
    templates = [
        "https://www.yuantafunds.com/fund/detail/1066",
        "https://www.yuantafunds.com/fund/holding/1066",
        "https://www.yuantafunds.com/active/ETF/0050",
        "https://www.yuantafunds.com/ETF/0050",
        "https://www.yuantafunds.com/ETF/Download?fundid=1066&date={yyyymm}",
        "https://www.yuantafunds.com/api/fund/holding?fundid=1066&date={yyyymm}",
        "https://api.yuantafunds.com/ECAPI/api/ETF/GetHoldStock?fundid=0050&date={target_date}",
        "https://api.yuantafunds.com/ECAPI/api/ETF/GetHoldStock?fundId=1066&date={target_date}",
        "https://etfapi.yuantaetfs.com/ectranslation/api/bridge?APIType=ETFAPI&CompanyName=YUANTAFUNDS&PageName=%2FtradeInfo%2Fpcf%2F0050&DeviceId=null&FuncId=PCF%2FDaily&ticker=0050&ndate={ndate}",
        "https://etfapi.yuantaetfs.com/ectranslation/api/trans?APIType=ETFBackstage&CompanyName=YUANTAFUNDS&PageName=%2Fproduct%2Fdetail%2F0050%2Fratio&DeviceId=null&FuncId=ETFTag%2FGetProductInformation&AppName=ETF&Device=4&Platform=ETF&stk_cd=0050&date={target_date}",
    ]
    for target in TARGETS:
        for template in templates:
            url = template.format(**target)
            status, ctype, body, error = fetch(session, "GET", url, timeout=10)
            text = decode(body)
            saved = save_raw("yuanta_legacy_phase8", target["period"], url, ctype, status, body, "yuanta legacy/alternative route probe", raw_rows) if body else ""
            date_field, date_value = detect_date(text)
            rows = parse_holdings_rows(text)
            decision = "accepted" if rows and date_matches(date_value, target) else "date_missing_or_mismatch" if rows else "no_rows"
            legacy = {"source": "Yuanta legacy/API alternative", "period": target["period"], "query_url": url, "method": "GET", "http_code": status, "content_type": ctype, "date_field_detected": date_field, "source_date": date_value, "holdings_date": date_value, "row_count": len(rows), "acceptance_decision": decision, "retrieved_path": str(saved), "error": error, "notes": "current/rolling/date-mismatched rows are not accepted"}
            legacy_rows.append(legacy)
            source_rows.append({"source": legacy["source"], "source_family": "yuanta_legacy_alternative", "period": target["period"], "query_url": url, "method": "GET", "params": "", "http_code": status, "content_type": ctype, "date_field_detected": date_field, "source_date": date_value, "holdings_date": date_value, "row_count": len(rows), "acceptance_decision": decision, "retrieved_path": str(saved), "error": error, "notes": legacy["notes"]})
            for parsed in rows:
                samples.append({"period": target["period"], "source": url, "source_date": date_value, "holdings_date": date_value, "ticker": parsed["ticker"], "name": parsed["name"], "weight": parsed["weight"], "source_type": "yuanta_legacy_alternative", "formal_exact": "false", "evidence_quality": "target_date_matched" if date_matches(date_value, target) else "date_missing_or_mismatch", "parser_status": "parsed_from_response", "notes": "not accepted unless target date matches"})
                if parsed["name"] and date_matches(date_value, target):
                    accepted.append({"period": target["period"], "source": url, "source_date": date_value, "holdings_date": date_value, "ticker": parsed["ticker"], "name": parsed["name"], "weight": parsed["weight"], "source_type": "source_backed_manual_candidate", "formal_exact": "false", "evidence_quality": "target_date_matched_yuanta_legacy", "matched_evidence": f"{saved}#{parsed['ticker']}"})


def probe_yuanta_pcf_date_sweep(session: requests.Session, raw_rows: list[dict], source_rows: list[dict], legacy_rows: list[dict], samples: list[dict], accepted: list[dict]) -> None:
    """Bounded month sweep for the live Yuanta PCF/Daily endpoint.

    This route is intentionally narrower than previous generic API probes: it
    uses the exact ectranslation/api/bridge shape observed in Phase 7/8 and
    sweeps only the target month plus a short after-month window.
    """
    for target in TARGETS:
        start = date(int(target["year"]), int(target["month"]), 1)
        for offset in range(0, 40):
            d = start + timedelta(days=offset)
            ndate = d.strftime("%Y%m%d")
            url = "https://etfapi.yuantaetfs.com/ectranslation/api/bridge?" + urllib.parse.urlencode({
                "APIType": "ETFAPI",
                "CompanyName": "YUANTAFUNDS",
                "PageName": "/tradeInfo/pcf/0050",
                "DeviceId": "null",
                "FuncId": "PCF/Daily",
                "ticker": "0050",
                "ndate": ndate,
            })
            status, ctype, body, error = fetch(session, "GET", url, timeout=10)
            text = decode(body)
            saved = save_raw("yuanta_pcf_daily_sweep_phase8", target["period"], url, ctype, status, body, "target-month PCF/Daily date sweep", raw_rows) if body else ""
            date_field, date_value = detect_date(text)
            rows = parse_holdings_rows(text)
            decision = "accepted" if rows and date_matches(date_value, target) else "date_missing_or_mismatch" if rows else "no_rows"
            legacy = {"source": "Yuanta PCF/Daily target-month sweep", "period": target["period"], "query_url": url, "method": "GET", "http_code": status, "content_type": ctype, "date_field_detected": date_field, "source_date": date_value, "holdings_date": date_value, "row_count": len(rows), "acceptance_decision": decision, "retrieved_path": str(saved), "error": error, "notes": "exact ectranslation/api/bridge PCF/Daily month sweep; accept only when anndate/source_date falls in target month"}
            legacy_rows.append(legacy)
            source_rows.append({"source": legacy["source"], "source_family": "yuanta_pcf_daily_month_sweep", "period": target["period"], "query_url": url, "method": "GET", "params": f"ndate={ndate}", "http_code": status, "content_type": ctype, "date_field_detected": date_field, "source_date": date_value, "holdings_date": date_value, "row_count": len(rows), "acceptance_decision": decision, "retrieved_path": str(saved), "error": error, "notes": legacy["notes"]})
            for parsed in rows:
                samples.append({"period": target["period"], "source": url, "source_date": date_value, "holdings_date": date_value, "ticker": parsed["ticker"], "name": parsed["name"], "weight": parsed["weight"], "source_type": "yuanta_pcf_daily_month_sweep", "formal_exact": "false", "evidence_quality": "target_month_matched" if date_matches(date_value, target) else "date_missing_or_mismatch", "parser_status": "parsed_from_json", "notes": "accepted only when PCF anndate/source_date falls in target month"})
                if parsed["name"] and date_matches(date_value, target):
                    accepted.append({"period": target["period"], "source": url, "source_date": date_value, "holdings_date": date_value, "ticker": parsed["ticker"], "name": parsed["name"], "weight": parsed["weight"], "source_type": "source_backed_manual_candidate", "formal_exact": "false", "evidence_quality": "target_month_matched_yuanta_pcf_daily", "matched_evidence": f"{saved}#{parsed['ticker']}"})


def probe_index_proxy(session: requests.Session, raw_rows: list[dict], source_rows: list[dict], proxy_rows: list[dict]) -> None:
    index_urls = [
        "https://www.taiwanindex.com.tw/index/index/TW50",
        "https://www.taiwanindex.com.tw/constituent/TW50",
        "https://www.taiwanindex.com.tw/index/constituent/TW50",
        "https://www.twse.com.tw/zh/products/securities/indices/taiwan-index/taiwan50.html",
        "https://www.twse.com.tw/rwd/zh/TAIEX/MI_5MINS_INDEX?response=json",
        "https://zh.wikipedia.org/wiki/%E8%87%BA%E7%81%A350%E6%8C%87%E6%95%B8",
    ]
    for url in index_urls:
        status, ctype, body, error = fetch(session, "GET", url, timeout=12)
        text = decode(body)
        saved = save_raw("index_proxy_phase8", "all", url, ctype, status, body, "index proxy source family probe", raw_rows) if body else ""
        rows = parse_holdings_rows(text) if re.search(r"臺灣50|台灣50|TW50|成分股|成份股|constituent", text, re.I) else []
        date_field, date_value = detect_date(text)
        source_rows.append({"source": "Taiwan Index/TWSE index proxy", "source_family": "index_constituents_proxy", "period": "all", "query_url": url, "method": "GET", "params": "", "http_code": status, "content_type": ctype, "date_field_detected": date_field, "source_date": date_value, "holdings_date": date_value, "row_count": len(rows), "acceptance_decision": "proxy_only_not_0050_holdings" if rows else "no_rows", "retrieved_path": str(saved), "error": error, "notes": "index constituents are separated from accepted 0050 holdings"})
        for target in TARGETS:
            for parsed in rows[:80]:
                proxy_rows.append({"source": "Taiwan Index/TWSE index proxy", "period": target["period"], "query_url": url, "source_date": date_value, "effective_date": date_value, "ticker": parsed["ticker"], "name": parsed["name"], "weight": parsed["weight"], "proxy_type": "index_constituents_proxy_candidate", "formal_exact": "false", "evidence_quality": "not_0050_holdings_or_not_target_dated", "retrieved_path": str(saved), "notes": "proxy candidate only; Core/Research must decide if index constituents can substitute 0050 holdings"})


class CdpClient:
    def __init__(self, ws_url: str):
        self.ws_url = ws_url
        self.ws = None
        self.next_id = 0
        self.pending: dict[int, asyncio.Future] = {}
        self.events: asyncio.Queue = asyncio.Queue()

    async def __aenter__(self):
        self.ws = await websockets.connect(self.ws_url, max_size=16 * 1024 * 1024)
        asyncio.create_task(self._reader())
        return self

    async def __aexit__(self, *_args):
        await self.ws.close()

    async def _reader(self):
        async for raw in self.ws:
            msg = json.loads(raw)
            if "id" in msg and msg["id"] in self.pending:
                self.pending.pop(msg["id"]).set_result(msg)
            else:
                await self.events.put(msg)

    async def send(self, method: str, params: dict | None = None) -> dict:
        self.next_id += 1
        msg_id = self.next_id
        fut = asyncio.get_running_loop().create_future()
        self.pending[msg_id] = fut
        await self.ws.send(json.dumps({"id": msg_id, "method": method, "params": params or {}}))
        return await asyncio.wait_for(fut, timeout=20)


def chrome_path() -> str:
    for candidate in CHROME_CANDIDATES:
        if Path(candidate).exists():
            return candidate
    raise RuntimeError("Chrome/Edge executable not found")


def start_chrome_non_headless(port: int) -> subprocess.Popen:
    profile = RAW / "chrome_profile_phase8_persisted"
    profile.mkdir(parents=True, exist_ok=True)
    args = [
        chrome_path(),
        f"--remote-debugging-port={port}",
        f"--user-data-dir={profile}",
        "--no-first-run",
        "--disable-extensions",
        "--disable-background-networking",
        "--window-position=-32000,-32000",
        "--window-size=1200,900",
        "about:blank",
    ]
    flags = subprocess.CREATE_NO_WINDOW if os.name == "nt" else 0
    return subprocess.Popen(args, stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL, creationflags=flags)


def wait_for_cdp(port: int) -> str:
    for _ in range(60):
        try:
            response = requests.put(f"http://127.0.0.1:{port}/json/new?about:blank", timeout=1)
            if response.ok:
                return response.json()["webSocketDebuggerUrl"]
        except Exception:
            pass
        time.sleep(0.5)
    raise RuntimeError("Chrome DevTools endpoint unavailable")


async def collect_cdp(client: CdpClient, seconds: float, capture_label: str, period: str, raw_rows: list[dict], browser_rows: list[dict], samples: list[dict], accepted: list[dict], target: dict | None = None) -> None:
    requests_by_id: dict[str, dict] = {}
    deadline = time.time() + seconds
    while time.time() < deadline:
        try:
            msg = await asyncio.wait_for(client.events.get(), timeout=0.5)
        except asyncio.TimeoutError:
            continue
        method = msg.get("method")
        params = msg.get("params", {})
        if method == "Network.requestWillBeSent":
            requests_by_id[params.get("requestId", "")] = params.get("request", {})
        elif method == "Network.responseReceived":
            response = params.get("response", {})
            request_id = params.get("requestId", "")
            url = response.get("url", "")
            if "sitca.org.tw" not in url.lower():
                continue
            try:
                body_msg = await client.send("Network.getResponseBody", {"requestId": request_id})
                body_text = body_msg.get("result", {}).get("body", "")
                body = base64.b64decode(body_text) if body_msg.get("result", {}).get("base64Encoded") else body_text.encode("utf-8", errors="replace")
            except Exception as exc:
                body = f"getResponseBody failed: {type(exc).__name__}: {exc}".encode()
            text = decode(body)
            ctype = response.get("headers", {}).get("content-type") or response.get("headers", {}).get("Content-Type", "")
            saved = save_raw("nonheadless_sitca_capture_phase8", period, url, ctype, response.get("status", ""), body, capture_label, raw_rows)
            date_field, date_value = detect_date(text)
            rows = parse_holdings_rows(text) if looks_like_holdings_context(text) else []
            decision = "accepted" if target and rows and date_matches(date_value, target) else "candidate_rows_need_target_date_match" if rows else "no_holdings_rows"
            req = requests_by_id.get(request_id, {})
            browser_rows.append({"source": "SITCA non-headless persisted Chrome", "period": period, "mode": "non_headless_persisted_profile", "method": req.get("method", ""), "url": url, "http_code": response.get("status", ""), "content_type": ctype, "post_body": req.get("postData", ""), "date_field_detected": date_field, "source_date": date_value, "holdings_date": date_value, "row_count": len(rows), "acceptance_decision": decision, "retrieved_path": str(saved), "error": "", "notes": capture_label})
            for parsed in rows:
                samples.append({"period": period, "source": url, "source_date": date_value, "holdings_date": date_value, "ticker": parsed["ticker"], "name": parsed["name"], "weight": parsed["weight"], "source_type": "sitca_nonheadless_browser_capture", "formal_exact": "false", "evidence_quality": "target_date_matched" if target and date_matches(date_value, target) else "date_missing_or_mismatch", "parser_status": "parsed_from_nonheadless_browser_response", "notes": "not accepted unless target date matches"})
                if parsed["name"] and target and date_matches(date_value, target):
                    accepted.append({"period": period, "source": url, "source_date": date_value, "holdings_date": date_value, "ticker": parsed["ticker"], "name": parsed["name"], "weight": parsed["weight"], "source_type": "source_backed_manual_candidate", "formal_exact": "false", "evidence_quality": "target_date_matched_nonheadless_sitca", "matched_evidence": f"{saved}#{parsed['ticker']}"})


async def run_non_headless_sitca(raw_rows: list[dict], browser_rows: list[dict], samples: list[dict], accepted: list[dict]) -> None:
    port = 9231
    proc = start_chrome_non_headless(port)
    try:
        ws_url = wait_for_cdp(port)
        async with CdpClient(ws_url) as client:
            await client.send("Page.enable")
            await client.send("Network.enable")
            await client.send("Page.navigate", {"url": SITCA_URL})
            await collect_cdp(client, 8, "initial load", "all", raw_rows, browser_rows, samples, accepted)
            for target in TARGETS:
                expression = f"""
(() => {{
 const y=document.querySelector('[name="ctl00$ContentPlaceHolder1$ddlQ_YEAR"]');
 const m=document.querySelector('[name="ctl00$ContentPlaceHolder1$ddlQ_MONTH"]');
 if (y) y.value='{target["year"]}';
 if (m) m.value='{target["month"]}';
 const b=document.querySelector('[name="ctl00$ContentPlaceHolder1$BtnQuery"]');
 if (b) {{ b.click(); return 'clicked_button'; }}
 const form=document.querySelector('form');
 if (form) {{ form.submit(); return 'submitted_form'; }}
 return 'no_query_control';
}})()
"""
                await client.send("Runtime.evaluate", {"expression": expression, "returnByValue": True})
                await collect_cdp(client, 6, "set year/month without dispatch and click query", target["period"], raw_rows, browser_rows, samples, accepted, target)
    finally:
        proc.terminate()
        try:
            proc.wait(timeout=5)
        except subprocess.TimeoutExpired:
            proc.kill()


def build_missing(source_rows: list[dict], browser_rows: list[dict], proxy_rows: list[dict], samples: list[dict], accepted: list[dict]) -> list[dict]:
    missing = []
    for target in TARGETS:
        accepted_count = sum(1 for row in accepted if row["period"] == target["period"])
        missing.append({"period": target["period"], "target_date": target["target_date"], "source_probe_attempts": sum(1 for row in source_rows if row["period"] in {target["period"], "all"}), "browser_capture_attempts": sum(1 for row in browser_rows if row["period"] in {target["period"], "all"}), "proxy_candidate_rows": sum(1 for row in proxy_rows if row["period"] == target["period"]), "parsed_sample_rows": sum(1 for row in samples if row["period"] == target["period"]), "accepted_rows": accepted_count, "status": "accepted_rows_found" if accepted_count else "missing_accepted_rows", "blocker": "" if accepted_count else "No Phase8 source returned target-date 0050 holdings rows.", "next_programmatic_source": "Continue with SITCA alternate handlers/static file indexes, non-headless human-visible UI capture if needed, Taiwan Index official review PDFs as proxy-only, and Yuanta legacy monthly report archive discovery."})
    return missing


def write_summary(manifest: dict, missing: list[dict], source_rows: list[dict], browser_rows: list[dict], proxy_rows: list[dict], samples: list[dict], accepted: list[dict]) -> None:
    lines = [
        "# 0050 歷史成分股來源 Phase 8：formal PIT source continuation",
        "",
        "## 結論",
        "",
        "本批沒有收束，新增 Phase 8 實際 source attempts：non-headless/persisted Chrome SITCA UI path、SITCA static/download handler discovery、元大舊站/API alternative route、Taiwan Index/TWSE index proxy route。",
        "",
        f"- Accepted historical rows: {len(accepted)}",
        f"- Parsed holdings sample rows: {len(samples)}",
        f"- Source probe attempts: {len(source_rows)}",
        f"- Browser capture attempts: {len(browser_rows)}",
        f"- Index proxy candidate rows: {len(proxy_rows)}",
        "",
        "目前仍未取得 2014Q4、2016Q1、2021Q4、2023Q4 任一段可 accepted 的 0050 historical holdings rows。" if not accepted else "本批已找到部分 target-date rows，仍需 Core 複核 source quality。",
        "",
        "## Period Status",
        "",
        "| period | target_date | source probes | browser attempts | proxy rows | parsed sample rows | accepted rows | status |",
        "|---|---:|---:|---:|---:|---:|---:|---|",
    ]
    for row in missing:
        lines.append(f"| {row['period']} | {row['target_date']} | {row['source_probe_attempts']} | {row['browser_capture_attempts']} | {row['proxy_candidate_rows']} | {row['parsed_sample_rows']} | {row['accepted_rows']} | {row['status']} |")
    lines.extend([
        "",
        "## Source Decisions",
        "",
        "- `accepted_historical_rows.csv` only accepts target-period 0050 holdings rows with date match.",
        "- `index_constituents_proxy_candidates.csv` is kept separate; Taiwan Index/TWSE rows are not treated as 0050 ETF holdings.",
        "- current/rolling/date-mismatched 元大 API rows remain parser samples only.",
        "- SITCA non-headless or POST responses without holdings context are not accepted.",
        "",
        "## 下一個可程式化來源",
        "",
        "1. Continue SITCA alternate handler/static file discovery around IN2421 and related ASP.NET endpoints, including site search/CDX for downloadable monthly artifacts.",
        "2. Run non-headless capture with visible UI/manual-free DOM event sequence variants: choose year, wait onchange postback, choose month, wait, then image button coordinates.",
        "3. Search Taiwan Index official review PDFs / FTSE TWSE review notices as `index_constituents_proxy_candidate` only, then ask Core/Research whether index proxy can substitute 0050 holdings for formal replay.",
        "4. Continue Yuanta legacy monthly report archive discovery through old yuantafunds endpoints and Wayback HTML pages, but never accept rolling/current PDFs as historical.",
        "",
        "## Guardrails",
        "",
        "- `formal_model_changed=false`",
        "- `trade_decision_changed=false`",
        "- `formal_exact=false` unless future source proves exact target-date holdings",
        "- `current_snapshot_used_as_historical=false`",
        "- raw responses are retained under `raw_sources/` and excluded from git",
    ])
    (OUT / "final_summary_zh.md").write_text("\n".join(lines) + "\n", encoding="utf-8")


def main() -> None:
    started = now()
    (OUT / "current_step.txt").write_text("running phase8 source probes\n", encoding="utf-8")
    raw_rows: list[dict] = []
    source_rows: list[dict] = []
    browser_rows: list[dict] = []
    sitca_candidates: list[dict] = []
    proxy_rows: list[dict] = []
    legacy_rows: list[dict] = []
    samples: list[dict] = []
    accepted: list[dict] = []

    session = requests.Session()
    session.headers.update(HEADERS)
    sitca_button_post_replay(session, raw_rows, source_rows, samples, accepted)
    discover_sitca_static_handlers(session, raw_rows, source_rows, sitca_candidates)
    probe_yuanta_legacy(session, raw_rows, source_rows, legacy_rows, samples, accepted)
    probe_yuanta_pcf_date_sweep(session, raw_rows, source_rows, legacy_rows, samples, accepted)
    probe_index_proxy(session, raw_rows, source_rows, proxy_rows)

    browser_error = ""
    try:
        asyncio.run(run_non_headless_sitca(raw_rows, browser_rows, samples, accepted))
    except Exception as exc:
        browser_error = f"{type(exc).__name__}: {exc}"
        browser_rows.append({"source": "SITCA non-headless persisted Chrome", "period": "all", "mode": "non_headless_persisted_profile", "method": "", "url": SITCA_URL, "http_code": "", "content_type": "", "post_body": "", "date_field_detected": "", "source_date": "", "holdings_date": "", "row_count": 0, "acceptance_decision": "browser_capture_failed", "retrieved_path": "", "error": browser_error, "notes": "non-headless Chrome launch or CDP capture failed"})

    missing = build_missing(source_rows, browser_rows, proxy_rows, samples, accepted)
    sitca_accepted = sum(1 for row in accepted if "sitca" in row["source"].lower())
    yuanta_accepted = sum(1 for row in accepted if "yuanta" in row["source"].lower())
    quality = [
        {"source": "SITCA IN2421 non-headless/static/replay", "source_type": "formal_0050_holdings_candidate", "formal_exact": "false", "evidence_quality": "no_target_date_rows" if not sitca_accepted else "partial_target_date_rows", "accepted_rows": sitca_accepted, "decision": "not_formal_ready" if not sitca_accepted else "manual_candidate_partial", "notes": "SITCA responses must include holdings context and target date"},
        {"source": "Yuanta PCF/Daily + legacy/API alternative", "source_type": "formal_0050_holdings_candidate", "formal_exact": "false", "evidence_quality": "no_target_date_rows" if not yuanta_accepted else "partial_target_date_rows", "accepted_rows": yuanta_accepted, "decision": "not_formal_ready" if not yuanta_accepted else "manual_candidate_partial", "notes": "target-month PCF/Daily rows accepted as source-backed manual candidates; rolling/current/date-mismatched rows are rejected"},
        {"source": "Taiwan Index/TWSE", "source_type": "index_constituents_proxy_candidate", "formal_exact": "false", "evidence_quality": "proxy_only", "accepted_rows": 0, "decision": "separate_proxy_candidate_only", "notes": "not 0050 holdings; Core/Research must decide proxy use"},
    ]
    completed = [{"step": "phase8_formal_pit_source_continuation", "status": "completed_partial" if not accepted else "completed_partial_with_rows", "completed_at": now(), "notes": f"accepted_historical_rows={len(accepted)}; browser_error={browser_error}"}]
    failed = [{"period": row["period"], "step": "target_period_acceptance", "status": "missing_accepted_rows", "error": row["blocker"], "next_step": row["next_programmatic_source"]} for row in missing if row["accepted_rows"] == 0]
    run_log = [{"started_at": started, "finished_at": now(), "status": "completed_partial_no_valid_dated_rows" if not accepted else "completed_partial_with_rows", "source_probe_attempts": len(source_rows), "browser_capture_attempts": len(browser_rows), "proxy_candidate_rows": len(proxy_rows), "parsed_rows": len(samples), "accepted_rows": len(accepted), "notes": f"read_phase7={PHASE7}; browser_error={browser_error}"}]
    manifest = {
        "task_id": "TASK-RADAR-DATA-TW50-0050-FORMAL-PIT-SOURCE-PHASE8-20260629",
        "output_dir": str(OUT),
        "previous_output": str(PHASE7),
        "generated_at": now(),
        "target_periods": TARGETS,
        "source_probe_attempt_count": len(source_rows),
        "browser_capture_attempt_count": len(browser_rows),
        "sitca_static_handler_candidate_count": len(sitca_candidates),
        "index_constituents_proxy_candidate_rows": len(proxy_rows),
        "yuanta_legacy_source_candidate_count": len(legacy_rows),
        "parsed_holdings_sample_rows": len(samples),
        "accepted_historical_rows": len(accepted),
        "formal_model_changed": False,
        "current_snapshot_used_as_historical": False,
    }

    for name, rows in [
        ("source_probe_attempts.csv", source_rows),
        ("browser_capture_attempts.csv", browser_rows),
        ("sitca_static_handler_candidates.csv", sitca_candidates),
        ("index_constituents_proxy_candidates.csv", proxy_rows),
        ("yuanta_legacy_source_candidates.csv", legacy_rows),
        ("raw_source_archive_manifest.csv", raw_rows),
        ("parsed_holdings_sample.csv", samples),
        ("accepted_historical_rows.csv", accepted),
        ("missing_periods.csv", missing),
        ("source_quality_decision.csv", quality),
        ("completed.csv", completed),
        ("failed.csv", failed),
        ("run_log.csv", run_log),
    ]:
        write_csv(name, rows)
    (OUT / "manifest.json").write_text(json.dumps(manifest, ensure_ascii=False, indent=2), encoding="utf-8")
    write_summary(manifest, missing, source_rows, browser_rows, proxy_rows, samples, accepted)
    (OUT / "current_step.txt").write_text("completed_partial\n", encoding="utf-8")


if __name__ == "__main__":
    try:
        main()
    except Exception as exc:
        (OUT / "current_step.txt").write_text(f"failed: {type(exc).__name__}: {exc}\n", encoding="utf-8")
        raise
