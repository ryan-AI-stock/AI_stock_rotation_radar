from __future__ import annotations

import csv
import json
from datetime import datetime, timezone
from pathlib import Path
from typing import Any


QUEUE_FIELDS = [
    "queue_id",
    "batch_id",
    "priority",
    "symbol",
    "ticker",
    "exchange",
    "name",
    "theme",
    "subtheme",
    "membership_role",
    "gap_reason",
    "required_evidence",
    "recommended_source_types",
    "collection_status",
    "assigned_to",
    "review_status",
    "evidence_id",
    "notes",
    "created_at",
    "updated_at",
]

EVIDENCE_FIELDS = [
    "evidence_id",
    "symbol",
    "ticker",
    "exchange",
    "name",
    "theme",
    "subtheme",
    "membership_role",
    "effective_start",
    "effective_end",
    "source_date",
    "source_type",
    "source_title",
    "source_url",
    "source_publisher",
    "source_license_status",
    "evidence_quote_or_summary",
    "confidence",
    "confidence_reason",
    "collector",
    "review_status",
    "reviewer",
    "reviewed_at",
    "usable_for_formal_replay",
    "notes",
]

GAP_FIELDS_REQUIRED = ["symbol", "ticker", "exchange", "name", "theme", "role", "gap_reason", "required_evidence"]
THEME_PRIORITY = {
    "PCB/載板": 1,
    "CPO/矽光子": 2,
    "AI伺服器/ODM": 3,
    "電源/BBU": 4,
    "ASIC/IP": 5,
    "車用電子": 6,
    "機器人/自動化": 7,
    "記憶體": 8,
}
FORMAL_SOURCE_TYPES = {
    "mops_company_filing",
    "annual_report_segment",
    "company_annual_report",
    "company_news_release",
    "investor_conference_material",
    "company_product_page_archived",
    "monthly_revenue_note",
    "dated_industry_report",
    "dated_news_article",
    "underwriting_prospectus",
    "internal_archived_radar_theme_definition",
}
NON_FORMAL_DRAFT_SOURCE_TYPES = {"source_pending", "current_static_theme_map"}
VALID_REVIEW_STATUSES = {"draft", "reviewed", "accepted", "rejected", "expired", "needs_license_check"}
VALID_CONFIDENCE = {"high", "medium", "low"}


def build_theme_membership_evidence_v2(
    *,
    gap_path: str | Path = "data/formal_sources/date_aware_theme_membership_full_2022_2023_gap.csv",
    queue_path: str | Path = "data/formal_sources/theme_membership_evidence_queue_v2.csv",
    ledger_path: str | Path = "data/formal_sources/theme_membership_evidence_v2.csv",
    readiness_path: str | Path = "data/formal_sources/date_aware_theme_membership_v2_readiness.json",
    batch_size: int = 10,
    sample_size: int = 5,
) -> dict[str, Any]:
    gap_rows = _read_gap_rows(Path(gap_path))
    now = _utc_now_iso()
    queue_rows = _build_queue_rows(gap_rows, batch_size=batch_size, now=now)
    sample_rows = _build_sample_ledger_rows(queue_rows[:sample_size], now=now)
    readiness = _build_readiness(queue_rows=queue_rows, sample_rows=sample_rows, batch_size=batch_size)

    _write_rows(Path(queue_path), QUEUE_FIELDS, queue_rows)
    _write_rows(Path(ledger_path), EVIDENCE_FIELDS, sample_rows)
    _write_json(Path(readiness_path), readiness)
    return readiness


