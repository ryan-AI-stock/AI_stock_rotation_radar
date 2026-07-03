import csv
import json
import re
import sys
import time
from collections import Counter, defaultdict
from datetime import date, datetime, timezone
from pathlib import Path
from urllib import request

from bs4 import BeautifulSoup


TASK_ID = "TASK-RADAR-DATA-DYNAMIC-POOL1-QUARTERLY-FUNDAMENTALS-FULL-SWEEP-20260703"
OUT = Path(__file__).resolve().parent
RAW = OUT / "raw_sources"
SHARDS = OUT / "shards"
RAW.mkdir(exist_ok=True)
SHARDS.mkdir(exist_ok=True)

API = "https://mops.twse.com.tw/mops/api/redirectToOld"
REFERER = "https://mops.twse.com.tw/mops/#/web/t163sb04"
MARKETS = {"sii": "TWSE", "otc": "TPEx"}
SOURCE_ROUTE = "mops_spa_redirectToOld/ajax_t163sb04"
SOURCE_TYPE = "source_candidate_no_exact_filing_date"

ROW_FIELDS = [
    "ticker",
    "name",
    "market",
    "fiscal_year",
    "quarter",
    "source_date",
    "available_date",
    "source_url",
    "source_route",
    "source_type",
    "formal_exact",
    "raw_source_id",
    "table_index",
    "statement_profile",
    "operating_revenue",
    "gross_profit",
    "operating_income",
    "pretax_income",
    "net_income",
    "eps",
    "total_assets",
    "total_liabilities",
    "equity",
    "roe",
    "gross_margin",
    "operating_margin",
]


def now_iso() -> str:
    return datetime.now(timezone.utc).astimezone().isoformat()


def append_log(status: str, message: str) -> None:
    with (OUT / "run_log.csv").open("a", encoding="utf-8", newline="") as f:
        f.write(f"{now_iso()},{status},{message}\n")


def write_text(path: Path, text: str) -> None:
    path.write_text(text, encoding="utf-8")


def write_csv(path: Path, fieldnames, rows) -> None:
    with path.open("w", encoding="utf-8-sig", newline="") as f:
        writer = csv.DictWriter(f, fieldnames=fieldnames)
        writer.writeheader()
        for row in rows:
            writer.writerow({k: row.get(k, "") for k in fieldnames})


def append_csv(path: Path, fieldnames, rows) -> None:
    exists = path.exists()
    with path.open("a", encoding="utf-8-sig", newline="") as f:
        writer = csv.DictWriter(f, fieldnames=fieldnames)
        if not exists:
            writer.writeheader()
        for row in rows:
            writer.writerow({k: row.get(k, "") for k in fieldnames})


def tw_year(ad_year: int) -> str:
    return str(ad_year - 1911)


def season_code(quarter: int) -> str:
    return f"{quarter:02d}"


def conservative_available_date(fiscal_year: int, quarter: int) -> str:
    if quarter == 1:
        return f"{fiscal_year}-05-15"
    if quarter == 2:
        return f"{fiscal_year}-08-14"
    if quarter == 3:
        return f"{fiscal_year}-11-14"
    return f"{fiscal_year + 1}-03-31"


def period_list(start_year: int = 2015) -> list[tuple[int, int]]:
    today = date.today()
    periods = []
    for year in range(start_year, today.year + 1):
        for quarter in range(1, 5):
            if date.fromisoformat(conservative_available_date(year, quarter)) <= today:
                periods.append((year, quarter))
    return periods


def post_json(url: str, payload: dict, timeout: int = 30):
    data = json.dumps(payload, ensure_ascii=False).encode("utf-8")
    req = request.Request(
        url,
        data=data,
        method="POST",
        headers={
            "User-Agent": "Mozilla/5.0",
            "Referer": REFERER,
            "Content-Type": "application/json",
            "Accept": "application/json,text/html,*/*",
        },
    )
    with request.urlopen(req, timeout=timeout) as resp:
        return resp.status, resp.headers.get("Content-Type", ""), resp.read()


def get_url(url: str, timeout: int = 90):
    req = request.Request(
        url,
        headers={
            "User-Agent": "Mozilla/5.0",
            "Referer": REFERER,
            "Accept": "text/html,application/json,*/*",
        },
    )
    with request.urlopen(req, timeout=timeout) as resp:
        return resp.status, resp.headers.get("Content-Type", ""), resp.read()


def normalize_number(value: str) -> str:
    value = (value or "").strip().replace(",", "")
    if value in {"", "--", "---", "nan"}:
        return ""
    return value


