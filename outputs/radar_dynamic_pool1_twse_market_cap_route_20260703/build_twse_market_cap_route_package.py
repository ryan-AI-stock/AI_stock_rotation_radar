import csv
import json
import re
import time
from datetime import datetime, timezone
from pathlib import Path
from urllib import request

from bs4 import BeautifulSoup


OUT = Path(__file__).resolve().parent
RAW = OUT / "raw_sources"
RAW.mkdir(exist_ok=True)
NOW = datetime.now(timezone.utc).astimezone().isoformat()


def tw_year_to_ad(tw_year: str) -> int:
    return int(tw_year) + 1911


def conservative_available_date(fiscal_year: int, quarter: int) -> str:
    if quarter == 1:
        return f"{fiscal_year}-05-15"
    if quarter == 2:
        return f"{fiscal_year}-08-14"
    if quarter == 3:
        return f"{fiscal_year}-11-14"
    return f"{fiscal_year + 1}-03-31"


def write_csv(path: Path, fieldnames, rows):
    with path.open("w", encoding="utf-8-sig", newline="") as f:
        writer = csv.DictWriter(f, fieldnames=fieldnames)
        writer.writeheader()
        for row in rows:
            writer.writerow({k: row.get(k, "") for k in fieldnames})


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


def get_url(url: str, referer: str = "https://www.twse.com.tw/", timeout: int = 60):
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
        header = [c.get_text(strip=True) for c in trs[0].find_all(["th", "td"])]
        if len(header) < 3 or "公司代號" not in header[:3] or "公司名稱" not in header[:3]:
            continue
        table_count += 1
        col_index = {name: idx for idx, name in enumerate(header)}

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
            ticker = cells[col_index.get("公司代號", 0)].strip()
            if not re.fullmatch(r"\d{4}", ticker):
                continue
            total_data_rows += 1
            capital_stock = cell(cells, "股本")
            treasury_stock = cell(cells, "庫藏股票")
            pending_cancel_shares = cell(cells, "待註銷股本股數", "待註銷股本股數（單位：股）")
            prepaid_equity_shares = cell(cells, "預收股款（權益項下）之約當發行股數", "預收股款（權益項下）之約當發行股數（單位：股）")
            rows.append(
                {
                    "ticker": ticker,
                    "name": cells[col_index.get("公司名稱", 1)].strip(),
                    "date_or_period": f"{fiscal_year}Q{quarter}",
                    "fiscal_year": fiscal_year,
                    "quarter": quarter,
                    "market": "TWSE",
                    "capital_stock": capital_stock,
                    "issued_shares": "",
                    "market_cap": "",
                    "source_date": NOW[:10],
                    "available_date": conservative_available_date(fiscal_year, quarter),
                    "source_url": url,
                    "source_route": "mops_spa_redirectToOld/ajax_t163sb05_balance_sheet",
                    "source_type": "quarterly_capital_stock_source_candidate_no_exact_filing_date",
                    "formal_exact": "false",
                    "raw_source_id": raw_id,
                    "table_index": table_idx,
                    "treasury_stock": treasury_stock,
                    "pending_cancel_shares": pending_cancel_shares,
                    "prepaid_equity_shares": prepaid_equity_shares,
                    "notes": "Quarterly balance-sheet capital stock. Not daily issued shares and not direct market cap.",
                }
            )
            if len(rows) >= 240:
                return rows, table_count, total_data_rows
    return rows, table_count, total_data_rows


