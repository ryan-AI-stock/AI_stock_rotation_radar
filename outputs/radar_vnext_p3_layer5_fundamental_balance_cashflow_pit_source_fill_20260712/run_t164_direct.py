import hashlib
import json
import re
import time
from concurrent.futures import ThreadPoolExecutor, as_completed

import requests

import build_package as bp


API = "https://mops.twse.com.tw/mops/api"
HEADERS = {
    "Content-Type": "application/json",
    "Accept": "application/json, text/plain, */*",
    "Origin": "https://mops.twse.com.tw",
    "Referer": "https://mops.twse.com.tw/mops/#/web/t05st01",
    "User-Agent": "Mozilla/5.0",
    "Accept-Language": "zh-TW,zh;q=0.9",
}

LOCAL_CACHE_INDEX = {}
for cache_path in bp.OUT.parents[1].glob("outputs/**/raw_cache/t164sb0*.json"):
    match = re.match(r"(t164sb0[35])_(\d{4})_(\d{3})Q([1-4])_", cache_path.name)
    if match:
        LOCAL_CACHE_INDEX[(match.group(1), match.group(2), int(match.group(3)) + 1911, int(match.group(4)))] = cache_path


def value(rows, patterns):
    for row in rows:
        label = bp.clean_label(row[0] if row else "")
        if any(re.search(pattern, label) for pattern in patterns):
            return bp.clean_number(row[1] if len(row) > 1 else ""), row[0]
    return "", ""


def fetch_one(report_type, year, quarter, ticker, info):
    route = "t164sb03" if report_type == "balance" else "t164sb05"
    payload = {"companyId": ticker, "dataType": "2", "year": str(year - 1911), "season": str(quarter), "subsidiaryCompanyId": ""}
    local_cache = LOCAL_CACHE_INDEX.get((route, ticker, year, quarter))
    last_error = ""
    for attempt in range(3):
        try:
            if local_cache is not None and attempt == 0:
                raw = local_cache.read_bytes()
                source_route = f"local_reuse:{local_cache.relative_to(bp.OUT.parents[1])}"
            else:
                response = requests.post(f"{API}/{route}", json=payload, headers=HEADERS, timeout=30)
                response.raise_for_status()
                raw = response.content
                source_route = f"POST {API}/{route}"
            digest = hashlib.sha256(raw).hexdigest()
            parsed = json.loads(raw.decode("utf-8-sig"))
            rows = ((parsed.get("result") or {}).get("reportList") or [])
            if parsed.get("code") != 200 or not rows:
                raise ValueError(f"MOPS code={parsed.get('code')} message={parsed.get('message')}")
            mapped = {}
            if report_type == "balance":
                mapped["total_assets"], _ = value(rows, [r"^(資產總額|資產總計)$"])
                mapped["total_liabilities"], _ = value(rows, [r"^(負債總額|負債總計)$"])
                mapped["total_equity"], _ = value(rows, [r"^(權益總額|權益總計)$"])
                mapped["current_assets"], _ = value(rows, [r"^流動資產(合計)?$"])
                mapped["current_liabilities"], _ = value(rows, [r"^流動負債(合計)?$"])
            else:
                mapped["operating_cash_flow"], _ = value(rows, [r"營業活動之淨現金流入\(流出\)", r"營業活動之淨現金流量", r"營業活動淨現金流量"])
                mapped["investing_cash_flow"], _ = value(rows, [r"投資活動之淨現金流入\(流出\)", r"投資活動之淨現金流量", r"投資活動淨現金流量"])
                mapped["capex_proxy"], mapped["capex_proxy_label"] = value(rows, [r"取得不動產、廠房及設備", r"購置不動產、廠房及設備"])
            financial = any(token in str(info.get("industry", "")) for token in ("金融", "銀行", "保險", "證券", "金控", "異業"))
            out = {
                "ticker": ticker,
                "name": info.get("name", ""),
                "market": info.get("market", ""),
                "industry_profile": info.get("industry", ""),
                "financial_profile": financial,
                "fiscal_year": year,
                "quarter": quarter,
                "report_period": f"{year}Q{quarter}",
                "statement_basis": "cumulative" if report_type == "cashflow" else "period_end",
                "available_date": bp.available_date(year, quarter),
                "available_date_quality": "conservative_statutory_deadline_proxy_diagnostic",
                "exact_publication_timestamp_available": False,
                "source": "MOPS official t164 financial statement API",
                "source_route": source_route,
                "source_url": f"https://mops.twse.com.tw/mops/#/web/{route}",
                "response_hash": digest,
                "response_bytes": len(raw),
                "source_quality": "official_period_specific_diagnostic_pit_proxy",
                "human_review_required": report_type == "cashflow" and bool(mapped.get("capex_proxy")),
                "accepted_for_formal": False,
                "future_data_violation_count": 0,
                **mapped,
                **bp.FLAGS,
            }
            return ticker, out, None, len(raw), digest, attempt + 1
        except Exception as exc:
            last_error = repr(exc)
            time.sleep(0.4 * (attempt + 1))
    return ticker, None, last_error, 0, "", 3


