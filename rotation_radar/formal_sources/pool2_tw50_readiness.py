from __future__ import annotations

import csv
import json
from datetime import datetime, timezone
from pathlib import Path
from typing import Any


POOL2_PROXY_FIELDS = [
    "snapshot_date",
    "effective_date",
    "end_date",
    "ticker",
    "name",
    "weight_pct",
    "source_file",
    "source_url_or_manual_note",
    "source_report_date",
    "download_method",
    "parser_status",
    "review_status",
    "reviewer",
    "is_proxy",
    "source_mode",
    "exact_tw50_official_constituents",
    "point_in_time_safe",
    "notes",
]

EXACT_TW50_FIELDS = [
    "effective_date",
    "end_date",
    "ticker",
    "name",
    "source",
    "source_updated_at",
    "evidence_uri",
    "evidence_type",
    "point_in_time_safe",
]


def build_pool2_tw50_readiness(
    *,
    output_dir: str | Path,
    core_coverage_dir: str | Path,
    intake_readiness_path: str | Path = "data/formal_sources/tw50_0050_holdings_manual_ledger_intake/manual_pdf_intake_readiness.json",
    phase3_checklist_path: str | Path = "data/formal_sources/tw50_0050_holdings_manual_ledger_phase3/source_acquisition_checklist.csv",
    phase4_search_readiness_path: str | Path = "data/formal_sources/tw50_0050_holdings_manual_ledger_phase4_drive_local_search/phase4_drive_local_search_readiness.json",
) -> dict[str, Any]:
    output = Path(output_dir)
    output.mkdir(parents=True, exist_ok=True)

    core_dir = Path(core_coverage_dir)
    coverage_rows = _read_rows(core_dir / "tw50_constituent_coverage_summary.csv")
    core_metadata = _read_json(core_dir / "metadata.json")
    intake_readiness = _read_json(Path(intake_readiness_path))
    phase4_search_readiness = _read_optional_json(Path(phase4_search_readiness_path))
    checklist_rows = _read_rows(Path(phase3_checklist_path))

    missing_required = _missing_required_sources(checklist_rows, intake_readiness)
    future_data_violation_count = 0
    exact_ready = _coverage_ready(coverage_rows)
    proxy_rows: list[dict[str, str]] = []
    proxy_ready = False

    status = "ready" if exact_ready else "blocked_waiting_user_files"
    blockers = []
    if not exact_ready:
        blockers.append("exact_tw50_constituents_ready=false: Core coverage remains below 95% for at least one period.")
    if missing_required:
        blockers.append(
            "yuanta_0050_holdings_proxy_ready=false: missing manual PDFs "
            + ", ".join(row["expected_filename"] for row in missing_required[:5])
        )
    if not proxy_ready:
        blockers.append("proxy_specific_readiness_ready=false: accepted holdings proxy rows=0.")

    readiness = {
        "generated_at": _utc_now_iso(),
        "task_id": "TASK-BACKTEST-CORE-POOL2-PIT-REPLAY-COVERAGE-20260623",
        "status": status,
        "ready": exact_ready,
        "formal_ready": exact_ready,
        "exact_tw50_official_constituents_ready": exact_ready,
        "yuanta_0050_holdings_proxy_ready": proxy_ready,
        "source_mode": "blocked_no_accepted_pit_rows",
        "is_proxy": False,
        "exact_tw50_official_constituents": True,
        "future_data_violation_count": future_data_violation_count,
        "core_coverage_dir": str(core_dir),
        "core_coverage_summary": coverage_rows,
        "core_source_row_count": core_metadata.get("source_row_count", 0),
        "core_source_effective_min": core_metadata.get("source_effective_min", ""),
        "core_source_effective_max": core_metadata.get("source_effective_max", ""),
        "manual_pdf_intake_status": intake_readiness.get("status", ""),
        "manual_pdf_dir": intake_readiness.get("pdf_dir", ""),
        "manual_pdfs_found": intake_readiness.get("pdfs_found", 0),
        "valid_pdf_header_count": intake_readiness.get("valid_pdf_header_count", 0),
        "missing_priority_one_files": intake_readiness.get("missing_priority_one_files", []),
        "phase4_drive_local_search_status": phase4_search_readiness.get("status", ""),
        "phase4_drive_local_search_blocker": phase4_search_readiness.get("blocker", ""),
        "accepted_proxy_rows": len(proxy_rows),
        "historical_snapshot_rows": len(proxy_rows),
        "missing_manual_source_count": len(missing_required),
        "blocking_issues": blockers,
        "next_actions": [
            "Place required historical Yuanta PDFs into the manual_pdfs intake folder using the expected filenames.",
            "Run python -m rotation_radar.formal_sources.build_tw50_holdings_manual_intake.",
            "Parse and manually review holdings rows before appending accepted proxy rows.",
            "Core must use proxy-specific readiness for Yuanta 0050 holdings proxy; do not pass proxy rows as exact official TW50 constituents.",
        ],
        "outputs": {
            "readiness": str(output / "pool2_tw50_readiness.json"),
            "coverage_gap_summary": str(output / "coverage_gap_summary.csv"),
            "manual_source_request": str(output / "manual_source_request.csv"),
            "0050_holdings_proxy_rows": str(output / "0050_holdings_proxy_rows.csv"),
            "tw50_constituents_pit_candidate": str(output / "tw50_constituents_pit_candidate.csv"),
            "manifest": str(output / "manifest.md"),
        },
    }

    _write_rows(output / "coverage_gap_summary.csv", _coverage_fields(coverage_rows), coverage_rows)
    _write_rows(output / "manual_source_request.csv", _manual_request_fields(), missing_required)
    _write_rows(output / "0050_holdings_proxy_rows.csv", POOL2_PROXY_FIELDS, proxy_rows)
    _write_rows(output / "tw50_constituents_pit_candidate.csv", EXACT_TW50_FIELDS, [])
    _write_json(output / "pool2_tw50_readiness.json", readiness)
    _write_manifest(output / "manifest.md", readiness)
    return readiness


