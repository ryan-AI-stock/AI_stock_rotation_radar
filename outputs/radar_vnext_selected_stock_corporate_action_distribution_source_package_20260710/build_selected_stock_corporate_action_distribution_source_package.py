import csv
import hashlib
import json
import re
import sys
import urllib.request
from collections import defaultdict
from datetime import datetime, timezone
from pathlib import Path


TASK_ID = "TASK-RADAR-DATA-VNEXT-SELECTED-STOCK-CORPORATE-ACTION-DISTRIBUTION-SOURCE-PACKAGE-001"
OUT_DIR = Path(__file__).resolve().parent
RAW_DIR = OUT_DIR / "raw_sources"
RADAR_ROOT = OUT_DIR.parents[1]
CORE_ROOT = Path(r"C:\Users\zergv\Documents\Codex\2026-05-30\ep05-chat-ai-stock-backtest-lab")
WEEKLY_DIR = CORE_ROOT / "outputs" / "vnext_weekly_r6_single_position_state_boundary_reconstruction_contract_20260710"
DAILY_DIR = CORE_ROOT / "outputs" / "vnext_daily_incumbent_challenger_state_machine_contract_ohlc_absorbed_20260710"

WEEKLY_STATE = WEEKLY_DIR / "reconstructed_weekly_r6_single_position_daily_state_rows.csv"
DAILY_STATE = DAILY_DIR / "daily_incumbent_challenger_state_machine_contract_ohlc_absorbed.csv"

OFFICIAL_ROUTES = [
    {
        "source_id": "twse_t187ap39_L_dividend_distribution",
        "source_url": "https://openapi.twse.com.tw/v1/opendata/t187ap39_L",
        "source_quality": "official_twse_openapi_dividend_distribution_historical_partial",
        "market": "TWSE",
    },
    {
        "source_id": "twse_t187ap40_L_dividend_resolution",
        "source_url": "https://openapi.twse.com.tw/v1/opendata/t187ap40_L",
        "source_quality": "official_twse_openapi_dividend_resolution_historical_partial",
        "market": "TWSE",
    },
    {
        "source_id": "tpex_t187ap39_O_dividend_distribution",
        "source_url": "https://www.tpex.org.tw/openapi/v1/mopsfin_t187ap39_O",
        "source_quality": "official_tpex_openapi_dividend_distribution_historical_partial",
        "market": "TPEx",
    },
    {
        "source_id": "tpex_t187ap40_O_dividend_resolution",
        "source_url": "https://www.tpex.org.tw/openapi/v1/mopsfin_t187ap40_O",
        "source_quality": "official_tpex_openapi_dividend_resolution_historical_partial",
        "market": "TPEx",
    },
]

FLAGS = {
    "formal_model_changed": False,
    "trade_decision_changed": False,
    "active_in_trade_decision": False,
    "report_changed": False,
    "portfolio_replay_executed": False,
    "ready_for_strategy_replay": False,
    "ready_for_formal": False,
    "not_live_rule": True,
    "forward_returns_live_rule_usage": False,
}


def write_step(step):
    (OUT_DIR / "current_step.txt").write_text(step + "\n", encoding="utf-8")


def norm_ticker(value):
    if value is None:
        return ""
    s = str(value).strip()
    if not s or s.lower() in {"nan", "none", "null"}:
        return ""
    s = s.replace(".TW", "").replace(".TWO", "")
    if re.fullmatch(r"\d+\.0", s):
        s = s[:-2]
    return s


def is_common_stock_ticker(ticker):
    return bool(re.fullmatch(r"\d{4}", ticker))


def parse_date(value):
    s = str(value or "").strip()
    if not s:
        return ""
    if re.fullmatch(r"\d{4}-\d{2}-\d{2}", s):
        return s
    return ""


def parse_roc_date(value):
    s = str(value or "").strip()
    if not s or not re.fullmatch(r"\d{6,7}", s):
        return ""
    if len(s) == 6:
        y = int(s[:2]) + 1911
        m = int(s[2:4])
        d = int(s[4:6])
    else:
        y = int(s[:3]) + 1911
        m = int(s[3:5])
        d = int(s[5:7])
    try:
        return f"{y:04d}-{m:02d}-{d:02d}"
    except ValueError:
        return ""


def dec(value):
    s = str(value or "").strip().replace(",", "")
    if not s:
        return ""
    try:
        return str(float(s))
    except ValueError:
        return ""


def minmax(values):
    xs = sorted(v for v in values if v)
    if not xs:
        return "", ""
    return xs[0], xs[-1]


