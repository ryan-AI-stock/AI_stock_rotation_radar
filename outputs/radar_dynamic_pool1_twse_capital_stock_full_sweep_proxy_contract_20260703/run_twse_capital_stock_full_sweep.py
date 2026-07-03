import csv
import json
import re
import sys
import time
from datetime import datetime, timezone
from pathlib import Path
from urllib import request

from bs4 import BeautifulSoup


OUT = Path(__file__).resolve().parent
RAW = OUT / "raw_sources"
RAW.mkdir(exist_ok=True)

FIELDS = [
    "ticker",
    "name",
    "date_or_period",
    "fiscal_year",
    "quarter",
    "market",
    "capital_stock",
    "issued_shares",
    "market_cap",
    "source_date",
    "available_date",
    "source_url",
    "source_route",
    "source_type",
    "formal_exact",
    "raw_source_id",
    "table_index",
    "treasury_stock",
    "pending_cancel_shares",
    "prepaid_equity_shares",
    "notes",
]


def now_iso():
    return datetime.now(timezone.utc).astimezone().isoformat()


def write_csv(path: Path, fieldnames, rows):
    with path.open("w", encoding="utf-8-sig", newline="") as f:
        writer = csv.DictWriter(f, fieldnames=fieldnames)
        writer.writeheader()
        for row in rows:
            writer.writerow({k: row.get(k, "") for k in fieldnames})


def append_csv(path: Path, fieldnames, rows):
    exists = path.exists()
    with path.open("a", encoding="utf-8-sig", newline="") as f:
        writer = csv.DictWriter(f, fieldnames=fieldnames)
        if not exists:
            writer.writeheader()
        for row in rows:
            writer.writerow({k: row.get(k, "") for k in fieldnames})


def completed_periods():
    path = OUT / "completed.csv"
    if not path.exists():
        return set()
    with path.open("r", encoding="utf-8-sig", newline="") as f:
        return {r["period"] for r in csv.DictReader(f) if r.get("status") == "completed"}


def conservative_available_date(fiscal_year: int, quarter: int) -> str:
    if quarter == 1:
        return f"{fiscal_year}-05-15"
    if quarter == 2:
        return f"{fiscal_year}-08-14"
    if quarter == 3:
        return f"{fiscal_year}-11-14"
    return f"{fiscal_year + 1}-03-31"


def normalize_number(value):
    value = str(value or "").strip().replace(",", "")
    if value in {"", "--", "---", "nan", "None"}:
        return ""
    return value


def post_json(url: str, payload: dict, referer: str, timeout: int = 30):
    data = json.dumps(payload, ensure_ascii=False).encode("utf-8")
    req = request.Request(
        url,
        data=data,
        method="POST",
        headers={
            "User-Agent": "Mozilla/5.0",
            "Referer": referer,
            "Content-Type": "application/json",
            "Accept": "application/json,text/html,*/*",
        },
    )
    with request.urlopen(req, timeout=timeout) as resp:
        return resp.status, resp.headers.get("Content-Type", ""), resp.read()


def get_url(url: str, referer: str, timeout: int = 90):
    req = request.Request(
        url,
        headers={"User-Agent": "Mozilla/5.0", "Referer": referer, "Accept": "text/html,application/json,*/*"},
    )
    with request.urlopen(req, timeout=timeout) as resp:
        return resp.status, resp.headers.get("Content-Type", ""), resp.read()


def parse_balance_sheet_html(html: str, fiscal_year: int, quarter: int, url: str, raw_id: str):
    soup = BeautifulSoup(html, "html.parser")
    rows = []
    table_count = 0
    total_data_rows = 0
    for table_idx, table in enumerate(soup.find_all("table")):
        trs = table.find_all("tr")
        if not trs:
            continue
        header = [c.get_text(strip=True).replace("\n", "") for c in trs[0].find_all(["th", "td"])]
        if len(header) < 3 or "公司代號" not in "".join(header[:2]) or "公司名稱" not in header[:3]:
            continue
        table_count += 1
        col_index = {name: idx for idx, name in enumerate(header)}
        # Some MOPS headers render "公司代號" as "公司代號" or "公司代號" with <br>.
        code_idx = next((idx for idx, name in enumerate(header) if "公司" in name and "代號" in name), 0)
        name_idx = next((idx for idx, name in enumerate(header) if name == "公司名稱"), 1)

        def cell(cells, *names):
            for name in names:
                idx = col_index.get(name)
                if idx is not None and idx < len(cells):
                    return normalize_number(cells[idx])
            return ""

        for tr in trs[1:]:
            cells = [c.get_text(strip=True) for c in tr.find_all(["th", "td"])]
            if len(cells) < 3:
                continue
            ticker = cells[code_idx].strip() if code_idx < len(cells) else ""
            if not re.fullmatch(r"\d{4}", ticker):
                continue
            total_data_rows += 1
            rows.append(
                {
                    "ticker": ticker,
                    "name": cells[name_idx].strip() if name_idx < len(cells) else "",
                    "date_or_period": f"{fiscal_year}Q{quarter}",
                    "fiscal_year": fiscal_year,
                    "quarter": quarter,
                    "market": "TWSE",
                    "capital_stock": cell(cells, "股本"),
                    "issued_shares": "",
                    "market_cap": "",
                    "source_date": now_iso()[:10],
                    "available_date": conservative_available_date(fiscal_year, quarter),
                    "source_url": url,
                    "source_route": "mops_spa_redirectToOld/ajax_t163sb05_balance_sheet",
                    "source_type": "quarterly_capital_stock_source_candidate_no_exact_filing_date",
                    "formal_exact": "false",
                    "raw_source_id": raw_id,
                    "table_index": table_idx,
                    "treasury_stock": cell(cells, "庫藏股票"),
                    "pending_cancel_shares": cell(cells, "待註銷股本股數", "待註銷股本股數（單位：股）"),
                    "prepaid_equity_shares": cell(cells, "預收股款（權益項下）之約當發行股數", "預收股款（權益項下）之約當發行股數（單位：股）"),
                    "notes": "Quarterly balance-sheet capital stock. Proxy input only; not daily issued shares and not direct market cap.",
                }
            )
    return rows, table_count, total_data_rows


