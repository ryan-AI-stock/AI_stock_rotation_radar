from __future__ import annotations

import csv
import json
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

from .theme_membership_evidence_v2 import EVIDENCE_FIELDS


PERIODS = [
    {"period": "2022", "start_date": "2022-01-03", "end_date": "2022-12-30"},
    {"period": "2023", "start_date": "2023-01-03", "end_date": "2023-12-29"},
    {"period": "2024", "start_date": "2024-01-02", "end_date": "2024-12-31"},
    {"period": "2025", "start_date": "2025-01-02", "end_date": "2025-12-31"},
    {"period": "2026_ytd", "start_date": "2026-01-02", "end_date": "2026-05-26"},
]

PRICE_COVERAGE_THRESHOLD = 0.95
MEMBERSHIP_COVERAGE_THRESHOLD = 0.95


def build_pool3_radar_readiness(
    *,
    output_dir: str | Path,
    theme_map_path: str | Path = "data/theme_map.csv",
    formal_universe_path: str | Path = "data/history_replay/formal_grade_2021_2023/formal_universe.csv",
    memory_v1_path: str | Path = "data/formal_sources/date_aware_theme_membership_memory_v1.csv",
    v2_ledger_path: str | Path = "data/formal_sources/theme_membership_evidence_v2.csv",
    v2_readiness_path: str | Path = "data/formal_sources/date_aware_theme_membership_v2_readiness.json",
    price_cache_dir: str | Path,
    update_v2_live_files: bool = False,
) -> dict[str, Any]:
    output = Path(output_dir)
    output.mkdir(parents=True, exist_ok=True)

    theme_rows = _read_rows(Path(theme_map_path))
    formal_rows = _read_rows(Path(formal_universe_path))
    existing_ledger = _read_rows(Path(v2_ledger_path))
    accepted_rows = _accepted_v2_rows(existing_ledger)
    accepted_by_symbol = {row["symbol"]: row for row in accepted_rows}

    for row in _memory_v1_to_v2_rows(Path(memory_v1_path)):
        accepted_by_symbol.setdefault(row["symbol"], row)
    accepted_rows = [accepted_by_symbol[symbol] for symbol in sorted(accepted_by_symbol)]

    formal_symbols = {row["symbol"]: row for row in formal_rows}
    accepted_formal_symbols = sorted(symbol for symbol in accepted_by_symbol if symbol in formal_symbols)
    blocked_membership = [
        {
            "symbol": row["symbol"],
            "name": row.get("name", ""),
            "theme": row.get("theme", ""),
            "gap_reason": "missing_accepted_date_aware_v2_evidence",
            "required_evidence": "accepted dated source evidence with effective_start, source_date, source_url, and usable_for_formal_replay=true",
        }
        for row in formal_rows
        if row["symbol"] not in accepted_by_symbol
    ]
    future_violations = _future_data_violations(accepted_rows)
    membership_coverage = len(accepted_formal_symbols) / len(formal_rows) if formal_rows else 0.0
    theme_membership_ready = (
        membership_coverage >= MEMBERSHIP_COVERAGE_THRESHOLD
        and len(blocked_membership) == 0
        and future_violations == 0
    )

    coverage_rows, skipped_rows = _price_coverage(theme_rows, Path(price_cache_dir))
    price_ready = all(float(row["price_cache_coverage_ratio"]) >= PRICE_COVERAGE_THRESHOLD for row in coverage_rows)
    formal_top3_ready = theme_membership_ready and price_ready
    blockers = []
    if not theme_membership_ready:
        blockers.append(
            "theme_membership_v2_ready=false: "
            f"accepted_formal_symbols={len(accepted_formal_symbols)}/{len(formal_rows)}"
        )
    if not price_ready:
        low = [
            f"{row['period']}={row['price_cache_coverage_ratio']}"
            for row in coverage_rows
            if float(row["price_cache_coverage_ratio"]) < PRICE_COVERAGE_THRESHOLD
        ]
        blockers.append("price_cache_coverage_below_95pct: " + ";".join(low))
    if future_violations:
        blockers.append(f"future_data_violation_count={future_violations}")

    readiness = {
        "created_at": _utc_now_iso(),
        "status": "ready" if formal_top3_ready else "partial_price_ready_membership_blocked" if price_ready else "partial_blocked",
        "formal_top3_ready": formal_top3_ready,
        "formal_top3_source_mode": "date_aware_v2_full" if formal_top3_ready else "formal_blocked",
        "theme_membership_v2_ready": theme_membership_ready,
        "theme_membership_v2_formal_top3_status": "formal_ready" if formal_top3_ready else "formal_blocked",
        "accepted_evidence_row_count": len(accepted_rows),
        "usable_for_formal_replay_count": len(accepted_rows),
        "accepted_formal_universe_symbol_count": len(accepted_formal_symbols),
        "formal_universe_symbol_count": len(formal_rows),
        "date_aware_membership_coverage_ratio": round(membership_coverage, 8),
        "blocked_membership_symbol_count": len(blocked_membership),
        "future_data_violation_count": future_violations,
        "price_cache_dir": str(Path(price_cache_dir)),
        "price_cache_coverage_by_year": coverage_rows,
        "price_cache_skipped_row_count": len(skipped_rows),
        "blocking_issues": blockers,
        "warnings": [
            "This readiness package is for BACKTEST_LAB Core formal challenger validation only.",
            "It does not modify the daily public Radar report, PDF/HTML layout, Drive publish, LINE entry, or workflow.",
            "Current/static theme maps remain research-only unless backed by accepted date-aware evidence.",
        ],
    }

    _write_rows(output / "accepted_theme_membership_v2.csv", EVIDENCE_FIELDS, accepted_rows)
    _write_rows(output / "blocked_theme_membership_v2_gap.csv", ["symbol", "name", "theme", "gap_reason", "required_evidence"], blocked_membership)
    _write_rows(output / "price_cache_coverage_by_year.csv", list(coverage_rows[0]) if coverage_rows else [], coverage_rows)
    _write_rows(
        output / "skipped_members_report.csv",
        ["period", "symbol", "name", "theme", "ticker_candidates", "reason"],
        skipped_rows,
    )
    _write_json(output / "readiness_manifest.json", readiness)
    _write_manifest_md(output / "manifest.md", readiness)

    if update_v2_live_files:
        merged_ledger = _merge_ledger(existing_ledger, accepted_rows)
        _write_rows(Path(v2_ledger_path), EVIDENCE_FIELDS, merged_ledger)
        v2_readiness = _build_v2_readiness(readiness)
        _write_json(Path(v2_readiness_path), v2_readiness)

    return readiness


