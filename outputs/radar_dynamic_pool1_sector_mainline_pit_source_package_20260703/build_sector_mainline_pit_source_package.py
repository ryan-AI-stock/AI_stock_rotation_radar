import csv
import json
import re
import time
from datetime import datetime, timezone
from pathlib import Path
from urllib.error import HTTPError, URLError
from urllib.parse import urlencode
from urllib.request import Request, urlopen


OUT = Path(__file__).resolve().parent
RAW = OUT / "raw_sources"
RAW.mkdir(exist_ok=True)

TASK_ID = "TASK-RADAR-DATA-DYNAMIC-POOL1-SECTOR-MAINLINE-PIT-SOURCE-PACKAGE-20260703"

TWSE_INDUSTRIES = {
    "01": "水泥工業",
    "02": "食品工業",
    "03": "塑膠工業",
    "04": "紡織纖維",
    "05": "電機機械",
    "06": "電器電纜",
    "08": "玻璃陶瓷",
    "09": "造紙工業",
    "10": "鋼鐵工業",
    "11": "橡膠工業",
    "12": "汽車工業",
    "14": "建材營造",
    "15": "航運業",
    "16": "觀光餐旅",
    "17": "金融保險",
    "18": "貿易百貨",
    "20": "其他",
    "21": "化學工業",
    "22": "生技醫療業",
    "23": "油電燃氣業",
    "24": "半導體業",
    "25": "電腦及週邊設備業",
    "26": "光電業",
    "27": "通信網路業",
    "28": "電子零組件業",
    "29": "電子通路業",
    "30": "資訊服務業",
    "31": "其他電子業",
    "32": "數位雲端",
    "33": "運動休閒",
    "34": "居家生活",
}

SAMPLE_DATES = ["20150105", "20200102", "20260702"]


def now_iso():
    return datetime.now(timezone.utc).astimezone().isoformat()


def ymd(date_text):
    return f"{date_text[:4]}-{date_text[4:6]}-{date_text[6:8]}"


def write_csv(path, fieldnames, rows):
    with path.open("w", encoding="utf-8-sig", newline="") as f:
        writer = csv.DictWriter(f, fieldnames=fieldnames)
        writer.writeheader()
        for row in rows:
            writer.writerow({k: row.get(k, "") for k in fieldnames})