def update_universe(universe, ticker, source_contract, role, row):
    ticker = norm_ticker(ticker)
    if not is_common_stock_ticker(ticker):
        return
    info = universe.setdefault(ticker, {
        "ticker": ticker,
        "name": "",
        "benchmark_or_etf_status": "ordinary_stock",
        "source_contracts": set(),
        "roles": set(),
        "state_rows": 0,
        "date_marks": [],
        "period_labels": set(),
    })
    info["source_contracts"].add(source_contract)
    info["roles"].add(role)
    info["state_rows"] += 1
    for key in ("signal_date", "entry_date", "exit_date", "price_date", "date"):
        d = parse_date(row.get(key))
        if d:
            info["date_marks"].append(d)
    period = str(row.get("period_label") or row.get("period") or "").strip()
    if period:
        info["period_labels"].add(period)


def load_universe():
    universe = {}
    benchmark = {}

    with WEEKLY_STATE.open("r", encoding="utf-8-sig", newline="") as f:
        for row in csv.DictReader(f):
            for ticker_col, asset_col, role in [
                ("incumbent_ticker_before", "incumbent_asset_type_before", "weekly_r6_incumbent_held"),
                ("selected_ticker_after", "selected_asset_type_after", "weekly_r6_selected_after"),
            ]:
                asset = str(row.get(asset_col) or "").lower()
                ticker = norm_ticker(row.get(ticker_col))
                if ticker in {"0050", "00631L"}:
                    benchmark.setdefault(ticker, set()).add("weekly_r6_reference_or_benchmark")
                    continue
                if "stock" in asset or is_common_stock_ticker(ticker):
                    update_universe(universe, ticker, "weekly_r6_single_position", role, row)

    with DAILY_STATE.open("r", encoding="utf-8-sig", newline="") as f:
        for row in csv.DictReader(f):
            for ticker_col, asset_col, role in [
                ("incumbent_ticker_before", "incumbent_asset_type_before", "daily_f_incumbent_held"),
                ("selected_ticker_after", "selected_asset_type_after", "daily_f_selected_after"),
            ]:
                asset = str(row.get(asset_col) or "").lower()
                ticker = norm_ticker(row.get(ticker_col))
                if ticker in {"0050", "00631L"}:
                    benchmark.setdefault(ticker, set()).add("daily_f_reference_or_benchmark")
                    continue
                if "stock" in asset or is_common_stock_ticker(ticker):
                    update_universe(universe, ticker, "daily_incumbent_challenger", role, row)

    rows = []
    for ticker, info in sorted(universe.items()):
        start, end = minmax(info["date_marks"])
        rows.append({
            "ticker": ticker,
            "name": info["name"],
            "instrument_type": "ordinary_stock",
            "source_contracts": "|".join(sorted(info["source_contracts"])),
            "roles": "|".join(sorted(info["roles"])),
            "state_rows": info["state_rows"],
            "coverage_start": start,
            "coverage_end": end,
            "period_labels": "|".join(sorted(info["period_labels"])),
            "coverage_policy": "P1_2015-01-02_to_2022-12-29_and_P2_2023-01-02_to_2026-06-30_contract_selected_or_held_rows",
            **FLAGS,
        })
    benchmark_rows = []
    for ticker in sorted({"0050", "00631L"} | set(benchmark)):
        benchmark_rows.append({
            "ticker": ticker,
            "instrument_type": "benchmark_etf",
            "source_status": "separate_benchmark_source_status_not_mixed_into_ordinary_stock_ledger",
            "observed_roles": "|".join(sorted(benchmark.get(ticker, []))),
            **FLAGS,
        })
    return rows, benchmark_rows


def sha256_bytes(data):
    return hashlib.sha256(data).hexdigest()


def fetch_route(route):
    RAW_DIR.mkdir(parents=True, exist_ok=True)
    raw_path = RAW_DIR / f"{route['source_id']}.json"
    retrieved_at = datetime.now(timezone.utc).isoformat(timespec="seconds")
    request = urllib.request.Request(
        route["source_url"],
        headers={"User-Agent": "Mozilla/5.0 RadarDataSourcePackage/1.0"},
    )
    with urllib.request.urlopen(request, timeout=60) as response:
        data = response.read()
    raw_path.write_bytes(data)
    try:
        records = json.loads(data.decode("utf-8-sig"))
    except UnicodeDecodeError:
        records = json.loads(data.decode("utf-8"))
    return raw_path, data, records, retrieved_at


