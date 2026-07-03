from __future__ import annotations

import csv
import json
from collections import Counter
from datetime import datetime
from pathlib import Path
from typing import Any


REPO_ROOT = Path(__file__).resolve().parents[2]
OUTPUT_DIR = Path(__file__).resolve().parent

TARGET_START = "2015-01-01"
TARGET_END = "2021-12-31"
TASK_ID = "TASK-BACKTEST-DATA-2015-2021-SECTOR-MAINLINE-PIT-CONTRACT-001"


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


def source_exists(path: str) -> bool:
    return (REPO_ROOT / path).exists()


def build_membership_panel() -> list[dict[str, Any]]:
    rows: list[dict[str, Any]] = []
    membership = read_csv(REPO_ROOT / "data/formal_sources/date_aware_theme_membership_full_2022_2023.csv")
    for row in membership:
        source_date = row.get("source_date", "")
        effective_start = row.get("effective_start", "")
        if not source_date or source_date > TARGET_END:
            continue
        rows.append(
            {
                "as_of_date": source_date,
                "effective_date": effective_start or source_date,
                "source_date": source_date,
                "symbol": row.get("symbol", ""),
                "ticker": row.get("ticker", ""),
                "name": row.get("name", ""),
                "sector": row.get("theme", ""),
                "mainline": row.get("theme", ""),
                "theme": row.get("theme", ""),
                "classification_level": "theme_as_sector_proxy",
                "role": "",
                "source_type": row.get("source_type", ""),
                "source_url": row.get("source_url", ""),
                "source_file": "data/formal_sources/date_aware_theme_membership_full_2022_2023.csv",
                "confidence": row.get("confidence", ""),
                "formal_exact": "false",
                "proxy": "true",
                "parser_status": "existing_partial_row",
                "validation_decision": "diagnostic_partial_only",
                "notes": "Existing dated membership row is usable as partial evidence only; it does not cover full 2015-2021 sector/mainline universe.",
            }
        )
    rows.sort(key=lambda item: (item["source_date"], item["symbol"]))
    return rows


def distinct_dates(rows: list[dict[str, str]], column: str = "date") -> set[str]:
    return {row.get(column, "") for row in rows if row.get(column, "")}


def dates_by_year(rows: list[dict[str, str]], column: str = "date") -> Counter[str]:
    counter: Counter[str] = Counter()
    for row in rows:
        value = row.get(column, "")
        if len(value) >= 4:
            counter[value[:4]] += 1
    return counter


def distinct_symbols_by_year(rows: list[dict[str, str]], date_column: str = "date") -> dict[str, set[str]]:
    result: dict[str, set[str]] = {str(year): set() for year in range(2015, 2022)}
    for row in rows:
        value = row.get(date_column, "")
        symbol = row.get("symbol", "")
        if len(value) >= 4 and symbol and value[:4] in result:
            result[value[:4]].add(symbol)
    return result


def build_coverage_by_year(membership_rows: list[dict[str, Any]]) -> list[dict[str, Any]]:
    turnover_rows = read_csv(REPO_ROOT / "data/formal_sources/official_turnover_20211201_20231231.csv")
    revenue_rows = read_csv(REPO_ROOT / "data/formal_sources/point_in_time_fundamentals_monthly_revenue_20211201_20231231.csv")
    turnover_dates = distinct_dates(turnover_rows)
    turnover_symbols = distinct_symbols_by_year(turnover_rows)
    revenue_symbols = distinct_symbols_by_year(revenue_rows, "available_date")
    membership_symbols_by_year: dict[str, set[str]] = {str(year): set() for year in range(2015, 2022)}
    for row in membership_rows:
        year = row["source_date"][:4]
        if year in membership_symbols_by_year:
            membership_symbols_by_year[year].add(row["symbol"])

    coverage: list[dict[str, Any]] = []
    for year in range(2015, 2022):
        y = str(year)
        turnover_date_count = len([d for d in turnover_dates if d.startswith(y)])
        coverage.append(
            {
                "year": y,
                "sector_membership_status": "partial_dated_evidence" if membership_symbols_by_year[y] else "missing_pit_membership",
                "sector_membership_symbol_count": len(membership_symbols_by_year[y]),
                "sector_membership_contract_ready": "false",
                "sector_breadth_daily_status": "blocked_missing_membership_or_daily_universe",
                "sector_breadth_trading_day_count": 0,
                "liquid_universe_status": "blocked_missing_full_market_pit_liquidity_panel",
                "liquid_universe_trading_day_count": 0,
                "official_turnover_status": "partial_official_from_2021_12" if turnover_date_count else "missing_official_turnover",
                "official_turnover_trading_day_count": turnover_date_count,
                "official_turnover_symbol_count": len(turnover_symbols[y]),
                "pit_revenue_status": "partial_from_2021_12" if revenue_symbols[y] else "not_required_for_breadth_contract_or_missing",
                "pit_revenue_symbol_count": len(revenue_symbols[y]),
                "overall_readiness": "blocked",
                "notes": "No complete date-aware sector/mainline membership plus liquid universe daily panel is available for this year.",
            }
        )
    return coverage


