from __future__ import annotations

import csv
import hashlib
import json
import re
import time
from pathlib import Path
from urllib.parse import quote

import requests

OUT = Path("outputs/radar_tw50_0050_historical_source_download_201411_202312_20260629")
RAW = OUT / "raw_sources"
RAW.mkdir(parents=True, exist_ok=True)

TARGETS = [
    ("2014Q4", "2014-12-31", "20141231"),
    ("2016Q1", "2016-03-31", "20160331"),
    ("2021Q4", "2021-12-31", "20211231"),
    ("2023Q4", "2023-12-31", "20231231"),
]

SOURCES = [
    ("yuanta_0050_monthly", "monthly_report", "https://www.yuantafunds.com/fund/download/1066元大台灣卓越50基金月報.pdf"),
    ("yuanta_domestic_quarterly_holdings", "quarterly_holdings", "https://www.yuantafunds.com/fund/download/元大國內基金季持股.pdf"),
]

HEADERS = {
    "User-Agent": "Mozilla/5.0 RadarDataFastProbe/1.0",
    "Accept": "application/pdf,text/html,application/json,*/*",
}


def ts() -> str:
    return time.strftime("%Y-%m-%dT%H:%M:%S+08:00")


def safe(s: str) -> str:
    return re.sub(r"[^A-Za-z0-9_.-]+", "_", s).strip("_")[:180]


def get(url: str, timeout: int = 6, max_bytes: int = 2_000_000):
    try:
        with requests.get(url, headers=HEADERS, timeout=(3, timeout), stream=True, allow_redirects=True) as r:
            chunks = []
            total = 0
            for chunk in r.iter_content(chunk_size=65536):
                if not chunk:
                    continue
                chunks.append(chunk)
                total += len(chunk)
                if total >= max_bytes:
                    break
            return r.status_code, r.headers.get("content-type", ""), b"".join(chunks), r.url, ""
    except Exception as exc:
        return "", "", b"", "", f"{type(exc).__name__}: {exc}"


def wayback_available(url: str, stamp: str) -> str:
    return "https://archive.org/wayback/available?url=" + quote(url, safe="") + "&timestamp=" + stamp


def wayback_direct(url: str, stamp: str) -> str:
    return "https://web.archive.org/web/" + stamp + "id_/" + url


def cdx(url: str, stamp: str) -> str:
    start = stamp[:6]
    end = str(int(stamp[:4]) + 1) + stamp[4:6]
    return (
        "https://web.archive.org/cdx?url="
        + quote(url, safe="")
        + f"&from={start}&to={end}&output=json&fl=timestamp,original,statuscode,mimetype,digest&filter=statuscode:200&limit=5"
    )


def write_csv(path: Path, rows: list[dict], fields: list[str]) -> None:
    with path.open("w", newline="", encoding="utf-8") as fh:
        w = csv.DictWriter(fh, fieldnames=fields, extrasaction="ignore")
        w.writeheader()
        w.writerows(rows)


