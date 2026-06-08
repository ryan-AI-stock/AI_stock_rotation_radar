from __future__ import annotations

import csv
import json
from datetime import datetime, timezone
from pathlib import Path
from typing import Any


DAILY_RANKING_FIELDS = [
    "snapshot_date",
    "theme_rank",
    "theme",
    "theme_score",
    "theme_turnover_twd",
    "theme_turnover_share",
    "theme_turnover_momentum_5d",
    "theme_turnover_momentum_20d",
    "theme_price_momentum_20d",
    "theme_price_momentum_60d",
    "theme_breadth",
    "source_mode",
    "data_quality_status",
]

CANDIDATE_FIELDS = [
    "snapshot_date",
    "theme_rank",
    "theme",
    "symbol",
    "ticker",
    "exchange",
    "name",
    "theme_membership_effective_start",
    "theme_membership_source_date",
    "theme_membership_source_url",
    "theme_membership_confidence",
    "official_turnover_twd",
    "stock_turnover_share_in_theme",
    "stock_turnover_rank_in_theme",
    "close",
    "adj_close",
    "volume",
    "market_cap_twd",
    "stock_score",
    "fundamental_pass",
    "fundamental_score",
    "revenue_yoy",
    "revenue_mom",
    "fundamental_period",
    "fundamental_available_date",
    "overheated_flag",
    "risk_heat",
    "liquidity_flag",
    "bucket",
    "data_quality_status",
]

SNAPSHOT_FIELDS = [
    "snapshot_date",
    "source_mode",
    "top3_theme_count",
    "candidate_count",
    "future_data_violation_count",
    "data_quality_status",
    "blocking_issue",
]

GAP_FIELDS = [
    "gap_type",
    "status",
    "required_mode",
    "current_mode",
    "affected_date_start",
    "affected_date_end",
    "affected_count",
    "evidence_path",
    "reason",
    "next_action",
]

REQUIRED_READINESS_FIELDS = [
    "ready",
    "source_mode",
    "start_date",
    "end_date",
    "trading_day_count",
    "dates_with_top3_theme_count",
    "candidate_row_count",
    "theme_membership_coverage_ratio",
    "official_turnover_coverage_ratio",
    "fundamental_coverage_ratio",
    "future_data_violation_count",
    "missing_top3_theme_date_count",
    "missing_candidate_date_count",
    "blocking_issues",
    "warnings",
]