def main():
    _, req_rows = bp.extract_requirements()
    info = {}
    for row in req_rows:
        info[row["ticker"]] = {"name": row["name"], "market": row["market"], "industry": ""}
    work = bp.build_work(req_rows)
    result_cache = bp.OUT / "batch_results"
    result_cache.mkdir(exist_ok=True)
    completed = set()
    for path in result_cache.glob("*.json"):
        try:
            existing = json.loads(path.read_text(encoding="utf-8"))
            if existing.get("manifest", {}).get("route_status") in {"accepted", "partial"}:
                completed.add(path.stem)
        except Exception:
            pass
    total = len(work)
    for position, item in enumerate(work, 1):
        report_type, year, quarter, batch_index, ids = item
        key = f"{report_type}_{year}Q{quarter}_b{batch_index:03d}"
        if key in completed:
            continue
        rows = []
        missing = []
        response_bytes = 0
        hashes = []
        attempts = 0
        errors = []
        with ThreadPoolExecutor(max_workers=min(8, len(ids))) as pool:
            futures = {pool.submit(fetch_one, report_type, year, quarter, ticker, info[ticker]): ticker for ticker in ids}
            for future in as_completed(futures):
                ticker, row, error, byte_count, digest, attempt_count = future.result()
                attempts += attempt_count
                response_bytes += byte_count
                if digest:
                    hashes.append(digest)
                if row:
                    rows.append(row)
                else:
                    missing.append(ticker)
                    errors.append(f"{ticker}:{error}")
        aggregate_hash = hashlib.sha256("".join(sorted(hashes)).encode("ascii")).hexdigest() if hashes else ""
        manifest = {
            "batch_key": key,
            "report_type": report_type,
            "report_period": f"{year}Q{quarter}",
            "request_ticker_count": len(ids),
            "returned_ticker_count": len(rows),
            "missing_ticker_count": len(missing),
            "http_status": 200 if rows else "",
            "response_bytes": response_bytes,
            "response_hash": aggregate_hash,
            "attempt_count": attempts,
            "route_status": "accepted" if rows and not missing else "partial" if rows else "failed",
            "source_url": f"{API}/{'t164sb03' if report_type == 'balance' else 't164sb05'}",
            "retrieved_at": bp.NOW,
            "error": " | ".join(errors),
            **bp.FLAGS,
        }
        bp.write_json(result_cache / f"{key}.json", {"rows": rows, "missing": missing, "manifest": manifest})
        completed.add(key)
        bp.save_checkpoint(completed, total, f"t164_direct {len(completed)}/{total} last={key}")
        if position % 10 == 0:
            print(f"{len(completed)}/{total} {key}", flush=True)
    bp.CURRENT_STEP.write_text("t164_direct_complete_finalize_with_build_package", encoding="utf-8")
    print(f"complete batches={len(completed)}/{total}", flush=True)


if __name__ == "__main__":
    main()
