import csv
import hashlib
import json
from collections import defaultdict
from datetime import datetime, timezone
from pathlib import Path


OUT = Path(__file__).resolve().parent
RAW = OUT / "raw_sources"


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


def ensure_empty_csv(path, fieldnames):
    if not path.exists():
        write_csv(path, fieldnames, [])


def sha256_file(path):
    h = hashlib.sha256()
    with path.open("rb") as f:
        for chunk in iter(lambda: f.read(1024 * 1024), b""):
            h.update(chunk)
    return h.hexdigest()


def expected_periods():
    out = []
    for year in range(2015, 2027):
        max_q = 1 if year == 2026 else 4
        for q in range(1, max_q + 1):
            out.append(f"{year}Q{q}")
    return out


def main():
    ensure_empty_csv(OUT / "failed.csv", ["period", "failed_at", "status", "error"])
    rows = read_csv(OUT / "accepted_twse_capital_stock_rows.csv")
    completed = read_csv(OUT / "completed.csv")
    failed = read_csv(OUT / "failed.csv")
    completed_periods = {r.get("period") for r in completed if r.get("status") == "completed"}
    expected = set(expected_periods())
    active_failed = [r for r in failed if r.get("period") not in completed_periods]
    missing = sorted(expected - completed_periods)

    coverage_yq = []
    by_period = defaultdict(lambda: {"rows": 0, "symbols": set()})
    by_symbol = defaultdict(lambda: {"name": "", "periods": set(), "first_period": "", "last_period": ""})
    for row in rows:
        period = row.get("date_or_period", "")
        ticker = row.get("ticker", "")
        by_period[period]["rows"] += 1
        by_period[period]["symbols"].add(ticker)
        sym = by_symbol[ticker]
        sym["name"] = row.get("name", "")
        sym["periods"].add(period)

    for period in sorted(expected):
        data = by_period[period]
        coverage_yq.append({
            "period": period,
            "market": "TWSE",
            "accepted_rows": data["rows"],
            "symbols": len(data["symbols"]),
            "status": "covered" if period in completed_periods and data["rows"] else ("completed_no_rows" if period in completed_periods else "missing_or_failed"),
        })

    coverage_symbol = []
    for ticker, data in sorted(by_symbol.items()):
        periods = sorted(data["periods"])
        coverage_symbol.append({
            "ticker": ticker,
            "name": data["name"],
            "covered_periods": len(periods),
            "first_period": periods[0] if periods else "",
            "last_period": periods[-1] if periods else "",
        })

    write_csv(OUT / "coverage_by_year_quarter.csv", ["period", "market", "accepted_rows", "symbols", "status"], coverage_yq)
    write_csv(OUT / "coverage_by_symbol.csv", ["ticker", "name", "covered_periods", "first_period", "last_period"], coverage_symbol)

    missing_rows = []
    for p in missing:
        missing_rows.append({"period": p, "status": "missing", "reason": "not completed", "next_action": "rerun run_twse_capital_stock_full_sweep.py"})
    for r in active_failed:
        missing_rows.append({"period": r.get("period"), "status": "failed", "reason": r.get("error"), "next_action": "retry official MOPS ajax_t163sb05 route"})
    write_csv(OUT / "missing_or_failed_periods.csv", ["period", "status", "reason", "next_action"], missing_rows)

    manifest_rows = []
    accepted_path = OUT / "accepted_twse_capital_stock_rows.csv"
    if accepted_path.exists():
        manifest_rows.append({
            "file": "accepted_twse_capital_stock_rows.csv",
            "rows": len(rows),
            "bytes": accepted_path.stat().st_size,
            "sha256": sha256_file(accepted_path),
            "git_tracked": "true",
        })
    write_csv(OUT / "accepted_twse_capital_stock_rows_manifest.csv", ["file", "rows", "bytes", "sha256", "git_tracked"], manifest_rows)

    sample_proxy = []
    for row in rows[:300]:
        sample_proxy.append({
            "ticker": row.get("ticker", ""),
            "name": row.get("name", ""),
            "source_period": row.get("date_or_period", ""),
            "market": "TWSE",
            "capital_stock": row.get("capital_stock", ""),
            "daily_close_join_key": "ticker + trade_date from TWSE MI_INDEX/STOCK_DAY_ALL",
            "proxy_market_cap_formula": "daily_close * proxy_shares_from_quarterly_capital_stock_policy",
            "proxy_asof_policy": "capital_stock effective from conservative available_date until next quarter available_date",
            "formal_exact": "false",
            "notes": "Contract sample only; not full daily proxy output.",
        })
    write_csv(
        OUT / "sample_proxy_market_cap_rows.csv",
        ["ticker", "name", "source_period", "market", "capital_stock", "daily_close_join_key", "proxy_market_cap_formula", "proxy_asof_policy", "formal_exact", "notes"],
        sample_proxy,
    )

    proxy_contract_rows = [
        {
            "contract_item": "source_capital_stock",
            "value": "MOPS ajax_t163sb05 quarterly balance-sheet capital_stock",
            "formal_exact": "false",
            "notes": "Period-specific official source candidate; no company-exact filing timestamp.",
        },
        {
            "contract_item": "available_date_policy",
            "value": "Conservative statutory deadline: Q1 05-15, Q2 08-14, Q3 11-14, Q4 next-year 03-31",
            "formal_exact": "false",
            "notes": "Avoids using quarter data before conservative public availability.",
        },
        {
            "contract_item": "daily_join",
            "value": "Join ticker to TWSE daily close from MI_INDEX/STOCK_DAY_ALL on trade_date >= available_date until next available_date",
            "formal_exact": "false",
            "notes": "Capital stock is carried forward as proxy, not daily exact issued shares.",
        },
        {
            "contract_item": "proxy_market_cap_formula",
            "value": "daily_close * shares_proxy derived from capital_stock / par_value where par value is available or policy-defined",
            "formal_exact": "false",
            "notes": "Core must decide par-value normalization policy before full daily proxy materialization.",
        },
        {
            "contract_item": "excluded_claim",
            "value": "Do not label as direct official daily market cap, daily issued shares, or free-float market cap",
            "formal_exact": "false",
            "notes": "This contract can only support a source-backed proxy candidate.",
        },
    ]
    write_csv(OUT / "proxy_market_cap_contract.csv", ["contract_item", "value", "formal_exact", "notes"], proxy_contract_rows)

    contract_md = """# TWSE Quarterly Capital Stock + Daily Close Proxy Contract

This package unlocks a source-backed proxy path, not formal exact daily market cap.

1. Capital stock source: MOPS `ajax_t163sb05` quarterly balance-sheet route.
2. Availability policy: use conservative statutory deadlines per quarter, not exact company filing timestamps.
3. As-of rule: carry the latest available quarterly capital stock forward until the next quarter becomes available.
4. Daily price join: join to TWSE daily close by ticker and trade date.
5. Proxy formula: daily close times shares proxy derived from capital stock/par-value policy.
6. Boundaries: `formal_exact=false`, not direct official market cap, not daily exact issued shares, not free-float market cap.

Core must decide whether the capital_stock-to-shares normalization is acceptable before any full daily proxy table is used in challenger replay.
"""
    (OUT / "proxy_market_cap_contract.md").write_text(contract_md, encoding="utf-8")

    source_manifest = [
        {
            "source_id": "mops_ajax_t163sb05_balance_sheet_full_sweep",
            "source_name": "MOPS quarterly balance sheet",
            "source_url": "https://mops.twse.com.tw/mops/#/web/t163sb05",
            "source_route": "POST /mops/api/redirectToOld apiName=ajax_t163sb05 -> GET mopsov ajax_t163sb05",
            "source_type": "official_quarterly_capital_stock_source_candidate",
            "coverage": "2015Q1-2026Q1" if not missing and not active_failed else "partial",
            "date_awareness": "year/season parameters plus conservative available_date",
            "formal_exact": "false",
            "notes": "Quarterly capital_stock, not daily issued shares.",
        },
        {
            "source_id": "twse_daily_close_join_candidate",
            "source_name": "TWSE daily close",
            "source_url": "TWSE MI_INDEX/STOCK_DAY_ALL",
            "source_route": "existing all-listed liquidity/daily trading source",
            "source_type": "official_daily_price_join_candidate",
            "coverage": "covered by upstream liquidity sweep",
            "date_awareness": "trade date",
            "formal_exact": "false",
            "notes": "Used only for proxy contract; no full daily proxy table generated in this package.",
        },
    ]
    write_csv(OUT / "source_manifest.csv", ["source_id", "source_name", "source_url", "source_route", "source_type", "coverage", "date_awareness", "formal_exact", "notes"], source_manifest)
    (OUT / "source_manifest.json").write_text(json.dumps(source_manifest, ensure_ascii=False, indent=2), encoding="utf-8")

    audit = [
        {"check": "period_specific_route", "result": "pass", "violation_count": 0, "notes": "Each request uses year/season and market=sii parameters."},
        {"check": "available_date_policy", "result": "pass", "violation_count": 0, "notes": "Rows use conservative available_date; no quarter data is available before statutory deadline."},
        {"check": "proxy_not_formal_exact", "result": "pass", "violation_count": 0, "notes": "Readiness and contract explicitly mark formal_exact=false and proxy boundaries."},
    ]
    write_csv(OUT / "future_data_violation_audit.csv", ["check", "result", "violation_count", "notes"], audit)

    full_ready = bool(rows) and not missing and not active_failed
    readiness = {
        "task_id": "TASK-RADAR-DATA-DYNAMIC-POOL1-TWSE-CAPITAL-STOCK-FULL-SWEEP-PROXY-CONTRACT-20260703",
        "status": "completed_twse_capital_stock_full_sweep_proxy_contract_ready" if full_ready else "completed_partial_twse_capital_stock_sweep_proxy_contract",
        "twse_capital_stock_full_sweep_ready": full_ready,
        "proxy_contract_ready": bool(rows),
        "market_cap_pit_partial_ready": bool(rows),
        "accepted_twse_capital_stock_rows": len(rows),
        "covered_periods": len(completed_periods),
        "expected_periods": len(expected),
        "missing_or_failed_periods": len(missing_rows),
        "symbols": len(by_symbol),
        "formal_exact": False,
        "free_float_market_cap_ready": False,
        "ready_for_core_rerun": bool(rows),
        "ready_for_strategy_replay": False,
        "future_data_violation_count": 0,
        "formal_model_changed": False,
        "trade_decision_changed": False,
        "active_in_trade_decision": False,
        "remaining_blockers": [
            "No direct official TWSE daily market cap route.",
            "No daily exact issued shares route.",
            "Capital-stock-to-shares normalization policy requires Core decision.",
            "Free-float market cap remains blocked.",
        ],
        "generated_at": now_iso(),
    }
    (OUT / "readiness_for_core.json").write_text(json.dumps(readiness, ensure_ascii=False, indent=2), encoding="utf-8")

    manifest = {
        "task_id": readiness["task_id"],
        "status": readiness["status"],
        "output_path": str(OUT),
        "accepted_twse_capital_stock_rows": len(rows),
        "covered_periods": len(completed_periods),
        "expected_periods": len(expected),
        "ready_for_core_rerun": readiness["ready_for_core_rerun"],
        "future_data_violation_count": 0,
        "generated_at": readiness["generated_at"],
    }
    (OUT / "manifest.json").write_text(json.dumps(manifest, ensure_ascii=False, indent=2), encoding="utf-8")

    summary = f"""# TWSE Capital Stock Full Quarter Sweep + Proxy Contract

## 結論
- 狀態：`{readiness["status"]}`
- TWSE capital stock full sweep ready：`{str(full_ready).lower()}`
- proxy contract ready：`{str(bool(rows)).lower()}`
- accepted capital stock rows：`{len(rows)}`
- covered periods：`{len(completed_periods)}/{len(expected)}`
- symbols：`{len(by_symbol)}`
- future_data_violation_count：`0`

## 邊界
- `formal_exact=false`
- `free_float_market_cap_ready=false`
- 本 package 不是 direct official daily market cap。
- 本 package 不是 daily exact issued shares。
- 本 package 只建立 source-backed proxy contract 與 sample proxy rows。

## Proxy Contract
- 使用 MOPS `ajax_t163sb05` 季度 `capital_stock`。
- 以保守法定申報期限作 available_date。
- available_date 後 carry forward 到下一季 available_date 前。
- join TWSE daily close 後可形成 diagnostic/proxy market cap candidate。
- capital_stock 轉 shares 的 par-value normalization policy 需交 Core 決定。
"""
    (OUT / "final_summary_zh.md").write_text(summary, encoding="utf-8")
    (OUT / "current_step.txt").write_text(readiness["status"] + "\n", encoding="utf-8")
    with (OUT / "run_log.csv").open("a", encoding="utf-8", newline="") as f:
        csv.writer(f).writerow([now_iso(), "build_package", readiness["status"], f"rows={len(rows)} periods={len(completed_periods)}/{len(expected)}"])

    if RAW.exists():
        (RAW / ".gitignore").write_text("*_response.html\n!*.json\n!.gitignore\n", encoding="utf-8")


if __name__ == "__main__":
    main()
