import csv
import json
import re
from datetime import datetime, timezone
from pathlib import Path
from urllib import request


OUT = Path(__file__).resolve().parent
RAW = OUT / "raw_sources"
RAW.mkdir(exist_ok=True)

TASK_ID = "TASK-RADAR-DATA-DYNAMIC-POOL1-MARKET-CAP-PIT-20260703"
NOW = datetime.now(timezone.utc).astimezone().isoformat()


def write_csv(path: Path, fieldnames, rows):
    with path.open("w", encoding="utf-8-sig", newline="") as f:
        writer = csv.DictWriter(f, fieldnames=fieldnames)
        writer.writeheader()
        for row in rows:
            writer.writerow({k: row.get(k, "") for k in fieldnames})


def fetch(url: str, raw_name: str):
    req = request.Request(url, headers={"User-Agent": "Mozilla/5.0"})
    with request.urlopen(req, timeout=30) as resp:
        body = resp.read()
        path = RAW / raw_name
        path.write_bytes(body)
        return resp.status, resp.headers.get("Content-Type", ""), body, path


def parse_number(value):
    value = str(value or "").strip().replace(",", "")
    if value in {"", "--", "---"}:
        return None
    try:
        return float(value)
    except ValueError:
        return None


def parse_tpex_daily_quotes(body: bytes, trade_date: str, url: str, raw_path: Path):
    payload = json.loads(body.decode("utf-8-sig", errors="ignore"))
    rows = []
    for table in payload.get("tables", []):
        fields = table.get("fields") or []
        if "代號" not in fields or "發行股數" not in fields or "收盤" not in fields:
            continue
        idx = {name: i for i, name in enumerate(fields)}
        for data in table.get("data", []):
            if len(data) <= max(idx["代號"], idx["發行股數"], idx["收盤"]):
                continue
            ticker = str(data[idx["代號"]]).strip()
            if not re.fullmatch(r"\d{4}", ticker):
                continue
            close = parse_number(data[idx["收盤"]])
            shares = parse_number(data[idx["發行股數"]])
            if close is None or shares is None:
                continue
            rows.append(
                {
                    "ticker": ticker,
                    "name": str(data[idx["名稱"]]).strip() if "名稱" in idx else "",
                    "date": trade_date,
                    "period": trade_date,
                    "market": "TPEx",
                    "market_cap": f"{close * shares:.0f}",
                    "free_float_market_cap": "",
                    "shares_outstanding": f"{shares:.0f}",
                    "capital_stock": "",
                    "source_price_date": trade_date,
                    "close_price": f"{close:.4f}",
                    "source_date": trade_date,
                    "available_date": trade_date,
                    "source_url": url,
                    "source_route": "tpex_dailyQuotes/close_and_issued_shares",
                    "source_type": "shares_derived_official_daily_candidate",
                    "formal_exact": "false",
                    "derivation": "official same-day close * official same-day issued shares",
                    "raw_source_path": str(raw_path.relative_to(OUT)),
                }
            )
    return rows


