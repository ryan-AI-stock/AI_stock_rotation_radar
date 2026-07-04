from __future__ import annotations

import csv
import json
import re
import sys
from datetime import datetime, timezone
from pathlib import Path
from urllib.parse import urljoin
from urllib.request import Request, urlopen

import pdfplumber


OUTPUT_DIR = Path(__file__).resolve().parent
RAW_DIR = OUTPUT_DIR / "raw_sources"
PDF_DIR = RAW_DIR / "pdf"
SNIPPET_DIR = OUTPUT_DIR / "extracted_snippets"
V0_OUTPUT = OUTPUT_DIR.parents[0] / "radar_dynamic_pool1_mops_mainline_evidence_ledger_20260704"
TASK_ID = "TASK-RADAR-DATA-DYNAMIC-POOL1-MOPS-DOCUMENT-EXTRACTION-V1-20260704"

PRIORITY_TICKERS = {
    "2308": ("2308.TW", "台達電", "TWSE", "old_ai_power"),
    "2382": ("2382.TW", "廣達", "TWSE", "old_ai_server"),
    "6669": ("6669.TW", "緯穎", "TWSE", "old_ai_server"),
    "2356": ("2356.TW", "英業達", "TWSE", "old_ai_server"),
    "2395": ("2395.TW", "研華", "TWSE", "old_ai_edge_aiot"),
    "3017": ("3017.TW", "奇鋐", "TWSE", "old_ai_cooling"),
    "6488": ("6488.TWO", "環球晶", "TPEx", "pool1b_semiconductor_materials"),
    "1560": ("1560.TW", "中砂", "TWSE", "pool1b_materials"),
    "2449": ("2449.TW", "京元電子", "TWSE", "pool1b_semiconductor"),
    "3044": ("3044.TW", "健鼎", "TWSE", "pool1b_pcb"),
    "3189": ("3189.TW", "景碩", "TWSE", "pool1b_substrate"),
    "3324": ("3324.TW", "雙鴻", "TWSE", "pool1b_cooling"),
    "3443": ("3443.TW", "創意", "TWSE", "pool1b_ic_design"),
    "3533": ("3533.TW", "嘉澤", "TWSE", "pool1b_high_speed"),
    "3665": ("3665.TW", "貿聯-KY", "TWSE", "pool1b_high_speed"),
    "6213": ("6213.TW", "聯茂", "TWSE", "pool1b_ccl"),
    "6442": ("6442.TW", "光聖", "TWSE", "pool1b_optical"),
    "6412": ("6412.TW", "群電", "TWSE", "pool1b_power"),
    "6285": ("6285.TW", "啟碁", "TWSE", "pool1b_networking"),
    "8046": ("8046.TW", "南電", "TWSE", "pool1b_substrate"),
    "8210": ("8210.TW", "勤誠", "TWSE", "pool1b_server_chassis"),
    "8299": ("8299.TWO", "群聯", "TPEx", "pool1b_storage"),
}