def _accepted_v2_rows(rows: list[dict[str, str]]) -> list[dict[str, str]]:
    return [
        {field: row.get(field, "") for field in EVIDENCE_FIELDS}
        for row in rows
        if row.get("review_status") == "accepted" and row.get("usable_for_formal_replay", "").lower() == "true"
    ]


def _memory_v1_to_v2_rows(path: Path) -> list[dict[str, str]]:
    if not path.exists():
        return []
    output = []
    for row in _read_rows(path):
        if not _is_memory_row_usable(row):
            continue
        output.append(
            {
                "evidence_id": f"TMEM-V2-MEMORY-{row['symbol']}-001",
                "symbol": row["symbol"],
                "ticker": _ticker(row["symbol"]),
                "exchange": "TWSE",
                "name": row["name"],
                "theme": row["theme"],
                "subtheme": row["theme"],
                "membership_role": "formal_universe_member",
                "effective_start": row["effective_start"],
                "effective_end": row.get("effective_end", ""),
                "source_date": row["source_date"],
                "source_type": row["source_type"],
                "source_title": row["notes"][:120],
                "source_url": row["source_url"],
                "source_publisher": _publisher_from_source_type(row["source_type"]),
                "source_license_status": "public_source_reference_only",
                "evidence_quote_or_summary": row["notes"],
                "confidence": row["confidence"],
                "confidence_reason": "Normalized from date_aware_theme_membership_memory_v1; row has dated source evidence and non-static source type.",
                "collector": "AI_stock_rotation_radar",
                "review_status": "accepted",
                "reviewer": "AI_stock_rotation_radar",
                "reviewed_at": "2026-06-23",
                "usable_for_formal_replay": "true",
                "notes": "Phase 2 normalized accepted evidence. Still partial because full-universe coverage is below threshold.",
            }
        )
    return output


