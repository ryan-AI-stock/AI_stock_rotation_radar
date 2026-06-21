from __future__ import annotations

import csv
import json
from datetime import datetime, timezone
from pathlib import Path
from typing import Any


INTAKE_STATUS_FIELDS = [
    "period_id",
    "period_type",
    "target_snapshot_date",
    "priority",
    "expected_filename",
    "expected_path",
    "file_status",
    "byte_size",
    "pdf_header_status",
    "review_status",
    "next_action",
]


def build_tw50_holdings_manual_intake(
    *,
    checklist_path: str | Path = "data/formal_sources/tw50_0050_holdings_manual_ledger_phase3/source_acquisition_checklist.csv",
    pdf_dir: str | Path = "data/formal_sources/tw50_0050_holdings_manual_ledger_intake/manual_pdfs",
    output_dir: str | Path = "data/formal_sources/tw50_0050_holdings_manual_ledger_intake",
) -> dict[str, Any]:
    checklist = _read_checklist(Path(checklist_path))
    pdf_root = Path(pdf_dir)
    out_root = Path(output_dir)
    rows = [_build_status_row(row, pdf_root) for row in checklist]

    found_count = sum(1 for row in rows if row["file_status"] == "found")
    valid_pdf_count = sum(1 for row in rows if row["pdf_header_status"] == "valid_pdf_header")
    priority_one_rows = [row for row in rows if row["priority"] == "1"]
    missing_priority_one = [row["expected_filename"] for row in priority_one_rows if row["file_status"] != "found"]
    invalid_priority_one = [
        row["expected_filename"]
        for row in priority_one_rows
        if row["file_status"] == "found" and row["pdf_header_status"] != "valid_pdf_header"
    ]
    status = "intake_ready_for_manual_review" if valid_pdf_count else "blocked_waiting_user_files"

    readiness = {
        "generated_at": _utc_now_iso(),
        "status": status,
        "ready": False,
        "formal_ready": False,
        "source_mode": "yuanta_0050_holdings_proxy",
        "is_proxy": True,
        "exact_tw50_official_constituents": False,
        "checklist_path": str(Path(checklist_path)),
        "pdf_dir": str(pdf_root),
        "target_count": len(rows),
        "pdfs_found": found_count,
        "valid_pdf_header_count": valid_pdf_count,
        "priority_one_target_count": len(priority_one_rows),
        "missing_priority_one_files": missing_priority_one,
        "invalid_priority_one_files": invalid_priority_one,
        "accepted_rows": 0,
        "historical_snapshot_rows": 0,
        "next_action": _next_action(valid_pdf_count, missing_priority_one, invalid_priority_one),
    }

    _write_csv(out_root / "manual_pdf_intake_status.csv", INTAKE_STATUS_FIELDS, rows)
    _write_json(out_root / "manual_pdf_intake_readiness.json", readiness)
    _write_manifest(out_root / "manifest.md", readiness)
    return readiness


def _build_status_row(source: dict[str, str], pdf_root: Path) -> dict[str, str]:
    expected_filename = source["expected_filename"]
    expected_path = pdf_root / expected_filename
    if expected_path.exists():
        file_status = "found"
        byte_size = str(expected_path.stat().st_size)
        pdf_header_status = _pdf_header_status(expected_path)
        review_status = "ready_for_parser_review" if pdf_header_status == "valid_pdf_header" else "blocked_invalid_pdf"
        next_action = (
            "run parser/manual review; do not mark accepted until source date and holdings rows are verified"
            if pdf_header_status == "valid_pdf_header"
            else "replace with a valid PDF file"
        )
    else:
        file_status = "missing"
        byte_size = "0"
        pdf_header_status = "not_checked"
        review_status = "source_pending"
        next_action = "place the expected PDF in the manual_pdfs folder"
    return {
        "period_id": source["period_id"],
        "period_type": source["period_type"],
        "target_snapshot_date": source["target_snapshot_date"],
        "priority": source["priority"],
        "expected_filename": expected_filename,
        "expected_path": str(expected_path),
        "file_status": file_status,
        "byte_size": byte_size,
        "pdf_header_status": pdf_header_status,
        "review_status": review_status,
        "next_action": next_action,
    }


def _read_checklist(path: Path) -> list[dict[str, str]]:
    required = ["period_id", "period_type", "target_snapshot_date", "priority", "expected_filename"]
    with path.open("r", encoding="utf-8-sig", newline="") as handle:
        reader = csv.DictReader(handle)
        if reader.fieldnames is None:
            raise ValueError(f"{path} is missing a header")
        missing = [field for field in required if field not in reader.fieldnames]
        if missing:
            raise ValueError(f"{path} missing fields: {', '.join(missing)}")
        rows = [{field: str(row.get(field, "")).strip() for field in required} for row in reader]
    if not rows:
        raise ValueError(f"{path} has no source targets")
    for row in rows:
        if not row["expected_filename"].lower().endswith(".pdf"):
            raise ValueError(f"expected_filename must be a PDF: {row['expected_filename']}")
    return rows


def _pdf_header_status(path: Path) -> str:
    with path.open("rb") as handle:
        header = handle.read(5)
    return "valid_pdf_header" if header == b"%PDF-" else "invalid_pdf_header"


def _next_action(valid_pdf_count: int, missing_priority_one: list[str], invalid_priority_one: list[str]) -> str:
    if invalid_priority_one:
        return "Replace invalid priority-1 PDF files before parser/manual review."
    if missing_priority_one:
        return "Acquire priority-1 PDFs before parser/manual review can begin."
    if valid_pdf_count:
        return "Run parser/manual review for found PDFs; keep formal_ready=false until rows are reviewed."
    return "Place historical Yuanta PDF files into the manual_pdfs folder."


def _write_csv(path: Path, fieldnames: list[str], rows: list[dict[str, str]]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("w", encoding="utf-8-sig", newline="") as handle:
        writer = csv.DictWriter(handle, fieldnames=fieldnames)
        writer.writeheader()
        writer.writerows(rows)


def _write_json(path: Path, payload: dict[str, Any]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(payload, ensure_ascii=False, indent=2), encoding="utf-8")


def _write_manifest(path: Path, readiness: dict[str, Any]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    content = "\n".join(
        [
            "# TW50/0050 Manual PDF Intake Manifest",
            "",
            f"Status: `{readiness['status']}`",
            "",
            "Files:",
            "",
            "- `manual_pdf_intake_status.csv`",
            "- `manual_pdf_intake_readiness.json`",
            "- `manual_pdfs/README.md`",
            "- `manual_pdfs/.gitignore`",
            "",
            "This intake checker only verifies whether expected historical Yuanta PDF files exist locally.",
            "It does not parse holdings rows, write the manual ledger, or mark any source as formal-ready.",
            "",
            "Data boundary:",
            "",
            "- `source_mode=yuanta_0050_holdings_proxy`",
            "- `is_proxy=true`",
            "- `exact_tw50_official_constituents=false`",
            "",
            f"Next action: {readiness['next_action']}",
            "",
        ]
    )
    path.write_text(content, encoding="utf-8")


def _utc_now_iso() -> str:
    return datetime.now(timezone.utc).replace(microsecond=0).isoformat()