def main() -> None:
    attempts = []
    raw_manifest = []
    parsed = []
    accepted = []
    run_log = [{"timestamp": ts(), "step": "start_fast_probe", "status": "running", "details": "Short-timeout bounded probe started."}]
    (OUT / "current_step.txt").write_text("running_fast_probe\n", encoding="utf-8")

    for period, target_date, stamp in TARGETS:
        for sid, kind, src_url in SOURCES:
            probes = [
                ("direct_official_fixed_url", src_url),
                ("wayback_available", wayback_available(src_url, stamp)),
                ("wayback_direct_timestamp", wayback_direct(src_url, stamp)),
                ("wayback_cdx_bounded", cdx(src_url, stamp)),
            ]
            for attempt_type, url in probes:
                code, ctype, body, final_url, err = get(url, timeout=6, max_bytes=2_000_000)
                status = "error" if err else ("http_ok" if code and int(code) < 400 else "http_non_ok")
                retrieved_path = ""
                note = ""
                if attempt_type == "wayback_available" and body:
                    try:
                        payload = json.loads(body.decode("utf-8", errors="replace"))
                        closest = payload.get("archived_snapshots", {}).get("closest", {})
                        note = "closest_timestamp={}; closest_status={}; closest_url={}".format(
                            closest.get("timestamp", ""), closest.get("status", ""), closest.get("url", "")
                        )
                    except Exception as exc:
                        note = f"availability_json_error={type(exc).__name__}: {exc}"
                elif attempt_type == "wayback_cdx_bounded" and body:
                    try:
                        payload = json.loads(body.decode("utf-8", errors="replace"))
                        note = f"cdx_rows={max(0, len(payload)-1) if isinstance(payload, list) else 0}"
                    except Exception as exc:
                        note = f"cdx_json_error={type(exc).__name__}: {exc}"
                elif attempt_type == "wayback_direct_timestamp" and code == 200 and body:
                    fname = safe(f"{period}_{sid}_{stamp}.bin")
                    if b"%PDF" in body[:1024] or "pdf" in ctype.lower():
                        fname = fname[:-4] + ".pdf"
                    path = RAW / fname
                    path.write_bytes(body)
                    retrieved_path = str(path).replace("\\", "/")
                    raw_manifest.append(
                        {
                            "source_id": f"{period}_{sid}_{stamp}",
                            "raw_file_path": retrieved_path,
                            "source_url_or_reference": final_url or url,
                            "document_date": target_date,
                            "covered_effective_start": target_date,
                            "covered_effective_end": target_date,
                            "source_type": "source_backed_manual_proxy",
                            "archive_status": "downloaded_wayback_direct_candidate",
                            "checksum_sha256": hashlib.sha256(body).hexdigest(),
                            "notes": "Downloaded by timestamp direct Wayback URL; content/date review required before acceptance.",
                        }
                    )
                if attempt_type == "direct_official_fixed_url":
                    note = "Rolling/current official URL probe only; never accepted as historical without dated archive."
                attempts.append(
                    {
                        "source": sid,
                        "target_period": period,
                        "url": url,
                        "attempt_type": attempt_type,
                        "status": status,
                        "http_code": code,
                        "content_type": ctype,
                        "bytes": len(body),
                        "error": err,
                        "retrieved_path": retrieved_path,
                        "notes": note,
                    }
                )

    missing = []
    for period, target_date, _ in TARGETS:
        accepted_count = sum(1 for r in accepted if r.get("target_period") == period)
        parsed_count = sum(1 for r in parsed if r.get("target_period") == period)
        raw_count = sum(1 for r in raw_manifest if r["source_id"].startswith(period + "_"))
        missing.append(
            {
                "period_id": period,
                "target_date": target_date,
                "raw_candidates": raw_count,
                "parsed_sample_rows": parsed_count,
                "accepted_rows": accepted_count,
                "status": "accepted" if accepted_count else ("raw_candidate_needs_review" if raw_count else "missing"),
                "blocker": "No reviewed dated historical 0050 holdings rows accepted.",
                "next_programmatic_attempt": "Search archived Yuanta HTML/product pages for historical PDF hrefs, not only fixed rolling PDF URLs.",
            }
        )

    quality = [
        {
            "source_family": "official_fixed_urls",
            "decision": "attempted_not_accepted_as_historical",
            "formal_exact": "false",
            "manual_proxy_allowed": "true_if_dated_snapshot",
            "rationale": "Fixed official URLs are rolling/current; direct 200 responses are not historical PIT evidence.",
        },
        {
            "source_family": "wayback_direct_and_cdx",
            "decision": "attempted_with_http_evidence",
            "formal_exact": "false",
            "manual_proxy_allowed": "true_if_pdf_date_and_rows_reviewed",
            "rationale": "Wayback snapshots can become source-backed manual/proxy evidence only after content/date review and row extraction.",
        },
    ]

    attempt_fields = ["source", "target_period", "url", "attempt_type", "status", "http_code", "content_type", "bytes", "error", "retrieved_path", "notes"]
    write_csv(OUT / "download_attempts.csv", attempts, attempt_fields)
    write_csv(OUT / "raw_source_archive_manifest.csv", raw_manifest, ["source_id", "raw_file_path", "source_url_or_reference", "document_date", "covered_effective_start", "covered_effective_end", "source_type", "archive_status", "checksum_sha256", "notes"])
    parsed_fields = ["target_period", "holdings_date", "source_id", "source_file", "source_url", "ticker", "name", "weight", "source_type", "formal_exact", "evidence_quality", "parser_status", "notes"]
    write_csv(OUT / "parsed_holdings_sample.csv", parsed, parsed_fields)
    write_csv(OUT / "accepted_historical_rows.csv", accepted, parsed_fields)
    write_csv(OUT / "missing_periods.csv", missing, list(missing[0].keys()))
    write_csv(OUT / "source_quality_decision.csv", quality, list(quality[0].keys()))
    completed = [{"item_id": "fast_probe_matrix", "completed_at": ts(), "status": "completed", "evidence": f"{len(attempts)} attempts across 4 target periods and 2 source families."}]
    failed = [m for m in missing if m["accepted_rows"] == 0]
    write_csv(OUT / "completed.csv", completed, ["item_id", "completed_at", "status", "evidence"])
    write_csv(OUT / "failed.csv", failed, ["period_id", "target_date", "raw_candidates", "parsed_sample_rows", "accepted_rows", "status", "blocker", "next_programmatic_attempt"])
    run_log.append({"timestamp": ts(), "step": "finish_fast_probe", "status": "completed", "details": f"attempts={len(attempts)} raw_candidates={len(raw_manifest)} accepted_rows=0"})
    write_csv(OUT / "run_log.csv", run_log, ["timestamp", "step", "status", "details"])
    manifest = {
        "schema_version": 1,
        "task_id": "TASK-RADAR-DATA-TW50-0050-HISTORICAL-SOURCE-DOWNLOAD-201411-202312-20260629",
        "status": "completed_partial_no_accepted_historical_rows",
        "created_at": ts(),
        "download_attempt_count": len(attempts),
        "raw_source_count": len(raw_manifest),
        "parsed_holdings_sample_rows": 0,
        "accepted_historical_rows": 0,
        "target_periods": [p[0] for p in TARGETS],
        "formal_model_changed": False,
        "trade_decision_changed": False,
        "formal_exact": False,
        "current_snapshot_used_as_historical": False,
        "future_data_violation_count": 0,
        "large_download_started": False,
        "first_runner_status": "stopped_after_network_hang_and_replaced_by_fast_probe",
        "output_dir": str(OUT).replace("\\", "/"),
    }
    (OUT / "manifest.json").write_text(json.dumps(manifest, ensure_ascii=False, indent=2), encoding="utf-8")
    (OUT / "current_step.txt").write_text("completed\n", encoding="utf-8")
    print(json.dumps(manifest, ensure_ascii=False, indent=2))


if __name__ == "__main__":
    main()