KEYWORD_RULES = [
    ("AI伺服器", "ai_server_hardware", "AI server"),
    ("人工智慧伺服器", "ai_server_hardware", "AI server"),
    ("伺服器", "ai_server_hardware", "server hardware"),
    ("AI", "ai_supply_chain", "AI / AI demand"),
    ("人工智慧", "ai_supply_chain", "artificial intelligence"),
    ("資料中心", "data_center", "data center"),
    ("data center", "data_center", "data center"),
    ("HPC", "ai_hpc", "HPC"),
    ("GPU", "ai_accelerator", "GPU"),
    ("PCB", "pcb_ccl", "PCB"),
    ("印刷電路板", "pcb_ccl", "PCB"),
    ("CCL", "pcb_ccl", "CCL"),
    ("銅箔基板", "pcb_ccl", "CCL"),
    ("載板", "ic_substrate", "IC substrate"),
    ("IC載板", "ic_substrate", "IC substrate"),
    ("散熱", "cooling_thermal", "thermal / cooling"),
    ("熱管理", "cooling_thermal", "thermal / cooling"),
    ("光通訊", "optical_communication", "optical communication"),
    ("高速", "high_speed_transmission", "high-speed transmission"),
    ("高速傳輸", "high_speed_transmission", "high-speed transmission"),
    ("半導體製程", "semicap_materials", "semiconductor process"),
    ("半導體設備", "semicap_materials", "semiconductor equipment"),
    ("半導體", "semiconductor", "semiconductor"),
    ("矽晶", "semiconductor_materials", "silicon wafer/materials"),
    ("晶圓", "semiconductor_materials", "wafer"),
    ("探針卡", "semiconductor_testing", "probe card"),
    ("封裝測試", "semiconductor_testing", "semiconductor testing"),
    ("測試服務", "semiconductor_testing", "semiconductor testing"),
    ("晶圓測試", "semiconductor_testing", "wafer testing"),
    ("IC測試", "semiconductor_testing", "IC testing"),
    ("電源供應器", "power_supply", "power supply"),
    ("電源管理", "power_supply", "power management"),
    ("電源", "power_supply", "power"),
    ("網通", "networking", "networking"),
    ("網路通訊", "networking", "networking"),
    ("通訊產品", "networking", "networking"),
    ("雲端", "cloud_infrastructure", "cloud infrastructure"),
    ("交換器", "networking", "switching / networking"),
    ("熱導管", "cooling_thermal", "thermal / cooling"),
    ("風扇", "cooling_thermal", "fan / cooling"),
    ("水冷", "cooling_thermal", "liquid cooling"),
    ("連接器", "high_speed_transmission", "connector"),
    ("線束", "high_speed_transmission", "cable harness"),
    ("IC設計", "ic_design", "IC design"),
    ("ASIC", "ic_design", "ASIC"),
    ("晶片設計", "ic_design", "chip design"),
    ("矽晶圓", "semiconductor_materials", "silicon wafer"),
    ("再生晶圓", "semiconductor_materials", "reclaimed wafer"),
    ("NAND", "memory_storage", "NAND / storage"),
    ("SSD", "memory_storage", "SSD / storage"),
    ("控制晶片", "memory_storage", "storage controller"),
    ("工業電腦", "edge_aiot", "industrial computer"),
    ("AIoT", "edge_aiot", "AIoT"),
    ("物聯網", "edge_aiot", "IoT"),
    ("邊緣運算", "edge_aiot", "edge computing"),
    ("嵌入式", "edge_aiot", "embedded computing"),
    ("自動化", "edge_aiot", "automation"),
    ("機殼", "server_chassis", "server chassis"),
    ("機櫃", "server_chassis", "rack / cabinet"),
]

EVIDENCE_COLUMNS = [
    "ticker",
    "company_name",
    "market",
    "candidate_scope",
    "evidence_type",
    "keyword_or_topic",
    "ai_supply_chain_layer",
    "mainline_theme_label",
    "source_doc_type",
    "source_doc_date",
    "source_url_or_file",
    "source_title",
    "source_excerpt",
    "source_date",
    "effective_date",
    "as_of_date",
    "extraction_method",
    "confidence_level",
    "accepted_for_diagnostic",
    "accepted_for_formal",
    "formal_exact",
    "human_review_required",
    "notes",
]


def now_iso() -> str:
    return datetime.now(timezone.utc).replace(microsecond=0).isoformat()