def validate_theme_membership_evidence_v2(
    *,
    queue_path: str | Path = "data/formal_sources/theme_membership_evidence_queue_v2.csv",
    ledger_path: str | Path = "data/formal_sources/theme_membership_evidence_v2.csv",
    readiness_path: str | Path = "data/formal_sources/date_aware_theme_membership_v2_readiness.json",
    formal_top3_readiness_path: str | Path = "data/history_replay/formal_top3_capital_flow_2022_2023/top3_capital_flow_readiness.json",
) -> dict[str, Any]:
    queue_rows = _read_required_rows(Path(queue_path), QUEUE_FIELDS)
    ledger_rows = _read_required_rows(Path(ledger_path), EVIDENCE_FIELDS)
    readiness = _read_json(Path(readiness_path))

    _validate_unique_ids(queue_rows, "queue_id")
    _validate_unique_ids([row for row in ledger_rows if row["evidence_id"]], "evidence_id")
    for row in queue_rows:
        _validate_queue_row(row)
    for row in ledger_rows:
        _validate_ledger_row(row)

    if readiness.get("ready") is not False:
        raise ValueError("v2 readiness must remain ready=false until full-universe evidence coverage is accepted")
    source_mode = readiness.get("source_mode")
    if source_mode not in {"evidence_queue_phase1_partial", "evidence_queue_phase2_partial"}:
        raise ValueError("unexpected v2 source_mode")
    if source_mode == "evidence_queue_phase1_partial" and readiness.get("usable_for_formal_replay_count") != 0:
        raise ValueError("Phase 0/1 must not create usable formal evidence")
    if source_mode == "evidence_queue_phase2_partial":
        accepted_rows = [row for row in ledger_rows if row["review_status"] == "accepted" and row["usable_for_formal_replay"].lower() == "true"]
        expected_accepted = int(readiness.get("accepted_evidence_row_count", 0) or 0)
        expected_usable = int(readiness.get("usable_for_formal_replay_count", 0) or 0)
        if len(accepted_rows) != expected_accepted or len(accepted_rows) != expected_usable:
            raise ValueError("Phase 2 accepted/usable readiness counts do not match ledger rows")
    if readiness.get("formal_top3_status") != "formal_blocked":
        raise ValueError("formal_top3_status must remain formal_blocked")
    if Path(formal_top3_readiness_path).exists():
        formal_top3 = _read_json(Path(formal_top3_readiness_path))
        if formal_top3.get("ready") is not False or formal_top3.get("source_mode") != "formal_blocked":
            raise ValueError("formal_top3 readiness was unexpectedly released")
    return readiness


