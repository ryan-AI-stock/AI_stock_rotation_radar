from __future__ import annotations

import csv
import json
from dataclasses import dataclass
from pathlib import Path
from typing import Any


@dataclass(frozen=True)
class FormalGradeAuditResult:
    manifest_path: Path
    readiness_path: Path
    daily_coverage_path: Path
    formal_universe_path: Path
    missing_ohlcv_path: Path
    fundamental_gap_path: Path
    theme_membership_gap_path: Path
    turnover_gap_path: Path
    unavailable_items_path: Path
    readme_path: Path


def build_formal_grade_audit(
    *,
    source_dir: str | Path,
    output_dir: str | Path,
    theme_map_path: str | Path,
) -> FormalGradeAuditResult:
    """Create a formal-grade readiness audit without promoting limited replay data.

    This function intentionally does not copy limited replay snapshots into the
    formal-grade output. If point-in-time fundamentals, date-aware theme
    membership, or official turnover are unavailable, the formal package must
    fail closed and document why.
    """

    source = Path(source_dir)
    output = Path(output_dir)
    output.mkdir(parents=True, exist_ok=True)

    source_manifest = _read_json(source / "historical_backtest_grade_manifest.json")
    source_readiness = _read_json(source / "historical_backtest_grade_readiness.json")
    theme_rows = _read_theme_map(Path(theme_map_path))

    missing_ohlcv = sorted(str(item) for item in source_readiness.get("missing_ohlcv_symbols", []))
    missing_fundamental = sorted(str(item) for item in source_readiness.get("missing_fundamental_symbols", []))
    covered_symbols = sorted({row["symbol"] for row in theme_rows} - set(missing_ohlcv))
    rows_by_symbol = _first_theme_rows_by_symbol(theme_rows)
    formal_universe = [rows_by_symbol[symbol] for symbol in covered_symbols if symbol in rows_by_symbol]

    blockers = [
        {
            "item": "point_in_time_fundamentals",
            "status": "blocked",
            "required_mode": "point_in_time or point_in_time_limited",
            "current_mode": str(source_readiness.get("fundamental_mode", "")),
            "reason": (
                "Only baseline/carry-forward stock metrics are available in this repo; "
                "there is no historical financial announcement or acquisition-date table."
            ),
        },
        {
            "item": "date_aware_theme_membership",
            "status": "blocked",
            "required_mode": "date_aware",
            "current_mode": str(source_readiness.get("theme_membership_mode", "")),
            "reason": (
                "theme_map.csv has no effective_start/effective_end/source_date fields, "
                "so current classifications cannot be safely replayed as historical membership."
            ),
        },
        {
            "item": "official_exchange_turnover",
            "status": "blocked",
            "required_mode": "official_exchange_turnover or official_partial_with_gap_report",
            "current_mode": str(source_readiness.get("turnover_mode", "")),
            "reason": (
                "The historical cache used by the replay contains OHLCV only; turnover_value "
                "was computed as close * volume, not official TWSE/TPEx turnover amount."
            ),
        },
    ]

    manifest_path = output / "historical_formal_grade_manifest.json"
    readiness_path = output / "historical_formal_grade_readiness.json"
    daily_coverage_path = output / "historical_formal_grade_daily_coverage.csv"
    formal_universe_path = output / "formal_universe.csv"
    missing_ohlcv_path = output / "missing_ohlcv_symbols.csv"
    fundamental_gap_path = output / "fundamental_gap_report.csv"
    theme_membership_gap_path = output / "theme_membership_gap_report.csv"
    turnover_gap_path = output / "official_turnover_gap_report.csv"
    unavailable_items_path = output / "formal_grade_unavailable_items.csv"
    readme_path = output / "README.md"

    _write_formal_universe(formal_universe_path, formal_universe)
    _write_missing_ohlcv(missing_ohlcv_path, theme_rows, missing_ohlcv)
    _write_fundamental_gaps(fundamental_gap_path, theme_rows, missing_fundamental)
    _write_theme_membership_gaps(theme_membership_gap_path, theme_rows)
    _write_turnover_gaps(turnover_gap_path, formal_universe)
    _write_unavailable_items(unavailable_items_path, blockers)
    daily_rows = _write_daily_coverage(
        daily_coverage_path,
        source / "historical_backtest_grade_daily_coverage.csv",
        blockers,
    )

    manifest = {
        "dataset_type": "historical_formal_grade_audit",
        "dataset_mode": "formal_grade_blocked",
        "description": "Formal-grade readiness audit for sector radar historical replay data.",
        "source_backtest_grade_dir": str(source),
        "source_dataset_mode": source_manifest.get("dataset_mode"),
        "requested_start_date": source_readiness.get("requested_start_date"),
        "requested_end_date": source_readiness.get("requested_end_date"),
        "actual_start_date": source_readiness.get("actual_start_date"),
        "actual_end_date": source_readiness.get("actual_end_date"),
        "source_snapshot_count": source_readiness.get("snapshot_count", 0),
        "formal_snapshot_count": 0,
        "daily_coverage_rows": daily_rows,
        "theme_map_symbol_count": len({row["symbol"] for row in theme_rows}),
        "formal_universe_symbol_count": len(formal_universe),
        "formal_universe_missing_ohlcv_count": 0,
        "excluded_missing_ohlcv_symbol_count": len(missing_ohlcv),
        "missing_fundamental_symbol_count": len(missing_fundamental),
        "future_fundamental_violation_count": source_readiness.get("future_fundamental_violation_count"),
        "fundamental_mode": "unavailable_point_in_time_history",
        "theme_membership_mode": "unavailable_current_static_map_only",
        "turnover_mode": "unavailable_official_exchange_turnover",
        "ready_for_formal_strategy_conclusion": False,
        "readiness_path": str(readiness_path),
        "daily_coverage_path": str(daily_coverage_path),
        "formal_universe_path": str(formal_universe_path),
        "gap_reports": {
            "missing_ohlcv_symbols": str(missing_ohlcv_path),
            "fundamental_gap_report": str(fundamental_gap_path),
            "theme_membership_gap_report": str(theme_membership_gap_path),
            "official_turnover_gap_report": str(turnover_gap_path),
            "formal_grade_unavailable_items": str(unavailable_items_path),
        },
        "blocking_issues": blockers,
        "formal_grade_policy": (
            "Do not use this output as formal strategy evidence until readiness "
            "ready_for_formal_strategy_conclusion becomes true."
        ),
    }

    readiness = {
        "ready_for_formal_audit_ingestion": True,
        "ready_for_formal_strategy_conclusion": False,
        "readiness_status": "blocked_source_data_unavailable",
        "source_ready_for_backtest_lab_ingestion": source_readiness.get("ready_for_backtest_lab_ingestion"),
        "source_readiness_status": source_readiness.get("readiness_status"),
        "acceptance_criteria": {
            "future_fundamental_violation_count_is_zero": source_readiness.get("future_fundamental_violation_count") == 0,
            "formal_universe_missing_ohlcv_is_zero": True,
            "fundamental_not_baseline_seed_carry_forward": False,
            "theme_membership_not_current_static_map_only": False,
            "turnover_not_close_times_volume_only": False,
        },
        "formal_universe_symbol_count": len(formal_universe),
        "formal_universe_missing_ohlcv_count": 0,
        "excluded_missing_ohlcv_symbol_count": len(missing_ohlcv),
        "missing_fundamental_symbol_count": len(missing_fundamental),
        "blocking_issue_count": len(blockers),
        "blocking_issues": blockers,
        "required_next_data_sources": [
            "point-in-time fundamental history with announcement or acquisition dates",
            "date-aware theme membership table with effective_start/effective_end/source fields",
            "official TWSE/TPEx daily turnover amount for the replay universe",
        ],
        "formal_grade_conclusion": (
            "目前資料只能支援研究草稿，不能支援正式雷達個股輪動策略結論。"
        ),
    }

    _write_json(manifest_path, manifest)
    _write_json(readiness_path, readiness)
    _write_readme(readme_path, manifest, readiness)

    return FormalGradeAuditResult(
        manifest_path=manifest_path,
        readiness_path=readiness_path,
        daily_coverage_path=daily_coverage_path,
        formal_universe_path=formal_universe_path,
        missing_ohlcv_path=missing_ohlcv_path,
        fundamental_gap_path=fundamental_gap_path,
        theme_membership_gap_path=theme_membership_gap_path,
        turnover_gap_path=turnover_gap_path,
        unavailable_items_path=unavailable_items_path,
        readme_path=readme_path,
    )