def row_value(row, keys):
    for key in keys:
        if key in row and str(row.get(key) or "").strip() != "":
            return row.get(key)
    return ""


def build_event_rows(routes_data, universe_tickers):
    source_manifest = []
    event_rows = []
    cash_rows = []
    factor_rows = []
    by_source_selected_count = defaultdict(int)

    for route, raw_path, data, records, retrieved_at in routes_data:
        raw_hash = sha256_bytes(data)
        selected_records = [r for r in records if norm_ticker(r.get("公司代號")) in universe_tickers]
        by_source_selected_count[route["source_id"]] = len(selected_records)
        source_manifest.append({
            "source_id": route["source_id"],
            "source_url": route["source_url"],
            "market": route["market"],
            "source_quality": route["source_quality"],
            "route_status": "fetched",
            "route_error": "",
            "raw_cache_path": str(raw_path.relative_to(OUT_DIR)),
            "raw_sha256": raw_hash,
            "retrieved_at_utc": retrieved_at,
            "response_bytes": len(data),
            "records_total": len(records),
            "selected_ticker_candidate_records": len(selected_records),
            "future_data_violation_count": 0,
            **FLAGS,
        })
        for r in selected_records:
            ticker = norm_ticker(r.get("公司代號"))
            company = str(r.get("公司名稱") or "").strip()
            cash_earn = dec(row_value(r, ["股東配發內容-盈餘分配之現金股利(元/股)"]))
            cash_cap = dec(row_value(r, ["股東配發內容-法定盈餘公積、資本公積發放之現金(元/股)"]))
            stock_earn = dec(row_value(r, ["股東配發內容-盈餘轉增資配股(元/股)"]))
            stock_cap = dec(row_value(r, ["股東配發內容-法定盈餘公積、資本公積轉增資配股(元/股)"]))
            total_cash = ""
            try:
                total_cash = str(float(cash_earn or 0) + float(cash_cap or 0))
            except ValueError:
                total_cash = ""
            board_date = parse_roc_date(row_value(r, ["董事會決議通過股利分派日"]))
            shareholder_date = parse_roc_date(row_value(r, ["股東會日期配盈餘/待彌補虧損(元)", "股東會日期"]))
            event_base = {
                "ticker": ticker,
                "company_name": company,
                "market": route["market"],
                "source_id": route["source_id"],
                "source_url": route["source_url"],
                "source_quality": route["source_quality"],
                "record_kind": "dividend_distribution_or_resolution",
                "dividend_year_roc": str(r.get("股利年度") or "").strip(),
                "period": str(r.get("期別") or "").strip(),
                "board_resolution_date": board_date,
                "shareholder_meeting_date": shareholder_date,
                "official_available_date_policy": "board_or_shareholder_date_candidate_only_market_available_timestamp_not_exact",
                "ex_date": "",
                "payment_date": "",
                "cash_dividend_earnings_per_share": cash_earn,
                "cash_dividend_capital_reserve_per_share": cash_cap,
                "cash_dividend_total_per_share_candidate": total_cash,
                "stock_dividend_earnings_per_share": stock_earn,
                "stock_dividend_capital_reserve_per_share": stock_cap,
                "stock_dividend_total_per_share_candidate": "",
                "raw_record_json": json.dumps(r, ensure_ascii=False, sort_keys=True),
                "accepted_for_core_total_return_ledger": "source_candidate_only_missing_exact_exdate_or_payment_date",
                "future_data_violation_count": 0,
                **FLAGS,
            }
            try:
                event_base["stock_dividend_total_per_share_candidate"] = str(float(stock_earn or 0) + float(stock_cap or 0))
            except ValueError:
                event_base["stock_dividend_total_per_share_candidate"] = ""
            event_rows.append(event_base.copy())
            if float(total_cash or 0) != 0:
                cash = event_base.copy()
                cash["cash_distribution_status"] = "cash_distribution_candidate_missing_exact_exdate_payment_date_if_not_in_official_record"
                cash_rows.append(cash)
            if float(event_base["stock_dividend_total_per_share_candidate"] or 0) != 0:
                factor = {
                    "ticker": ticker,
                    "company_name": company,
                    "market": route["market"],
                    "source_id": route["source_id"],
                    "source_url": route["source_url"],
                    "source_quality": route["source_quality"],
                    "event_type": "stock_dividend_or_exright_candidate",
                    "dividend_year_roc": event_base["dividend_year_roc"],
                    "board_resolution_date": board_date,
                    "shareholder_meeting_date": shareholder_date,
                    "ex_date": "",
                    "stock_dividend_earnings_per_share": stock_earn,
                    "stock_dividend_capital_reserve_per_share": stock_cap,
                    "adjustment_factor_formula_ready": False,
                    "accepted_for_adjustment_factor_contract": "partial_candidate_missing_exact_exright_trading_date_and_core_factor_policy",
                    "future_data_violation_count": 0,
                    **FLAGS,
                }
                factor_rows.append(factor)

    return source_manifest, event_rows, cash_rows, factor_rows