def _is_memory_row_usable(row: dict[str, str]) -> bool:
    required = ["symbol", "name", "theme", "effective_start", "source_date", "source_type", "source_url", "confidence"]
    if any(not row.get(field, "").strip() for field in required):
        return False
    if row["source_type"] in {"", "current_static_map", "theme_map", "static_theme_map"}:
        return False
    if row["confidence"] not in {"high", "medium", "low"}:
        return False
    return _parse_date(row["effective_start"]) <= _parse_date(row["source_date"])


def _price_coverage(theme_rows: list[dict[str, str]], cache_dir: Path) -> tuple[list[dict[str, Any]], list[dict[str, str]]]:
    coverage_rows = []
    skipped_rows = []
    for period in PERIODS:
        resolved = 0
        period_skipped = []
        for row in theme_rows:
            candidates = _ticker_candidates(row["symbol"])
            matching = [cache_dir / f"{ticker.replace('.', '_')}.csv" for ticker in candidates]
            if any(_cache_covers(path, period["start_date"], period["end_date"]) for path in matching):
                resolved += 1
            else:
                period_skipped.append(
                    {
                        "period": period["period"],
                        "symbol": row["symbol"],
                        "name": row.get("name", ""),
                        "theme": row.get("theme", ""),
                        "ticker_candidates": "|".join(candidates),
                        "reason": "cache_missing_or_range_not_covered",
                    }
                )
        total = len(theme_rows)
        skipped_rows.extend(period_skipped)
        coverage_rows.append(
            {
                "period": period["period"],
                "start_date": period["start_date"],
                "end_date": period["end_date"],
                "member_count": total,
                "resolved_member_count": resolved,
                "skipped_member_count": len(period_skipped),
                "price_cache_coverage_ratio": round(resolved / total, 6) if total else 0.0,
            }
        )
    return coverage_rows, skipped_rows


def _cache_covers(path: Path, start_date: str, end_date: str) -> bool:
    if not path.exists():
        return False
    dates = []
    with path.open("r", encoding="utf-8-sig", newline="") as handle:
        for row in csv.DictReader(handle):
            date = row.get("date", "").strip()
            close = _float(row.get("close", "0"))
            volume = _float(row.get("volume", "0"))
            if date and close > 0 and volume > 0:
                dates.append(date)
    if not dates:
        return False
    start_gap = (_parse_date(min(dates)) - _parse_date(start_date)).days
    end_gap = (_parse_date(end_date) - _parse_date(max(dates))).days
    return start_gap <= 10 and end_gap <= 10


def _future_data_violations(rows: list[dict[str, str]]) -> int:
    violations = 0
    for row in rows:
        try:
            if _parse_date(row["effective_start"]) > _parse_date(row["source_date"]):
                violations += 1
        except (KeyError, ValueError):
            violations += 1
    return violations


def _merge_ledger(existing_rows: list[dict[str, str]], accepted_rows: list[dict[str, str]]) -> list[dict[str, str]]:
    existing_by_id = {row.get("evidence_id", ""): {field: row.get(field, "") for field in EVIDENCE_FIELDS} for row in existing_rows}
    for row in accepted_rows:
        existing_by_id[row["evidence_id"]] = {field: row.get(field, "") for field in EVIDENCE_FIELDS}
    return [existing_by_id[key] for key in sorted(existing_by_id)]


