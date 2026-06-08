from __future__ import annotations

import csv
import json
from datetime import datetime, timezone
from pathlib import Path
from typing import Any


FULL_MEMBERSHIP_FIELDS = [
    "symbol",
    "ticker",
    "exchange",
    "name",
    "theme",
    "effective_start",
    "effective_end",
    "source_date",
    "source_type",
    "source_url",
    "confidence",
    "evidence_note",
    "usable_for_formal_top3",
]

FULL_GAP_FIELDS = [
    "symbol",
    "ticker",
    "exchange",
    "name",
    "theme",
    "role",
    "gap_reason",
    "required_evidence",
    "needs_manual_review",
    "research_only_fallback",
    "checked_at",
]

VALID_CONFIDENCE = {"high", "medium", "low"}
STATIC_SOURCE_TYPES = {"", "current_static_map", "theme_map", "static_theme_map"}


def build_full_date_aware_membership(
    *,
    output_path: str | Path,
    gap_path: str | Path,
    readiness_path: str | Path,
    formal_universe_path: str | Path = "data/history_replay/formal_grade_2021_2023/formal_universe.csv",
    market_universe_path: str | Path = "data/market_universe.generated.csv",
    source_files: list[str | Path] | None = None,
    start_date: str = "2022-01-03",
    end_date: str = "2023-12-29",
) -> dict[str, Any]:
    source_files = source_files or ["data/formal_sources/date_aware_theme_membership_memory_v1.csv"]
    formal_rows = _read_formal_universe(Path(formal_universe_path))
    market_by_symbol = _read_market_universe(Path(market_universe_path))
    evidence_by_symbol = _read_evidence_rows(source_files)

    usable_rows: list[dict[str, str]] = []
    gap_rows: list[dict[str, str]] = []
    checked_at = _utc_now_iso()
    for item in formal_rows:
        symbol = item["symbol"]
        market = market_by_symbol.get(symbol, {})
        evidence = evidence_by_symbol.get(symbol)
        if evidence and _is_usable_evidence(evidence):
            exchange = market.get("market", "")
            usable_rows.append(
                {
                    "symbol": symbol,
                    "ticker": _ticker(symbol, exchange),
                    "exchange": exchange,
                    "name": item["name"],
                    "theme": item["theme"],
                    "effective_start": evidence["effective_start"],
                    "effective_end": evidence.get("effective_end", ""),
                    "source_date": evidence["source_date"],
                    "source_type": evidence["source_type"],
                    "source_url": evidence["source_url"],
                    "confidence": evidence["confidence"],
                    "evidence_note": evidence.get("notes", evidence.get("evidence_note", "")),
                    "usable_for_formal_top3": "yes",
                }
            )
        else:
            gap_rows.append(
                {
                    "symbol": symbol,
                    "ticker": _ticker(symbol, market.get("market", "")),
                    "exchange": market.get("market", ""),
                    "name": item["name"],
                    "theme": item["theme"],
                    "role": item["role"],
                    "gap_reason": _gap_reason(evidence),
                    "required_evidence": "dated company filing, dated product/revenue note, dated research note, or archived radar theme definition with source_date <= first snapshot date used",
                    "needs_manual_review": "yes",
                    "research_only_fallback": "current theme_map.csv may be used only for research-only replay, not formal top3 backtest",
                    "checked_at": checked_at,
                }
            )

    _write_rows(Path(output_path), FULL_MEMBERSHIP_FIELDS, usable_rows)
    _write_rows(Path(gap_path), FULL_GAP_FIELDS, gap_rows)
    readiness = _build_readiness(
        start_date=start_date,
        end_date=end_date,
        formal_count=len(formal_rows),
        usable_count=len(usable_rows),
        gap_count=len(gap_rows),
    )
    _write_json(Path(readiness_path), readiness)
    return readiness


def validate_full_date_aware_membership(
    *,
    membership_path: str | Path,
    gap_path: str | Path,
    readiness_path: str | Path,
) -> dict[str, Any]:
    rows = _read_required_rows(Path(membership_path), FULL_MEMBERSHIP_FIELDS)
    _read_required_rows(Path(gap_path), FULL_GAP_FIELDS)
    for row in rows:
        _validate_membership_row(row)

    readiness = _read_json(Path(readiness_path))
    required = {
        "ready",
        "source_mode",
        "start_date",
        "end_date",
        "formal_universe_symbol_count",
        "date_aware_row_count",
        "gap_symbol_count",
        "coverage_ratio",
        "future_data_violation_count",
        "blocking_issues",
        "warnings",
    }
    missing = sorted(required - set(readiness))
    if missing:
        raise ValueError(f"readiness missing required fields: {', '.join(missing)}")
    if readiness["source_mode"] not in {"date_aware_full", "date_aware_full_blocked"}:
        raise ValueError(f"unsupported source_mode: {readiness['source_mode']}")
    if readiness["ready"] and readiness["source_mode"] != "date_aware_full":
        raise ValueError("ready=true requires source_mode=date_aware_full")
    if not readiness["ready"] and readiness["source_mode"] != "date_aware_full_blocked":
        raise ValueError("ready=false requires source_mode=date_aware_full_blocked")
    if readiness["future_data_violation_count"] != 0:
        raise ValueError("future_data_violation_count must be zero")
    if not readiness["ready"] and not readiness["blocking_issues"]:
        raise ValueError("blocked readiness requires blocking_issues")
    return readiness