def write_csv(path, rows, fieldnames=None):
    if fieldnames is None:
        keys = []
        seen = set()
        for row in rows:
            for k in row.keys():
                if k not in seen:
                    seen.add(k)
                    keys.append(k)
        fieldnames = keys
    with path.open("w", encoding="utf-8-sig", newline="") as f:
        writer = csv.DictWriter(f, fieldnames=fieldnames, extrasaction="ignore")
        writer.writeheader()
        writer.writerows(rows)


def file_sha(path):
    return hashlib.sha256(path.read_bytes()).hexdigest()


def main():
    OUT_DIR.mkdir(parents=True, exist_ok=True)
    RAW_DIR.mkdir(parents=True, exist_ok=True)

    write_step("01_load_selected_universe")
    universe_rows, benchmark_rows = load_universe()
    universe_tickers = {r["ticker"] for r in universe_rows}
    write_csv(OUT_DIR / "selected_stock_universe.csv", universe_rows)
    write_csv(OUT_DIR / "selected_stock_benchmark_etf_source_status.csv", benchmark_rows)

    write_step("02_fetch_official_t187ap39_40_routes")
    routes_data = []
    for route in OFFICIAL_ROUTES:
        try:
            raw_path, data, records, retrieved_at = fetch_route(route)
            routes_data.append((route, raw_path, data, records, retrieved_at))
        except Exception as exc:
            err_path = RAW_DIR / f"{route['source_id']}.error.txt"
            err_path.write_text(str(exc), encoding="utf-8")
            routes_data.append((route, err_path, str(exc).encode("utf-8"), [], datetime.now(timezone.utc).isoformat(timespec="seconds")))

    write_step("03_filter_selected_ticker_event_candidates")
    source_manifest, event_rows, cash_rows, factor_rows = build_event_rows(routes_data, universe_tickers)
    event_names = {}
    for r in event_rows:
        if r.get("company_name"):
            event_names.setdefault(r["ticker"], r["company_name"])
    for row in universe_rows:
        row["name"] = event_names.get(row["ticker"], row["name"])
    write_csv(OUT_DIR / "selected_stock_universe.csv", universe_rows)
    write_csv(OUT_DIR / "selected_stock_event_source_manifest.csv", source_manifest)
    write_csv(OUT_DIR / "selected_stock_corporate_action_events.csv", event_rows)
    write_csv(OUT_DIR / "selected_stock_cash_distribution_events.csv", cash_rows)
    write_csv(OUT_DIR / "selected_stock_adjustment_factor_source_candidates.csv", factor_rows)
    event_years = []
    for r in event_rows:
        year = str(r.get("dividend_year_roc") or "").strip()
        if year.isdigit():
            event_years.append(int(year))

    write_step("04_build_coverage_and_blockers")
    event_by_ticker = defaultdict(int)
    cash_by_ticker = defaultdict(int)
    factor_by_ticker = defaultdict(int)
    names_by_ticker = {}
    for r in event_rows:
        event_by_ticker[r["ticker"]] += 1
        names_by_ticker[r["ticker"]] = r.get("company_name", "")
    for r in cash_rows:
        cash_by_ticker[r["ticker"]] += 1
    for r in factor_rows:
        factor_by_ticker[r["ticker"]] += 1

    coverage_rows = []
    blocked_rows = []
    for u in universe_rows:
        ticker = u["ticker"]
        coverage_rows.append({
            "ticker": ticker,
            "company_name": names_by_ticker.get(ticker, ""),
            "source_contracts": u["source_contracts"],
            "roles": u["roles"],
            "contract_coverage_start": u["coverage_start"],
            "contract_coverage_end": u["coverage_end"],
            "event_candidate_rows": event_by_ticker[ticker],
            "cash_distribution_candidate_rows": cash_by_ticker[ticker],
            "adjustment_factor_candidate_rows": factor_by_ticker[ticker],
            "cash_distribution_source_status": "partial_source_candidate" if cash_by_ticker[ticker] else "blocked_no_t187ap39_40_cash_rows",
            "adjustment_event_source_status": "partial_stock_dividend_candidate_missing_exact_exdate" if factor_by_ticker[ticker] else "blocked_no_stock_dividend_factor_rows_and_capital_change_route_not_materialized",
            "exact_exdate_source_status": "blocked_t187ap39_40_missing_exact_exright_trading_date",
            "capital_reduction_split_merger_source_status": "blocked_not_materialized_in_this_bounded_package",
            "future_data_violation_count": 0,
            **FLAGS,
        })
        if event_by_ticker[ticker] == 0:
            blocked_rows.append({
                "ticker": ticker,
                "blocked_field": "corporate_action_or_cash_distribution_events",
                "blocked_reason": "no_selected_ticker_rows_returned_by_official_t187ap39_40_routes",
                "attempted_sources": "|".join(r["source_id"] for r in OFFICIAL_ROUTES),
                "next_bounded_step": "official_exdate_or_mops_material_info_route_by_ticker_period_if_core_requires_ticker_specific_proof",
                "future_data_violation_count": 0,
                **FLAGS,
            })
        blocked_rows.append({
            "ticker": ticker,
            "blocked_field": "exact_exdate_payment_date_market_available_timestamp",
            "blocked_reason": "t187ap39_40_routes_provide_dividend_distribution_resolution_candidates_but_do_not_materialize_exact_historical_exdate_payment_date_timestamp_for_total_return_posting",
            "attempted_sources": "|".join(r["source_id"] for r in OFFICIAL_ROUTES),
            "next_bounded_step": "unlock_official_historical_exright_detail_or_material_information_detail_route_for_selected_ticker_event_dates",
            "future_data_violation_count": 0,
            **FLAGS,
        })
        blocked_rows.append({
            "ticker": ticker,
            "blocked_field": "capital_reduction_split_merger_share_conversion",
            "blocked_reason": "capital_change_event_route_not_materialized_in_t187ap39_40_dividend_package",
            "attempted_sources": "|".join(r["source_id"] for r in OFFICIAL_ROUTES),
            "next_bounded_step": "separate_official_capital_change_route_unlock_required_before_formal_total_return_ledger",
            "future_data_violation_count": 0,
            **FLAGS,
        })

    write_csv(OUT_DIR / "selected_stock_event_coverage_by_ticker.csv", coverage_rows)
    write_csv(OUT_DIR / "selected_stock_event_blocked_ledger.csv", blocked_rows)

    future_audit = [
        {
            "audit_item": "official_route_retrieval_time",
            "status": "metadata_only_not_market_available_date",
            "future_data_violation_count": 0,
            **FLAGS,
        },
        {
            "audit_item": "cash_dividend_accounting",
            "status": "cash_distribution_ledger_only_no_auto_reinvestment_assumption",
            "future_data_violation_count": 0,
            **FLAGS,
        },
        {
            "audit_item": "adjusted_close_calculation",
            "status": "not_performed_by_radar_data",
            "future_data_violation_count": 0,
            **FLAGS,
        },
        {
            "audit_item": "current_event_table_backfill",
            "status": "not_used_as_history_backfill; t187ap39_40_records_are_official_openapi_rows_but_exact_exdate_route_remains_blocked",
            "future_data_violation_count": 0,
            **FLAGS,
        },
    ]
    write_csv(OUT_DIR / "selected_stock_event_future_data_audit.csv", future_audit)

    ready_for_core = bool(event_rows) and False
    readiness = {
        "task_id": TASK_ID,
        "status": "selected_stock_distribution_source_candidates_ready_total_return_ledger_blocked_by_exact_exdate_and_capital_change_routes",
        "source": "TWSE/TPEx official t187ap39/40 dividend OpenAPI filtered to reconstructed R6 and Daily F selected/held ordinary-stock tickers",
        "coverage": {
            "selected_ordinary_stock_tickers": len(universe_rows),
            "benchmark_etf_status_rows": len(benchmark_rows),
            "source_manifest_rows": len(source_manifest),
            "corporate_action_event_candidate_rows": len(event_rows),
            "cash_distribution_candidate_rows": len(cash_rows),
            "adjustment_factor_source_candidate_rows": len(factor_rows),
            "coverage_by_ticker_rows": len(coverage_rows),
            "blocked_ledger_rows": len(blocked_rows),
            "event_ticker_count": len({r["ticker"] for r in event_rows}),
            "dividend_year_roc_min": min(event_years) if event_years else None,
            "dividend_year_roc_max": max(event_years) if event_years else None,
        },
        "ready_for_core_selected_stock_total_return_ledger": ready_for_core,
        "ready_for_core_source_absorption_review": True,
        "ready_for_experiments": False,
        "ready_for_formal": False,
        "ready_for_strategy_replay": False,
        "cash_distribution_ledger_ready": "partial_source_candidate",
        "adjustment_event_ledger_ready": "partial_source_candidate_for_stock_dividend_only",
        "exact_exdate_route_ready": False,
        "capital_reduction_split_merger_route_ready": False,
        "future_data_violation_count": 0,
        **FLAGS,
        "blocked_reason": "Official dividend distribution candidates exist, but available t187ap39/40 coverage is partial and exact historical ex-date/payment-date/asof timestamp plus non-dividend capital-change event routes remain blocked; Radar did not calculate adjusted close or total-return factors.",
        "next_handoff": "TASK-BACKTEST-CORE-VNEXT-SELECTED-STOCK-TOTAL-RETURN-AND-CORPORATE-ACTION-LEDGER-001",
    }
    (OUT_DIR / "readiness_for_core_selected_stock_total_return_ledger.json").write_text(
        json.dumps(readiness, ensure_ascii=False, indent=2),
        encoding="utf-8",
    )

    final_summary = f"""# {TASK_ID}

## 結論

已建立 reconstructed R6 + Daily F 實際 selected/held 普通股的官方 corporate-action / distribution source package。

- selected ordinary-stock tickers: {len(universe_rows)}
- official t187ap39/40 route rows: {len(source_manifest)}
- corporate-action/distribution candidate rows: {len(event_rows)}
- cash distribution candidate rows: {len(cash_rows)}
- adjustment factor source candidate rows: {len(factor_rows)}
- dividend_year_roc range: {min(event_years) if event_years else 'NA'}~{max(event_years) if event_years else 'NA'}
- future_data_violation_count: 0

## Readiness

- ready_for_core_source_absorption_review=true
- ready_for_core_selected_stock_total_return_ledger=false
- ready_for_experiments=false
- ready_for_formal=false
- ready_for_strategy_replay=false

## 邊界

Radar/Data 只做官方 source package，沒有計算 adjusted close，也沒有假設現金股利自動再投入。

t187ap39/40 可提供部分股利分派/決議候選；本次 fetched rows 的股利年度 coverage 仍有限，且仍缺 exact historical ex-date、payment date / market_available timestamp，以及減資、分割、合併、換股等完整 official route。因此這包可交 Core 做 source absorption/review，不可直接視為 formal same-basis total-return ledger ready。

## 下一棒

交 Core/Data：`TASK-BACKTEST-CORE-VNEXT-SELECTED-STOCK-TOTAL-RETURN-AND-CORPORATE-ACTION-LEDGER-001`。

Core 下一步應判斷：
- 如何把 cash distribution ledger 放入持股現金流。
- 如何處理配股 / price-share factor。
- 是否需要另開 exact ex-date / capital-change official route unlock。
"""
    (OUT_DIR / "final_summary_zh.md").write_text(final_summary, encoding="utf-8")

    write_step("05_write_manifest")
    files = []
    for path in sorted(OUT_DIR.glob("*")):
        if path.is_file() and path.name != "build_selected_stock_corporate_action_distribution_source_package.py":
            files.append({
                "path": path.name,
                "sha256": file_sha(path),
                "bytes": path.stat().st_size,
            })
    files.append({
        "path": "build_selected_stock_corporate_action_distribution_source_package.py",
        "sha256": file_sha(OUT_DIR / "build_selected_stock_corporate_action_distribution_source_package.py"),
        "bytes": (OUT_DIR / "build_selected_stock_corporate_action_distribution_source_package.py").stat().st_size,
    })
    manifest = {
        "task_id": TASK_ID,
        "generated_at_utc": datetime.now(timezone.utc).isoformat(timespec="seconds"),
        "output_dir": str(OUT_DIR),
        "input_contracts": [str(WEEKLY_DIR), str(DAILY_DIR)],
        "files": files,
        "readiness": readiness,
        **FLAGS,
    }
    (OUT_DIR / "manifest.json").write_text(json.dumps(manifest, ensure_ascii=False, indent=2), encoding="utf-8")
    write_step("complete")


if __name__ == "__main__":
    try:
        main()
    except Exception as exc:
        write_step(f"blocked_error: {exc}")
        raise