def _build_v2_readiness(pool3_readiness: dict[str, Any]) -> dict[str, Any]:
    return {
        "ready": False,
        "source_mode": "evidence_queue_phase2_partial",
        "formal_top3_status": "formal_blocked",
        "gap_symbol_count": int(pool3_readiness["blocked_membership_symbol_count"]),
        "queued_symbol_count": int(pool3_readiness["blocked_membership_symbol_count"]),
        "sample_evidence_row_count": int(pool3_readiness["accepted_evidence_row_count"]),
        "accepted_evidence_row_count": int(pool3_readiness["accepted_evidence_row_count"]),
        "usable_for_formal_replay_count": int(pool3_readiness["usable_for_formal_replay_count"]),
        "formal_universe_symbol_count": int(pool3_readiness["formal_universe_symbol_count"]),
        "date_aware_membership_coverage_ratio": float(pool3_readiness["date_aware_membership_coverage_ratio"]),
        "future_data_violation_count": int(pool3_readiness["future_data_violation_count"]),
        "blocking_issues": pool3_readiness["blocking_issues"],
        "warnings": [
            "Phase 2 partial includes accepted dated evidence rows, but full-universe coverage is still below formal threshold.",
            "formal_top3 remains blocked until accepted evidence coverage reaches the formal threshold and Core revalidates.",
        ],
    }


def _read_rows(path: Path) -> list[dict[str, str]]:
    with path.open("r", encoding="utf-8-sig", newline="") as handle:
        return [{key: str(value).strip() for key, value in row.items()} for row in csv.DictReader(handle)]


def _write_rows(path: Path, fieldnames: list[str], rows: list[dict[str, Any]]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("w", encoding="utf-8-sig", newline="") as handle:
        writer = csv.DictWriter(handle, fieldnames=fieldnames)
        writer.writeheader()
        writer.writerows(rows)


def _write_json(path: Path, payload: dict[str, Any]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(payload, ensure_ascii=False, indent=2), encoding="utf-8")


def _write_manifest_md(path: Path, readiness: dict[str, Any]) -> None:
    lines = [
        "# Pool3 Radar Formal Readiness",
        "",
        f"- status: `{readiness['status']}`",
        f"- formal_top3_ready: `{readiness['formal_top3_ready']}`",
        f"- theme_membership_v2_ready: `{readiness['theme_membership_v2_ready']}`",
        f"- accepted_evidence_row_count: {readiness['accepted_evidence_row_count']}",
        f"- date_aware_membership_coverage_ratio: {readiness['date_aware_membership_coverage_ratio']}",
        f"- future_data_violation_count: {readiness['future_data_violation_count']}",
        "",
        "## Price Coverage",
        "",
    ]
    for row in readiness["price_cache_coverage_by_year"]:
        lines.append(f"- {row['period']}: {row['resolved_member_count']}/{row['member_count']} = {row['price_cache_coverage_ratio']}")
    lines.extend(["", "## Blockers", ""])
    lines.extend([f"- {item}" for item in readiness["blocking_issues"]] or ["- none"])
    path.write_text("\n".join(lines) + "\n", encoding="utf-8")


def _ticker(symbol: str) -> str:
    return f"{symbol}.TW"


def _ticker_candidates(symbol: str) -> list[str]:
    return [f"{symbol}.TW", f"{symbol}.TWO"]


def _publisher_from_source_type(source_type: str) -> str:
    if source_type.startswith("company_"):
        return "company official source"
    if source_type == "underwriting_prospectus":
        return "underwriting prospectus"
    return "dated public source"


def _parse_date(value: str) -> datetime.date:
    return datetime.strptime(value, "%Y-%m-%d").date()


def _float(value: str | None) -> float:
    try:
        return float(str(value or "0").replace(",", ""))
    except ValueError:
        return 0.0


def _utc_now_iso() -> str:
    return datetime.now(timezone.utc).replace(microsecond=0).isoformat()
