from __future__ import annotations

import asyncio
import base64
import csv
import hashlib
import json
import os
import re
import shutil
import subprocess
import tempfile
import time
import urllib.parse
from pathlib import Path

import requests
import websockets

SCRIPT_DIR = Path(__file__).resolve().parent
REPO = SCRIPT_DIR.parents[1]
OUT = SCRIPT_DIR
PHASE6 = REPO / "outputs" / "radar_tw50_0050_session_replay_phase6_201411_202312_20260629"
RAW = OUT / "raw_sources"
RAW.mkdir(parents=True, exist_ok=True)

TARGETS = [
    {"period": "2014Q4", "target_date": "2014-12-31", "year": "2014", "month": "12", "ndate": "20141231"},
    {"period": "2016Q1", "target_date": "2016-03-31", "year": "2016", "month": "03", "ndate": "20160331"},
    {"period": "2021Q4", "target_date": "2021-12-31", "year": "2021", "month": "12", "ndate": "20211231"},
    {"period": "2023Q4", "target_date": "2023-12-31", "year": "2023", "month": "12", "ndate": "20231231"},
]

YUANTA_PAGES = [
    "https://www.yuantaetfs.com/product/detail/0050/ratio",
    "https://www.yuantaetfs.com/tradeInfo/pcf/0050",
    "https://www.yuantaetfs.com/#/product/detail/0050/ratio",
    "https://www.yuantaetfs.com/#/tradeInfo/pcf/0050",
]

CHROME_CANDIDATES = [
    r"C:\Program Files\Google\Chrome\Application\chrome.exe",
    r"C:\Program Files (x86)\Microsoft\Edge\Application\msedge.exe",
    r"C:\Program Files (x86)\Google\Chrome\Application\chrome.exe",
    r"C:\Program Files\Microsoft\Edge\Application\msedge.exe",
]

CSV_FIELDS = {
    "browser_capture_inventory.csv": ["capture_id", "source", "page_url", "status", "http_status", "title", "request_count", "api_request_count", "relevant_response_count", "notes"],
    "sitca_network_requests.csv": ["capture_id", "phase", "method", "url", "status", "http_status", "content_type", "request_headers", "post_body", "response_path", "response_sha256", "date_field_detected", "holdings_date", "row_count", "error"],
    "yuanta_network_requests.csv": ["capture_id", "page_url", "method", "url", "status", "http_status", "content_type", "request_headers", "post_body", "response_path", "response_sha256", "date_field_detected", "holdings_date", "row_count", "api_family", "error"],
    "exact_replay_attempts.csv": ["source", "period", "target_date", "template_url", "replay_url", "status", "http_status", "content_type", "response_path", "response_sha256", "date_field_detected", "holdings_date", "row_count", "accepted", "source_type", "formal_exact", "error", "notes"],
    "raw_source_archive_manifest.csv": ["source", "period", "url", "retrieved_path", "content_type", "http_status", "sha256", "bytes", "notes"],
    "parsed_holdings_sample.csv": ["period", "source", "source_date", "holdings_date", "ticker", "name", "weight", "source_type", "formal_exact", "evidence_quality", "parser_status", "notes"],
    "accepted_historical_rows.csv": ["period", "source", "source_date", "holdings_date", "ticker", "name", "weight", "source_type", "formal_exact", "evidence_quality", "matched_evidence"],
    "missing_periods.csv": ["period", "target_date", "sitca_capture_rows", "yuanta_capture_rows", "exact_replay_attempts", "parsed_sample_rows", "accepted_rows", "status", "blocker", "next_programmatic_source"],
    "source_quality_decision.csv": ["source", "source_type", "formal_exact", "evidence_quality", "accepted_rows", "decision", "notes"],
    "completed.csv": ["step", "status", "completed_at", "notes"],
    "failed.csv": ["period", "step", "status", "error", "next_step"],
    "run_log.csv": ["started_at", "finished_at", "status", "sitca_requests", "yuanta_requests", "exact_replay_attempts", "parsed_rows", "accepted_rows", "notes"],
}


def now() -> str:
    return time.strftime("%Y-%m-%dT%H:%M:%S+08:00")


def sha256(data: bytes) -> str:
    return hashlib.sha256(data).hexdigest()


def safe_name(text: str) -> str:
    return re.sub(r"[^A-Za-z0-9_.-]+", "_", text).strip("_")[:140] or "item"