def _build_readiness(*, start_date: str, end_date: str, formal_count: int, usable_count: int, gap_count: int) -> dict[str, Any]:
    coverage_ratio = usable_count / formal_count if formal_count else 0.0
    full_ready = coverage_ratio >= 0.95 and gap_count == 0
    return {
        "ready": full_ready,
        "source_mode": "date_aware_full" if full_ready else "date_aware_full_blocked",
        "start_date": start_date,
        "end_date": end_date,
        "formal_universe_symbol_count": formal_count,
        "date_aware_row_count": usable_count,
        "gap_symbol_count": gap_count,
        "coverage_ratio": round(coverage_ratio, 8),
        "future_data_violation_count": 0,
        "blocking_issues": [] if full_ready else ["date_aware_theme_membership_full_universe_incomplete"],
        "warnings": [] if full_ready else [
            "Only symbols with dated evidence are usable for formal top3 replay.",
            "The remaining symbols require manual dated evidence collection; current static theme_map.csv is research-only.",
            "Formal top3 capital-flow package must remain formal_blocked until full-universe membership coverage is sufficient.",
        ],
    }


def _read_formal_universe(path: Path) -> list[dict[str, str]]:
    with path.open("r", encoding="utf-8-sig", newline="") as handle:
        return [
            {
                "symbol": row.get("symbol", "").strip(),
                "name": row.get("name", "").strip(),
                "theme": row.get("theme", "").strip(),
                "role": row.get("role", "").strip(),
            }
            for row in csv.DictReader(handle)
            if row.get("symbol", "").strip()
        ]


def _read_market_universe(path: Path) -> dict[str, dict[str, str]]:
    with path.open("r", encoding="utf-8-sig", newline="") as handle:
        return {row.get("symbol", "").strip(): row for row in csv.DictReader(handle) if row.get("symbol", "").strip()}


def _read_evidence_rows(paths: list[str | Path]) -> dict[str, dict[str, str]]:
    output: dict[str, dict[str, str]] = {}
    for path_value in paths:
        path = Path(path_value)
        if not path.exists():
            continue
        with path.open("r", encoding="utf-8-sig", newline="") as handle:
            for row in csv.DictReader(handle):
                symbol = row.get("symbol", "").strip()
                if symbol and symbol not in output:
                    output[symbol] = {key: str(value).strip() for key, value in row.items()}
    return output


def _is_usable_evidence(row: dict[str, str]) -> bool:
    required = ["symbol", "name", "theme", "effective_start", "source_date", "source_type", "source_url", "confidence"]
    if any(not row.get(field, "").strip() for field in required):
        return False
    if row["source_type"] in STATIC_SOURCE_TYPES:
        return False
    if row["confidence"] not in VALID_CONFIDENCE:
        return False
    _parse_iso_date(row["effective_start"])
    _parse_iso_date(row["source_date"])
    if row.get("effective_end"):
        _parse_iso_date(row["effective_end"])
    return True


def _validate_membership_row(row: dict[str, str]) -> None:
    missing = [field for field in FULL_MEMBERSHIP_FIELDS if field != "effective_end" and not row.get(field)]
    if missing:
        raise ValueError(f"membership row {row.get('symbol', '')} missing fields: {', '.join(missing)}")
    if row["confidence"] not in VALID_CONFIDENCE:
        raise ValueError(f"invalid confidence for {row['symbol']}: {row['confidence']}")
    if row["source_type"] in STATIC_SOURCE_TYPES:
        raise ValueError(f"static source is not allowed for {row['symbol']}")
    effective_start = _parse_iso_date(row["effective_start"])
    source_date = _parse_iso_date(row["source_date"])
    if effective_start > source_date:
        raise ValueError(f"effective_start after source_date for {row['symbol']}")
    if row["usable_for_formal_top3"] != "yes":
        raise ValueError(f"usable_for_formal_top3 must be yes for {row['symbol']}")


def _gap_reason(evidence: dict[str, str] | None) -> str:
    if evidence is None:
        return "missing_date_aware_evidence"
    try:
        usable = _is_usable_evidence(evidence)
    except ValueError:
        usable = False
    if not usable:
        return "invalid_or_incomplete_date_aware_evidence"
    return "unknown_gap"


def _read_required_rows(path: Path, expected_fields: list[str]) -> list[dict[str, str]]:
    with path.open("r", encoding="utf-8-sig", newline="") as handle:
        reader = csv.DictReader(handle)
        if reader.fieldnames != expected_fields:
            raise ValueError(f"{path} header mismatch")
        return [{field: str(row.get(field, "")).strip() for field in expected_fields} for row in reader]


def _ticker(symbol: str, exchange: str) -> str:
    if exchange == "TWSE":
        return f"{symbol}.TW"
    if exchange == "TPEx":
        return f"{symbol}.TWO"
    return symbol


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


def _parse_iso_date(value: str):
    return datetime.strptime(value, "%Y-%m-%d").date()


def _utc_now_iso() -> str:
    return datetime.now(timezone.utc).replace(microsecond=0).isoformat()
