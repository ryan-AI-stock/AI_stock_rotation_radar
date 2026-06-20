from __future__ import annotations

import csv
import json
from datetime import datetime, timezone
from pathlib import Path
from typing import Any


PACKAGE_START_DATE = "2024-01-02"
PACKAGE_END_DATE = "2026-05-26"
CORE_STOCK_TICKERS = ["2308.TW", "2317.TW", "2330.TW", "2382.TW", "2454.TW", "3231.TW", "6669.TW"]

GAP_FIELDS = [
    "factor_id",
    "status",
    "symbol",
    "ticker",
    "date",
    "gap_reason",
    "source_file",
    "notes",
]

FACTOR_INPUTS = {
    "institutional_flows": {
        "csv": "institutional_flows_daily_20240102_20260526.csv",
        "readiness": "institutional_flows_daily_20240102_20260526_readiness.json",
        "gap": "institutional_flows_daily_20240102_20260526_gap.csv",
    },
    "margin_short": {
        "csv": "margin_short_daily_20240102_20260526.csv",
        "readiness": "margin_short_daily_20240102_20260526_readiness.json",
        "gap": "margin_short_daily_20240102_20260526_gap.csv",
    },
    "day_trading": {
        "csv": "day_trading_daily_20240102_20260526.csv",
        "readiness": "day_trading_daily_20240102_20260526_readiness.json",
        "gap": "day_trading_daily_20240102_20260526_gap.csv",
    },
}


def build_backtest_factor_package(
    *,
    package_dir: str | Path = "data/formal_sources/backtest_factor_2024_2026",
    readiness_output: str | Path | None = None,
    gap_output: str | Path | None = None,
    manifest_output: str | Path | None = None,
) -> dict[str, Any]:
    root = Path(package_dir)
    readiness_path = Path(readiness_output) if readiness_output else root / "readiness.json"
    gap_path = Path(gap_output) if gap_output else root / "gap.csv"
    manifest_path = Path(manifest_output) if manifest_output else root / "manifest.md"

    factor_status = {}
    gap_rows: list[dict[str, str]] = []
    source_paths = {}

    for factor_id, paths in FACTOR_INPUTS.items():
        readiness_file = root / paths["readiness"]
        csv_file = root / paths["csv"]
        gap_file = root / paths["gap"]
        source_paths[factor_id] = _relative(csv_file)
        if not readiness_file.exists():
            factor_status[factor_id] = _missing_factor_status(factor_id, csv_file, readiness_file)
            gap_rows.append(
                _gap_row(
                    factor_id=factor_id,
                    status="blocked",
                    reason="readiness_file_missing",
                    source_file=readiness_file,
                    notes="Build and validate the source dataset before packaging.",
                )
            )
            continue

        readiness = _read_json(readiness_file)
        coverage = float(readiness.get("stock_coverage_ratio", readiness.get("coverage_ratio", 0.0)) or 0.0)
        future_violations = int(readiness.get("future_data_violation_count", 0) or 0)
        source_validator_ready = bool(readiness.get("ready"))
        coverage_threshold_met = coverage >= 0.95 and future_violations == 0
        ready = source_validator_ready and coverage_threshold_met
        factor_status[factor_id] = {
            "ready": ready,
            "status": "ready" if ready else "partial",
            "source_validator_ready": source_validator_ready,
            "coverage_threshold_met": coverage_threshold_met,
            "source_mode": readiness.get("source_mode", ""),
            "source_start": readiness.get("start_date", ""),
            "source_end": readiness.get("end_date", ""),
            "coverage_ratio": readiness.get("coverage_ratio", 0.0),
            "fresh_coverage_ratio": coverage,
            "future_data_violation_count": future_violations,
            "gap_count": int(readiness.get("stock_gap_count", 0) or 0),
            "blocking_issues": readiness.get("blocking_issues", []),
            "warnings": readiness.get("warnings", []),
            "csv": _relative(csv_file),
            "readiness": _relative(readiness_file),
            "gap": _relative(gap_file),
        }
        gap_rows.extend(_read_source_gap_rows(factor_id=factor_id, status="partial" if not ready else "ready", gap_file=gap_file))

    factor_status["valuation"] = _valuation_blocked_status()
    gap_rows.append(
        _gap_row(
            factor_id="valuation",
            status="blocked",
            reason="point_in_time_official_valuation_source_not_ingested",
            source_file="",
            notes=(
                "Do not backfill 2024-01-02~2026-05-26 with the 2026-06-14 manual snapshot; "
                "EPS/PE/PB must come from an official point-in-time source before use."
            ),
        )
    )

    package_ready = all(factor_status[factor_id]["ready"] for factor_id in FACTOR_INPUTS)
    valuation_ready = factor_status["valuation"]["ready"]
    payload = {
        "ready": package_ready and valuation_ready,
        "source_mode": "backtest_factor_package_ready" if package_ready and valuation_ready else "backtest_factor_package_partial",
        "decision_layer": "data_readiness",
        "active_in_trade_decision": False,
        "start_date": PACKAGE_START_DATE,
        "end_date": PACKAGE_END_DATE,
        "expected_stock_tickers": CORE_STOCK_TICKERS,
        "generated_at_utc": datetime.now(timezone.utc).replace(microsecond=0).isoformat(),
        "factor_status": factor_status,
        "core_validator_source_paths": source_paths,
        "future_data_violation_count": sum(
            int(status.get("future_data_violation_count", 0) or 0) for status in factor_status.values()
        ),
        "blocking_issues": _blocking_issues(factor_status),
        "notes": [
            "This package is a Radar data-layer handoff for BACKTEST_LAB validation only.",
            "It does not change the daily Radar report, fixed PDF/LINE entry, Drive publishing, or BACKTEST_LAB formal model.",
            "valuation remains blocked until an official point-in-time source is ingested.",
        ],
    }

    readiness_path.parent.mkdir(parents=True, exist_ok=True)
    _write_json(readiness_path, payload)
    _write_csv(gap_path, GAP_FIELDS, gap_rows)
    _write_manifest(manifest_path, payload)
    return payload


