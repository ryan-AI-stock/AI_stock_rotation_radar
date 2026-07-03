from __future__ import annotations

import csv
import json
from datetime import datetime
from pathlib import Path
from typing import Any


REPO_ROOT = Path(__file__).resolve().parents[2]
OUTPUT_DIR = Path(__file__).resolve().parent
CORE_OUTPUT = Path(
    r"C:\Users\zergv\Documents\Codex\2026-05-30\ep05-chat-ai-stock-backtest-lab\outputs\dynamic_pool1_pit_readiness_contract_20260703"
)
TASK_ID = "TASK-RADAR-DATA-DYNAMIC-POOL1-PIT-SOURCE-ACQUISITION-20260703"


def read_csv(path: str | Path) -> list[dict[str, str]]:
    path = Path(path)
    if not path.exists():
        return []
    with path.open("r", encoding="utf-8-sig", newline="") as handle:
        return list(csv.DictReader(handle))


def read_json(path: str | Path) -> dict[str, Any]:
    path = Path(path)
    if not path.exists():
        return {}
    return json.loads(path.read_text(encoding="utf-8"))


def write_csv(path: str | Path, rows: list[dict[str, Any]], fieldnames: list[str]) -> None:
    path = Path(path)
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("w", encoding="utf-8-sig", newline="") as handle:
        writer = csv.DictWriter(handle, fieldnames=fieldnames, extrasaction="ignore")
        writer.writeheader()
        writer.writerows(rows)


def write_json(path: str | Path, payload: dict[str, Any]) -> None:
    Path(path).write_text(json.dumps(payload, ensure_ascii=False, indent=2), encoding="utf-8")


def csv_stats(path: str | Path, date_columns: tuple[str, ...] = ("date", "source_date", "release_date", "available_date", "effective_date", "report_date")) -> dict[str, Any]:
    path = Path(path)
    rows = read_csv(path)
    columns = list(rows[0].keys()) if rows else []
    dates: list[str] = []
    for row in rows:
        for column in date_columns:
            value = row.get(column, "")
            if len(value) >= 10 and value[:4].isdigit():
                dates.append(value[:10])
                break
            if len(value) == 8 and value.isdigit():
                dates.append(f"{value[:4]}-{value[4:6]}-{value[6:8]}")
                break
    symbols = {row.get("symbol", "") for row in rows if row.get("symbol", "")}
    return {
        "exists": path.exists(),
        "row_count": len(rows),
        "columns": columns,
        "min_date": min(dates) if dates else "",
        "max_date": max(dates) if dates else "",
        "symbol_count": len(symbols),
    }


def year_coverage_from_stats(stats: dict[str, Any], start_year: int = 2015, end_year: int = 2026) -> dict[str, str]:
    min_date = stats.get("min_date", "")
    max_date = stats.get("max_date", "")
    result: dict[str, str] = {}
    for year in range(start_year, end_year + 1):
        y = str(year)
        if min_date and max_date and min_date[:4] <= y <= max_date[:4]:
            result[y] = "covered_or_partial"
        else:
            result[y] = "missing"
    return result