def write_csv(name: str, rows: list[dict]) -> None:
    with (OUT / name).open("w", newline="", encoding="utf-8") as fh:
        writer = csv.DictWriter(fh, fieldnames=CSV_FIELDS[name], extrasaction="ignore")
        writer.writeheader()
        writer.writerows(rows)


def detect_date(text: str) -> tuple[str, str]:
    patterns = [
        ("anndate", r'"anndate"\s*:\s*"([^"]+)"'),
        ("DataDate", r'"DataDate"\s*:\s*"([^"]+)"'),
        ("date", r'"(?:date|Date|navDate|searchDate)"\s*:\s*"([^"]+)"'),
        ("chinese_label", r"(資料日期|持股日期|年月)[^0-9]{0,12}([0-9]{3,4}[/-]?[0-9]{2}(?:[/-]?[0-9]{2})?)"),
    ]
    for field, pattern in patterns:
        match = re.search(pattern, text, flags=re.I)
        if match:
            return field, normalize_date(match.group(2) if field == "chinese_label" else match.group(1))
    return "", ""


def normalize_date(raw: str) -> str:
    text = (raw or "").strip().replace("/", "-")
    if re.fullmatch(r"20\d{6}", text):
        return f"{text[:4]}-{text[4:6]}-{text[6:8]}"
    if re.fullmatch(r"20\d{4}", text):
        return f"{text[:4]}-{text[4:6]}"
    if re.fullmatch(r"\d{3}-?\d{2}-?\d{0,2}", text):
        digits = text.replace("-", "")
        year = int(digits[:3]) + 1911
        if len(digits) >= 7:
            return f"{year:04d}-{digits[3:5]}-{digits[5:7]}"
        return f"{year:04d}-{digits[3:5]}"
    return text


def count_ticker_rows(text: str) -> int:
    matches = re.findall(r"(?:^|[^\d])(?:00[1-9]\d|0[1-9]\d{2}|[1-9]\d{3})(?:[^\d]|$)", text)
    return min(len(matches), 500)


def parse_holdings_rows(text: str) -> list[dict]:
    rows: list[dict] = []
    seen: set[str] = set()
    for obj in re.findall(r"\{[^{}]{0,900}\}", text):
        code = re.search(r'"(?:StockCode|stock_code|stk_cd|STK_CD|Code|code|股票代號)"\s*:\s*"?(?P<ticker>\d{4})"?', obj, flags=re.I)
        if not code:
            continue
        ticker = code.group("ticker")
        if ticker in seen:
            continue
        name = re.search(r'"(?:StockName|stock_name|stk_nm|STK_NM|Name|name|股票名稱)"\s*:\s*"(?P<name>[^"]{1,40})"', obj, flags=re.I)
        weight = re.search(r'"(?:Weight|weight|ratio|Ratio|proportion|Proportion|權重|持股比率)"\s*:\s*"?(?P<weight>[0-9]+(?:\.[0-9]+)?)"?', obj, flags=re.I)
        rows.append({"ticker": ticker, "name": name.group("name") if name else "", "weight": weight.group("weight") if weight else ""})
        seen.add(ticker)
        if len(rows) >= 80:
            break
    return rows


def compact_headers(headers: dict) -> str:
    keep = {}
    for key, value in headers.items():
        lower = key.lower()
        if lower in {"accept", "content-type", "origin", "referer", "user-agent", "x-requested-with"}:
            keep[lower] = value
        elif lower == "cookie":
            keep[lower] = "[masked]"
    return json.dumps(keep, ensure_ascii=False)


def is_yuanta_api(url: str) -> bool:
    return bool(re.search(r"yuantaetfs\.com|etfapi\.yuantaetfs\.com|api\.yuantafunds\.com", url, re.I) and re.search(r"api/bridge|api/trans|ETFAPI|ETFBackstage|PCF|HoldStock|ratio|0050", url, re.I))


def looks_like_sitca_holdings_table(text: str) -> bool:
    return bool(re.search(r"0050|元大|台灣卓越|卓越50|股票代號|持股|投資組合|基金名稱", text, re.I))