def _missing_factor_status(factor_id: str, csv_file: Path, readiness_file: Path) -> dict[str, Any]:
    return {
        "ready": False,
        "status": "blocked",
        "source_validator_ready": False,
        "coverage_threshold_met": False,
        "source_mode": f"{factor_id}_missing",
        "source_start": "",
        "source_end": "",
        "coverage_ratio": 0.0,
        "fresh_coverage_ratio": 0.0,
        "future_data_violation_count": 0,
        "gap_count": len(CORE_STOCK_TICKERS),
        "blocking_issues": [f"{_relative(readiness_file)} is missing."],
        "warnings": [],
        "csv": _relative(csv_file),
        "readiness": _relative(readiness_file),
        "gap": "",
    }


def _valuation_blocked_status() -> dict[str, Any]:
    return {
        "ready": False,
        "status": "blocked",
        "source_validator_ready": False,
        "coverage_threshold_met": False,
        "source_mode": "valuation_point_in_time_blocked",
        "source_start": "",
        "source_end": "",
        "coverage_ratio": 0.0,
        "fresh_coverage_ratio": 0.0,
        "future_data_violation_count": 0,
        "gap_count": len(CORE_STOCK_TICKERS),
        "blocking_issues": [
            "No official point-in-time EPS/PE/PB source has been ingested for 2024-01-02~2026-05-26.",
            "The 2026-06-14 manual valuation snapshot must not be used to backfill historical dates.",
        ],
        "warnings": [],
        "csv": "",
        "readiness": "",
        "gap": "",
    }