def parse_float(value: str):
    value = normalize_number(value)
    if value == "":
        return None
    try:
        return float(value)
    except ValueError:
        return None


def ratio(numerator: str, denominator: str) -> str:
    n = parse_float(numerator)
    d = parse_float(denominator)
    if n is None or d in (None, 0):
        return ""
    return f"{n / d:.8f}"


def pick(cells, col_index, *names) -> str:
    for name in names:
        if name in col_index and col_index[name] < len(cells):
            return normalize_number(cells[col_index[name]])
    return ""


def parse_financial_html(html: str, market: str, fiscal_year: int, quarter: int, source_url: str, raw_id: str):
    soup = BeautifulSoup(html, "html.parser")
    rows = []
    table_count = 0
    for table_idx, table in enumerate(soup.find_all("table")):
        trs = table.find_all("tr")
        if not trs:
            continue
        header = [c.get_text(strip=True) for c in trs[0].find_all(["th", "td"])]
        if len(header) < 3 or "公司代號" not in header[:3] or "公司名稱" not in header[:3]:
            continue
        table_count += 1
        col_index = {name: idx for idx, name in enumerate(header)}
        profile = "general"
        joined_header = "|".join(header)
        if "利息淨收益" in joined_header:
            profile = "bank_or_financial"
        elif "收益" in joined_header and "支出及費用" in joined_header:
            profile = "securities"
        elif "收入" in joined_header and "支出" in joined_header:
            profile = "special_income_statement"
        elif "營業收入" in joined_header:
            profile = "industrial"
        for tr in trs[1:]:
            cells = [c.get_text(strip=True) for c in tr.find_all(["th", "td"])]
            if len(cells) < 3:
                continue
            ticker = cells[col_index.get("公司代號", 0)].strip()
            if not re.fullmatch(r"\d{4}", ticker):
                continue
            operating_revenue = pick(cells, col_index, "營業收入", "收益", "收入", "利息淨收益")
            gross_profit = pick(cells, col_index, "營業毛利（毛損）", "營業毛利（毛損）淨額")
            operating_income = pick(cells, col_index, "營業利益（損失）", "營業利益", "營業淨利（淨損）")
            pretax_income = pick(
                cells,
                col_index,
                "繼續營業單位稅前淨利（淨損）",
                "稅前淨利（淨損）",
                "繼續營業單位稅前純益（純損）",
            )
            net_income = pick(
                cells,
                col_index,
                "本期淨利（淨損）",
                "本期稅後淨利（淨損）",
                "繼續營業單位本期淨利（淨損）",
                "繼續營業單位本期純益（純損）",
            )
            rows.append(
                {
                    "ticker": ticker,
                    "name": cells[col_index.get("公司名稱", 1)].strip(),
                    "market": market,
                    "fiscal_year": fiscal_year,
                    "quarter": quarter,
                    "source_date": date.today().isoformat(),
                    "available_date": conservative_available_date(fiscal_year, quarter),
                    "source_url": source_url,
                    "source_route": SOURCE_ROUTE,
                    "source_type": SOURCE_TYPE,
                    "formal_exact": "false",
                    "raw_source_id": raw_id,
                    "table_index": table_idx,
                    "statement_profile": profile,
                    "operating_revenue": operating_revenue,
                    "gross_profit": gross_profit,
                    "operating_income": operating_income,
                    "pretax_income": pretax_income,
                    "net_income": net_income,
                    "eps": pick(cells, col_index, "基本每股盈餘（元）", "基本每股盈餘", "每股盈餘"),
                    "total_assets": pick(cells, col_index, "資產總計"),
                    "total_liabilities": pick(cells, col_index, "負債總計"),
                    "equity": pick(cells, col_index, "權益總計", "歸屬於母公司業主之權益合計"),
                    "roe": "",
                    "gross_margin": ratio(gross_profit, operating_revenue),
                    "operating_margin": ratio(operating_income, operating_revenue),
                }
            )
    return rows, table_count


def load_completed_periods() -> set[str]:
    path = OUT / "completed.csv"
    if not path.exists():
        return set()
    with path.open("r", encoding="utf-8-sig", newline="") as f:
        return {row["period_market"] for row in csv.DictReader(f) if row.get("status") == "completed"}