def api_family(url: str) -> str:
    if re.search(r"api/bridge", url, re.I):
        return "api_bridge"
    if re.search(r"api/trans", url, re.I):
        return "api_trans"
    if re.search(r"PCF", url, re.I):
        return "pcf_related"
    return "other"


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
    raise RuntimeError("No Chrome/Edge executable found")


def start_chrome(port: int) -> subprocess.Popen:
    profile = RAW / "chrome_profile"
    if profile.exists():
        shutil.rmtree(profile, ignore_errors=True)
    profile.mkdir(parents=True, exist_ok=True)
    args = [
        chrome_path(),
        f"--remote-debugging-port={port}",
        f"--user-data-dir={profile}",
        "--headless=new",
        "--disable-gpu",
        "--no-first-run",
        "--disable-extensions",
        "--disable-background-networking",
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
    raise RuntimeError("Chrome DevTools endpoint did not become available")


async def collect_events(client: CdpClient, seconds: float, capture_id: str, page_url: str, raw_rows: list[dict], sitca_rows: list[dict], yuanta_rows: list[dict], samples: list[dict]) -> None:
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
            req = params.get("request", {})
            requests_by_id[params.get("requestId", "")] = req
        elif method == "Network.responseReceived":
            response = params.get("response", {})
            request_id = params.get("requestId", "")
            url = response.get("url", "")
            if not ("sitca.org.tw" in url.lower() or is_yuanta_api(url)):
                continue
            try:
                body_msg = await client.send("Network.getResponseBody", {"requestId": request_id})
                body_data = body_msg.get("result", {}).get("body", "")
                body = base64.b64decode(body_data) if body_msg.get("result", {}).get("base64Encoded") else body_data.encode("utf-8", errors="replace")
            except Exception as exc:
                body = f"CDP getResponseBody failed: {type(exc).__name__}: {exc}".encode()
            content_type = response.get("headers", {}).get("content-type") or response.get("headers", {}).get("Content-Type", "")
            ext = "json" if "json" in content_type else "html"
            file_path = RAW / f"{safe_name(capture_id)}_{len(raw_rows)}.{ext}"
            file_path.write_bytes(body)
            text = body.decode("utf-8", errors="replace")
            date_field, holdings_date = detect_date(text)
            parsed = parse_holdings_rows(text)
            if "sitca.org.tw" in url.lower() and not looks_like_sitca_holdings_table(text):
                parsed = []
                row_count = 0
            else:
                row_count = len(parsed) or count_ticker_rows(text)
            req = requests_by_id.get(request_id, {})
            record_common = {
                "method": req.get("method", ""),
                "url": url,
                "status": "http_ok" if int(response.get("status", 0)) < 400 else "http_non_ok",
                "http_status": response.get("status", ""),
                "content_type": content_type,
                "request_headers": compact_headers(req.get("headers", {})),
                "post_body": req.get("postData", ""),
                "response_path": str(file_path),
                "response_sha256": sha256(body),
                "date_field_detected": date_field,
                "holdings_date": holdings_date,
                "row_count": row_count,
                "error": "",
            }
            raw_rows.append({"source": "browser_cdp_capture", "period": "live", "url": url, "retrieved_path": str(file_path), "content_type": content_type, "http_status": response.get("status", ""), "sha256": sha256(body), "bytes": len(body), "notes": capture_id})
            if "sitca.org.tw" in url.lower():
                sitca_rows.append({"capture_id": capture_id, "phase": "network", **record_common})
            elif is_yuanta_api(url):
                yuanta_rows.append({"capture_id": capture_id, "page_url": page_url, "api_family": api_family(url), **record_common})
                for row in parsed:
                    samples.append({"period": "live_current_or_page_date", "source": url, "source_date": holdings_date, "holdings_date": holdings_date, "ticker": row["ticker"], "name": row["name"], "weight": row["weight"], "source_type": "endpoint_contract_sample", "formal_exact": "false", "evidence_quality": "date_mismatch_or_current_only", "parser_status": "parsed_from_live_capture", "notes": "not accepted unless date matches target period"})


async def capture_page(client: CdpClient, url: str, capture_id: str, raw_rows: list[dict], sitca_rows: list[dict], yuanta_rows: list[dict], samples: list[dict], inventory: list[dict]) -> None:
    before_sitca = len(sitca_rows)
    before_yuanta = len(yuanta_rows)
    status = "captured"
    notes = ""
    http_status = ""
    title = ""
    try:
        nav = await client.send("Page.navigate", {"url": url})
        if nav.get("error"):
            status = "error"
            notes = json.dumps(nav["error"], ensure_ascii=False)
        await collect_events(client, 8, capture_id, url, raw_rows, sitca_rows, yuanta_rows, samples)
        title_msg = await client.send("Runtime.evaluate", {"expression": "document.title", "returnByValue": True})
        title = title_msg.get("result", {}).get("result", {}).get("value", "")
        if "sitca.org.tw" in url.lower():
            for target in TARGETS:
                expression = f"""
(() => {{
 const y=document.querySelector('[name="ctl00$ContentPlaceHolder1$ddlQ_YEAR"]');
 const m=document.querySelector('[name="ctl00$ContentPlaceHolder1$ddlQ_MONTH"]');
 if (y) {{ y.value='{target["year"]}'; y.dispatchEvent(new Event('change', {{bubbles:true}})); }}
 if (m) {{ m.value='{target["month"]}'; m.dispatchEvent(new Event('change', {{bubbles:true}})); }}
 const b=document.querySelector('[name="ctl00$ContentPlaceHolder1$BtnQuery"]');
 if (b) {{ b.click(); return 'clicked'; }}
 return 'no_button';
}})()
"""
                await client.send("Runtime.evaluate", {"expression": expression, "returnByValue": True})
                await collect_events(client, 4, f"{capture_id}_{target['period']}", url, raw_rows, sitca_rows, yuanta_rows, samples)
    except Exception as exc:
        status = "error"
        notes = f"{type(exc).__name__}: {exc}"
    page_rows = sitca_rows[before_sitca:] if "sitca.org.tw" in url.lower() else yuanta_rows[before_yuanta:]
    if page_rows:
        http_status = page_rows[0].get("http_status", "")
    inventory.append({
        "capture_id": capture_id,
        "source": "SITCA IN2421.aspx" if "sitca.org.tw" in url.lower() else "Yuanta 0050 live page",
        "page_url": url,
        "status": status,
        "http_status": http_status,
        "title": title,
        "request_count": len(page_rows),
        "api_request_count": sum(1 for row in page_rows if "api_" in row.get("api_family", "") or row.get("method") == "POST"),
        "relevant_response_count": sum(1 for row in page_rows if int(row.get("row_count") or 0) > 0),
        "notes": notes,
    })


def build_replay_urls(yuanta_rows: list[dict]) -> list[str]:
    templates = []
    for row in yuanta_rows:
        url = row.get("url", "")
        if re.search(r"api/bridge|api/trans", url, re.I) and url not in templates:
            templates.append(url)
    templates.extend([
        "https://www.yuantaetfs.com/api/bridge?APIType=ETFAPI&CompanyName=YUANTAFUNDS&PageName=%2FtradeInfo%2Fpcf%2F0050&DeviceId=null&FuncId=PCF%2FDaily&ticker=0050&ndate=__NDATE__",
        "https://www.yuantaetfs.com/api/trans?APIType=ETFBackstage&CompanyName=YUANTAFUNDS&PageName=%2FtradeInfo%2Fpcf%2F0050&DeviceId=null&FuncId=ETFPCF&stk_cd=0050",
        "https://www.yuantaetfs.com/api/bridge?APIType=ETFAPI&CompanyName=YUANTAFUNDS&PageName=%2Fproduct%2Fdetail%2F0050%2Fratio&DeviceId=null&FuncId=PCF%2FDaily&ticker=0050&ndate=__NDATE__",
    ])
    return list(dict.fromkeys(templates))[:10]


def with_target_date(template: str, target: dict) -> str:
    url = template.replace("__NDATE__", target["ndate"])
    parsed = urllib.parse.urlsplit(url)
    query = dict(urllib.parse.parse_qsl(parsed.query, keep_blank_values=True))
    for key in ["ndate", "date", "DataDate", "anndate"]:
        if key in query:
            query[key] = target["ndate"] if key == "ndate" else target["target_date"]
    if "ndate" not in query and re.search(r"PCF/Daily|PCF%2FDaily", url, re.I):
        query["ndate"] = target["ndate"]
    if "ticker" not in query and re.search(r"PCF/Daily|PCF%2FDaily", url, re.I):
        query["ticker"] = "0050"
    return urllib.parse.urlunsplit((parsed.scheme, parsed.netloc, parsed.path, urllib.parse.urlencode(query), parsed.fragment))


def run_replays(yuanta_rows: list[dict], raw_rows: list[dict], samples: list[dict], accepted: list[dict]) -> list[dict]:
    rows = []
    session = requests.Session()
    session.headers.update({"user-agent": "Mozilla/5.0 RadarDataPhase7/1.0", "accept": "application/json,text/html,*/*"})
    for target in TARGETS:
        for template in build_replay_urls(yuanta_rows):
            replay_url = with_target_date(template, target)
            record = {"source": "yuanta_exact_replay", "period": target["period"], "target_date": target["target_date"], "template_url": template, "replay_url": replay_url, "status": "", "http_status": "", "content_type": "", "response_path": "", "response_sha256": "", "date_field_detected": "", "holdings_date": "", "row_count": 0, "accepted": "false", "source_type": "browser_capture_exact_replay", "formal_exact": "false", "error": "", "notes": "accepted only if holdings/source date matches target period"}
            try:
                response = session.get(replay_url, timeout=15)
                body = response.content
                content_type = response.headers.get("content-type", "")
                ext = "json" if "json" in content_type else "html"
                file_path = RAW / f"{safe_name(target['period'])}_replay_{len(rows)}.{ext}"
                file_path.write_bytes(body)
                text = body.decode("utf-8", errors="replace")
                date_field, holdings_date = detect_date(text)
                parsed_rows = parse_holdings_rows(text)
                record.update({"status": "http_ok" if response.ok else "http_non_ok", "http_status": response.status_code, "content_type": content_type, "response_path": str(file_path), "response_sha256": sha256(body), "date_field_detected": date_field, "holdings_date": holdings_date, "row_count": len(parsed_rows) or count_ticker_rows(text)})
                raw_rows.append({"source": "yuanta_exact_replay", "period": target["period"], "url": replay_url, "retrieved_path": str(file_path), "content_type": content_type, "http_status": response.status_code, "sha256": sha256(body), "bytes": len(body), "notes": "exact replay from browser captured/common params"})
                target_match = holdings_date in {target["target_date"], target["target_date"][:7]}
                for parsed in parsed_rows:
                    samples.append({"period": target["period"], "source": replay_url, "source_date": holdings_date, "holdings_date": holdings_date, "ticker": parsed["ticker"], "name": parsed["name"], "weight": parsed["weight"], "source_type": "browser_capture_exact_replay", "formal_exact": "false", "evidence_quality": "target_date_matched_manual_candidate" if target_match else "date_mismatch_or_missing_date", "parser_status": "parsed_from_replay_response", "notes": "not accepted unless date matches target period"})
                    if target_match:
                        accepted.append({"period": target["period"], "source": replay_url, "source_date": holdings_date, "holdings_date": holdings_date, "ticker": parsed["ticker"], "name": parsed["name"], "weight": parsed["weight"], "source_type": "source_backed_manual_proxy", "formal_exact": "false", "evidence_quality": "target_date_matched_browser_replay", "matched_evidence": f"{file_path}#{parsed['ticker']}"})
                if target_match and parsed_rows:
                    record["accepted"] = "true"
            except Exception as exc:
                record["status"] = "error"
                record["error"] = f"{type(exc).__name__}: {exc}"
            rows.append(record)
    return rows


def write_summary(inventory: list[dict], sitca_rows: list[dict], yuanta_rows: list[dict], replay_rows: list[dict], samples: list[dict], accepted: list[dict], missing: list[dict]) -> None:
    sitca_posts = [row for row in sitca_rows if row.get("method") == "POST"]
    yuanta_apis = [row for row in yuanta_rows if row.get("api_family") in {"api_bridge", "api_trans"}]
    lines = [
        "# 0050 歷史成分股來源 Phase 7：browser network capture",
        "",
        "## 結論",
        "",
        "本批完成 Chrome DevTools Protocol live browser network capture 與 exact replay attempts。",
        "",
        f"- Accepted historical rows: {len(accepted)}",
        f"- Parsed holdings sample rows: {len(samples)}",
        f"- SITCA captured requests: {len(sitca_rows)}",
        f"- SITCA captured POST requests: {len(sitca_posts)}",
        f"- Yuanta captured relevant requests: {len(yuanta_rows)}",
        f"- Yuanta captured api bridge/trans requests: {len(yuanta_apis)}",
        f"- Exact replay attempts: {len(replay_rows)}",
        "",
        "目前仍未取得 2014Q4、2016Q1、2021Q4、2023Q4 任一段可 accepted 的 0050 歷史成分股清單。" if not accepted else "本批有 target-date matched rows；仍需 Core normalize 前複核。",
        "",
        "## SITCA Live Capture",
        "",
        f"Browser capture observed {len(sitca_posts)} SITCA POST request(s), but semantic filtering found 0 target holdings-table rows." if sitca_posts else "Browser capture loaded IN2421.aspx, but no successful holdings-table POST was observed in headless Chrome.",
        "詳情見 `sitca_network_requests.csv`；headers 已遮罩 cookie。",
        "",
        "## Yuanta Live Capture",
        "",
        f"Browser capture observed {len(yuanta_apis)} Yuanta api/bridge or api/trans request(s)." if yuanta_apis else "Browser capture did not expose a usable historical Yuanta api/bridge or api/trans request.",
        "Exact replay attempts were generated from captured/common parameters and target dates.",
        "",
        "## Period Status",
        "",
        "| period | target_date | replay_attempts | parsed_sample_rows | accepted_rows | status |",
        "|---|---:|---:|---:|---:|---|",
    ]
    for row in missing:
        lines.append(f"| {row['period']} | {row['target_date']} | {row['exact_replay_attempts']} | {row['parsed_sample_rows']} | {row['accepted_rows']} | {row['status']} |")
    lines.extend([
        "",
        "## 下一個可程式化來源",
        "",
        "1. 改用 non-headless Chrome + persisted profile 再 capture 一次，確認 SITCA 是否拒絕 headless 或需要真實 UI event path。",
        "2. 針對 SITCA `IN2421.aspx` 背後 static/download endpoint、站內檔案索引或 alternate ASP.NET handler 做 bounded discovery。",
        "3. 針對元大 Nuxt `getBaseUrl/getCommonParameters` 與 DeviceId/common params 做 deeper trace；若 API 只提供 current/near-current，保留 endpoint contract sample，不列 historical accepted。",
        "4. TWSE/Taiwan Index constituents 仍只能作 proxy，除非 source decision 能明確連到 0050 ETF holdings。",
        "",
        "## Guardrails",
        "",
        "- `formal_exact=false`",
        "- `current_snapshot_used_as_historical=false`",
        "- `formal_model_changed=false`",
        "- `trade_decision_changed=false`",
        "- raw browser responses are retained under `raw_sources/` and excluded from git",
    ])
    (OUT / "final_summary_zh.md").write_text("\n".join(lines) + "\n", encoding="utf-8")


async def run_browser_capture(raw_rows: list[dict], sitca_rows: list[dict], yuanta_rows: list[dict], samples: list[dict], inventory: list[dict]) -> None:
    port = 9227
    proc = start_chrome(port)
    try:
        ws_url = wait_for_cdp(port)
        async with CdpClient(ws_url) as client:
            await client.send("Page.enable")
            await client.send("Network.enable")
            await capture_page(client, "https://www.sitca.org.tw/ROC/Industry/IN2421.aspx", "sitca_live_in2421", raw_rows, sitca_rows, yuanta_rows, samples, inventory)
            for idx, page_url in enumerate(YUANTA_PAGES):
                await capture_page(client, page_url, f"yuanta_live_{idx}", raw_rows, sitca_rows, yuanta_rows, samples, inventory)
    finally:
        proc.terminate()
        try:
            proc.wait(timeout=5)
        except subprocess.TimeoutExpired:
            proc.kill()


def main() -> None:
    started = now()
    (OUT / "current_step.txt").write_text("running cdp browser capture\n", encoding="utf-8")
    raw_rows: list[dict] = []
    sitca_rows: list[dict] = []
    yuanta_rows: list[dict] = []
    samples: list[dict] = []
    accepted: list[dict] = []
    inventory: list[dict] = []
    asyncio.run(run_browser_capture(raw_rows, sitca_rows, yuanta_rows, samples, inventory))
    replay_rows = run_replays(yuanta_rows, raw_rows, samples, accepted)
    missing = []
    for target in TARGETS:
        replay_count = sum(1 for row in replay_rows if row["period"] == target["period"])
        sample_count = sum(1 for row in samples if row["period"] == target["period"])
        accepted_count = sum(1 for row in accepted if row["period"] == target["period"])
        missing.append({
            "period": target["period"],
            "target_date": target["target_date"],
            "sitca_capture_rows": len(sitca_rows),
            "yuanta_capture_rows": len(yuanta_rows),
            "exact_replay_attempts": replay_count,
            "parsed_sample_rows": sample_count,
            "accepted_rows": accepted_count,
            "status": "accepted_manual_proxy_rows" if accepted_count else "missing_accepted_rows",
            "blocker": "" if accepted_count else "Live browser capture/replay did not return target-date 0050 holdings rows.",
            "next_programmatic_source": "Non-headless Chrome/devtools capture with persisted profile, then SITCA static endpoint discovery or Yuanta common-params deeper trace.",
        })
    quality = [
        {"source": "SITCA IN2421.aspx CDP browser capture", "source_type": "browser_capture_candidate", "formal_exact": "false", "evidence_quality": "rows_detected_needs_date_match" if any(int(r.get("row_count") or 0) for r in sitca_rows) else "no_holdings_rows_detected", "accepted_rows": 0, "decision": "not_formal_ready", "notes": "accepted only if target date rows are parsed"},
        {"source": "Yuanta 0050 CDP browser capture", "source_type": "endpoint_contract_sample", "formal_exact": "false", "evidence_quality": "live_api_contract_captured" if yuanta_rows else "no_api_contract_captured", "accepted_rows": len(accepted), "decision": "manual_proxy_partial" if accepted else "not_formal_ready", "notes": "current/date-mismatched payloads are not historical evidence"},
        {"source": "Phase7 exact replay", "source_type": "browser_capture_exact_replay", "formal_exact": "false", "evidence_quality": "target_date_rows_found" if accepted else "no_target_date_rows", "accepted_rows": len(accepted), "decision": "manual_proxy_partial" if accepted else "blocked_partial", "notes": "no current snapshot backfill"},
    ]
    completed = [{"step": "phase7_cdp_browser_network_capture", "status": "completed_partial", "completed_at": now(), "notes": f"accepted_historical_rows={len(accepted)}"}]
    failed = [{"period": row["period"], "step": "target_period_acceptance", "status": "missing_accepted_rows", "error": row["blocker"], "next_step": row["next_programmatic_source"]} for row in missing if not row["accepted_rows"]]
    run_log = [{"started_at": started, "finished_at": now(), "status": "completed_partial_with_rows" if accepted else "completed_partial_no_valid_dated_rows", "sitca_requests": len(sitca_rows), "yuanta_requests": len(yuanta_rows), "exact_replay_attempts": len(replay_rows), "parsed_rows": len(samples), "accepted_rows": len(accepted), "notes": f"read_phase6={PHASE6}"}]

    for name, rows in [
        ("browser_capture_inventory.csv", inventory),
        ("sitca_network_requests.csv", sitca_rows),
        ("yuanta_network_requests.csv", yuanta_rows),
        ("exact_replay_attempts.csv", replay_rows),
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
    (OUT / "manifest.json").write_text(json.dumps({
        "task_id": "TASK-RADAR-DATA-TW50-0050-BROWSER-NETWORK-CAPTURE-PHASE7-20260629",
        "output_dir": str(OUT),
        "previous_output": str(PHASE6),
        "generated_at": now(),
        "target_periods": TARGETS,
        "accepted_historical_rows": len(accepted),
        "parsed_holdings_sample_rows": len(samples),
        "sitca_network_request_count": len(sitca_rows),
        "yuanta_network_request_count": len(yuanta_rows),
        "exact_replay_attempt_count": len(replay_rows),
        "formal_exact": False,
        "formal_model_changed": False,
        "current_snapshot_used_as_historical": False,
    }, ensure_ascii=False, indent=2), encoding="utf-8")
    write_summary(inventory, sitca_rows, yuanta_rows, replay_rows, samples, accepted, missing)
    (OUT / "current_step.txt").write_text("completed_partial\n", encoding="utf-8")


if __name__ == "__main__":
    try:
        main()
    except Exception as exc:
        (OUT / "current_step.txt").write_text(f"failed: {type(exc).__name__}: {exc}\n", encoding="utf-8")
        raise