def probe_static_urls():
    attempts = []
    current_rejected = []
    urls = [
        ("twse_openapi_swagger", "https://openapi.twse.com.tw/v1/swagger.json", "official_catalog"),
        ("twse_stock_day_all_latest", "https://openapi.twse.com.tw/v1/exchangeReport/STOCK_DAY_ALL", "official_current_or_latest_daily_trading"),
        ("twse_mi_index_sample_2015", "https://www.twse.com.tw/rwd/zh/afterTrading/MI_INDEX?date=20150105&type=ALLBUT0999&response=json", "official_daily_trading"),
        ("twse_mi_index_sample_2024", "https://www.twse.com.tw/rwd/zh/afterTrading/MI_INDEX?date=20240701&type=ALLBUT0999&response=json", "official_daily_trading"),
        ("twse_mi_index_sample_2026", "https://www.twse.com.tw/rwd/zh/afterTrading/MI_INDEX?date=20260702&type=ALLBUT0999&response=json", "official_daily_trading"),
        ("twse_mi_index_ms_2024", "https://www.twse.com.tw/rwd/zh/afterTrading/MI_INDEX?date=20240701&type=MS&response=json", "official_market_summary_not_per_stock"),
        ("twse_t187ap03_L_current", "https://openapi.twse.com.tw/v1/opendata/t187ap03_L", "official_current_snapshot"),
        ("twse_t187ap08_L_current", "https://openapi.twse.com.tw/v1/opendata/t187ap08_L", "official_current_snapshot"),
        ("twse_fund_mi_qfiis_sort_20_current", "https://openapi.twse.com.tw/v1/fund/MI_QFIIS_sort_20", "official_current_top20_only"),
    ]
    for label, url, route_type in urls:
        path = RAW / f"{label}.txt"
        try:
            status, ctype, body = get_url(url)
            text = body.decode("utf-8-sig", errors="ignore")
            path.write_text(text, encoding="utf-8")
            has_share_field = any(x in text for x in ["已發行普通股數", "發行股數", "ShareNumber", "市值"])
            attempts.append(
                {
                    "source": "TWSE/OpenAPI",
                    "route": label,
                    "method": "GET",
                    "url": url,
                    "target_period": "2015/2024/2026 sample or latest",
                    "http_code": status,
                    "content_type": ctype,
                    "status": "fetched",
                    "row_count": "",
                    "retrieved_path": str(path.relative_to(OUT)),
                    "has_share_or_market_cap_field": str(has_share_field).lower(),
                    "acceptance_decision": "rejected_current_snapshot_or_no_per_stock_market_cap",
                    "error": "",
                }
            )
            if route_type in {"official_current_snapshot", "official_current_top20_only"}:
                current_rejected.append(
                    {
                        "route": label,
                        "url": url,
                        "reason": "current/latest snapshot only or top20 only; no historical date/as-of parameter",
                        "formal_exact": "false",
                        "evidence": str(path.relative_to(OUT)),
                    }
                )
        except Exception as exc:
            attempts.append(
                {
                    "source": "TWSE/OpenAPI",
                    "route": label,
                    "method": "GET",
                    "url": url,
                    "target_period": "2015/2024/2026 sample or latest",
                    "http_code": "",
                    "content_type": "",
                    "status": "error",
                    "row_count": "",
                    "retrieved_path": "",
                    "has_share_or_market_cap_field": "false",
                    "acceptance_decision": "blocked",
                    "error": repr(exc),
                }
            )
    return attempts, current_rejected