def build_formal_top3_capital_flow_package(
    *,
    output_dir: str | Path,
    start_date: str = "2022-01-03",
    end_date: str = "2023-12-29",
    official_turnover_file: str | Path = "data/formal_sources/official_turnover_20211201_20231231.csv",
    official_turnover_readiness: str | Path = "data/formal_sources/official_turnover_v1_readiness.json",
    fundamental_readiness: str | Path = "data/formal_sources/point_in_time_revenue_v1_readiness.json",
    theme_membership_readiness: str | Path = "data/formal_sources/date_aware_theme_membership_v1_readiness.json",
    memory_theme_membership_readiness: str | Path = "data/formal_sources/date_aware_theme_membership_memory_v1_readiness.json",
) -> dict[str, Any]:
    output = Path(output_dir)
    output.mkdir(parents=True, exist_ok=True)

    official_ready = _read_json(official_turnover_readiness)
    fundamental_ready = _read_json(fundamental_readiness)
    theme_ready = _read_json(theme_membership_readiness)
    memory_ready = _read_json(memory_theme_membership_readiness) if Path(memory_theme_membership_readiness).exists() else {}
    trading_day_count = _count_turnover_dates(Path(official_turnover_file), start_date=start_date, end_date=end_date)

    paths = _package_paths(output)
    _write_rows(paths["daily_ranking"], DAILY_RANKING_FIELDS, [])
    _write_rows(paths["candidates"], CANDIDATE_FIELDS, [])
    _write_rows(paths["snapshot"], SNAPSHOT_FIELDS, [])

    blocking_issues = [
        "date_aware_theme_membership_full_universe_blocked",
        "top3_theme_ranking_not_generated_due_to_membership_block",
        "candidate_pool_not_generated_due_to_membership_block",
    ]
    gap_rows = [
        {
            "gap_type": "date_aware_theme_membership",
            "status": "blocked",
            "required_mode": "date_aware_full_universe",
            "current_mode": str(theme_ready.get("source_mode", "")),
            "affected_date_start": start_date,
            "affected_date_end": end_date,
            "affected_count": str(theme_ready.get("static_only_count", "")),
            "evidence_path": str(theme_membership_readiness),
            "reason": "Full-universe top3 capital flow replay cannot use current static theme_map.csv as historical theme membership evidence.",
            "next_action": "Build date-aware membership evidence for all themes and symbols used by the formal universe.",
        },
        {
            "gap_type": "memory_theme_membership_partial_only",
            "status": "non_sufficient_for_top3_formal_ready",
            "required_mode": "date_aware_all_top3_themes",
            "current_mode": str(memory_ready.get("source_mode", "not_available")),
            "affected_date_start": start_date,
            "affected_date_end": end_date,
            "affected_count": str(memory_ready.get("static_only_count", "")),
            "evidence_path": str(memory_theme_membership_readiness),
            "reason": "Memory v1 partial source can support a narrow memory subset, but cannot rank all daily top3 capital-flow themes.",
            "next_action": "Use memory partial only for narrow research replay, not for formal top3 cross-theme rotation.",
        },
        {
            "gap_type": "top3_theme_daily_ranking",
            "status": "not_generated",
            "required_mode": "formal_ready_top3_daily",
            "current_mode": "formal_blocked",
            "affected_date_start": start_date,
            "affected_date_end": end_date,
            "affected_count": str(trading_day_count),
            "evidence_path": str(paths["daily_ranking"]),
            "reason": "Theme ranking would require date-aware membership before aggregating official turnover into themes.",
            "next_action": "Regenerate package after full-universe date-aware membership is available.",
        },
        {
            "gap_type": "top3_theme_stock_candidates",
            "status": "not_generated",
            "required_mode": "candidate_rows_for_each_top3_theme_date",
            "current_mode": "formal_blocked",
            "affected_date_start": start_date,
            "affected_date_end": end_date,
            "affected_count": str(trading_day_count),
            "evidence_path": str(paths["candidates"]),
            "reason": "Candidate rows would inherit the same date-aware theme membership blocker.",
            "next_action": "Regenerate candidates after formal top3 theme ranking is available.",
        },
    ]
    _write_rows(paths["gap"], GAP_FIELDS, gap_rows)

    readiness = {
        "ready": False,
        "source_mode": "formal_blocked",
        "start_date": start_date,
        "end_date": end_date,
        "trading_day_count": trading_day_count,
        "dates_with_top3_theme_count": 0,
        "candidate_row_count": 0,
        "theme_membership_coverage_ratio": float(theme_ready.get("coverage_ratio", 0.0)),
        "official_turnover_coverage_ratio": float(official_ready.get("coverage_ratio", 0.0)),
        "fundamental_coverage_ratio": float(fundamental_ready.get("coverage_ratio", 0.0)),
        "future_data_violation_count": int(fundamental_ready.get("future_data_violation_count", 0)),
        "missing_top3_theme_date_count": trading_day_count,
        "missing_candidate_date_count": trading_day_count,
        "blocking_issues": blocking_issues,
        "warnings": [
            "formal_ready is blocked because full-universe date-aware theme membership is unavailable.",
            "official turnover and PIT monthly revenue sources are ready enough for ingestion, but theme membership remains the gating source.",
            "memory date-aware membership v1 is partial and cannot be generalized to all top3 capital-flow themes.",
        ],
    }
    _write_json(paths["readiness"], readiness)

    manifest = {
        "created_at": _utc_now_iso(),
        "package": "formal_top3_capital_flow_2022_2023",
        "status": "formal_blocked",
        "start_date": start_date,
        "end_date": end_date,
        "inputs": {
            "official_turnover_file": str(official_turnover_file),
            "official_turnover_readiness": str(official_turnover_readiness),
            "fundamental_readiness": str(fundamental_readiness),
            "theme_membership_readiness": str(theme_membership_readiness),
            "memory_theme_membership_readiness": str(memory_theme_membership_readiness),
        },
        "outputs": {key: str(path) for key, path in paths.items()},
        "notes": [
            "Empty ranking/candidate/snapshot CSVs are intentional for formal_blocked status.",
            "Do not downgrade this package to research-only without an explicit downstream decision.",
        ],
    }
    _write_json(paths["manifest"], manifest)
    return readiness