def _blocking_issues(factor_status: dict[str, dict[str, Any]]) -> list[str]:
    issues = []
    for factor_id, status in factor_status.items():
        if status["ready"]:
            continue
        issue_text = "; ".join(str(issue) for issue in status.get("blocking_issues", []) if issue)
        issues.append(f"{factor_id}: {issue_text or status['status']}")
    return issues


def _read_source_gap_rows(*, factor_id: str, status: str, gap_file: Path) -> list[dict[str, str]]:
    if not gap_file.exists():
        return []
    rows = []
    with gap_file.open("r", encoding="utf-8-sig", newline="") as handle:
        for row in csv.DictReader(handle):
            rows.append(
                _gap_row(
                    factor_id=factor_id,
                    status=status,
                    symbol=row.get("symbol", ""),
                    ticker=row.get("ticker", ""),
                    date=row.get("date", ""),
                    reason=row.get("missing_reason") or row.get("gap_reason") or row.get("reason", ""),
                    source_file=gap_file,
                    notes=row.get("notes", ""),
                )
            )
    return rows


def _gap_row(
    *,
    factor_id: str,
    status: str,
    reason: str,
    source_file: str | Path,
    notes: str,
    symbol: str = "",
    ticker: str = "",
    date: str = "",
) -> dict[str, str]:
    return {
        "factor_id": factor_id,
        "status": status,
        "symbol": symbol,
        "ticker": ticker,
        "date": date,
        "gap_reason": reason,
        "source_file": _relative(source_file) if source_file else "",
        "notes": notes,
    }


def _write_manifest(path: Path, payload: dict[str, Any]) -> None:
    lines = [
        "# BACKTEST_LAB Factor Input Data Package 2024-2026",
        "",
        f"- package_status: {payload['source_mode']}",
        f"- ready: {str(payload['ready']).lower()}",
        f"- decision_layer: {payload['decision_layer']}",
        f"- active_in_trade_decision: {str(payload['active_in_trade_decision']).lower()}",
        f"- period: {payload['start_date']} to {payload['end_date']}",
        f"- expected_stock_tickers: {', '.join(payload['expected_stock_tickers'])}",
        "",
        "## Core Validator Source Paths",
    ]
    for factor_id, source_path in payload["core_validator_source_paths"].items():
        lines.append(f"- {factor_id}: `{source_path}`")
    lines.extend(["", "## Readiness"])
    for factor_id, status in payload["factor_status"].items():
        lines.append(
            "- "
            f"{factor_id}: status={status['status']}, "
            f"source_start={status['source_start'] or 'n/a'}, "
            f"source_end={status['source_end'] or 'n/a'}, "
            f"fresh_coverage_ratio={float(status['fresh_coverage_ratio']):.6f}, "
            f"coverage_threshold_met={str(status['coverage_threshold_met']).lower()}, "
            f"source_validator_ready={str(status['source_validator_ready']).lower()}, "
            f"future_data_violation_count={status['future_data_violation_count']}"
        )
    lines.extend(
        [
            "",
            "## Guardrails",
            "- This package is not a trade signal and is not active in the formal trade decision layer.",
            "- Valuation remains blocked because a point-in-time official source has not been ingested.",
            "- Do not use later manual snapshots to backfill historical valuation factors.",
        ]
    )
    path.write_text("\n".join(lines) + "\n", encoding="utf-8")


def _read_json(path: Path) -> dict[str, Any]:
    return json.loads(path.read_text(encoding="utf-8"))


def _write_json(path: Path, payload: dict[str, Any]) -> None:
    path.write_text(json.dumps(payload, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")


def _write_csv(path: Path, fieldnames: list[str], rows: list[dict[str, str]]) -> None:
    with path.open("w", encoding="utf-8-sig", newline="") as handle:
        writer = csv.DictWriter(handle, fieldnames=fieldnames)
        writer.writeheader()
        writer.writerows(rows)


def _relative(path: str | Path) -> str:
    path_obj = Path(path)
    try:
        return path_obj.as_posix()
    except TypeError:
        return str(path)