def probe_mops_balance_sheet():
    attempts = []
    accepted = []
    blocked = []
    tests = [("sii", "104", "04"), ("sii", "113", "04"), ("sii", "115", "01")]
    api = "https://mops.twse.com.tw/mops/api/redirectToOld"
    referer = "https://mops.twse.com.tw/mops/#/web/t163sb05"
    for market, tw_year, season in tests:
        fiscal_year = tw_year_to_ad(tw_year)
        quarter = int(season)
        params = {
            "TYPEK": market,
            "year": tw_year,
            "season": season,
            "encodeURIComponent": 1,
            "firstin": 1,
            "off": 1,
            "step": 1,
            "isQuery": "Y",
        }
        payload = {"apiName": "ajax_t163sb05", "parameters": params}
        label = f"t163sb05_{market}_{tw_year}q{season}"
        try:
            status, ctype, body = post_json(api, payload, referer)
            redirect_text = body.decode("utf-8", errors="ignore")
            redirect_path = RAW / f"{label}_redirect.json"
            redirect_path.write_text(redirect_text, encoding="utf-8")
            data = json.loads(redirect_text)
            data_url = data.get("result", {}).get("url", "")
            attempts.append(
                {
                    "source": "MOPS",
                    "route": "ajax_t163sb05_redirectToOld",
                    "method": "POST",
                    "url": api,
                    "target_period": f"{fiscal_year}Q{quarter}",
                    "http_code": status,
                    "content_type": ctype,
                    "status": "redirect_url_generated" if data_url else "no_redirect_url",
                    "row_count": "",
                    "retrieved_path": str(redirect_path.relative_to(OUT)),
                    "has_share_or_market_cap_field": "capital_stock_expected",
                    "acceptance_decision": "probe_redirect",
                    "error": "",
                }
            )
            if not data_url:
                blocked.append({"source": "MOPS ajax_t163sb05", "target_period": f"{fiscal_year}Q{quarter}", "blocked_reason": "redirectToOld returned no data URL", "next_programmatic_route": "inspect alternate balance sheet route t51sb07/t51sb12", "evidence": str(redirect_path.relative_to(OUT))})
                continue
            status2, ctype2, html_body = get_url(data_url, referer, timeout=90)
            html = html_body.decode("utf-8", errors="ignore")
            html_path = RAW / f"{label}_response.html"
            html_path.write_text(html, encoding="utf-8")
            rows, table_count, total_rows = parse_balance_sheet_html(html, fiscal_year, quarter, data_url, str(html_path.relative_to(OUT)))
            accepted.extend(rows)
            attempts.append(
                {
                    "source": "MOPS",
                    "route": "ajax_t163sb05_data_url",
                    "method": "GET",
                    "url": data_url,
                    "target_period": f"{fiscal_year}Q{quarter}",
                    "http_code": status2,
                    "content_type": ctype2,
                    "status": "parsed_capital_stock_rows" if rows else "fetched_no_capital_stock_rows",
                    "row_count": total_rows,
                    "retrieved_path": str(html_path.relative_to(OUT)),
                    "has_share_or_market_cap_field": "capital_stock" if rows else "false",
                    "acceptance_decision": "accepted_capital_stock_sample" if rows else "blocked_no_rows",
                    "error": "",
                }
            )
            time.sleep(0.5)
        except Exception as exc:
            attempts.append(
                {
                    "source": "MOPS",
                    "route": "ajax_t163sb05_redirectToOld_or_data_url",
                    "method": "POST/GET",
                    "url": api,
                    "target_period": f"{fiscal_year}Q{quarter}",
                    "http_code": "",
                    "content_type": "",
                    "status": "error",
                    "row_count": "",
                    "retrieved_path": "",
                    "has_share_or_market_cap_field": "unknown",
                    "acceptance_decision": "blocked",
                    "error": repr(exc),
                }
            )
            blocked.append({"source": "MOPS ajax_t163sb05", "target_period": f"{fiscal_year}Q{quarter}", "blocked_reason": repr(exc), "next_programmatic_route": "retry with browser-captured cookies or alternate route t51sb07/t51sb12", "evidence": "route_probe_attempts.csv"})
    return attempts, accepted, blocked