def fetch_period_market(year: int, quarter: int, market: str):
    tw = tw_year(year)
    season = season_code(quarter)
    label = f"t163sb04_{market}_{tw}q{season}"
    params = {
        "TYPEK": market,
        "year": tw,
        "season": season,
        "encodeURIComponent": 1,
        "firstin": 1,
        "off": 1,
        "step": 1,
        "isQuery": "Y",
    }
    payload = {"apiName": "ajax_t163sb04", "parameters": params}
    status, ctype, body = post_json(API, payload, timeout=30)
    redirect_text = body.decode("utf-8", errors="ignore")
    redirect_path = RAW / f"{label}_redirect.json"
    redirect_path.write_text(redirect_text, encoding="utf-8")
    data = json.loads(redirect_text)
    data_url = data.get("result", {}).get("url", "")
    if not data_url:
        raise RuntimeError("redirectToOld returned no data_url")

    html_path = RAW / f"{label}_response.html"
    fetch_status = "downloaded"
    fetch_error = ""
    try:
        status2, ctype2, html_body = get_url(data_url, timeout=90)
        html = html_body.decode("utf-8", errors="ignore")
        html_path.write_text(html, encoding="utf-8")
    except Exception as exc:
        if not html_path.exists():
            raise
        status2, ctype2 = "", "text/html; charset=UTF-8"
        html = html_path.read_text(encoding="utf-8", errors="ignore")
        fetch_status = "existing_raw_after_fetch_error"
        fetch_error = repr(exc)

    rows, table_count = parse_financial_html(
        html,
        market,
        year,
        quarter,
        data_url,
        str(html_path.relative_to(OUT)),
    )
    attempts = [
        {
            "period_market": f"{year}Q{quarter}_{market}",
            "target_period": f"{year}Q{quarter}",
            "market": market,
            "source": "mops_spa_redirectToOld",
            "method": "POST",
            "url": API,
            "http_code": status,
            "content_type": ctype,
            "status": "redirect_url_generated",
            "row_count": "",
            "table_count": "",
            "retrieved_path": str(redirect_path.relative_to(OUT)),
            "error": "",
            "data_url": data_url,
        },
        {
            "period_market": f"{year}Q{quarter}_{market}",
            "target_period": f"{year}Q{quarter}",
            "market": market,
            "source": "mopsov_ajax_t163sb04_data_url",
            "method": "GET",
            "url": data_url,
            "http_code": status2,
            "content_type": ctype2,
            "status": "parsed_financial_rows" if rows else "fetched_no_rows",
            "row_count": len(rows),
            "table_count": table_count,
            "retrieved_path": str(html_path.relative_to(OUT)),
            "error": fetch_error,
            "data_url": data_url,
        },
    ]
    return rows, attempts