def build_inventory() -> list[dict[str, Any]]:
    official_turnover = REPO_ROOT / "data/formal_sources/official_turnover_20211201_20231231.csv"
    monthly_revenue = REPO_ROOT / "data/formal_sources/point_in_time_fundamentals_monthly_revenue_20211201_20231231.csv"
    backtest_factor = REPO_ROOT / "data/formal_sources/backtest_factor_2024_2026/readiness.json"
    sector_contract = REPO_ROOT / "outputs/radar_2015_2021_sector_mainline_pit_contract_20260703/readiness.json"
    pcf_daily = REPO_ROOT / "outputs/radar_tw50_0050_pcf_daily_full_range_pit_candidate_201411_202312_20260629/validated_daily_pcf_candidate.csv"
    missing_price = REPO_ROOT / "outputs/radar_0050_pit_missing_price_coverage_4tickers_20260629/coverage_by_ticker.csv"

    official_turnover_stats = csv_stats(official_turnover)
    monthly_revenue_stats = csv_stats(monthly_revenue, ("available_date", "source_date", "date"))
    pcf_stats = csv_stats(pcf_daily, ("holdings_date", "source_date", "date"))
    missing_price_stats = csv_stats(missing_price, ("first_date", "last_date"))
    factor_ready = read_json(backtest_factor)
    sector_ready = read_json(sector_contract)

    rows: list[dict[str, Any]] = [
        {
            "dataset": "all_listed_liquid_universe_pit_daily",
            "source_id": "twse_tpex_full_market_daily_candidate",
            "source_name": "TWSE/TPEx daily full-market trading files",
            "source_path_or_url": "TWSE/TPEx official daily trading APIs/files",
            "source_type": "official_candidate",
            "official_proxy_manual": "official",
            "coverage_start": "2015-01-01",
            "coverage_end": "2026-latest",
            "row_count": "",
            "symbol_count": "",
            "source_date_available": "true",
            "release_date_available": "not_required_for_daily_trade_file_if_trade_date_is_source_date",
            "effective_date_available": "true",
            "formal_ready": "false",
            "partial_ready": "false",
            "diagnostic_only": "false",
            "decision": "blocked_until_acquired",
            "next_programmatic_source": "Bounded downloader for TWSE MI_INDEX/STOCK_DAY/all-market CSV and TPEx daily quotes; add listing/delisting/suspension metadata.",
            "notes": "Needed to build all-listed liquid tradable universe; current generated universe cannot be backfilled.",
        },
        {
            "dataset": "monthly_revenue_pit",
            "source_id": "radar_mops_monthly_revenue_v1",
            "source_name": "MOPS monthly revenue PIT v1",
            "source_path_or_url": "data/formal_sources/point_in_time_fundamentals_monthly_revenue_20211201_20231231.csv",
            "source_type": "point_in_time_limited",
            "official_proxy_manual": "official",
            "coverage_start": monthly_revenue_stats["min_date"],
            "coverage_end": monthly_revenue_stats["max_date"],
            "row_count": monthly_revenue_stats["row_count"],
            "symbol_count": monthly_revenue_stats["symbol_count"],
            "source_date_available": "true",
            "release_date_available": "true",
            "effective_date_available": "true",
            "formal_ready": "false",
            "partial_ready": "true",
            "diagnostic_only": "false",
            "decision": "accepted_partial_existing_universe",
            "next_programmatic_source": "Extend existing MOPS monthly revenue fetcher to all-listed universe and 2015-latest with available_date/release_date.",
            "notes": "Good source pattern, but current file covers formal universe 2021-12~2023-12 only, not all-listed Dynamic Pool1.",
        },
        {
            "dataset": "quarterly_fundamentals_pit",
            "source_id": "mops_quarterly_financials_xbrl_candidate",
            "source_name": "MOPS quarterly financial statements / XBRL candidate",
            "source_path_or_url": "MOPS financial statements, XBRL, financial summary endpoints",
            "source_type": "official_candidate",
            "official_proxy_manual": "official",
            "coverage_start": "2015-01-01",
            "coverage_end": "2026-latest",
            "row_count": "",
            "symbol_count": "",
            "source_date_available": "unknown_until_acquired",
            "release_date_available": "required_not_acquired",
            "effective_date_available": "required_not_acquired",
            "formal_ready": "false",
            "partial_ready": "false",
            "diagnostic_only": "false",
            "decision": "blocked",
            "next_programmatic_source": "Probe MOPS/XBRL financial statement endpoints by company/quarter and capture announcement or filing date.",
            "notes": "Backtest factor package still marks valuation/fundamentals PIT blocked.",
        },
        {
            "dataset": "historical_market_cap_pit",
            "source_id": "official_turnover_plus_price_candidate",
            "source_name": "market cap from date-aware shares outstanding + close price candidate",
            "source_path_or_url": "Need shares outstanding PIT source plus price history",
            "source_type": "derived_candidate",
            "official_proxy_manual": "proxy_until_shares_source_accepted",
            "coverage_start": "",
            "coverage_end": "",
            "row_count": "",
            "symbol_count": "",
            "source_date_available": "required_not_acquired",
            "release_date_available": "required_not_acquired",
            "effective_date_available": "required_not_acquired",
            "formal_ready": "false",
            "partial_ready": "false",
            "diagnostic_only": "true",
            "decision": "blocked_current_snapshot_only",
            "next_programmatic_source": "Acquire capital/share outstanding PIT from MOPS/TWSE capital changes, then combine with date-aware prices.",
            "notes": "Current market cap or refreshed stock metrics cannot be used as historical PIT.",
        },
        {
            "dataset": "sector_membership_pit",
            "source_id": "radar_2015_2021_sector_mainline_contract",
            "source_name": "2015-2021 sector/mainline PIT contract package",
            "source_path_or_url": "outputs/radar_2015_2021_sector_mainline_pit_contract_20260703",
            "source_type": "contract_blocked",
            "official_proxy_manual": "manual_evidence_candidate",
            "coverage_start": "2015-01-01",
            "coverage_end": "2021-12-31",
            "row_count": sector_ready.get("sector_membership_pit_panel_rows", 0),
            "symbol_count": "",
            "source_date_available": "true_for_partial_rows_only",
            "release_date_available": "not_required",
            "effective_date_available": "true_for_partial_rows_only",
            "formal_ready": "false",
            "partial_ready": "false",
            "diagnostic_only": "false",
            "decision": "blocked",
            "next_programmatic_source": "MOPS annual reports/prospectuses/company formal filings and any official historical industry classification archive.",
            "notes": "Current sector/theme maps excluded; 2015-2021 all years blocked.",
        },
        {
            "dataset": "sector_breadth_pit_daily",
            "source_id": "sector_breadth_from_membership_and_liquidity_candidate",
            "source_name": "Derived sector/mainline breadth daily candidate",
            "source_path_or_url": "Derived only after membership and liquid universe are accepted",
            "source_type": "derived_candidate",
            "official_proxy_manual": "derived",
            "coverage_start": "",
            "coverage_end": "",
            "row_count": 0,
            "symbol_count": "",
            "source_date_available": "inherits_underlying_sources",
            "release_date_available": "not_required",
            "effective_date_available": "inherits_underlying_sources",
            "formal_ready": "false",
            "partial_ready": "false",
            "diagnostic_only": "false",
            "decision": "blocked",
            "next_programmatic_source": "Build after all-listed liquidity and PIT sector/mainline membership are accepted.",
            "notes": "Cannot be safely derived from current static maps.",
        },
        {
            "dataset": "all_listed_liquid_universe_pit_daily",
            "source_id": "radar_official_turnover_v1",
            "source_name": "Radar official turnover v1",
            "source_path_or_url": "data/formal_sources/official_turnover_20211201_20231231.csv",
            "source_type": "official_partial_with_gap_report",
            "official_proxy_manual": "official",
            "coverage_start": official_turnover_stats["min_date"],
            "coverage_end": official_turnover_stats["max_date"],
            "row_count": official_turnover_stats["row_count"],
            "symbol_count": official_turnover_stats["symbol_count"],
            "source_date_available": "true",
            "release_date_available": "not_required_for_daily_official_turnover",
            "effective_date_available": "true",
            "formal_ready": "false",
            "partial_ready": "true",
            "diagnostic_only": "false",
            "decision": "accepted_partial_turnover_component",
            "next_programmatic_source": "Extend official turnover ingestion to all-listed universe and 2015-latest.",
            "notes": "Useful daily official turnover component for liquidity screening, but not enough for an all-listed PIT tradable universe without listing/delisting/suspension metadata.",
        },
        {
            "dataset": "all_listed_liquid_universe_pit_daily",
            "source_id": "radar_0050_pcf_daily_full_range",
            "source_name": "Yuanta 0050 PCF/Daily full-range PIT candidate",
            "source_path_or_url": "outputs/radar_tw50_0050_pcf_daily_full_range_pit_candidate_201411_202312_20260629",
            "source_type": "source_backed_manual_candidate",
            "official_proxy_manual": "manual_proxy",
            "coverage_start": pcf_stats["min_date"],
            "coverage_end": pcf_stats["max_date"],
            "row_count": pcf_stats["row_count"],
            "symbol_count": pcf_stats["symbol_count"],
            "source_date_available": "true",
            "release_date_available": "not_required",
            "effective_date_available": "true",
            "formal_ready": "false",
            "partial_ready": "false",
            "diagnostic_only": "true",
            "decision": "proxy_not_dynamic_pool1",
            "next_programmatic_source": "Do not use for all-listed Dynamic Pool1; keep as 0050 holdings PIT candidate only.",
            "notes": "Useful for 0050/TW50 work, not all-listed dynamic Pool1 universe.",
        },
        {
            "dataset": "all_listed_liquid_universe_pit_daily",
            "source_id": "radar_0050_missing_price_4tickers",
            "source_name": "0050 PIT missing price coverage 4 tickers",
            "source_path_or_url": "outputs/radar_0050_pit_missing_price_coverage_4tickers_20260629",
            "source_type": "official_twse_unadjusted_ohlcv",
            "official_proxy_manual": "official",
            "coverage_start": missing_price_stats["min_date"],
            "coverage_end": missing_price_stats["max_date"],
            "row_count": missing_price_stats["row_count"],
            "symbol_count": missing_price_stats["symbol_count"],
            "source_date_available": "true",
            "release_date_available": "not_required_for_daily_price",
            "effective_date_available": "true",
            "formal_ready": "false",
            "partial_ready": "false",
            "diagnostic_only": "true",
            "decision": "price_component_only",
            "next_programmatic_source": "Do not treat four tickers as all-listed universe; extend TWSE/TPEx full-market daily downloader.",
            "notes": "Backfills 0050 PIT price blocker only; adjusted_close unavailable.",
        },
        {
            "dataset": "quarterly_fundamentals_pit",
            "source_id": "backtest_factor_2024_2026_valuation_blocked",
            "source_name": "Backtest factor package 2024-2026 valuation status",
            "source_path_or_url": "data/formal_sources/backtest_factor_2024_2026/readiness.json",
            "source_type": "readiness_evidence",
            "official_proxy_manual": "official_partial_other_factors",
            "coverage_start": factor_ready.get("start_date", ""),
            "coverage_end": factor_ready.get("end_date", ""),
            "row_count": "",
            "symbol_count": len(factor_ready.get("expected_stock_tickers", [])),
            "source_date_available": "false_for_valuation",
            "release_date_available": "false_for_valuation",
            "effective_date_available": "false_for_valuation",
            "formal_ready": "false",
            "partial_ready": "false",
            "diagnostic_only": "false",
            "decision": "confirms_quarterly_fundamentals_blocked",
            "next_programmatic_source": "MOPS/XBRL quarterly financial statements with filing/release date.",
            "notes": "Institutional/margin/day-trading are ready for 7 stocks, but valuation/fundamentals PIT remains blocked.",
        },
    ]
    return rows