def main() -> int:
    OUTPUT_DIR.mkdir(parents=True, exist_ok=True)
    started = datetime.now().astimezone().isoformat(timespec="seconds")
    (OUTPUT_DIR / "current_step.txt").write_text("building_contract\n", encoding="utf-8")

    membership_rows = build_membership_panel()
    coverage_rows = build_coverage_by_year(membership_rows)

    membership_fields = [
        "as_of_date",
        "effective_date",
        "source_date",
        "symbol",
        "ticker",
        "name",
        "sector",
        "mainline",
        "theme",
        "classification_level",
        "role",
        "source_type",
        "source_url",
        "source_file",
        "confidence",
        "formal_exact",
        "proxy",
        "parser_status",
        "validation_decision",
        "notes",
    ]
    breadth_fields = [
        "date",
        "sector",
        "mainline",
        "constituent_count",
        "liquid_constituent_count",
        "up_count",
        "down_count",
        "strong_count",
        "above_ma20_count",
        "above_ma60_count",
        "advance_decline_ratio",
        "strong_ratio",
        "relative_strength_20d",
        "relative_strength_60d",
        "turnover_twd",
        "source_type",
        "formal_exact",
        "proxy",
        "validation_decision",
        "notes",
    ]
    liquid_fields = [
        "date",
        "symbol",
        "ticker",
        "name",
        "exchange",
        "listed_date",
        "delisted_date",
        "is_listed_on_date",
        "is_suspended",
        "close",
        "volume",
        "turnover_twd",
        "avg_turnover_20d_twd",
        "avg_volume_20d",
        "liquidity_pass",
        "exclusion_reason",
        "source_type",
        "formal_exact",
        "proxy",
        "validation_decision",
        "notes",
    ]

    write_csv(OUTPUT_DIR / "sector_membership_pit_panel.csv", membership_rows, membership_fields)
    write_csv(OUTPUT_DIR / "sector_membership_pit_panel_schema.csv", [{"field": f, "required": "true"} for f in membership_fields], ["field", "required"])
    write_csv(OUTPUT_DIR / "sector_breadth_pit_daily.csv", [], breadth_fields)
    write_csv(OUTPUT_DIR / "sector_breadth_pit_daily_schema.csv", [{"field": f, "required": "true"} for f in breadth_fields], ["field", "required"])
    write_csv(OUTPUT_DIR / "liquid_universe_pit_daily.csv", [], liquid_fields)
    write_csv(OUTPUT_DIR / "liquid_universe_pit_daily_schema.csv", [{"field": f, "required": "true"} for f in liquid_fields], ["field", "required"])
    write_csv(
        OUTPUT_DIR / "coverage_by_year.csv",
        coverage_rows,
        [
            "year",
            "sector_membership_status",
            "sector_membership_symbol_count",
            "sector_membership_contract_ready",
            "sector_breadth_daily_status",
            "sector_breadth_trading_day_count",
            "liquid_universe_status",
            "liquid_universe_trading_day_count",
            "official_turnover_status",
            "official_turnover_trading_day_count",
            "official_turnover_symbol_count",
            "pit_revenue_status",
            "pit_revenue_symbol_count",
            "overall_readiness",
            "notes",
        ],
    )

    source_rows = [
        {
            "source_id": "current_static_sector_map",
            "source_path_or_url": "data/sector_map.csv",
            "contract_component": "sector_membership_pit_panel",
            "coverage_start": "",
            "coverage_end": "",
            "source_type": "current_static_proxy",
            "official_or_proxy": "proxy",
            "formal_usable": "false",
            "diagnostic_usable": "false",
            "reason": "No source_date/effective_date/as_of_date; using it for 2015 would be future-data leakage risk.",
        },
        {
            "source_id": "current_static_theme_map",
            "source_path_or_url": "data/theme_map.csv",
            "contract_component": "sector_membership_pit_panel",
            "coverage_start": "",
            "coverage_end": "",
            "source_type": "current_static_proxy",
            "official_or_proxy": "proxy",
            "formal_usable": "false",
            "diagnostic_usable": "false",
            "reason": "No source_date/effective_date/as_of_date; current stories cannot be replayed as 2015 membership.",
        },
        {
            "source_id": "date_aware_theme_membership_full_2022_2023",
            "source_path_or_url": "data/formal_sources/date_aware_theme_membership_full_2022_2023.csv",
            "contract_component": "sector_membership_pit_panel",
            "coverage_start": "2021-01-13",
            "coverage_end": "2022-05-04",
            "source_type": "dated_evidence_partial",
            "official_or_proxy": "manual_evidence_candidate",
            "formal_usable": "false",
            "diagnostic_usable": "partial",
            "reason": "Only 8 dated memory-theme rows before 2022; does not cover sector/mainline universe or 2015-2020.",
        },
        {
            "source_id": "official_turnover_v1",
            "source_path_or_url": "data/formal_sources/official_turnover_20211201_20231231.csv",
            "contract_component": "sector_breadth_pit_daily",
            "coverage_start": "2021-12-01",
            "coverage_end": "2023-12-31",
            "source_type": "official_partial_with_gap_report",
            "official_or_proxy": "official",
            "formal_usable": "partial",
            "diagnostic_usable": "partial",
            "reason": "Starts 2021-12 only; cannot cover 2015-2021 full target without backfill.",
        },
        {
            "source_id": "point_in_time_revenue_v1",
            "source_path_or_url": "data/formal_sources/point_in_time_fundamentals_monthly_revenue_20211201_20231231.csv",
            "contract_component": "source_manifest",
            "coverage_start": "2021-12-01",
            "coverage_end": "2023-12-31",
            "source_type": "point_in_time_limited",
            "official_or_proxy": "official",
            "formal_usable": "not_sufficient_for_breadth",
            "diagnostic_usable": "partial",
            "reason": "Useful PIT source pattern but not a sector membership or daily liquid universe source.",
        },
        {
            "source_id": "twse_tpex_daily_market_official_candidate",
            "source_path_or_url": "TWSE/TPEx daily market APIs or historical daily files",
            "contract_component": "liquid_universe_pit_daily,sector_breadth_pit_daily",
            "coverage_start": "2015-01-01",
            "coverage_end": "2021-12-31",
            "source_type": "programmatic_source_candidate",
            "official_or_proxy": "official_candidate",
            "formal_usable": "unknown_until_acquired",
            "diagnostic_usable": "unknown_until_acquired",
            "reason": "Next programmable route for full-market daily OHLCV/volume/turnover and suspension/listing filters.",
        },
        {
            "source_id": "mops_annual_report_industry_evidence_candidate",
            "source_path_or_url": "MOPS annual reports / prospectuses / company formal files by source_date",
            "contract_component": "sector_membership_pit_panel",
            "coverage_start": "2015-01-01",
            "coverage_end": "2021-12-31",
            "source_type": "programmatic_source_candidate",
            "official_or_proxy": "manual_evidence_candidate",
            "formal_usable": "unknown_until_acquired",
            "diagnostic_usable": "unknown_until_acquired",
            "reason": "Next route for date-aware membership evidence; must parse source_date and avoid modern thematic labels.",
        },
    ]
    write_csv(
        OUTPUT_DIR / "source_manifest.csv",
        source_rows,
        [
            "source_id",
            "source_path_or_url",
            "contract_component",
            "coverage_start",
            "coverage_end",
            "source_type",
            "official_or_proxy",
            "formal_usable",
            "diagnostic_usable",
            "reason",
        ],
    )

    audit_rows = [
        {
            "audit_item": "current_static_sector_map",
            "checked_source": "data/sector_map.csv",
            "future_data_violation_count": 0,
            "future_data_risk_count": 1,
            "decision": "exclude_from_pit_contract",
            "evidence": "Header lacks source_date/effective_date/as_of_date; not accepted as 2015-2021 PIT membership.",
        },
        {
            "audit_item": "current_static_theme_map",
            "checked_source": "data/theme_map.csv",
            "future_data_violation_count": 0,
            "future_data_risk_count": 1,
            "decision": "exclude_from_pit_contract",
            "evidence": "Header lacks source_date/effective_date/as_of_date and includes modern themes; not accepted as 2015-2021 PIT membership.",
        },
        {
            "audit_item": "dated_membership_rows",
            "checked_source": "data/formal_sources/date_aware_theme_membership_full_2022_2023.csv",
            "future_data_violation_count": 0,
            "future_data_risk_count": 0,
            "decision": "partial_diagnostic_only",
            "evidence": f"{len(membership_rows)} rows have source_date <= 2021-12-31, but coverage is far below sector/mainline universe needs.",
        },
        {
            "audit_item": "package_acceptance",
            "checked_source": "all accepted package rows",
            "future_data_violation_count": 0,
            "future_data_risk_count": 0,
            "decision": "blocked_not_formal_ready",
            "evidence": "No static modern map rows were accepted into formal PIT membership; empty breadth/liquid panels prevent accidental future-data replay.",
        },
    ]
    write_csv(
        OUTPUT_DIR / "future_data_violation_audit.csv",
        audit_rows,
        ["audit_item", "checked_source", "future_data_violation_count", "future_data_risk_count", "decision", "evidence"],
    )

    blockers = [
        {
            "component": "sector_membership_pit_panel",
            "status": "blocked",
            "missing_data": "Full 2015-2021 date-aware sector/mainline membership with source_date/effective_date/as_of_date.",
            "next_programmatic_source": "MOPS annual reports, prospectuses, company formal filings, TWSE/TPEx industry classification archives if available.",
        },
        {
            "component": "sector_breadth_pit_daily",
            "status": "blocked",
            "missing_data": "Daily sector/mainline constituent set and liquid tradable universe for each trading day.",
            "next_programmatic_source": "TWSE/TPEx daily full-market OHLCV/turnover plus PIT membership after membership contract is acquired.",
        },
        {
            "component": "liquid_universe_pit_daily",
            "status": "blocked",
            "missing_data": "2015-2021 full-market listing/delisting/suspension/liquidity filters.",
            "next_programmatic_source": "TWSE/TPEX listed company daily/monthly metadata, daily trading files, delisting/suspension announcements.",
        },
    ]
    write_csv(OUTPUT_DIR / "blocked_requirements.csv", blockers, ["component", "status", "missing_data", "next_programmatic_source"])

    readiness = {
        "task_id": TASK_ID,
        "status": "blocked",
        "formal_ready": False,
        "diagnostic_only": False,
        "blocked": True,
        "target_start": TARGET_START,
        "target_end": TARGET_END,
        "sector_membership_pit_panel_ready": False,
        "sector_membership_pit_panel_rows": len(membership_rows),
        "sector_breadth_pit_daily_ready": False,
        "sector_breadth_pit_daily_rows": 0,
        "liquid_universe_pit_daily_ready": False,
        "liquid_universe_pit_daily_rows": 0,
        "future_data_violation_count": 0,
        "future_data_risk_excluded_count": 2,
        "coverage_years_ready": [],
        "coverage_years_blocked": [str(year) for year in range(2015, 2022)],
        "blocking_issues": [
            "missing_2015_2021_full_date_aware_sector_mainline_membership",
            "missing_2015_2021_sector_breadth_pit_daily",
            "missing_2015_2021_liquid_universe_pit_daily",
        ],
        "source_notes": [
            "Existing current sector_map/theme_map are explicitly excluded from PIT contract because they have no source_date/effective_date/as_of_date.",
            "Existing official_turnover_v1 and PIT revenue v1 start at 2021-12; they cannot support full 2015-2021 sector/mainline pool.",
            "The package defines the contract and blockers for Experiments; it does not run strategy performance and does not modify formal models.",
        ],
    }
    write_json(OUTPUT_DIR / "readiness.json", readiness)

    completed = [
        {
            "item": "contract_package",
            "status": "completed_blocked_readiness",
            "details": "All required contract files, source manifest, future-data audit, coverage_by_year, and readiness were produced.",
        }
    ]
    failed = [
        {
            "item": "formal_ready",
            "status": "blocked",
            "reason": "Required 2015-2021 PIT sector/mainline membership, breadth, and liquid universe panels are not available in current repo.",
        }
    ]
    write_csv(OUTPUT_DIR / "completed.csv", completed, ["item", "status", "details"])
    write_csv(OUTPUT_DIR / "failed.csv", failed, ["item", "status", "reason"])
    run_log = [
        {"timestamp": started, "step": "start", "status": "running", "details": TASK_ID},
        {
            "timestamp": datetime.now().astimezone().isoformat(timespec="seconds"),
            "step": "inventory_existing_sources",
            "status": "completed",
            "details": "Read current static maps, date-aware membership readiness, official turnover readiness, PIT revenue readiness, formal grade audit.",
        },
        {
            "timestamp": datetime.now().astimezone().isoformat(timespec="seconds"),
            "step": "write_contract_outputs",
            "status": "completed",
            "details": f"membership_rows={len(membership_rows)} readiness=blocked future_data_violation_count=0",
        },
    ]
    write_csv(OUTPUT_DIR / "run_log.csv", run_log, ["timestamp", "step", "status", "details"])

    manifest = {
        "task_id": TASK_ID,
        "status": "blocked",
        "output_dir": str(OUTPUT_DIR),
        "created_at": datetime.now().astimezone().isoformat(timespec="seconds"),
        "required_outputs": {
            "sector_membership_pit_panel": str(OUTPUT_DIR / "sector_membership_pit_panel.csv"),
            "sector_breadth_pit_daily": str(OUTPUT_DIR / "sector_breadth_pit_daily.csv"),
            "liquid_universe_pit_daily": str(OUTPUT_DIR / "liquid_universe_pit_daily.csv"),
            "source_manifest": str(OUTPUT_DIR / "source_manifest.csv"),
            "future_data_violation_audit": str(OUTPUT_DIR / "future_data_violation_audit.csv"),
            "coverage_by_year": str(OUTPUT_DIR / "coverage_by_year.csv"),
            "readiness": str(OUTPUT_DIR / "readiness.json"),
        },
        "formal_model_changed": False,
        "trade_decision_changed": False,
    }
    write_json(OUTPUT_DIR / "manifest.json", manifest)

    summary = [
        "# 2015-2021 sector/mainline PIT contract",
        "",
        f"- Task: `{TASK_ID}`",
        "- Readiness: `blocked`",
        "- formal_ready: `false`",
        "- diagnostic_only: `false` for sector/mainline backtest, because breadth/liquid universe panels are absent.",
        "- future_data_violation_count: `0` for accepted package rows.",
        "- current static maps excluded: `sector_map.csv` and `theme_map.csv` are not accepted as PIT membership.",
        "",
        "## Contract decision",
        "",
        "2015-2021 sector/mainline pool does **not** currently have a reliable backtest data foundation in this repo. Existing dated membership evidence is partial and concentrated in 2021 memory-theme rows. Existing official turnover and PIT revenue sources start at 2021-12 and cannot cover 2015-2021.",
        "",
        "## Blocking data",
        "",
        "- Full date-aware sector/mainline membership panel with `source_date`, `effective_date`, and `as_of_date`.",
        "- Daily sector/mainline breadth panel after membership is available.",
        "- Full-market liquid tradable universe panel with listing, delisting, suspension, volume, and turnover filters.",
        "",
        "## Next programmable sources",
        "",
        "- TWSE/TPEx daily full-market trading files for OHLCV/turnover/liquidity.",
        "- TWSE/TPEx listing/delisting/suspension metadata or announcements.",
        "- MOPS annual reports/prospectuses/company formal filings for dated sector/mainline membership evidence.",
        "- Any official historical industry classification archive, if available; otherwise classify as manual evidence candidate, not exact.",
    ]
    (OUTPUT_DIR / "final_summary_zh.md").write_text("\n".join(summary) + "\n", encoding="utf-8")
    (OUTPUT_DIR / "current_step.txt").write_text("completed\n", encoding="utf-8")
    print(json.dumps(readiness, ensure_ascii=False, indent=2))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