def validate_top3_capital_flow_package(*, output_dir: str | Path) -> dict[str, Any]:
    output = Path(output_dir)
    paths = _package_paths(output)
    missing_files = [str(path) for path in paths.values() if not path.exists()]
    if missing_files:
        raise FileNotFoundError(f"top3 package missing files: {', '.join(missing_files)}")

    _assert_header(paths["daily_ranking"], DAILY_RANKING_FIELDS)
    _assert_header(paths["candidates"], CANDIDATE_FIELDS)
    _assert_header(paths["snapshot"], SNAPSHOT_FIELDS)
    _assert_header(paths["gap"], GAP_FIELDS)

    readiness = _read_json(paths["readiness"])
    missing_fields = [field for field in REQUIRED_READINESS_FIELDS if field not in readiness]
    if missing_fields:
        raise ValueError(f"readiness missing required fields: {', '.join(missing_fields)}")
    if readiness["source_mode"] not in {"formal_ready", "formal_blocked"}:
        raise ValueError(f"unsupported source_mode: {readiness['source_mode']}")
    if readiness["ready"] and readiness["source_mode"] != "formal_ready":
        raise ValueError("ready=true requires source_mode=formal_ready")
    if not readiness["ready"] and readiness["source_mode"] != "formal_blocked":
        raise ValueError("ready=false requires source_mode=formal_blocked")
    if readiness["future_data_violation_count"] != 0:
        raise ValueError("future_data_violation_count must be zero")
    if readiness["source_mode"] == "formal_blocked" and not readiness["blocking_issues"]:
        raise ValueError("formal_blocked requires blocking_issues")
    return readiness


def _package_paths(output: Path) -> dict[str, Path]:
    return {
        "daily_ranking": output / "top3_theme_daily_ranking_2022_2023.csv",
        "candidates": output / "top3_theme_stock_candidates_2022_2023.csv",
        "snapshot": output / "top3_capital_flow_snapshot_2022_2023.csv",
        "readiness": output / "top3_capital_flow_readiness.json",
        "gap": output / "top3_capital_flow_gap_report.csv",
        "manifest": output / "top3_capital_flow_manifest.json",
    }


def _count_turnover_dates(path: Path, *, start_date: str, end_date: str) -> int:
    if not path.exists():
        return 0
    dates: set[str] = set()
    with path.open("r", encoding="utf-8-sig", newline="") as handle:
        for row in csv.DictReader(handle):
            value = str(row.get("date", "")).strip()
            if start_date <= value <= end_date:
                dates.add(value)
    return len(dates)


def _assert_header(path: Path, expected_fields: list[str]) -> None:
    with path.open("r", encoding="utf-8-sig", newline="") as handle:
        reader = csv.reader(handle)
        header = next(reader, [])
    if header != expected_fields:
        raise ValueError(f"{path} header mismatch")


def _write_rows(path: Path, fieldnames: list[str], rows: list[dict[str, str]]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("w", encoding="utf-8-sig", newline="") as handle:
        writer = csv.DictWriter(handle, fieldnames=fieldnames)
        writer.writeheader()
        writer.writerows(rows)


def _read_json(path: str | Path) -> dict[str, Any]:
    return json.loads(Path(path).read_text(encoding="utf-8"))


def _write_json(path: Path, payload: dict[str, Any]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(payload, ensure_ascii=False, indent=2), encoding="utf-8")


def _utc_now_iso() -> str:
    return datetime.now(timezone.utc).replace(microsecond=0).isoformat()