def classify_rows(inventory: list[dict[str, Any]]) -> tuple[list[dict[str, Any]], list[dict[str, Any]], list[dict[str, Any]]]:
    accepted = [row for row in inventory if str(row["decision"]).startswith("accepted_partial")]
    proxy = [row for row in inventory if row["diagnostic_only"] == "true" or "proxy" in str(row["decision"])]
    blocked = [row for row in inventory if row["formal_ready"] == "false" and row["partial_ready"] == "false" and row not in proxy]
    return accepted, proxy, blocked


def build_coverage(inventory: list[dict[str, Any]]) -> list[dict[str, Any]]:
    datasets = [
        "all_listed_liquid_universe_pit_daily",
        "monthly_revenue_pit",
        "quarterly_fundamentals_pit",
        "historical_market_cap_pit",
        "sector_membership_pit",
        "sector_breadth_pit_daily",
    ]
    rows: list[dict[str, Any]] = []
    for dataset in datasets:
        dataset_sources = [row for row in inventory if row["dataset"] == dataset]
        for year in range(2015, 2027):
            y = str(year)
            statuses: list[str] = []
            for source in dataset_sources:
                start = str(source.get("coverage_start", ""))
                end = str(source.get("coverage_end", ""))
                if start and end and start[:4] <= y <= end[:4]:
                    if source["partial_ready"] == "true":
                        statuses.append("partial_ready")
                    elif source["diagnostic_only"] == "true":
                        statuses.append("proxy_or_diagnostic")
                    else:
                        statuses.append("candidate_not_acquired")
            if "partial_ready" in statuses:
                status = "partial_ready"
            elif "proxy_or_diagnostic" in statuses:
                status = "proxy_or_diagnostic_only"
            elif "candidate_not_acquired" in statuses:
                status = "candidate_not_acquired"
            else:
                status = "blocked_missing"
            rows.append(
                {
                    "dataset": dataset,
                    "year": y,
                    "coverage_status": status,
                    "formal_ready": "false",
                    "source_ids": ";".join(source["source_id"] for source in dataset_sources),
                    "notes": "Dynamic Pool1 not ready until this dataset is accepted all-listed PIT." if status != "partial_ready" else "Partial source exists but does not cover all-listed Dynamic Pool1 requirements.",
                }
            )
    return rows