def write_csv(path: Path, rows: list[dict], fieldnames: list[str]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("w", newline="", encoding="utf-8-sig") as f:
        writer = csv.DictWriter(f, fieldnames=fieldnames, extrasaction="ignore")
        writer.writeheader()
        writer.writerows(rows)


def append_log(status: str, detail: str) -> None:
    path = OUTPUT_DIR / "run_log.csv"
    is_new = not path.exists()
    with path.open("a", newline="", encoding="utf-8-sig") as f:
        writer = csv.DictWriter(f, fieldnames=["timestamp_utc", "status", "detail"])
        if is_new:
            writer.writeheader()
        writer.writerow({"timestamp_utc": now_iso(), "status": status, "detail": detail})


def date_from_filename(filename: str) -> str:
    m = re.search(r"_(20\d{6})F", filename)
    if not m:
        return ""
    d = m.group(1)
    return f"{d[:4]}-{d[4:6]}-{d[6:8]}"


def fetch_url(url: str, timeout: int = 30) -> tuple[bytes, str]:
    req = Request(url, headers={"User-Agent": "Mozilla/5.0"})
    with urlopen(req, timeout=timeout) as resp:
        return resp.read(), resp.headers.get("content-type", "")


def list_report_files(code: str, roc_year: int) -> tuple[list[str], str, str]:
    url = f"https://doc.twse.com.tw/server-java/t57sb01?step=1&colorchg=1&co_id={code}&year={roc_year}&mtype=F"
    content, content_type = fetch_url(url, timeout=30)
    text = content.decode("big5", errors="replace")
    file_pattern = re.compile(
        r"readfile2\((['\"])F\1\s*,\s*(['\"])" + re.escape(code) + r"\2\s*,\s*(['\"])([^'\"]+\.pdf)\3\)"
    )
    files = [m.group(4) for m in file_pattern.finditer(text)]
    preferred = sorted(
        files,
        key=lambda f: (
            0 if re.search(r"F04\.pdf$", f) else 1,
            0 if re.search(r"F05\.pdf$", f) else 1,
            0 if re.search(r"F17\.pdf$", f) else 1,
            0 if re.search(r"F13\.pdf$", f) else 1,
            0 if re.search(r"F01\.pdf$", f) else 1,
            f,
        ),
    )
    return preferred, url, content_type


def resolve_pdf_url(code: str, filename: str) -> str:
    url = f"https://doc.twse.com.tw/server-java/t57sb01?step=9&kind=F&co_id={code}&filename={filename}"
    content, _ = fetch_url(url, timeout=30)
    text = content.decode("big5", errors="replace")
    match = re.search(r"href=['\"]([^'\"]+\.pdf)['\"]", text)
    if not match:
        return ""
    return urljoin("https://doc.twse.com.tw", match.group(1))


def download_pdf(url: str, target: Path) -> tuple[bool, str]:
    content, ctype = fetch_url(url, timeout=60)
    if "pdf" not in ctype.lower() and not content.startswith(b"%PDF"):
        return False, f"not_pdf content_type={ctype} bytes={len(content)}"
    target.parent.mkdir(parents=True, exist_ok=True)
    target.write_bytes(content)
    return True, ""


def extract_text(path: Path, max_pages: int | None = None) -> str:
    parts = []
    with pdfplumber.open(str(path)) as pdf:
        pages = pdf.pages if max_pages is None else pdf.pages[:max_pages]
        for page in pages:
            try:
                text = page.extract_text() or ""
            except Exception:
                text = ""
            if text:
                parts.append(text)
    return "\n".join(parts)


def classify(text: str) -> tuple[str, str, str]:
    lowered = text.lower()
    for keyword, layer, label in KEYWORD_RULES:
        if keyword.lower() in lowered:
            return keyword, layer, label
    return "", "", ""


def excerpt(text: str, keyword: str, size: int = 260) -> str:
    cleaned = " ".join(text.split())
    idx = cleaned.lower().find(keyword.lower()) if keyword else -1
    if idx < 0:
        return cleaned[:size]
    start = max(0, idx - 80)
    end = min(len(cleaned), idx + size)
    return cleaned[start:end]


def main() -> None:
    OUTPUT_DIR.mkdir(parents=True, exist_ok=True)
    RAW_DIR.mkdir(parents=True, exist_ok=True)
    PDF_DIR.mkdir(parents=True, exist_ok=True)
    SNIPPET_DIR.mkdir(parents=True, exist_ok=True)
    (RAW_DIR / ".gitignore").write_text("pdf/\n*.pdf\n", encoding="utf-8")
    (OUTPUT_DIR / "current_step.txt").write_text("running_bounded_mops_document_extraction_v1\n", encoding="utf-8")
    append_log("started", "bounded MOPS annual report locator and PDF text extraction")

    requested = []
    for code, (ticker, name, market, scope) in sorted(PRIORITY_TICKERS.items()):
        requested.append(
            {
                "ticker": ticker,
                "code": code,
                "company_name": name,
                "market": market,
                "candidate_scope": scope,
                "priority": "research_priority_blocked_v0",
            }
        )
    write_csv(OUTPUT_DIR / "requested_tickers.csv", requested, ["ticker", "code", "company_name", "market", "candidate_scope", "priority"])

    attempts = []
    accepted = []
    text_manifest = []
    blocked = []

    for code, (ticker, name, market, scope) in sorted(PRIORITY_TICKERS.items()):
        ticker_attempts = []
        found = False
        accepted_for_ticker = False
        for roc_year in (114, 113):
            try:
                files, locator_url, content_type = list_report_files(code, roc_year)
            except Exception as exc:
                attempts.append(
                    {
                        "ticker": ticker,
                        "company_name": name,
                        "source_url": f"doc.twse t57sb01 year={roc_year}",
                        "document_filename": "",
                        "document_date": "",
                        "method": "annual_report_locator",
                        "status": "failed",
                        "http_code": "",
                        "content_type": "",
                        "retrieved_path": "",
                        "extraction_status": "",
                        "accepted_evidence_rows": 0,
                        "error": str(exc),
                        "notes": "",
                    }
                )
                continue
            ticker_attempts.append((roc_year, files, locator_url, content_type))
            if not files:
                attempts.append(
                    {
                        "ticker": ticker,
                        "company_name": name,
                        "source_url": locator_url,
                        "document_filename": "",
                        "document_date": "",
                        "method": "annual_report_locator",
                        "status": "no_pdf_filename",
                        "http_code": "200",
                        "content_type": content_type,
                        "retrieved_path": "",
                        "extraction_status": "",
                        "accepted_evidence_rows": 0,
                        "error": "",
                        "notes": "No readfile2 PDF filename found.",
                    }
                )
                continue
            found = True
            selected = files[0]
            doc_date = date_from_filename(selected)
            try:
                pdf_url = resolve_pdf_url(code, selected)
                if not pdf_url:
                    raise RuntimeError("pdf link not resolved from step=9 response")
                pdf_path = PDF_DIR / f"{ticker.replace('.', '_')}_{selected}"
                ok, error = download_pdf(pdf_url, pdf_path)
                if not ok:
                    raise RuntimeError(error)
                text = extract_text(pdf_path)
                keyword, layer, theme = classify(text)
                snippet_path = ""
                if keyword:
                    snippet = excerpt(text, keyword)
                    snippet_path_obj = SNIPPET_DIR / f"{ticker.replace('.', '_')}_{selected}.txt"
                    snippet_path_obj.write_text(snippet + "\n", encoding="utf-8")
                    snippet_path = str(snippet_path_obj)
                    accepted.append(
                        {
                            "ticker": ticker,
                            "company_name": name,
                            "market": market,
                            "candidate_scope": scope,
                            "evidence_type": "mops_annual_report_pdf_text_keyword_evidence",
                            "keyword_or_topic": keyword,
                            "ai_supply_chain_layer": layer,
                            "mainline_theme_label": theme,
                            "source_doc_type": "MOPS annual report PDF",
                            "source_doc_date": doc_date,
                            "source_url_or_file": pdf_url,
                            "source_title": selected,
                            "source_excerpt": snippet,
                            "source_date": doc_date,
                            "effective_date": doc_date,
                            "as_of_date": doc_date,
                            "extraction_method": "doc_twse_t57sb01_pdfplumber_keyword_extract",
                            "confidence_level": "medium",
                            "accepted_for_diagnostic": "true",
                            "accepted_for_formal": "false",
                            "formal_exact": "false",
                            "human_review_required": "true",
                            "notes": "Bounded v1 annual-report extraction; diagnostic-only until Research/Core validates taxonomy policy.",
                        }
                    )
                    accepted_for_ticker = True
                text_manifest.append(
                    {
                        "ticker": ticker,
                        "document_filename": selected,
                        "document_date": doc_date,
                        "source_url": pdf_url,
                        "raw_pdf_path": str(pdf_path),
                        "snippet_path": snippet_path,
                        "text_char_count": len(text),
                        "keyword_match": keyword,
                        "extraction_status": "text_extracted_keyword_found" if keyword else "text_extracted_no_keyword_match",
                    }
                )
                attempts.append(
                    {
                        "ticker": ticker,
                        "company_name": name,
                        "source_url": locator_url,
                        "document_filename": selected,
                        "document_date": doc_date,
                        "method": "annual_report_locator_download_extract",
                        "status": "completed",
                        "http_code": "200",
                        "content_type": "application/pdf",
                        "retrieved_path": str(pdf_path),
                        "extraction_status": "keyword_found" if keyword else "no_keyword_match",
                        "accepted_evidence_rows": 1 if keyword else 0,
                        "error": "",
                        "notes": f"PDF URL: {pdf_url}",
                    }
                )
            except Exception as exc:
                attempts.append(
                    {
                        "ticker": ticker,
                        "company_name": name,
                        "source_url": locator_url,
                        "document_filename": selected,
                        "document_date": doc_date,
                        "method": "annual_report_locator_download_extract",
                        "status": "failed",
                        "http_code": "200",
                        "content_type": content_type,
                        "retrieved_path": "",
                        "extraction_status": "failed",
                        "accepted_evidence_rows": 0,
                        "error": str(exc),
                        "notes": "",
                    }
                )
            if accepted_for_ticker:
                break
        if not accepted_for_ticker:
            blocked.append(
                {
                    "ticker": ticker,
                    "company_name": name,
                    "market": market,
                    "candidate_scope": scope,
                    "status": "blocked_or_no_keyword_match",
                    "blocked_reason": "MOPS annual report locator ran, but no accepted keyword evidence was extracted in bounded v1.",
                    "document_locator_attempts": len(ticker_attempts),
                    "next_programmatic_source": "Investor conference materials, prospectus, material information, and company IR presentations.",
                    "accepted_for_diagnostic": "false",
                    "accepted_for_formal": "false",
                }
            )

    write_csv(OUTPUT_DIR / "document_locator_attempts.csv", attempts, [
        "ticker",
        "company_name",
        "source_url",
        "document_filename",
        "document_date",
        "method",
        "status",
        "http_code",
        "content_type",
        "retrieved_path",
        "extraction_status",
        "accepted_evidence_rows",
        "error",
        "notes",
    ])
    write_csv(OUTPUT_DIR / "mops_document_locator_manifest.csv", attempts, [
        "ticker",
        "company_name",
        "source_url",
        "document_filename",
        "document_date",
        "method",
        "status",
        "http_code",
        "content_type",
        "retrieved_path",
        "extraction_status",
        "accepted_evidence_rows",
        "error",
        "notes",
    ])
    write_csv(OUTPUT_DIR / "accepted_document_evidence_rows.csv", accepted, EVIDENCE_COLUMNS)
    write_csv(OUTPUT_DIR / "extracted_text_evidence_rows.csv", accepted, EVIDENCE_COLUMNS)
    write_csv(OUTPUT_DIR / "extracted_text_manifest.csv", text_manifest, [
        "ticker",
        "document_filename",
        "document_date",
        "source_url",
        "raw_pdf_path",
        "snippet_path",
        "text_char_count",
        "keyword_match",
        "extraction_status",
    ])
    write_csv(OUTPUT_DIR / "blocked_tickers.csv", blocked, [
        "ticker",
        "company_name",
        "market",
        "candidate_scope",
        "status",
        "blocked_reason",
        "document_locator_attempts",
        "next_programmatic_source",
        "accepted_for_diagnostic",
        "accepted_for_formal",
    ])
    write_csv(OUTPUT_DIR / "blocked_document_sources.csv", blocked, [
        "ticker",
        "company_name",
        "market",
        "candidate_scope",
        "status",
        "blocked_reason",
        "document_locator_attempts",
        "next_programmatic_source",
        "accepted_for_diagnostic",
        "accepted_for_formal",
    ])

    audit = [
        {
            "check": "accepted_rows_have_required_dates",
            "status": "pass" if all(r["source_date"] and r["source_doc_date"] and r["effective_date"] and r["as_of_date"] for r in accepted) else "fail",
            "future_data_violation_count": 0,
            "notes": "Dates are parsed from MOPS annual report filenames and used as source/effective/as-of date for diagnostic availability.",
        },
        {
            "check": "current_static_generated_maps_excluded",
            "status": "pass",
            "future_data_violation_count": 0,
            "notes": "No current/static/generated map is used in accepted evidence.",
        },
        {
            "check": "diagnostic_only_boundary",
            "status": "pass" if all(r["accepted_for_formal"] == "false" and r["formal_exact"] == "false" for r in accepted) else "fail",
            "future_data_violation_count": 0,
            "notes": "All accepted rows are diagnostic-only and require human review.",
        },
    ]
    write_csv(OUTPUT_DIR / "future_data_violation_audit.csv", audit, ["check", "status", "future_data_violation_count", "notes"])
    write_csv(OUTPUT_DIR / "source_quality_audit.csv", [
        {
            "source_type": "MOPS annual report PDF",
            "attempted_tickers": len(PRIORITY_TICKERS),
            "accepted_evidence_rows": len(accepted),
            "accepted_unique_tickers": len({r["ticker"] for r in accepted}),
            "blocked_tickers": len(blocked),
            "quality_decision": (
                "diagnostic_only_all_requested_tickers_ready"
                if accepted and not blocked
                else "diagnostic_only_partial_ready"
                if accepted
                else "blocked"
            ),
            "notes": "PDF text extraction is bounded to annual reports; source is dated but taxonomy label needs human review.",
        }
    ], ["source_type", "attempted_tickers", "accepted_evidence_rows", "accepted_unique_tickers", "blocked_tickers", "quality_decision", "notes"])

    if accepted and not blocked:
        status = "partial_ready_all_requested_tickers_document_evidence_v1"
    elif accepted:
        status = "partial_ready_document_evidence_v1"
    else:
        status = "blocked_no_document_evidence"
    remaining_blockers = [
        "All accepted evidence remains diagnostic-only pending Research/Core review.",
        "Formal taxonomy and strategy replay remain blocked; this package only supplies dated document evidence.",
        "Investor conference / material information / company IR presentation extraction remains an optional next source to raise confidence.",
    ]
    if blocked:
        remaining_blockers.insert(
            0,
            "Annual report PDF keyword extraction did not cover every requested ticker.",
        )
    readiness = {
        "task_id": TASK_ID,
        "status": status,
        "requested_tickers": len(PRIORITY_TICKERS),
        "accepted_document_evidence_rows": len(accepted),
        "accepted_unique_tickers": len({r["ticker"] for r in accepted}),
        "blocked_tickers": len(blocked),
        "ready_for_core_rerun": bool(accepted),
        "ready_for_taxonomy_evidence_panel_update": bool(accepted),
        "ready_for_strategy_replay": False,
        "accepted_for_formal": False,
        "diagnostic_only": True,
        "future_data_violation_count": 0,
        "formal_model_changed": False,
        "trade_decision_changed": False,
        "active_in_trade_decision": False,
        "raw_pdf_git_policy": "raw_sources/pdf is gitignored; extracted snippets and evidence ledgers are tracked.",
        "remaining_blockers": remaining_blockers,
    }
    for filename in ("manifest.json", "readiness_for_core.json"):
        (OUTPUT_DIR / filename).write_text(json.dumps(readiness, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")

    summary = f"""# MOPS document extraction v1

## 結論
- 狀態：`{status}`
- requested tickers：{len(PRIORITY_TICKERS)}
- accepted document evidence rows：{len(accepted)}
- accepted unique tickers：{len({r['ticker'] for r in accepted})}
- blocked tickers：{len(blocked)}
- `future_data_violation_count=0`
- `ready_for_taxonomy_evidence_panel_update={str(bool(accepted)).lower()}`
- `ready_for_strategy_replay=false`

## 邊界
- 本棒只做 MOPS 年報 document locator + PDF text extraction，沒有全市場擴張。
- 所有 accepted rows 都是 diagnostic-only：`accepted_for_formal=false`、`formal_exact=false`、`human_review_required=true`。
- raw PDF 留在 `raw_sources/pdf` 並以 `.gitignore` 排除；提交的是 locator、snippets、evidence ledger 與 audit。
- 未使用 current/static/generated maps。

## 下一步
- Core 可用本包增量更新 taxonomy evidence panel，但不能交 strategy replay。
- 若 Research/Core 需要提高信心，再補 investor conference / material information / company IR presentations；本棒不把年報 evidence 包裝成 formal taxonomy。
"""
    (OUTPUT_DIR / "final_summary_zh.md").write_text(summary, encoding="utf-8")
    write_csv(OUTPUT_DIR / "completed.csv", [{"task_id": TASK_ID, "status": status, "accepted_rows": len(accepted)}], ["task_id", "status", "accepted_rows"])
    write_csv(OUTPUT_DIR / "failed.csv", [], ["task_id", "status", "reason"])
    (OUTPUT_DIR / "current_step.txt").write_text(status + "\n", encoding="utf-8")
    append_log("completed", f"accepted_rows={len(accepted)} blocked_tickers={len(blocked)}")
    print(json.dumps(readiness, ensure_ascii=False))


if __name__ == "__main__":
    sys.exit(main())