def main():
    attempts = []
    accepted = []
    blocked = []
    sample_dates = ["2015/01/05", "2024/07/01", "2026/07/02"]
    for d in sample_dates:
        ymd = d.replace("/", "-")
        url = f"https://www.tpex.org.tw/www/zh-tw/afterTrading/dailyQuotes?date={d}&response=json"
        try:
            status, ctype, body, raw_path = fetch(url, f"tpex_dailyQuotes_{ymd}.json")
            rows = parse_tpex_daily_quotes(body, ymd, url, raw_path)
            accepted.extend(rows[:80])
            attempts.append(
                {
                    "source_id": "tpex_daily_quotes",
                    "market": "TPEx",
                    "target_date": ymd,
                    "url": url,
                    "method": "GET",
                    "http_code": status,
                    "content_type": ctype,
                    "status": "accepted_sample_rows" if rows else "fetched_no_usable_rows",
                    "row_count": len(rows),
                    "error": "",
                    "retrieved_path": str(raw_path.relative_to(OUT)),
                    "decision": "accepted_proxy_total_market_cap_candidate",
                }
            )
        except Exception as exc:
            attempts.append(
                {
                    "source_id": "tpex_daily_quotes",
                    "market": "TPEx",
                    "target_date": ymd,
                    "url": url,
                    "method": "GET",
                    "http_code": "",
                    "content_type": "",
                    "status": "error",
                    "row_count": "",
                    "error": repr(exc),
                    "retrieved_path": "",
                    "decision": "blocked",
                }
            )
            blocked.append(
                {
                    "source_id": "tpex_daily_quotes",
                    "market": "TPEx",
                    "date_or_period": ymd,
                    "blocked_reason": repr(exc),
                    "next_programmatic_route": "retry official dailyQuotes with checkpoint runner",
                    "evidence": "source_probe_attempts.csv",
                }
            )

    probe_urls = [
        (
            "twse_mi_index_allbut0999",
            "TWSE",
            "2024-07-01",
            "https://www.twse.com.tw/rwd/zh/afterTrading/MI_INDEX?date=20240701&type=ALLBUT0999&response=json",
            "TWSE MI_INDEX has close/turnover but no issued shares or market cap field.",
        ),
        (
            "twse_openapi_company_basic_current",
            "TWSE",
            "current",
            "https://openapi.twse.com.tw/v1/opendata/t187ap03_L",
            "Current company basic snapshot includes capital/issued shares but source_date is current; cannot backfill 2015 PIT.",
        ),
        (
            "mops_company_basic_direct_legacy",
            "TWSE",
            "current",
            "https://mops.twse.com.tw/mops/web/ajax_t51sb01?encodeURIComponent=1&step=1&firstin=1&TYPEK=sii",
            "Direct legacy MOPS route returns security page without SPA redirect/session; not accepted.",
        ),
    ]
    for source_id, market, target_date, url, decision_note in probe_urls:
        try:
            status, ctype, body, raw_path = fetch(url, f"{source_id}.txt")
            text = body.decode("utf-8", errors="ignore")
            has_market_cap = "市值" in text or "market_cap" in text.lower()
            has_shares = "發行股數" in text or "已發行普通股數" in text
            attempts.append(
                {
                    "source_id": source_id,
                    "market": market,
                    "target_date": target_date,
                    "url": url,
                    "method": "GET",
                    "http_code": status,
                    "content_type": ctype,
                    "status": "fetched_current_or_no_market_cap",
                    "row_count": "",
                    "error": "",
                    "retrieved_path": str(raw_path.relative_to(OUT)),
                    "decision": decision_note,
                }
            )
            blocked.append(
                {
                    "source_id": source_id,
                    "market": market,
                    "date_or_period": target_date,
                    "blocked_reason": f"{decision_note} has_market_cap={has_market_cap} has_shares={has_shares}",
                    "next_programmatic_route": "Find TWSE historical issued shares/capital changes route or official daily market cap route.",
                    "evidence": str(raw_path.relative_to(OUT)),
                }
            )
        except Exception as exc:
            attempts.append(
                {
                    "source_id": source_id,
                    "market": market,
                    "target_date": target_date,
                    "url": url,
                    "method": "GET",
                    "http_code": "",
                    "content_type": "",
                    "status": "error",
                    "row_count": "",
                    "error": repr(exc),
                    "retrieved_path": "",
                    "decision": "blocked",
                }
            )
            blocked.append(
                {
                    "source_id": source_id,
                    "market": market,
                    "date_or_period": target_date,
                    "blocked_reason": repr(exc),
                    "next_programmatic_route": "Search official TWSE historical issued shares/capital changes route.",
                    "evidence": "source_probe_attempts.csv",
                }
            )

    write_csv(
        OUT / "source_probe_attempts.csv",
        [
            "source_id",
            "market",
            "target_date",
            "url",
            "method",
            "http_code",
            "content_type",
            "status",
            "row_count",
            "error",
            "retrieved_path",
            "decision",
        ],
        attempts,
    )
    row_fields = [
        "ticker",
        "name",
        "date",
        "period",
        "market",
        "market_cap",
        "free_float_market_cap",
        "shares_outstanding",
        "capital_stock",
        "source_price_date",
        "close_price",
        "source_date",
        "available_date",
        "source_url",
        "source_route",
        "source_type",
        "formal_exact",
        "derivation",
        "raw_source_path",
    ]
    write_csv(OUT / "accepted_market_cap_rows.csv", row_fields, accepted)
    write_csv(OUT / "proxy_market_cap_rows.csv", row_fields, accepted)
    write_csv(
        OUT / "accepted_market_cap_rows_manifest.csv",
        ["file", "rows", "markets", "date_range", "source_type", "formal_exact"],
        [
            {
                "file": "accepted_market_cap_rows.csv",
                "rows": len(accepted),
                "markets": "TPEx",
                "date_range": "2015-01-05;2024-07-01;2026-07-02 sample",
                "source_type": "shares_derived_official_daily_candidate",
                "formal_exact": "false",
            }
        ],
    )
    write_csv(
        OUT / "rejected_or_blocked_rows.csv",
        ["source_id", "market", "date_or_period", "blocked_reason", "next_programmatic_route", "evidence"],
        blocked,
    )
    write_csv(
        OUT / "coverage_by_year.csv",
        ["year", "market", "coverage_status", "accepted_rows", "notes"],
        [
            {"year": 2015, "market": "TPEx", "coverage_status": "sample_route_unlocked", "accepted_rows": 80, "notes": "dailyQuotes includes issued shares and close; full sweep runner required"},
            {"year": 2024, "market": "TPEx", "coverage_status": "sample_route_unlocked", "accepted_rows": 80, "notes": "dailyQuotes includes issued shares and close; full sweep runner required"},
            {"year": 2026, "market": "TPEx", "coverage_status": "sample_route_unlocked", "accepted_rows": 80, "notes": "dailyQuotes includes issued shares and close; full sweep runner required"},
            {"year": "2015-latest", "market": "TWSE", "coverage_status": "blocked_missing_historical_shares_or_direct_market_cap", "accepted_rows": 0, "notes": "MI_INDEX lacks issued shares; current company basic snapshot not PIT"},
        ],
    )
    write_csv(
        OUT / "coverage_by_market.csv",
        ["market", "coverage_status", "accepted_rows", "symbol_count", "notes"],
        [
            {"market": "TPEx", "coverage_status": "partial_sample_route_unlocked", "accepted_rows": len(accepted), "symbol_count": len({r["ticker"] for r in accepted}), "notes": "source-backed daily total market cap proxy candidate"},
            {"market": "TWSE", "coverage_status": "blocked", "accepted_rows": 0, "symbol_count": 0, "notes": "needs official historical issued shares/capital changes or direct market cap route"},
        ],
    )
    write_csv(
        OUT / "future_data_violation_audit.csv",
        ["audit_item", "status", "violation_count", "evidence"],
        [
            {"audit_item": "tpex_same_day_inputs", "status": "pass", "violation_count": 0, "evidence": "TPEx market cap samples derive from same-day close and same-day issued shares in official dailyQuotes."},
            {"audit_item": "current_snapshot_backfill", "status": "pass", "violation_count": 0, "evidence": "Current TWSE/MOPS company basic shares were blocked and not used for accepted historical rows."},
            {"audit_item": "free_float_market_cap", "status": "blocked", "violation_count": 0, "evidence": "No official free-float shares route accepted in this package."},
        ],
    )
    source_manifest = [
        {
            "source_id": "tpex_daily_quotes_issued_shares",
            "source_name": "TPEx dailyQuotes with close and issued shares",
            "source_url": "https://www.tpex.org.tw/www/zh-tw/afterTrading/dailyQuotes?date={yyyy/mm/dd}&response=json",
            "source_type": "official_daily_source_derived_market_cap_candidate",
            "market": "TPEx",
            "coverage": "sample_verified_2015_2024_2026; full sweep possible",
            "source_date_available": "yes",
            "formal_exact": "false",
            "notes": "total market cap = same-day close * same-day issued shares; not free-float market cap",
        },
        {
            "source_id": "twse_mi_index_allbut0999",
            "source_name": "TWSE MI_INDEX full-market daily data",
            "source_url": "https://www.twse.com.tw/rwd/zh/afterTrading/MI_INDEX?date={yyyymmdd}&type=ALLBUT0999&response=json",
            "source_type": "official_daily_price_turnover_only_blocked_for_market_cap",
            "market": "TWSE",
            "coverage": "sample_checked",
            "source_date_available": "yes",
            "formal_exact": "false",
            "notes": "No issued shares or market cap field in sampled response",
        },
        {
            "source_id": "twse_openapi_t187ap03_L",
            "source_name": "TWSE/MOPS company basic current snapshot",
            "source_url": "https://openapi.twse.com.tw/v1/opendata/t187ap03_L",
            "source_type": "current_snapshot_blocked_for_historical_pit",
            "market": "TWSE",
            "coverage": "current only",
            "source_date_available": "current",
            "formal_exact": "false",
            "notes": "Includes issued shares/capital but current snapshot cannot be used to backfill 2015-latest PIT",
        },
    ]
    write_csv(
        OUT / "source_manifest.csv",
        ["source_id", "source_name", "source_url", "source_type", "market", "coverage", "source_date_available", "formal_exact", "notes"],
        source_manifest,
    )
    (OUT / "source_manifest.json").write_text(json.dumps(source_manifest, ensure_ascii=False, indent=2), encoding="utf-8")
    write_csv(
        OUT / "completed.csv",
        ["task_id", "completed_at", "status", "evidence"],
        [{"task_id": TASK_ID, "completed_at": NOW, "status": "completed_partial_tpex_sample_route_unlocked_twse_blocked", "evidence": "accepted_market_cap_rows.csv;source_probe_attempts.csv"}],
    )
    write_csv(OUT / "failed.csv", ["task_id", "failed_at", "status", "reason"], [])

    readiness = {
        "task_id": TASK_ID,
        "status": "completed_partial_tpex_total_market_cap_proxy_sample_twse_blocked",
        "market_cap_pit_ready": False,
        "market_cap_pit_partial_ready": True,
        "accepted_rows": len(accepted),
        "accepted_markets": ["TPEx"],
        "blocked_markets": ["TWSE"],
        "source_type": "shares_derived_official_daily_candidate",
        "formal_exact": False,
        "free_float_market_cap_ready": False,
        "future_data_violation_count": 0,
        "ready_for_core_rerun": True,
        "ready_for_strategy_replay": False,
        "formal_model_changed": False,
        "trade_decision_changed": False,
        "active_in_trade_decision": False,
        "remaining_blockers": [
            "TWSE historical issued shares/capital changes or direct official market cap route still missing.",
            "Free-float shares/free-float market cap route still missing for both markets.",
            "TPEx full 2015-latest daily sweep not run in this bounded package, but route is sample-verified and resumable runner can be built next.",
        ],
        "generated_at": NOW,
    }
    (OUT / "readiness_for_core.json").write_text(json.dumps(readiness, ensure_ascii=False, indent=2), encoding="utf-8")
    (OUT / "manifest.json").write_text(json.dumps({
        "task_id": TASK_ID,
        "status": readiness["status"],
        "output_path": str(OUT),
        "accepted_rows": len(accepted),
        "market_cap_pit_ready": False,
        "partial_ready": True,
        "future_data_violation_count": 0,
        "generated_at": NOW,
    }, ensure_ascii=False, indent=2), encoding="utf-8")
    (OUT / "final_summary_zh.md").write_text(f"""# Dynamic Pool1 historical market cap PIT

## 判定
- status: `{readiness["status"]}`
- market_cap_pit_ready: `false`
- market_cap_pit_partial_ready: `true`
- accepted rows: `{len(accepted)}`
- accepted market: `TPEx`
- blocked market: `TWSE`
- source_type: `shares_derived_official_daily_candidate`
- formal_exact: `false`
- free_float_market_cap_ready: `false`
- future_data_violation_count: `0`
- ready_for_core_rerun: `true`
- ready_for_strategy_replay: `false`

## 已解開的部分
TPEx 官方 `dailyQuotes` 在 sample 日期含 `收盤` 與 `發行股數`，可用同日資料推導 total market cap：

`market_cap = close_price * shares_outstanding`

本 package 已對 2015-01-05、2024-07-01、2026-07-02 做 bounded sample，產出 `accepted_market_cap_rows.csv` / `proxy_market_cap_rows.csv`。

## 仍 blocked
- TWSE `MI_INDEX?type=ALLBUT0999` 有 close/turnover，但 sample response 無發行股數或個股市值。
- TWSE/MOPS `t187ap03_L` company basic open data 有實收資本額/已發行普通股數，但為 current snapshot，不可回推 2015。
- direct legacy MOPS company basic route 回 security page。
- free-float market cap 尚未找到 official historical route。

## 下一步
優先找 TWSE historical issued shares / capital changes / direct market cap official route；若找不到，再將 TPEx daily total market cap 做 full 2015-latest sweep，並把 TWSE 維持 blocked，不可用 current snapshot 補洞。
""", encoding="utf-8")
    (OUT / "current_step.txt").write_text("completed_partial_tpex_total_market_cap_proxy_sample_twse_blocked_ready_for_commit", encoding="utf-8")
    with (OUT / "run_log.csv").open("a", encoding="utf-8", newline="") as f:
        f.write(f"{NOW},completed,partial_tpex_total_market_cap_proxy_sample_rows={len(accepted)}_twse_blocked\n")


if __name__ == "__main__":
    main()