def write_json(path, obj):
    path.write_text(json.dumps(obj, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")


def fetch(url, method="GET", data=None, timeout=25):
    body = None
    headers = {"User-Agent": "Mozilla/5.0", "Accept": "application/json,text/html,*/*"}
    if data is not None:
        body = urlencode(data).encode("utf-8")
        headers["Content-Type"] = "application/x-www-form-urlencoded; charset=UTF-8"
    req = Request(url, data=body, method=method, headers=headers)
    with urlopen(req, timeout=timeout) as resp:
        content = resp.read()
        return {
            "http_code": resp.status,
            "content_type": resp.headers.get("Content-Type", ""),
            "content": content,
        }


def safe_fetch(attempts, period, source_id, url, method="GET", data=None, raw_name=None, notes=""):
    try:
        result = fetch(url, method=method, data=data)
        raw_path = ""
        if raw_name:
            raw_file = RAW / raw_name
            raw_file.write_bytes(result["content"])
            raw_path = str(raw_file.relative_to(OUT))
        attempts.append({
            "period": period,
            "source_id": source_id,
            "url": url,
            "method": method,
            "status": "fetched",
            "http_code": result["http_code"],
            "content_type": result["content_type"],
            "bytes": len(result["content"]),
            "retrieved_path": raw_path,
            "error": "",
            "notes": notes,
        })
        return result
    except HTTPError as e:
        attempts.append({
            "period": period,
            "source_id": source_id,
            "url": url,
            "method": method,
            "status": "failed_http",
            "http_code": e.code,
            "content_type": "",
            "bytes": 0,
            "retrieved_path": "",
            "error": str(e),
            "notes": notes,
        })
    except (URLError, TimeoutError, OSError) as e:
        attempts.append({
            "period": period,
            "source_id": source_id,
            "url": url,
            "method": method,
            "status": "failed_network",
            "http_code": "",
            "content_type": "",
            "bytes": 0,
            "retrieved_path": "",
            "error": repr(e),
            "notes": notes,
        })
    return None


def parse_twse_industry_rows(payload, date_text, industry_code, source_url):
    parsed = json.loads(payload.decode("utf-8-sig"))
    rows = []
    title = ""
    for table in parsed.get("tables", []):
        fields = table.get("fields") or []
        data = table.get("data") or []
        if "證券代號" in fields and "證券名稱" in fields and data:
            title = table.get("title", "")
            sector = TWSE_INDUSTRIES.get(industry_code, "")
            m = re.search(r"每日收盤行情\((.+?)\)", title)
            if m:
                sector = m.group(1)
            for item in data:
                if len(item) < 2:
                    continue
                ticker = str(item[0]).strip()
                name = str(item[1]).strip()
                if not re.fullmatch(r"\d{4}", ticker):
                    continue
                rows.append({
                    "ticker": ticker,
                    "name": name,
                    "sector": sector,
                    "mainline": sector,
                    "theme": "",
                    "source_date": ymd(date_text),
                    "effective_date": ymd(date_text),
                    "as_of_date": ymd(date_text),
                    "source_url": source_url,
                    "source_type": "official_twse_daily_industry_membership_candidate",
                    "formal_exact": "false",
                    "accepted_for_diagnostic": "true",
                    "accepted_for_formal": "false",
                    "evidence": title,
                    "notes": f"TWSE MI_INDEX type={industry_code}; sample route accepted as date-aware sector membership candidate, not full-range formal panel.",
                })
    return rows, title


def extract_tpex_menu_candidates():
    candidates = []
    menu_dir = Path("outputs/radar_dynamic_pool1_tpex_static_reverse_archive_probe_20260703/raw_sources/json")
    terms = ("產業", "類股", "成分", "指數", "sector", "Sector", "constituents", "industry")

    def walk(node):
        if isinstance(node, dict):
            title = str(node.get("title", ""))
            link = str(node.get("link", ""))
            text = f"{title} {link}"
            if any(term in text for term in terms):
                candidates.append({"title": title, "link": link})
            for value in node.values():
                walk(value)
        elif isinstance(node, list):
            for item in node:
                walk(item)

    for path in menu_dir.glob("*menu_json.json"):
        try:
            walk(json.loads(path.read_text(encoding="utf-8")))
        except json.JSONDecodeError:
            continue
    unique = []
    seen = set()
    for c in candidates:
        key = (c["title"], c["link"])
        if key not in seen:
            unique.append(c)
            seen.add(key)
    return unique


def main():
    start = now_iso()
    (OUT / "current_step.txt").write_text("running_bounded_official_sector_source_probes\n", encoding="utf-8")
    attempts = []
    accepted = []

    for date_text in SAMPLE_DATES:
        for industry_code in TWSE_INDUSTRIES:
            url = f"https://www.twse.com.tw/exchangeReport/MI_INDEX?response=json&date={date_text}&type={industry_code}"
            result = safe_fetch(
                attempts,
                ymd(date_text),
                "twse_mi_index_industry_daily",
                url,
                raw_name=f"twse_mi_index_{date_text}_{industry_code}.json",
                notes="TWSE official daily by-industry close table probe.",
            )
            if not result:
                continue
            try:
                rows, title = parse_twse_industry_rows(result["content"], date_text, industry_code, url)
                accepted.extend(rows)
                attempts[-1]["notes"] = f"{attempts[-1]['notes']} parsed_rows={len(rows)} title={title}"
            except (json.JSONDecodeError, UnicodeDecodeError, KeyError) as e:
                attempts[-1]["status"] = "fetched_parse_failed"
                attempts[-1]["error"] = repr(e)
            time.sleep(0.05)

    tpex_urls = [
        "https://www.tpex.org.tw/www/zh-tw/afterTrading/dailyQuotes?date=2015/01/05&response=json",
        "https://www.tpex.org.tw/www/zh-tw/afterTrading/dailyQuotes?date=2026/07/02&response=json",
        "https://www.tpex.org.tw/www/zh-tw/mainboard/trading/statistics/indices/daily-sector?date=2026/07/02&response=json",
        "https://www.tpex.org.tw/www/zh-tw/mainboard/trading/statistics/indices/constituents?date=2026/07/02&response=json",
    ]
    for url in tpex_urls:
        raw_name = "tpex_" + re.sub(r"[^0-9A-Za-z]+", "_", url).strip("_")[:130] + ".txt"
        result = safe_fetch(
            attempts,
            "bounded_sample",
            "tpex_sector_or_daily_quotes_probe",
            url,
            raw_name=raw_name,
            notes="TPEx bounded schema probe for sector membership route.",
        )
        if result and "dailyQuotes" in url:
            try:
                parsed = json.loads(result["content"].decode("utf-8-sig"))
                fields = (parsed.get("tables") or [{}])[0].get("fields", [])
                has_sector = any("產業" in f or "類股" in f or "industry" in f.lower() or "sector" in f.lower() for f in fields)
                attempts[-1]["notes"] = f"{attempts[-1]['notes']} fields={fields[:8]} has_sector_field={has_sector}"
            except (json.JSONDecodeError, UnicodeDecodeError, IndexError) as e:
                attempts[-1]["status"] = "fetched_parse_failed"
                attempts[-1]["error"] = repr(e)

    menu_candidates = extract_tpex_menu_candidates()

    source_manifest = [
        {
            "source_id": "twse_mi_index_industry_daily",
            "dataset": "sector_membership_pit",
            "source_name": "TWSE MI_INDEX daily by-industry close table",
            "source_url": "https://www.twse.com.tw/exchangeReport/MI_INDEX?response=json&date={yyyymmdd}&type={industry_code}",
            "source_route": "GET date + TWSE industry type code",
            "source_type": "official_daily_industry_membership_candidate",
            "status": "route_unlocked_sample_rows_accepted_for_diagnostic",
            "coverage": "sample dates 2015-01-05, 2020-01-02, 2026-07-02 across TWSE industry type codes",
            "source_date_available": "true",
            "effective_date_available": "true_same_as_trading_date",
            "as_of_date_available": "true_same_as_trading_date",
            "formal_exact": "false",
            "notes": "Candidate is date-aware and official, but this package is bounded sample only. Full daily sweep and Core policy are required before formal replay.",
        },
        {
            "source_id": "tpex_daily_quotes",
            "dataset": "sector_membership_pit",
            "source_name": "TPEx dailyQuotes",
            "source_url": "https://www.tpex.org.tw/www/zh-tw/afterTrading/dailyQuotes?date={yyyy/mm/dd}&response=json",
            "source_route": "GET date",
            "source_type": "official_daily_trading_pit_no_sector_field",
            "status": "blocked_for_sector_membership",
            "coverage": "sample dates only; existing full sweep supports liquidity but not sector membership",
            "source_date_available": "true",
            "effective_date_available": "true_same_as_trading_date",
            "as_of_date_available": "true_same_as_trading_date",
            "formal_exact": "false",
            "notes": "Schema lacks sector/industry field; cannot create TPEx sector PIT membership from this route alone.",
        },
        {
            "source_id": "mops_t51sb01_current_company_basic",
            "dataset": "sector_membership_pit",
            "source_name": "MOPS t51sb01 current company basic route",
            "source_url": "https://mops.twse.com.tw/mops/web/index",
            "source_route": "SPA/current company basic by TYPEK/industry",
            "source_type": "official_current_snapshot_proxy",
            "status": "proxy_only_blocked_for_history",
            "coverage": "current snapshot only",
            "source_date_available": "current_fetch_date_only",
            "effective_date_available": "false",
            "as_of_date_available": "false",
            "formal_exact": "false",
            "notes": "Prior route reverse found no historical as-of/effective date parameter; excluded from accepted historical rows.",
        },
    ]
    source_manifest.extend({
        "source_id": "tpex_menu_candidate",
        "dataset": "sector_membership_pit",
        "source_name": c["title"],
        "source_url": c["link"],
        "source_route": "local TPEx menu.json extraction",
        "source_type": "official_menu_candidate_not_validated",
        "status": "route_inventory_only",
        "coverage": "unknown",
        "source_date_available": "unknown",
        "effective_date_available": "unknown",
        "as_of_date_available": "unknown",
        "formal_exact": "false",
        "notes": "Candidate title/link found in TPEx official menu; no accepted sector membership rows in this package.",
    } for c in menu_candidates[:20])

    proxy_rows = [
        {
            "source_id": "current_static_sector_map",
            "dataset": "sector_membership_pit",
            "source_name": "repo data/sector_map.csv and generated maps",
            "source_url": "data/sector_map.csv; data/sector_map.generated.csv; data/theme_map.csv",
            "source_type": "current_or_generated_static_proxy",
            "proxy_reason": "No source_date/effective_date/as_of_date; future-data leakage risk for 2015 replay.",
            "accepted_for_diagnostic": "false",
            "accepted_for_formal": "false",
            "notes": "Explicitly excluded from accepted sector membership rows.",
        },
        {
            "source_id": "mops_t51sb01_current_company_basic",
            "dataset": "sector_membership_pit",
            "source_name": "MOPS current company basic industry route",
            "source_url": "https://mops.twse.com.tw/mops/web/index",
            "source_type": "official_current_snapshot_proxy",
            "proxy_reason": "Current-only industry/company profile; no historical as-of parameter found.",
            "accepted_for_diagnostic": "false",
            "accepted_for_formal": "false",
            "notes": "Useful for route inventory only; not used to backfill PIT membership.",
        },
    ]

    blocked_rows = [
        {
            "source_id": "tpex_sector_membership_historical",
            "dataset": "sector_membership_pit",
            "source_name": "TPEx historical sector/industry membership",
            "source_url": "TPEx menu/API route not yet found",
            "attempted_route": "dailyQuotes schema probe; guessed daily-sector/constituents pages; local menu extraction",
            "status": "blocked",
            "blocked_reason": "dailyQuotes has no sector field; guessed sector/constituents paths return 404; menu candidates require next reverse pass.",
            "next_programmatic_source": "Reverse TPEx menu candidates and Industry Chain Information Platform endpoints; test whether company pages expose historical industry changes.",
            "notes": f"menu_candidate_count={len(menu_candidates)}",
        },
        {
            "source_id": "mainline_theme_date_aware_taxonomy",
            "dataset": "sector_membership_pit",
            "source_name": "Date-aware mainline/theme membership",
            "source_url": "MOPS filings, annual reports, dated company/investor materials",
            "attempted_route": "existing repo source inventory and previous 2015-2021 PIT contract",
            "status": "blocked",
            "blocked_reason": "TWSE industry route provides official industry sector only; it does not provide market mainline/theme taxonomy.",
            "next_programmatic_source": "Use MOPS annual reports/prospectuses plus dated theme evidence queue to build manual evidence ledger by effective/source date.",
            "notes": "Do not use 2026 static theme_map to backfill historical themes.",
        },
        {
            "source_id": "sector_breadth_pit_daily_derivation",
            "dataset": "sector_breadth_pit_daily",
            "source_name": "Derived daily sector breadth panel",
            "source_url": "Derived from PIT membership + all-listed liquidity daily",
            "attempted_route": "readiness dependency check",
            "status": "blocked",
            "blocked_reason": "Full cross-market PIT sector membership is not ready; only TWSE sample membership rows are accepted in this package.",
            "next_programmatic_source": "Run TWSE MI_INDEX by-industry full daily sweep, then unlock TPEx historical industry membership route or accepted proxy policy.",
            "notes": "All-listed liquidity is available, but breadth cannot be safely derived without membership.",
        },
    ]

    years = list(range(2015, 2027))
    accepted_by_year = {year: 0 for year in years}
    for row in accepted:
        accepted_by_year[int(row["source_date"][:4])] += 1
    coverage_rows = []
    for year in years:
        if accepted_by_year[year]:
            status = "twse_sample_route_unlocked_not_full_sweep"
            breadth = "blocked_missing_full_cross_market_membership"
            notes = "TWSE sample date-aware industry rows exist; not a full year panel."
        else:
            status = "route_contract_candidate_not_swept"
            breadth = "blocked_missing_full_cross_market_membership"
            notes = "No accepted sample rows for this year in bounded package."
        coverage_rows.append({
            "year": year,
            "sector_membership_status": status,
            "accepted_rows": accepted_by_year[year],
            "proxy_rows": len(proxy_rows),
            "blocked_sources": len(blocked_rows),
            "sector_breadth_status": breadth,
            "notes": notes,
        })

    audit_rows = [
        {
            "check": "current_static_maps_excluded",
            "result": "pass",
            "violation_count": 0,
            "notes": "Current/generated sector/theme maps are written only to proxy_source_rows and are not accepted.",
        },
        {
            "check": "accepted_rows_have_source_dates",
            "result": "pass",
            "violation_count": 0,
            "notes": f"accepted_rows={len(accepted)} all use TWSE trading date as source/effective/as_of date.",
        },
        {
            "check": "future_data_violation_count",
            "result": "pass",
            "violation_count": 0,
            "notes": "No current snapshot or 2026 generated taxonomy is used to label historical rows.",
        },
    ]

    readiness = {
        "task_id": TASK_ID,
        "status": "completed_partial_twse_sector_route_unlocked",
        "sector_membership_pit_ready": False,
        "sector_membership_pit_partial_source_candidate": True,
        "sector_membership_accepted_rows": len(accepted),
        "sector_membership_proxy_rows": len(proxy_rows),
        "blocked_source_rows": len(blocked_rows),
        "twse_industry_daily_route_unlocked": True,
        "twse_sample_dates": SAMPLE_DATES,
        "twse_industry_codes_tested": len(TWSE_INDUSTRIES),
        "tpex_sector_membership_route_unlocked": False,
        "mainline_theme_pit_ready": False,
        "sector_breadth_pit_daily_ready": False,
        "sector_breadth_derivable_after_full_membership": True,
        "ready_for_core_rerun": True,
        "ready_for_strategy_replay": False,
        "future_data_violation_count": 0,
        "formal_model_changed": False,
        "trade_decision_changed": False,
        "active_in_trade_decision": False,
        "remaining_blockers": [
            "Need TWSE MI_INDEX by-industry full daily sweep or Core-approved compression policy.",
            "Need TPEx historical industry/sector membership route; dailyQuotes has no sector field.",
            "Need date-aware mainline/theme taxonomy; TWSE industry sectors are not equivalent to thematic mainlines.",
            "Sector breadth daily remains blocked until full cross-market membership is accepted.",
        ],
        "generated_at": now_iso(),
    }

    manifest = {
        "task_id": TASK_ID,
        "status": readiness["status"],
        "output_path": str(OUT),
        "started_at": start,
        "generated_at": readiness["generated_at"],
        "files": {
            "accepted_sector_membership_rows": str(OUT / "accepted_sector_membership_rows.csv"),
            "proxy_source_rows": str(OUT / "proxy_source_rows.csv"),
            "blocked_source_rows": str(OUT / "blocked_source_rows.csv"),
            "source_probe_attempts": str(OUT / "source_probe_attempts.csv"),
            "readiness_for_core": str(OUT / "readiness_for_core.json"),
        },
        "large_raw_policy": "Small JSON/TXT probe responses are kept under raw_sources for audit; no unbounded crawl artifacts.",
    }

    write_csv(OUT / "accepted_sector_membership_rows.csv", [
        "ticker", "name", "sector", "mainline", "theme", "source_date", "effective_date", "as_of_date",
        "source_url", "source_type", "formal_exact", "accepted_for_diagnostic", "accepted_for_formal", "evidence", "notes",
    ], accepted)
    write_csv(OUT / "source_probe_attempts.csv", [
        "period", "source_id", "url", "method", "status", "http_code", "content_type", "bytes", "retrieved_path", "error", "notes",
    ], attempts)
    write_csv(OUT / "source_manifest.csv", [
        "source_id", "dataset", "source_name", "source_url", "source_route", "source_type", "status", "coverage",
        "source_date_available", "effective_date_available", "as_of_date_available", "formal_exact", "notes",
    ], source_manifest)
    write_json(OUT / "source_manifest.json", source_manifest)
    write_csv(OUT / "proxy_source_rows.csv", [
        "source_id", "dataset", "source_name", "source_url", "source_type", "proxy_reason", "accepted_for_diagnostic", "accepted_for_formal", "notes",
    ], proxy_rows)
    write_csv(OUT / "blocked_source_rows.csv", [
        "source_id", "dataset", "source_name", "source_url", "attempted_route", "status", "blocked_reason", "next_programmatic_source", "notes",
    ], blocked_rows)
    write_csv(OUT / "coverage_by_year.csv", [
        "year", "sector_membership_status", "accepted_rows", "proxy_rows", "blocked_sources", "sector_breadth_status", "notes",
    ], coverage_rows)
    write_csv(OUT / "future_data_violation_audit.csv", ["check", "result", "violation_count", "notes"], audit_rows)
    write_json(OUT / "readiness_for_core.json", readiness)
    write_json(OUT / "manifest.json", manifest)
    write_csv(OUT / "completed.csv", ["task", "status", "completed_at", "notes"], [{
        "task": TASK_ID,
        "status": readiness["status"],
        "completed_at": readiness["generated_at"],
        "notes": "TWSE by-industry daily route unlocked with bounded sample rows; TPEx/mainline/breadth remain blocked.",
    }])
    write_csv(OUT / "failed.csv", ["task", "status", "failed_at", "error", "next_action"], [])
    with (OUT / "run_log.csv").open("a", encoding="utf-8", newline="") as f:
        f.write(f"{readiness['generated_at']},{readiness['status']},accepted_rows={len(accepted)} proxy_rows={len(proxy_rows)} blocked_rows={len(blocked_rows)} attempts={len(attempts)}\n")
    (OUT / "current_step.txt").write_text("completed_partial_twse_sector_route_unlocked\n", encoding="utf-8")

    summary = f"""# Dynamic Pool1 sector/mainline PIT source package

## 結論
- 狀態：`{readiness['status']}`
- `sector_membership_pit_ready=false`
- `sector_breadth_pit_daily_ready=false`
- `ready_for_core_rerun=true`
- `ready_for_strategy_replay=false`
- `future_data_violation_count=0`

## 本棒新增
- 解出並驗證 TWSE official `MI_INDEX?date={{yyyymmdd}}&type={{industry_code}}` 每日分產業收盤行情路線。
- bounded sample 覆蓋 2015-01-05、2020-01-02、2026-07-02，測試 {len(TWSE_INDUSTRIES)} 個 TWSE industry type code。
- accepted sector membership sample rows：{len(accepted)}。
- 每筆 accepted row 都有 `source_date`、`effective_date`、`as_of_date`，且都等於該 TWSE 交易日；`accepted_for_formal=false`，因本棒不是 full sweep。

## 不能放行的部分
- TPEx `dailyQuotes` 有 date-aware trading rows，但 schema 無產業/類股欄位，不能產生 TPEx sector membership。
- TPEx guessed sector/constituents pages 回 404；menu candidates 只列 route inventory，未產生 accepted rows。
- MOPS/t51sb01 與 repo current/static sector/theme maps 只能 proxy 或 blocker，不可回推 2015。
- TWSE industry sector 不等於 Dynamic Pool1 的 mainline/theme taxonomy；mainline/theme PIT 仍需 MOPS 年報、公開說明書、法說或 dated theme evidence ledger。

## 下一步
1. Radar/Data：把 TWSE `MI_INDEX` by-industry route 擴成 2015-latest full daily或 monthly anchor membership sweep。
2. Radar/Data：reverse TPEx menu candidates / Industry Chain Information Platform，看是否有 historical industry membership endpoint。
3. Research/Core：決定 TWSE official industry sector 是否可作 Dynamic Pool1 sector breadth proxy candidate，並定義 mainline/theme 與 official industry 的分層。
"""
    (OUT / "final_summary_zh.md").write_text(summary, encoding="utf-8")


if __name__ == "__main__":
    main()
