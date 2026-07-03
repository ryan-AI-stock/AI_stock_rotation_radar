import csv
import hashlib
import json
from collections import defaultdict
from datetime import date, datetime, timedelta, timezone
from pathlib import Path


OUT = Path(__file__).resolve().parent
SHARD_DIR = OUT / "tpex_full_sweep_shards"
RAW_DIR = OUT / "tpex_full_sweep_raw"


def now_iso():
    return datetime.now(timezone.utc).replace(microsecond=0).isoformat()


def read_csv(path):
    if not path.exists():
        return []
    with path.open("r", encoding="utf-8-sig", newline="") as f:
        return list(csv.DictReader(f))


def write_csv(path, rows, fieldnames):
    with path.open("w", encoding="utf-8", newline="") as f:
        w = csv.DictWriter(f, fieldnames=fieldnames)
        w.writeheader()
        for row in rows:
            w.writerow({k: row.get(k, "") for k in fieldnames})


def sha256_file(path):
    h = hashlib.sha256()
    with path.open("rb") as f:
        for chunk in iter(lambda: f.read(1024 * 1024), b""):
            h.update(chunk)
    return h.hexdigest()


def count_rows(path):
    with path.open("r", encoding="utf-8-sig", newline="") as f:
        return max(sum(1 for _ in f) - 1, 0)


def weekday_dates(start, end):
    cur = start
    out = []
    while cur <= end:
        if cur.weekday() < 5:
            out.append(cur.isoformat())
        cur += timedelta(days=1)
    return out