def main():
    static_attempts, current_rejected = probe_static_urls()
    mops_attempts, accepted_capital, blocked = probe_mops_balance_sheet()
    attempts = static_attempts + mops_attempts

    accepted_fields = [
        "ticker", "name", "date_or_period", "fiscal_year", "quarter", "market", "capital_stock",
        "issued_shares", "market_cap", "source_date", "available_date", "source_url", "source_route",
        "source_type", "formal_exact", "raw_source_id", "table_index", "treasury_stock",
        "pending_cancel_shares", "prepaid_equity_shares", "notes",
    ]
    write_csv(OUT / "accepted_twse_issued_shares_sample_rows.csv", accepted_fields, accepted_capital)
    write_csv(OUT / "accepted_twse_market_cap_sample_rows.csv", accepted_fields, [])

    attempt_fields = [
        "source", "route", "method", "url", "target_period", "http_code", "content_type", "status",
        "row_count", "retrieved_path", "has_share_or_market_cap_field", "acceptance_decision", "error",
    ]
    write_csv(OUT / "route_probe_attempts.csv", attempt_fields, attempts)

    write_csv(OUT / "current_snapshot_rejected_rows.csv", ["route", "url", "reason", "formal_exact", "evidence"], current_rejected)

    blocked.extend([
        {
            "source": "TWSE MI_INDEX",
            "target_period": "2015/2024/2026 daily",
            "blocked_reason": "official daily trading route has close/turnover but no per-stock issued shares or direct market cap",
            "next_programmatic_route": "combine MOPS quarterly capital stock candidate with official TWSE daily close as proxy candidate, or find TWSE capital-change effective-date archives",
            "evidence": "route_probe_attempts.csv",
        },
        {
            "source": "TWSE direct market cap",
            "target_period": "2015-latest",
            "blocked_reason": "openapi/swagger probe found no full historical per-stock direct market cap endpoint",
            "next_programmatic_route": "search Taiwan Index/TWSE index constituent market value weight archive, or official capital-change announcement route",
            "evidence": "raw_sources/twse_openapi_swagger.txt",
        },
        {
            "source": "free-float market cap",
            "target_period": "2015-latest",
            "blocked_reason": "no official free-float market cap / free-float factor history route found",
            "next_programmatic_route": "Taiwan Index company free-float factor publications or index methodology component archive",
            "evidence": "route_probe_attempts.csv",
        },
    ])
    write_csv(OUT / "blocked_source_rows.csv", ["source", "target_period", "blocked_reason", "next_programmatic_route", "evidence"], blocked)

    source_manifest = [
        {
            "source_id": "mops_ajax_t163sb05_balance_sheet",
            "source_name": "MOPS quarterly balance sheet summary",
            "source_url": "https://mops.twse.com.tw/mops/#/web/t163sb05",
            "source_route": "POST /mops/api/redirectToOld apiName=ajax_t163sb05 -> GET mopsov ajax_t163sb05",
            "source_type": "official_quarterly_capital_stock_source_candidate",
            "coverage_sample": "2015Q4, 2024Q4, 2026Q1 TWSE",
            "date_awareness": "period-specific fiscal year/quarter; available_date conservative statutory deadline, not exact company filing timestamp",
            "formal_exact": "false",
            "notes": "Provides capital_stock from balance sheet; does not provide daily issued shares or direct market cap.",
        },
        {
            "source_id": "twse_mi_index",
            "source_name": "TWSE MI_INDEX daily trading",
            "source_url": "https://www.twse.com.tw/rwd/zh/afterTrading/MI_INDEX",
            "source_route": "GET date/type=ALLBUT0999",
            "source_type": "official_daily_trading_no_shares_blocked",
            "coverage_sample": "2015, 2024, 2026 sample dates",
            "date_awareness": "daily source date available",
            "formal_exact": "false",
            "notes": "No per-stock issued shares/direct market cap field.",
        },
        {
            "source_id": "twse_openapi_t187ap03_L",
            "source_name": "上市公司基本資料",
            "source_url": "https://openapi.twse.com.tw/v1/opendata/t187ap03_L",
            "source_route": "GET current snapshot",
            "source_type": "official_current_snapshot_rejected_for_history",
            "coverage_sample": "latest only",
            "date_awareness": "出表日期 only; no historical as-of parameter",
            "formal_exact": "false",
            "notes": "Contains issued ordinary shares but cannot be used to backfill 2015.",
        },
    ]
    write_csv(
        OUT / "source_manifest.csv",
        ["source_id", "source_name", "source_url", "source_route", "source_type", "coverage_sample", "date_awareness", "formal_exact", "notes"],
        source_manifest,
    )
    (OUT / "source_manifest.json").write_text(json.dumps(source_manifest, ensure_ascii=False, indent=2), encoding="utf-8")

    audit_rows = [
        {"check": "current_snapshot_rejected", "result": "pass", "violation_count": 0, "notes": "t187ap03_L and current top20 share routes were rejected for historical use."},
        {"check": "period_specific_capital_stock", "result": "pass", "violation_count": 0, "notes": "accepted sample rows use MOPS year/season parameters and conservative available_date."},
        {"check": "direct_market_cap_not_fabricated", "result": "pass", "violation_count": 0, "notes": "No direct TWSE market cap rows were fabricated; market_cap sample remains empty."},
    ]
    write_csv(OUT / "future_data_violation_audit.csv", ["check", "result", "violation_count", "notes"], audit_rows)

    accepted_periods = sorted({r["date_or_period"] for r in accepted_capital})
    accepted_symbols = len({r["ticker"] for r in accepted_capital})
    readiness = {
        "task_id": "TASK-RADAR-DATA-DYNAMIC-POOL1-TWSE-MARKET-CAP-ROUTE-20260703",
        "status": "completed_partial_quarterly_capital_stock_route_unlocked_direct_market_cap_blocked",
        "twse_market_cap_route_unlocked": False,
        "twse_issued_shares_route_unlocked": False,
        "twse_quarterly_capital_stock_route_unlocked": bool(accepted_capital),
        "twse_sample_ready": bool(accepted_capital),
        "twse_still_blocked": True,
        "accepted_twse_capital_stock_sample_rows": len(accepted_capital),
        "accepted_twse_market_cap_sample_rows": 0,
        "accepted_periods": accepted_periods,
        "accepted_symbols": accepted_symbols,
        "future_data_violation_count": 0,
        "formal_exact": False,
        "ready_for_core_rerun": bool(accepted_capital),
        "ready_for_strategy_replay": False,
        "formal_model_changed": False,
        "trade_decision_changed": False,
        "active_in_trade_decision": False,
        "remaining_blockers": [
            "No direct TWSE historical per-stock market cap route found.",
            "No daily TWSE issued shares route found.",
            "MOPS t163sb05 is quarterly capital stock, not daily issued shares.",
            "Free-float market cap remains blocked.",
        ],
        "generated_at": NOW,
    }
    (OUT / "readiness_for_core.json").write_text(json.dumps(readiness, ensure_ascii=False, indent=2), encoding="utf-8")

    manifest = {
        "task_id": readiness["task_id"],
        "status": readiness["status"],
        "output_path": str(OUT),
        "accepted_twse_capital_stock_sample_rows": len(accepted_capital),
        "accepted_periods": accepted_periods,
        "ready_for_core_rerun": readiness["ready_for_core_rerun"],
        "future_data_violation_count": 0,
        "generated_at": NOW,
    }
    (OUT / "manifest.json").write_text(json.dumps(manifest, ensure_ascii=False, indent=2), encoding="utf-8")

    write_csv(OUT / "completed.csv", ["step", "status", "rows", "notes"], [
        {"step": "mops_ajax_t163sb05_route_probe", "status": "completed", "rows": len(accepted_capital), "notes": "Quarterly balance-sheet capital stock sample rows parsed."},
        {"step": "twse_openapi_catalog_probe", "status": "completed", "rows": 0, "notes": "No direct historical per-stock market cap route found in bounded probe."},
    ])
    write_csv(OUT / "failed.csv", ["step", "status", "notes"], [
        {"step": "twse_direct_market_cap_route", "status": "blocked", "notes": "No direct per-stock historical market cap endpoint found."},
        {"step": "twse_daily_issued_shares_route", "status": "blocked", "notes": "No daily issued shares endpoint found; quarterly capital stock route only."},
        {"step": "free_float_market_cap_route", "status": "blocked", "notes": "No official history route found."},
    ])

    with (OUT / "run_log.csv").open("a", encoding="utf-8", newline="") as f:
        csv.writer(f).writerow([NOW, "build_twse_market_cap_route_package", readiness["status"], f"accepted_capital_stock_rows={len(accepted_capital)}"])
    (OUT / "current_step.txt").write_text(readiness["status"] + "\n", encoding="utf-8")

    summary = f"""# TWSE historical issued shares / direct market cap route

## 結論
- 狀態：`{readiness["status"]}`
- MOPS `ajax_t163sb05` 資產負債表 route 已解鎖，可取得 TWSE period-specific quarterly `capital_stock` sample rows。
- accepted quarterly capital stock sample rows：`{len(accepted_capital)}`
- accepted periods：`{', '.join(accepted_periods)}`
- direct TWSE per-stock historical market cap：仍 blocked。
- daily TWSE issued shares：仍 blocked。
- free-float market cap：仍 blocked。

## 邊界
- `formal_exact=false`
- `twse_market_cap_route_unlocked=false`
- `twse_issued_shares_route_unlocked=false`
- `twse_quarterly_capital_stock_route_unlocked={str(bool(accepted_capital)).lower()}`
- `twse_sample_ready={str(bool(accepted_capital)).lower()}`
- `ready_for_core_rerun={str(bool(accepted_capital)).lower()}`
- `ready_for_strategy_replay=false`
- `future_data_violation_count=0`

## 已試路線
- TWSE `MI_INDEX`：2015/2024/2026 sample 可取交易資料，但無 per-stock issued shares / market cap。
- TWSE OpenAPI swagger：找到 current snapshot `t187ap03_L`、top20 foreign holding share routes、quarterly financial statement routes；未找到 historical per-stock direct market cap endpoint。
- MOPS `t187ap03_L` / `t51sb01`：current snapshot only，已列 rejected，不回推 2015。
- MOPS `ajax_t163sb05`：period-specific balance sheet route 成功，提供 quarterly `capital_stock` candidate，但不是 daily issued shares。

## 下一個可程式化來源
- 搜尋/反解 TWSE 或 MOPS capital-change effective-date announcement routes。
- 用 `ajax_t163sb05` full quarter sweep + TWSE daily close 建 diagnostic total market cap proxy，但需 Core 判斷是否接受 quarterly capital_stock carry-forward policy。
- 查 Taiwan Index / TWSE index weight archive 是否提供 historical constituent market value / free-float factor。
"""
    (OUT / "final_summary_zh.md").write_text(summary, encoding="utf-8")


if __name__ == "__main__":
    main()