def _coverage_ready(rows: list[dict[str, str]]) -> bool:
    return bool(rows) and all(float(row.get("coverage_ratio", "0") or 0) >= 0.95 for row in rows)


def _missing_required_sources(rows: list[dict[str, str]], intake: dict[str, Any]) -> list[dict[str, str]]:
    missing_priority_one = set(intake.get("missing_priority_one_files", []))
    output = []
    for row in rows:
        expected = row.get("expected_filename", "").strip()
        source_status = row.get("source_status", "").strip()
        if expected in missing_priority_one or source_status in {"source_pending", ""}:
            output.append(
                {
                    "period_id": row.get("period_id", ""),
                    "period_type": row.get("period_type", ""),
                    "target_snapshot_date": row.get("target_snapshot_date", ""),
                    "priority": row.get("priority", ""),
                    "expected_filename": expected,
                    "preferred_source": row.get("preferred_source", ""),
                    "reason": "missing_manual_pdf_or_not_accepted",
                    "required_action": "provide PDF, run intake, parse holdings, manual review, then mark accepted only after evidence is verified",
                }
            )
    return output


def _coverage_fields(rows: list[dict[str, str]]) -> list[str]:
    if rows:
        return list(rows[0].keys())
    return [
        "period",
        "start",
        "end",
        "checked_dates",
        "ready_dates",
        "gap_dates",
        "coverage_ratio",
        "minimum_active_count",
        "min_active_count",
        "max_active_count",
        "first_ready_date",
        "last_ready_date",
    ]


def _manual_request_fields() -> list[str]:
    return [
        "period_id",
        "period_type",
        "target_snapshot_date",
        "priority",
        "expected_filename",
        "preferred_source",
        "reason",
        "required_action",
    ]


def _read_json(path: Path) -> dict[str, Any]:
    return json.loads(path.read_text(encoding="utf-8"))


def _read_optional_json(path: Path) -> dict[str, Any]:
    if not path.exists():
        return {}
    return _read_json(path)


def _read_rows(path: Path) -> list[dict[str, str]]:
    with path.open("r", encoding="utf-8-sig", newline="") as handle:
        return [{key: str(value or "") for key, value in row.items()} for row in csv.DictReader(handle)]


def _write_rows(path: Path, fieldnames: list[str], rows: list[dict[str, str]]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("w", encoding="utf-8-sig", newline="") as handle:
        writer = csv.DictWriter(handle, fieldnames=fieldnames)
        writer.writeheader()
        writer.writerows(rows)


def _write_json(path: Path, payload: dict[str, Any]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(payload, ensure_ascii=False, indent=2), encoding="utf-8")


def _write_manifest(path: Path, readiness: dict[str, Any]) -> None:
    lines = [
        "# Pool2 TW50/0050 PIT Replay Readiness",
        "",
        f"Status: `{readiness['status']}`",
        f"Exact TW50 official constituents ready: `{readiness['exact_tw50_official_constituents_ready']}`",
        f"Yuanta 0050 holdings proxy ready: `{readiness['yuanta_0050_holdings_proxy_ready']}`",
        f"Future data violation count: `{readiness['future_data_violation_count']}`",
        "",
        "## Coverage Summary",
        "",
        _markdown_table(readiness["core_coverage_summary"]),
        "",
        "## Blocking Issues",
        "",
        *[f"- {item}" for item in readiness["blocking_issues"]],
        "",
        "## Required Manual Sources",
        "",
        "- Priority 1: `yuanta_0050_monthly_202201.pdf`",
        "- Priority 1: `yuanta_domestic_holdings_2022Q1.pdf`",
        "- Place files under `data/formal_sources/tw50_0050_holdings_manual_ledger_intake/manual_pdfs/`.",
        "",
        "## Core Boundary",
        "",
        "- `0050_holdings_proxy_rows.csv` is a proxy-specific interface and currently has zero accepted rows.",
        "- `tw50_constituents_pit_candidate.csv` is schema-only because no exact official PIT rows were acquired.",
        "- Core must not treat Yuanta holdings proxy rows as exact official TW50 constituents.",
        "",
        "## Next Commands",
        "",
        "```powershell",
        "python -m rotation_radar.formal_sources.build_tw50_holdings_manual_intake",
        "python -m rotation_radar.formal_sources.build_pool2_tw50_readiness --core-coverage-dir C:\\Users\\zergv\\Documents\\Codex\\2026-05-30\\ep05-chat-ai-stock-backtest-lab\\outputs\\pool2_tw50_pit_replay_coverage_20260623 --output-dir data\\formal_sources\\pool2_tw50_pit_replay_readiness_20260623",
        "```",
        "",
    ]
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text("\n".join(lines), encoding="utf-8")


def _markdown_table(rows: list[dict[str, str]]) -> str:
    if not rows:
        return "_No rows._"
    columns = list(rows[0].keys())
    output = [
        "| " + " | ".join(columns) + " |",
        "| " + " | ".join(["---"] * len(columns)) + " |",
    ]
    for row in rows:
        output.append("| " + " | ".join(str(row.get(column, "")) for column in columns) + " |")
    return "\n".join(output)


def _utc_now_iso() -> str:
    return datetime.now(timezone.utc).replace(microsecond=0).isoformat()