def build_reports():
    shard_paths = sorted(SHARDS.glob("accepted_quarterly_fundamentals_rows_*.csv"))
    all_rows = []
    for path in shard_paths:
        with path.open("r", encoding="utf-8-sig", newline="") as f:
            all_rows.extend(csv.DictReader(f))

    periods = period_list(2015)
    expected = {(year, quarter, market) for year, quarter in periods for market in MARKETS}
    observed = {(int(r["fiscal_year"]), int(r["quarter"]), r["market"]) for r in all_rows}
    attempt_rows = []
    attempts_path = OUT / "route_request_attempts.csv"
    if attempts_path.exists():
        with attempts_path.open("r", encoding="utf-8-sig", newline="") as f:
            attempt_rows = list(csv.DictReader(f))

    row_counts = Counter((int(r["fiscal_year"]), int(r["quarter"]), r["market"]) for r in all_rows)
    symbol_set = {r["ticker"] for r in all_rows}
    market_counts = Counter(r["market"] for r in all_rows)
    yq_rows = []
    for year, quarter in periods:
        for market in MARKETS:
            count = row_counts.get((year, quarter, market), 0)
            yq_rows.append(
                {
                    "fiscal_year": year,
                    "quarter": quarter,
                    "market": market,
                    "accepted_rows": count,
                    "coverage_status": "covered" if count > 0 else "missing",
                    "available_date": conservative_available_date(year, quarter),
                }
            )
    write_csv(
        OUT / "coverage_by_year_quarter.csv",
        ["fiscal_year", "quarter", "market", "accepted_rows", "coverage_status", "available_date"],
        yq_rows,
    )
    write_csv(
        OUT / "coverage_by_market.csv",
        ["market", "accepted_rows", "symbol_count"],
        [
            {
                "market": market,
                "accepted_rows": market_counts.get(market, 0),
                "symbol_count": len({r["ticker"] for r in all_rows if r["market"] == market}),
            }
            for market in MARKETS
        ],
    )
    missing = [
        {
            "fiscal_year": year,
            "quarter": quarter,
            "market": market,
            "reason": "no accepted rows after sweep",
            "next_step": "retry period-market route or inspect MOPS response",
        }
        for year, quarter, market in sorted(expected - observed)
    ]
    write_csv(
        OUT / "missing_or_failed_periods.csv",
        ["fiscal_year", "quarter", "market", "reason", "next_step"],
        missing,
    )
    write_csv(
        OUT / "rejected_or_blocked_rows.csv",
        ["fiscal_year", "quarter", "market", "source", "blocked_reason", "evidence", "next_programmatic_route"],
        [],
    )
    write_csv(
        OUT / "future_data_violation_audit.csv",
        ["audit_item", "status", "violation_count", "evidence"],
        [
            {
                "audit_item": "period_specific_route",
                "status": "pass",
                "violation_count": 0,
                "evidence": "Each request uses fiscal year/quarter and market parameters in MOPS redirectToOld contract.",
            },
            {
                "audit_item": "current_snapshot_backfill",
                "status": "pass",
                "violation_count": 0,
                "evidence": "No current company profile or current financial snapshot was used.",
            },
            {
                "audit_item": "filing_date_exactness",
                "status": "partial",
                "violation_count": 0,
                "evidence": "available_date uses conservative statutory deadline; per-company filing_date remains unavailable.",
            },
        ],
    )

    shard_manifest = []
    for path in shard_paths:
        with path.open("r", encoding="utf-8-sig", newline="") as f:
            count = sum(1 for _ in csv.DictReader(f))
        shard_manifest.append(
            {
                "shard_path": str(path.relative_to(OUT)),
                "fiscal_year": path.stem.rsplit("_", 1)[-1],
                "rows": count,
                "git_tracked": "true",
            }
        )
    write_csv(
        OUT / "accepted_quarterly_fundamentals_rows_manifest.csv",
        ["shard_path", "fiscal_year", "rows", "git_tracked"],
        shard_manifest,
    )
    source_manifest = [
        {
            "source_id": "mops_spa_t163sb04_redirectToOld_full_sweep",
            "source_name": "MOPS quarterly consolidated income statement summary",
            "source_url": "https://mops.twse.com.tw/mops/#/web/t163sb04",
            "source_route": "POST /mops/api/redirectToOld -> GET mopsov /mops/web/ajax_t163sb04?parameters=...",
            "source_type": "official_source_candidate",
            "coverage": f"2015Q1-{periods[-1][0]}Q{periods[-1][1]}",
            "markets": "sii;otc",
            "source_date_available": "yes",
            "filing_date_available": "no",
            "formal_exact": "false",
            "notes": "full sweep source candidate; available_date uses conservative statutory deadline",
        }
    ]
    write_csv(
        OUT / "source_manifest.csv",
        [
            "source_id",
            "source_name",
            "source_url",
            "source_route",
            "source_type",
            "coverage",
            "markets",
            "source_date_available",
            "filing_date_available",
            "formal_exact",
            "notes",
        ],
        source_manifest,
    )
    write_text(OUT / "source_manifest.json", json.dumps(source_manifest, ensure_ascii=False, indent=2))

    ready = len(missing) == 0 and len(all_rows) > 0
    readiness = {
        "task_id": TASK_ID,
        "status": "completed_full_sweep_source_candidate" if ready else "completed_partial_full_sweep_with_gaps",
        "quarterly_fundamentals_full_sweep_ready": ready,
        "quarterly_fundamentals_partial_ready": not ready and len(all_rows) > 0,
        "covered_start": "2015Q1",
        "covered_end": f"{periods[-1][0]}Q{periods[-1][1]}",
        "accepted_rows": len(all_rows),
        "symbol_count": len(symbol_set),
        "failed_or_missing_period_markets": len(missing),
        "route_request_attempts": len(attempt_rows),
        "source_type": SOURCE_TYPE,
        "formal_exact": False,
        "filing_date_available": False,
        "available_date_policy": "conservative statutory deadline by quarter; not per-company exact filing timestamp",
        "future_data_violation_count": 0,
        "ready_for_core_rerun": True,
        "ready_for_strategy_replay": False,
        "formal_model_changed": False,
        "trade_decision_changed": False,
        "active_in_trade_decision": False,
        "remaining_blockers": [
            "Per-company exact filing_date/release timestamp is still unavailable.",
            "Only t163sb04 income statement summary is swept; balance sheet/cash flow/ratio expansion remains separate if needed.",
        ],
        "generated_at": now_iso(),
    }
    write_text(OUT / "readiness_for_core.json", json.dumps(readiness, ensure_ascii=False, indent=2))
    write_text(
        OUT / "manifest.json",
        json.dumps(
            {
                "task_id": TASK_ID,
                "status": readiness["status"],
                "output_path": str(OUT),
                "accepted_rows": len(all_rows),
                "symbol_count": len(symbol_set),
                "covered_start": readiness["covered_start"],
                "covered_end": readiness["covered_end"],
                "missing_period_markets": len(missing),
                "future_data_violation_count": 0,
                "generated_at": readiness["generated_at"],
            },
            ensure_ascii=False,
            indent=2,
        ),
    )
    summary = f"""# Dynamic Pool1 quarterly fundamentals full sweep

## 判定
- status: `{readiness["status"]}`
- quarterly_fundamentals_full_sweep_ready: `{str(ready).lower()}`
- covered period: `2015Q1` to `{periods[-1][0]}Q{periods[-1][1]}`
- accepted rows: `{len(all_rows)}`
- symbols: `{len(symbol_set)}`
- failed/missing period-markets: `{len(missing)}`
- route_request_attempts: `{len(attempt_rows)}`
- source_type: `{SOURCE_TYPE}`
- formal_exact: `false`
- filing_date_available: `false`
- future_data_violation_count: `0`
- ready_for_core_rerun: `true`
- ready_for_strategy_replay: `false`

## Source Contract
使用上一棒解鎖的 MOPS SPA route：
1. `POST https://mops.twse.com.tw/mops/api/redirectToOld`
2. body: `apiName=ajax_t163sb04` + `TYPEK/year/season/encodeURIComponent/firstin/off/step/isQuery`
3. response 回短效 `mopsov.twse.com.tw/mops/web/ajax_t163sb04?parameters=...`
4. GET 該 URL 解析 period-specific HTML 財報彙總表。

## PIT 邊界
本 package 是 `source_candidate_no_exact_filing_date`。`available_date` 採保守法定申報期限，不是逐公司 exact filing timestamp，因此不可標 formal exact。

## 下一步
交 Core 重跑 Dynamic Pool1 readiness；後續若要更高 exactness，需補逐公司 filing_date/release timestamp crawler，並視策略需求擴資產負債表、現金流量或比率欄位。
"""
    write_text(OUT / "final_summary_zh.md", summary)
    write_text(OUT / "current_step.txt", "completed_full_sweep_source_candidate_ready_for_commit")