def _build_queue_rows(gap_rows: list[dict[str, str]], *, batch_size: int, now: str) -> list[dict[str, str]]:
    sorted_rows = sorted(
        gap_rows,
        key=lambda row: (THEME_PRIORITY.get(row["theme"], 99), row["symbol"]),
    )
    output: list[dict[str, str]] = []
    for index, row in enumerate(sorted_rows, start=1):
        batch_no = ((index - 1) // batch_size) + 1
        queue_id = f"TMEMQ-V2-B{batch_no:02d}-{row['symbol']}-{_theme_code(row['theme'])}"
        output.append(
            {
                "queue_id": queue_id,
                "batch_id": f"batch_{batch_no:02d}",
                "priority": str(THEME_PRIORITY.get(row["theme"], 99)),
                "symbol": row["symbol"],
                "ticker": row["ticker"],
                "exchange": row["exchange"],
                "name": row["name"],
                "theme": row["theme"],
                "subtheme": row["role"],
                "membership_role": "watchlist",
                "gap_reason": row["gap_reason"],
                "required_evidence": row["required_evidence"],
                "recommended_source_types": "mops_company_filing;annual_report_segment;investor_conference_material;company_product_page_archived;monthly_revenue_note;dated_news_article",
                "collection_status": "queued",
                "assigned_to": "",
                "review_status": "draft",
                "evidence_id": "",
                "notes": "Needs dated evidence before formal replay. Current static theme_map remains research-only.",
                "created_at": now,
                "updated_at": now,
            }
        )
    for row in output[:5]:
        row["collection_status"] = "sample_schema_checked"
        row["notes"] = "Phase 1 sample row selected to verify queue and review flow; still not formal evidence."
    return output


def _build_sample_ledger_rows(queue_rows: list[dict[str, str]], *, now: str) -> list[dict[str, str]]:
    output: list[dict[str, str]] = []
    for row in queue_rows:
        evidence_id = f"TMEM-V2-SAMPLE-{row['symbol']}-{_theme_code(row['theme'])}-001"
        row["evidence_id"] = evidence_id
        output.append(
            {
                "evidence_id": evidence_id,
                "symbol": row["symbol"],
                "ticker": row["ticker"],
                "exchange": row["exchange"],
                "name": row["name"],
                "theme": row["theme"],
                "subtheme": row["subtheme"],
                "membership_role": row["membership_role"],
                "effective_start": "",
                "effective_end": "",
                "source_date": "",
                "source_type": "source_pending",
                "source_title": "",
                "source_url": "",
                "source_publisher": "",
                "source_license_status": "unknown",
                "evidence_quote_or_summary": "Phase 1 sample row created to verify ledger/review schema; dated source evidence has not been collected yet.",
                "confidence": "low",
                "confidence_reason": "No source collected yet; sample is not usable for formal replay.",
                "collector": "AI_stock_rotation_radar",
                "review_status": "draft",
                "reviewer": "",
                "reviewed_at": "",
                "usable_for_formal_replay": "false",
                "notes": f"Created at {now}. Do not convert to accepted until dated source_url/source_date/effective_start are reviewed.",
            }
        )
    return output


def _build_readiness(*, queue_rows: list[dict[str, str]], sample_rows: list[dict[str, str]], batch_size: int) -> dict[str, Any]:
    theme_counts: dict[str, int] = {}
    for row in queue_rows:
        theme_counts[row["theme"]] = theme_counts.get(row["theme"], 0) + 1
    batch_count = ((len(queue_rows) - 1) // batch_size) + 1 if queue_rows else 0
    return {
        "ready": False,
        "source_mode": "evidence_queue_phase1_partial",
        "formal_top3_status": "formal_blocked",
        "gap_symbol_count": len(queue_rows),
        "queued_symbol_count": len(queue_rows),
        "sample_evidence_row_count": len(sample_rows),
        "accepted_evidence_row_count": 0,
        "usable_for_formal_replay_count": 0,
        "batch_size": batch_size,
        "batch_count": batch_count,
        "theme_gap_counts": theme_counts,
        "batch_strategy": [
            "Process queue by blocker count first: PCB/載板, CPO/矽光子, AI伺服器/ODM, 電源/BBU, ASIC/IP, 車用電子, 機器人/自動化, 記憶體.",
            "Collect 10 symbols per batch after the 5-symbol schema sample; keep rows draft until reviewed.",
            "Prefer company/MOPS/annual report/investor material sources; news is supporting evidence only.",
            "Do not regenerate formal_top3 as ready until accepted evidence coverage is sufficient and future-data checks pass.",
        ],
        "blocking_issues": [
            "no_accepted_v2_evidence_yet",
            "61 formal universe symbols still require dated source review",
            "formal_top3 remains blocked until v2 evidence is accepted and normalized",
        ],
        "warnings": [
            "Phase 0/1 only creates queue and draft sample ledger rows.",
            "Draft sample rows use source_pending and usable_for_formal_replay=false.",
            "This package does not change daily report content, ranking logic, fixed PDF, LINE entry, or publish workflow.",
        ],
    }


def _validate_queue_row(row: dict[str, str]) -> None:
    if row["review_status"] not in VALID_REVIEW_STATUSES:
        raise ValueError(f"invalid queue review_status for {row['queue_id']}: {row['review_status']}")
    if row["collection_status"] not in {"queued", "sample_schema_checked", "collecting", "blocked", "done"}:
        raise ValueError(f"invalid collection_status for {row['queue_id']}: {row['collection_status']}")
    if not row["required_evidence"]:
        raise ValueError(f"queue row missing required_evidence: {row['queue_id']}")


def _validate_ledger_row(row: dict[str, str]) -> None:
    if row["review_status"] not in VALID_REVIEW_STATUSES:
        raise ValueError(f"invalid ledger review_status for {row['evidence_id']}: {row['review_status']}")
    if row["confidence"] not in VALID_CONFIDENCE:
        raise ValueError(f"invalid confidence for {row['evidence_id']}: {row['confidence']}")
    source_type = row["source_type"]
    if source_type not in FORMAL_SOURCE_TYPES | NON_FORMAL_DRAFT_SOURCE_TYPES:
        raise ValueError(f"invalid source_type for {row['evidence_id']}: {source_type}")
    usable = row["usable_for_formal_replay"].lower() == "true"
    if usable:
        if row["review_status"] != "accepted":
            raise ValueError(f"usable evidence must be accepted: {row['evidence_id']}")
        if source_type in NON_FORMAL_DRAFT_SOURCE_TYPES:
            raise ValueError(f"usable evidence cannot use draft source type: {row['evidence_id']}")
        for field in ("effective_start", "source_date", "source_url", "source_title", "source_publisher"):
            if not row[field]:
                raise ValueError(f"usable evidence missing {field}: {row['evidence_id']}")
    else:
        if row["review_status"] == "accepted":
            raise ValueError(f"accepted evidence must be usable or explicitly rejected/expired: {row['evidence_id']}")


def _read_gap_rows(path: Path) -> list[dict[str, str]]:
    rows = _read_required_rows(path, None)
    missing = [field for field in GAP_FIELDS_REQUIRED if field not in rows.fieldnames]
    if missing:
        raise ValueError(f"{path} missing fields: {', '.join(missing)}")
    return [{field: str(row.get(field, "")).strip() for field in GAP_FIELDS_REQUIRED} for row in rows.rows]


class _CsvRows:
    def __init__(self, *, fieldnames: list[str] | None, rows: list[dict[str, str]]) -> None:
        self.fieldnames = fieldnames or []
        self.rows = rows


def _read_required_rows(path: Path, expected_fields: list[str] | None) -> _CsvRows | list[dict[str, str]]:
    with path.open("r", encoding="utf-8-sig", newline="") as handle:
        reader = csv.DictReader(handle)
        if expected_fields is not None and reader.fieldnames != expected_fields:
            raise ValueError(f"{path} header mismatch")
        rows = [{key: str(value).strip() for key, value in row.items()} for row in reader]
    if expected_fields is None:
        return _CsvRows(fieldnames=reader.fieldnames, rows=rows)
    return [{field: row.get(field, "") for field in expected_fields} for row in rows]


def _validate_unique_ids(rows: list[dict[str, str]], field: str) -> None:
    values = [row[field] for row in rows if row.get(field)]
    if len(values) != len(set(values)):
        raise ValueError(f"duplicate {field} detected")


def _write_rows(path: Path, fieldnames: list[str], rows: list[dict[str, str]]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("w", encoding="utf-8-sig", newline="") as handle:
        writer = csv.DictWriter(handle, fieldnames=fieldnames)
        writer.writeheader()
        writer.writerows(rows)


def _read_json(path: Path) -> dict[str, Any]:
    return json.loads(path.read_text(encoding="utf-8"))


def _write_json(path: Path, payload: dict[str, Any]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(payload, ensure_ascii=False, indent=2), encoding="utf-8")


def _theme_code(theme: str) -> str:
    mapping = {
        "PCB/載板": "PCB",
        "CPO/矽光子": "CPO",
        "AI伺服器/ODM": "AISERVER",
        "電源/BBU": "POWERBBU",
        "ASIC/IP": "ASICIP",
        "車用電子": "AUTO",
        "機器人/自動化": "ROBOTICS",
        "記憶體": "MEMORY",
    }
    return mapping.get(theme, "THEME")


def _utc_now_iso() -> str:
    return datetime.now(timezone.utc).replace(microsecond=0).isoformat()
