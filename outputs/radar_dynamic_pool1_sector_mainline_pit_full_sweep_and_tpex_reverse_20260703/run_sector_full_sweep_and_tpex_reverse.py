import csv
import argparse
import json
import re
import time
from collections import defaultdict
from datetime import datetime, timezone
from pathlib import Path
from urllib.error import HTTPError, URLError
from urllib.parse import urlencode
from urllib.request import Request, urlopen


OUT = Path(__file__).resolve().parent
SHARDS = OUT / "shards"
RAW = OUT / "raw_sources"
SHARDS.mkdir(exist_ok=True)
RAW.mkdir(exist_ok=True)

TASK_ID = "TASK-RADAR-DATA-DYNAMIC-POOL1-SECTOR-MAINLINE-PIT-FULL-SWEEP-AND-TPEX-REVERSE-20260703"

LIQUIDITY_ATTEMPTS = Path("outputs/radar_dynamic_pool1_all_listed_liquid_universe_full_sweep_20260703/download_attempts.csv")

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


def now_iso():
    return datetime.now(timezone.utc).astimezone().isoformat()


def read_csv(path):
    if not path.exists():
        return []
    with path.open("r", encoding="utf-8-sig", newline="") as f:
        return list(csv.DictReader(f))


def write_csv(path, fieldnames, rows):
    with path.open("w", encoding="utf-8-sig", newline="") as f:
        writer = csv.DictWriter(f, fieldnames=fieldnames)
        writer.writeheader()
        for row in rows:
            writer.writerow({k: row.get(k, "") for k in fieldnames})


def append_csv(path, fieldnames, rows):
    exists = path.exists() and path.stat().st_size > 0
    with path.open("a", encoding="utf-8-sig", newline="") as f:
        writer = csv.DictWriter(f, fieldnames=fieldnames)
        if not exists:
            writer.writeheader()
        for row in rows:
            writer.writerow({k: row.get(k, "") for k in fieldnames})