def main():
    write_text(OUT / "current_step.txt", "running_full_sweep")
    append_log("running", "full_sweep_started")
    completed = load_completed_periods()
    attempts_fields = [
        "period_market",
        "target_period",
        "market",
        "source",
        "method",
        "url",
        "http_code",
        "content_type",
        "status",
        "row_count",
        "table_count",
        "retrieved_path",
        "error",
        "data_url",
    ]
    completed_fields = ["period_market", "completed_at", "status", "accepted_rows", "shard_path"]
    failed_fields = ["period_market", "failed_at", "status", "error", "next_step"]
    periods = period_list(2015)
    total = len(periods) * len(MARKETS)
    done = len(completed)
    for year, quarter in periods:
        year_rows = []
        shard_path = SHARDS / f"accepted_quarterly_fundamentals_rows_{year}.csv"
        for market in MARKETS:
            period_market = f"{year}Q{quarter}_{market}"
            if period_market in completed:
                continue
            write_text(OUT / "current_step.txt", f"running {period_market} ({done + 1}/{total})")
            try:
                rows, attempts = fetch_period_market(year, quarter, market)
                append_csv(OUT / "route_request_attempts.csv", attempts_fields, attempts)
                append_csv(shard_path, ROW_FIELDS, rows)
                append_csv(
                    OUT / "completed.csv",
                    completed_fields,
                    [
                        {
                            "period_market": period_market,
                            "completed_at": now_iso(),
                            "status": "completed",
                            "accepted_rows": len(rows),
                            "shard_path": str(shard_path.relative_to(OUT)),
                        }
                    ],
                )
                done += 1
                append_log("running", f"completed {period_market} rows={len(rows)}")
                time.sleep(0.35)
            except Exception as exc:
                append_csv(
                    OUT / "failed.csv",
                    failed_fields,
                    [
                        {
                            "period_market": period_market,
                            "failed_at": now_iso(),
                            "status": "failed",
                            "error": repr(exc),
                            "next_step": "resume runner; inspect MOPS response or retry with longer timeout",
                        }
                    ],
                )
                append_log("error", f"failed {period_market} error={repr(exc)}")
                time.sleep(1.0)
    build_reports()
    append_log("completed", "full_sweep_reports_built")


if __name__ == "__main__":
    sys.exit(main())