def _read_json(path: Path) -> dict[str, Any]:
    return json.loads(path.read_text(encoding="utf-8"))


def _write_json(path: Path, data: dict[str, Any]) -> None:
    path.write_text(json.dumps(data, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")


def _read_theme_map(path: Path) -> list[dict[str, str]]:
    with path.open("r", encoding="utf-8-sig", newline="") as handle:
        return [
            {key: (value or "").strip() for key, value in row.items()}
            for row in csv.DictReader(handle)
        ]


def _first_theme_rows_by_symbol(rows: list[dict[str, str]]) -> dict[str, dict[str, str]]:
    output: dict[str, dict[str, str]] = {}
    for row in rows:
        output.setdefault(row["symbol"], row)
    return output


def _write_formal_universe(path: Path, rows: list[dict[str, str]]) -> None:
    _write_rows(
        path,
        ["symbol", "name", "theme", "role", "formal_ohlcv_available", "formal_status"],
        [
            {
                "symbol": row.get("symbol", ""),
                "name": row.get("name", ""),
                "theme": row.get("theme", ""),
                "role": row.get("role", ""),
                "formal_ohlcv_available": "true",
                "formal_status": "ohlcv_available_but_formal_blocked_by_fundamental_theme_turnover",
            }
            for row in rows
        ],
    )


def _write_missing_ohlcv(path: Path, rows: list[dict[str, str]], missing_symbols: list[str]) -> None:
    by_symbol = _first_theme_rows_by_symbol(rows)
    _write_rows(
        path,
        ["symbol", "name", "theme", "reason"],
        [
            {
                "symbol": symbol,
                "name": by_symbol.get(symbol, {}).get("name", ""),
                "theme": by_symbol.get(symbol, {}).get("theme", ""),
                "reason": "missing OHLCV in available replay cache",
            }
            for symbol in missing_symbols
        ],
    )


def _write_fundamental_gaps(path: Path, rows: list[dict[str, str]], missing_symbols: list[str]) -> None:
    missing = set(missing_symbols)
    _write_rows(
        path,
        ["symbol", "name", "theme", "fundamental_status", "fundamental_unavailable_reason"],
        [
            {
                "symbol": row.get("symbol", ""),
                "name": row.get("name", ""),
                "theme": row.get("theme", ""),
                "fundamental_status": "missing_baseline_and_point_in_time" if row.get("symbol", "") in missing else "baseline_only_not_point_in_time",
                "fundamental_unavailable_reason": (
                    "No point-in-time financial announcement/acquisition-date table is available."
                ),
            }
            for row in rows
        ],
    )


def _write_theme_membership_gaps(path: Path, rows: list[dict[str, str]]) -> None:
    _write_rows(
        path,
        ["symbol", "name", "theme", "theme_membership_status", "unavailable_reason"],
        [
            {
                "symbol": row.get("symbol", ""),
                "name": row.get("name", ""),
                "theme": row.get("theme", ""),
                "theme_membership_status": "current_static_map_only",
                "unavailable_reason": "theme_map.csv has no effective date or historical source fields.",
            }
            for row in rows
        ],
    )


def _write_turnover_gaps(path: Path, rows: list[dict[str, str]]) -> None:
    _write_rows(
        path,
        ["symbol", "name", "theme", "turnover_status", "unavailable_reason"],
        [
            {
                "symbol": row.get("symbol", ""),
                "name": row.get("name", ""),
                "theme": row.get("theme", ""),
                "turnover_status": "close_times_volume_only",
                "unavailable_reason": "Official TWSE/TPEx turnover amount is not present in the replay OHLCV cache.",
            }
            for row in rows
        ],
    )


def _write_unavailable_items(path: Path, blockers: list[dict[str, str]]) -> None:
    _write_rows(
        path,
        ["item", "status", "required_mode", "current_mode", "reason"],
        blockers,
    )


def _write_daily_coverage(path: Path, source_path: Path, blockers: list[dict[str, str]]) -> int:
    if not source_path.exists():
        _write_rows(path, ["date", "formal_ready", "blocking_issue_count", "blocking_items"], [])
        return 0

    with source_path.open("r", encoding="utf-8-sig", newline="") as handle:
        source_rows = list(csv.DictReader(handle))

    blocking_items = ";".join(item["item"] for item in blockers)
    rows = []
    for row in source_rows:
        output = dict(row)
        output["formal_ready"] = "false"
        output["blocking_issue_count"] = str(len(blockers))
        output["blocking_items"] = blocking_items
        rows.append(output)

    fieldnames = list(source_rows[0].keys()) if source_rows else ["date"]
    fieldnames.extend(["formal_ready", "blocking_issue_count", "blocking_items"])
    _write_rows(path, fieldnames, rows)
    return len(rows)


def _write_rows(path: Path, fieldnames: list[str], rows: list[dict[str, Any]]) -> None:
    with path.open("w", encoding="utf-8-sig", newline="") as handle:
        writer = csv.DictWriter(handle, fieldnames=fieldnames, extrasaction="ignore")
        writer.writeheader()
        writer.writerows(rows)


def _write_readme(path: Path, manifest: dict[str, Any], readiness: dict[str, Any]) -> None:
    lines = [
        "# Formal Grade Historical Radar Audit",
        "",
        "This folder is a formal-grade readiness audit, not a formal-grade replay dataset.",
        "",
        f"- ready_for_formal_strategy_conclusion: {str(readiness['ready_for_formal_strategy_conclusion']).lower()}",
        f"- readiness_status: {readiness['readiness_status']}",
        f"- source_snapshot_count: {manifest['source_snapshot_count']}",
        f"- formal_universe_symbol_count: {manifest['formal_universe_symbol_count']}",
        f"- excluded_missing_ohlcv_symbol_count: {manifest['excluded_missing_ohlcv_symbol_count']}",
        "",
        "Blocking items:",
    ]
    for item in readiness["blocking_issues"]:
        lines.append(f"- {item['item']}: {item['reason']}")
    lines.extend(
        [
            "",
            "Conclusion:",
            "",
            readiness["formal_grade_conclusion"],
            "",
        ]
    )
    path.write_text("\n".join(lines), encoding="utf-8")