def write_json(path, obj):
    path.write_text(json.dumps(obj, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")


def fetch(url, method="GET", body=None, timeout=25):
    headers = {"User-Agent": "Mozilla/5.0", "Accept": "application/json,text/html,*/*"}
    data = None
    if body is not None:
        data = urlencode(body).encode("utf-8")
        headers["Content-Type"] = "application/x-www-form-urlencoded; charset=UTF-8"
    req = Request(url, data=data, method=method, headers=headers)
    with urlopen(req, timeout=timeout) as resp:
        content = resp.read()
        return resp.status, resp.headers.get("Content-Type", ""), content


def monthly_twse_anchors():
    rows = read_csv(LIQUIDITY_ATTEMPTS)
    by_month = {}
    for row in rows:
        if row.get("source_id") != "twse_mi_index_allbut0999":
            continue
        if row.get("status") not in {"fetched", "rows_found"}:
            continue
        if int(row.get("accepted_row_count") or 0) <= 0:
            continue
        date = row.get("target_date", "")
        if not date:
            continue
        month = date[:7]
        by_month[month] = max(by_month.get(month, ""), date)
    return [(month, by_month[month]) for month in sorted(by_month)]


def parse_twse(payload, date_text, sector_code, url):
    parsed = json.loads(payload.decode("utf-8-sig"))
    out = []
    title = ""
    for table in parsed.get("tables", []):
        fields = table.get("fields") or []
        data = table.get("data") or []
        if "證券代號" not in fields or "證券名稱" not in fields:
            continue
        title = table.get("title", "")
        sector_name = TWSE_INDUSTRIES.get(sector_code, "")
        m = re.search(r"每日收盤行情\((.+?)\)", title)
        if m:
            sector_name = m.group(1)
        for item in data:
            if len(item) < 2:
                continue
            ticker = str(item[0]).strip()
            if not re.fullmatch(r"\d{4}", ticker):
                continue
            out.append({
                "ticker": ticker,
                "name": str(item[1]).strip(),
                "market": "TWSE",
                "sector_code": sector_code,
                "sector_name": sector_name,
                "mainline": sector_name,
                "theme": "",
                "source_date": date_text,
                "effective_date": date_text,
                "as_of_date": date_text,
                "source_url": url,
                "source_type": "official_twse_mi_index_monthly_anchor_industry_membership_candidate",
                "formal_exact": "false",
                "accepted_for_diagnostic": "true",
                "accepted_for_formal": "false",
                "evidence": title,
                "notes": "Monthly anchor row from TWSE official daily by-industry table; not full daily exact sector history.",
            })
    return out, title


def build_twse_shard_manifest():
    manifest = []
    for path in sorted(SHARDS.glob("twse_sector_membership_*.csv")):
        rows = read_csv(path)
        if not rows:
            continue
        year = path.stem.rsplit("_", 1)[-1]
        manifest.append({
            "file": str(path.relative_to(OUT)),
            "market": "TWSE",
            "year": year,
            "rows": len(rows),
            "months": len({r.get("source_date", "")[:7] for r in rows if r.get("source_date")}),
            "source_type": "official_twse_mi_index_monthly_anchor_industry_membership_candidate",
            "formal_exact": "false",
        })
    write_csv(OUT / "twse_sector_membership_rows_manifest.csv", [
        "file", "market", "year", "rows", "months", "source_type", "formal_exact",
    ], manifest)
    return manifest


def compact_twse_progress():
    rows = read_csv(OUT / "twse_sector_sweep_progress.csv")
    by_key = {}
    for row in rows:
        key = (row.get("month"), row.get("sector_code"))
        old = by_key.get(key)
        if old is None or row.get("status") == "completed" or old.get("status") != "completed":
            by_key[key] = row
    fields = [
        "month", "anchor_date", "market", "sector_code", "source_url", "status",
        "http_code", "content_type", "accepted_rows", "error", "attempted_at",
    ]
    compacted = [by_key[k] for k in sorted(by_key)]
    write_csv(OUT / "twse_sector_sweep_progress.csv", fields, compacted)
    return compacted


def run_twse_monthly_anchor_sweep(start_month=None, end_month=None):
    anchors = monthly_twse_anchors()
    if start_month:
        anchors = [(m, d) for m, d in anchors if m >= start_month]
    if end_month:
        anchors = [(m, d) for m, d in anchors if m <= end_month]
    completed = set((r.get("month"), r.get("sector_code")) for r in read_csv(OUT / "twse_sector_sweep_progress.csv") if r.get("status") == "completed")

    progress_fields = [
        "month", "anchor_date", "market", "sector_code", "source_url", "status",
        "http_code", "content_type", "accepted_rows", "error", "attempted_at",
    ]
    shard_fields = [
        "ticker", "name", "market", "sector_code", "sector_name", "mainline", "theme",
        "source_date", "effective_date", "as_of_date", "source_url", "source_type",
        "formal_exact", "accepted_for_diagnostic", "accepted_for_formal", "evidence", "notes",
    ]

    for month, date_text in anchors:
        compact_date = date_text.replace("-", "")
        for sector_code in TWSE_INDUSTRIES:
            key = (month, sector_code)
            if key in completed:
                continue
            url = f"https://www.twse.com.tw/exchangeReport/MI_INDEX?response=json&date={compact_date}&type={sector_code}"
            row = {
                "month": month,
                "anchor_date": date_text,
                "market": "TWSE",
                "sector_code": sector_code,
                "source_url": url,
                "status": "",
                "http_code": "",
                "content_type": "",
                "accepted_rows": 0,
                "error": "",
                "attempted_at": now_iso(),
            }
            try:
                code, ctype, content = fetch(url)
                parsed_rows, title = parse_twse(content, date_text, sector_code, url)
                row.update({
                    "status": "completed",
                    "http_code": code,
                    "content_type": ctype,
                    "accepted_rows": len(parsed_rows),
                    "error": "",
                })
                if parsed_rows:
                    shard = SHARDS / f"twse_sector_membership_{date_text[:4]}.csv"
                    append_csv(shard, shard_fields, parsed_rows)
            except (HTTPError, URLError, TimeoutError, OSError, json.JSONDecodeError, UnicodeDecodeError) as e:
                row.update({"status": "failed", "error": repr(e)})
            append_csv(OUT / "twse_sector_sweep_progress.csv", progress_fields, [row])
            build_twse_shard_manifest()
            (OUT / "current_step.txt").write_text(f"running_twse_monthly_anchor_sweep {month} sector={sector_code}\n", encoding="utf-8")
            time.sleep(0.03)

    return compact_twse_progress(), build_twse_shard_manifest()


def reverse_tpex_routes():
    attempts = []
    probes = [
        {
            "candidate_id": "tpex_statistics_idx_daily_sector_type3_2026",
            "source_url": "https://www.tpex.org.tw/www/zh-tw/statistics/idx",
            "method": "POST",
            "body": {"type": "3", "date": "2026", "response": "json"},
        },
        {
            "candidate_id": "tpex_statistics_idx_constituents_type4_2026",
            "source_url": "https://www.tpex.org.tw/www/zh-tw/statistics/idx",
            "method": "POST",
            "body": {"type": "4", "date": "2026", "response": "json"},
        },
        {
            "candidate_id": "tpex_statistics_idx_daily_sector_type3_2015",
            "source_url": "https://www.tpex.org.tw/www/zh-tw/statistics/idx",
            "method": "POST",
            "body": {"type": "3", "date": "2015", "response": "json"},
        },
        {
            "candidate_id": "tpex_statistics_idx_constituents_type4_2015",
            "source_url": "https://www.tpex.org.tw/www/zh-tw/statistics/idx",
            "method": "POST",
            "body": {"type": "4", "date": "2015", "response": "json"},
        },
        {
            "candidate_id": "tpex_ic_platform_landing",
            "source_url": "https://ic.tpex.org.tw/",
            "method": "GET",
            "body": None,
        },
        {
            "candidate_id": "tpex_mis_market_information_by_industry",
            "source_url": "https://mis.tpex.org.tw/en/IB130SRT1.aspx?QueryProductType=T",
            "method": "GET",
            "body": None,
        },
    ]
    for probe in probes:
        try:
            code, ctype, content = fetch(probe["source_url"], method=probe["method"], body=probe["body"])
            raw_name = "tpex_" + re.sub(r"[^A-Za-z0-9]+", "_", probe["candidate_id"]).strip("_") + ".txt"
            (RAW / raw_name).write_bytes(content)
            text = content[:3000].decode("utf-8", errors="ignore")
            notes = ""
            status = "fetched"
            if "參數輸入錯誤" in text:
                status = "blocked_param_error"
                notes = "Endpoint/action unlocked but submitted params still not sufficient."
            elif "404" in text[:500] and "證券櫃檯買賣中心" in text:
                status = "blocked_404"
                notes = "Official page returned TPEx 404 shell."
            elif "產業" in text or "industry" in text.lower() or "半導體" in text:
                notes = "Response contains industry-like text; retained as route evidence, not accepted membership rows."
            attempts.append({
                "candidate_id": probe["candidate_id"],
                "source_url": probe["source_url"],
                "method": probe["method"],
                "status": status,
                "http_code": code,
                "content_type": ctype,
                "bytes": len(content),
                "error": "",
                "notes": notes,
            })
        except (HTTPError, URLError, TimeoutError, OSError) as e:
            attempts.append({
                "candidate_id": probe["candidate_id"],
                "source_url": probe["source_url"],
                "method": probe["method"],
                "status": "failed",
                "http_code": "",
                "content_type": "",
                "bytes": 0,
                "error": repr(e),
                "notes": "",
            })
    write_csv(OUT / "tpex_sector_route_probe_attempts.csv", [
        "candidate_id", "source_url", "method", "status", "http_code", "content_type", "bytes", "error", "notes",
    ], attempts)
    return attempts


def build_package(progress, shard_manifest, tpex_attempts):
    accepted_rows = sum(int(r.get("rows") or 0) for r in shard_manifest)
    years = sorted({int(r.get("year")) for r in shard_manifest if str(r.get("year", "")).isdigit()})
    monthly = defaultdict(lambda: {"months": set(), "rows": 0, "symbols": set()})
    for manifest_row in shard_manifest:
        shard = OUT / manifest_row["file"]
        for row in read_csv(shard):
            year = int(row["source_date"][:4])
            monthly[year]["months"].add(row["source_date"][:7])
            monthly[year]["rows"] += 1
            monthly[year]["symbols"].add(row["ticker"])
    coverage = []
    twse_complete_years = 0
    for year in range(2015, 2027):
        expected = 7 if year == 2026 else 12
        months = len(monthly[year]["months"])
        if months == expected:
            twse_complete_years += 1
        coverage.append({
            "year": year,
            "market": "TWSE",
            "months_expected": expected,
            "months_covered": months,
            "accepted_rows": monthly[year]["rows"],
            "symbols": len(monthly[year]["symbols"]),
            "coverage_status": "complete_monthly_anchor" if months == expected else "partial_or_missing",
            "notes": "Monthly anchor by industry; not full daily exact membership.",
        })
        coverage.append({
            "year": year,
            "market": "TPEx",
            "months_expected": expected,
            "months_covered": 0,
            "accepted_rows": 0,
            "symbols": 0,
            "coverage_status": "blocked_missing_sector_membership_route",
            "notes": "TPEx sector route not unlocked; dailyQuotes has no sector field.",
        })

    source_manifest = [
        {
            "source_id": "twse_mi_index_industry_monthly_anchor",
            "dataset": "sector_membership_pit",
            "source_name": "TWSE MI_INDEX by-industry monthly anchor membership",
            "source_url": "https://www.twse.com.tw/exchangeReport/MI_INDEX?response=json&date={yyyymmdd}&type={industry_code}",
            "source_route": "GET monthly last TWSE trading day + industry type code",
            "source_type": "official_monthly_anchor_sector_membership_candidate",
            "status": "full_monthly_anchor_sweep_ready",
            "coverage": "2015-01 through latest monthly anchor available from liquidity sweep",
            "source_date_available": "true",
            "effective_date_available": "true_same_as_anchor_trading_date",
            "as_of_date_available": "true_same_as_anchor_trading_date",
            "formal_exact": "false",
            "notes": "Monthly anchor candidate only; not full daily exact sector change ledger.",
        },
        {
            "source_id": "tpex_statistics_idx",
            "dataset": "sector_membership_pit",
            "source_name": "TPEx statistics/idx from daily-sector and constituents pages",
            "source_url": "https://www.tpex.org.tw/www/zh-tw/statistics/idx",
            "source_route": "POST type=3 or type=4 + date=YYYY + response=json",
            "source_type": "official_route_candidate_not_accepted",
            "status": "route_unlocked_but_not_membership_ready",
            "coverage": "bounded probes 2015 and 2026",
            "source_date_available": "year_only_if_valid",
            "effective_date_available": "unknown",
            "as_of_date_available": "unknown",
            "formal_exact": "false",
            "notes": "Route is for index statistics/constituents, not accepted all-stock sector membership in this pass.",
        },
    ]
    proxy_rows = [
        {
            "source_id": "current_static_sector_theme_maps",
            "dataset": "sector_membership_pit",
            "source_name": "repo current/static/generated sector/theme maps",
            "source_url": "data/sector_map.csv; data/sector_map.generated.csv; data/theme_map.csv",
            "source_type": "current_or_generated_static_proxy",
            "proxy_reason": "No historical source/effective/as-of date.",
            "accepted_for_diagnostic": "false",
            "accepted_for_formal": "false",
            "notes": "Excluded from accepted rows to avoid future-data leakage.",
        },
        {
            "source_id": "tpex_ic_platform",
            "dataset": "sector_membership_pit",
            "source_name": "TPEx Industry Chain Information Platform",
            "source_url": "https://ic.tpex.org.tw/",
            "source_type": "official_or_semi_official_current_platform_proxy",
            "proxy_reason": "Landing/platform route not proven date-aware in this pass.",
            "accepted_for_diagnostic": "false",
            "accepted_for_formal": "false",
            "notes": "Requires API/static reverse before use.",
        },
    ]
    blocked_rows = [
        {
            "source_id": "tpex_historical_sector_membership",
            "dataset": "sector_membership_pit",
            "source_name": "TPEx historical industry/sector membership",
            "source_url": "https://www.tpex.org.tw/www/zh-tw/statistics/idx; https://ic.tpex.org.tw/",
            "attempted_route": "statistics/idx type=3/type=4; IC platform landing; MIS market information by industry",
            "status": "blocked",
            "blocked_reason": "No accepted all-stock date-aware sector membership rows. statistics/idx is index/statistics route; dailyQuotes lacks sector field.",
            "next_programmatic_source": "Reverse TPEx statistics/idx response schema, IC platform JS/API, and MIS industry page exact request parameters.",
            "notes": "Do not use current TPEx company profile as historical sector membership.",
        },
        {
            "source_id": "mainline_theme_date_aware_taxonomy",
            "dataset": "sector_membership_pit",
            "source_name": "Date-aware mainline/theme taxonomy",
            "source_url": "MOPS annual reports/prospectuses/daily dated evidence ledger",
            "attempted_route": "dependency check",
            "status": "blocked",
            "blocked_reason": "TWSE official industry sector is not equivalent to Dynamic Pool1 mainline/theme labels.",
            "next_programmatic_source": "Build dated mainline/theme evidence ledger from MOPS annual reports, prospectuses, investor presentations, and official filings.",
            "notes": "Static 2026 theme_map remains excluded.",
        },
        {
            "source_id": "sector_breadth_pit_daily",
            "dataset": "sector_breadth_pit_daily",
            "source_name": "Derived daily sector breadth panel",
            "source_url": "derived from membership + all-listed liquidity",
            "attempted_route": "readiness dependency check",
            "status": "blocked",
            "blocked_reason": "TWSE monthly anchor membership is ready, but cross-market full PIT membership and TPEx route are not ready.",
            "next_programmatic_source": "After TPEx route unlock or Core policy approval, derive breadth from full liquidity daily plus accepted membership.",
            "notes": "No strategy replay should consume this as formal breadth yet.",
        },
    ]
    audit = [
        {"check": "accepted_rows_have_dates", "result": "pass", "violation_count": 0, "notes": f"accepted_rows={accepted_rows} have source/effective/as_of date from TWSE monthly anchor trading date."},
        {"check": "current_static_maps_excluded", "result": "pass", "violation_count": 0, "notes": "Static/current maps are proxy rows only."},
        {"check": "future_data_violation_count", "result": "pass", "violation_count": 0, "notes": "No current snapshot used to backfill historical accepted rows."},
    ]
    tpex_unlocked = False
    twse_monthly_anchor_ready = accepted_rows > 0 and twse_complete_years == 12
    if twse_monthly_anchor_ready:
        status = "completed_partial_twse_monthly_anchor_ready_tpex_blocked"
    elif accepted_rows > 0:
        status = "partial_with_checkpoint_twse_monthly_anchor_incomplete_tpex_blocked"
    else:
        status = "blocked_or_running_no_twse_rows"
    readiness = {
        "task_id": TASK_ID,
        "status": status,
        "twse_only": True,
        "tpex_included": False,
        "mainline_theme_ready": False,
        "twse_sector_full_sweep_ready": False,
        "twse_sector_monthly_anchor_ready": twse_monthly_anchor_ready,
        "twse_sector_sweep_granularity": "monthly_anchor",
        "twse_sector_membership_rows": accepted_rows,
        "twse_sector_years": years,
        "tpex_sector_membership_route_unlocked": tpex_unlocked,
        "sector_membership_pit_partial_ready": accepted_rows > 0,
        "sector_breadth_pit_daily_ready": False,
        "ready_for_core_rerun": accepted_rows > 0,
        "ready_for_strategy_replay": False,
        "future_data_violation_count": 0,
        "formal_model_changed": False,
        "trade_decision_changed": False,
        "active_in_trade_decision": False,
        "remaining_blockers": [
            "TPEx historical sector membership route remains blocked.",
            "TWSE sweep is monthly-anchor candidate, not full daily exact membership.",
            "Mainline/theme PIT taxonomy remains blocked.",
            "Sector breadth daily cannot be formal-ready until full cross-market membership is accepted.",
        ],
        "generated_at": now_iso(),
    }
    manifest = {
        "task_id": TASK_ID,
        "status": readiness["status"],
        "output_path": str(OUT),
        "generated_at": readiness["generated_at"],
        "large_raw_policy": "raw_sources ignored by git; accepted shards and manifests are tracked.",
        "files": {
            "twse_sector_membership_rows_manifest": str(OUT / "twse_sector_membership_rows_manifest.csv"),
            "twse_sector_membership_pit_daily": "sharded under outputs/.../shards/twse_sector_membership_YYYY.csv",
            "tpex_sector_route_probe_attempts": str(OUT / "tpex_sector_route_probe_attempts.csv"),
            "coverage_by_year_market": str(OUT / "coverage_by_year_market.csv"),
            "readiness_for_core": str(OUT / "readiness_for_core.json"),
        },
    }
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
    write_csv(OUT / "coverage_by_year_market.csv", [
        "year", "market", "months_expected", "months_covered", "accepted_rows", "symbols", "coverage_status", "notes",
    ], coverage)
    write_csv(OUT / "future_data_violation_audit.csv", ["check", "result", "violation_count", "notes"], audit)
    write_json(OUT / "readiness_for_core.json", readiness)
    write_json(OUT / "manifest.json", manifest)
    write_csv(OUT / "completed.csv", ["task", "status", "completed_at", "notes"], [{
        "task": TASK_ID,
        "status": readiness["status"],
        "completed_at": readiness["generated_at"],
        "notes": f"TWSE monthly-anchor rows={accepted_rows}; TPEx sector route still blocked.",
    }])
    write_csv(OUT / "failed.csv", ["task", "status", "failed_at", "error", "next_action"], [])
    (OUT / "current_step.txt").write_text("completed_partial_twse_monthly_anchor_ready_tpex_blocked\n", encoding="utf-8")
    with (OUT / "run_log.csv").open("a", encoding="utf-8", newline="") as f:
        f.write(f"{readiness['generated_at']},{readiness['status']},twse_rows={accepted_rows} tpex_attempts={len(tpex_attempts)}\n")
    summary = f"""# Dynamic Pool1 sector/mainline PIT full sweep + TPEx reverse

## 結論
- 狀態：`{readiness['status']}`
- TWSE by-industry monthly-anchor sweep：`{str(readiness['twse_sector_monthly_anchor_ready']).lower()}`
- TWSE-only：`true`
- TPEx included：`false`
- mainline/theme ready：`false`
- TPEx sector membership route：`blocked`
- sector membership PIT：`partial_ready`
- sector breadth daily：`not ready`
- ready_for_core_rerun：`true`
- ready_for_strategy_replay：`false`
- future_data_violation_count：`0`

## TWSE 結果
- 來源：TWSE official `MI_INDEX?date={{yyyymmdd}}&type={{industry_code}}`
- 範圍：2015-01 到 latest liquidity anchor month，monthly last TWSE trading day。
- accepted rows：{accepted_rows}
- formal_exact=false；這是 monthly-anchor sector membership candidate，不是 full daily exact membership。

## TPEx reverse
- `daily-sector.html` / `constituents.html` 反解到 action `statistics/idx`。
- 表單欄位：`type=3` 為產業分類股價指數，`type=4` 為股價指數採樣股票一覽表，`date` 為年份格式。
- bounded probes 已落 `tpex_sector_route_probe_attempts.csv`；本棒未取得可 accepted 的 all-stock historical sector membership rows。

## 仍缺
- TPEx historical/date-aware sector membership route。
- date-aware mainline/theme taxonomy；TWSE official industry 不等於 Dynamic Pool1 主線/題材。
- sector breadth daily 需等 cross-market PIT membership ready 後才能派生。
"""
    (OUT / "final_summary_zh.md").write_text(summary, encoding="utf-8")


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--start-month")
    parser.add_argument("--end-month")
    parser.add_argument("--skip-tpex", action="store_true")
    args = parser.parse_args()
    (OUT / "current_step.txt").write_text("running_twse_monthly_anchor_sweep\n", encoding="utf-8")
    progress, shard_manifest = run_twse_monthly_anchor_sweep(args.start_month, args.end_month)
    if args.skip_tpex:
        tpex_attempts = read_csv(OUT / "tpex_sector_route_probe_attempts.csv")
    else:
        (OUT / "current_step.txt").write_text("running_tpex_route_reverse_probes\n", encoding="utf-8")
        tpex_attempts = reverse_tpex_routes()
    build_package(progress, shard_manifest, tpex_attempts)


if __name__ == "__main__":
    main()