def periods():
    for fiscal_year in range(2015, 2027):
        max_q = 1 if fiscal_year == 2026 else 4
        for quarter in range(1, max_q + 1):
            yield fiscal_year, quarter


def main():
    api = "https://mops.twse.com.tw/mops/api/redirectToOld"
    referer = "https://mops.twse.com.tw/mops/#/web/t163sb05"
    done = completed_periods()
    for fiscal_year, quarter in periods():
        period = f"{fiscal_year}Q{quarter}"
        if period in done:
            continue
        tw_year = str(fiscal_year - 1911)
        season = f"{quarter:02d}"
        label = f"t163sb05_sii_{tw_year}q{season}"
        params = {
            "TYPEK": "sii",
            "year": tw_year,
            "season": season,
            "encodeURIComponent": 1,
            "firstin": 1,
            "off": 1,
            "step": 1,
            "isQuery": "Y",
        }
        payload = {"apiName": "ajax_t163sb05", "parameters": params}
        try:
            status, ctype, body = post_json(api, payload, referer)
            redirect_text = body.decode("utf-8", errors="ignore")
            redirect_path = RAW / f"{label}_redirect.json"
            redirect_path.write_text(redirect_text, encoding="utf-8")
            data_url = json.loads(redirect_text).get("result", {}).get("url", "")
            append_csv(
                OUT / "route_request_attempts.csv",
                ["period", "source", "method", "url", "http_code", "content_type", "status", "row_count", "retrieved_path", "error"],
                [{
                    "period": period,
                    "source": "MOPS redirectToOld ajax_t163sb05",
                    "method": "POST",
                    "url": api,
                    "http_code": status,
                    "content_type": ctype,
                    "status": "redirect_url_generated" if data_url else "no_redirect_url",
                    "row_count": "",
                    "retrieved_path": str(redirect_path.relative_to(OUT)),
                    "error": "",
                }],
            )
            if not data_url:
                raise RuntimeError("redirectToOld returned no data URL")
            status2, ctype2, html_body = get_url(data_url, referer)
            html = html_body.decode("utf-8", errors="ignore")
            html_path = RAW / f"{label}_response.html"
            html_path.write_text(html, encoding="utf-8")
            rows, table_count, total_rows = parse_balance_sheet_html(
                html, fiscal_year, quarter, data_url, str(html_path.relative_to(OUT))
            )
            if rows:
                append_csv(OUT / "accepted_twse_capital_stock_rows.csv", FIELDS, rows)
            append_csv(
                OUT / "route_request_attempts.csv",
                ["period", "source", "method", "url", "http_code", "content_type", "status", "row_count", "retrieved_path", "error"],
                [{
                    "period": period,
                    "source": "MOPS mopsov ajax_t163sb05",
                    "method": "GET",
                    "url": data_url,
                    "http_code": status2,
                    "content_type": ctype2,
                    "status": "parsed_capital_stock_rows" if rows else "fetched_no_rows",
                    "row_count": total_rows,
                    "retrieved_path": str(html_path.relative_to(OUT)),
                    "error": "",
                }],
            )
            append_csv(
                OUT / "completed.csv",
                ["period", "completed_at", "status", "row_count"],
                [{"period": period, "completed_at": now_iso(), "status": "completed", "row_count": len(rows)}],
            )
            (OUT / "current_step.txt").write_text(f"completed {period} rows={len(rows)}\n", encoding="utf-8")
            time.sleep(0.35)
        except Exception as exc:
            append_csv(
                OUT / "failed.csv",
                ["period", "failed_at", "status", "error"],
                [{"period": period, "failed_at": now_iso(), "status": "failed", "error": repr(exc)}],
            )
            append_csv(
                OUT / "route_request_attempts.csv",
                ["period", "source", "method", "url", "http_code", "content_type", "status", "row_count", "retrieved_path", "error"],
                [{
                    "period": period,
                    "source": "MOPS ajax_t163sb05",
                    "method": "POST/GET",
                    "url": api,
                    "http_code": "",
                    "content_type": "",
                    "status": "error",
                    "row_count": "",
                    "retrieved_path": "",
                    "error": repr(exc),
                }],
            )
            (OUT / "current_step.txt").write_text(f"failed {period}: {repr(exc)}\n", encoding="utf-8")
            time.sleep(1.0)


if __name__ == "__main__":
    sys.exit(main())