def main() -> int:
    OUTPUT_DIR.mkdir(parents=True, exist_ok=True)
    started = datetime.now().astimezone().isoformat(timespec="seconds")
    (OUTPUT_DIR / "current_step.txt").write_text("building_source_acquisition_package\n", encoding="utf-8")

    inventory = build_inventory()
    for row in inventory:
        row["acceptance_decision"] = row["decision"]
    accepted, proxy, blocked = classify_rows(inventory)
    coverage = build_coverage(inventory)

    fields = [
        "dataset",
        "source_id",
        "source_name",
        "source_path_or_url",
        "source_type",
        "official_proxy_manual",
        "coverage_start",
        "coverage_end",
        "row_count",
        "symbol_count",
        "source_date_available",
        "release_date_available",
        "effective_date_available",
        "formal_ready",
        "partial_ready",
        "diagnostic_only",
        "decision",
        "acceptance_decision",
        "next_programmatic_source",
        "notes",
    ]
    write_csv(OUTPUT_DIR / "candidate_source_inventory.csv", inventory, fields)
    write_csv(OUTPUT_DIR / "source_manifest.csv", inventory, fields)
    write_json(OUTPUT_DIR / "source_manifest.json", {"task_id": TASK_ID, "sources": inventory})
    write_csv(OUTPUT_DIR / "accepted_source_rows.csv", accepted, fields)
    write_csv(OUTPUT_DIR / "proxy_source_rows.csv", proxy, fields)
    write_csv(OUTPUT_DIR / "blocked_source_rows.csv", blocked, fields)
    write_csv(OUTPUT_DIR / "coverage_by_dataset_year.csv", coverage, ["dataset", "year", "coverage_status", "formal_ready", "source_ids", "notes"])

    future_audit = [
        {
            "source_id": "current_generated_static_maps",
            "dataset": "sector_membership_pit",
            "future_data_violation_count": 0,
            "future_data_risk_excluded_count": 2,
            "decision": "excluded_from_accepted_sources",
            "evidence": "sector_map/theme_map/current generated universe lack source/effective/release dates and are not accepted for Dynamic Pool1 history.",
        },
        {
            "source_id": "accepted_partial_sources",
            "dataset": "monthly_revenue_pit;sector_breadth_turnover_component",
            "future_data_violation_count": 0,
            "future_data_risk_excluded_count": 0,
            "decision": "partial_ready_not_formal_ready",
            "evidence": "Partial official sources retain available/source dates but do not cover all-listed Dynamic Pool1 scope.",
        },
        {
            "source_id": "package_readiness",
            "dataset": "all",
            "future_data_violation_count": 0,
            "future_data_risk_excluded_count": 2,
            "decision": "dynamic_pool1_shadow_challenger_ready_false",
            "evidence": "No current snapshot/proxy/static sector map is promoted to formal-ready historical PIT.",
        },
    ]
    write_csv(
        OUTPUT_DIR / "future_data_violation_audit.csv",
        future_audit,
        ["source_id", "dataset", "future_data_violation_count", "future_data_risk_excluded_count", "decision", "evidence"],
    )

    readiness = {
        "task_id": TASK_ID,
        "status": "completed_partial_sources_but_core_ready_false",
        "dynamic_pool1_shadow_challenger_ready": False,
        "ready_for_core_rerun": True,
        "ready_for_strategy_replay": False,
        "formal_model_changed": False,
        "trade_decision_changed": False,
        "active_in_trade_decision": False,
        "future_data_violation_count": 0,
        "candidate_source_count": len(inventory),
        "accepted_partial_source_count": len(accepted),
        "proxy_source_count": len(proxy),
        "blocked_source_count": len(blocked),
        "partial_ready_datasets": sorted({row["dataset"] for row in accepted}),
        "blocked_datasets": [
            "all_listed_liquid_universe_pit_daily",
            "quarterly_fundamentals_pit",
            "historical_market_cap_pit",
            "sector_membership_pit",
            "sector_breadth_pit_daily",
        ],
        "core_readiness_runner_input_hint": {
            "source_manifest": str(OUTPUT_DIR / "source_manifest.csv"),
            "accepted_source_rows": str(OUTPUT_DIR / "accepted_source_rows.csv"),
            "proxy_source_rows": str(OUTPUT_DIR / "proxy_source_rows.csv"),
            "blocked_source_rows": str(OUTPUT_DIR / "blocked_source_rows.csv"),
            "coverage_by_dataset_year": str(OUTPUT_DIR / "coverage_by_dataset_year.csv"),
        },
        "blocking_issues": [
            "No all-listed PIT liquid universe accepted.",
            "Monthly revenue PIT has partial existing source pattern but not all-listed full-period Dynamic Pool1 coverage.",
            "No quarterly fundamentals PIT with filing/release date.",
            "No historical market cap PIT from date-aware shares outstanding or official market cap.",
            "Sector/mainline membership and breadth remain blocked; current static maps excluded.",
        ],
        "next_data_steps": [
            "Build bounded TWSE/TPEx full-market daily downloader plus listing/delisting/suspension metadata ledger.",
            "Extend MOPS monthly revenue PIT ingestion to all-listed universe and full Dynamic Pool1 period.",
            "Probe MOPS/XBRL quarterly financial statements with filing/release date.",
            "Acquire shares outstanding/capital changes PIT and derive market cap with date-aware prices.",
            "Acquire date-aware sector/mainline membership from official historical classifications or dated company filings.",
        ],
    }
    write_json(OUTPUT_DIR / "readiness_for_core.json", readiness)
    write_json(
        OUTPUT_DIR / "manifest.json",
        {
            "task_id": TASK_ID,
            "status": readiness["status"],
            "created_at": datetime.now().astimezone().isoformat(timespec="seconds"),
            "output_dir": str(OUTPUT_DIR),
            "core_input_output": str(CORE_OUTPUT),
            "formal_model_changed": False,
            "trade_decision_changed": False,
            "active_in_trade_decision": False,
            "future_data_violation_count": 0,
        },
    )
    write_csv(
        OUTPUT_DIR / "completed.csv",
        [{"item": "source_acquisition_package", "status": "completed", "details": "Inventory, accepted/proxy/blocked rows, coverage, future audit, and readiness_for_core produced."}],
        ["item", "status", "details"],
    )
    write_csv(
        OUTPUT_DIR / "failed.csv",
        [
            {"item": "dynamic_pool1_shadow_challenger_ready", "status": "blocked", "reason": "Critical PIT layers still missing."},
            {"item": "formal_ready_sources", "status": "blocked", "reason": "No complete all-listed universe/fundamental/market-cap/sector PIT package yet."},
        ],
        ["item", "status", "reason"],
    )
    write_csv(
        OUTPUT_DIR / "run_log.csv",
        [
            {"timestamp": started, "step": "start", "status": "running", "details": TASK_ID},
            {"timestamp": datetime.now().astimezone().isoformat(timespec="seconds"), "step": "read_core_contract", "status": "completed", "details": str(CORE_OUTPUT)},
            {"timestamp": datetime.now().astimezone().isoformat(timespec="seconds"), "step": "write_package", "status": "completed", "details": f"inventory={len(inventory)} accepted_partial={len(accepted)} proxy={len(proxy)} blocked={len(blocked)}"},
        ],
        ["timestamp", "step", "status", "details"],
    )
    summary = [
        "# Dynamic Pool1 PIT source acquisition package",
        "",
        f"- Task: `{TASK_ID}`",
        "- Status: `completed_partial_sources_but_core_ready_false`",
        "- ready_for_core_rerun: `true`",
        "- ready_for_strategy_replay: `false`",
        "- dynamic_pool1_shadow_challenger_ready: `false`",
        "- future_data_violation_count: `0`",
        "",
        "## Partial-ready sources",
        "",
        "- `monthly_revenue_pit`: existing MOPS monthly revenue PIT v1 has release/available-date pattern, but only covers the existing formal universe and 2021-12~2023-12.",
        "- `all_listed_liquid_universe_pit_daily` component: official turnover v1 is a usable partial daily official turnover component for liquidity screening, but the full universe still needs listing/delisting/suspension PIT metadata.",
        "",
        "## Still blocked",
        "",
        "- all-listed liquid universe PIT daily",
        "- quarterly fundamentals PIT",
        "- historical market cap PIT",
        "- sector/mainline PIT membership",
        "- sector/mainline breadth daily",
        "",
        "## Boundary",
        "",
        "Current/generated/static sector maps, current AI theme lists, current market universe, and 0050/TW50-specific PIT candidates are not promoted to Dynamic Pool1 formal sources.",
    ]
    (OUTPUT_DIR / "final_summary_zh.md").write_text("\n".join(summary) + "\n", encoding="utf-8")
    (OUTPUT_DIR / "current_step.txt").write_text("completed\n", encoding="utf-8")
    print(json.dumps(readiness, ensure_ascii=False, indent=2))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