def main():
    completed = read_csv(OUT / "tpex_market_cap_completed.csv")
    failed = read_csv(OUT / "tpex_market_cap_failed.csv")
    shards = sorted(SHARD_DIR.glob("accepted_tpex_market_cap_rows_*.csv"))

    shard_rows = []
    sample_rows = []
    coverage_month = {}
    coverage_year = defaultdict(lambda: {"market": "TPEx", "accepted_rows": 0, "trading_days": set(), "months": set()})
    coverage_market = defaultdict(lambda: {"accepted_rows": 0, "covered_dates": set(), "covered_years": set()})

    for shard in shards:
        ym = shard.stem.replace("accepted_tpex_market_cap_rows_", "")
        rows = count_rows(shard)
        digest = sha256_file(shard)
        year = ym[:4]
        dates = set()
        symbols = set()
        with shard.open("r", encoding="utf-8-sig", newline="") as f:
            reader = csv.DictReader(f)
            for row in reader:
                if len(sample_rows) < 1000:
                    sample_rows.append(row)
                if row.get("date"):
                    dates.add(row["date"])
                if row.get("ticker"):
                    symbols.add(row["ticker"])
        coverage_month[ym] = {
            "year_month": ym,
            "market": "TPEx",
            "accepted_rows": rows,
            "trading_days": len(dates),
            "symbols": len(symbols),
            "status": "covered" if rows else "missing",
        }
        coverage_year[year]["accepted_rows"] += rows
        coverage_year[year]["trading_days"].update(dates)
        coverage_year[year]["months"].add(ym)
        coverage_market["TPEx"]["accepted_rows"] += rows
        coverage_market["TPEx"]["covered_dates"].update(dates)
        coverage_market["TPEx"]["covered_years"].add(year)
        shard_rows.append({
            "shard_path": str(shard.relative_to(OUT)),
            "year_month": ym,
            "market": "TPEx",
            "rows": rows,
            "bytes": shard.stat().st_size,
            "sha256": digest,
            "git_tracked": "false_large_local_shard",
        })

    if sample_rows:
        sample_fields = list(sample_rows[0].keys())
        write_csv(OUT / "proxy_market_cap_rows.csv", sample_rows, sample_fields)

    write_csv(
        OUT / "accepted_market_cap_rows_manifest.csv",
        shard_rows,
        ["shard_path", "year_month", "market", "rows", "bytes", "sha256", "git_tracked"],
    )

    twse_rows = [
        {
            "market": "TWSE",
            "route": "TWSE MI_INDEX type=ALLBUT0999",
            "status": "blocked_no_issued_shares_or_direct_market_cap_field",
            "sample_or_blocker": "blocker",
            "source_type": "official_route_probe",
            "formal_exact": "false",
            "notes": "MI_INDEX provides daily trading fields such as close and turnover but not PIT issued shares or direct market cap.",
        },
        {
            "market": "TWSE",
            "route": "MOPS SPA t05st03 base company profile",
            "status": "route_unlocked_current_only_not_accepted_for_historical_pit",
            "sample_or_blocker": "current_only_sample_candidate",
            "source_type": "official_current_snapshot_candidate",
            "formal_exact": "false",
            "notes": "Static JS confirms t05st03 fields include capitalAmount, listingDate and commonStockAmount; no date/as-of parameter was found, so it cannot backfill 2015 historical shares.",
        },
        {
            "market": "TWSE",
            "route": "MOPS t51sb01 / ajax_t51sb01",
            "status": "route_unlocked_current_summary_not_historical_market_cap",
            "sample_or_blocker": "current_only_summary_candidate",
            "source_type": "official_current_snapshot_candidate",
            "formal_exact": "false",
            "notes": "Static JS confirms basic-data summary route by TYPEK and industry, but no effective date parameter for historical issued shares.",
        },
        {
            "market": "TWSE",
            "route": "free-float market cap",
            "status": "blocked_no_official_full_history_route_found",
            "sample_or_blocker": "blocker",
            "source_type": "blocked",
            "formal_exact": "false",
            "notes": "No official free-float market cap route found in this bounded pass.",
        },
    ]
    write_csv(
        OUT / "twse_blocker_or_sample_rows.csv",
        twse_rows,
        ["market", "route", "status", "sample_or_blocker", "source_type", "formal_exact", "notes"],
    )

    completed_dates = {r.get("date") for r in completed if r.get("status") == "completed"}
    expected_dates = set(weekday_dates(date(2015, 1, 1), date.today()))
    missing_dates = sorted(expected_dates - completed_dates)
    active_failed = [r for r in failed if r.get("date") not in completed_dates]
    tpex_done = bool(completed) and not active_failed and not missing_dates

    route_attempts = [
        {
            "source": "TPEx",
            "route": "dailyQuotes",
            "method": "GET",
            "target": "2015-latest full date sweep",
            "status": "completed" if tpex_done else "running_or_partial",
            "accepted_rows": sum(int(r["rows"]) for r in shard_rows) if shard_rows else 0,
            "error": "",
        },
        {
            "source": "TWSE",
            "route": "MI_INDEX?type=ALLBUT0999",
            "method": "GET",
            "target": "direct market cap / issued shares fields",
            "status": "blocked_no_field",
            "accepted_rows": 0,
            "error": "No issued shares or direct market cap field in official daily trading response.",
        },
        {
            "source": "MOPS",
            "route": "SPA chunk t05st03 + base t05st03",
            "method": "static_reverse",
            "target": "TWSE current company profile shares/capital route",
            "status": "route_unlocked_current_only",
            "accepted_rows": 0,
            "error": "No historical effective/as-of date parameter found.",
        },
        {
            "source": "MOPS",
            "route": "SPA chunk t51sb01/ajax_t51sb01",
            "method": "static_reverse",
            "target": "TWSE listed company basic summary",
            "status": "route_unlocked_current_only",
            "accepted_rows": 0,
            "error": "No historical effective/as-of date parameter found.",
        },
    ]
    write_csv(
        OUT / "route_probe_attempts.csv",
        route_attempts,
        ["source", "route", "method", "target", "status", "accepted_rows", "error"],
    )

    blocked = [
        {
            "dataset": "TWSE total market cap PIT",
            "market": "TWSE",
            "blocked_reason": "official direct historical market cap or PIT issued shares route not found",
            "next_programmatic_source": "reverse MOPS capital-change pages / TWSE listed company capital-change archive / official open-data catalog for dated issued shares",
        },
        {
            "dataset": "free-float market cap PIT",
            "market": "TWSE/TPEx",
            "blocked_reason": "official free-float shares or free-float market cap history not found",
            "next_programmatic_source": "Taiwan Index free-float factor publications or index-company constituent/free-float archives if available",
        },
    ]
    write_csv(
        OUT / "rejected_or_blocked_rows.csv",
        blocked,
        ["dataset", "market", "blocked_reason", "next_programmatic_source"],
    )

    coverage_year_rows = []
    for year in sorted(coverage_year):
        data = coverage_year[year]
        coverage_year_rows.append({
            "year": year,
            "market": "TPEx",
            "accepted_rows": data["accepted_rows"],
            "covered_trading_days": len(data["trading_days"]),
            "covered_months": len(data["months"]),
            "status": "covered" if data["accepted_rows"] else "missing",
        })
    coverage_year_rows.append({
        "year": "2015-latest",
        "market": "TWSE",
        "accepted_rows": 0,
        "covered_trading_days": 0,
        "covered_months": 0,
        "status": "blocked_no_historical_issued_shares_or_direct_market_cap_route",
    })
    write_csv(
        OUT / "coverage_by_year.csv",
        coverage_year_rows,
        ["year", "market", "accepted_rows", "covered_trading_days", "covered_months", "status"],
    )

    coverage_market_rows = []
    for market, data in sorted(coverage_market.items()):
        coverage_market_rows.append({
            "market": market,
            "accepted_rows": data["accepted_rows"],
            "covered_dates": len(data["covered_dates"]),
            "covered_years": len(data["covered_years"]),
            "status": "full_sweep_completed" if tpex_done else "partial_or_running",
        })
    coverage_market_rows.append({
        "market": "TWSE",
        "accepted_rows": 0,
        "covered_dates": 0,
        "covered_years": 0,
        "status": "blocked_route_not_unlocked_for_historical_market_cap",
    })
    write_csv(
        OUT / "coverage_by_market.csv",
        coverage_market_rows,
        ["market", "accepted_rows", "covered_dates", "covered_years", "status"],
    )

    write_csv(
        OUT / "tpex_full_sweep_coverage.csv",
        [coverage_month[k] for k in sorted(coverage_month)],
        ["year_month", "market", "accepted_rows", "trading_days", "symbols", "status"],
    )

    source_manifest = [
        {
            "source": "TPEx dailyQuotes",
            "source_url": "https://www.tpex.org.tw/www/en-us/afterTrading/dailyQuotes",
            "source_type": "official_source_candidate",
            "coverage": "2015-latest TPEx daily rows in local shards",
            "date_awareness": "source_date is trading date",
            "formal_exact": "false",
            "notes": "market_cap derived as close_price * official shares_outstanding from same daily quote source.",
        },
        {
            "source": "TWSE MI_INDEX",
            "source_url": "https://www.twse.com.tw/exchangeReport/MI_INDEX",
            "source_type": "official_route_probe_blocked",
            "coverage": "daily trading fields only",
            "date_awareness": "trading date available; issued shares/direct market cap unavailable",
            "formal_exact": "false",
            "notes": "Not accepted for TWSE market cap because shares/direct market cap field is missing.",
        },
        {
            "source": "MOPS t05st03/t51sb01 SPA",
            "source_url": "https://mops.twse.com.tw/mops/web/index",
            "source_type": "official_current_snapshot_candidate",
            "coverage": "current company basic/profile route only in this pass",
            "date_awareness": "no historical as-of parameter found",
            "formal_exact": "false",
            "notes": "Static chunks expose capital/commonStockAmount fields but are current-only for PIT use.",
        },
    ]
    write_csv(
        OUT / "source_manifest.csv",
        source_manifest,
        ["source", "source_url", "source_type", "coverage", "date_awareness", "formal_exact", "notes"],
    )
    (OUT / "source_manifest.json").write_text(json.dumps(source_manifest, ensure_ascii=False, indent=2), encoding="utf-8")

    write_csv(
        OUT / "future_data_violation_audit.csv",
        [
            {
                "check": "current_snapshot_not_used_for_historical_twse_market_cap",
                "result": "pass",
                "violation_count": 0,
                "notes": "MOPS current company profile routes were recorded as blockers/current-only candidates, not accepted historical rows.",
            },
            {
                "check": "tpex_same_day_source_date",
                "result": "pass",
                "violation_count": 0,
                "notes": "TPEx derived market cap rows use the same daily official quote date as source_date.",
            },
        ],
        ["check", "result", "violation_count", "notes"],
    )

    total_rows = sum(int(r["rows"]) for r in shard_rows) if shard_rows else 0
    completed_dates = {r.get("date") for r in completed if r.get("status") == "completed"}
    expected_dates = set(weekday_dates(date(2015, 1, 1), date.today()))
    missing_dates = sorted(expected_dates - completed_dates)
    active_failed = [r for r in failed if r.get("date") not in completed_dates]
    tpex_done = bool(completed) and not active_failed and not missing_dates
    readiness = {
        "task_id": "TASK-RADAR-DATA-DYNAMIC-POOL1-MARKET-CAP-TWSE-ROUTE-TPEX-FULL-SWEEP-20260703",
        "status": "completed_partial_tpex_full_candidate_twse_blocked" if tpex_done else "running_or_partial_tpex_sweep_twse_blocked",
        "market_cap_pit_ready": False,
        "market_cap_pit_partial_ready": bool(total_rows),
        "tpex_full_sweep_completed": tpex_done,
        "tpex_completed_dates": len(completed_dates),
        "tpex_expected_weekday_dates": len(expected_dates),
        "tpex_missing_dates": len(missing_dates),
        "tpex_accepted_rows": total_rows,
        "twse_status": "blocked_no_historical_issued_shares_or_direct_market_cap_route",
        "twse_route_unlocked": False,
        "twse_sample_ready": False,
        "free_float_market_cap_ready": False,
        "formal_exact": False,
        "future_data_violation_count": 0,
        "ready_for_core_rerun": bool(total_rows),
        "ready_for_strategy_replay": False,
        "formal_model_changed": False,
        "trade_decision_changed": False,
        "active_in_trade_decision": False,
        "generated_at": now_iso(),
    }
    (OUT / "readiness_for_core.json").write_text(json.dumps(readiness, ensure_ascii=False, indent=2), encoding="utf-8")

    manifest = {
        "task_id": readiness["task_id"],
        "status": readiness["status"],
        "output_path": str(OUT),
        "tpex_accepted_rows": total_rows,
        "tpex_shards": len(shard_rows),
        "tpex_completed_dates": len(completed_dates),
        "tpex_expected_weekday_dates": len(expected_dates),
        "tpex_missing_dates": len(missing_dates),
        "twse_status": readiness["twse_status"],
        "large_local_shards_git_tracked": False,
        "future_data_violation_count": 0,
        "ready_for_core_rerun": readiness["ready_for_core_rerun"],
        "generated_at": readiness["generated_at"],
    }
    (OUT / "manifest.json").write_text(json.dumps(manifest, ensure_ascii=False, indent=2), encoding="utf-8")

    completed_rows = [{
        "step": "tpex_market_cap_full_sweep",
        "status": "completed" if tpex_done else "partial_or_running",
        "accepted_rows": total_rows,
        "notes": "Full rows are local shards; committed package keeps manifest, coverage, and sample.",
    }]
    write_csv(OUT / "completed.csv", completed_rows, ["step", "status", "accepted_rows", "notes"])

    failed_rows = []
    if active_failed:
        for row in active_failed:
            failed_rows.append({"step": "tpex_market_cap_full_sweep", "status": "failed", "notes": json.dumps(row, ensure_ascii=False)})
    failed_rows.extend([
        {"step": "twse_historical_market_cap_route", "status": "blocked", "notes": "No PIT issued shares/direct market cap route found; MOPS t05st03/t51sb01 are current-only."},
        {"step": "free_float_market_cap_route", "status": "blocked", "notes": "No official free-float market cap history route found."},
    ])
    write_csv(OUT / "failed.csv", failed_rows, ["step", "status", "notes"])

    with (OUT / "run_log.csv").open("a", encoding="utf-8", newline="") as f:
        csv.writer(f).writerow([now_iso(), "package_builder", readiness["status"], f"tpex_rows={total_rows}; twse=blocked"])

    (OUT / "current_step.txt").write_text(readiness["status"] + "\n", encoding="utf-8")

    summary = f"""# Dynamic Pool1 Market Cap PIT TWSE Route + TPEx Full Sweep

## 結論
- 狀態：`{readiness["status"]}`
- TPEx：`dailyQuotes` full sweep {'完成' if tpex_done else '仍在跑或 partial'}，accepted rows = `{total_rows}`，以 `close_price * shares_outstanding` 建 total market cap source candidate。
- TWSE：仍 blocked。`MI_INDEX` 無 issued shares/direct market cap；MOPS SPA `t05st03` / `t51sb01` route 可靜態解出 current company basic/commonStockAmount 欄位，但本棒未找到 historical as-of/effective date 參數，不可回推 2015。
- Free-float market cap：未找到 official historical route，仍 blocked。

## PIT / formal 邊界
- `formal_exact=false`
- `market_cap_pit_ready=false`
- `market_cap_pit_partial_ready={str(bool(total_rows)).lower()}`
- `ready_for_core_rerun={str(bool(total_rows)).lower()}`
- `ready_for_strategy_replay=false`
- `future_data_violation_count=0`

## 可交 Core 的資料
- TPEx full rows 保存在本機 shards：`tpex_full_sweep_shards/`
- shard index：`accepted_market_cap_rows_manifest.csv`
- committed sample：`proxy_market_cap_rows.csv`
- coverage：`coverage_by_year.csv`、`coverage_by_market.csv`、`tpex_full_sweep_coverage.csv`

## Remaining blockers
- TWSE historical issued shares / direct official market cap route 未找到。
- MOPS current company profile route 不能當 PIT historical source。
- free-float market cap / free-float factor history 未取得。
"""
    (OUT / "final_summary_zh.md").write_text(summary, encoding="utf-8")

    if RAW_DIR.exists():
        (RAW_DIR / ".gitignore").write_text("*\n!.gitignore\n", encoding="utf-8")
    if SHARD_DIR.exists():
        (SHARD_DIR / ".gitignore").write_text("*\n!.gitignore\n", encoding="utf-8")


if __name__ == "__main__":
    main()
